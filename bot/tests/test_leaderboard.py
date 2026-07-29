from datetime import date, datetime, timezone

import pytest

from bot.commands.leaderboard import (
    LcqExtras,
    LeaderboardData,
    LeaderboardEntry,
    PersonalStanding,
    PersonalStandingsData,
    _is_soup,
    decode_filter,
    encode_filter,
    process_leaderboard,
    process_leaderboard_for_archetype,
    process_leaderboard_for_format,
    process_leaderboard_for_lcq,
    process_leaderboard_for_peasant,
    process_personal_standings,
    render_filtered_data,
    render_personal_embed,
    render_public_embed,
)
from bot.services.player_stats import StatsData, process_stats, render_embed as render_stats_embed
from bot.models import DraftEvent, MagicSet, Player, PlayerStats, PodDraftEvent, PodDraftParticipant
from bot.sets import active_set_code
from bot.config import settings


def _seed_set(session, code="SOS"):
    s = MagicSet(code=code, name=code, start_date=date(2026, 4, 21))
    session.add(s)
    session.flush()
    return s


def _seed_player(session, name, discord_id, token_suffix, active=True, leaderboard_opt_in=True):
    token = (token_suffix * 32)[:32]
    p = Player(
        slug=f"{name.lower()}-{discord_id}",
        discord_id=discord_id,
        discord_username=name.lower(),
        display_name=name,
        seventeenlands_token=token,
        active=active,
        leaderboard_opt_in=leaderboard_opt_in,
    )
    session.add(p)
    session.flush()
    return p


def _seed_stats(session, p, s, trophies=0, events=1, fmt="PremierDraft", expansion=None, wins=None, losses=None):
    """Single PlayerStats row, defaults to Premier so compute_score weights it at 10pts.

    A row with (trophies=0, events=N) yields score=0 — same effect as the old _score(score=0).
    Explicit wins/losses override the trophy-derived defaults for wins-scored formats like LCQ Draft 2.
    """
    session.add(PlayerStats(
        player_id=p.id, set_id=s.id, format=fmt, expansion=expansion or s.code,
        events=events, wins=trophies * 7 if wins is None else wins,
        losses=max(0, events - trophies) if losses is None else losses,
        games_played=events * 5, trophies=trophies,
    ))


def test_leaderboard_returns_none_when_no_set_seeded(session):
    assert process_leaderboard(session, viewer_discord_id=None) is None


def test_leaderboard_falls_back_to_latest_seeded_set_when_active_missing(session):
    ecl = _seed_set(session, code="ECL")
    alice = _seed_player(session, "Alice", "1", "a")
    _seed_stats(session, alice, ecl, trophies=3, events=5)
    session.commit()

    data = process_leaderboard(session, viewer_discord_id=None)

    assert data is not None
    assert data.set_code == "ECL"


def test_leaderboard_orders_by_score_desc(session):
    s = _seed_set(session)
    a = _seed_player(session, "Alice", "1", "a")
    b = _seed_player(session, "Bob", "2", "b")
    c = _seed_player(session, "Carol", "3", "c")
    _seed_stats(session, a, s, trophies=2, events=4)
    _seed_stats(session, b, s, trophies=5, events=8)
    _seed_stats(session, c, s, trophies=1, events=3)
    session.commit()

    data = process_leaderboard(session, viewer_discord_id=None, top_n=3)
    assert [(e.rank, e.display_name, e.trophies) for e in data.top] == [
        (1, "Bob", 5),
        (2, "Alice", 2),
        (3, "Carol", 1),
    ]


def test_leaderboard_excludes_inactive_players(session):
    s = _seed_set(session)
    a = _seed_player(session, "Alice", "1", "a", active=True)
    b = _seed_player(session, "Bob", "2", "b", active=False)
    _seed_stats(session, a, s, trophies=2, events=4)
    _seed_stats(session, b, s, trophies=10, events=10)
    session.commit()

    data = process_leaderboard(session, viewer_discord_id=None, top_n=3)
    assert [e.display_name for e in data.top] == ["Alice"]


