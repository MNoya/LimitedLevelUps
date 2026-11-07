"""Merge a set's official MTG Arena event schedule article into ``scribe_calendar.json``.

Wizards posts each set's full Arena calendar in advance, weeks before MTG Scribe catches up, so the Arena
queues come from that article and Scribe keeps the tabletop events, coverage and Constructed. Run it after
``snapshot_scribe``:

    .venv/bin/python -m bot.scripts.arena_schedule https://magic.wizards.com/en/news/mtg-arena/<set>-event-schedule
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

from bot.commands.event_scribe import seed_for_label, slugify
from bot.services import mtgscribe

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
QUEUE_OPENS = time(11, 0)
PLAY_IN_OPENS = time(9, 0)
PLAY_IN_CLOSES = time(6, 0)
MIDWEEK_OPENS = time(17, 0)
STAMP = "%Y-%m-%d %H:%M:%S"
MONTHS = {name: number for number, name in enumerate(
    ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
     "november", "december"), start=1)}
CALENDAR_HEADING = "full event calendar"


@dataclass(frozen=True)
class Item:
    section: str
    subsection: str
    text: str


@dataclass(frozen=True)
class DateSpan:
    first: date
    last: date


def main() -> None:
    url = sys.argv[1]
    request = urllib.request.Request(url, headers={"User-Agent": "LimitedLevelUps/1.0"})
    html = urllib.request.urlopen(request, timeout=30).read().decode("utf-8")
    events, skipped = events_from_items(parse_calendar(html), date.today())
    captured = json.loads(mtgscribe.CALENDAR_PATH.read_text(encoding="utf-8"))
    merged = merge_events(captured, events)
    mtgscribe.CALENDAR_PATH.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"merged {len(events)} Arena events from the article into {len(captured)} captured, {len(merged)} total")
    for item in skipped:
        print(f"  skipped [{item.section}] {item.text}")


def parse_calendar(html: str) -> list[Item]:
    parser = _CalendarParser()
    parser.feed(html)
    return parser.items


def events_from_items(items: list[Item], today: date) -> tuple[list[dict], list[Item]]:
    events: list[dict] = []
    skipped: list[Item] = []
    for item in items:
        event = _event_for(item, today)
        if event is None:
            skipped.append(item)
        else:
            events.append(event)
    return events, skipped


def merge_events(captured: list[dict], generated: list[dict]) -> list[dict]:
    merged = [dict(event) for event in captured]
    for event in generated:
        overlapping = _overlapping_same_title(merged, event)
        if overlapping is None:
            merged.append(event)
        else:
            _stretch(overlapping, event)
    return sorted(merged, key=lambda event: (event["utc_start_date"], event["title"]))


def parse_span(text: str, today: date) -> DateSpan | None:
    match = re.match(r"([A-Za-z]+) (\d+)(?:[–-](?:([A-Za-z]+) )?(\d+))?", text)
    if match is None or match[1].lower() not in MONTHS:
        return None
    first_month = MONTHS[match[1].lower()]
    first = _nearest_date(first_month, int(match[2]), today)
    if match[4] is None:
        return DateSpan(first, first)
    last_month = MONTHS[match[3].lower()] if match[3] else first_month
    last = date(first.year + (1 if last_month < first_month else 0), last_month, int(match[4]))
    return DateSpan(first, last)


def set_name(text: str) -> str:
    cleaned = re.sub(r"\(.*?\)", "", text)
    cleaned = cleaned.replace("®", "").replace("™", "")
    cleaned = re.sub(r"Magic: The Gathering\s*(\||—)?\s*", "", cleaned)
    cleaned = " ".join(cleaned.split())
    seed = seed_for_label(cleaned)
    return seed.name if seed is not None else cleaned


def _event_for(item: Item, today: date) -> dict | None:
    span = parse_span(item.text, today)
    if span is None:
        return None
    subject = item.text.split(":", 1)[1].strip() if ":" in item.text else ""
    section = item.section
    if section in ("premier draft", "flashback premier draft"):
        name = set_name(subject)
        flashback = ["flashback"] if section.startswith("flashback") else []
        return _queue(f"Premier Draft: {name}", ["premier-draft", *flashback], name, span)
    simple = {"pick-two draft": ("Pick-Two Draft", "pick-2-draft"), "traditional draft": ("Traditional Draft",
              "traditional-draft"), "quick draft": ("Quick Draft", "quick-draft"),
              "contender draft": ("Contender Draft", "contender-draft")}
    if section in simple:
        label, tag = simple[section]
        name = set_name(subject)
        return _queue(f"{label}: {name}", [tag], name, span)
    if section == "sealed and traditional sealed":
        return _sealed(subject, span)
    if section == "arena direct":
        return _arena_direct(subject, span)
    if section == "cube":
        return _cube(subject, span)
    if section == "midweek magic":
        return _midweek(subject, span)
    if section == "arena championship qualifier events":
        return _qualifier(item, subject, span)
    if section == "other events":
        return _other(subject, span)
    return None


def _sealed(subject: str, span: DateSpan) -> dict | None:
    for suffix, tag in ((" Traditional Sealed", "traditional-sealed"), (" Sealed", "sealed")):
        if subject.endswith(suffix):
            name = set_name(subject.removesuffix(suffix))
            label = "Traditional Sealed" if tag == "traditional-sealed" else "Sealed"
            return _queue(f"{label}: {name}", [tag], name, span)
    return None


def _arena_direct(subject: str, span: DateSpan) -> dict | None:
    if "Arena Powered Cube" in subject:
        tags = ["arena-direct", "arena-powered-cube", "draft", "play-boosters"]
        return _queue("Arena Direct: Arena Powered Cube Draft", tags, None, span)
    match = re.match(r"Arena Direct for (.+) (Collector|Play) Booster boxes", subject, re.IGNORECASE)
    if match is None:
        return None
    name = set_name(match[1])
    kind = match[2].capitalize()
    booster_tag = "collector-booster" if kind == "Collector" else "play-boosters"
    return _queue(f"Arena Direct: {name} {kind} Booster Boxes", ["arena-direct", booster_tag, "sealed"], name, span)


def _cube(subject: str, span: DateSpan) -> dict | None:
    if subject == "Arena Powered Cube":
        return _queue("Arena Powered Cube", ["arena-powered-cube", "premier-draft"], None, span)
    if subject == "Pick-Two Arena Powered Cube":
        return _queue("Pick-Two Arena Powered Cube", ["arena-powered-cube", "pick-2-draft"], None, span)
    return None


def _midweek(subject: str, span: DateSpan) -> dict | None:
    if not subject.endswith(" Bot Draft"):
        return None
    name = set_name(subject.removesuffix(" Bot Draft"))
    opens = datetime.combine(span.first, MIDWEEK_OPENS, tzinfo=ET)
    closes = datetime.combine(span.last + timedelta(days=1), MIDWEEK_OPENS, tzinfo=ET)
    tags = ["arena", "limited", "midweek-magic", "quick-draft", slugify(name)]
    return _event(f"Midweek Magic: {name} Bot Draft", tags, opens, closes)


def _qualifier(item: Item, subject: str, span: DateSpan) -> dict | None:
    format_name = item.subsection.split(":", 1)[1].strip() if ":" in item.subsection else ""
    if "(Bonus Event)" in item.text:
        bonus = re.search(r"Best-of-One (.+) Sealed", subject)
        if bonus is None:
            return None
        name = set_name(bonus[1])
        tags = ["arena", "best-of-one", "limited", "play-in", "qualifier", "sealed", slugify(name)]
        return _play_in(f"ACQ Bo1 Play-In (Bonus): {name} Sealed", tags, span.first)
    if not format_name:
        return None
    label, format_tags = _qualifier_format(format_name)
    if subject == "Best-of-One Qualifier Play-In":
        return _play_in(f"ACQ Bo1 Play-In: {label}", ["best-of-one", "play-in", *format_tags], span.first)
    if subject == "Best-of-Three Qualifier Play-In":
        return _play_in(f"ACQ Bo3 Play-In: {label}", ["best-of-three", "play-in", *format_tags], span.first)
    if subject == "Qualifier Weekend":
        opens = datetime.combine(span.first, time(0, 0), tzinfo=ET)
        closes = datetime.combine(span.last, time(23, 59, 59), tzinfo=ET)
        championship = ["arena-championship"] if "constructed" in format_tags else []
        return _event(f"ACQ Weekend: {label}", ["arena", "qualifier", *championship, *format_tags], opens, closes)
    return None


def _qualifier_format(format_name: str) -> tuple[str, list[str]]:
    if format_name.endswith(" Sealed"):
        name = set_name(format_name.removesuffix(" Sealed"))
        return f"{name} Sealed", ["limited", "sealed", slugify(name)]
    return format_name, ["constructed", slugify(format_name)]


def _other(subject: str, span: DateSpan) -> dict | None:
    if subject.endswith(" Omniscience Draft"):
        name = set_name(subject.removesuffix(" Omniscience Draft"))
        return _queue(f"Omniscience Draft: {name}", ["draft", "omniscience"], name, span)
    if subject == "Mixed-Up Premier Draft":
        return _queue("Premier Draft: Mixed-Up", ["mixed-up", "premier-draft"], None, span)
    return None


def _queue(title: str, tags: list[str], name: str | None, span: DateSpan) -> dict:
    set_tags = [slugify(name)] if name is not None else []
    opens = datetime.combine(span.first, QUEUE_OPENS, tzinfo=ET)
    closes = datetime.combine(span.last + timedelta(days=1), QUEUE_OPENS, tzinfo=ET)
    return _event(title, ["arena", "limited", *tags, *set_tags], opens, closes)


def _play_in(title: str, tags: list[str], day: date) -> dict:
    opens = datetime.combine(day, PLAY_IN_OPENS, tzinfo=ET)
    closes = datetime.combine(day + timedelta(days=1), PLAY_IN_CLOSES, tzinfo=ET)
    return _event(title, ["arena", "qualifier", *tags], opens, closes)


def _event(title: str, tags: list[str], opens: datetime, closes: datetime) -> dict:
    return {
        "title": title,
        "tags": [{"slug": slug} for slug in sorted(set(tags))],
        "utc_start_date": opens.astimezone(UTC).strftime(STAMP),
        "utc_end_date": closes.astimezone(UTC).strftime(STAMP),
        "start_date": opens.strftime(STAMP),
        "end_date": closes.strftime(STAMP),
    }


def _nearest_date(month: int, day: int, today: date) -> date:
    candidates = [date(today.year + offset, month, day) for offset in (-1, 0, 1)]
    best = candidates[0]
    for candidate in candidates[1:]:
        if abs((candidate - today).days) < abs((best - today).days):
            best = candidate
    return best


def _overlapping_same_title(events: list[dict], event: dict) -> dict | None:
    for existing in events:
        if existing["title"] != event["title"]:
            continue
        if existing["utc_start_date"] <= event["utc_end_date"] and event["utc_start_date"] <= existing["utc_end_date"]:
            return existing
    return None


def _stretch(existing: dict, event: dict) -> None:
    if event["utc_start_date"] < existing["utc_start_date"]:
        existing["utc_start_date"] = event["utc_start_date"]
        existing["start_date"] = event["start_date"]
    if event["utc_end_date"] > existing["utc_end_date"]:
        existing["utc_end_date"] = event["utc_end_date"]
        existing["end_date"] = event["end_date"]


class _CalendarParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[Item] = []
        self._inside_calendar = False
        self._section = ""
        self._subsection = ""
        self._tag: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("h2", "h3", "h4", "li"):
            self._tag = tag
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._tag is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != self._tag:
            return
        text = " ".join("".join(self._text).split())
        self._tag = None
        if tag == "h2":
            self._inside_calendar = text.lower() == CALENDAR_HEADING
        elif not self._inside_calendar:
            return
        elif tag == "h3":
            self._section = text.lower()
            self._subsection = ""
        elif tag == "h4":
            self._subsection = text
        elif tag == "li":
            self.items.append(Item(self._section, self._subsection, text))


if __name__ == "__main__":
    main()
