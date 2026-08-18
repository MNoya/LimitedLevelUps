import asyncio
import re
from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from bot.commands.pod_draft import build_pod_settings_view
from bot.config import settings
from bot.models import MagicSet, Player, PodDraftEvent, PodDraftParticipant
from bot.services.pod_drafts import (
    build_mock_session,
    capture_deck_screenshot,
    finalize_mock_event,
    record_mock_event,
    reroll_session_suffix,
)
from bot.services.pod_format_select import format_options
from bot.sets import (
    active_set_code,
    is_known_set,
    preview_set_code,
    recent_released_sets,
    upcoming_sets,
)


MOCK_SESSION_RE = re.compile(r"LLU-([A-Z]+)-Mock-(\d+)-[a-z]{4}")


class _StubBot:
    """Enough bot for the Settings panel: it resolves the pod's thread as the notice channel."""

    def get_channel(self, channel_id: int) -> object:
        return object()


def _session_factory(session):
    class _Ctx:
        def __enter__(self):
            return session

        def __exit__(self, *exc):
            return False

    return lambda: _Ctx()


def _seed_player(session, discord_id="901", username="cap", display_name="Cap"):
    player = Player(
        slug=f"{username}-{discord_id}",
        discord_id=discord_id,
        discord_username=username,
        display_name=display_name,
        seventeenlands_token="t" * 32,
        active=True,
    )
    session.add(player)
    session.flush()
    return player


def test_upcoming_sets_and_known_set():
    before_msh_rotates = datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc)
    upcoming_codes = [s.code for s in upcoming_sets(before_msh_rotates)]

    assert active_set_code(before_msh_rotates) not in upcoming_codes
    assert "MSH" in upcoming_codes
    assert is_known_set("msh") and not is_known_set("zzz")


def test_recent_released_sets_excludes_active_and_upcoming_and_caps():
    when = datetime(2026, 7, 14, 12, tzinfo=timezone.utc)
    codes = [seed.code for seed in recent_released_sets(when=when)]

    assert active_set_code(when) not in codes
    assert not any(seed.code in codes for seed in upcoming_sets(when))
    assert codes[0] == "SOS"
    assert len(codes) <= 8


def test_recent_released_sets_honors_limit():
    when = datetime(2026, 7, 14, 12, tzinfo=timezone.utc)
    assert len(recent_released_sets(limit=3, when=when)) == 3


def test_preview_set_code_prefers_the_set_in_spoiler_season():
    before_msh_rotates = datetime(2026, 6, 20, 12, tzinfo=timezone.utc)
    after_the_last_registered_set = datetime(2099, 1, 1, tzinfo=timezone.utc)

    assert preview_set_code(before_msh_rotates) == "MSH"
    assert preview_set_code(after_the_last_registered_set) == active_set_code(after_the_last_registered_set)


def test_format_options_excludes_unreleased_sets():
    options = format_options(None)
    values = [opt.value for opt in options]
    upcoming_codes = [s.code for s in upcoming_sets()]

    assert [opt.value for opt in options if opt.default] == [active_set_code()]
    assert upcoming_codes
    assert all(code not in values for code in upcoming_codes)


def test_build_mock_session_numbers_per_set(session, monkeypatch):
    monkeypatch.setattr(settings, "pod_draft_session_prefix", "LLU")

    first_id, first_n = build_mock_session(session, "MSH")
    record_mock_event(
        session, set_code="MSH",
        event_time=datetime(2026, 6, 23, tzinfo=timezone.utc), discord_thread_id="t1",
    )
    second_id, second_n = build_mock_session(session, "MSH")
    other_id, other_n = build_mock_session(session, "SOS")

    assert (first_n, second_n, other_n) == (1, 2, 1)
    assert MOCK_SESSION_RE.fullmatch(first_id).group(1, 2) == ("MSH", "1")
    assert MOCK_SESSION_RE.fullmatch(second_id).group(1, 2) == ("MSH", "2")
    assert MOCK_SESSION_RE.fullmatch(other_id).group(1, 2) == ("SOS", "1")


def test_build_mock_session_never_reuses_a_freed_number(session, monkeypatch):
    monkeypatch.setattr(settings, "pod_draft_session_prefix", "LLU")
    canceled = record_mock_event(
        session, set_code="MSH",
        event_time=datetime(2026, 6, 23, tzinfo=timezone.utc), discord_thread_id="t1",
    )
    abandoned_session = canceled.draftmancer_session

    session.delete(canceled)
    session.flush()
    reopened_session, number = build_mock_session(session, "MSH")

    assert number == 1
    assert reopened_session != abandoned_session


def test_reroll_session_suffix_keeps_the_base_and_changes_the_tail(session, monkeypatch):
    monkeypatch.setattr(settings, "pod_draft_session_prefix", "LLU")
    event = record_mock_event(
        session, set_code="MSH",
        event_time=datetime(2026, 6, 23, tzinfo=timezone.utc), discord_thread_id="t1",
    )
    original = event.draftmancer_session

    fresh = reroll_session_suffix(session, event.id)

    assert fresh != original
    assert event.draftmancer_session == fresh
    assert MOCK_SESSION_RE.fullmatch(fresh).group(1, 2) == ("MSH", "1")


def test_reroll_session_suffix_returns_none_for_a_missing_event(session):
    assert reroll_session_suffix(session, str(uuid4())) is None


