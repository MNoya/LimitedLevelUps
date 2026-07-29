import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from bot.services import pod_tournament
from bot.services.ping_roles import plan_set_champion_swap
from bot.services.pod_tournament import (
    ANNOUNCEMENT_TOP_N,
    CHAMPION_TITLE_GLYPH,
    CHAMPIONSHIP_DECK_HEADER,
    SET_CHAMPION_TITLE_GLYPH,
    _format_champion_title,
    ParticipantDeckData,
    deck_complete,
    incomplete_champion_decks,
    incomplete_top_decks,
    normalize_player_name,
    build_deck_ping,
    deck_missing_parts,
    format_reported_result,
    format_round_announcement,
    tally_match_records,
)


def test_reconcile_rearms_within_deck_wait_but_forces_once_it_elapses(monkeypatch):
    """A restart still inside the deck-wait must not jump the gate: recently-finalized pods post
    non-forced (so an incomplete winning set keeps holding) and re-arm the remaining wait, while a pod
    whose wait already elapsed posts forced."""
    now = datetime.now(timezone.utc)
    within = now - timedelta(seconds=30)
    elapsed = now - timedelta(seconds=pod_tournament.CHAMPIONSHIP_DEADLINE_SECONDS + 300)
    monkeypatch.setattr(
        pod_tournament, "_load_unannounced_finalized_sync",
        lambda: [("recent", "t1", within), ("old", "t2", elapsed)],
    )
    posts = []
    rearms = []

    async def fake_post(bot, event_id, thread_id, *, force=True):
        posts.append((event_id, force))
        return True

    async def fake_delayed(bot, event_id, thread_id, delay):
        rearms.append(event_id)

    monkeypatch.setattr(pod_tournament, "post_championship_for_event", fake_post)
    monkeypatch.setattr(pod_tournament, "_delayed_championship_post", fake_delayed)

    async def run():
        await pod_tournament.reconcile_unannounced_championships(bot=None)
        await asyncio.sleep(0)

    asyncio.run(run())

    assert ("recent", False) in posts
    assert ("old", True) in posts
    assert rearms == ["recent"]


def test_post_trophy_hype_forwards_format_title_to_view(monkeypatch):
    """Regression: the team 3-0 card passes a custom title formatter; post_trophy_hype must forward it
    to the view builder rather than dropping it (it used to raise TypeError)."""
    captured = {}

    def fake_build(champions, **kwargs):
        captured.update(kwargs)
        return "view"

    class _Channel:
        id = 1

        async def send(self, **kwargs):
            return None

    async def fake_scan(channel, after, recap_url):
        return set(), False

    monkeypatch.setattr(pod_tournament, "build_trophy_hype_view", fake_build)
    monkeypatch.setattr(pod_tournament, "_find_trophy_hype_channel", lambda guild: _Channel())
    monkeypatch.setattr(pod_tournament, "load_event_started_at_sync", lambda event_id: None)
    monkeypatch.setattr(pod_tournament, "_scan_trophy_hype_channel", fake_scan)

    def fmt(name, colors, short_event):
        return f"{name} goes 3-0"

    champion = SimpleNamespace(player_name="Noya", wins=3, losses=0)

    async def run():
        return await pod_tournament.post_trophy_hype(
            "e1", SimpleNamespace(id=9, roles=[]), 123, [champion],
            event_name="Pod", displays={}, player_colors={}, deck_data={}, dm_info={},
            format_title=fmt,
        )

    result = asyncio.run(run())

    assert result is True
    assert captured.get("format_title") is fmt


def test_deck_complete_requires_colors_and_screenshot():
    assert deck_complete(_deck("WU", "http://img/x.png"))
    assert not deck_complete(_deck("WU", None))
    assert not deck_complete(_deck(None, "http://img/x.png"))
    assert not deck_complete(None)


def test_championship_clear_when_top_finishers_all_complete():
    standings = _standings("Aria", "Bryn", "Caedmon", "Doryn", "Esk")
    deck_data = _complete_decks("Aria", "Bryn", "Caedmon", "Doryn")
    assert incomplete_top_decks(standings, deck_data) == []


def test_championship_waits_on_missing_top_finisher():
    standings = _standings("Aria", "Bryn", "Caedmon", "Doryn")
    deck_data = _complete_decks("Aria", "Bryn", "Caedmon")
    deck_data[normalize_player_name("Doryn")] = _deck("WU", None)
    assert incomplete_top_decks(standings, deck_data) == ["Doryn"]


def test_championship_ignores_players_outside_top_n():
    extra = "Faron"
    standings = _standings("Aria", "Bryn", "Caedmon", "Doryn", extra)
    deck_data = _complete_decks("Aria", "Bryn", "Caedmon", "Doryn")
    assert incomplete_top_decks(standings, deck_data) == []


def test_championship_requires_all_when_pod_smaller_than_top_n():
    standings = _standings("Aria", "Bryn", "Caedmon")
    assert len(standings) < ANNOUNCEMENT_TOP_N
    deck_data = _complete_decks("Aria", "Bryn")
    assert incomplete_top_decks(standings, deck_data) == ["Caedmon"]


