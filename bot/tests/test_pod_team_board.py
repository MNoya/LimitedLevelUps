import discord
import pytest

from bot.services import pod_team
from bot.services.pod_drafts import normalize_player_name
from bot.services.pod_team_board import (
    PROGRESS_GAP,
    PROGRESS_PENDING,
    PROGRESS_SKIPPED,
    REPORT_BUTTON_PREFIX,
    REVEAL_BUTTON_PREFIX,
    TeamBoardView,
    _round_all_reported,
    _round_has_playable_match,
    blocking_round,
    build_board_data,
    build_team_board_views,
    build_team_round_view,
    build_team_summary,
    clinched,
    match_line,
    match_progress_bar,
)
from bot.services.pod_tournament import SKIPPED_SENTINEL


GREEN = ["Ava", "Cara", "Eli"]
BLUE = ["Bram", "Dex", "Fern"]


def _fixture_data(reported=(), finalized=False, green=GREEN, blue=BLUE):
    """Board data for a green-vs-blue roster. `reported` is (match_index, winner_name, score)
    triples applied over the pending slate, match_index counting across rounds in rotation order."""
    seat_order = [name for pair in zip(green, blue) for name in pair]
    teams = pod_team.assign_teams(seat_order)
    team_rows = [(name, teams[name]) for name in seat_order]
    displays = {
        normalize_player_name(name): {"display_name": name, "arena": f"{name.lower()}#1000{i}"}
        for i, name in enumerate(seat_order)
    }
    matches = []
    for round_num in (1, 2, 3):
        for a, b in pod_team.pair_round(green, blue, round_num):
            matches.append({
                "match_id": f"m{len(matches)}", "round": round_num,
                "a_name": a, "b_name": b, "winner_name": None, "score": None,
            })
    for index, winner, score in reported:
        matches[index].update(winner_name=winner, score=score)
    return build_board_data("event-1", team_rows, matches, displays, finalized)


def _single_view(data) -> TeamBoardView:
    (view,) = build_team_board_views(data)
    return view


def _sections(view: TeamBoardView):
    (container,) = view.children
    return [item for item in container.children if isinstance(item, discord.ui.Section)]


def _button(section):
    return section.accessory.item


def _round_headers(view: TeamBoardView):
    (container,) = view.children
    return [
        item.content for item in container.children
        if isinstance(item, discord.ui.TextDisplay) and "### Round" in item.content
    ]


def test_board_data_counts_wins_and_pending_by_winner_team():
    data = _fixture_data(reported=[(0, "Ava", "2-0"), (1, "Dex", "2-1"), (2, "Fern", "2-0")])

    assert data.wins == {pod_team.TEAM_A: 1, pod_team.TEAM_B: 2}
    assert data.pending == 6


def test_board_data_skipped_match_is_not_pending_and_scores_nothing():
    data = _fixture_data(reported=[(0, SKIPPED_SENTINEL, "0-0")])

    assert data.wins == {pod_team.TEAM_A: 0, pod_team.TEAM_B: 0}
    assert data.pending == 8


def test_view_renders_all_nine_matches_grouped_in_three_rounds():
    view = _single_view(_fixture_data())

    assert len(_sections(view)) == 9
    assert len(_round_headers(view)) == 3


def test_pending_button_is_grey_report():
    view = _single_view(_fixture_data())

    button = _button(_sections(view)[0])

    assert button.style is discord.ButtonStyle.secondary
    assert button.label == "Report"
    assert not button.disabled


def test_reported_buttons_recolor_by_winning_team_with_score_label():
    data = _fixture_data(reported=[(0, "Ava", "2-0"), (1, "Dex", "2-1")])

    view = _single_view(data)
    green_win, blue_win = _button(_sections(view)[0]), _button(_sections(view)[1])

    assert green_win.style is discord.ButtonStyle.success
    assert green_win.label == "2-0"
    assert blue_win.style is discord.ButtonStyle.primary
    assert blue_win.label == "2-1"


def test_finalized_board_disables_every_button():
    data = _fixture_data(reported=[(0, "Ava", "2-0")], finalized=True)

    view = _single_view(data)

    assert all(_button(s).disabled for s in _sections(view))


def test_summary_embed_column_headers_carry_no_score():
    embed, _ = build_team_summary(_fixture_data(reported=[(0, "Ava", "2-0"), (3, "Ava", "2-1")]))

    assert all(not any(ch.isdigit() for ch in field.name) for field in embed.fields)


