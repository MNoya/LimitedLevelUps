"""The pod setup a Settings panel writes to the event row, held as one JSON blob.

These are Draftmancer session parameters. Storing them means the Settings panel can offer them from
registration onward, before any session exists, and the values reach the table when the lobby opens.
Adding a setting is a key and a default here, with no migration.

Every read merges over the defaults, so a caller always gets a complete set and never has to decide
what an absent key means.
"""
from __future__ import annotations

from sqlalchemy import select

from bot.config import settings
from bot.database import SessionLocal
from bot.models import PodDraftEvent
from bot.services.pod_confirm import SESSION_SEATS, table_capacity_for


PICK_TIMER = "pick_timer"
PICKS_PER_PACK = "picks_per_pack"
PICKS_SET_BY_USER = "picks_set_by_user"
MAX_PLAYERS = "max_players"
PACKS_PER_PLAYER = "packs_per_player"
CARDS_PER_PACK = "cards_per_pack"


def defaults() -> dict[str, int | None]:
    """A pod nobody has configured. The pack shape defaults to nothing so a set keeps its own collation
    and an imported cube keeps the numbers its list carries."""
    return {
        PICK_TIMER: settings.pod_draft_pick_timer,
        PICKS_PER_PACK: settings.pod_draft_picks_per_pack,
        PICKS_SET_BY_USER: False,
        MAX_PLAYERS: settings.pod_draft_max_players,
        PACKS_PER_PLAYER: None,
        CARDS_PER_PACK: None,
    }


def load_sync(event_id: str) -> dict[str, int | None]:
    return {**defaults(), **stored_sync(event_id)}


def stored_sync(event_id: str) -> dict[str, int | None]:
    """Only what someone set, for a caller that has to tell a chosen value from a defaulted one."""
    with SessionLocal() as session:
        stored = session.execute(
            select(PodDraftEvent.settings).where(PodDraftEvent.id == event_id)
        ).scalar_one_or_none()
    return dict(stored or {})


def store_sync(event_id: str, **values: int | None) -> None:
    """Merge the named settings into the blob, leaving the rest of it alone."""
    known = defaults()
    unknown = sorted(set(values) - set(known))
    if unknown:
        raise ValueError(f"Unknown pod settings: {', '.join(unknown)}")
    with SessionLocal() as session:
        row = session.get(PodDraftEvent, event_id)
        if row is None:
            return
        row.settings = {**(row.settings or {}), **values}
        session.commit()


def size_room_sync(event_id: str, seatable: int) -> None:
    """Open this pod's room at the table its roster plans, read at one session's ceiling since a room
    never splits, and leave a size somebody already chose alone"""
    if MAX_PLAYERS in stored_sync(event_id):
        return
    store_sync(event_id, max_players=table_capacity_for(min(seatable, SESSION_SEATS)))


def clear_sync(event_id: str, *keys: str) -> None:
    """Drop settings back to their defaults, for a pod whose format change invalidates its pack shape."""
    with SessionLocal() as session:
        row = session.get(PodDraftEvent, event_id)
        if row is None:
            return
        remaining = {key: value for key, value in (row.settings or {}).items() if key not in keys}
        row.settings = remaining
        session.commit()


def apply_to_manager(manager, stored: dict[str, int | None]) -> None:
    """Seed a manager from stored setup so the session it opens carries the pod's configuration."""
    manager.pick_timer = stored[PICK_TIMER]
    manager.picks_per_pack = stored[PICKS_PER_PACK]
    manager.picks_set_by_user = stored[PICKS_SET_BY_USER]
    manager.max_players = stored[MAX_PLAYERS]
    manager.packs_per_player = stored[PACKS_PER_PLAYER]
    manager.cards_per_pack = stored[CARDS_PER_PACK]


def from_manager(manager) -> dict[str, int | None]:
    """What a live table is running, which leads the stored blob whenever the draft flow moved a value
    on its own instead of through the Settings panel."""
    return {
        PICK_TIMER: manager.pick_timer,
        PICKS_PER_PACK: manager.picks_per_pack,
        PICKS_SET_BY_USER: manager.picks_set_by_user,
        MAX_PLAYERS: manager.max_players,
        PACKS_PER_PLAYER: manager.packs_per_player,
        CARDS_PER_PACK: manager.cards_per_pack,
    }
