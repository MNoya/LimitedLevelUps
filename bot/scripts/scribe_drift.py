"""Report where the captured MTG Scribe calendar has outrun the code that reads it.

MTG Scribe renames formats between rotations ("Pick 2 Draft" → "Pick-Two Draft"), introduces tags
(`arena-open`, `welcome-decks`), and publishes reruns before tagging them, so a fresh capture can
render wrong without anything failing. This checks the new calendar against every vocabulary the
render depends on and prints what needs a code change:

    .venv/bin/python -m bot.scripts.scribe_drift
    .venv/bin/python -m bot.scripts.scribe_drift --previous /tmp/prev.json

``--previous`` points at the calendar being replaced (``git show HEAD:bot/services/scribe_calendar.json``)
and adds new-since-last-capture reporting for tags and format labels. Read-only; exits 1 when anything
needs attention so a caller can branch on it.
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from bot.commands.event_scribe import BOOSTER_LABELS, DRAFT_FORMATS, _seed_for_label, _slugify
from bot.services import mtgscribe
from bot.services.scribe_formats import FORMAT_SHORT_NAMES
from bot.sets import ALL_SETS, CUBE_CODE

SET_SYMBOL_DIR = Path(__file__).resolve().parents[2] / "frontend" / "public" / "set-symbols"
COMPETITIVE_HINTS = ("qualifier", "play-in", "championship", "arena-open")
FLASHBACK_FORMATS = ("Premier Draft", "Traditional Draft", "Sealed", "Traditional Sealed")
ACCEPTED_LONG_FORMATS = ("Contender Draft", "Alchemy Draft", "Remix Draft")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous", type=Path, help="the calendar being replaced, for new-since reporting")
    args = parser.parse_args()

    events = mtgscribe.load_events(arena_only=True)
    findings: list[str] = []
    findings.extend(_unmapped_format_labels(events))
    findings.extend(_ambiguous_set_labels(events))
    findings.extend(_unmatched_set_labels(events))
    findings.extend(_untagged_reruns(events))
    findings.extend(_unlisted_competitive_tags(events))
    findings.extend(_missing_set_symbols(events))
    findings.extend(_encoded_titles(events))
    if args.previous is not None:
        findings.extend(_new_since(events, args.previous))

    print(f"checked {len(events)} arena events in {mtgscribe.CALENDAR_PATH.name}\n")
    if not findings:
        print("no drift — every format label, tag and set label the calendar uses is already handled")
        return
    for finding in findings:
        print(f"  {finding}")
    print(f"\n{len(findings)} item(s) need a look before committing")
    raise SystemExit(1)


def _unmapped_format_labels(events: list) -> list[str]:
    """A label that reads as a draft family but is absent from the short-name map renders unshortened
    and sorts last in the "and others" collapse — how "Pick-Two Draft" first surfaced."""
    findings = []
    for label in sorted({event.format_label for event in events if event.format_label}):
        if label in FORMAT_SHORT_NAMES or label in DRAFT_FORMATS or label in ACCEPTED_LONG_FORMATS:
            continue
        if label.endswith("Draft"):
            findings.append(f"format label {label!r} looks like a draft family but is in neither "
                            f"FORMAT_SHORT_NAMES nor DRAFT_FORMATS")
    return findings


def _ambiguous_set_labels(events: list) -> list[str]:
    """Two seeds matching one label means the render picks by name length, which is right for
    "Dominaria United" over "Dominaria" but worth eyeballing on any new collision."""
    findings = []
    for label in sorted({event.group_label for event in events}):
        matches = [seed for seed in ALL_SETS
                   if seed.name.lower() in label.lower() or label.lower() in seed.name.lower()]
        if len(matches) > 1:
            picked = _seed_for_label(label)
            codes = ", ".join(seed.code for seed in matches)
            findings.append(f"set label {label!r} matches {codes} — resolves to {picked.code}")
    return findings


def _unmatched_set_labels(events: list) -> list[str]:
    """A Limited queue whose label matches no seed renders with no set symbol. Fine for an Arena-only
    product ("Mixed-Up"), a missing set otherwise."""
    findings = []
    for label in sorted({event.group_label for event in events if "limited" in event.tag_slugs}):
        if _seed_for_label(label) is not None:
            continue
        if any(word in label.lower() for word in ("cube", "midweek")):
            continue
        findings.append(f"set label {label!r} matches no seed in ALL_SETS — renders without a symbol")
    return findings


def _untagged_reruns(events: list) -> list[str]:
    """Scribe tags only the next rerun or two at publish, so a rerun of a rotated-out set with no
    `flashback` tag gets its own set header instead of the roster, and never announces."""
    today = date.today()
    findings = []
    for event in events:
        if mtgscribe.FLASHBACK_TAG in event.tag_slugs or event.format_label not in FLASHBACK_FORMATS:
            continue
        seed = _seed_for_label(event.group_label)
        if seed is None or seed.code == CUBE_CODE or seed.end_date is None or seed.end_date >= today:
            continue
        findings.append(f"{event.title!r} ({event.start:%b %-d}) reruns rotated-out {seed.code} "
                        f"with no flashback tag")
    return findings


def _unlisted_competitive_tags(events: list) -> list[str]:
    """A competitive-looking tag outside COMPETITIVE_TAGS drops the event from the Competitive filter,
    the set-channel pin and its announce — how `arena-open` was missed."""
    findings = []
    seen = set()
    for event in events:
        for tag in event.tag_slugs:
            if tag in seen or tag in mtgscribe.COMPETITIVE_TAGS:
                continue
            if any(hint in tag for hint in COMPETITIVE_HINTS) and tag not in BOOSTER_LABELS:
                seen.add(tag)
                findings.append(f"tag {tag!r} looks competitive but is not in COMPETITIVE_TAGS "
                                f"(first seen on {event.title!r})")
    return findings


def _missing_set_symbols(events: list) -> list[str]:
    """The symbol PNG is the source for the Discord application emoji, so a set without one renders
    its lines with no glyph."""
    rendered = [event for event in events if "limited" in event.tag_slugs]
    seeds = {seed.code for seed in (_seed_for_label(event.group_label) for event in rendered) if seed is not None}
    findings = []
    for code in sorted(seeds):
        if not (SET_SYMBOL_DIR / f"{code.lower()}.png").exists():
            findings.append(f"set {code} has no frontend/public/set-symbols/{code.lower()}.png — "
                            f"run generate_set_symbols {code} then upload_app_emojis keyrune:{code.lower()}")
    return findings


def _encoded_titles(events: list) -> list[str]:
    """``_parse_event`` unescapes titles; a surviving entity means a double-encoded upstream value."""
    return [f"title {event.title!r} still carries an HTML entity" for event in events if "&#" in event.title]


def _new_since(events: list, previous_path: Path) -> list[str]:
    """Tags and format labels absent from the calendar being replaced — the shortlist worth reading
    even when nothing else here fires, since a rename shows up as one new label and one gone."""
    with previous_path.open(encoding="utf-8") as previous_file:
        old_raw = json.load(previous_file)
    old = [mtgscribe._parse_event(raw) for raw in old_raw]
    findings = []
    set_slugs = {_slugify(seed.name) for seed in ALL_SETS}
    new_tags = {tag for event in events for tag in event.tag_slugs} - {t for e in old for t in e.tag_slugs}
    for tag in sorted(new_tags - set_slugs):
        findings.append(f"new tag {tag!r}")
    new_formats = ({event.format_label for event in events if event.format_label}
                   - {event.format_label for event in old if event.format_label})
    for label in sorted(new_formats):
        findings.append(f"new format label {label!r}")
    return findings


if __name__ == "__main__":
    main()
