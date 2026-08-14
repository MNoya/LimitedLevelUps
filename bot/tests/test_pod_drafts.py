import re
from datetime import date, datetime, time, timedelta, timezone

import pytest
from sqlalchemy import select

from bot.config import settings
from bot.models import MagicSet, Player, PodDraftEvent, PodDraftParticipant
from bot.scripts.draftmancer_log import build_compact, simulate
from bot.services.pod_drafts import (
    FinalStanding,
    active_event_for_discord_user_in_dm,
    capture_deck_screenshot,
    declined_pod_roles,
    dm_draft_link_enabled,
    draftmancer_url_for,
    finalize_champion,
    get_participant_deck_state,
    is_championship,
    list_champions,
    participant_dm_info,
    player_for_name,
    pod_summary_by_set_for_player,
    record_match,
    record_ondemand_event,
    seed_event_participants,
    set_dm_draft_link,
    set_pod_roles_declined,
    set_participant_deck_colors,
    upsert_participant,
)
from bot.services.pod_schedule import SCHEDULE_TZ


_SESSION_RE = re.compile(r"^(?P<base>.+)-(?P<suffix>[a-z]{4})$")


def _session_base(session_id: str) -> str:
    """The readable base of a Draftmancer session id, asserting the unguessable 4-letter random tail."""
    match = _SESSION_RE.match(session_id)
    assert match is not None, f"{session_id!r} lacks a 4-letter suffix"
    return match["base"]


def _seed_set(session, code="SOS"):
    s = MagicSet(code=code, name=f"{code} long name", start_date=date(2026, 4, 1))
    session.add(s)
    session.flush()
    return s


def _seed_player(session, discord_id="111", username="alice", display_name="Alice"):
    p = Player(
        slug=f"{username}-{discord_id}",
        discord_id=discord_id,
        discord_username=username,
        display_name=display_name,
        seventeenlands_token="t" * 32,
        active=True,
    )
    session.add(p)
    session.flush()
    return p


def _make_event(session, set_code="SOS", event_date=date(2026, 5, 13),
                attendees=("Alice", "Bob", "Carl"), name=None):
    """Create a bot-native pod event plus its roster, linking each name to a Player when one matches —
    the shared factory the pod-draft tests build on."""
    event_time = datetime.combine(event_date, time(14, 0), tzinfo=SCHEDULE_TZ)
    event = record_ondemand_event(
        session, set_code=set_code, event_time=event_time,
        name=name or f"{set_code} Pod Draft — {event_date:%b %d}",
        discord_thread_id=f"thread-{event_date.isoformat()}",
    )
    for attendee in attendees:
        player = player_for_name(session, attendee)
        session.add(PodDraftParticipant(
            event_id=event.id, display_name=attendee, player_id=player.id if player else None,
        ))
    session.flush()
    return event


def test_record_event_persists_and_links_known_attendees(session, monkeypatch):
    monkeypatch.setattr(settings, "pod_draft_session_prefix", "LLU")
    _seed_set(session, "SOS")
    _seed_player(session, discord_id="111", username="alice", display_name="Alice")

    event = _make_event(session, attendees=("Alice", "Stranger"))

    assert event.socket_status == "pending"
    assert _session_base(event.draftmancer_session) == "LLU-May-13"
    assert event.set_id is not None

    participants = session.execute(
        select(PodDraftParticipant).where(PodDraftParticipant.event_id == event.id)
    ).scalars().all()
    by_name = {p.display_name: p for p in participants}
    assert by_name["Alice"].player_id is not None
    assert by_name["Stranger"].player_id is None


def test_record_event_same_day_pods_share_base_but_get_distinct_sessions(session, monkeypatch):
    monkeypatch.setattr(settings, "pod_draft_session_prefix", "LLU")
    _seed_set(session)
    e1 = _make_event(session, attendees=())
    e2 = _make_event(session, attendees=())
    e3 = _make_event(session, attendees=())
    sessions = [e1.draftmancer_session, e2.draftmancer_session, e3.draftmancer_session]
    assert [_session_base(s) for s in sessions] == ["LLU-May-13"] * 3
    assert len(set(sessions)) == 3