def test_leaderboard_excludes_opted_out_players(session):
    s = _seed_set(session)
    a = _seed_player(session, "Alice", "1", "a")
    b = _seed_player(session, "Bob", "2", "b", leaderboard_opt_in=False)
    _seed_stats(session, a, s, trophies=2, events=4)
    _seed_stats(session, b, s, trophies=10, events=10)
    session.commit()

    data = process_leaderboard(session, viewer_discord_id=None, top_n=3)
    assert [e.display_name for e in data.top] == ["Alice"]


def test_leaderboard_excludes_opted_out_players_with_pod_points(session):
    s = _seed_set(session)
    a = _seed_player(session, "Alice", "1", "a")
    opted_out = _seed_player(session, "Bob", "2", "b", leaderboard_opt_in=False)
    pod_only = _seed_player(session, "Cara", "3", "c")
    _seed_stats(session, a, s, trophies=2, events=4)
    pod = _seed_pod_event(session, s.code, "SOS Pod 1")
    session.add(PodDraftParticipant(
        event_id=pod.id, player_id=opted_out.id, display_name="Bob", placement=1, record="3-0",
    ))
    session.add(PodDraftParticipant(
        event_id=pod.id, player_id=pod_only.id, display_name="Cara", placement=1, record="3-0",
    ))
    session.commit()

    data = process_leaderboard(session, viewer_discord_id=None, top_n=3)

    assert [e.display_name for e in data.top] == ["Alice", "Cara"]


def test_leaderboard_excludes_players_with_no_stats(session):
    s = _seed_set(session)
    a = _seed_player(session, "Alice", "1", "a")
    _seed_player(session, "Newcomer", "2", "b")  # no stats yet
    _seed_stats(session, a, s, trophies=3, events=5)
    session.commit()

    data = process_leaderboard(session, viewer_discord_id=None, top_n=3)
    assert [e.display_name for e in data.top] == ["Alice"]


def test_leaderboard_includes_viewer_outside_top(session):
    s = _seed_set(session)
    for i in range(5):
        p = _seed_player(session, f"P{i}", str(i), chr(ord("a") + i))
        # Higher trophies + higher events → higher score; preserves ordering
        _seed_stats(session, p, s, trophies=10 - i, events=12 - i)
    viewer = _seed_player(session, "Me", "viewer", "z")
    _seed_stats(session, viewer, s, trophies=1, events=20)  # lowest score
    session.commit()

    data = process_leaderboard(session, viewer_discord_id="viewer", top_n=3)
    assert len(data.top) == 3
    assert data.viewer is not None
    assert data.viewer.display_name == "Me"
    assert data.viewer.rank == 6


def test_leaderboard_viewer_none_when_not_registered(session):
    s = _seed_set(session)
    p = _seed_player(session, "Alice", "1", "a")
    _seed_stats(session, p, s, trophies=2, events=4)
    session.commit()

    data = process_leaderboard(session, viewer_discord_id="not_a_user", top_n=3)
    assert data.viewer is None


# ---------------------------------------------------------------------------
# render_public_embed
# ---------------------------------------------------------------------------


def _data(viewer=None, top=None, last_updated=None, drafter_count=0):
    return LeaderboardData(
        set_code="SOS",
        set_name="Secrets of Strixhaven",
        top=top if top is not None else [
            LeaderboardEntry(1, "alice-id", "alice", "Alice", 50.0, 5),
            LeaderboardEntry(2, "bob-id", "bob", "Bob", 30.0, 3),
        ],
        viewer=viewer,
        last_updated=last_updated,
        drafter_count=drafter_count,
    )


