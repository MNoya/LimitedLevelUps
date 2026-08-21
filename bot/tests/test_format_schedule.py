from datetime import date, datetime, time, timedelta, timezone

import pytest

from bot.commands.event_scribe import (
    build_announcement,
    build_schedule_embed,
    scribe_url,
    select_groups,
)
from bot.services import mtgscribe
from bot.services.format_schedule import (
    ANNOUNCE_COMPETITIVE,
    ANNOUNCE_NONE,
    LATEST_SET_CATEGORY,
    OPEN_TZ,
    SCHEDULE_PINS,
    already_announced,
    announcement_format,
    effective_start,
    latest_set_channel,
    newest_set,
    set_pin_frozen,
    awards_eve_set,
    channel_for_set,
    newly_opened,
    next_rotation,
    previous_window_start,
    set_seed_for_channel,
    set_tracking_todo_index,
)
from bot.sets import ALL_SETS
from bot.tasks.format_schedule_post import announcement_for
from bot.tasks.set_awards_post import incoming_set_channel


class _StubCategory:
    def __init__(self, name):
        self.name = name


class _StubChannel:
    def __init__(self, name, category, created_at):
        self.id = name
        self.name = name
        self.category = category
        self.created_at = created_at


class _StubGuild:
    def __init__(self, channels):
        self.text_channels = channels


def _event(format_label, group_label, tags, now, start_off, end_off):
    start = now + timedelta(days=start_off)
    end = now + timedelta(days=end_off)
    return mtgscribe.ScribeEvent(
        title=f"{format_label}: {group_label}",
        format_label=format_label,
        group_label=group_label,
        start=start,
        end=end,
        start_local=start.replace(tzinfo=None),
        end_local=end.replace(tzinfo=None),
        tag_slugs=tags,
    )


def _group(label, tags, formats, start, end):
    return mtgscribe.EventGroup(
        label=label,
        formats=list(formats),
        start=start,
        end=end,
        start_local=start.replace(tzinfo=None),
        end_local=end.replace(tzinfo=None),
        flashback="flashback" in tags,
        cube="cube" in tags,
        competitive="qualifier" in tags,
    )


def test_newest_set_ignores_permanent_cube():
    newest = newest_set()

    assert newest.code != "CUBE"
    assert all(seed.start_date <= newest.start_date for seed in ALL_SETS if seed.code != "CUBE")


def test_set_seed_for_channel_resolves_the_outgoing_set():
    when = datetime(2026, 7, 1, tzinfo=timezone.utc)

    stale = set_seed_for_channel("secrets-of-strixhaven", when)
    active = set_seed_for_channel("marvel-super-heroes", when)
    unmatched = set_seed_for_channel("whats-the-build", when)

    assert stale.code == "SOS"
    assert active is None
    assert unmatched is None


def test_archival_render_carries_no_relative_timestamp():
    """The freeze is detected by reading the pin back, so a live board must always carry a `<t:` token
    and an archival one must never — otherwise the final write repeats or never happens."""
    now = datetime(2026, 8, 4, 15, tzinfo=timezone.utc)
    running = _group("Marvel Super Heroes", (), ["Premier Draft"], now - timedelta(days=30), now + timedelta(days=6))
    soon = _group("The Hobbit", (), ["Premier Draft"], now + timedelta(days=7), now + timedelta(days=50))

    live = build_schedule_embed([running], [soon], {}, "Marvel Super Heroes").description
    archival = build_schedule_embed([running], [soon], {}, "Marvel Super Heroes", archival=True).description

    assert "<t:" in live
    assert "<t:" not in archival


def test_archival_render_drops_the_section_headers():
    now = datetime(2026, 8, 4, 15, tzinfo=timezone.utc)
    running = _group("Marvel Super Heroes", (), ["Premier Draft"], now - timedelta(days=30), now + timedelta(days=6))
    soon = _group("The Hobbit", (), ["Premier Draft"], now + timedelta(days=7), now + timedelta(days=50))

    live = build_schedule_embed([running], [soon], {}, "Marvel Super Heroes").description
    archival = build_schedule_embed([running], [soon], {}, "Marvel Super Heroes", archival=True).description

    assert live.count("###") == 2
    assert archival.count("###") == 0


def test_archival_render_keeps_every_window_of_a_repeated_format():
    """A live board shows a recurring format once, since its later run surfaces after the first ends.
    A frozen season record has no later render to rely on, so a hidden second run is a queue lost."""
    now = datetime(2026, 8, 4, 15, tzinfo=timezone.utc)
    early = _group("Marvel Super Heroes", (), ["Quick Draft"], now - timedelta(days=33), now - timedelta(days=23))
    late = _group("Marvel Super Heroes", (), ["Quick Draft"], now - timedelta(days=4), now + timedelta(days=7))

    live = build_schedule_embed([early, late], [], {}, "Marvel Super Heroes").description
    archival = build_schedule_embed([early, late], [], {}, "Marvel Super Heroes", archival=True).description

    assert live.count("Quick Draft") == 1
    assert archival.count("Quick Draft") == 2