def test_is_championship_detects_name_case_insensitively():
    assert is_championship("SOS Dischord Community Championship Pod Draft")
    assert is_championship("set CHAMPIONSHIP")

    assert not is_championship("SOS Pod Draft #14")
    assert not is_championship("")
    assert not is_championship(None)


def test_record_ondemand_event_closes_decklist_only_for_championship_name(session):
    _seed_set(session)
    champ = _make_event(session, attendees=(), name="SOS Community Championship Pod Draft")
    normal = _make_event(session, attendees=(), name="SOS Pod Draft #14")

    assert champ.closed_decklist is True
    assert normal.closed_decklist is False


def test_record_event_with_no_matching_set_leaves_set_id_null(session):
    event = _make_event(session, set_code="CUBE")
    assert event.set_id is None
    assert event.set_code == "CUBE"


def test_upsert_participant_matches_existing_by_display_name(session):
    _seed_set(session)
    event = _make_event(session, attendees=("Alice",))

    p = upsert_participant(session, event.id, display_name="alice", draftmancer_name="Alice#1234")

    rows = session.execute(
        select(PodDraftParticipant).where(PodDraftParticipant.event_id == event.id)
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].id == p.id
    assert rows[0].draftmancer_name == "Alice#1234"


def test_upsert_participant_matches_existing_by_draftmancer_name(session):
    _seed_set(session)
    event = _make_event(session, attendees=("Alice",))
    upsert_participant(session, event.id, display_name="Alice", draftmancer_name="A#1")

    again = upsert_participant(session, event.id, display_name="Different", draftmancer_name="a#1")

    rows = session.execute(
        select(PodDraftParticipant).where(PodDraftParticipant.event_id == event.id)
    ).scalars().all()
    assert len(rows) == 1
    assert again.id == rows[0].id


def test_upsert_participant_creates_new_row_when_no_match(session):
    _seed_set(session)
    event = _make_event(session, attendees=("Alice",))
    upsert_participant(session, event.id, display_name="Brand New", draftmancer_name="New#9999")

    rows = session.execute(
        select(PodDraftParticipant).where(PodDraftParticipant.event_id == event.id)
    ).scalars().all()
    assert len(rows) == 2


def test_upsert_participant_backfills_player_id(session):
    _seed_set(session)
    event = _make_event(session, attendees=("Stranger",))
    _seed_player(session, discord_id="222", username="stranger", display_name="Stranger")

    upsert_participant(session, event.id, display_name="Stranger")

    row = session.execute(
        select(PodDraftParticipant).where(PodDraftParticipant.event_id == event.id)
    ).scalar_one()
    assert row.player_id is not None


def test_upsert_participant_adopts_arena_handle_for_player_without_one(session):
    _seed_set(session)
    event = _make_event(session, attendees=("Bigmits",))
    player = _seed_player(session, discord_id="333", username="bigmits", display_name="Bigmits")
    assert player.arena_name is None

    upsert_participant(session, event.id, display_name="Bigmits", draftmancer_name="Bigmits#91757")

    session.refresh(player)
    assert player.arena_name == "Bigmits#91757"
    assert "bigmits" in player.arena_aliases


def test_seed_event_participants_leaves_second_name_unlinked_when_player_already_seated(session):
    _seed_set(session)
    event = _make_event(session, attendees=())
    player = _seed_player(session, discord_id="555", username="noya", display_name="Noya")
    player.arena_aliases = ["noya"]
    session.flush()

    seed_event_participants(session, event.id, ["Noya#08011", "Noya2#08011"])

    rows = session.execute(
        select(PodDraftParticipant).where(PodDraftParticipant.event_id == event.id)
    ).scalars().all()
    linked = [row for row in rows if row.player_id == player.id]
    assert len(rows) == 2
    assert len(linked) == 1