def test_stats_embed_opted_out_hides_rank_and_points_keeps_trophies():
    data = StatsData(
        set_code="SOS", set_name="SOS", player_name="Bob", player_slug="bob",
        rank=None, total_score=42.0, total_trophies=3, opted_out=True,
        breakdown=[{"label": "Premier", "events": 2, "wins": 7, "losses": 3, "trophies": 3, "score": 42.0}],
    )
    desc = render_stats_embed(data).description or ""
    summary = desc.split("\n", 1)[0]
    assert "3 🏆" in summary
    assert "#" not in summary
    assert "42.0 pts" not in desc
    assert "pts" not in desc


def test_stats_embed_not_yet_on_board_when_not_opted_out_and_no_rank():
    data = StatsData(
        set_code="SOS", set_name="SOS", player_name="Newcomer", player_slug="new",
        rank=None, total_score=0.0, total_trophies=0, opted_out=False,
    )
    summary = (render_stats_embed(data).description or "").split("\n", 1)[0]
    assert summary
    assert "#" not in summary
    assert "🏆" not in summary


def test_public_embed_omits_you_are_line_for_outside_viewer():
    viewer = LeaderboardEntry(7, "me-id", "me", "Me", 1.0, 0)
    embed = render_public_embed(_data(viewer=viewer))
    assert "#7" not in (embed.description or "")


def test_public_embed_handles_empty_top():
    embed = render_public_embed(_data(top=[]))
    assert embed.description
    assert "Alice" not in embed.description


def test_public_embed_footer_has_drafter_count_and_last_updated():
    embed = render_public_embed(_data(
        last_updated=datetime(2026, 5, 3, 12, 0, 0),
        drafter_count=8,
    ))
    assert "8" in embed.footer.text
    assert "/join" in embed.footer.text
    assert "\n" in embed.footer.text
    assert "netlify" not in embed.footer.text


def test_public_embed_footer_singular_for_one_drafter():
    embed = render_public_embed(_data(
        last_updated=datetime(2026, 5, 3, 12, 0, 0),
        drafter_count=1,
    ))
    assert "1 player" in embed.footer.text
    import re
    assert re.search(r"\bplayers\b", embed.footer.text) is None


def test_public_embed_footer_omits_count_when_zero():
    embed = render_public_embed(_data(
        last_updated=datetime(2026, 5, 3, 12, 0, 0),
        drafter_count=0,
    ))
    assert not any(ch.isdigit() for ch in embed.footer.text)


def test_public_embed_wraps_each_row_in_inline_code():
    embed = render_public_embed(_data(drafter_count=2))
    assert embed.description is not None
    assert embed.description.count("`") >= 2 * 2


# ---------------------------------------------------------------------------
# 0-point hiding
# ---------------------------------------------------------------------------


def test_leaderboard_hides_zero_point_players(session):
    s = _seed_set(session)
    a = _seed_player(session, "Alice", "1", "a")
    b = _seed_player(session, "Bob", "2", "b")
    c = _seed_player(session, "Carol", "3", "c")
    _seed_stats(session, a, s, trophies=2, events=4)
    _seed_stats(session, b, s, trophies=0, events=5)  # no trophies → score 0
    _seed_stats(session, c, s, trophies=1, events=2)
    session.commit()

    data = process_leaderboard(session, viewer_discord_id=None, top_n=10)
    assert [e.display_name for e in data.top] == ["Alice", "Carol"]


def test_leaderboard_zero_point_viewer_still_sees_their_rank(session):
    s = _seed_set(session)
    top = _seed_player(session, "Top", "1", "a")
    me = _seed_player(session, "Me", "viewer", "z")
    _seed_stats(session, top, s, trophies=2, events=4)
    _seed_stats(session, me, s, trophies=0, events=3)  # 0 trophies → 0 score
    session.commit()

    data = process_leaderboard(session, viewer_discord_id="viewer", top_n=10)
    assert data.top == [e for e in data.top if e.score > 0]
    assert data.viewer is not None
    assert data.viewer.display_name == "Me"
    assert data.viewer.score == 0.0


# ---------------------------------------------------------------------------
# drafter_count
# ---------------------------------------------------------------------------


