"""The repost fallback: a card the bot cannot locate is, to the thread, no card at all."""
import asyncio

import pytest

from bot.tasks import pod_draft_reminder as reminder


@pytest.fixture
def calls(monkeypatch):
    seen = {"edited": 0, "reposted": 0}

    async def fake_repost(event_id):
        seen["reposted"] += 1

    monkeypatch.setattr(reminder, "repost_roster_reminder", fake_repost)
    monkeypatch.setattr(reminder, "load_event_thread_id_for_roster_sync", lambda event_id: 4242)
    return seen


def _edit_returning(value, seen):
    async def fake_edit(event_id):
        seen["edited"] += 1
        return value
    return fake_edit


def test_a_card_that_cannot_be_located_is_posted_instead(calls, monkeypatch):
    monkeypatch.setattr(reminder, "refresh_roster_reminder_for_event", _edit_returning(False, calls))
    reminder._messages_since_card.clear()

    asyncio.run(reminder.refresh_or_repost_roster_reminder("evt"))

    assert (calls["edited"], calls["reposted"]) == (1, 1)


def test_a_card_edited_in_place_is_not_reposted(calls, monkeypatch):
    monkeypatch.setattr(reminder, "refresh_roster_reminder_for_event", _edit_returning(True, calls))
    reminder._messages_since_card.clear()

    asyncio.run(reminder.refresh_or_repost_roster_reminder("evt"))

    assert (calls["edited"], calls["reposted"]) == (1, 0)


def test_a_buried_card_skips_the_edit_and_moves(calls, monkeypatch):
    monkeypatch.setattr(reminder, "refresh_roster_reminder_for_event", _edit_returning(True, calls))
    reminder._messages_since_card[4242] = reminder.BURIED_AFTER_MESSAGES

    asyncio.run(reminder.refresh_or_repost_roster_reminder("evt"))

    assert (calls["edited"], calls["reposted"]) == (0, 1)


def test_a_confirm_answer_never_hands_discord_a_none_view(monkeypatch):
    """discord.py rejects `view=None`, so the no-view case must be MISSING. Only reachable through a
    real interaction, which is why the button failed in production and no test noticed."""
    import discord

    from bot.commands import pod_rsvp

    monkeypatch.setattr(pod_rsvp, "arena_handle_for_sync", lambda discord_id: "Finkel#11111")
    monkeypatch.setattr(pod_rsvp, "_owned_lobby_session", lambda event_id: None)
    monkeypatch.setattr(pod_rsvp, "_pod_identity", lambda result: ("MSH Aug 8 Early Pod", None))

    _answer, view = asyncio.run(pod_rsvp._confirm_answer(_FakeInteraction(), _FakeResult()))

    assert view is discord.utils.MISSING


class _FakeUser:
    id = 1


class _FakeResult:
    class state:
        event_id = "evt"


class _FakeInteraction:
    user = _FakeUser()
