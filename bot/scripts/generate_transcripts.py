"""Generate Whisper transcripts for YouTube episodes and upsert them keyed on youtube_id"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path

from sqlalchemy import select

from bot.database import SessionLocal
from bot.models import Episode, EpisodeTranscript

log = logging.getLogger(__name__)

SKIP_CATEGORIES = {"Draft", "Sealed"}
BLOCK_MIN_SECONDS = 25.0
BLOCK_MAX_SECONDS = 60.0
SENTENCE_BOUNDARY = re.compile(r"(?<=[.?!…])\s+")
WHISPER_MODEL = "large-v3"
SOURCE = f"whisper-{WHISPER_MODEL}"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = _parse_args()
    with SessionLocal() as session:
        targets = _select_targets(session, args)
        if not targets:
            log.info("no episodes to transcribe")
            return
        log.info(f"transcribing {len(targets)} episode(s)")
        for youtube_id, title in targets:
            _process_one(session, youtube_id, title, args)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Local-only, zero cost: yt-dlp pulls audio, whisper-ctranslate2 (GPU) transcribes, "
        "rows land in episode_transcripts. Point DATABASE_URL at prod to publish, local to test. "
        "Needs yt-dlp (with a deno JS runtime), whisper-ctranslate2 and ffmpeg on PATH.",
    )
    parser.add_argument("--youtube-id", action="append", default=[], help="Transcribe these ids only")
    parser.add_argument("--latest", type=int, help="Transcribe the N most recent eligible episodes")
    parser.add_argument("--redo", action="store_true", help="Overwrite episodes already transcribed")
    parser.add_argument("--cookies-file", help="Netscape cookies.txt for YouTube, only if a download is blocked")
    parser.add_argument("--device", default="cuda", choices=("cuda", "cpu"))
    parser.add_argument("--no-structure", action="store_true", help="Skip chapter headings and Claude paragraphs")
    return parser.parse_args()


def _select_targets(session, args: argparse.Namespace) -> list[tuple[str, str]]:
    done = set(session.execute(select(EpisodeTranscript.youtube_id)).scalars())
    query = select(Episode.youtube_id, Episode.title).where(Episode.youtube_id.isnot(None))
    if args.youtube_id:
        query = query.where(Episode.youtube_id.in_(args.youtube_id))
    else:
        query = query.where(Episode.category.notin_(SKIP_CATEGORIES))
    query = query.order_by(Episode.published_at.desc())

    targets: list[tuple[str, str]] = []
    for youtube_id, title in session.execute(query):
        if youtube_id in done and not args.redo:
            continue
        targets.append((youtube_id, title))
        if args.latest and len(targets) >= args.latest:
            break
    return targets


def _process_one(session, youtube_id: str, title: str, args: argparse.Namespace) -> None:
    log.info(f"[{youtube_id}] {title}")
    cookie_args = ["--cookies", args.cookies_file] if args.cookies_file else []
    with tempfile.TemporaryDirectory(prefix="llu-transcript-") as tmp:
        workdir = Path(tmp)
        audio = _download_audio(youtube_id, workdir, cookie_args)
        whisper_segments = _transcribe(audio, workdir, args.device)
    segments = _group_segments(whisper_segments)
    if not args.no_structure:
        chapters = _fetch_chapters(youtube_id, cookie_args)
        breaks = _paragraph_break_indices(segments)
        segments = _structure(segments, chapters, breaks)
        headings = sum(1 for s in segments if s.get("heading"))
        log.info(f"[{youtube_id}] structured into {len(segments)} paragraphs, {headings} headings")
    word_count = sum(len(block["text"].split()) for block in segments)
    _upsert(session, youtube_id, segments, word_count)
    log.info(f"[{youtube_id}] wrote {len(segments)} segments, {word_count} words")


def _download_audio(youtube_id: str, workdir: Path, cookie_args: list[str]) -> Path:
    output = workdir / "audio.%(ext)s"
    subprocess.run(
        [
            "yt-dlp",
            "--remote-components", "ejs:github",
            *cookie_args,
            "--extractor-args", "youtube:player_client=web_safari,mweb,tv",
            "-f", "bestaudio/best",
            "-x", "--audio-format", "mp3", "--audio-quality", "5",
            "-o", str(output),
            f"https://www.youtube.com/watch?v={youtube_id}",
        ],
        check=True,
    )
    return workdir / "audio.mp3"


def _transcribe(audio: Path, workdir: Path, device: str) -> list[dict]:
    env = os.environ.copy()
    cuda_libs = _cuda_lib_path()
    if cuda_libs:
        existing = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = f"{cuda_libs}:{existing}" if existing else cuda_libs
    subprocess.run(
        [
            "whisper-ctranslate2", str(audio),
            "--model", WHISPER_MODEL,
            "--device", device,
            "--compute_type", "float16" if device == "cuda" else "int8",
            "--vad_filter", "True",
            "--no_repeat_ngram_size", "3",
            "--language", "en",
            "--output_format", "json",
            "--output_dir", str(workdir),
        ],
        check=True,
        env=env,
    )
    payload = json.loads((workdir / f"{audio.stem}.json").read_text(encoding="utf-8"))
    return payload["segments"]


def _cuda_lib_path() -> str:
    root = Path.home() / ".local/share/uv/tools/whisper-ctranslate2"
    dirs = []
    for lib in ("cublas", "cudnn"):
        matches = list(root.glob(f"lib/python*/site-packages/nvidia/{lib}/lib"))
        if matches:
            dirs.append(str(matches[0]))
    return ":".join(dirs)


def _group_segments(whisper_segments: list[dict], min_span: float = BLOCK_MIN_SECONDS) -> list[dict]:
    blocks: list[dict] = []
    block_start = None
    block_texts: list[str] = []
    for text, start in _sentences(whisper_segments):
        if block_start is None:
            block_start = start
        if block_texts and start - block_start >= min_span:
            blocks.append({"t": round(block_start), "text": " ".join(block_texts)})
            block_start = start
            block_texts = []
        block_texts.append(text)
    if block_texts:
        blocks.append({"t": round(block_start), "text": " ".join(block_texts)})
    return blocks


def _sentences(whisper_segments: list[dict], max_span: float = BLOCK_MAX_SECONDS) -> list[tuple[str, float]]:
    units: list[tuple[str, float]] = []
    carry = ""
    carry_start = None
    for segment in whisper_segments:
        if carry_start is None:
            carry_start = segment["start"]
        carry = f"{carry} {segment['text'].strip()}".strip()
        parts = SENTENCE_BOUNDARY.split(carry)
        carry = parts.pop()
        for sentence in parts:
            units.append((sentence.strip(), carry_start))
            carry_start = segment["start"]
        if carry and segment["end"] - carry_start >= max_span:
            units.append((carry.strip(), carry_start))
            carry = ""
            carry_start = None
    if carry.strip():
        units.append((carry.strip(), carry_start if carry_start is not None else 0.0))
    return units


def _fetch_chapters(youtube_id: str, cookie_args: list[str]) -> list[dict]:
    result = subprocess.run(
        [
            "yt-dlp",
            "--remote-components", "ejs:github",
            *cookie_args,
            "--extractor-args", "youtube:player_client=web_safari,mweb,tv",
            "--skip-download", "--print", "%(chapters)j",
            f"https://www.youtube.com/watch?v={youtube_id}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    raw = result.stdout.strip()
    if not raw or raw in ("null", "NA"):
        return []
    return json.loads(raw)


def _paragraph_break_indices(blocks: list[dict]) -> set[int]:
    numbered = "\n".join(f"{i}: {block['text']}" for i, block in enumerate(blocks))
    prompt = (
        "Below are numbered transcript segments from a Magic: The Gathering podcast. Group them into "
        "readable paragraphs: a paragraph is a few consecutive segments on one point, and a new paragraph "
        "starts when the speaker moves to a new point. Return ONLY a JSON array of the segment numbers that "
        "begin a new paragraph, for example [0,3,7,12]. Do not return any text or the segments themselves.\n\n"
        + numbered
    )
    result = subprocess.run(["claude", "-p", prompt], check=True, capture_output=True, text=True)
    match = re.search(r"\[[\d,\s]*\]", result.stdout)
    if not match:
        return {0}
    indices = {int(n) for n in json.loads(match.group(0))}
    indices.add(0)
    return {i for i in indices if 0 <= i < len(blocks)}


def _structure(blocks: list[dict], chapters: list[dict], breaks: set[int]) -> list[dict]:
    heads = _chapter_heads(blocks, chapters)
    starts = set(breaks) | set(heads) | {0}
    paragraphs: list[dict] = []
    current: dict | None = None
    for index, block in enumerate(blocks):
        if index in starts or current is None:
            current = {"t": block["t"], "text": block["text"]}
            if index in heads:
                current["heading"] = heads[index]
            paragraphs.append(current)
        else:
            current["text"] = f"{current['text']} {block['text']}"
    return paragraphs


def _chapter_heads(blocks: list[dict], chapters: list[dict]) -> dict[int, str]:
    heads: dict[int, str] = {}
    for chapter in sorted(chapters, key=lambda c: c.get("start_time") or 0.0):
        title = (chapter.get("title") or "").strip()
        if not title:
            continue
        start = chapter.get("start_time") or 0.0
        head_index = len(blocks) - 1
        for index, block in enumerate(blocks):
            if block["t"] >= start - 3:
                head_index = index
                break
        while head_index in heads and head_index < len(blocks) - 1:
            head_index += 1
        heads[head_index] = title
    return heads


def _upsert(session, youtube_id: str, segments: list[dict], word_count: int) -> None:
    row = session.get(EpisodeTranscript, youtube_id)
    if row is None:
        row = EpisodeTranscript(youtube_id=youtube_id)
        session.add(row)
    row.segments = segments
    row.word_count = word_count
    row.source = SOURCE
    session.commit()


if __name__ == "__main__":
    main()