def test_record_match_is_idempotent(session):
    _seed_set(session)
    event = _make_event(session)

    first = record_match(session, event.id, 1, "Alice", "Bob", winner_name="Alice", score="2-1")
    again = record_match(session, event.id, 1, "Alice", "Bob", winner_name="Alice", score="2-0")

    assert first.id == again.id
    assert again.score == "2-0"


def test_finalize_champion_writes_standings_and_marks_complete(session):
    _seed_set(session)
    event = _make_event(session, attendees=("Alice", "Bob", "Carl"))

    standings = [
        FinalStanding(draftmancer_name="Alice", placement=1, record="3-0", eliminated_round=None),
        FinalStanding(draftmancer_name="Bob", placement=2, record="2-1", eliminated_round=3),
        FinalStanding(draftmancer_name="Carl", placement=3, record="1-2", eliminated_round=3),
    ]
    updated = finalize_champion(session, event.id, standings)

    assert updated.socket_status == "complete"
    rows = session.execute(
        select(PodDraftParticipant).where(PodDraftParticipant.event_id == event.id)
    ).scalars().all()
    by_name = {p.display_name: p for p in rows}
    assert by_name["Alice"].placement == 1
    assert by_name["Alice"].record == "3-0"
    assert by_name["Alice"].eliminated_round is None
    assert by_name["Bob"].placement == 2
    assert by_name["Bob"].eliminated_round == 3


def test_finalize_champion_stamps_finalized_at_and_preserves_it_on_rerun(session):
    _seed_set(session)
    event = _make_event(session, attendees=("Alice", "Bob"))
    standings = [
        FinalStanding(draftmancer_name="Alice", placement=1, record="3-0", eliminated_round=None),
        FinalStanding(draftmancer_name="Bob", placement=2, record="2-1", eliminated_round=3),
    ]
    first = finalize_champion(session, event.id, standings)
    assert first.finalized_at is not None
    stamped = first.finalized_at

    again = finalize_champion(session, event.id, standings)
    assert again.finalized_at == stamped


def _seed_linked_event(session, *, discord_id, thread_id, event_time, name="Pod Draft"):
    event = record_ondemand_event(
        session, set_code="SOS", event_time=event_time, name=name, discord_thread_id=thread_id,
    )
    player = player_for_name(session, "Alice")
    session.add(PodDraftParticipant(
        event_id=event.id, display_name="Alice", player_id=player.id if player else None,
    ))
    session.flush()
    return event


def test_active_event_resolver_returns_finalized_pod(session):
    """Regression: a player submitting deck colors after finalization must still resolve to the pod."""
    _seed_set(session)
    _seed_player(session, discord_id="42", username="alice", display_name="Alice")
    now = datetime.now(timezone.utc)
    event = _seed_linked_event(session, discord_id="42", thread_id="thread-fin", event_time=now)
    finalize_champion(session, event.id, [
        FinalStanding(draftmancer_name="Alice", placement=1, record="3-0", eliminated_round=None),
    ])
    assert event.socket_status == "complete"

    resolved = active_event_for_discord_user_in_dm(session, "42")
    assert resolved == (event.id, "thread-fin")


def test_active_event_resolver_excludes_pods_outside_window(session):
    _seed_set(session)
    _seed_player(session, discord_id="42", username="alice", display_name="Alice")
    old = datetime.now(timezone.utc) - timedelta(hours=25)
    _seed_linked_event(session, discord_id="42", thread_id="thread-old", event_time=old)

    assert active_event_for_discord_user_in_dm(session, "42") is None


def test_active_event_resolver_returns_newest_within_window(session):
    _seed_set(session)
    _seed_player(session, discord_id="42", username="alice", display_name="Alice")
    now = datetime.now(timezone.utc)
    _seed_linked_event(session, discord_id="42", thread_id="thread-older", event_time=now - timedelta(hours=6))
    newer = _seed_linked_event(session, discord_id="42", thread_id="thread-newer", event_time=now - timedelta(hours=1))

    resolved = active_event_for_discord_user_in_dm(session, "42")
    assert resolved == (newer.id, "thread-newer")


