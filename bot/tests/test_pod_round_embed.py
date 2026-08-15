import re

from bot.services.pod_tournament import (
    DECK_IMAGE_NOTICE,
    LAST_CHANCE,
    LOSERS,
    MIDDLE,
    NBSP,
    REPORT_NOTICE,
    PAIR_UP,
    TROPHY,
    WINNERS,
    _ROUND_TITLE_RE,
    MatchResultSelect,
    RoundResultsView,
    round_header,
    _waiting_footer_line,
    mark_trophy_match,
    round_embed,
    round_groups,
)


# --- grouping data model (presentation-free; stable across formatting changes) ---

def test_round2_eight_players_split_into_winners_and_losers():
    states = [
        _ms("Aria", "Caedmon", "1-0", "1-0"),
        _ms("Esk", "Gwyn", "1-0", "1-0"),
        _ms("Bryn", "Doryn", "0-1", "0-1"),
        _ms("Fenn", "Hale", "0-1", "0-1"),
    ]
    groups = round_groups(2, states)
    assert _kinds(groups) == [WINNERS, LOSERS]
    assert _pairs(groups[0][1]) == {frozenset(("Aria", "Caedmon")), frozenset(("Esk", "Gwyn"))}
    assert _pairs(groups[1][1]) == {frozenset(("Bryn", "Doryn")), frozenset(("Fenn", "Hale"))}


def test_round2_six_players_insert_pair_up_between_brackets():
    states = [
        _ms("Aria", "Caedmon", "1-0", "1-0"),
        _ms("Bryn", "Esk", "0-1", "1-0"),
        _ms("Doryn", "Fenn", "0-1", "0-1"),
    ]
    groups = round_groups(2, states)
    assert _kinds(groups) == [WINNERS, PAIR_UP, LOSERS]
    assert _pairs(groups[1][1]) == {frozenset(("Bryn", "Esk"))}


def test_round2_ten_players_two_brackets_plus_pair_up():
    states = [
        _ms("Aria", "Caedmon", "1-0", "1-0"),
        _ms("Esk", "Gwyn", "1-0", "1-0"),
        _ms("Iris", "Bryn", "1-0", "0-1"),
        _ms("Doryn", "Fenn", "0-1", "0-1"),
        _ms("Hale", "Juno", "0-1", "0-1"),
    ]
    groups = round_groups(2, states)
    assert _kinds(groups) == [WINNERS, PAIR_UP, LOSERS]
    assert [len(ms) for _, ms in groups] == [2, 1, 2]


def test_final_round_splits_trophy_middle_last_chance():
    states = [
        _ms("Aria", "Esk", "2-0", "2-0"),
        _ms("Bryn", "Caedmon", "1-1", "1-1"),
        _ms("Doryn", "Fenn", "1-1", "1-1"),
        _ms("Gwyn", "Hale", "0-2", "0-2"),
    ]
    mark_trophy_match(states, 3)
    groups = round_groups(3, states)
    assert _kinds(groups) == [TROPHY, MIDDLE, LAST_CHANCE]
    assert [len(ms) for _, ms in groups] == [1, 2, 1]
    assert _pairs(groups[0][1]) == {frozenset(("Aria", "Esk"))}


# --- dropdown order matches the embed ---

def test_round_results_view_orders_dropdowns_like_the_embed():
    states = [  # interleaved by record, as incremental bracket creation produces
        _ms("Noya", "Bram", "1-0", "1-0"),
        _ms("Eli", "Fern", "0-1", "0-1"),
        _ms("Gus", "Hana", "1-0", "1-0"),
        _ms("Cara", "Dex", "0-1", "0-1"),
    ]

    view = RoundResultsView(states, round_num=2)

    dropdown_ids = [
        child.options[0].value.split("|")[0]
        for child in view.children
        if isinstance(child, MatchResultSelect)
    ]
    embed_ids = [m["match_id"] for _, group in round_groups(2, states) for m in group]
    assert dropdown_ids == embed_ids
    assert dropdown_ids == ["Noya-Bram", "Gus-Hana", "Eli-Fern", "Cara-Dex"]


# --- rendering ---

def test_round2_renders_three_groups_with_records_on_the_pair_up():
    states = [
        _ms("Aria", "Caedmon", "1-0", "1-0"),
        _ms("Bryn", "Esk", "0-1", "1-0"),
        _ms("Doryn", "Fenn", "0-1", "0-1"),
    ]
    groups = _norm(round_embed(2, states).description).split("\n\n")
    assert all(part in groups[0] for part in ("Aria", "Caedmon"))
    assert all(part in groups[1] for part in ("Esk", "(1-0)", "Bryn", "(0-1)"))
    assert all(part in groups[2] for part in ("Doryn", "Fenn"))


def test_round1_seated_annotates_seat_pairings():
    states = [_seated("Aria", "Bryn", 1, 5), _seated("Caedmon", "Doryn", 2, 6)]
    embed = round_embed(1, states)
    assert "Aria vs Bryn (1v5)" in _norm(embed.description)


