"""Diarize episodes with whisperx and label each speaker by first name"""
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
from bot.scripts.generate_transcripts import (
    _annotate_structure,
    _apply_known_terms,
    _claude_json,
    _download_audio,
    _download_audio_url,
    _tag_cards,
    _upsert,
)

log = logging.getLogger(__name__)

SOURCE = "whisper-large-v3-diarized"
DEFAULT_MAX_MINUTES = 180
MIN_SPEAKER_WORDS = 15
INTRO_TURNS = 20
PARAGRAPH_SENTENCES = 3
GENERIC_LABEL = re.compile(r"^(Host|Guest(?: \d+)?|Speaker \d+)$")

WHISPERX_BIN = os.environ.get("WHISPERX_BIN", str(Path.home() / "whisperx-proto/.venv/bin/whisperx"))
HF_TOKEN_FILE = os.environ.get("HF_TOKEN_FILE", str(Path.home() / "whisperx-proto/hf_token"))

ATTRIBUTION_PROMPT = (
    "You are labeling speakers in a Limited Level-Ups Magic: The Gathering podcast. "
    "The recurring hosts are Alex, Marc, and Abram. A guest is usually named in the episode title. "
    "Below is the episode title and the opening of the transcript with generic speaker labels. "
    "First decide if this is a single-person monologue (one host talking, no interview or conversation). "
    "If it is a monologue, set solo true. Otherwise map each generic label to the speaker's real FIRST "
    "NAME (Marc, not Marc Anderson); leave a label unchanged if you cannot determine its name.\n"
    'Return ONLY JSON: {"solo": <true|false>, "speakers": {"<label>": "<first name>", ...}}.\n\n'
    "TITLE: {title}\n\nOPENING:\n{intro}\n"
)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = _parse_args()
    failed: set[str] = set()
    while True:
        with SessionLocal() as session:
            target = _next_target(session, args, failed)
        if target is None:
            log.info("no episodes left to diarize")
            return
        key, title, audio_url, set_code = target
        log.info(f"[{key}] {title}")
        try:
            with SessionLocal() as session:
                _process(session, key, title, audio_url, set_code, args)
        except Exception as exc:
            log.warning(f"[{key}] failed, skipping: {exc}")
            failed.add(key)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diarize audio-only episodes (no youtube_id) with whisperx, then name speakers with a cheap "
        "Claude pass over the intro. With --youtube, diarize episodes from their YouTube audio and add chapters "
        "and card links. Needs the whisperx venv (WHISPERX_BIN) and a HuggingFace token (HF_TOKEN_FILE) whose "
        "account accepted pyannote/speaker-diarization-community-1. Writes to DATABASE_URL.",
    )
    parser.add_argument("--category", default="Guest", help="Episode category to diarize")
    parser.add_argument("--youtube-id", help="Diarize this episode only: its guid, or its youtube id with --youtube")
    parser.add_argument("--youtube", action="store_true", help="Diarize episodes that have a YouTube video")
    parser.add_argument("--max-minutes", type=int, default=DEFAULT_MAX_MINUTES, help="Skip episodes longer than this")
    parser.add_argument("--redo", action="store_true", help="Re-diarize episodes already transcribed")
    parser.add_argument("--no-attribution", action="store_true", help="Keep generic Host/Guest labels, skip Claude")
    parser.add_argument("--no-card-fix", action="store_true", help="With --youtube, skip the Claude card-name pass")
    return parser.parse_args()


def _next_target(session, args: argparse.Namespace, failed: set[str]) -> tuple[str, str, str, str | None] | None:
    if args.youtube:
        key = Episode.youtube_id
        done_query = select(EpisodeTranscript.youtube_id).where(EpisodeTranscript.source == SOURCE)
        query = select(key, Episode.title, Episode.audio_url, Episode.set_code).where(key.isnot(None))
    else:
        key = Episode.guid
        done_query = select(EpisodeTranscript.youtube_id)
        query = select(key, Episode.title, Episode.audio_url, Episode.set_code).where(
            Episode.youtube_id.is_(None), Episode.audio_url.isnot(None), Episode.audio_url != ""
        )
    if args.youtube_id:
        query = query.where(key == args.youtube_id)
    else:
        query = query.where(Episode.category == args.category, Episode.duration_seconds <= args.max_minutes * 60)
    query = query.order_by(Episode.duration_seconds)
    done = set(session.execute(done_query).scalars())
    for episode_key, title, audio_url, set_code in session.execute(query):
        if episode_key in failed:
            continue
        if episode_key in done and not args.redo:
            continue
        return episode_key, title, audio_url, set_code
    return None


