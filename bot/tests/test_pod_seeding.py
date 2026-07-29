from datetime import date

import pytest

from bot.commands.pod_draft import CHAMPIONSHIP_CUT, _build_seeding_embed, _seating_pool
from bot.services.seeding_table import seeding_block
from bot.models import MagicSet, Player, PlayerStats
from bot.services.player_stats import SeededAttendee, seed_attendees


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


def test_seed_attendees_orders_ranked_by_standing_unranked_at_bottom(session):
    s = _seed_set(session)
    alice = _seed_player(session, "Alice", "1", "a")
    bob = _seed_player(session, "Bob", "2", "b")
    carol = _seed_player(session, "Carol", "3", "c", leaderboard_opt_in=False)
    _seed_stats(session, alice, s, trophies=2, events=4)
    _seed_stats(session, bob, s, trophies=5, events=8)
    _seed_stats(session, carol, s, trophies=9, events=9)
    session.commit()

    seeded = seed_attendees(session, [
        "Alice",    # ranked
        "Bob",      # ranked higher
        "Carol",    # opted out -> unranked despite trophies
        "Ghost",    # no Player row -> unranked, raw sesh name
    ])

    assert [(a.display_name, a.rank) for a in seeded] == [
        ("Bob", 1),
        ("Alice", 2),
        ("Carol", None),
        ("Ghost", None),
    ]
    assert seeded[2].score is None and seeded[2].trophies is None


def test_seed_attendees_uses_canonical_player_name(session):
    s = _seed_set(session)
    alice = _seed_player(session, "Alice", "1", "a")
    _seed_stats(session, alice, s, trophies=1, events=3)
    session.commit()

    # sesh lists the lowercase username; the embed name resolves to the player's display name
    seeded = seed_attendees(session, ["alice"])
    assert seeded[0].display_name == "Alice"
    assert seeded[0].rank == 1


def _attendee(name, rank=None, score=None, trophies=None, slug=None):
    return SeededAttendee(slug=slug, display_name=name, rank=rank, score=score, trophies=trophies)


def _is_divider(line):
    return "─" in line and set(line) <= {"`", "─"}


def test_seeding_block_draws_cut_after_eighth_when_over_eight():
    attendees = [_attendee(f"P{i}", rank=i, score=100 - i, trophies=0) for i in range(1, 11)]
    block = seeding_block(attendees, seats=list(range(1, 11)), cut_after=8)
    lines = block.splitlines()

    divider_idx = next(i for i, line in enumerate(lines) if _is_divider(line))
    # header + 8 rows precede the divider; row 9 follows it
    assert "8." in lines[divider_idx - 1]
    assert "9." in lines[divider_idx + 1]


def test_seeding_block_no_divider_when_eight_or_fewer():
    attendees = [_attendee(f"P{i}", rank=i, score=100 - i, trophies=0) for i in range(1, 6)]
    block = seeding_block(attendees, seats=list(range(1, 6)), cut_after=None)
    assert not any(_is_divider(line) for line in block.splitlines())


def test_seeding_block_shows_rnk_and_links_ranked_players():
    block = seeding_block([_attendee("Alice", rank=4, score=50, trophies=1, slug="alice-1")], seats=[1])
    assert "#4" in block
    assert "/player/alice-1" in block


def test_seeding_block_unranked_renders_dash_and_no_link():
    block = seeding_block([_attendee("Ghost")])
    assert "—" in block
    assert "/player/" not in block


def test_build_seeding_embed_includes_both_sections():
    yes = [_attendee("Alice", rank=1, score=50, trophies=1, slug="alice-1")]
    maybe = [_attendee("Bob", rank=2, score=20, trophies=0, slug="bob-2")]
    embed = _build_seeding_embed(yes, maybe, seat_cap=CHAMPIONSHIP_CUT)
    assert "✅" in embed.description
    assert "🤷" in embed.description
    assert embed.description.count("(1)") == 2


_FILLERS = ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"]


@pytest.mark.parametrize(
    "locked, locked_keys, yes, expected_pool, expected_overflow",
    [
        ([], set(), ["Ava", "Bram"], ["Ava", "Bram"], []),
        ([], set(), _FILLERS + ["R9", "R10"], _FILLERS, ["R9", "R10"]),
        (["Ava", "Bram"], {"ava", "bram", "ava#123"}, ["Ava#123", "Cara"], ["Ava", "Bram", "Cara"], []),
        (["Ava"], {"ava"}, _FILLERS, ["Ava"] + _FILLERS[:7], _FILLERS[7:]),
        (_FILLERS, {n.casefold() for n in _FILLERS}, ["Ava", "Bram"], _FILLERS, ["Ava", "Bram"]),
        ([], set(), ["Ava", "ava", "Bram"], ["Ava", "Bram"], []),
    ],
    ids=["rsvps-only", "rsvp-overflow", "locked-deduped-by-arena", "locked-plus-fillers", "full-table-all-overflow",
         "duplicate-rsvp-dropped"],
)
def test_seating_pool_locks_session_players_first(locked, locked_keys, yes, expected_pool, expected_overflow):
    pool, overflow = _seating_pool(locked, locked_keys, yes)

    assert pool == expected_pool
    assert overflow == expected_overflow
