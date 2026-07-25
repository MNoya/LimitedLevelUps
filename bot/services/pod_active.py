"""Registry of active PodDraftManagers keyed by event_id.

Lives in its own module so pod_draft_manager and pod_tournament can both import it without a circular dependency.
The card-phase hook sits here for the same reason: draft start, draft done, and the champion post all re-render
the scheduled card, and those call sites span both modules.
"""
from __future__ import annotations

import asyncio

ACTIVE_POD_MANAGERS = {}

_CARD_PHASE_HOOK = None
_POD_COMPLETE_HOOK = None


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