def test_drafter_count_counts_only_players_with_events_in_current_set(session):
    s = _seed_set(session)
    a = _seed_player(session, "Alice", "1", "a")
    b = _seed_player(session, "Bob", "2", "b")
    c = _seed_player(session, "Carol", "3", "c")
    _seed_stats(session, a, s, trophies=1, events=2)   # counted
    _seed_stats(session, b, s, trophies=0, events=0)   # zero events — not counted
    _seed_stats(session, c, s, trophies=0, events=1)   # counted
    session.commit()

    data = process_leaderboard(session, viewer_discord_id=None, top_n=10)
    assert data.drafter_count == 2


def test_drafter_count_excludes_inactive_players(session):
    s = _seed_set(session)
    a = _seed_player(session, "Alice", "1", "a", active=True)
    b = _seed_player(session, "Bob", "2", "b", active=False)
    _seed_stats(session, a, s, trophies=1, events=2)
    _seed_stats(session, b, s, trophies=2, events=5)
    session.commit()

    data = process_leaderboard(session, viewer_discord_id=None, top_n=10)
    assert data.drafter_count == 1


# ---------------------------------------------------------------------------
# historical set override + embed link
# ---------------------------------------------------------------------------


def test_process_leaderboard_renders_non_active_set_via_override(session):
    active = _seed_set(session, code=active_set_code())
    stx = _seed_set(session, code="STX")
    alice = _seed_player(session, "Alice", "1", "a")
    _seed_stats(session, alice, stx, trophies=3, events=5)
    bob = _seed_player(session, "Bob", "2", "b")
    _seed_stats(session, bob, active, trophies=2, events=4)
    session.commit()

    default = process_leaderboard(session, viewer_discord_id=None)
    assert default.set_code == active_set_code()

    data = process_leaderboard(session, viewer_discord_id=None, magic_set=stx)
    assert data.set_code == "STX"
    assert [e.display_name for e in data.top] == ["Alice"]


def test_embed_link_strips_path_and_points_at_set_for_historical():
    entry = LeaderboardEntry(rank=1, player_id="p", slug="alice-1", display_name="Alice", score=42.0, trophies=3)
    data = LeaderboardData(set_code="STX", set_name="STX", top=[entry], viewer=None)
    embed = render_public_embed(data)
    host = settings.public_site_url.split("://", 1)[-1].rstrip("/")
    assert f"[{host}]" in embed.description
    assert f"[{host}/leaderboard]" not in embed.description
    assert embed.url.endswith("/STX")


def test_embed_link_active_set_has_no_set_path():
    active = active_set_code()
    entry = LeaderboardEntry(rank=1, player_id="p", slug="alice-1", display_name="Alice", score=42.0, trophies=3)
    data = LeaderboardData(set_code=active, set_name=active, top=[entry], viewer=None)
    embed = render_public_embed(data)
    assert not embed.url.rstrip("/").endswith(f"/{active}")


# ---------------------------------------------------------------------------
# personal standings (scope:Me)
# ---------------------------------------------------------------------------


def test_personal_standings_unfiltered_aggregates_all_formats(session):
    s = _seed_set(session)
    alice = _seed_player(session, "Alice", "1", "a")
    _seed_stats(session, alice, s, trophies=2, events=4, fmt="PremierDraft")
    _seed_stats(session, alice, s, trophies=1, events=2, fmt="QuickDraft")
    session.commit()

    data = process_personal_standings(session, "1")
    assert data.format_label is None
    assert len(data.rows) == 1
    assert (data.rows[0].events, data.rows[0].trophies) == (6, 3)


def test_personal_standings_format_filter_scopes_to_group(session):
    s = _seed_set(session)
    alice = _seed_player(session, "Alice", "1", "a")
    _seed_stats(session, alice, s, trophies=2, events=4, fmt="PremierDraft")
    _seed_stats(session, alice, s, trophies=1, events=2, fmt="QuickDraft")
    session.commit()

    data = process_personal_standings(session, "1", format_label="Premier")
    assert data.format_label == "Premier"
    assert len(data.rows) == 1
    assert (data.rows[0].events, data.rows[0].trophies) == (4, 2)