def test_set_pin_freezes_inside_the_final_week():
    cases = [
        (datetime(2026, 8, 1, 15, tzinfo=timezone.utc), False),
        (datetime(2026, 8, 4, 15, tzinfo=timezone.utc), True),
        (datetime(2026, 8, 10, 15, tzinfo=timezone.utc), True),
        (datetime(2026, 8, 12, 15, tzinfo=timezone.utc), False),
    ]

    frozen = [(when, set_pin_frozen(when)) for when, _ in cases]

    assert frozen == cases


def test_awards_eve_set_returns_outgoing_on_release_eve():
    eve = datetime(2026, 4, 20, 15, tzinfo=timezone.utc)
    ordinary = datetime(2026, 4, 15, 15, tzinfo=timezone.utc)

    outgoing = awards_eve_set(eve)

    assert outgoing.code == "TMT"
    assert awards_eve_set(ordinary) is None


def test_channel_for_set_matches_name_within_strategy_category():
    strategy = _StubCategory("MTG Strategy")
    other = _StubCategory("Format Archive")
    sos = next(seed for seed in ALL_SETS if seed.code == "SOS")
    channels = [
        _StubChannel("secrets-of-strixhaven", strategy, None),
        _StubChannel("secrets-of-strixhaven-old", other, None),
    ]

    match = channel_for_set(channels, sos)

    assert match.name == "secrets-of-strixhaven"


def test_channel_for_set_ignores_a_newer_preview_season_channel():
    """A mod creates the incoming set's channel weeks before it starts, so the newest channel in MTG
    Strategy belongs to a set that has not released yet, not to the one currently running."""
    strategy = _StubCategory(LATEST_SET_CATEGORY)
    msh = next(seed for seed in ALL_SETS if seed.code == "MSH")
    base = datetime(2026, 6, 8, tzinfo=timezone.utc)
    channels = [
        _StubChannel("🦸-marvel-super-heroes", strategy, base),
        _StubChannel("🏔️-the-hobbit", strategy, base + timedelta(days=53)),
    ]

    match = channel_for_set(channels, msh, LATEST_SET_CATEGORY)

    assert match.name == "🦸-marvel-super-heroes"
    assert latest_set_channel(channels, LATEST_SET_CATEGORY).name == "🏔️-the-hobbit"


def test_incoming_set_channel_targets_the_channel_of_the_set_releasing_next():
    strategy = _StubCategory(LATEST_SET_CATEGORY)
    base = datetime(2026, 6, 8, tzinfo=timezone.utc)
    hobbit = _StubChannel("🏔️-the-hobbit", strategy, base)
    fracture = _StubChannel("reality-fracture", None, base + timedelta(days=53))
    hob = next(seed for seed in ALL_SETS if seed.code == "HOB")

    assert incoming_set_channel(_StubGuild([hobbit, fracture]), hob, hobbit) is fracture
    assert incoming_set_channel(_StubGuild([hobbit]), hob, hobbit) is None
    assert incoming_set_channel(_StubGuild([hobbit, fracture]), hob, fracture) is None


class _TodoChannel:
    def __init__(self, channel_id, name):
        self.id = channel_id
        self.name = name


def test_set_tracking_todo_index_picks_the_action_linked_to_a_set_channel():
    channels = [
        _TodoChannel("overview", "channel-overview"),
        _TodoChannel("ecl", "lorwyn-eclipsed"),
    ]
    actions = [
        {"channel_id": "overview", "title": "Explore the server"},
        {"channel_id": "ecl", "title": "See what people are discussing"},
    ]

    assert set_tracking_todo_index(actions, channels) == 1


def test_set_tracking_todo_index_is_none_when_no_action_links_a_set_channel():
    channels = [_TodoChannel("overview", "channel-overview")]
    actions = [{"channel_id": "overview", "title": "Explore the server"}]

    assert set_tracking_todo_index(actions, channels) is None


def test_set_pin_routes_by_latest_set_category():
    set_pin = next(pin for pin in SCHEDULE_PINS if pin.key == "set")

    assert set_pin.channel_name is None
    assert set_pin.category == LATEST_SET_CATEGORY