def test_trophy_hype_waits_on_champions_only():
    champions = _standings("Aria", "Bryn")
    deck_data = _complete_decks("Aria")
    deck_data[normalize_player_name("Bryn")] = _deck("WU", None)
    deck_data[normalize_player_name("Caedmon")] = _deck(None, None)

    assert incomplete_champion_decks(champions, deck_data) == ["Bryn"]


def test_deck_missing_parts_reports_each_gap():
    assert deck_missing_parts(_deck("WU", "http://img/x.png")) == []
    assert deck_missing_parts(_deck("WU", None)) == ["screenshot"]
    assert deck_missing_parts(_deck(None, "http://img/x.png")) == ["colors"]
    assert deck_missing_parts(_deck(None, None)) == ["screenshot", "colors"]
    assert deck_missing_parts(None) == ["screenshot", "colors"]


def test_deck_ping_is_action_forward_split_by_audience():
    text = build_deck_ping((["1"], ["1", "2"]), (["3"], ["3"]), "https://limitedlevelups.com/pods/pod-7")

    assert text == (
        "Championship post is waiting on a few decks 🏆\n"
        "Please post your deck screenshot <@1> <@3>\n"
        "Submit your deck colors with the button below <@1> <@2> <@3>\n"
        "\n"
        "Draft Recap at [limitedlevelups.com/pods/pod-7]"
        "(https://limitedlevelups.com/pods/pod-7) 🎨"
    )


def test_deck_ping_pod_link_embeds_and_hides_scheme():
    text = build_deck_ping(([], []), (["3"], []), "https://limitedlevelups.com/pods/pod-7")
    assert "[limitedlevelups.com/pods/pod-7](https://limitedlevelups.com/pods/pod-7)" in text


def test_deck_ping_drops_championship_header_once_post_is_clear():
    text = build_deck_ping(([], []), (["3"], ["3"]), "https://limitedlevelups.com/pods/pod-7")
    assert CHAMPIONSHIP_DECK_HEADER not in text
    assert "<@3>" in text


def test_deck_ping_is_empty_when_nobody_owes_anything():
    assert build_deck_ping(([], []), ([], []), "https://limitedlevelups.com/pods/pod-7") == ""


def test_tally_match_records_shows_partial_wl_before_finalize():
    rows = [
        ("Alice#1", "Bob#2", "Alice#1"),
        ("Alice#1", "Cara#3", "Alice#1"),
        ("Bob#2", "Cara#3", None),          # R3 not yet reported
        ("Dez#4", "Eve#5", "(skipped)"),    # no match played
    ]

    records = tally_match_records(rows)

    assert records["alice"] == "2-0"
    assert records["bob"] == "0-1"          # partial: one loss so far, R3 pending
    assert records["cara"] == "0-1"
    assert "dez" not in records and "eve" not in records


def test_reported_result_uses_display_names_either_side():
    match = {
        "a_name": "marlo#1", "b_name": "bob#2",
        "a_display": "Marlo", "b_display": "Bob", "score": "2-1",
    }

    assert format_reported_result({**match, "winner_name": "marlo#1"}) == "Marlo wins 2-1 vs Bob"
    assert format_reported_result({**match, "winner_name": "bob#2"}) == "Bob wins 2-1 vs Marlo"


def test_round_announcement_prefixes_the_round_label():
    match = {
        "a_name": "marlo#1", "b_name": "bob#2",
        "a_display": "Marlo", "b_display": "Bob", "score": "2-0",
        "winner_name": "marlo#1",
    }

    assert format_round_announcement(1, match) == "**Round 1** Marlo wins 2-0 vs Bob"

    linked = format_round_announcement(3, match, "https://discord.com/channels/1/2/3")
    assert linked == "**[__Round 3__](https://discord.com/channels/1/2/3)** Marlo wins 2-0 vs Bob"


def _standings(*names: str) -> list:
    return [SimpleNamespace(player_name=n) for n in names]


def _deck(colors: str | None, screenshot: str | None) -> ParticipantDeckData:
    return ParticipantDeckData(colors=colors, screenshot_url=screenshot, screenshot_caption=None)


def _complete_decks(*names: str) -> dict:
    return {normalize_player_name(n): _deck("WU", "http://img/x.png") for n in names}


def test_champion_title_crowns_a_set_championship_without_doubling_the_glyph():
    title = _format_champion_title([("ironick", None)], "👑 MSH Set Championship")

    assert title.startswith(SET_CHAMPION_TITLE_GLYPH)
    assert CHAMPION_TITLE_GLYPH not in title
    assert title.count(SET_CHAMPION_TITLE_GLYPH) == 1


def test_champion_title_keeps_the_trophy_for_a_regular_pod():
    title = _format_champion_title([("ironick", None)], "MSH Jul 21 Late Pod")

    assert title.startswith(CHAMPION_TITLE_GLYPH)
    assert SET_CHAMPION_TITLE_GLYPH not in title


def test_champion_role_swap_moves_outgoing_holders_and_leaves_a_repeat_winner_alone():
    cases = [
        (({"1", "2"}, {"3"}), ({"1", "2"}, {"3"})),
        (({"1"}, {"1"}), (set(), set())),
        ((set(), {"9"}), (set(), {"9"})),
        (({"1", "2"}, {"2", "5"}), ({"1"}, {"5"})),
    ]
    for (holders, champions), expected in cases:
        assert plan_set_champion_swap(holders, champions) == expected