def test_list_champions_returns_filtered_and_ordered_by_date(session):
    _seed_set(session, "SOS")
    _seed_set(session, "ECL")
    for set_code, ed in [("SOS", date(2026, 5, 6)), ("SOS", date(2026, 5, 13)), ("ECL", date(2026, 4, 1))]:
        event = _make_event(session, set_code=set_code, event_date=ed, attendees=())
        standing = FinalStanding(
            draftmancer_name=f"Champ-{set_code}-{ed.isoformat()}", placement=1, record="3-0",
            eliminated_round=None,
        )
        finalize_champion(session, event.id, [standing])

    all_rows = list_champions(session)
    assert [r["event_date"] for r in all_rows] == [date(2026, 4, 1), date(2026, 5, 6), date(2026, 5, 13)]

    sos_only = list_champions(session, set_code="sos")
    assert {r["set_code"] for r in sos_only} == {"SOS"}
    assert len(sos_only) == 2


def test_pod_summary_by_set_aggregates_per_set(session):
    _seed_set(session, "SOS")
    _seed_set(session, "ECL")
    player = _seed_player(session, discord_id="777", username="champ", display_name="Champ")

    e1 = _make_event(session, set_code="SOS", event_date=date(2026, 5, 6), attendees=("Champ",))
    finalize_champion(session, e1.id, [
        FinalStanding("Champ", placement=1, record="3-0", eliminated_round=None),
    ])
    e2 = _make_event(session, set_code="ECL", event_date=date(2026, 4, 1), attendees=("Champ",))
    finalize_champion(session, e2.id, [
        FinalStanding("Champ", placement=2, record="2-1", eliminated_round=3),
    ])

    summary = pod_summary_by_set_for_player(session, player.id)
    assert summary["SOS"] == (1, 3, 0, 1, 0, 0)   # events, wins, losses, trophies, two-win, one-win
    assert summary["ECL"] == (1, 2, 1, 0, 1, 0)


def test_pod_summary_trophy_from_pod_win_without_3_0(session):
    _seed_set(session, "SOS")
    player = _seed_player(session, discord_id="778", username="smallpod", display_name="SmallPod")

    event = _make_event(session, set_code="SOS", event_date=date(2026, 5, 6), attendees=("SmallPod",))
    finalize_champion(session, event.id, [
        FinalStanding("SmallPod", placement=1, record="2-1", eliminated_round=None),
    ])

    summary = pod_summary_by_set_for_player(session, player.id)
    assert summary["SOS"].trophies == 1   # 2-1 that won the pod counts as a trophy
    assert summary["SOS"].two_win_finishes == 0   # not also a two-win finish


def test_pod_summary_team_finishes_score_by_record_only(session):
    _seed_set(session, "SOS")
    player = _seed_player(session, discord_id="779", username="teamer", display_name="Teamer")

    e1 = _make_event(session, set_code="SOS", event_date=date(2026, 5, 6), attendees=("Teamer",))
    finalize_champion(session, e1.id, [
        FinalStanding("Teamer", placement=None, record="2-1", eliminated_round=None),
    ])
    e2 = _make_event(session, set_code="SOS", event_date=date(2026, 5, 20), attendees=("Teamer",))
    finalize_champion(session, e2.id, [
        FinalStanding("Teamer", placement=None, record="3-0", eliminated_round=None),
    ])

    summary = pod_summary_by_set_for_player(session, player.id)
    assert summary["SOS"].events == 2      # placement-less finishes still count
    assert summary["SOS"].trophies == 1    # the 3-0, on record alone
    assert summary["SOS"].two_win_finishes == 1    # a 2-1 without placement stays a two-win finish


def test_pod_summary_empty_for_unknown_player(session):
    assert pod_summary_by_set_for_player(session, "ghost") == {}