def test_personal_standings_format_rank_uses_format_board(session):
    s = _seed_set(session)
    alice = _seed_player(session, "Alice", "1", "a")
    bob = _seed_player(session, "Bob", "2", "b")
    _seed_stats(session, alice, s, trophies=2, events=3, fmt="PremierDraft")
    _seed_stats(session, bob, s, trophies=5, events=6, fmt="PremierDraft")
    session.commit()

    data = process_personal_standings(session, "1", format_label="Premier")
    assert data.rows[0].rank == 2


def test_personal_standings_format_excludes_sets_without_group_events(session):
    s = _seed_set(session)
    alice = _seed_player(session, "Alice", "1", "a")
    _seed_stats(session, alice, s, trophies=1, events=2, fmt="QuickDraft")
    session.commit()

    data = process_personal_standings(session, "1", format_label="Premier")
    assert data.rows == []


def _seed_lcq_stats(session, alice, bob, s):
    _seed_stats(session, alice, s, trophies=1, events=1, fmt="LimitedChampionshipQualifier_Draft1")
    _seed_stats(session, alice, s, events=1, fmt="LimitedChampionshipQualifier_Draft2", wins=4, losses=2)
    _seed_stats(session, bob, s, events=1, fmt="LimitedChampionshipQualifier_Draft2", wins=3, losses=3)
    _seed_stats(session, bob, s, trophies=5, events=5, fmt="PremierDraft")
    session.commit()


def test_format_board_lcq_combines_both_lcq_groups(session):
    s = _seed_set(session)
    alice = _seed_player(session, "Alice", "1", "a")
    bob = _seed_player(session, "Bob", "2", "b")
    _seed_lcq_stats(session, alice, bob, s)

    data = process_leaderboard_for_format(session, viewer_discord_id=None, format_label="LCQ")

    assert [(e.rank, e.display_name) for e in data.top] == [(1, "Alice"), (2, "Bob")]
    # Alice: D1 trophy 1×30×1 shrunk by 1/3 → 10, plus D2 4×(4/6)×10 → 26.67
    assert data.top[0].score == 36.67
    # Bob's Premier trophies stay off the LCQ board: D2 only, 3×(3/6)×10
    assert data.top[1].score == 15.0


def test_lcq_board_carries_d1_trophies_d2_record_and_cash(session):
    s = _seed_set(session)
    alice = _seed_player(session, "Alice", "1", "a")
    bob = _seed_player(session, "Bob", "2", "b")
    _seed_stats(session, alice, s, trophies=1, events=1, fmt="LimitedChampionshipQualifier_Draft1", wins=3, losses=0)
    _seed_stats(session, alice, s, events=2, fmt="LimitedChampionshipQualifier_Draft2", wins=11, losses=3)
    _seed_stats(session, bob, s, events=1, fmt="LimitedChampionshipQualifier_Draft2", wins=3, losses=2)
    _seed_draft(session, alice, s, "LimitedChampionshipQualifier_Draft1", "WU", "a1", trophy=True, wins=3, losses=0)
    _seed_draft(session, alice, s, "LimitedChampionshipQualifier_Draft2", "WU", "a2", wins=6, losses=1)
    _seed_draft(session, alice, s, "LimitedChampionshipQualifier_Draft2", "UG", "a3", wins=5, losses=2)
    _seed_draft(session, bob, s, "LimitedChampionshipQualifier_Draft2", "BR", "b1", wins=3, losses=2)
    session.commit()

    data = process_leaderboard_for_lcq(session, viewer_discord_id=None)

    assert [e.display_name for e in data.top] == ["Alice", "Bob"]
    assert data.top[0].lcq == LcqExtras(d1_trophies=1, d2_wins=11, d2_losses=3, cash=3000)
    assert data.top[1].lcq == LcqExtras(d1_trophies=0, d2_wins=3, d2_losses=2, cash=0)


