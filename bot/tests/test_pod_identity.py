"""Tests for pod-draft player identity matching and arena-name format validation."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from bot.models import Player
from bot.services.pod_draft_manager import _find_guild_member_for_arena
from bot.services.pod_drafts import (
    attach_arena_alias,
    has_arena_suffix,
    levenshtein,
    lobby_match_status,
    normalize_player_name,
    player_for_name,
    player_arena_handle,
    classify_lobby_names,
    strip_arena_suffix,
    suggest_lobby_name,
)

_ARENA_INPUT_RE = re.compile(r"^.+#\d+$")


def _seed_player(
    session,
    *,
    discord_id,
    username,
    display_name,
    arena_name=None,
    arena_aliases=None,
    active=True,
):
    if arena_aliases is None:
        arena_aliases = [normalize_player_name(arena_name)] if arena_name else []
    p = Player(
        slug=f"{username}-{discord_id}",
        discord_id=discord_id,
        discord_username=username,
        display_name=display_name,
        arena_name=arena_name,
        arena_aliases=arena_aliases,
        active=active,
    )
    session.add(p)
    session.flush()
    return p


# --- normalize_player_name ---

def test_normalize_strips_arena_suffix():
    assert normalize_player_name("Noya#12345") == "noya"


def test_normalize_lowercases_bare_name():
    assert normalize_player_name("MartinTheGreat") == "martinthegreat"


def test_normalize_hash_with_no_digits_is_not_stripped():
    # a bare trailing `#` is not an Arena suffix, so the hash stays
    assert normalize_player_name("Name#") == "name#"
    assert normalize_player_name("Name#abc") == "name#abc"


def test_normalize_strips_question_mark_placeholder_suffix():
    assert normalize_player_name("WonderAlice#?????") == "wonderalice"


def test_normalize_strips_only_trailing_suffix():
    assert normalize_player_name("Na#12me#99") == "na#12me"


def test_normalize_empty_string():
    assert normalize_player_name("") == ""


# --- strip_arena_suffix / has_arena_suffix ---

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Alice#48087", "Alice"),
        ("Alias#13488 (Bob)", "Alias (Bob)"),
        ("Marlo#?????", "Marlo"),
        ("driftwood60", "driftwood60"),
        ("Plain Name", "Plain Name"),
        ("#12345", "#12345"),
    ],
)
def test_strip_arena_suffix_preserves_case_and_nickname(raw, expected):
    assert strip_arena_suffix(raw) == expected


@pytest.mark.parametrize(
    "raw, present",
    [
        ("Alice#48087", True),
        ("Alias#13488 (Bob)", True),
        ("Marlo#?????", True),
        ("driftwood60", False),
        ("Name#abc", False),
    ],
)
def test_has_arena_suffix(raw, present):
    assert has_arena_suffix(raw) is present


# --- player_for_name priority ---

def test_player_arena_handle_returns_full_handle(session):
    _seed_player(session, discord_id="10", username="dana", display_name="Dana", arena_name="Dana#4242")

    assert player_arena_handle(session, "10") == "Dana#4242"


def test_player_arena_handle_none_when_unset_or_partial(session):
    _seed_player(session, discord_id="11", username="evan", display_name="Evan", arena_name=None)
    _seed_player(session, discord_id="12", username="finn", display_name="Finn", arena_name="Finn")

    assert player_arena_handle(session, "11") is None
    assert player_arena_handle(session, "12") is None


def test_player_arena_handle_none_for_unknown_discord_id(session):
    assert player_arena_handle(session, "does-not-exist") is None


def test_exact_arena_name_wins_over_display_name(session):
    _seed_player(session, discord_id="1", username="alice", display_name="Alice", arena_name="MagicAlice#9999")
    _seed_player(session, discord_id="2", username="magicalice", display_name="MagicAlice")

    # "MagicAlice#9999" matches player 1's arena_name exactly (lower), not player 2's display_name
    found = player_for_name(session, "MagicAlice#9999")
    assert found is not None
    assert found.discord_id == "1"


def test_arena_name_match_is_case_insensitive(session):
    _seed_player(session, discord_id="3", username="bob", display_name="Bob", arena_name="Bob#5678")

    assert player_for_name(session, "bob#5678") is not None
    assert player_for_name(session, "BOB#5678") is not None


def test_falls_back_to_normalized_display_name(session):
    _seed_player(session, discord_id="4", username="charlie", display_name="Charlie")

    found = player_for_name(session, "Charlie#0001")
    assert found is not None
    assert found.discord_id == "4"


def test_falls_back_to_normalized_discord_username(session):
    # display_name doesn't match but discord_username does after normalization
    _seed_player(session, discord_id="5", username="nightowl", display_name="NightOwl2025")

    found = player_for_name(session, "nightowl#777")
    assert found is not None
    assert found.discord_id == "5"


def test_returns_none_when_no_match(session):
    _seed_player(session, discord_id="6", username="dave", display_name="Dave")
    assert player_for_name(session, "ghost#1234") is None


def test_matches_inactive_player_as_fallback(session):
    _seed_player(session, discord_id="7", username="retired", display_name="Retired",
                 arena_name="retired#4242", active=False)

    found = player_for_name(session, "retired#4242")

    assert found is not None
    assert found.discord_id == "7"


def test_active_player_wins_over_inactive_sharing_handle(session):
    _seed_player(session, discord_id="70", username="oldowner", display_name="Old Owner",
                 arena_name="sharedhandle#111", active=False)
    _seed_player(session, discord_id="71", username="newowner", display_name="New Owner",
                 arena_name="sharedhandle#222", active=True)

    found = player_for_name(session, "sharedhandle#333")

    assert found is not None
    assert found.discord_id == "71"


def test_display_name_wins_over_discord_username_when_both_match(session):
    # Two players: one whose display_name normalizes to "ace", one whose username is "ace"
    _seed_player(session, discord_id="8", username="notace", display_name="Ace")
    _seed_player(session, discord_id="9", username="ace", display_name="Somebody Else")

    found = player_for_name(session, "Ace#1111")
    # display_name leg fires before discord_username leg; p_display should win
    assert found is not None
    assert found.discord_id == "8"


def test_fuzzy_resolves_off_by_one_alias_typo(session):
    _seed_player(session, discord_id="20", username="vortex", display_name="Vortex", arena_name="Vortexia0#48954")

    found = player_for_name(session, "Vortexia#48954")
    assert found is not None
    assert found.discord_id == "20"


def test_fuzzy_skips_when_two_players_are_equally_close(session):
    _seed_player(session, discord_id="21", username="a", display_name="A", arena_name="questor#1")
    _seed_player(session, discord_id="22", username="b", display_name="B", arena_name="questar#2")

    assert player_for_name(session, "questir#9") is None


def test_fuzzy_ignores_short_aliases(session):
    _seed_player(session, discord_id="23", username="newt", display_name="Newt", arena_name="newt#1")

    assert player_for_name(session, "bolt#2") is None


# --- attach_arena_alias ---

def test_attach_creates_player_for_new_discord_id(session):
    player_id = attach_arena_alias(
        session, discord_id="30", discord_username="newbie", display_name="Newbie",
        avatar_hash=None, arena_name="Vortexia#48954",
    )

    created = session.execute(select(Player).where(Player.discord_id == "30")).scalar_one()
    assert created.id == player_id
    assert "vortexia" in created.arena_aliases


def test_attach_relinking_own_handle_keeps_it(session):
    _seed_player(session, discord_id="31", username="owner", display_name="Owner", arena_name="Vortexia#1")

    attach_arena_alias(
        session, discord_id="31", discord_username="owner", display_name="Owner",
        avatar_hash=None, arena_name="Vortexia#999",
    )

    owner = session.execute(select(Player).where(Player.discord_id == "31")).scalar_one()
    assert owner.arena_aliases == ["vortexia"]
    assert owner.arena_name == "Vortexia#1"


def test_attach_takes_a_shared_handle_from_its_previous_holder(session):
    owner = _seed_player(session, discord_id="32", username="owner", display_name="Owner", arena_name="Vortexia#1")

    borrower_id = attach_arena_alias(
        session, discord_id="33", discord_username="borrower", display_name="Borrower",
        avatar_hash=None, arena_name="Vortexia#999",
    )

    assert player_for_name(session, "Vortexia#999").id == borrower_id
    assert owner.arena_aliases == []
    assert owner.arena_name is None


def test_a_released_handle_leaves_the_prior_holders_row_intact(session):
    owner = _seed_player(
        session, discord_id="34", username="owner", display_name="Owner",
        arena_name="Vortexia#1", arena_aliases=["vortexia", "othername"],
    )

    attach_arena_alias(
        session, discord_id="35", discord_username="borrower", display_name="Borrower",
        avatar_hash=None, arena_name="Vortexia#999",
    )

    assert owner.arena_aliases == ["othername"]
    assert owner.active is True


def test_attach_dedupes_alias_and_keeps_existing_arena_name(session):
    _seed_player(
        session, discord_id="36", username="dev", display_name="Dev",
        arena_name="Primary#1", arena_aliases=["primary"],
    )

    attach_arena_alias(
        session, discord_id="36", discord_username="dev", display_name="Dev",
        avatar_hash=None, arena_name="Primary#2",
    )

    player = session.execute(select(Player).where(Player.discord_id == "36")).scalar_one()
    assert player.arena_aliases == ["primary"]
    assert player.arena_name == "Primary#1"


@pytest.mark.parametrize(
    ("stored", "candidate", "overwrite", "expected"),
    [
        ("Moth", "MothQueen#11111", False, "MothQueen#11111"),
        ("Moth", "DreamShard#68947", True, "DreamShard#68947"),
        ("Moth", "Wanderer", False, "Moth"),
        ("MothQueen#11111", "DreamShard#68947", False, "MothQueen#11111"),
        ("MothQueen#11111", "DreamShard#68947", True, "DreamShard#68947"),
        (None, "Wanderer", False, None),
        (None, "MothQueen#11111", False, "MothQueen#11111"),
    ],
)
def test_attach_arena_name_adoption(session, stored, candidate, overwrite, expected):
    _seed_player(session, discord_id="40", username="moth", display_name="Moth", arena_name=stored)

    attach_arena_alias(
        session, discord_id="40", discord_username="moth", display_name="Moth",
        avatar_hash=None, arena_name=candidate, overwrite=overwrite,
    )

    player = session.execute(select(Player).where(Player.discord_id == "40")).scalar_one()
    assert player.arena_name == expected
    assert normalize_player_name(candidate) in player.arena_aliases


def test_attach_creates_player_without_arena_name_for_bare_nickname(session):
    attach_arena_alias(
        session, discord_id="41", discord_username="wand", display_name="Wanderer",
        avatar_hash=None, arena_name="Wanderer",
    )

    created = session.execute(select(Player).where(Player.discord_id == "41")).scalar_one()
    assert created.arena_name is None
    assert "wanderer" in created.arena_aliases


# --- classify_lobby_names ---

def test_classify_returns_display_name_for_recognized_names(session):
    _seed_player(session, discord_id="10", username="known", display_name="Known")

    classified, _ = classify_lobby_names(session, ["Known", "Unknown#9999"])

    result = dict(classified)
    assert result["Known"] == "Known"
    assert result["Unknown#9999"] is None


def test_classify_resolves_name_with_arena_suffix_via_display_name(session):
    _seed_player(session, discord_id="11", username="noya", display_name="Noya")

    classified, _ = classify_lobby_names(session, ["Noya#12345"])

    assert dict(classified)["Noya#12345"] == "Noya"


def test_classify_resolves_via_stored_arena_name(session):
    _seed_player(
        session, discord_id="12", username="martin", display_name="Noya",
        arena_name="MartinTheGreat#5432",
    )

    classified, _ = classify_lobby_names(session, ["MartinTheGreat#5432", "Noya#0001"])

    result = dict(classified)
    assert result["MartinTheGreat#5432"] == "Noya"
    assert result["Noya#0001"] == "Noya"


def test_classify_empty_list(session):
    assert classify_lobby_names(session, []) == ([], frozenset())


def test_classify_preserves_order(session):
    _seed_player(session, discord_id="13", username="one", display_name="One")
    _seed_player(session, discord_id="14", username="three", display_name="Three")

    names = ["One", "Two#0", "Three", "Four#0"]
    classified, _ = classify_lobby_names(session, names)

    assert [n for n, _ in classified] == names
    assert [dn for _, dn in classified] == ["One", None, "Three", None]


def test_classify_marks_a_player_with_no_finished_pod_and_leaves_a_veteran_plain(session):
    _seed_player(session, discord_id="15", username="rookie", display_name="Rookie")
    veteran = _seed_player(session, discord_id="16", username="finkel", display_name="Jon Finkel")
    veteran.first_pod_at = datetime(2026, 8, 1, tzinfo=timezone.utc)
    session.flush()

    _, new_drafters = classify_lobby_names(session, ["Rookie", "Jon Finkel"])

    assert new_drafters == frozenset({"Rookie"})


# --- lobby did-you-mean fuzzy suggestion ---

@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("abc", "abc", 0),
        ("abc", "abd", 1),
        ("abc", "ab", 1),
        ("stylish", "sytlish", 2),
    ],
)
def test_levenshtein_distance(a, b, expected):
    assert levenshtein(a, b) == expected


def test_suggest_catches_transposition():
    live = ["Stylish Greninja#01952", "Baneless#56063"]
    assert suggest_lobby_name("Sytlish Greninja#01952", live) == "Stylish Greninja#01952"


def test_suggest_returns_none_when_nothing_close():
    assert suggest_lobby_name("Totally Different#1", ["Baneless#56063"]) is None


def test_suggest_ignores_short_names():
    assert suggest_lobby_name("ab#1", ["abz#2"]) is None


def test_suggest_picks_closest_of_several():
    live = ["Zephyrus#1", "Vortexia#2", "Baneless#3"]
    assert suggest_lobby_name("Vortexib#9", live) == "Vortexia#2"


# --- lobby_match_status ---

def test_lobby_match_status_matched_when_seat_resolves(session, monkeypatch):
    monkeypatch.setattr("bot.services.pod_drafts.SessionLocal", _session_factory(session))
    player = _seed_player(
        session, discord_id="50", username="greninja", display_name="Sage Mode Greninja",
        arena_name="Stylish Greninja#01952",
    )

    matched, suggestion = lobby_match_status(
        "Stylish Greninja#01952", player.id, ["Stylish Greninja#01952", "Baneless#1"],
    )

    assert matched is True
    assert suggestion is None


def test_lobby_match_status_unmatched_returns_suggestion(session, monkeypatch):
    monkeypatch.setattr("bot.services.pod_drafts.SessionLocal", _session_factory(session))
    player = _seed_player(
        session, discord_id="51", username="greninja", display_name="Sage Mode Greninja",
        arena_name="Sytlish Greninja#01952",
    )

    matched, suggestion = lobby_match_status(
        "Sytlish Greninja#01952", player.id, ["Stylish Greninja#01952", "Baneless#1"],
    )

    assert matched is False
    assert suggestion == "Stylish Greninja#01952"


def _session_factory(session):
    class _Ctx:
        def __enter__(self):
            return session

        def __exit__(self, *exc):
            return False

    return lambda: _Ctx()


# --- /link-arena input format (regex) ---

def test_valid_arena_handle_accepted():
    assert _ARENA_INPUT_RE.match("Noya#12345")
    assert _ARENA_INPUT_RE.match("Mr Fancy#1")
    assert _ARENA_INPUT_RE.match("a#0")


def test_bare_name_without_hash_rejected():
    assert not _ARENA_INPUT_RE.match("NoHashAtAll")


def test_hash_without_digits_rejected():
    assert not _ARENA_INPUT_RE.match("Name#")


def test_hash_with_non_digit_suffix_rejected():
    assert not _ARENA_INPUT_RE.match("Name#abc")


def test_empty_string_rejected():
    assert not _ARENA_INPUT_RE.match("")


# --- multi-account alias matching ---

def test_alias_exact_match_resolves_to_owner(session):
    _seed_player(
        session, discord_id="10", username="flutterdev", display_name="flutterdev",
        arena_name="fullerene60#49190",
        arena_aliases=["fullerene60", "edvor"],
    )
    assert player_for_name(session, "fullerene60#49190").discord_id == "10"
    assert player_for_name(session, "edvor#11111").discord_id == "10"


def test_alias_match_independent_of_primary_arena_name(session):
    _seed_player(
        session, discord_id="11", username="dev2", display_name="Dev Two",
        arena_name="primaryhandle#10000",
        arena_aliases=["primaryhandle", "secondhandle"],
    )
    assert player_for_name(session, "secondhandle#22222").discord_id == "11"


def test_longest_alias_prefix_wins(session):
    _seed_player(
        session, discord_id="12", username="a", display_name="A",
        arena_aliases=["drag"],
    )
    _seed_player(
        session, discord_id="13", username="b", display_name="B",
        arena_aliases=["dragonslayer"],
    )
    assert player_for_name(session, "dragonslayer99#1234").discord_id == "13"
    assert player_for_name(session, "dragfoo#9999").discord_id == "12"


def test_alias_no_match_falls_back_to_display_name(session):
    _seed_player(
        session, discord_id="14", username="zoinks", display_name="zoinks",
        arena_name=None,
    )
    assert player_for_name(session, "zoinks#42").discord_id == "14"


# --- token-in-display-name matching (tier 4) ---

def test_token_match_in_display_name(session):
    _seed_player(session, discord_id="20", username="zorn", display_name="Zorn (Kael)")
    assert player_for_name(session, "Kael#12345").discord_id == "20"


def test_token_match_does_not_fire_for_short_norm(session):
    _seed_player(session, discord_id="21", username="xy", display_name="XY (ab)")
    assert player_for_name(session, "ab#1") is None


def test_token_match_with_placeholder_suffix(session):
    _seed_player(session, discord_id="22", username="zorn", display_name="Zorn (Kael)")
    assert player_for_name(session, "kael#?????").discord_id == "22"


# --- guild-member fallback for players without a row ---

def _stub_guild(*members):
    return SimpleNamespace(members=[SimpleNamespace(display_name=dn, name=un) for dn, un in members])


def test_guild_member_exact_display_name_match():
    guild = _stub_guild(("MNG", "mng_discord"))
    found = _find_guild_member_for_arena(guild, "MNG#61656")
    assert found is not None
    assert found.display_name == "MNG"


def test_guild_member_token_match_in_parenthesized_nick():
    guild = _stub_guild(("Zorn (Kael)", "zorn_kael"))
    found = _find_guild_member_for_arena(guild, "kael#?????")
    assert found is not None
    assert found.display_name == "Zorn (Kael)"


def test_guild_member_exact_match_wins_over_token_match():
    guild = _stub_guild(("Zorn (Kael)", "zorn_kael"), ("Kael", "kael_discord"))
    found = _find_guild_member_for_arena(guild, "Kael#12345")
    assert found.display_name == "Kael"


def test_guild_member_no_match_returns_none():
    guild = _stub_guild(("Somebody", "somebody"))
    assert _find_guild_member_for_arena(guild, "ghost#1234") is None


def test_exact_display_name_beats_token_match(session):
    exact = _seed_player(session, discord_id="22", username="u22", display_name="Kael")
    _seed_player(session, discord_id="23", username="u23", display_name="Zorn (Kael)")
    assert player_for_name(session, "Kael#12345").discord_id == exact.discord_id
