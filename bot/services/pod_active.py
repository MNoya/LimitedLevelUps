"""Registries of live pod state that exists only in memory, keyed by event_id.

Lives in its own module so pod_draft_manager and pod_tournament can both import it without a circular
dependency. The card-phase hook sits here for the same reason: draft start, draft done, and the champion
post all re-render the scheduled card, and those call sites span both modules.

ACTIVE_TABLE_VIEWS holds the live second-table claim card per source event, keyed the same way. It sits
next to the managers because a forming table has no event row yet, so a reader outside the command layer
has nowhere else to find one.
"""
from __future__ import annotations

import asyncio

ACTIVE_POD_MANAGERS = {}
ACTIVE_TABLE_VIEWS = {}

_CARD_PHASE_HOOK = None
_POD_COMPLETE_HOOK = None
_POD_CARD_HOOK = None


def set_card_phase_hook(callback) -> None:
    """pod_draft registers the scheduled-card re-render here so lifecycle transitions can refresh the
    card's status line without the service layer importing the command module."""
    global _CARD_PHASE_HOOK
    _CARD_PHASE_HOOK = callback


def set_pod_complete_hook(callback) -> None:
    """The daily launcher registers the column roll here: solo, team, and mock pods all finalize in
    different modules, and none of them may import the launcher task."""
    global _POD_COMPLETE_HOOK
    _POD_COMPLETE_HOOK = callback


def set_pod_card_hook(callback) -> None:
    """pod_rsvp registers the pod-card poster here so a pod born in the service layer can post one
    without importing the command module."""
    global _POD_CARD_HOOK
    _POD_CARD_HOOK = callback


async def post_pod_card(channel, *, name: str, event_time, set_code: str, roster=None):
    """The card a pod with no scheduled signal owns, or None if the hook is unset or the post failed."""
    if _POD_CARD_HOOK is None:
        return None
    return await _POD_CARD_HOOK(channel, name=name, event_time=event_time, set_code=set_code, roster=roster)


def notify_card_phase(bot, event_id: str) -> None:
    """Re-render the pod's scheduled card for a lifecycle change (no-op if unset). Fired at draft
    start, a draft restart, draft done, and the champion post; the render itself derives the status
    line from the live manager."""
    if _CARD_PHASE_HOOK is not None:
        asyncio.create_task(_CARD_PHASE_HOOK(bot, event_id))


def notify_pod_complete(bot, event_id: str) -> None:
    """Roll the launcher column this pod played in to the next day (no-op if unset). Fired once the pod is
    finalized, never at draft done: a pod mid-rounds still owns its slot."""
    if _POD_COMPLETE_HOOK is not None:
        asyncio.create_task(_POD_COMPLETE_HOOK(bot, event_id))


def active_manager_for_channel(channel_id: int | None):
    """The live manager whose pod thread is this channel, or None."""
    for manager in ACTIVE_POD_MANAGERS.values():
        if manager.thread_id == channel_id:
            return manager
    return None