def test_lcq_board_renders_d2_and_cash_columns(session):
    s = _seed_set(session)
    alice = _seed_player(session, "Alice", "1", "a")
    _seed_stats(session, alice, s, trophies=1, events=1, fmt="LimitedChampionshipQualifier_Draft1", wins=3, losses=0)
    _seed_draft(session, alice, s, "LimitedChampionshipQualifier_Draft1", "WU", "a1", trophy=True, wins=3, losses=0)
    _seed_draft(session, alice, s, "LimitedChampionshipQualifier_Draft2", "WU", "a2", wins=6, losses=1)
    session.commit()

    data, suffix = render_filtered_data(session, filter_type="format", filter_value="LCQ", viewer_discord_id=None)
    desc = render_public_embed(data).description or ""

    assert suffix == "LCQ"
    header = desc.split("\n", 1)[0]
    assert "Day2" in header and "💰" in header
    assert "6-1" in desc and "2K" in desc


def test_personal_standings_lcq_filter_scopes_and_ranks(session):
    s = _seed_set(session)
    alice = _seed_player(session, "Alice", "1", "a")
    bob = _seed_player(session, "Bob", "2", "b")
    _seed_lcq_stats(session, alice, bob, s)

    data = process_personal_standings(session, "2", format_label="LCQ")

    assert data.format_label == "LCQ"
    assert len(data.rows) == 1
    assert (data.rows[0].score, data.rows[0].rank, data.rows[0].events) == (15.0, 2, 1)


def _seed_direct(session, p, s, wins, losses, finished, eid):
    session.add(DraftEvent(
        player_id=p.id, set_id=s.id, seventeenlands_event_id=eid,
        format="ArenaDirect_Sealed", expansion=s.code,
        wins=wins, losses=losses, is_trophy=wins == 7,
        finished_at=finished,
    ))


def test_personal_standings_direct_aggregates_boxes_and_ranks(session):
    # 2026-05-10 sits outside the SOS collector-booster window, so the standard
    # 7-win=2-box / 6-win=1-box rule applies.
    s = _seed_set(session)
    alice = _seed_player(session, "Alice", "1", "a")
    bob = _seed_player(session, "Bob", "2", "b")
    _seed_direct(session, alice, s, 7, 2, datetime(2026, 5, 10), "a1")  # 2 boxes, trophy
    _seed_direct(session, alice, s, 6, 3, datetime(2026, 5, 10), "a2")  # 1 box
    _seed_direct(session, bob, s, 7, 1, datetime(2026, 5, 10), "b1")    # 2 boxes
    session.commit()

    data = process_personal_standings(session, "1", format_label="Direct")
    assert data.format_label == "Direct"
    assert len(data.rows) == 1
    row = data.rows[0]
    assert (row.score, row.trophies, row.events) == (3.0, 1, 2)  # 3 boxes
    assert (row.wins, row.losses) == (13, 5)
    assert row.rank == 1  # 3 boxes ahead of Bob's 2


def test_personal_standings_direct_collector_window_restricts_boxes(session):
    # Inside the SOS collector-booster window only a 7-win trophy pays (1 box).
    s = _seed_set(session)
    alice = _seed_player(session, "Alice", "1", "a")
    _seed_direct(session, alice, s, 7, 1, datetime(2026, 5, 1), "a1")  # trophy → 1 box
    _seed_direct(session, alice, s, 6, 3, datetime(2026, 5, 1), "a2")  # no box
    session.commit()

    data = process_personal_standings(session, "1", format_label="Direct")
    assert data.rows[0].score == 1.0