def test_latest_set_channel_picks_the_newest_set_channel_in_the_category():
    strategy = _StubCategory(LATEST_SET_CATEGORY)
    other = _StubCategory("General")
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    channels = [
        _StubChannel("marvel-super-heroes", strategy, base),
        _StubChannel("the-hobbit", strategy, base + timedelta(days=180)),
        _StubChannel("whats-the-pick", strategy, base + timedelta(days=200)),
        _StubChannel("star-trek", other, base + timedelta(days=999)),
        _StubChannel("reality-fracture", None, base + timedelta(days=500)),
    ]

    latest = latest_set_channel(channels, LATEST_SET_CATEGORY)

    assert latest.name == "the-hobbit"


def test_set_pin_renders_whole_set_but_announces_competitive_only():
    set_pin = next(pin for pin in SCHEDULE_PINS if pin.key == "set")

    assert set_pin.pin_filters == ()
    assert set_pin.announce_filters == ("competitive",)


def test_named_channels_use_their_fixed_substring():
    cube = next(pin for pin in SCHEDULE_PINS if pin.key == "cube")

    assert cube.channel_name == "cube-talk"
    assert cube.category is None


def test_cube_announcement_links_known_list_only():
    now = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
    end = now + timedelta(days=6)
    known = _group("Arena Powered Cube", ("cube",), ["Premier Draft"], now, end)
    unknown = _group("Some Kind of new Cube", ("cube",), ["Premier Draft"], now, end)

    assert "cubecobra.com/cube/about/mtgapc" in build_announcement(known, {}, format_word="").description
    assert "cubecobra" not in build_announcement(unknown, {}, format_word="").description


def test_cube_is_announce_only_no_pin():
    cube = next(pin for pin in SCHEDULE_PINS if pin.key == "cube")

    assert cube.maintain_pin is False
    assert cube.announce_filters == ("cube",)


def test_quick_and_flashback_are_separate_pins_in_one_channel():
    quick = next(pin for pin in SCHEDULE_PINS if pin.key == "quick")
    flashback = next(pin for pin in SCHEDULE_PINS if pin.key == "flashback")

    assert quick.channel_name == flashback.channel_name == "quick-or-flashback-draft"
    assert quick.scope_label == "Quick Draft"
    assert flashback.scope_label == "Flashback"
    assert quick.pin_filters == ("quick",)
    assert flashback.pin_filters == ("flashback",)


def test_previous_window_is_the_window_before_the_current_one():
    # Firing at the 08:00 PDT window (15:00 UTC); the previous window is 06:00 PDT the same day
    now = datetime(2026, 6, 16, 15, 0, tzinfo=timezone.utc)

    previous = previous_window_start(now).astimezone(OPEN_TZ)

    assert previous.date() == date(2026, 6, 16)
    assert previous.timetz().replace(tzinfo=None) == time(6, 0)


def test_previous_window_wraps_to_yesterdays_last_window():
    # Firing at the first window of the day (06:00 PDT, 13:00 UTC); the previous is yesterday's 14:00
    now = datetime(2026, 6, 16, 13, 0, tzinfo=timezone.utc)

    previous = previous_window_start(now).astimezone(OPEN_TZ)

    assert previous.date() == date(2026, 6, 15)
    assert previous.timetz().replace(tzinfo=None) == time(14, 0)


def test_competitive_midnight_et_start_normalizes_to_morning_open():
    qualifier_weekend = _group("Marvel Super Heroes", ("qualifier",), ["Sealed"],
                               datetime(2026, 7, 11, 4, 0, tzinfo=timezone.utc),
                               datetime(2026, 7, 13, 3, 59, tzinfo=timezone.utc))

    go_live = effective_start(qualifier_weekend).astimezone(OPEN_TZ)

    assert go_live.date() == date(2026, 7, 11)
    assert go_live.timetz().replace(tzinfo=None) == time(6, 0)


def test_newly_opened_keeps_events_opened_since_the_window():
    now = datetime(2026, 6, 15, 16, 0, tzinfo=timezone.utc)
    since = now - timedelta(hours=2)
    fresh = _group("Fresh", (), ["Quick Draft"], now - timedelta(minutes=10), now + timedelta(days=7))
    stale = _group("Stale", (), ["Quick Draft"], since - timedelta(hours=1), now + timedelta(days=7))
    future = _group("Future", (), ["Quick Draft"], now + timedelta(hours=1), now + timedelta(days=7))

    assert newly_opened([fresh, stale, future], since, now) == [fresh]


def test_sealed_is_pin_only_and_set_channel_announces_competitive():
    sealed = next(pin for pin in SCHEDULE_PINS if pin.key == "sealed")
    set_pin = next(pin for pin in SCHEDULE_PINS if pin.key == "set")

    assert sealed.announce == ANNOUNCE_NONE
    assert set_pin.announce == ANNOUNCE_COMPETITIVE


