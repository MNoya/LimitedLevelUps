import asyncio
from datetime import date

from bot.models import MagicSet, Player, PlayerStats
from bot.services.player_stats import leaderboard_seat_order, seated_ring_order
from bot.services.pod_draft_manager import PodDraftManager
from bot.services.pod_seating_select import parse_seat_reorder

ORDER = ["alice#1", "bob#2", "carol#3", "dave#4"]
LABELS = ["Alice", "Bob", "Carol", "Dave"]


def test_reorder_by_names_only():
    reordered, err = parse_seat_reorder("Carol\nAlice\nDave\nBob", ORDER, LABELS)
    assert err is None
    assert reordered == ["carol#3", "alice#1", "dave#4", "bob#2"]


def test_ignores_stray_leading_numbers():
    reordered, err = parse_seat_reorder("#3 Carol\n1- Alice\n4) Dave\n2. Bob", ORDER, LABELS)
    assert err is None
    assert reordered == ["carol#3", "alice#1", "dave#4", "bob#2"]


def test_rejects_invalid_order():
    reordered, _ = parse_seat_reorder("Alice\nBob\nCarol\nEve", ORDER, LABELS)
    assert reordered is None


def test_seated_ring_order_eight_player_layout():
    # Names rank-ordered best first; expected ring matches the spec table:
    # Seat 0..7 -> #1 #2 #4 #3 #8 #7 #5 #6
    ranked = ["r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8"]
    assert seated_ring_order(ranked) == ["r1", "r2", "r4", "r3", "r8", "r7", "r5", "r6"]


def test_seated_ring_order_non_eight_has_no_swap():
    # Six players: top half in order, bottom half reversed, no 3<->4 / 5<->6 swap
    ranked = ["r1", "r2", "r3", "r4", "r5", "r6"]
    assert seated_ring_order(ranked) == ["r1", "r2", "r3", "r6", "r5", "r4"]


def test_seating_lobby_order_returns_name_display_pairs(session):
    mgr = PodDraftManager(object(), "evt", "sid", 123, "SOS", 8)
    mgr.session_users = [
        {"userID": "1", "userName": "Ava"},
        {"userID": "2", "userName": "Bram"},
    ]

    order = asyncio.run(mgr.seating_lobby_order())

    assert order == [("Ava", "Ava"), ("Bram", "Bram")]


def _seed_set(session, code="SOS"):
    s = MagicSet(code=code, name=code, start_date=date(2026, 4, 21))
    session.add(s)
    session.flush()
    return s


def _seed_player(session, name, discord_id, token_suffix, leaderboard_opt_in=True):
    p = Player(
        slug=f"{name.lower()}-{discord_id}",
        discord_id=discord_id,
        discord_username=name.lower(),
        display_name=name,
        seventeenlands_token=(token_suffix * 32)[:32],
        active=True,
        leaderboard_opt_in=leaderboard_opt_in,
    )
    session.add(p)
    session.flush()
    return p


def _seed_stats(session, p, s, trophies, events):
    session.add(PlayerStats(
        player_id=p.id, set_id=s.id, format="PremierDraft", expansion=s.code,
        events=events, wins=trophies * 7, losses=max(0, events - trophies),
        games_played=events * 5, trophies=trophies,
    ))


def test_leaderboard_seat_order_ranks_present_users_unranked_to_bottom(session):
    s = _seed_set(session)
    alice = _seed_player(session, "Alice", "1", "a")
    bob = _seed_player(session, "Bob", "2", "b")
    _seed_player(session, "Carol", "3", "c", leaderboard_opt_in=False)
    _seed_stats(session, alice, s, trophies=2, events=4)
    _seed_stats(session, bob, s, trophies=5, events=8)  # Bob outscores Alice -> rank 1
    session.commit()

    # Four-player lobby: Bob (1), Alice (2), Carol (unranked, opted out), Ghost (no Player row)
    order = leaderboard_seat_order(session, ["Alice", "Bob", "Carol", "Ghost"])

    # Rank order best->worst is [Bob, Alice, Carol, Ghost]; ring = top-in-order + bottom-reversed
    assert order == ["Bob", "Alice", "Ghost", "Carol"]


def test_leaderboard_seat_order_unmatched_names_sort_to_bottom_by_name(session):
    _seed_set(session)
    session.commit()
    # Nobody is on the board, so all four are unranked and fall back to name order
    order = leaderboard_seat_order(session, ["Delta", "Alpha", "Charlie", "Bravo"])
    # Rank-ordered names (all unranked) = alphabetical; then ring top/reversed
    assert order == ["Alpha", "Bravo", "Delta", "Charlie"]