def test_stats_aggregates_direct_boxes(session):
    s = _seed_set(session)
    alice = _seed_player(session, "Alice", "1", "a")
    _seed_direct(session, alice, s, 7, 2, datetime(2026, 5, 10), "a1")
    _seed_direct(session, alice, s, 6, 3, datetime(2026, 5, 10), "a2")
    session.commit()

    data = process_stats(session, player_name=None, viewer_discord_id="1", set_code="SOS")
    assert data.direct_stats == {"events": 2, "wins": 13, "losses": 5, "boxes": 3}


def _personal(rows=None, opted_out=False, format_label=None):
    return PersonalStandingsData(
        player_name="Alice", player_slug="alice",
        rows=rows if rows is not None else [
            PersonalStanding(set_code="SOS", score=42.0, trophies=3, events=5, wins=21, losses=4, rank=1),
        ],
        opted_out=opted_out, format_label=format_label,
    )


def test_personal_embed_omits_winrate_when_unfiltered():
    desc = render_personal_embed(_personal()).description or ""
    assert "Win%" not in desc


def test_personal_embed_shows_winrate_when_format_filtered():
    desc = render_personal_embed(_personal(format_label="Premier")).description or ""
    assert "Win%" in desc
    assert "84%" in desc  # 21 wins / 25 games


def test_personal_embed_title_appends_format_suffix():
    embed = render_personal_embed(_personal(format_label="Premier"))
    assert embed.title.endswith("· Premier")


def test_personal_embed_title_plain_without_filter():
    embed = render_personal_embed(_personal())
    assert "·" not in embed.title


def test_personal_embed_direct_uses_boxes_column_not_points():
    rows = [PersonalStanding(set_code="SOS", score=4.0, trophies=2, events=6, wins=38, losses=12, rank=1)]
    desc = render_personal_embed(_personal(rows=rows, format_label="Direct")).description or ""
    assert "📦" in desc
    assert "Pts" not in desc
    assert "Win%" in desc


def _seed_draft(session, p, s, fmt, colors, eid, trophy=False, wins=None, losses=2):
    session.add(DraftEvent(
        player_id=p.id, set_id=s.id, seventeenlands_event_id=eid,
        format=fmt, expansion=s.code, colors=colors,
        wins=(7 if trophy else 3) if wins is None else wins, losses=losses, is_trophy=trophy,
        finished_at=datetime(2026, 5, 10),
    ))


def test_encode_decode_filter_roundtrip():
    assert encode_filter(None, None) == (None, None)
    assert encode_filter("Premier", None) == ("format", "Premier")
    assert encode_filter(None, "WU") == ("color", "WU")
    assert encode_filter("Premier", "WU") == ("format+color", "Premier|WU")
    # Pod/Direct are standalone boards — color is dropped
    assert encode_filter("Pod", "WU") == ("format", "Pod")
    assert encode_filter("Direct", "UG") == ("format", "Direct")
    assert decode_filter("format+color", "Premier|WU") == ("Premier", "WU")
    assert decode_filter("format", "Premier") == ("Premier", None)
    assert decode_filter("color", "WU") == (None, "WU")
    assert decode_filter(None, None) == (None, None)


def test_archetype_board_combines_format_and_color(session):
    from bot.scoring import DEFAULT_QUEUE_GROUPS
    s = _seed_set(session)
    alice = _seed_player(session, "Alice", "1", "a")
    bob = _seed_player(session, "Bob", "2", "b")
    _seed_draft(session, alice, s, "PremierDraft", "UG", "a1", trophy=True)
    _seed_draft(session, alice, s, "PremierDraft", "UGbr", "a2", trophy=True)  # 2 main + 2 splash → still Simic
    _seed_draft(session, alice, s, "QuickDraft", "UG", "a3", trophy=True)      # Simic but wrong format
    _seed_draft(session, bob, s, "PremierDraft", "WU", "b1", trophy=True)      # Premier but wrong color
    session.commit()

    premier = next(g for g in DEFAULT_QUEUE_GROUPS if g.label == "Premier")
    combined = process_leaderboard_for_archetype(session, viewer_discord_id=None, archetype="UG", groups=(premier,))
    assert [(e.display_name, e.trophies) for e in combined.top] == [("Alice", 2)]  # a1 + a2, Quick excluded

    color_only = process_leaderboard_for_archetype(session, viewer_discord_id=None, archetype="UG")
    assert [(e.display_name, e.trophies) for e in color_only.top] == [("Alice", 3)]  # all Simic across formats