def test_stats_embed_pod_line_scoped_to_requested_set(session):
    from bot.services.player_stats import process_stats, render_embed

    _seed_set(session, "SOS")
    _seed_set(session, "ECL")
    _seed_player(session, discord_id="777", username="champ", display_name="Champ")
    e = _make_event(session, set_code="SOS", event_date=date(2026, 5, 6), attendees=("Champ",))
    finalize_champion(session, e.id, [FinalStanding("Champ", placement=1, record="3-0", eliminated_round=None)])
    session.commit()

    sos = render_embed(process_stats(session, player_name=None, viewer_discord_id="777", set_code="SOS"))
    assert "**Pod**" in (sos.description or "")

    ecl = render_embed(process_stats(session, player_name=None, viewer_discord_id="777", set_code="ECL"))
    assert "Pod" not in (ecl.description or "")


def _seed_pod_for_deck_color_tests(session, thread_id: str = "thread-42") -> tuple[str, str]:
    _seed_set(session, "SOS")
    player = _seed_player(session, discord_id="42", username="alice", display_name="Alice")
    event = record_ondemand_event(
        session, set_code="SOS", event_time=datetime(2026, 5, 13, 0, 0, tzinfo=timezone.utc),
        name="Pod Draft #1", discord_thread_id=thread_id,
    )
    for attendee in ("Alice", "Bob"):
        p = player_for_name(session, attendee)
        session.add(PodDraftParticipant(
            event_id=event.id, display_name=attendee, player_id=p.id if p else None,
        ))
    session.flush()
    return event.id, player.discord_id


def test_set_participant_deck_colors_saves(session):
    _seed_pod_for_deck_color_tests(session)
    ok = set_participant_deck_colors(session, "thread-42", "42", "WU")
    assert ok is True
    in_pod, color = get_participant_deck_state(session, "thread-42", "42")
    assert in_pod is True
    assert color == "WU"


def test_set_participant_deck_colors_rejects_non_participant(session):
    _seed_pod_for_deck_color_tests(session)
    # discord_id "99" is not on the participant list
    assert set_participant_deck_colors(session, "thread-42", "99", "WB") is False


def test_get_participant_deck_state_signals_not_in_pod(session):
    _seed_pod_for_deck_color_tests(session)
    in_pod, color = get_participant_deck_state(session, "thread-42", "99")
    assert in_pod is False
    assert color is None


def test_participant_dm_info_prefers_server_nickname_and_session_handle(session):
    event_id, _ = _seed_pod_for_deck_color_tests(session)
    participant = session.execute(
        select(PodDraftParticipant)
        .where(PodDraftParticipant.event_id == event_id, PodDraftParticipant.display_name == "Alice")
    ).scalar_one()
    participant.draftmancer_name = "Alice#1234"
    participant.display_name = "Alice#1234"
    player = session.execute(select(Player).where(Player.discord_id == "42")).scalar_one()
    player.display_name = "AliceServerNick"
    player.arena_name = "AliceMain#9999"
    session.flush()

    info = participant_dm_info(session, event_id)

    alice = info["alice"]
    assert alice.discord_id == "42"
    assert alice.display_name == "AliceServerNick"
    assert alice.arena_name == "Alice#1234"


def test_participant_dm_info_strips_arena_suffix_from_unlinked_fallback(session):
    event_id, _ = _seed_pod_for_deck_color_tests(session)
    bob = session.execute(
        select(PodDraftParticipant)
        .where(PodDraftParticipant.event_id == event_id, PodDraftParticipant.display_name == "Bob")
    ).scalar_one()
    bob.player_id = None
    bob.draftmancer_name = "Bob#4242"
    bob.display_name = "Bob#4242"
    session.flush()

    info = participant_dm_info(session, event_id)

    assert info["bob"].discord_id is None
    assert info["bob"].display_name == "Bob"


def test_set_participant_deck_colors_overwrites_on_resubmit(session):
    _seed_pod_for_deck_color_tests(session)
    set_participant_deck_colors(session, "thread-42", "42", "WU")
    set_participant_deck_colors(session, "thread-42", "42", "URg")
    _, color = get_participant_deck_state(session, "thread-42", "42")
    assert color == "URg"