def test_record_mock_event_fields(session, monkeypatch):
    monkeypatch.setattr(settings, "pod_draft_session_prefix", "LLU")
    session.add(MagicSet(code="MSH", name="Marvel Super Heroes", start_date=date(2026, 6, 23)))
    session.flush()

    event = record_mock_event(
        session, set_code="msh",
        event_time=datetime(2026, 6, 23, 18, tzinfo=timezone.utc), discord_thread_id="thread-1",
    )

    assert event.kind == "mock"
    assert event.set_code == "MSH"
    assert event.name == "MSH Mock Draft 1"
    assert MOCK_SESSION_RE.fullmatch(event.draftmancer_session)
    assert event.set_id is not None


def test_finalize_mock_event_marks_complete(session, monkeypatch):
    monkeypatch.setattr(settings, "pod_draft_session_prefix", "LLU")
    event = record_mock_event(
        session, set_code="MSH",
        event_time=datetime(2026, 6, 23, tzinfo=timezone.utc), discord_thread_id="t1",
    )

    finalized = finalize_mock_event(session, event.id)

    assert finalized is event
    assert event.socket_status == "complete"
    assert event.finalized_at is not None


def test_manager_imports_finalize_mock_event():
    from bot.services import pod_draft_manager, pod_drafts

    assert pod_draft_manager.finalize_mock_event is pod_drafts.finalize_mock_event


@pytest.mark.parametrize(
    "kind, socket_status, is_organizer, offers_cancel",
    [
        ("mock", "connected", False, True),
        ("mock", "connected", True, True),
        ("mock", "complete", False, False),
        ("mock", "complete", True, True),
        ("tournament", "connected", False, False),
        ("tournament", "connected", True, True),
    ],
    ids=["mock-anyone", "mock-organizer", "drafted-anyone", "drafted-organizer",
         "pod-anyone", "pod-organizer"],
)
def test_cancel_is_open_to_everyone_on_a_mock_lobby_until_the_draft_finishes(
    session, monkeypatch, kind, socket_status, is_organizer, offers_cancel,
):
    event = PodDraftEvent(
        event_date=date(2026, 6, 23), event_time=datetime(2026, 6, 23, tzinfo=timezone.utc),
        set_code="MSH", name="MSH Mock Draft 1", draftmancer_session="LLU-MSH-Mock-1",
        discord_thread_id="55501", socket_status=socket_status, kind=kind, current_round=None,
    )
    session.add(event)
    session.commit()
    for module in ("pod_drafts", "pod_launch", "pod_tournament"):
        monkeypatch.setattr(f"bot.services.{module}.SessionLocal", _session_factory(session))

    view = asyncio.run(build_pod_settings_view(_StubBot(), event.id, is_organizer=is_organizer))

    assert (view.on_cancel is not None) == offers_cancel


@pytest.mark.parametrize(
    "existing_colors, caption_colors, expected",
    [(None, "WR", "WR"), (None, None, None), ("UB", "WR", "UB")],
    ids=["fills-when-empty", "no-caption-colors", "never-overrides-reported"],
)
def test_mock_screenshot_backfills_colors_without_overriding(
    session, existing_colors, caption_colors, expected,
):
    player = _seed_player(session)
    event = PodDraftEvent(
        event_date=date(2026, 6, 23), event_time=datetime(2026, 6, 23, tzinfo=timezone.utc),
        set_code="MSH", name="MSH Mock Draft 1", draftmancer_session="LLU-MSH-Mock-1",
        discord_thread_id="mock-thread", socket_status="complete",
        kind="mock", current_round=None,
    )
    session.add(event)
    session.flush()
    session.add(PodDraftParticipant(
        event_id=event.id, player_id=player.id, display_name="Cap", deck_colors=existing_colors,
    ))
    session.flush()

    capture_deck_screenshot(session, "mock-thread", "901", "https://cdn.test/deck.png", "RW", caption_colors)

    stored = session.execute(
        select(PodDraftParticipant).where(PodDraftParticipant.event_id == event.id)
    ).scalar_one()
    assert stored.deck_colors == expected


@pytest.mark.parametrize(
    "socket_status, captured",
    [("pending", False), ("connected", False), ("draft_done", True), ("complete", True)],
)
def test_mock_screenshot_gate_opens_on_draft_completion(session, socket_status, captured):
    player = _seed_player(session)
    event = PodDraftEvent(
        event_date=date(2026, 6, 23), event_time=datetime(2026, 6, 23, tzinfo=timezone.utc),
        set_code="MSH", name="MSH Mock Draft 1", draftmancer_session="LLU-MSH-Mock-1",
        discord_thread_id="mock-thread", socket_status=socket_status,
        kind="mock", current_round=None,
    )
    session.add(event)
    session.flush()
    session.add(PodDraftParticipant(event_id=event.id, player_id=player.id, display_name="Cap"))
    session.flush()

    result = capture_deck_screenshot(session, "mock-thread", "901", "https://cdn.test/deck.png", None)

    stored = session.execute(
        select(PodDraftParticipant).where(PodDraftParticipant.event_id == event.id)
    ).scalar_one()
    if captured:
        assert result == event.id
        assert stored.deck_screenshot_url == "https://cdn.test/deck.png"
    else:
        assert result is None
        assert stored.deck_screenshot_url is None