def _process(session, key: str, title: str, audio_url: str, set_code: str | None, args: argparse.Namespace) -> None:
    with tempfile.TemporaryDirectory(prefix="diarize-") as tmp:
        workdir = Path(tmp)
        audio = _download_audio(key, workdir, []) if args.youtube else _download_audio_url(audio_url, workdir)
        whisper = _run_whisperx(audio, workdir)
    segments = _build_segments(whisper["segments"])
    if not args.no_attribution:
        _attribute_names(key, title, segments)
    if args.youtube:
        _annotate_structure(segments, key)
        _tag_cards(key, segments, set_code, args)
    _apply_known_terms(segments)
    word_count = sum(len(segment["text"].split()) for segment in segments)
    _upsert(session, key, segments, word_count, SOURCE)
    log.info(f"[{key}] wrote {len(segments)} paragraphs, {word_count} words")


def _run_whisperx(audio: Path, workdir: Path) -> dict:
    token = Path(HF_TOKEN_FILE).read_text().strip()
    subprocess.run(
        [WHISPERX_BIN, str(audio), "--model", "large-v3", "--language", "en", "--diarize",
         "--hf_token", token, "--compute_type", "float16", "--device", "cuda",
         "--output_dir", str(workdir), "--output_format", "json"],
        check=True,
    )
    return json.loads((workdir / f"{audio.stem}.json").read_text(encoding="utf-8"))


def _build_segments(raw: list[dict]) -> list[dict]:
    labels = _role_labels(raw)
    units = []
    for index, seg in enumerate(raw):
        text = (seg.get("text") or "").strip()
        role = labels[index]
        if text and role:
            units.append({"t": int(seg["start"]), "text": text, "speaker": role})

    segments: list[dict] = []
    run: list[dict] = []
    for unit in units:
        if run and run[-1]["speaker"] != unit["speaker"]:
            segments.extend(_paragraphs(run))
            run = []
        run.append(unit)
    segments.extend(_paragraphs(run))
    return segments


def _role_labels(raw: list[dict]) -> list[str | None]:
    words: dict[str, int] = {}
    for seg in raw:
        speaker = seg.get("speaker")
        words[speaker] = words.get(speaker, 0) + len((seg.get("text") or "").split())
    real = {speaker for speaker, count in words.items() if count >= MIN_SPEAKER_WORDS}

    names = ["Host", "Guest", "Guest 2", "Guest 3"]
    role_of: dict[str, str] = {}
    labels: list[str | None] = []
    last: str | None = None
    for seg in raw:
        speaker = seg.get("speaker")
        if speaker in real:
            if speaker not in role_of:
                role_of[speaker] = names[len(role_of)] if len(role_of) < len(names) else f"Speaker {len(role_of) + 1}"
            last = role_of[speaker]
        labels.append(last)
    return labels


def _paragraphs(run: list[dict]) -> list[dict]:
    out = []
    for start in range(0, len(run), PARAGRAPH_SENTENCES):
        group = run[start : start + PARAGRAPH_SENTENCES]
        out.append({"t": group[0]["t"], "text": " ".join(u["text"] for u in group), "speaker": group[0]["speaker"]})
    return out


def _attribute_names(guid: str, title: str, segments: list[dict]) -> None:
    generic = {s["speaker"] for s in segments if s.get("speaker") and GENERIC_LABEL.match(s["speaker"])}
    if not generic:
        return
    intro = "\n".join(f"{s.get('speaker', '?')}: {s['text'][:220]}" for s in segments[:INTRO_TURNS])
    prompt = ATTRIBUTION_PROMPT.replace("{title}", title).replace("{intro}", intro)
    raw = _claude_json(prompt, "attribution", guid)
    if raw is None:
        return
    data = json.loads(raw)
    if data.get("solo"):
        for segment in segments:
            segment.pop("speaker", None)
        log.info(f"[{guid}] solo monologue, speaker labels removed")
        return
    mapping = {k: v for k, v in data.get("speakers", {}).items() if v and not GENERIC_LABEL.match(v)}
    for segment in segments:
        if segment.get("speaker") in mapping:
            segment["speaker"] = mapping[segment["speaker"]]
    if mapping:
        log.info(f"[{guid}] named speakers {mapping}")


if __name__ == "__main__":
    main()