def _draft_log_payload():
    carddata = {
        "a": {"name": "Bolt", "collector_number": "1", "set": "sos", "rarity": "common",
              "colors": ["R"], "cmc": 1, "type": "Instant"},
        "b": {"name": "Bear", "collector_number": "2", "set": "sos", "rarity": "common",
              "colors": ["G"], "cmc": 2, "type": "Creature"},
        "c": {"name": "Forest", "collector_number": "3", "set": "sos", "rarity": "common",
              "colors": [], "cmc": 0, "type": "Land"},
        "d": {"name": "Drake", "collector_number": "4", "set": "sos", "rarity": "uncommon",
              "colors": ["U"], "cmc": 3, "type": "Creature"},
    }
    users = {
        "u1": {"userName": "Alice#1", "picks": [], "decklist": {"main": ["a", "c"], "side": ["b"]}},
        "u2": {"userName": "Bob#2", "picks": []},
    }
    return {
        "sessionID": "S1", "time": "t", "setRestriction": ["SOS"],
        "carddata": carddata, "users": users, "boosters": [["a", "b"], ["c", "d"]],
    }


def test_build_compact_card_table_drops_id_and_carries_cmc_and_type():
    compact = build_compact(_draft_log_payload())

    assert compact["v"] == 2
    first = compact["cards"][0]
    assert "id" not in first
    assert set(first) == {"n", "cn", "s", "r", "c", "cmc", "type"}
    assert (first["cmc"], first["type"]) == (1, "Instant")


def test_build_compact_decks_are_card_indices_aligned_to_seats():
    compact = build_compact(_draft_log_payload())

    assert len(compact["decks"]) == len(compact["seats"])
    assert compact["decks"][0] == {"main": [0, 2], "side": [1]}
    assert compact["decks"][1] == {"main": [], "side": []}


@pytest.mark.parametrize("pick_positions, expected_pp", [([0], 1), ([0, 2], 2)])
def test_build_compact_records_picks_per_turn(pick_positions, expected_pp):
    payload = _draft_log_payload()
    payload["users"]["u1"]["picks"] = [{"packNum": 0, "pickNum": 0, "booster": ["a", "b", "c", "d"],
                                        "pick": pick_positions}]

    compact = build_compact(payload)

    assert compact["pp"] == expected_pp
    assert compact["picks"][0][0] == pick_positions


def test_simulate_takes_both_cards_of_a_pick_2_turn_from_the_same_booster():
    compact = {
        "seats": ["Alice", "Bob"],
        "packs": [[0, 1, 2, 3], [4, 5, 6, 7], [8, 9, 10, 11], [12, 13, 14, 15],
                  [16, 17, 18, 19], [20, 21, 22, 23]],
        "picks": [[[0, 2, 0, 1], [0, 1, 0, 1], [0, 1, 0, 1]],
                  [[1, 3, 0, 1], [0, 1, 0, 1], [0, 1, 0, 1]]],
        "pp": 2,
    }

    out = simulate(compact)

    assert out[0][0] == [0, 2, 4, 6]
    assert out[1][0] == [5, 7, 1, 3]


def test_build_compact_decklist_ids_absent_from_card_table_are_dropped():
    payload = _draft_log_payload()
    payload["users"]["u1"]["decklist"]["main"].append("missing-card")

    compact = build_compact(payload)

    assert compact["decks"][0]["main"] == [0, 2]


def _share_decklist_manager():
    from bot.services.pod_draft_manager import PodDraftManager

    mgr = PodDraftManager(object(), "evt", "sid", 123, "SOS", 8)
    mgr.draft_logs = {"Alice#1": _draft_log_payload()}
    return mgr


