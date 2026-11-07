from datetime import date

import pytest

from bot.scripts.arena_schedule import events_from_items, merge_events, parse_calendar, parse_span, set_name

TODAY = date(2026, 11, 6)


@pytest.mark.parametrize("text, first, last", [
    ("November 13–22: Tarkir", date(2026, 11, 13), date(2026, 11, 22)),
    ("December 29–January 4: Theros", date(2026, 12, 29), date(2027, 1, 4)),
    ("January 5–11: Avatar", date(2027, 1, 5), date(2027, 1, 11)),
    ("November 14: Best-of-One Qualifier Play-In", date(2026, 11, 14), date(2026, 11, 14)),
])
def test_parse_span_reads_ranges_across_the_new_year(text, first, last):
    span = parse_span(text, TODAY)

    assert (span.first, span.last) == (first, last)


@pytest.mark.parametrize("text, expected", [
    ("Magic: The Gathering | Star Trek", "Star Trek"),
    ("Magic: The Gathering®—FINAL FANTASY™", "Final Fantasy"),
    ("Shadows over Innistrad Remastered (Abominable All-Stars)", "Shadows over Innistrad Remastered"),
    ("Dominaria", "Dominaria"),
])
def test_set_name_strips_branding_and_resolves_the_seed(text, expected):
    assert set_name(text) == expected


def test_calendar_items_map_to_queues_and_skip_constructed():
    items = parse_calendar(_ARTICLE)

    events, skipped = events_from_items(items, TODAY)

    by_title = {event["title"]: event for event in events}
    assert set(by_title) == {
        "Premier Draft: Star Trek",
        "Premier Draft: Tarkir: Dragonstorm",
        "Arena Direct: Star Trek Collector Booster Boxes",
        "ACQ Bo1 Play-In (Bonus): Star Trek Sealed",
    }
    assert by_title["Premier Draft: Star Trek"]["utc_end_date"] == "2027-02-03 16:00:00"
    assert {"slug": "flashback"} in by_title["Premier Draft: Tarkir: Dragonstorm"]["tags"]
    assert [item.text for item in skipped] == ["November 27–29: Historic Metagame Challenge"]


def test_merge_stretches_a_captured_window_and_adds_new_ones():
    captured = [_window("Premier Draft: Reality Fracture", "2026-09-29 15:00:00", "2026-11-10 16:00:00")]
    generated = [
        _window("Premier Draft: Reality Fracture", "2026-11-10 16:00:00", "2026-12-03 16:00:00"),
        _window("Premier Draft: Star Trek", "2026-11-10 16:00:00", "2027-02-03 16:00:00"),
    ]

    merged = merge_events(captured, generated)

    windows = [(event["title"], event["utc_start_date"], event["utc_end_date"]) for event in merged]
    assert windows == [
        ("Premier Draft: Reality Fracture", "2026-09-29 15:00:00", "2026-12-03 16:00:00"),
        ("Premier Draft: Star Trek", "2026-11-10 16:00:00", "2027-02-03 16:00:00"),
    ]


def _window(title: str, start: str, end: str) -> dict:
    return {"title": title, "tags": [], "utc_start_date": start, "utc_end_date": end, "start_date": start,
            "end_date": end}


_ARTICLE = """
<h2>Magic: The Gathering | Star Trek Event Schedule</h2>
<h3>Not the calendar</h3>
<ul><li>November 10: something before the calendar</li></ul>
<h2>Full Event Calendar</h2>
<h3>Premier Draft</h3>
<ul><li>November 10–February 2: <i>Magic: The Gathering</i> | <i>Star Trek</i></li></ul>
<h3>Flashback Premier Draft</h3>
<ul><li>November 13–22: <i>Tarkir: Dragonstorm</i></li></ul>
<h3>Arena Direct</h3>
<ul>
<li>November 13–22: Arena Direct for <i>Magic: The Gathering</i> | <i>Star Trek</i> Collector Booster boxes</li>
</ul>
<h3>Metagame Challenge</h3>
<ul><li>November 27–29: Historic Metagame Challenge</li></ul>
<h3>Arena Championship Qualifier Events</h3>
<h4>January Format: Standard</h4>
<ul><li>January 17 (Bonus Event): Best-of-One <i>Magic: The Gathering</i> | <i>Star Trek</i> Sealed</li></ul>
"""