def test_round1_without_seats_drops_seat_annotation():
    embed = round_embed(1, [_ms("Aria", "Bryn")])
    assert "(1v" not in embed.description


def test_round1_shows_arena_only_when_name_matches():
    states = [_seated("Aria", "Bryn", 1, 5, a_arena="Aria#08011", b_arena="Bryn#22222")]
    desc = _norm(round_embed(1, states).description)
    assert "`Aria#08011`" in desc
    assert "(Aria)" not in desc


def test_round1_appends_discord_name_when_it_diverges():
    states = [_seated("Marlo", "Aria", 1, 5, a_arena="driftwood#49190", b_arena="Aria#08011")]
    desc = _norm(round_embed(1, states).description)
    assert "`driftwood#49190` (Marlo)" in desc
    assert "`Aria#08011`" in desc
    assert "(Aria)" not in desc


def test_round1_omits_arena_when_unknown():
    states = [_seated("Aria", "Bryn", 1, 5, a_arena=None, b_arena=None)]
    desc = _norm(round_embed(1, states).description)
    assert "Aria vs Bryn (1v5)" in desc


def test_later_rounds_also_annotate_arena():
    states = [_ms("Aria", "Caedmon", "1-0", "1-0", a_arena="Aria#11111", b_arena="Caedmon#33333")]
    desc = _norm(round_embed(2, states).description)
    assert "`Aria#11111`" in desc
    assert "`Caedmon#33333`" in desc


def test_reported_and_skipped_lines_drop_the_pending_marker():
    states = [
        _ms("Aria", "Caedmon", "1-0", "1-0", winner_name="Aria", score="2-1"),
        _ms("Esk", "Gwyn", "1-0", "1-0", winner_name="(skipped)"),
    ]
    lines = _norm(round_embed(2, states).description).splitlines()
    reported = next(line for line in lines if "Aria" in line)
    assert "2-1" in reported
    assert "Caedmon" in reported
    skipped = next(line for line in lines if "Esk" in line)
    assert "Gwyn" in skipped
    assert "⚔️" not in reported
    assert "⚔️" not in skipped


def test_round_notices_are_round_one_only_and_stay_when_complete():
    pending = [_ms("Aria", "Caedmon")]
    done = [_ms("Aria", "Caedmon", winner_name="Aria", score="2-0")]

    for notice in (REPORT_NOTICE, DECK_IMAGE_NOTICE):
        assert notice in round_embed(1, pending).description
        assert notice in round_embed(1, done).description
        assert notice not in round_embed(2, pending).description


def _waiting_placeholder(pending: int = 1, prev_round: int = 1, url: str | None = None) -> dict:
    return {"placeholder": True, "label": f"waiting on Round {prev_round}", "waiting_prev_round": prev_round,
            "waiting_pending": pending, "waiting_prev_url": url, "a_record": "0-1", "b_record": "0-1",
            "winner_name": None, "score": None}


def test_bracket_footer_present_only_when_slots_wait():
    waiting = [_ms("Aria", "Caedmon", "1-0", "1-0"), _waiting_placeholder()]
    settled = [_ms("Aria", "Caedmon", "1-0", "0-1")]

    assert _waiting_footer_line(waiting) is not None
    assert _waiting_footer_line(settled) is None


def test_bracket_footer_links_previous_round_when_url_known():
    states = [_ms("Aria", "Caedmon", "1-0", "1-0"), _waiting_placeholder(url="https://discord.test/r1")]

    assert "https://discord.test/r1" in round_embed(2, states).description


def _ms(a: str, b: str, a_record: str = "0-0", b_record: str = "0-0", **extra) -> dict:
    state = {
        "match_id": f"{a}-{b}",
        "a_name": a, "b_name": b,
        "a_display": a, "b_display": b,
        "a_record": a_record, "b_record": b_record,
        "winner_name": None, "score": None,
    }
    state.update(extra)
    return state


def _seated(a: str, b: str, a_seat: int, b_seat: int, **extra) -> dict:
    return _ms(a, b, a_seat=a_seat, b_seat=b_seat, **extra)


def _kinds(groups) -> list[str]:
    return [kind for kind, _ in groups]


def _pairs(matches) -> set[frozenset[str]]:
    return {frozenset((m["a_name"], m["b_name"])) for m in matches}


def _norm(desc: str) -> str:
    """Collapse NBSP / space runs so render assertions don't pin exact whitespace."""
    return re.sub(f"[ {NBSP}]+", " ", desc)


def test_round_header_title_carries_round_number_for_recovery():
    cases = [
        (round_num, complete, seated)
        for round_num in (1, 2, 3)
        for complete in (True, False)
        for seated in (True, False)
    ]

    for round_num, complete, seated in cases:
        title = round_header(round_num, complete, seated=seated)
        match = _ROUND_TITLE_RE.search(title)

        assert match is not None, f"recovery regex missed title {title!r}"
        assert int(match.group(1)) == round_num
