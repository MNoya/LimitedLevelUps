from datetime import datetime, timezone

import pytest

from bot.models import PodDraftMatch, PodDraftParticipant
from bot.services import pod_swiss
from bot.services import pod_tournament
from bot.services.pod_drafts import add_pairing, record_ondemand_event
from bot.services.pod_tournament import (
    BYE_SCORE,
    apply_drop,
    insert_pending_matches,
    load_dropped_names,
)

HALL = ["Finkel", "LSV", "Reid", "Nassif", "Chapin", "Budde", "Kibler", "Juza"]


def _session_factory(session):
    class _Ctx:
        def __enter__(self):
            return session

        def __exit__(self, *exc):
            return False

    return lambda: _Ctx()


@pytest.fixture(autouse=True)
def bound_session(session, monkeypatch):
    monkeypatch.setattr(pod_tournament, "SessionLocal", _session_factory(session))


def _event(session):
    event = record_ondemand_event(
        session, set_code="SOS",
        event_time=datetime(2026, 5, 13, tzinfo=timezone.utc),
        name="SOS Pod Draft", discord_thread_id="thread-drop",
    )
    for i, name in enumerate(HALL):
        session.add(PodDraftParticipant(
            event_id=event.id, display_name=name, draftmancer_name=name, seat_index=i,
        ))
    session.flush()
    return event


def test_drop_forfeits_the_open_match_to_a_bye(session):
    event = _event(session)
    for idx, (a, b) in enumerate([("Finkel", "LSV"), ("Reid", "Nassif")]):
        add_pairing(session, event.id, 1, a, b, pairing_index=idx)
    session.commit()

    forfeited = apply_drop(event.id, "LSV", 1)

    rows = {(m.player_a_name, m.player_b_name): m for m in session.query(PodDraftMatch).all()}
    bye = rows[("Finkel", "LSV")]
    assert len(forfeited) == 1
    assert (bye.winner_name, bye.score) == ("Finkel", BYE_SCORE)
    assert rows[("Reid", "Nassif")].winner_name is None
    assert load_dropped_names(event.id) == {"lsv"}


def test_a_later_pairing_into_the_dropped_player_is_reported_on_creation(session):
    event = _event(session)
    add_pairing(session, event.id, 1, "Finkel", "LSV", pairing_index=0)
    session.commit()
    apply_drop(event.id, "LSV", 1)

    rows = insert_pending_matches(event.id, 2, [("LSV", "Reid"), ("Finkel", "Nassif")])

    by_id = {m.id: m for m in session.query(PodDraftMatch).filter_by(round=2).all()}
    forfeit = by_id[rows[0][0]]
    assert (forfeit.winner_name, forfeit.score) == ("Reid", BYE_SCORE)
    assert by_id[rows[1][0]].winner_name is None


def test_a_dropped_player_keeps_only_the_matches_they_played(session):
    matches = [
        pod_swiss.MatchOutcome(1, "LSV", "Finkel", "LSV", "2-1"),
        pod_swiss.MatchOutcome(2, "Reid", "LSV", "Reid", BYE_SCORE),
        pod_swiss.MatchOutcome(3, "Nassif", "LSV", "Nassif", BYE_SCORE),
    ]

    assert pod_swiss.played_record("LSV", matches) == (1, 0)
    assert pod_swiss.played_record("Reid", matches) == (1, 0)


def test_a_bye_dm_reads_from_each_side_of_the_match():
    forfeit = {
        "a_name": "LSV", "b_name": "Finkel", "a_display": "LSV", "b_display": "Finkel",
        "winner_name": "Finkel", "score": BYE_SCORE,
    }

    def body(viewer_is_a: bool) -> str:
        return pod_tournament.build_pairing_dm_embed(
            round_num=2, opponent_label="x", opponent_arena=None, pairings_url=None,
            match_state=forfeit, viewer_is_a=viewer_is_a,
        ).description

    assert body(viewer_is_a=True) != body(viewer_is_a=False)
