"""Pod-draft format registry + Draftmancer emit-branch tests."""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone

from bot.models import PodDraftEvent
from bot.services import pod_format
from bot.services.pod_format import PEASANT_CODE, PEASANT_CUBE_ID, PEASANT_LABEL
from bot.services.pod_draft_manager import PodDraftManager, _persist_format, set_event_format
from bot.services.pod_drafts import renamed_for_format, update_event_format


def test_cube_id_for_registered_cube():
    assert pod_format.cube_id_for(PEASANT_CODE) == PEASANT_CUBE_ID
    assert pod_format.cube_id_for(PEASANT_CODE.lower()) == PEASANT_CUBE_ID


def test_cube_id_for_plain_set_is_none():
    assert pod_format.cube_id_for("SOS") is None


def test_label_for_cube_vs_set():
    assert pod_format.label_for(PEASANT_CODE) == PEASANT_LABEL
    assert pod_format.label_for("SOS") is None


def test_format_applied_message_uses_label_then_code():
    assert PEASANT_LABEL in pod_format.format_applied_message(PEASANT_CODE)
    assert "SOS" in pod_format.format_applied_message("SOS")


class _FakeSio:
    """Captures emitted events; invokes ack callbacks with a success payload."""

    def __init__(self):
        self.connected = True
        self.calls: list[tuple[str, tuple]] = []

    async def emit(self, event, *args, callback=None):
        self.calls.append((event, args))
        if callback is not None:
            callback({})

    def events(self):
        return [name for name, _ in self.calls]


def _manager(set_code: str) -> PodDraftManager:
    mgr = PodDraftManager(object(), "evt", "sid", 123, set_code, 8)
    mgr.sio = _FakeSio()
    return mgr


def test_emit_format_loads_cube_for_registered_code():
    mgr = _manager(PEASANT_CODE)
    asyncio.run(mgr._emit_session_settings())
    expected_import = ("importCube", ({"service": "Cube Cobra", "cubeID": PEASANT_CUBE_ID, "matchVersions": True},))
    assert expected_import in mgr.sio.calls
    assert "setRestriction" not in mgr.sio.events()
    assert ("setUseCustomCardList", (False,)) not in mgr.sio.calls


def test_emit_format_restricts_to_set_for_plain_code():
    mgr = _manager("SOS")
    asyncio.run(mgr._emit_session_settings())
    assert ("setRestriction", (["sos"],)) in mgr.sio.calls
    assert "importCube" not in mgr.sio.events()


def test_emit_format_unloads_cube_before_restricting_to_set():
    mgr = _manager(PEASANT_CODE)
    asyncio.run(mgr._emit_format())

    mgr.set_code = "SOS"
    asyncio.run(mgr._emit_format())

    events = mgr.sio.events()
    assert events.index("setUseCustomCardList") < events.index("setRestriction")


# --- name swap on format change ---

def test_renamed_for_format_swaps_token_and_renumbers():
    assert renamed_for_format("MSH Pod Draft #14 - Jul 14", "MSH", "SOS", 6) == "SOS Pod Draft #6 - Jul 14"


def test_renamed_for_format_uppercases_new_token():
    assert renamed_for_format("MSH Pod Draft #1", "msh", "sos", 3) == "SOS Pod Draft #3"


def test_renamed_for_format_leaves_untokenized_name_untouched():
    assert renamed_for_format("Friday Night Pod", "MSH", "SOS", 9) == "Friday Night Pod"


def test_renamed_for_format_swaps_scheduled_card_name_to_cube():
    assert renamed_for_format("MSH Jul 18 Early Pod", "MSH", PEASANT_CODE, 1) == "Peasant Cube Jul 18 Early Pod"


# --- persistence + pre-draft guard ---

def _seed_event(session, socket_status="reminded", set_code="SOS", name="SOS Pod Draft"):
    event = PodDraftEvent(
        event_date=date(2026, 5, 13),
        event_time=datetime(2026, 5, 13, tzinfo=timezone.utc),
        set_code=set_code,
        name=name,
        draftmancer_session="LLU-SOS-1",
        discord_thread_id="thread-1",
        socket_status=socket_status,
    )
    session.add(event)
    session.flush()
    return event


def test_update_event_format_repoints_set_code(session):
    event = _seed_event(session)

    new_name = update_event_format(session, event.id, PEASANT_CODE)

    assert event.set_code == PEASANT_CODE
    assert event.format_label == PEASANT_LABEL
    assert new_name == "Peasant Cube Pod Draft"
    assert event.name == "Peasant Cube Pod Draft"


def test_update_event_format_renumbers_against_target_set(session):
    _seed_event(session, set_code="SOS", name="SOS Pod Draft #1 - May 1")
    _seed_event(session, set_code="SOS", name="SOS Pod Draft #2 - May 8")
    event = _seed_event(session, set_code="MSH", name="MSH Pod Draft #14 - Jul 1")

    new_name = update_event_format(session, event.id, "SOS")

    assert new_name == "SOS Pod Draft #3 - Jul 1"


def test_update_event_format_blocked_once_finalized(session):
    event = _seed_event(session, socket_status="complete")
    assert update_event_format(session, event.id, PEASANT_CODE) is None
    session.refresh(event)
    assert event.set_code == "SOS"


def test_persist_format_commits(session, monkeypatch):
    import bot.services.pod_draft_manager as mod
    event = _seed_event(session)
    monkeypatch.setattr(mod, "SessionLocal", _session_factory(session))
    assert _persist_format(event.id, PEASANT_CODE) == "Peasant Cube Pod Draft"
    assert session.get(PodDraftEvent, event.id).set_code == PEASANT_CODE


def test_set_event_format_rejects_finalized_event(session, monkeypatch):
    import bot.services.pod_draft_manager as mod
    event = _seed_event(session, socket_status="draft_done")
    monkeypatch.setattr(mod, "SessionLocal", _session_factory(session))
    err = asyncio.run(set_event_format(None, event.id, PEASANT_CODE))
    assert err == pod_format.FORMAT_LOCKED_MSG


def _session_factory(session):
    class _Ctx:
        def __enter__(self):
            return session

        def __exit__(self, *exc):
            return False

    return lambda: _Ctx()


# --- seat indexes ---

def test_persist_seat_indexes_from_log_writes_table_order(session, monkeypatch):
    import bot.services.pod_draft_manager as mod
    from sqlalchemy import select
    from bot.models import PodDraftParticipant
    from bot.services.pod_drafts import seed_event_participants

    event = _seed_event(session)
    seed_event_participants(session, event.id, ["Aria", "Bryn", "Caedmon", "Doryn"])
    session.flush()
    monkeypatch.setattr(mod, "SessionLocal", _session_factory(session))

    mgr = _manager("SOS")
    mgr.event_id = event.id
    mgr.draft_logs = {"Aria": {"users": {
        "0": {"userName": "Caedmon"}, "1": {"userName": "Aria"},
        "2": {"userName": "Doryn"}, "3": {"userName": "Bryn"},
    }}}

    assert mgr.persist_seat_indexes_from_log() is True
    seats = {
        p.draftmancer_name: p.seat_index
        for p in session.execute(select(PodDraftParticipant)).scalars()
    }
    assert seats == {"Caedmon": 0, "Aria": 1, "Doryn": 2, "Bryn": 3}


def test_persist_seat_indexes_from_log_noop_without_log(session, monkeypatch):
    import bot.services.pod_draft_manager as mod
    monkeypatch.setattr(mod, "SessionLocal", _session_factory(session))
    mgr = _manager("SOS")
    mgr.draft_logs = {}
    assert mgr.persist_seat_indexes_from_log() is False