def test_summary_embed_splits_names_and_arena_handles_into_two_columns():
    embed, _ = build_team_summary(_fixture_data())

    assert len(embed.fields) == 6
    assert all(field.inline for field in embed.fields)
    name_lines = embed.fields[0].value.splitlines()
    arena_lines = embed.fields[1].value.splitlines()
    assert len(name_lines) == len(arena_lines) == 3
    assert all(line.startswith("> ") for line in name_lines)
    assert any("Ava" in line for line in name_lines)
    assert any("ava#" in line for line in arena_lines)
    assert not any("ava#" in line for line in name_lines)


@pytest.mark.parametrize("winner,score,expected_names_order", [
    (None, None, ("Ava", "Bram")),
    ("Ava", "2-1", ("Ava", "Bram")),
    ("Bram", "2-0", ("Bram", "Ava")),
])
def test_match_line_shows_matchup_then_result_winner_first(winner, score, expected_names_order):
    m = {
        "match_id": "m0", "round": 1, "a_name": "Ava", "b_name": "Bram",
        "a_display": "Ava", "b_display": "Bram", "winner_name": winner, "score": score,
    }

    line = match_line(m)

    first, second = expected_names_order
    assert line.index(first) < line.index(second)
    if score:
        assert score in line


def test_match_line_marks_skipped_match():
    m = {
        "match_id": "m0", "round": 1, "a_name": "Ava", "b_name": "Bram",
        "a_display": "Ava", "b_display": "Bram", "winner_name": SKIPPED_SENTINEL, "score": "0-0",
    }

    line = match_line(m)

    assert "Ava" in line and "Bram" in line
    assert "wins" not in line


@pytest.mark.parametrize("size,expected_sections_per_page", [(3, [9]), (4, [8, 4]), (5, [10, 5])])
def test_three_v_three_fits_one_message_and_larger_boards_paginate(size, expected_sections_per_page):
    green = [f"G{i}" for i in range(size)]
    blue = [f"B{i}" for i in range(size)]
    data = _fixture_data(green=green, blue=blue)

    views = build_team_board_views(data)

    assert [len(_sections(v)) for v in views] == expected_sections_per_page
    all_ids = [id_ for v in views for id_ in sorted(v.report_custom_ids)]
    assert len(all_ids) == len(set(all_ids)) == size * 3


def test_only_the_last_page_closes_with_the_divider_and_bar():
    green = [f"G{i}" for i in range(5)]
    blue = [f"B{i}" for i in range(5)]

    *earlier, last = build_team_board_views(_fixture_data(green=green, blue=blue))

    (last_container,) = last.children
    assert isinstance(last_container.children[-2], discord.ui.Separator)
    assert PROGRESS_PENDING in last_container.children[-1].content
    for view in earlier:
        (container,) = view.children
        assert container.children[0].content.startswith("### Round")
        assert not any(isinstance(item, discord.ui.Separator) for item in container.children)
        text_items = [item for item in container.children if isinstance(item, discord.ui.TextDisplay)]
        assert not any(PROGRESS_PENDING in item.content for item in text_items)


def test_progress_bar_maps_each_match_to_its_state_and_shows_the_bolded_score():
    data = _fixture_data(reported=[(0, "Ava", "2-0"), (1, "Dex", "2-1"), (2, SKIPPED_SENTINEL, "0-0")])

    icons, tail = match_progress_bar(data).split(PROGRESS_GAP, 1)

    green, blue = pod_team.TEAM_EMOJI[pod_team.TEAM_A], pod_team.TEAM_EMOJI[pod_team.TEAM_B]
    assert icons.split("|") == [green, blue, PROGRESS_SKIPPED] + [PROGRESS_PENDING] * 6
    assert "1-1" in tail
    assert tail.startswith("**") and tail.endswith("**")
    assert pod_team.team_label(pod_team.TEAM_A) not in tail
    assert pod_team.team_label(pod_team.TEAM_B) not in tail


def test_progress_bar_status_tracks_lead_win_and_fresh_board_with_leader_first_score():
    fresh = match_progress_bar(_fixture_data())
    blue_lead = match_progress_bar(_fixture_data(reported=[(0, "Bram", "2-0")]))
    all_in = _fixture_data(reported=[
        (i, name, "2-0") for i, name in enumerate(["Ava", "Dex", "Eli", "Ava", "Cara", "Eli", "Ava", "Cara", "Eli"])
    ])

    assert fresh.split(PROGRESS_GAP, 1)[1] == "**0-0**"
    blue_tail = blue_lead.split(PROGRESS_GAP, 1)[1]
    assert "1-0" in blue_tail and pod_team.team_label(pod_team.TEAM_B) in blue_tail
    win_tail = match_progress_bar(all_in).split(PROGRESS_GAP, 1)[1]
    assert "8-1" in win_tail and pod_team.team_label(pod_team.TEAM_A) in win_tail