def test_personal_standings_resolves_named_player(session):
    s = _seed_set(session)
    _seed_player(session, "Alice", "1", "a")
    bob = _seed_player(session, "Bob", "2", "b")
    _seed_stats(session, bob, s, trophies=4, events=5)
    session.commit()
    # caller is Alice but player_name=Bob → Bob's lifetime standings
    data = process_personal_standings(session, "1", player_name="Bob")
    assert data.player_name == "Bob"
    assert data.rows[0].trophies == 4
    assert process_personal_standings(session, "1", player_name="Nobody") is None


def test_drafter_count_narrows_by_filter(session):
    from bot.commands.leaderboard import _drafter_count
    s = _seed_set(session)
    a = _seed_player(session, "Alice", "1", "a")
    b = _seed_player(session, "Bob", "2", "b")
    _seed_stats(session, a, s, trophies=1, events=2, fmt="PremierDraft")
    _seed_stats(session, b, s, trophies=1, events=2, fmt="QuickDraft")
    _seed_draft(session, a, s, "PremierDraft", "UG", "a1", trophy=True)  # Simic in Premier
    _seed_draft(session, b, s, "QuickDraft", "WU", "b1", trophy=True)    # Azorius in Quick
    session.commit()
    assert _drafter_count(session, s) == 2
    assert _drafter_count(session, s, format_value="Premier") == 1
    assert _drafter_count(session, s, color_value="UG") == 1
    assert _drafter_count(session, s, format_value="Premier", color_value="UG") == 1
    assert _drafter_count(session, s, format_value="Quick", color_value="UG") == 0


def _seed_pod_event(session, set_code, name):
    event = PodDraftEvent(
        event_date=date(2026, 5, 1), event_time=datetime(2026, 5, 1, tzinfo=timezone.utc),
        set_code=set_code, name=name, draftmancer_session=f"{name}-sess",
        discord_thread_id=f"{name}-thread", socket_status="complete",
    )
    session.add(event)
    session.flush()
    return event


def test_peasant_board_filters_to_peasant_pods(session):
    _seed_set(session)
    alice = _seed_player(session, "Alice", "1", "a")
    bob = _seed_player(session, "Bob", "2", "b")
    peasant = _seed_pod_event(session, "PEASANT", "Peasant Cube Draft 1")
    sos_pod = _seed_pod_event(session, "SOS", "SOS Pod 1")
    session.add(PodDraftParticipant(
        event_id=peasant.id, player_id=alice.id, display_name="Alice", placement=1, record="3-0",
    ))
    session.add(PodDraftParticipant(
        event_id=sos_pod.id, player_id=bob.id, display_name="Bob", placement=1, record="3-0",
    ))
    session.commit()

    data = process_leaderboard_for_peasant(session, viewer_discord_id=None)

    assert data.set_code == "PEASANT"
    assert data.show_score is False
    assert [(e.slug, e.trophies, e.events) for e in data.top] == [(alice.slug, 1, 1)]


@pytest.mark.parametrize(
    "colors, is_cube, expected",
    [
        ("WUbr", False, True),
        ("WUBR", False, True),
        ("WUB", False, False),
        ("WUBr", False, True),
        ("WUbr", True, False),
        ("WUBr", True, True),
        ("WUBR", True, True),
        ("WUB", True, False),
        ("WUBRg", True, True),
        ("", True, False),
        (None, True, False),
    ],
)
def test_is_soup_cube_requires_three_base_colors(colors, is_cube, expected):
    assert _is_soup(colors, is_cube) is expected