def test_announcement_for_dispatches_by_pin_policy():
    now = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
    competitive_pin = next(pin for pin in SCHEDULE_PINS if pin.key == "set")
    flashback_pin = next(pin for pin in SCHEDULE_PINS if pin.key == "flashback")
    comp = _group("Marvel Super Heroes", ("qualifier",), ["Qualifier Play-In Bo3"], now, now + timedelta(days=2))
    flash = _group("Aetherdrift", ("flashback",), ["Premier Draft"], now, now + timedelta(days=7))

    _, comp_marker = announcement_for(competitive_pin, comp, [comp], {})
    _, flash_marker = announcement_for(flashback_pin, flash, [flash], {})

    assert comp_marker == "Marvel Super Heroes"
    assert flash_marker == "Flashback"


def test_next_rotation_returns_soonest_after_current():
    now = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
    current = _group("Aetherdrift", ("flashback",), ["Premier Draft"], now, now + timedelta(days=7))
    soon = _group("Bloomburrow", ("flashback",), ["Premier Draft"], now + timedelta(days=7), now + timedelta(days=14))
    later = _group("Duskmourn", ("flashback",), ["Premier Draft"], now + timedelta(days=14), now + timedelta(days=21))

    assert next_rotation([current, later, soon], current) is soon


def test_announcement_previews_next_rotation_beyond_the_freshly_opened_slice():
    now = datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc)
    since = now - timedelta(hours=6)
    flashback_pin = next(pin for pin in SCHEDULE_PINS if pin.key == "flashback")
    live = _group("Final Fantasy", ("flashback",), ["Premier Draft"], now - timedelta(hours=1), now + timedelta(days=7))
    later_start = now + timedelta(days=7)
    upcoming = _group("Bloomburrow", ("flashback",), ["Premier Draft"], later_start, later_start + timedelta(days=7))
    scheduled = [live, upcoming]

    fresh = newly_opened(scheduled, since, now)
    embed, _ = announcement_for(flashback_pin, fresh[0], scheduled, {})

    assert fresh == [live]
    assert "Next Up:" in embed.description
    assert "Bloomburrow" in embed.description


def test_next_rotation_is_none_when_nothing_follows():
    now = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
    current = _group("Arena Powered Cube", ("cube",), ["Premier Draft"], now, now + timedelta(days=6))

    assert next_rotation([current], current) is None


def test_select_groups_ors_flashback_and_quick():
    now = datetime.now(timezone.utc)
    events = [
        _event("Premier Draft", "Aetherdrift", ("arena", "limited", "flashback", "premier-draft"), now, 1, 8),
        _event("Quick Draft", "Bloomburrow", ("arena", "limited", "quick-draft"), now, 1, 8),
        _event("Premier Draft", "Secrets of Strixhaven", ("arena", "limited", "premier-draft"), now, 1, 8),
    ]

    _, upcoming = select_groups(events, ["flashback", "quick"], apply_horizon=True)

    labels = {group.label for group in upcoming}
    assert labels == {"Aetherdrift", "Bloomburrow"}


def test_select_groups_cube_filter_matches_cube_tag():
    now = datetime.now(timezone.utc)
    events = [
        _event("Premier Draft", "Arena Powered Cube", ("arena", "limited", "premier-draft", "cube"), now, 1, 8),
        _event("Premier Draft", "Secrets of Strixhaven", ("arena", "limited", "premier-draft"), now, 1, 8),
    ]

    _, upcoming = select_groups(events, ["cube"], apply_horizon=True)

    assert [group.label for group in upcoming] == ["Arena Powered Cube"]


@pytest.mark.parametrize("filters,set_query,expected", [
    (["sealed"], "The Hobbit", "https://mtgscribe.com/events/list/?tribe-bar-search=Sealed+Hobbit"),
    (["sealed", "quick"], None, "https://mtgscribe.com/events/"),
    (None, None, "https://mtgscribe.com/events/"),
])
def test_scribe_url_follows_the_selection(filters, set_query, expected):
    assert scribe_url(filters, set_query) == expected


@pytest.mark.parametrize("tags,formats,expected", [
    (("flashback",), ["Premier Draft"], "Flashback"),
    (("qualifier",), ["Qualifier Play-In"], "Competitive"),
    (("cube",), ["Premier Draft"], ""),
    ((), ["Quick Draft"], "Quick Draft"),
    ((), ["Sealed"], "Sealed"),
])
def test_announcement_format_keys_on_group_type(tags, formats, expected):
    now = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
    group = _group("Set", tags, formats, now, now + timedelta(days=7))

    assert announcement_format(group) == expected


def test_already_announced_matches_word_and_label_together():
    word = "Flashback"
    recent = ["### **Aetherdrift** Flashback is live!\nEnds June 23 (in 7 days)"]

    assert already_announced(recent, word, "Aetherdrift")
    assert not already_announced(recent, word, "Bloomburrow")
    assert not already_announced(recent, "Quick Draft", "Aetherdrift")