def test_round_has_playable_match_needs_both_players_free_of_prior_rounds():
    none_done = _fixture_data()
    one_r1_done = _fixture_data(reported=[(0, "Ava", "2-0")])
    two_r1_done = _fixture_data(reported=[(0, "Ava", "2-0"), (1, "Dex", "2-1")])

    assert _round_has_playable_match(none_done, 1) is True
    assert _round_has_playable_match(none_done, 2) is False
    assert _round_has_playable_match(one_r1_done, 2) is False
    assert _round_has_playable_match(two_r1_done, 2) is True


@pytest.mark.parametrize("a_wins,b_wins,pending,expected", [
    (0, 0, 9, False),
    (2, 1, 6, False),
    (4, 1, 4, False),
    (5, 1, 3, True),
    (5, 4, 0, True),
    (3, 3, 0, True),
])
def test_clinched_when_the_lead_outruns_the_matches_left(a_wins, b_wins, pending, expected):
    assert clinched(a_wins, b_wins, pending) is expected


def test_blocking_round_names_the_earliest_round_still_holding_either_player():
    two_r1_done = _fixture_data(reported=[(0, "Ava", "2-0"), (1, "Dex", "2-1")])
    round2 = dict(_matches_in_round(two_r1_done, 2))

    assert blocking_round(two_r1_done, round2["Ava"]) is None
    assert blocking_round(two_r1_done, round2["Cara"]) == 1
    assert blocking_round(two_r1_done, round2["Eli"]) == 1


def test_blocking_round_clears_once_both_players_are_free():
    all_r1_done = _fixture_data(
        reported=[(0, "Ava", "2-0"), (1, "Dex", "2-1"), (2, SKIPPED_SENTINEL, "0-0")],
    )
    round2 = dict(_matches_in_round(all_r1_done, 2))

    assert all(blocking_round(all_r1_done, m) is None for m in round2.values())


def _matches_in_round(data, round_num):
    for r, matches in data.rounds:
        if r == round_num:
            return [(m["a_name"], m) for m in matches]
    return []


def test_round_has_playable_match_counts_skips_as_finished():
    two_done_one_skip = _fixture_data(reported=[(0, "Ava", "2-0"), (1, SKIPPED_SENTINEL, "0-0")])

    assert _round_has_playable_match(two_done_one_skip, 2) is True


def test_round_all_reported_only_when_every_match_in_round_has_a_result():
    partial = _fixture_data(reported=[(0, "Ava", "2-0"), (1, "Dex", "2-1")])
    full_r1 = _fixture_data(reported=[(0, "Ava", "2-0"), (1, "Dex", "2-1"), (2, "Fern", "2-0")])

    assert _round_all_reported(partial, 1) is False
    assert _round_all_reported(full_r1, 1) is True
    assert _round_all_reported(full_r1, 2) is False


def test_big_block_and_reveal_use_distinct_button_prefixes():
    data = _fixture_data()

    big_ids = set().union(*(view.report_custom_ids for view in build_team_board_views(data)))
    reveal_ids = build_team_round_view(data, 2).report_custom_ids

    assert big_ids and all(i.startswith(f"{REPORT_BUTTON_PREFIX}:") for i in big_ids)
    assert reveal_ids and all(i.startswith(f"{REVEAL_BUTTON_PREFIX}:") for i in reveal_ids)
    assert not (big_ids & reveal_ids)


def test_reveal_view_footer_is_cumulative_and_round_one_has_none():
    data = _fixture_data(reported=[(0, "Ava", "2-0"), (1, "Dex", "2-1"), (2, "Fern", "2-0")])

    round_one = build_team_round_view(data, 1)
    round_two = build_team_round_view(data, 2)

    (c1,) = round_one.children
    (c2,) = round_two.children
    r1_bars = [i.content for i in c1.children if isinstance(i, discord.ui.TextDisplay) and "|" in i.content]
    r2_bars = [i.content for i in c2.children if isinstance(i, discord.ui.TextDisplay) and "|" in i.content]
    assert r1_bars == []
    assert r2_bars and r2_bars[0].split(PROGRESS_GAP, 1)[0].count("|") == 5