def test_share_decklist_patches_seat_in_memory():
    import asyncio

    mgr = _share_decklist_manager()

    asyncio.run(mgr._on_share_decklist({"userID": "u2", "decklist": {"main": ["d"], "side": []}}))

    assert mgr.draft_logs["Alice#1"]["users"]["u2"]["decklist"] == {"main": ["d"], "side": []}


def test_share_decklist_ignored_for_mock_hashes_only_and_unknown_seat():
    import asyncio

    for kind, payload in [
        ("mock", {"userID": "u1", "decklist": {"main": ["a"], "side": []}}),
        ("tournament", {"userID": "u1", "decklist": {"hashes": {"main": 42}}}),
        ("tournament", {"userID": "ghost", "decklist": {"main": ["a"], "side": []}}),
    ]:
        mgr = _share_decklist_manager()
        mgr.kind = kind
        original = mgr.draft_logs["Alice#1"]["users"]["u1"]["decklist"].copy()

        asyncio.run(mgr._on_share_decklist(payload))

        assert mgr.draft_logs["Alice#1"]["users"]["u1"]["decklist"] == original


def test_persist_decklists_from_log_writes_when_log_present_else_skips():
    mgr = _share_decklist_manager()
    persisted: list[dict] = []
    mgr._persist_draft_log_gz = lambda payload: persisted.append(payload)

    assert mgr.persist_decklists_from_log() is True
    assert len(persisted) == 1

    mgr.draft_logs = {}
    assert mgr.persist_decklists_from_log() is False
    assert len(persisted) == 1


def test_persist_round_entry_artifacts_dispatches_seats_then_decklists_by_round():
    import asyncio

    from bot.services.pod_tournament import persist_round_entry_artifacts

    class _StubManager:
        def __init__(self):
            self.calls = []

        def persist_seat_indexes_from_log(self):
            self.calls.append("seats")

        def persist_decklists_from_log(self):
            self.calls.append("decks")

    round1, round2, round3 = _StubManager(), _StubManager(), _StubManager()

    asyncio.run(persist_round_entry_artifacts(round1, 1))
    asyncio.run(persist_round_entry_artifacts(round2, 2))
    asyncio.run(persist_round_entry_artifacts(round3, 3))

    assert round1.calls == ["seats"]
    assert round2.calls == ["decks"]
    assert round3.calls == []


@pytest.mark.parametrize(
    "current_round, championship_posted, existing_url, existing_caption, new_caption, captured",
    [
        (None, False, None, None, None, False),
        (1, False, None, None, None, False),
        (2, False, "https://cdn.test/old.png", None, None, False),
        (3, False, None, None, None, True),
        (3, False, "https://cdn.test/old.png", None, None, True),
        (3, False, "https://cdn.test/old.png", "3-0 trophy", None, False),
        (3, False, "https://cdn.test/old.png", "3-0 trophy", "went 2-1 actually", True),
        (3, True, "https://cdn.test/old.png", None, None, False),
        (3, True, "https://cdn.test/old.png", None, "3-0", True),
        (3, True, None, None, None, True),
    ],
    ids=[
        "before-pairings", "round-1-ignored", "round-2-ignored",
        "first-capture", "last-wins", "record-locks-slot", "record-replaces-record",
        "post-championship-ignored", "post-championship-record-overrides", "post-championship-fills-missing",
    ],
)
def test_capture_deck_screenshot_gating(
    session, current_round, championship_posted, existing_url, existing_caption, new_caption, captured,
):
    player = _seed_player(session, discord_id="901", username="cap", display_name="Cap")
    event = PodDraftEvent(
        event_date=date(2026, 6, 3), event_time=datetime(2026, 6, 3, tzinfo=timezone.utc),
        set_code="SOS", name="SOS Pod Capture", draftmancer_session="cap-sess",
        discord_thread_id="cap-thread", socket_status="complete",
        current_round=current_round,
        championship_posted_at=datetime(2026, 6, 3, 23, tzinfo=timezone.utc) if championship_posted else None,
    )
    session.add(event)
    session.flush()
    session.add(PodDraftParticipant(
        event_id=event.id, player_id=player.id, display_name="Cap",
        deck_screenshot_url=existing_url, deck_screenshot_caption=existing_caption,
    ))
    session.flush()

    result = capture_deck_screenshot(session, "cap-thread", "901", "https://cdn.test/new.png", new_caption)

    stored = session.execute(
        select(PodDraftParticipant).where(PodDraftParticipant.event_id == event.id)
    ).scalar_one()
    if captured:
        assert result == event.id
        assert stored.deck_screenshot_url == "https://cdn.test/new.png"
        assert stored.deck_screenshot_caption == new_caption
    else:
        assert result is None
        assert stored.deck_screenshot_url == existing_url


