"""Generate Whisper transcripts for YouTube episodes and upsert them keyed on youtube_id"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import tempfile
from difflib import SequenceMatcher
from pathlib import Path

from sqlalchemy import select

from bot.database import SessionLocal
from bot.models import Episode, EpisodeTranscript
from bot.scripts.card_links import fetch_set_cards, tag_text

log = logging.getLogger(__name__)

SKIP_CATEGORIES = {"Draft", "Sealed", "Guest"}
SENTENCE_MAX_SPAN = 60.0
SUBTOPIC_CHAPTER_GAP = 30
SENTENCE_BOUNDARY = re.compile(r"(?<=[.?!…])\s+")
MULETILLAS = re.compile(r"\b(uh+|um+|erm+|hmm+)\b[,]?\s*", re.I)
STUTTER_ANY = re.compile(r"\b(\w+)(?:[,.]?\s+\1\b){2,}", re.I)
STUTTER_WORDS = "i|a|the|and|so|it|is|that|you|no|yeah|yep|yup|well|but|to|of|we"
STUTTER_FILLER = re.compile(rf"\b({STUTTER_WORDS})(?:[,.]?\s+\1\b)+", re.I)
WHISPER_MODEL = "large-v3"
WHISPER_PROMPT = "Alright, welcome everybody. Let's talk about the format today, and go through it step by step."
SOURCE = f"whisper-{WHISPER_MODEL}"

STRUCTURE_PROMPT = (
    "Below are numbered sentences from a Magic: The Gathering podcast transcript. Do two things.\n"
    "1. Split into SUBTOPICS. A subtopic is one train of thought or point, finer than a chapter but coarser than "
    "a sentence (aim for one every 30 to 90 seconds of talk). For each, give the starting sentence number and a "
    "short 3 to 6 word title in Title Case that names the point. Start a subtopic on the sentence that opens the "
    "new point. Never start one on a sentence that concludes, sums up, or transitions out of the previous point; "
    "those trailing lines belong to the subtopic they close. The starting sentence must itself introduce the "
    "titled point and name or set up what the title says. If the sentence at a boundary is a short reaction or "
    "wrap-up of the previous point (for example 'Really sweet card.', 'So that card's great.', 'So don't "
    "underlook that one.') and does not introduce the new point, start the subtopic on the next sentence and "
    "leave that trailing sentence with the previous subtopic.\n"
    "2. Mark PARAGRAPH breaks for readability, roughly every 3 to 5 sentences.\n"
    "Return ONLY JSON: {\"subtopics\": [{\"start\": <int>, \"title\": <str>}], \"paragraphs\": [<int>, ...]}. "
    "Sentence 0 starts both.\n\n"
)

RESTORE_MIN_WORDS = 40


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
    parser.add_argument("--no-structure", action="store_true", help="Skip chapter headings and Claude subtopics")
    parser.add_argument("--no-restore", action="store_true", help="Skip punctuation restore of run-on stretches")
    parser.add_argument("--no-cards", action="store_true", help="Skip card-name detection and linking")
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
    units = [{"t": round(start), "text": text} for text, start in _sentences(whisper_segments)]
    if not args.no_restore:
        units = _restore_runons(units)
    if args.no_structure:
        segments = [{"t": unit["t"], "text": unit["text"]} for unit in units]
    else:
        chapters = _fetch_chapters(youtube_id, cookie_args)
        segments = _structure(units, chapters)
        headings = sum(1 for s in segments if s.get("heading"))
        subheadings = sum(1 for s in segments if s.get("subheading"))
        log.info(f"[{youtube_id}] {len(segments)} paragraphs, {headings} chapters, {subheadings} subtopics")
    for segment in segments:
        segment["text"] = _clean_text(segment["text"])
    if not args.no_cards:
        set_code = session.execute(select(Episode.set_code).where(Episode.youtube_id == youtube_id)).scalar()
        _link_cards(segments, set_code)
    word_count = sum(len(segment["text"].split()) for segment in segments)
    _upsert(session, youtube_id, segments, word_count)
    log.info(f"[{youtube_id}] wrote {len(segments)} segments, {word_count} words")


def _link_cards(segments: list[dict], set_code: str | None) -> None:
    if not set_code:
        return
    try:
        card_names = fetch_set_cards(set_code.lower())
    except Exception as exc:
        log.warning(f"card linking skipped for set {set_code}: {exc}")
        return
    linked = 0
    for segment in segments:
        corrected, cards = tag_text(segment["text"], card_names)
        segment["text"] = corrected
        if cards:
            segment["cards"] = cards
            linked += len(cards)
    log.info(f"linked {linked} card mentions from set {set_code}")


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
            "--no_repeat_ngram_size", "4",
            "--word_timestamps", "True",
            "--initial_prompt", WHISPER_PROMPT,
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


def _sentences(whisper_segments: list[dict], max_span: float = SENTENCE_MAX_SPAN) -> list[tuple[str, float]]:
    words = [(w["word"], w["start"]) for segment in whisper_segments for w in (segment.get("words") or [])]
    if not words:
        return _sentences_by_segment(whisper_segments, max_span)
    units: list[tuple[str, float]] = []
    carry = ""
    carry_start: float | None = None
    for text, start in words:
        if carry_start is None:
            carry_start = start
        carry += text
        parts = SENTENCE_BOUNDARY.split(carry)
        if len(parts) > 1:
            *complete, carry = parts
            for sentence in complete:
                units.append((sentence.strip(), carry_start))
            carry_start = start
        elif carry.strip() and start - carry_start >= max_span:
            units.append((carry.strip(), carry_start))
            carry = ""
            carry_start = None
    if carry.strip():
        units.append((carry.strip(), carry_start if carry_start is not None else 0.0))
    return units


def _sentences_by_segment(whisper_segments: list[dict], max_span: float) -> list[tuple[str, float]]:
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


def _clean_text(text: str) -> str:
    text = MULETILLAS.sub("", text)
    text = STUTTER_ANY.sub(r"\1", text)
    text = STUTTER_FILLER.sub(r"\1", text)
    sentences = SENTENCE_BOUNDARY.split(text)
    kept: list[str] = []
    for sentence in sentences:
        if kept and sentence.strip() and _is_duplicate(sentence, kept[-1]):
            continue
        kept.append(sentence)
    text = re.sub(r"\s{2,}", " ", " ".join(kept))
    return re.sub(r"\s+([.,?!])", r"\1", text).strip()


def _is_duplicate(sentence: str, previous: str) -> bool:
    current = re.sub(r"[^a-z0-9 ]", "", sentence.lower()).strip()
    prior = re.sub(r"[^a-z0-9 ]", "", previous.lower()).strip()
    if current == prior:
        return True
    if len(current.split()) < 10 or len(prior.split()) < 10:
        return False
    return SequenceMatcher(None, current, prior).ratio() >= 0.85


def _restore_runons(units: list[dict]) -> list[dict]:
    model = _load_punct_model()
    if not model:
        return units
    restored: list[dict] = []
    for unit in units:
        if len(unit["text"].split()) <= RESTORE_MIN_WORDS:
            restored.append(unit)
            continue
        fixed = _clean_restored(" ".join(model.restore(_strip_punct(unit["text"]))))
        for sentence in SENTENCE_BOUNDARY.split(fixed):
            text = sentence.strip()
            if text:
                restored.append({"t": unit["t"], "text": text})
    return restored


_PUNCT_MODEL = None


def _load_punct_model():
    global _PUNCT_MODEL
    if _PUNCT_MODEL is None:
        try:
            from bot.scripts.punctuation import PunctuationRestorer
        except ImportError:
            log.warning("punctuation deps missing, skipping restore (need onnxruntime, sentencepiece, huggingface_hub)")
            _PUNCT_MODEL = False
            return _PUNCT_MODEL
        _PUNCT_MODEL = PunctuationRestorer.from_pretrained()
    return _PUNCT_MODEL


def _strip_punct(text: str) -> str:
    return re.sub(r"[.,?!;:…\"]", "", text).lower()


def _clean_restored(text: str) -> str:
    text = re.sub(r"\s+([.,?!;:])", r"\1", text)
    text = re.sub(r"[,]+\s*([.?!])", r"\1", text)
    text = re.sub(r"([.,?!;:])\1+", r"\1", text)
    return re.sub(r"\s{2,}", " ", text).strip()


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


def _structure(units: list[dict], chapters: list[dict]) -> list[dict]:
    heads = _chapter_heads(units, chapters)
    subtopics, paragraphs = _subtopics_and_paragraphs(units)
    chapter_times = [units[i]["t"] for i in heads]
    subtopics = {
        i: title for i, title in subtopics.items()
        if all(abs(units[i]["t"] - c) >= SUBTOPIC_CHAPTER_GAP for c in chapter_times)
    }
    para_starts = paragraphs | set(subtopics) | set(heads) | {0}

    segments: list[dict] = []
    current: dict | None = None
    for index, unit in enumerate(units):
        if index in para_starts or current is None:
            current = {"t": unit["t"], "text": unit["text"]}
            if index in heads:
                title, chapter_t = heads[index]
                current["heading"] = title
                current["head_t"] = unit["t"]
                current["t"] = chapter_t
            if index in subtopics:
                current["subheading"] = subtopics[index]
            segments.append(current)
        else:
            current["text"] = f"{current['text']} {unit['text']}"
    return segments


def _subtopics_and_paragraphs(units: list[dict]) -> tuple[dict[int, str], set[int]]:
    numbered = "\n".join(f"{i}: {unit['text']}" for i, unit in enumerate(units))
    result = subprocess.run(["claude", "-p", STRUCTURE_PROMPT + numbered], check=True, capture_output=True, text=True)
    match = re.search(r"\{.*\}", result.stdout, re.DOTALL)
    if not match:
        return {}, {0}
    data = json.loads(match.group(0))
    subtopics = {int(s["start"]): str(s["title"]).strip() for s in data.get("subtopics", [])}
    paragraphs = {int(i) for i in data.get("paragraphs", [])} | {0}
    return subtopics, {i for i in paragraphs if 0 <= i < len(units)}


def _chapter_heads(blocks: list[dict], chapters: list[dict]) -> dict[int, tuple[str, int]]:
    heads: dict[int, tuple[str, int]] = {}
    for chapter in sorted(chapters, key=lambda c: c.get("start_time") or 0.0):
        title = (chapter.get("title") or "").strip()
        if not title:
            continue
        start = chapter.get("start_time") or 0.0
        head_index = len(blocks) - 1
        for index, block in enumerate(blocks):
            if block["t"] >= start:
                head_index = index
                break
        while head_index in heads and head_index < len(blocks) - 1:
            head_index += 1
        heads[head_index] = (title, round(start))
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
