"""Generate episode transcripts from YouTube captions (Whisper fallback) and upsert them keyed on youtube_id"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
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
SECTION_MIN_GAP = 60
SENTENCE_BOUNDARY = re.compile(r"(?<=[.?!…])\s+")
MULETILLAS = re.compile(r"\b(uh+|um+|erm+|hmm+)\b[,]?\s*", re.I)
STUTTER_ANY = re.compile(r"\b(\w+)(?:[,.]?\s+\1\b){2,}", re.I)
STUTTER_WORDS = "i|a|the|and|so|it|is|that|you|no|yeah|yep|yup|well|but|to|of|we"
STUTTER_FILLER = re.compile(rf"\b({STUTTER_WORDS})(?:[,.]?\s+\1\b)+", re.I)
WHISPER_MODEL = "large-v3"
WHISPER_PROMPT = "Alright, welcome everybody. Let's talk about the format today, and go through it step by step."
SOURCE = f"whisper-{WHISPER_MODEL}"
CAPTION_SOURCE = "youtube-caption"
CAPTION_RESTORED_SOURCE = "youtube-caption-restored"
CAPTION_PUNCT_MIN = 1.5
CAPTION_RETRY_WAIT = 600
_RATE_LIMITED = object()

CARD_FIX_PROMPT = (
    "You are given a Magic: The Gathering set's card list, then an auto-generated podcast transcript "
    "that misspells some card names. List EVERY distinct misspelled form of any card in the list, "
    "including partial and single-word references. Map each wrong form to the correctly spelled version "
    "of the SAME reference, preserving scope: a full multi-word attempt maps to the full correct name; "
    "a short or first-name reference maps to just that reference correctly spelled, never expanded. Fix "
    "spelling only. The transcript is phonetic, so a wrong form may be badly garbled (wrong vowels, "
    "split or merged words, homophones); match by sound and context to the closest card in the list. "
    'Each distinct wrong form once. Return ONLY JSON: {"fixes": [{"wrong": <exact misspelled text>, '
    '"right": <correct spelling, same scope>}]}. Skip correct references. Change nothing that is not a '
    "card name.\n\nCARD LIST:\n{cards}\n\nTRANSCRIPT:\n{text}\n"
)

KNOWN_TERMS = [
    (re.compile(r"\blimited level[-\s]?ups\b", re.I), "Limited Level-Ups"),
]

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
    "3. For each subtopic set \"section\": true only when it opens a major, self-contained part of the episode "
    "that a viewer would bookmark as a chapter, a clear shift to a new segment of the show, and you are highly "
    "confident. Most subtopics are not sections. Default to false, mark only a handful across the whole episode, "
    "and never mark two within a short span.\n"
    "Return ONLY JSON: {\"subtopics\": [{\"start\": <int>, \"title\": <str>, \"section\": <bool>}], "
    "\"paragraphs\": [<int>, ...]}. Sentence 0 starts both.\n\n"
)

RESTORE_MIN_WORDS = 40

CACHE_DIR = Path("cache/transcripts")
USAGE_LOG = Path("logs/transcript_usage.jsonl")
SPAWN_STAGGER_SECONDS = 5
CHAPTER_LOOKBACK_SECONDS = 12
CHAPTER_LOOKBACK_MAX = 2
CHAPTER_INTRO_OPENER = re.compile(
    r"^(?:next|now|the next|another|moving on|let'?s|let us|ok|okay|all ?right|alright|"
    r"so,?\s+(?:the\s+)?next|first|second|third|fourth|finally)\b",
    re.I,
)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = _parse_args()
    with SessionLocal() as session:
        if args.restructure:
            targets = _restructure_targets(args)
            if not targets:
                log.info("no cached episodes to restructure")
                return
            log.info(f"restructuring {len(targets)} cached episode(s)")
            for youtube_id in targets:
                _restructure_one(session, youtube_id, args)
            return
        targets = _select_targets(session, args)
        if not targets:
            log.info("no episodes to transcribe")
            return
        if args.workers > 1:
            _run_parallel(targets, args)
            return
        log.info(f"transcribing {len(targets)} episode(s)")
        for youtube_id, title in targets:
            if not _wait_for_usage(args):
                log.info("session usage at or above the limit, stopping (resume next run)")
                return
            while not _process_one(session, youtube_id, title, args):
                log.info(f"[{youtube_id}] captions rate-limited, waiting {CAPTION_RETRY_WAIT}s before retry")
                time.sleep(CAPTION_RETRY_WAIT)
                if not _wait_for_usage(args):
                    log.info("session usage at or above the limit, stopping (resume next run)")
                    return


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Local-only, zero cost. Default source is YouTube auto-captions (no GPU); Whisper is the "
        "fallback when no caption exists. Rows land in episode_transcripts. Point DATABASE_URL at prod to "
        "publish, local to test. Needs yt-dlp (with a deno JS runtime), the claude CLI and ffmpeg on PATH; "
        "the Whisper fallback also needs whisper-ctranslate2.",
    )
    parser.add_argument("--youtube-id", action="append", default=[], help="Transcribe these ids only")
    parser.add_argument("--latest", type=int, help="Transcribe the N most recent eligible episodes")
    parser.add_argument("--redo", action="store_true", help="Overwrite episodes already transcribed")
    parser.add_argument("--cookies-file", help="Netscape cookies.txt for YouTube, only if a download is blocked")
    parser.add_argument("--device", default="cuda", choices=("cuda", "cpu"))
    parser.add_argument("--workers", type=int, default=1, help="Backfill in N parallel worker processes")
    parser.add_argument(
        "--usage-limit",
        type=float,
        help="Hold before an episode once the active 5-hour window's ccusage cost reaches this many USD. "
        "Serial runs only; holds too if usage cannot be read. Calibrate from the percent shown in the Claude app",
    )
    parser.add_argument(
        "--usage-wait",
        type=int,
        help="With --usage-limit, sleep this many seconds and recheck instead of stopping, so the run "
        "throttles itself and keeps going as the window frees up",
    )
    parser.add_argument("--whisper", action="store_true", help="Force the Whisper audio path, ignore captions")
    parser.add_argument("--no-structure", action="store_true", help="Skip chapter headings and Claude subtopics")
    parser.add_argument("--no-restore", action="store_true", help="Skip punctuation restore of run-on stretches")
    parser.add_argument("--no-cards", action="store_true", help="Skip card-name detection and linking")
    parser.add_argument("--no-card-fix", action="store_true", help="Skip the Claude card-name correction pass")
    parser.add_argument(
        "--restructure",
        action="store_true",
        help="Re-run structuring from cached raw units, no download or Whisper (needs a prior cached run)",
    )
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


def _run_parallel(targets: list[tuple[str, str]], args: argparse.Namespace) -> None:
    ids = [youtube_id for youtube_id, _ in targets]
    workers = min(args.workers, len(ids))
    chunks = [ids[i::workers] for i in range(workers)]
    passthrough: list[str] = ["--workers", "1", "--device", args.device]
    for flag in ("redo", "whisper", "no_structure", "no_restore", "no_cards", "no_card_fix"):
        if getattr(args, flag):
            passthrough.append("--" + flag.replace("_", "-"))
    if args.cookies_file:
        passthrough += ["--cookies-file", args.cookies_file]
    log.info(f"backfill: {len(ids)} episodes across {workers} workers")
    procs: list[subprocess.Popen] = []
    for chunk in chunks:
        if not chunk:
            continue
        cmd = [sys.executable, "-m", "bot.scripts.generate_transcripts", *passthrough]
        for youtube_id in chunk:
            cmd += [f"--youtube-id={youtube_id}"]
        procs.append(subprocess.Popen(cmd))
        time.sleep(SPAWN_STAGGER_SECONDS)
    failures = sum(1 for proc in procs if proc.wait() != 0)
    log.info(f"backfill done: {len(ids)} episodes, {failures} worker(s) exited with errors")


def _under_usage_limit(limit_usd: float) -> bool:
    try:
        result = subprocess.run(
            ["npx", "-y", "ccusage@latest", "blocks", "--active", "--json"], check=True, capture_output=True, text=True
        )
    except Exception as exc:
        log.warning(f"usage check failed, treating as over the limit: {exc}")
        return False
    start = result.stdout.find("{")
    if start < 0:
        return False
    blocks = json.loads(result.stdout[start:]).get("blocks", [])
    active = next((block for block in blocks if block.get("isActive")), None)
    if not active:
        return True
    cost = active.get("costUSD", 0)
    log.info(f"active window at ${cost:.1f} of ${limit_usd:.1f} limit")
    return cost < limit_usd


def _wait_for_usage(args: argparse.Namespace) -> bool:
    while args.usage_limit and not _under_usage_limit(args.usage_limit):
        if not args.usage_wait:
            return False
        log.info(f"session usage at the limit, waiting {args.usage_wait}s before rechecking")
        time.sleep(args.usage_wait)
    return True


def _process_one(session, youtube_id: str, title: str, args: argparse.Namespace) -> bool:
    log.info(f"[{youtube_id}] {title}")
    cookie_args = ["--cookies", args.cookies_file] if args.cookies_file else []
    set_code = session.execute(select(Episode.set_code).where(Episode.youtube_id == youtube_id)).scalar()
    units, source = (None, SOURCE)
    if not args.whisper:
        caption = _caption_units(youtube_id, cookie_args)
        if caption is _RATE_LIMITED:
            return False
        if caption:
            units, source = caption
            log.info(f"[{youtube_id}] {len(units)} sentences from {source}")
    if units is None:
        with tempfile.TemporaryDirectory(prefix="llu-transcript-") as tmp:
            workdir = Path(tmp)
            audio = _download_audio(youtube_id, workdir, cookie_args)
            whisper_segments = _transcribe(audio, workdir, args.device)
        units = [{"t": round(start), "text": text} for text, start in _sentences(whisper_segments)]
        if not args.no_restore:
            units = _restore_runons(units)
        log.info(f"[{youtube_id}] {len(units)} sentences from {source}")
    chapters = _fetch_chapters(youtube_id, cookie_args)
    _write_cache(youtube_id, title, set_code, units, chapters, source)
    segments = _build_segments(youtube_id, units, chapters, set_code, args)
    word_count = sum(len(segment["text"].split()) for segment in segments)
    _upsert(session, youtube_id, segments, word_count, source)
    log.info(f"[{youtube_id}] wrote {len(segments)} segments, {word_count} words")
    return True


def _build_segments(youtube_id, units, chapters, set_code, args) -> list[dict]:
    if args.no_structure:
        segments = [{"t": unit["t"], "text": unit["text"]} for unit in units]
    else:
        segments = _structure(units, chapters, youtube_id)
        headings = sum(1 for s in segments if s.get("heading"))
        subheadings = sum(1 for s in segments if s.get("subheading"))
        log.info(f"[{youtube_id}] {len(segments)} paragraphs, {headings} chapters, {subheadings} subtopics")
    for segment in segments:
        segment["text"] = _clean_text(segment["text"])
    if not args.no_cards:
        card_names = _fetch_cards_safe(set_code)
        if card_names:
            if not args.no_card_fix:
                _fix_card_names(youtube_id, segments, card_names)
            _link_cards(segments, card_names)
    _apply_known_terms(segments)
    return segments


def _restructure_targets(args: argparse.Namespace) -> list[str]:
    if args.youtube_id:
        return [yid for yid in args.youtube_id if (CACHE_DIR / f"{yid}.json").exists()]
    return sorted(path.stem for path in CACHE_DIR.glob("*.json"))


def _restructure_one(session, youtube_id: str, args: argparse.Namespace) -> None:
    cache = _read_cache(youtube_id)
    log.info(f"[{youtube_id}] restructuring from cache")
    segments = _build_segments(youtube_id, cache["units"], cache["chapters"], cache.get("set_code"), args)
    word_count = sum(len(segment["text"].split()) for segment in segments)
    _upsert(session, youtube_id, segments, word_count, cache.get("source", SOURCE))
    log.info(f"[{youtube_id}] rewrote {len(segments)} segments, {word_count} words")


def _write_cache(youtube_id, title, set_code, units, chapters, source) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "youtube_id": youtube_id,
        "title": title,
        "set_code": set_code,
        "source": source,
        "chapters": chapters,
        "units": units,
    }
    (CACHE_DIR / f"{youtube_id}.json").write_text(json.dumps(payload, ensure_ascii=False))


def _read_cache(youtube_id) -> dict:
    return json.loads((CACHE_DIR / f"{youtube_id}.json").read_text())


def _fetch_cards_safe(set_code: str | None) -> list[str]:
    if not set_code:
        return []
    try:
        return fetch_set_cards(set_code.lower())
    except Exception as exc:
        log.warning(f"card list fetch skipped for set {set_code}: {exc}")
        return []


def _claude_json(prompt: str, label: str, youtube_id: str) -> str | None:
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "json"], check=True, capture_output=True, text=True
        )
    except subprocess.CalledProcessError as exc:
        log.warning(f"[{youtube_id}] {label} failed: {exc}")
        return None
    start = result.stdout.find("{")
    if start < 0:
        return None
    wrapper = json.loads(result.stdout[start:])
    _log_usage(youtube_id, label, wrapper.get("total_cost_usd"), wrapper.get("usage", {}))
    return wrapper.get("result", "")


def _log_usage(youtube_id: str, label: str, cost: float | None, usage: dict) -> None:
    USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "youtube_id": youtube_id,
        "call": label,
        "cost_usd": cost,
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
    }
    with open(USAGE_LOG, "a") as handle:
        handle.write(json.dumps(entry) + "\n")
    log.info(f"[{youtube_id}] {label}: ${cost:.4f}" if cost is not None else f"[{youtube_id}] {label}: no cost")


def _fix_card_names(youtube_id: str, segments: list[dict], card_names: list[str]) -> None:
    full_text = "\n".join(segment["text"] for segment in segments)
    prompt = CARD_FIX_PROMPT.replace("{cards}", "\n".join(card_names)).replace("{text}", full_text)
    output = _claude_json(prompt, "card-fix", youtube_id)
    if output is None:
        return
    match = re.search(r"\{.*\}", output, re.DOTALL)
    fixes = json.loads(match.group(0)).get("fixes", []) if match else []
    applied = 0
    for segment in segments:
        text = segment["text"]
        for fix in fixes:
            text, count = re.subn(rf"\b{re.escape(fix['wrong'])}\b", fix["right"], text, flags=re.I)
            applied += count
        segment["text"] = text
    log.info(f"[{youtube_id}] card-name fix: {len(fixes)} forms, {applied} applied")


def _link_cards(segments: list[dict], card_names: list[str]) -> None:
    linked = 0
    for segment in segments:
        corrected, cards = tag_text(segment["text"], card_names)
        segment["text"] = corrected
        if cards:
            segment["cards"] = cards
            linked += len(cards)
        elif "cards" in segment:
            del segment["cards"]
    log.info(f"linked {linked} card mentions")


def _apply_known_terms(segments: list[dict]) -> None:
    for segment in segments:
        text = segment["text"]
        for pattern, replacement in KNOWN_TERMS:
            text = pattern.sub(replacement, text)
        segment["text"] = text


def _caption_units(youtube_id: str, cookie_args: list[str]):
    srt = _download_caption(youtube_id, cookie_args)
    if srt is _RATE_LIMITED:
        return _RATE_LIMITED
    if not srt:
        return None
    words = _caption_word_times(srt)
    if not words:
        return None
    text = " ".join(word for word, _ in words)
    density = 100 * sum(text.count(mark) for mark in ".?!") / max(len(words), 1)
    if density >= CAPTION_PUNCT_MIN:
        return _caption_sentences(words), CAPTION_SOURCE
    return _restore_caption(words), CAPTION_RESTORED_SOURCE


def _download_caption(youtube_id: str, cookie_args: list[str]):
    with tempfile.TemporaryDirectory(prefix="llu-caption-") as tmp:
        stem = Path(tmp) / youtube_id
        rate_limited = False
        for attempt in range(4):
            result = subprocess.run(
                [
                    "yt-dlp", "--write-auto-subs", "--sub-langs", "en", "--skip-download",
                    "--convert-subs", "srt", *cookie_args,
                    "--extractor-args", "youtube:player_client=android",
                    "-o", f"{stem}.%(ext)s", f"https://www.youtube.com/watch?v={youtube_id}",
                ],
                capture_output=True, text=True,
            )
            srt = Path(f"{stem}.en.srt")
            if srt.exists():
                return srt.read_text()
            if "429" in result.stderr or "429" in result.stdout:
                rate_limited = True
                time.sleep(45)
                continue
            return None
    return _RATE_LIMITED if rate_limited else None


def _caption_word_times(srt: str) -> list[tuple[str, float]]:
    emitted: list[tuple[float, str]] = []
    last = None
    for block in srt.split("\n\n"):
        lines = [line for line in block.splitlines() if line.strip()]
        timing = next((line for line in lines if "-->" in line), None)
        if not timing:
            continue
        start = _parse_srt_ts(timing.split("-->")[0].strip())
        for line in [ln for ln in lines if "-->" not in ln and not ln.strip().isdigit()]:
            if line != last:
                emitted.append((start, line))
                last = line
    return [(word, start) for start, line in emitted for word in line.split()]


def _parse_srt_ts(stamp: str) -> float:
    hms, ms = stamp.split(",")
    hours, minutes, seconds = hms.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(ms) / 1000


def _caption_sentences(words: list[tuple[str, float]]) -> list[dict]:
    units: list[dict] = []
    current: list[str] = []
    current_t = None
    for word, start in words:
        if not current:
            current_t = start
        current.append(word)
        if re.search(r"[.?!…]['\"]?$", word):
            units.append({"t": round(current_t), "text": " ".join(current)})
            current = []
    if current:
        units.append({"t": round(current_t), "text": " ".join(current)})
    return units


def _restore_caption(words: list[tuple[str, float]]) -> list[dict]:
    model = _load_punct_model()
    if not model:
        return _caption_sentences(words)
    raw = _strip_punct(" ".join(word for word, _ in words))
    units: list[dict] = []
    index = 0
    for sentence in model.restore(raw):
        count = len(sentence.split())
        if not count:
            continue
        start = words[min(index, len(words) - 1)][1]
        units.append({"t": round(start), "text": sentence.strip()})
        index += count
    return units


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


def _structure(units: list[dict], chapters: list[dict], youtube_id: str) -> list[dict]:
    heads = _chapter_heads(units, chapters)
    subtopics, paragraphs, sections = _subtopics_and_paragraphs(units, youtube_id)
    if not heads:
        heads = _promote_sections(units, subtopics, sections)
    chapter_times = [units[i]["t"] for i in heads]
    subtopics = {
        i: title for i, title in subtopics.items()
        if i not in heads and all(abs(units[i]["t"] - c) >= SUBTOPIC_CHAPTER_GAP for c in chapter_times)
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
    return _merge_short_paragraphs(segments)


def _merge_short_paragraphs(segments: list[dict], min_words: int = 6) -> list[dict]:
    merged: list[dict] = []
    for segment in segments:
        prev = merged[-1] if merged else None
        joinable = prev is not None and not segment.get("heading") and not segment.get("subheading")
        if joinable and len(prev["text"].split()) <= min_words:
            prev["text"] = f"{prev['text']} {segment['text']}"
            continue
        merged.append(segment)
    return merged


def _subtopics_and_paragraphs(units: list[dict], youtube_id: str) -> tuple[dict[int, str], set[int], set[int]]:
    numbered = "\n".join(f"{i}: {unit['text']}" for i, unit in enumerate(units))
    output = _claude_json(STRUCTURE_PROMPT + numbered, "structure", youtube_id)
    match = re.search(r"\{.*\}", output, re.DOTALL) if output else None
    if not match:
        return {}, {0}, set()
    data = json.loads(match.group(0))
    subtopics = {int(s["start"]): str(s["title"]).strip() for s in data.get("subtopics", [])}
    sections = {int(s["start"]) for s in data.get("subtopics", []) if s.get("section")}
    paragraphs = {int(i) for i in data.get("paragraphs", [])} | {0}
    def valid(i):
        return 0 <= i < len(units)

    return subtopics, {i for i in paragraphs if valid(i)}, {i for i in sections if valid(i)}


def _promote_sections(units, subtopics, sections) -> dict[int, tuple[str, int]]:
    heads: dict[int, tuple[str, int]] = {}
    last_t = None
    for index in sorted(sections):
        if index not in subtopics:
            continue
        t = units[index]["t"]
        if last_t is not None and t - last_t < SECTION_MIN_GAP:
            continue
        heads[index] = (subtopics[index], round(t))
        last_t = t
    return heads


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
        head_index = _pull_head_to_intro(blocks, head_index, start, title, heads)
        heads[head_index] = (title, round(start))
    return heads


def _pull_head_to_intro(blocks, head_index, start, title, heads) -> int:
    keywords = [w.lower() for w in re.findall(r"[A-Za-z']+", title) if len(w) >= 5]
    target = head_index
    for back in range(1, CHAPTER_LOOKBACK_MAX + 1):
        candidate = head_index - back
        if candidate <= 0 or candidate in heads:
            break
        if start - blocks[candidate]["t"] > CHAPTER_LOOKBACK_SECONDS:
            break
        text = blocks[candidate]["text"].lstrip()
        opens = bool(CHAPTER_INTRO_OPENER.match(text))
        names_topic = any(keyword in text.lower() for keyword in keywords)
        if opens or names_topic:
            target = candidate
    return target


def _upsert(session, youtube_id: str, segments: list[dict], word_count: int, source: str = SOURCE) -> None:
    row = session.get(EpisodeTranscript, youtube_id)
    if row is None:
        row = EpisodeTranscript(youtube_id=youtube_id)
        session.add(row)
    row.segments = segments
    row.word_count = word_count
    row.source = source
    session.commit()


if __name__ == "__main__":
    main()