def test_draftmancer_url_for_base_has_no_username():
    url = draftmancer_url_for("LLU-SOS-1")

    assert url == f"{settings.draftmancer_web_url}/?session=LLU-SOS-1"
    assert "userName" not in url


@pytest.mark.parametrize("user_name", [None, ""])
def test_draftmancer_url_for_blank_username_returns_base(user_name):
    assert draftmancer_url_for("LLU-SOS-1", user_name) == draftmancer_url_for("LLU-SOS-1")


def test_draftmancer_url_for_encodes_arena_handle():
    url = draftmancer_url_for("LLU-SOS-1", "Tarmogoyf#99921")

    assert url == f"{settings.draftmancer_web_url}/?session=LLU-SOS-1&userName=Tarmogoyf%2399921"


def test_dm_draft_link_enabled_defaults_true_for_unknown(session):
    assert dm_draft_link_enabled(session, "999") is True


def test_set_dm_draft_link_creates_lightweight_row(session):
    set_dm_draft_link(
        session, discord_id="42", discord_username="ann", display_name="Ann",
        avatar_hash=None, enabled=False,
    )

    assert dm_draft_link_enabled(session, "42") is False
    player = session.execute(select(Player).where(Player.discord_id == "42")).scalar_one()
    assert player.arena_name is None
    assert player.leaderboard_opt_in is False


def test_set_dm_draft_link_updates_existing_row(session):
    _seed_player(session, discord_id="7", username="bo", display_name="Bo")

    set_dm_draft_link(
        session, discord_id="7", discord_username="bo", display_name="Bo",
        avatar_hash=None, enabled=False,
    )

    assert dm_draft_link_enabled(session, "7") is False


def test_declined_pod_roles_is_empty_for_a_player_with_no_row(session):
    assert declined_pod_roles(session, "999") == set()


def test_declining_a_role_creates_a_lightweight_row_and_sticks(session):
    set_pod_roles_declined(
        session, discord_id="42", discord_username="ann", display_name="Ann",
        avatar_hash=None, keys=["early"], declined=True,
    )

    assert declined_pod_roles(session, "42") == {"early"}
    player = session.execute(select(Player).where(Player.discord_id == "42")).scalar_one()
    assert player.leaderboard_opt_in is False


def test_declines_accumulate_and_clear_one_role_at_a_time(session):
    _seed_player(session, discord_id="7", username="bo", display_name="Bo")
    choice = dict(discord_id="7", discord_username="bo", display_name="Bo", avatar_hash=None)

    set_pod_roles_declined(session, **choice, keys=["early"], declined=True)
    set_pod_roles_declined(session, **choice, keys=["wknd_late"], declined=True)
    set_pod_roles_declined(session, **choice, keys=["early"], declined=False)

    assert declined_pod_roles(session, "7") == {"wknd_late"}


def test_declining_a_role_twice_stores_it_once(session):
    _seed_player(session, discord_id="7", username="bo", display_name="Bo")
    choice = dict(discord_id="7", discord_username="bo", display_name="Bo", avatar_hash=None)

    set_pod_roles_declined(session, **choice, keys=["late"], declined=True)
    set_pod_roles_declined(session, **choice, keys=["late"], declined=True)

    player = session.execute(select(Player).where(Player.discord_id == "7")).scalar_one()
    assert player.declined_pod_roles == ["late"]
