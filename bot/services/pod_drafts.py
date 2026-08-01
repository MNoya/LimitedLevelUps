"""Pod draft persistence and matching logic — pure SQLAlchemy, no Discord or websocket deps."""
from __future__ import annotations

import logging
import re
import secrets
import string
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, NamedTuple, Sequence
from urllib.parse import quote

from sqlalchemy import any_, delete, func, select, update
from sqlalchemy.orm import Session

from bot.config import settings
from bot.database import SessionLocal
from bot.models import (
    MagicSet,
    Player,
    PodDraftDmMessage,
    PodDraftEvent,
    PodDraftMatch,
    PodDraftParticipant,
    PodSignal,
    PodSignalMember,
)
from bot.services import pod_format
from bot.services import pod_format_interest
from bot.services import pod_signals
from bot.services.pod_schedule import NUM_RE, highest_event_number
from bot.services.pod_slot import next_collision_index, pod_display_name
from bot.slug import disambiguate_slug, slugify


log = logging.getLogger(__name__)


DM_KIND_ROUND = "round_pairing"
DM_KIND_SUBMIT_DECK = "submit_deck"
DM_KIND_SUBMIT_DECK_FINAL = "submit_deck_final"

FINALIZED_STATUSES = ("draft_done", "complete")

BOT_USER_NAME = "DisChordBot"
AI_BOT_NAME_RE = re.compile(r"^Bot #\d+$")


@dataclass(frozen=True)
class ParticipantDmInfo:
    """Per-participant info for round-start DMs. Keyed by normalized draftmancer_name."""
    participant_id: str
    discord_id: str | None
    display_name: str
    arena_name: str | None


@dataclass(frozen=True)
class FinalStanding:
    """One participant's outcome at champion finalization. Team pods carry no placement — a team
    draft has no individual champion, so their trophies stay record-only."""
    draftmancer_name: str
    placement: int | None
    record: str
    eliminated_round: int | None


def is_championship(name: str | None) -> bool:
    """The season-closing Set Championship pod, recognized by its event name."""
    return bool(name) and "championship" in name.lower()


def _lookup_set_id(session: Session, set_code: str) -> str | None:
    return session.execute(
        select(MagicSet.id).where(func.upper(MagicSet.code) == set_code.upper())
    ).scalar_one_or_none()


_SESSION_SUFFIX_LEN = 4


def _session_suffix() -> str:
    """Random lowercase tail that makes a Draftmancer session id unguessable, so nobody can enter and
    seize lobby ownership before the bot connects, and no two pods ever share a session."""
    return "".join(secrets.choice(string.ascii_lowercase) for _ in range(_SESSION_SUFFIX_LEN))


_SESSION_SUFFIX_RE = re.compile(rf"-[a-z]{{{_SESSION_SUFFIX_LEN}}}$")


def _session_id_off_base(session: Session, base: str) -> str:
    """A `<base>-<rand4>` session id not already taken by another event with the same base."""
    taken = set(session.execute(
        select(PodDraftEvent.draftmancer_session).where(PodDraftEvent.draftmancer_session.like(f"{base}-%"))
    ).scalars().all())
    while True:
        candidate = f"{base}-{_session_suffix()}"
        if candidate not in taken:
            return candidate


_ARENA_ID_RE = re.compile(r"#[0-9?]+$")
_ARENA_ID_SQL = r"#[0-9?]+$"
_NAME_TOKEN_RE = re.compile(r"[\s()/\\,|-]+")


def normalize_player_name(name: str) -> str:
    """Strip markdown escape backslashes and the trailing MTG Arena suffix, lowercase for matching.
    The suffix may be a `#?????` placeholder typed by players who don't know their Arena number."""
    return _ARENA_ID_RE.sub("", name.replace("\\", "")).lower()


_ARENA_TOKEN_RE = re.compile(r"\s*#[0-9?]+(?=$|\s|\))")


def strip_arena_suffix(name: str) -> str:
    """Display name with the MTG Arena `#12345` discriminator removed, case preserved. For surfaces that
    show the friendly name (standings, reported results) rather than the pre-match Arena reference.
    Handles a trailing suffix (`Alice#48087`) and one embedded before a nickname (`Alias#13488 (Bob)`)."""
    stripped = _ARENA_TOKEN_RE.sub("", name).strip()
    return stripped or name


def has_arena_suffix(name: str) -> bool:
    return bool(name and _ARENA_TOKEN_RE.search(name))


def name_token_match(norm: str, field: str) -> bool:
    """True when norm appears as a standalone word token of field, e.g. `wonderland`
    in `Alice (Wonderland)`."""
    return len(norm) >= 3 and norm in _NAME_TOKEN_RE.split(field.lower())


_FUZZY_MIN_LEN = 5
_SUGGEST_MAX_EDITS = 2


def within_one_edit(a: str, b: str) -> bool:
    """True when `a` and `b` are within a single insertion, deletion, or substitution
    (Levenshtein distance ≤ 1). Catches the off-by-one Arena handle typo `jineteroj0` vs `jineterojo`."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(1 for x, y in zip(a, b) if x != y) == 1
    shorter, longer = (a, b) if len(a) < len(b) else (b, a)
    i = j = 0
    edited = False
    while i < len(shorter) and j < len(longer):
        if shorter[i] == longer[j]:
            i += 1
            j += 1
        elif edited:
            return False
        else:
            edited = True
            j += 1
    return True


def levenshtein(a: str, b: str) -> int:
    """Edit distance between two strings; a transposition counts as two edits."""
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1]


def suggest_lobby_name(declared: str, live_names: Sequence[str]) -> str | None:
    """Closest live Draftmancer name to `declared` within a few edits, for a did-you-mean hint
    when /link-arena resolves to no seat in any active lobby. Catches transpositions like
    `sytlish`→`stylish` that within_one_edit rejects."""
    norm = normalize_player_name(declared)
    if len(norm) < _FUZZY_MIN_LEN:
        return None
    best_name = None
    best_dist = _SUGGEST_MAX_EDITS + 1
    for name in live_names:
        candidate = normalize_player_name(name)
        if len(candidate) < _FUZZY_MIN_LEN:
            continue
        dist = levenshtein(norm, candidate)
        if dist < best_dist:
            best_dist = dist
            best_name = name
    return best_name if best_dist <= _SUGGEST_MAX_EDITS else None


def _normalized_column(col):
    """SQL expression: lowercase a column and strip the trailing MTG Arena suffix."""
    return func.regexp_replace(func.lower(col), _ARENA_ID_SQL, "")


def classify_lobby_names(session: Session, names: Sequence[str]) -> list[tuple[str, str | None]]:
    """For each Draftmancer userName, return (arena_name, display_name) if linked else (arena_name, None)."""
    result = []
    for n in names:
        player = player_for_name(session, n)
        result.append((n, player.display_name if player else None))
    return result


def players_for_names(session: Session, names: Sequence[str]) -> list[tuple[str, Player | None]]:
    """Resolve each sesh attendee name to its Player (or None if unmatched), preserving order."""
    return [(n, player_for_name(session, n)) for n in names]


def player_for_name(session: Session, name: str) -> Player | None:
    """Resolve a Draftmancer/Discord name to a Player.

    Active players win; a retired or exiled player is matched only as a fallback, so pod
    attribution keeps recognizing someone who has since left the board without a stale row
    shadowing an active player who reused the same handle.

    Matching tiers (first hit wins):
      1. Exact match against any arena_aliases entry (normalized).
      2. Longest-prefix match against arena_aliases.
      3. Exact normalized display_name or discord_username.
      4. norm is a word token within display_name or discord_username
         (e.g. display "Alice (Wonderland)" matches Draftmancer name "Wonderland#12345").
    """
    norm = normalize_player_name(name)
    if not norm:
        return None
    return _match_player(session, norm, Player.active.is_(True)) \
        or _match_player(session, norm, Player.active.is_(False))


def _match_player(session: Session, norm: str, active_filter) -> Player | None:
    """Run the matching tiers over the player subset selected by `active_filter`."""
    found = session.execute(
        select(Player).where(active_filter, norm == any_(Player.arena_aliases)).limit(1)
    ).scalar_one_or_none()
    if found is not None:
        return found

    candidates = session.execute(select(Player).where(active_filter)).scalars().all()

    best: tuple[Player, str] | None = None
    for p in candidates:
        for alias in (p.arena_aliases or []):
            if alias and norm.startswith(alias):
                if best is None or len(alias) > len(best[1]):
                    best = (p, alias)
    if best is not None:
        return best[0]

    found = session.execute(
        select(Player).where(
            active_filter,
            (_normalized_column(Player.display_name) == norm)
            | (_normalized_column(Player.discord_username) == norm),
        ).limit(1)
    ).scalar_one_or_none()
    if found is not None:
        return found

    for p in candidates:
        for field in (p.display_name or "", p.discord_username or ""):
            if name_token_match(norm, field):
                return p

    if len(norm) >= _FUZZY_MIN_LEN:
        near: list[Player] = []
        for p in candidates:
            for alias in (p.arena_aliases or []):
                if len(alias) >= _FUZZY_MIN_LEN and within_one_edit(norm, alias):
                    near.append(p)
                    break
        if len(near) == 1:
            return near[0]

    return None


def lobby_match_status(declared: str, player_id: str, live_names: Sequence[str]) -> tuple[bool, str | None]:
    """Whether a live lobby seat now resolves to `player_id`, plus a did-you-mean name when it doesn't.

    Mirrors the lobby-card classifier: matched is True exactly when some Draftmancer name in
    `live_names` resolves via player_for_name to the just-linked player. When unmatched, the second
    element is the closest live name to `declared` (or None), surfaced as a /link-arena typo hint."""
    with SessionLocal() as session:
        for name in live_names:
            player = player_for_name(session, name)
            if player is not None and player.id == player_id:
                return True, None
    return False, suggest_lobby_name(declared, live_names)


def attach_arena_alias(
    session: Session,
    *,
    discord_id: str,
    discord_username: str,
    display_name: str,
    avatar_hash: str | None,
    arena_name: str,
    overwrite: bool = False,
) -> str:
    """Find-or-create the active player for `discord_id`, bind `arena_name` as a normalized alias, and
    return the player id. Shared by /link-arena and the lobby claim-seat button so the two never drift.

    Linking a handle someone else holds takes it from them, so a borrowed Arena account credits whoever
    is playing it now. Only future pods move: a finished pod already recorded which player sat in the
    seat. One holder at a time is also what keeps every seat lookup a single answer.

    Player.arena_name only ever holds a full ArenaID#12345 handle — a bare Draftmancer nickname is
    stored as an alias only, so it can't shadow the real handle in pairing displays. `overwrite` is
    the explicit /link-arena path: the user is declaring their handle, so it replaces whatever is
    stored.
    """
    normalized = normalize_player_name(arena_name)
    _release_handle(session, normalized, keep_discord_id=discord_id)
    player = session.execute(
        select(Player).where(Player.discord_id == discord_id)
    ).scalar_one_or_none()
    if player is None:
        taken_slugs = set(session.execute(select(Player.slug)).scalars().all())
        player = Player(
            slug=disambiguate_slug(slugify(display_name), taken_slugs),
            discord_id=discord_id,
            discord_username=discord_username,
            display_name=display_name,
            avatar_hash=avatar_hash,
            arena_name=arena_name if full_arena_handle(arena_name) else None,
            arena_aliases=[normalized],
            active=True,
            leaderboard_opt_in=False,
        )
        session.add(player)
    else:
        if overwrite or (full_arena_handle(arena_name) and not full_arena_handle(player.arena_name)):
            player.arena_name = arena_name
        if normalized not in player.arena_aliases:
            player.arena_aliases = [*player.arena_aliases, normalized]
    session.flush()
    return player.id


def _release_handle(session: Session, normalized: str, *, keep_discord_id: str) -> None:
    """Drop `normalized` from every other player holding it, clearing the stored handle when that is
    what it was. They keep their history and their row; they just stop answering to this name."""
    holders = session.execute(
        select(Player).where(
            Player.discord_id != keep_discord_id,
            normalized == any_(Player.arena_aliases),
        )
    ).scalars().all()
    for holder in holders:
        holder.arena_aliases = [alias for alias in holder.arena_aliases if alias != normalized]
        if normalize_player_name(holder.arena_name) == normalized:
            holder.arena_name = None
        log.info(f"arena handle {normalized!r} released from player {holder.id} to discord {keep_discord_id}")


def full_arena_handle(name: str | None) -> bool:
    """Whether `name` is a complete ArenaID#12345 handle rather than a bare Draftmancer nickname."""
    return "#" in (name or "")


def dm_draft_link_enabled(session: Session, discord_id: str) -> bool:
    """Whether `discord_id` receives the lobby-open link DM. Defaults on for a player with no row yet,
    matching the column default, so a drafter who never touched `/roles` still gets the DM."""
    enabled = session.execute(
        select(Player.dm_draft_link).where(Player.discord_id == discord_id)
    ).scalar_one_or_none()
    return True if enabled is None else enabled


def set_dm_draft_link(
    session: Session, *, discord_id: str, discord_username: str, display_name: str,
    avatar_hash: str | None, enabled: bool,
) -> None:
    """Persist the lobby-open DM preference, creating a lightweight player row when none exists so an
    onboarding-only member's choice sticks. Mirrors the row `attach_arena_alias` seeds, minus the handle."""
    player = _player_for_preference(
        session, discord_id=discord_id, discord_username=discord_username, display_name=display_name,
        avatar_hash=avatar_hash,
    )
    player.dm_draft_link = enabled
    session.flush()


def declined_pod_roles(session: Session, discord_id: str) -> set[str]:
    """The `PingRole.key`s this player switched off in `/roles`. Keys rather than role names, so a role
    that is renamed or retired never turns a stored no back into a yes. Empty for a player with no row."""
    declined = session.execute(
        select(Player.declined_pod_roles).where(Player.discord_id == discord_id)
    ).scalar_one_or_none()
    return set(declined or ())


def set_pod_roles_declined(
    session: Session, *, discord_id: str, discord_username: str, display_name: str,
    avatar_hash: str | None, keys: Iterable[str], declined: bool,
) -> None:
    """Record or clear an explicit choice about ping roles, creating a lightweight player row the same
    way the DM preference does. A decline never expires: the auto-grant reads it forever, and only the
    player turning the role back on in `/roles` clears it."""
    player = _player_for_preference(
        session, discord_id=discord_id, discord_username=discord_username, display_name=display_name,
        avatar_hash=avatar_hash,
    )
    stored = set(player.declined_pod_roles or ())
    player.declined_pod_roles = sorted(stored | set(keys) if declined else stored - set(keys))
    session.flush()


def declined_pod_roles_sync(discord_id: str) -> set[str]:
    with SessionLocal() as session:
        return declined_pod_roles(session, discord_id)


def set_pod_roles_declined_sync(
    *, discord_id: str, discord_username: str, display_name: str, avatar_hash: str | None,
    keys: Iterable[str], declined: bool,
) -> None:
    with SessionLocal() as session:
        set_pod_roles_declined(
            session, discord_id=discord_id, discord_username=discord_username, display_name=display_name,
            avatar_hash=avatar_hash, keys=keys, declined=declined,
        )
        session.commit()


def _player_for_preference(
    session: Session, *, discord_id: str, discord_username: str, display_name: str,
    avatar_hash: str | None,
) -> Player:
    """The row a preference hangs on, created when the member has none: someone who arrived through
    Discord onboarding and never linked anything still gets to keep a choice."""
    player = session.execute(
        select(Player).where(Player.discord_id == discord_id)
    ).scalar_one_or_none()
    if player is not None:
        return player
    taken_slugs = set(session.execute(select(Player.slug)).scalars().all())
    player = Player(
        slug=disambiguate_slug(slugify(display_name), taken_slugs),
        discord_id=discord_id,
        discord_username=discord_username,
        display_name=display_name,
        avatar_hash=avatar_hash,
        active=True,
        leaderboard_opt_in=False,
    )
    session.add(player)
    return player


def toggle_dm_draft_link(
    session: Session, *, discord_id: str, discord_username: str, display_name: str, avatar_hash: str | None,
) -> bool:
    """Flip the DM preference off its stored value and return the new state, creating a lightweight row
    when none exists. Shared by the `/roles` toggle and the in-DM toggle button so they can't drift."""
    new_state = not dm_draft_link_enabled(session, discord_id)
    set_dm_draft_link(
        session, discord_id=discord_id, discord_username=discord_username, display_name=display_name,
        avatar_hash=avatar_hash, enabled=new_state,
    )
    return new_state


def event_member_interests_sync(event_id: str) -> tuple[tuple[str, ...], ...]:
    """The format interest each signup brought to the pod this event grew from, read off the signal that
    created it, for deciding whether the opening lobby earns a format poll."""
    with SessionLocal() as session:
        signal = session.execute(
            select(PodSignal).where(PodSignal.event_id == event_id)
        ).scalar_one_or_none()
        if signal is None:
            return ()
        rows = session.execute(
            select(PodSignalMember.format_interest)
            .where(PodSignalMember.signal_id == signal.id)
            .order_by(PodSignalMember.created_at)
        ).scalars().all()
        return tuple(tuple(pod_format_interest.normalize(interest)) for interest in rows)


def event_signal_crowd_sync(event_id: str) -> list[str]:
    """Discord ids of everyone gathered on the signal that created this pod — Yes and Maybe alike,
    since the pre-start window is exactly when a roster member may choose a second table's seat
    instead. Empty for pods with no signal (sesh pods), which never carry a format tally."""
    with SessionLocal() as session:
        signal = session.execute(
            select(PodSignal).where(PodSignal.event_id == event_id)
        ).scalar_one_or_none()
        if signal is None:
            return []
        rows = session.execute(
            select(PodSignalMember.discord_user_id)
            .where(
                PodSignalMember.signal_id == signal.id,
                PodSignalMember.rsvp.in_((pod_signals.RSVP_YES, pod_signals.RSVP_MAYBE)),
            )
            .order_by(PodSignalMember.created_at)
        ).scalars().all()
        return list(rows)


def get_format_interests(session: Session, discord_id: str) -> list[str]:
    """The player's standing draft-format preference, empty when unset or the player has no row yet."""
    stored = session.execute(
        select(Player.format_interests).where(Player.discord_id == discord_id)
    ).scalar_one_or_none()
    return pod_format_interest.normalize(stored)


def set_format_interests(
    session: Session, *, discord_id: str, discord_username: str, display_name: str,
    avatar_hash: str | None, interests: list[str],
) -> None:
    """Persist the standing format preference, creating a lightweight player row when none exists so an
    onboarding-only member's choice sticks. Mirrors the row set_dm_draft_link seeds."""
    normalized = pod_format_interest.normalize(interests)
    player = session.execute(
        select(Player).where(Player.discord_id == discord_id)
    ).scalar_one_or_none()
    if player is None:
        taken_slugs = set(session.execute(select(Player.slug)).scalars().all())
        player = Player(
            slug=disambiguate_slug(slugify(display_name), taken_slugs),
            discord_id=discord_id,
            discord_username=discord_username,
            display_name=display_name,
            avatar_hash=avatar_hash,
            active=True,
            leaderboard_opt_in=False,
            format_interests=normalized,
        )
        session.add(player)
    else:
        player.format_interests = normalized
    session.flush()


def get_flashback_ranking(session: Session, discord_id: str) -> list[str]:
    """The player's ranked flashback preference, best first, empty when unset or the player has no row."""
    stored = session.execute(
        select(Player.flashback_ranking).where(Player.discord_id == discord_id)
    ).scalar_one_or_none()
    return list(stored) if stored else []


def set_flashback_ranking(session: Session, *, discord_id: str, ranking: list[str]) -> None:
    """Persist the ranked flashback preference on an existing player row, best first and capped at
    FLASHBACK_RANKING_MAX so a pod's Format Vote stays reasonable to fill. The interest save creates the row,
    so this only updates; a missing player is a no-op."""
    player = session.execute(
        select(Player).where(Player.discord_id == discord_id)
    ).scalar_one_or_none()
    if player is not None:
        player.flashback_ranking = ranking[: pod_format_interest.FLASHBACK_RANKING_MAX]
        session.flush()


def get_cube_choices(session: Session, discord_id: str) -> list[str]:
    """The player's marked server cubes, unordered, empty when unset or the player has no row."""
    stored = session.execute(
        select(Player.cube_choices).where(Player.discord_id == discord_id)
    ).scalar_one_or_none()
    return list(stored) if stored else []


def set_cube_choices(session: Session, *, discord_id: str, choices: list[str]) -> None:
    """Persist the marked server cubes on an existing player row. The interest save creates the row, so
    this only updates; a missing player is a no-op."""
    player = session.execute(
        select(Player).where(Player.discord_id == discord_id)
    ).scalar_one_or_none()
    if player is not None:
        player.cube_choices = choices
        session.flush()


def event_member_rankings_sync(event_id: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Each signup's Discord id paired with their ranked flashback preference, for pre-seeding a fresh pod's
    format poll from standing rankings. Members with no ranking are omitted."""
    with SessionLocal() as session:
        signal = session.execute(
            select(PodSignal).where(PodSignal.event_id == event_id)
        ).scalar_one_or_none()
        if signal is None:
            return ()
        rows = session.execute(
            select(PodSignalMember.discord_user_id, Player.flashback_ranking)
            .join(Player, Player.discord_id == PodSignalMember.discord_user_id)
            .where(PodSignalMember.signal_id == signal.id)
            .order_by(PodSignalMember.created_at)
        ).all()
        return tuple((discord_id, tuple(ranking)) for discord_id, ranking in rows if ranking)


def player_arena_handle(session: Session, discord_id: str) -> str | None:
    """The full Arena handle stored for `discord_id`, or None when the player is unknown or holds only
    a bare Draftmancer nickname. Drives the welcome's link gate and the returning card's handle line."""
    player = session.execute(
        select(Player).where(Player.discord_id == discord_id)
    ).scalar_one_or_none()
    if player is None or not full_arena_handle(player.arena_name):
        return None
    return player.arena_name


def build_mock_session(session: Session, set_code: str) -> tuple[str, int]:
    """`LLU-<SET>-Mock-<N>-<rand4>` with N the next free per-set mock number. The random tail keeps the
    id unguessable and un-reusable: cancelling a mock deletes its event row, which frees N, and without
    the tail the next mock of that set would reopen the exact lobby the cancelled one left behind, with
    whoever stayed in it still holding Draftmancer ownership."""
    base = f"{settings.pod_draft_session_prefix}-{set_code.upper()}-Mock"
    taken = session.execute(
        select(PodDraftEvent.draftmancer_session).where(PodDraftEvent.draftmancer_session.like(f"{base}-%"))
    ).scalars().all()
    highest = 0
    for session_id in taken:
        match = _MOCK_NUMBER_RE.search(session_id or "")
        if match:
            highest = max(highest, int(match.group(1)))
    number = highest + 1
    return _session_id_off_base(session, f"{base}-{number}"), number


_MOCK_NUMBER_RE = re.compile(r"-Mock-(\d+)")


def record_mock_event(
    session: Session, *, set_code: str, event_time: datetime, discord_thread_id: str,
) -> PodDraftEvent:
    """Insert a kind='mock' pod event — an on-demand draft with no sesh post, no RSVPs, no rounds.
    Participants and draft logs are written by the manager once the Draftmancer draft completes."""
    code = set_code.upper()
    session_id, number = build_mock_session(session, code)
    event = PodDraftEvent(
        event_date=event_time.date(),
        event_time=event_time,
        set_id=_lookup_set_id(session, code),
        set_code=code,
        format_label=pod_format.label_for(code),
        name=f"{code} Mock Draft {number}",
        draftmancer_session=session_id,
        discord_thread_id=discord_thread_id,
        socket_status="pending",
        kind="mock",
    )
    session.add(event)
    session.flush()
    return event


def record_mock_repost_sync(event_id: str, channel_id: str | None, message_id: str | None) -> None:
    """Track a mock draft's reposted card in the event's card columns. A mock's first card is its thread
    starter, resolved off the thread id, so these stay free for the repost — which the manager keeps in
    step with the anchor and retires before posting a newer one. Both None clears the record."""
    with SessionLocal() as session:
        event = session.get(PodDraftEvent, event_id)
        if event is None:
            return
        event.card_channel_id = channel_id
        event.card_message_id = message_id
        session.commit()


def mock_repost_sync(event_id: str) -> tuple[str, str] | None:
    """(channel id, message id) of the mock draft's reposted card, or None when it has none."""
    with SessionLocal() as session:
        event = session.get(PodDraftEvent, event_id)
        if event is None or not (event.card_channel_id and event.card_message_id):
            return None
        return event.card_channel_id, event.card_message_id


def reroll_session_suffix(session: Session, event_id: str) -> str | None:
    """Re-roll the random tail of an event's Draftmancer session id, abandoning a lobby the bot could not
    own for one nobody can already be sitting in. Draftmancer never hands ownership to a later arrival, so
    moving to a different session is the only way to get a lobby the bot controls. Returns the new id, or
    None when the event is gone."""
    event = session.get(PodDraftEvent, event_id)
    if event is None:
        return None
    base = _SESSION_SUFFIX_RE.sub("", event.draftmancer_session)
    event.draftmancer_session = _session_id_off_base(session, base)
    return event.draftmancer_session


def build_ondemand_session(session: Session, event_date: date) -> str:
    """`LLU-<Mon>-<Day>-<rand4>` for a poll/queue-born pod. The id omits the set code so a format
    change before the draft never desyncs the shown URL. The random tail keeps the session id
    unguessable so nobody can seize lobby ownership before the bot, and no two pods share a lobby."""
    base = f"{settings.pod_draft_session_prefix}-{event_date:%b}-{event_date.day}"
    return _session_id_off_base(session, base)


def record_ondemand_event(
    session: Session, *, set_code: str, event_time: datetime, name: str, discord_thread_id: str,
) -> PodDraftEvent:
    """Insert a kind='tournament' pod with no sesh post — the shared creation path for the daily poll
    and /pod-queue. The roster is seeded by the caller from the signal's members; rounds and champion
    finalize exactly like a sesh-born tournament."""
    code = set_code.upper()
    event = PodDraftEvent(
        event_date=event_time.date(),
        event_time=event_time,
        set_id=_lookup_set_id(session, code),
        set_code=code,
        format_label=pod_format.label_for(code),
        name=name,
        draftmancer_session=build_ondemand_session(session, event_time.date()),
        discord_thread_id=discord_thread_id,
        socket_status="pending",
        kind="tournament",
        closed_decklist=is_championship(name),
    )
    session.add(event)
    session.flush()
    return event


TABLE_SUFFIX_RE = re.compile(r"\s+(?:[-–]\s+)?Table\s+(\d+)\s*$", re.IGNORECASE)
_TABLE_INDEX_RE = re.compile(r"Table\s+(\d+)\s*$", re.IGNORECASE)


def table_base_name(name: str) -> str:
    """The event name with any trailing ` - Table N` stripped, so opening a table off a Table 2 still
    bases new tables on the original pod name rather than nesting `... Table 2 - Table 3`."""
    return TABLE_SUFFIX_RE.sub("", name).strip()


def next_table_index(session: Session, base_name: str) -> int:
    """Next free table number for `base_name`; the original pod is table 1, so the first new table is 2."""
    names = session.execute(
        select(PodDraftEvent.name).where(PodDraftEvent.name.ilike(f"{base_name}%Table %"))
    ).scalars().all()
    return next_collision_index(names, _TABLE_INDEX_RE)


def build_table_session(session: Session, source_session_id: str, table_index: int) -> str:
    """`<source session>-T<index>-<rand4>` for a second table off a pod. The random tail keeps it
    unguessable and unshared even to players who know the source lobby's id."""
    base = f"{source_session_id}-T{table_index}"
    return _session_id_off_base(session, base)


def record_table_event(session: Session, *, source_event_id: str, format_code: str | None = None) -> PodDraftEvent:
    """Insert a kind='tournament' table cloned from `source_event_id` — same pairings, seating, and
    start, but its own Draftmancer session and no sesh RSVP. The roster arrives from the new
    lobby. `discord_thread_id` is a placeholder the caller overwrites once the thread exists (as
    record_mock_event does). By default the table keeps the source's format and the ` - Table N`
    lineage name; a `format_code` differing from the source repoints set, label, and set id, and the
    table is named as its own pod of that format instead.

    The start is the source's, not the moment the table is opened: a table is one half of a pod that
    split, so a launcher column that groups its pods by start reads the two as one slot instead of
    sorting the table above the pod it came from."""
    source = session.get(PodDraftEvent, source_event_id)
    if source is None:
        raise ValueError(f"source pod event {source_event_id} not found")
    code = (format_code or source.set_code or "").upper()
    same_format = code == (source.set_code or "").upper()
    base_name = table_base_name(source.name)
    table_index = next_table_index(session, base_name)
    session_id = build_table_session(session, source.draftmancer_session, table_index)
    if same_format:
        name = f"{base_name} - Table {table_index}"
        set_id, set_code, format_label = source.set_id, source.set_code, source.format_label
    else:
        name = dedupe_event_name(session, pod_display_name(code, source.event_time))
        set_id = _lookup_set_id(session, code)
        set_code = code
        format_label = pod_format.label_for(code)
    event = PodDraftEvent(
        event_date=source.event_date,
        event_time=source.event_time,
        set_id=set_id,
        set_code=set_code,
        format_label=format_label,
        name=name,
        draftmancer_session=session_id,
        discord_thread_id="pending",
        socket_status="pending",
        kind="tournament",
        pairing_mode=source.pairing_mode,
        seating_mode=source.seating_mode,
        closed_decklist=source.closed_decklist,
    )
    session.add(event)
    session.flush()
    return event


def dedupe_event_name(session: Session, base: str) -> str:
    """`base`, or `base #N` when an event of that name already exists — two format tables opened off
    different pods in the same slot would otherwise collide on the slot-derived name."""
    names = session.execute(
        select(PodDraftEvent.name).where(PodDraftEvent.name.ilike(f"{base}%"))
    ).scalars().all()
    if base not in names:
        return base
    return f"{base} #{next_collision_index(names)}"


class TableTarget(NamedTuple):
    source_name: str
    table_index: int
    set_code: str | None
    event_time: datetime


def preview_table_target_sync(source_event_id: str) -> TableTarget | None:
    """What the table claim card needs to render before anything is inserted: the source's base name
    and next table index for lineage naming, plus its set and event time so a format-preset card can
    show the name the table will materialize under. None when the source is gone."""
    with SessionLocal() as session:
        source = session.get(PodDraftEvent, source_event_id)
        if source is None:
            return None
        base = table_base_name(source.name)
        return TableTarget(base, next_table_index(session, base), source.set_code, source.event_time)


def draftmancer_url_for(session_id: str, user_name: str | None = None) -> str:
    """Compose the player-facing session URL from current settings at send time, so a host change
    reaches already-recorded events instead of fossilizing in the row. A `user_name` appends
    `&userName=`, which Draftmancer reads to pre-fill the lobby name so pairing resolves without the
    player renaming by hand."""
    url = f"{settings.draftmancer_web_url}/?session={session_id}"
    if user_name:
        url += f"&userName={quote(user_name, safe='')}"
    return url


def pod_page_url(event_name: str) -> str:
    """The event's page on the website. The slug is derived from the name the same way the
    `public_pod_draft_events` view derives it, so the link is valid from the moment the row exists."""
    return f"{settings.public_site_url.rstrip('/')}/pods/{slugify(event_name)}"


def update_event_format(session: Session, event_id: str, code: str) -> str | None:
    """Repoint a pre-draft pod event's set_code, set_id and format label, swapping the leading set
    token in its name to match. Returns the (possibly renamed) event name, or None if missing or
    already finalized."""
    event = session.get(PodDraftEvent, event_id)
    if event is None or event.socket_status in FINALIZED_STATUSES:
        return None
    next_number = highest_event_number(_set_event_names(session, code)) + 1
    event.name = renamed_for_format(event.name, event.set_code, code, next_number)
    event.set_code = code
    event.set_id = _lookup_set_id(session, code)
    event.format_label = pod_format.label_for(code)
    return event.name


def _set_event_names(session: Session, code: str) -> list[str]:
    return list(session.execute(
        select(PodDraftEvent.name).where(PodDraftEvent.set_code == code.upper())
    ).scalars())


def renamed_for_format(name: str, old_code: str | None, new_code: str, next_number: int) -> str:
    """Rebuild a `SET Pod Draft #N - date` name for the new format: swap the leading format label and
    renumber to the new set's next slot, keeping the date suffix. Since pods are counted per set,
    switching MSH → SOS moves `#14` to SOS's own next number. Labels come from `format_display`, so a
    cube reads as its proper name (Peasant Cube) on both sides. Names that don't lead with the old
    format's label are returned unchanged."""
    if not old_code:
        return name
    prefix = f"{pod_format.format_display(old_code)} "
    if not name.upper().startswith(prefix.upper()):
        return name
    renumbered = NUM_RE.sub(f"#{next_number}", name[len(prefix):], count=1)
    return f"{pod_format.format_display(new_code)} {renumbered}"


def load_event_set_code_sync(event_id: str) -> str | None:
    """Current set_code (format code) for a pod event, or None when missing."""
    with SessionLocal() as session:
        return session.execute(
            select(PodDraftEvent.set_code).where(PodDraftEvent.id == event_id)
        ).scalar_one_or_none()


def load_event_pairing_mode_sync(event_id: str) -> str | None:
    """Current pairing_mode for a pod event, or None when missing."""
    with SessionLocal() as session:
        return session.execute(
            select(PodDraftEvent.pairing_mode).where(PodDraftEvent.id == event_id)
        ).scalar_one_or_none()


def load_event_seating_mode_sync(event_id: str) -> str | None:
    """Current seating_mode for a pod event, or None when missing."""
    with SessionLocal() as session:
        return session.execute(
            select(PodDraftEvent.seating_mode).where(PodDraftEvent.id == event_id)
        ).scalar_one_or_none()


def load_event_name_sync(event_id: str) -> str:
    with SessionLocal() as session:
        return session.execute(
            select(PodDraftEvent.name).where(PodDraftEvent.id == event_id)
        ).scalar_one_or_none() or "Pod Draft"


def load_event_kind_sync(event_id: str) -> str:
    with SessionLocal() as session:
        return session.execute(
            select(PodDraftEvent.kind).where(PodDraftEvent.id == event_id)
        ).scalar_one_or_none() or "tournament"


def load_event_closed_decklist_sync(event_id: str) -> bool:
    """Whether the pod hides its decklists and draft log on the website until it finishes."""
    with SessionLocal() as session:
        return bool(session.execute(
            select(PodDraftEvent.closed_decklist).where(PodDraftEvent.id == event_id)
        ).scalar_one_or_none())


def set_event_closed_decklist_sync(event_id: str, closed: bool) -> None:
    with SessionLocal() as session:
        session.execute(
            update(PodDraftEvent).where(PodDraftEvent.id == event_id).values(closed_decklist=closed)
        )
        session.commit()


def load_event_description_sync(event_id: str) -> str | None:
    """The organizer's note on the pod, shown in place of the card's RSVP prompt."""
    with SessionLocal() as session:
        return session.execute(
            select(PodDraftEvent.description).where(PodDraftEvent.id == event_id)
        ).scalar_one_or_none()


def set_event_description_sync(event_id: str, description: str | None) -> None:
    with SessionLocal() as session:
        session.execute(
            update(PodDraftEvent).where(PodDraftEvent.id == event_id).values(description=description)
        )
        session.commit()


def delete_event_sync(event_id: str) -> None:
    """Delete a pod event row; the cascade drops participants, matches, replays, and DM trackers."""
    with SessionLocal() as session:
        session.execute(delete(PodDraftEvent).where(PodDraftEvent.id == event_id))
        session.commit()


def load_event_id_by_thread_sync(thread_id: str) -> str | None:
    with SessionLocal() as session:
        return session.execute(
            select(PodDraftEvent.id).where(PodDraftEvent.discord_thread_id == thread_id)
        ).scalar_one_or_none()


def load_event_id_by_name_sync(name: str) -> str | None:
    with SessionLocal() as session:
        return session.execute(
            select(PodDraftEvent.id).where(PodDraftEvent.name == name)
        ).scalar_one_or_none()


def load_event_thread_id_sync(event_id: str) -> str | None:
    with SessionLocal() as session:
        return session.execute(
            select(PodDraftEvent.discord_thread_id).where(PodDraftEvent.id == event_id)
        ).scalar_one_or_none()


def load_event_time_sync(event_id: str) -> datetime | None:
    with SessionLocal() as session:
        return session.execute(
            select(PodDraftEvent.event_time).where(PodDraftEvent.id == event_id)
        ).scalar_one_or_none()


def load_event_seeding_context_sync(event_id: str) -> tuple[str | None, str | None, str]:
    """(seating_mode, thread_id, name) in one query — the fields the seeding-table refresh reads on every
    fire. name falls back to 'Pod Draft', the others to None when the event is missing."""
    with SessionLocal() as session:
        row = session.execute(
            select(PodDraftEvent.seating_mode, PodDraftEvent.discord_thread_id, PodDraftEvent.name)
            .where(PodDraftEvent.id == event_id)
        ).one_or_none()
    if row is None:
        return None, None, "Pod Draft"
    return row.seating_mode, row.discord_thread_id, row.name or "Pod Draft"


def search_event_names_sync(query: str, limit: int = 25) -> list[str]:
    """Most-recent-first event names matching a case-insensitive substring of `query`; empty query
    returns the most recent."""
    with SessionLocal() as session:
        stmt = select(PodDraftEvent.name).order_by(PodDraftEvent.event_date.desc().nulls_last())
        if query:
            stmt = stmt.where(PodDraftEvent.name.ilike(f"%{query}%"))
        return [n for n in session.execute(stmt.limit(limit)).scalars().all() if n]


def seed_event_participants(session: Session, event_id: str, roster: list[str]) -> None:
    """Upsert one pod_draft_participants row per Draftmancer userName in `roster`. Idempotent —
    safe to call multiple times on the same event; existing rows get backfilled instead of
    duplicated."""
    for name in roster:
        upsert_participant(session, event_id, display_name=name, draftmancer_name=name)


def apply_seat_indexes(session: Session, event_id: str, seats: list[str]) -> None:
    if not seats:
        return
    rows = session.execute(
        select(PodDraftParticipant).where(PodDraftParticipant.event_id == event_id)
    ).scalars().all()
    by_dm: dict[str, PodDraftParticipant] = {}
    by_display: dict[str, PodDraftParticipant] = {}
    for row in rows:
        if row.draftmancer_name:
            by_dm[normalize_player_name(row.draftmancer_name)] = row
        if row.display_name:
            by_display[normalize_player_name(row.display_name)] = row
    matched = 0
    for i, name in enumerate(seats):
        if not name or name == BOT_USER_NAME or AI_BOT_NAME_RE.match(name):
            continue
        key = normalize_player_name(name)
        row = by_dm.get(key) or by_display.get(key)
        if row is None:
            log.info(f"seat_index: no participant matching {name!r} in {event_id}")
            continue
        row.seat_index = i
        matched += 1
    log.info(f"seat_index: applied to {matched}/{len(seats)} seats for {event_id}")


def upsert_participant(
    session: Session,
    event_id: str,
    display_name: str,
    draftmancer_name: str | None = None,
) -> PodDraftParticipant:
    """Find-or-create a participant for this event.

    Match priority: existing draftmancer_name (normalized), existing display_name vs supplied draftmancer_name 
    (normalized), existing display_name vs supplied display_name (normalized).
    Backfills draftmancer_name and player_id when previously null.
    Arena-name mismatches fall through to /pod-link-arena.
    """
    rows = session.execute(
        select(PodDraftParticipant).where(PodDraftParticipant.event_id == event_id)
    ).scalars().all()

    target_dn = normalize_player_name(display_name)
    target_dm = normalize_player_name(draftmancer_name) if draftmancer_name else None

    found: PodDraftParticipant | None = None
    if target_dm:
        for row in rows:
            if row.draftmancer_name and normalize_player_name(row.draftmancer_name) == target_dm:
                found = row
                break
        if found is None:
            for row in rows:
                if normalize_player_name(row.display_name) == target_dm:
                    found = row
                    break
    if found is None:
        for row in rows:
            if normalize_player_name(row.display_name) == target_dn:
                found = row
                break

    if found is None:
        found = PodDraftParticipant(event_id=event_id, display_name=display_name)
        session.add(found)

    if draftmancer_name and not found.draftmancer_name:
        found.draftmancer_name = draftmancer_name

    if found.player_id is None:
        candidate = player_for_name(session, draftmancer_name or display_name)
        if candidate is None and draftmancer_name:
            candidate = player_for_name(session, display_name)
        if candidate is not None and _player_already_seated(rows, candidate.id, found):
            candidate = None
        if candidate is not None:
            found.player_id = candidate.id
            _adopt_session_arena_handle(candidate, draftmancer_name)

    session.flush()
    return found


def _player_already_seated(
    rows: list[PodDraftParticipant], player_id, exclude: PodDraftParticipant,
) -> bool:
    """Whether another seat in this event already holds `player_id`. Two Draftmancer names can resolve
    to one Player (e.g. a prefix-alias match), but uq_pod_participant_event_player allows a player a
    single seat; the second name stays unlinked instead of crashing the tournament seed."""
    return any(row is not exclude and row.player_id == player_id for row in rows)


def _adopt_session_arena_handle(player: Player, draftmancer_name: str | None) -> None:
    """Record the Draftmancer session handle on a matched Player that lacks one. Players who joined
    through 17lands carry no Arena handle (17lands exposes none), so their first pod — played under a
    full ArenaID#12345 name — is where we learn it. A handle already stored is never overwritten."""
    if not full_arena_handle(draftmancer_name):
        return
    if not full_arena_handle(player.arena_name):
        player.arena_name = draftmancer_name
    normalized = normalize_player_name(draftmancer_name)
    if normalized and normalized not in player.arena_aliases:
        player.arena_aliases = [*player.arena_aliases, normalized]


def add_pairing(
    session: Session,
    event_id: str,
    round_num: int,
    player_a_name: str,
    player_b_name: str,
    pairing_index: int = 0,
) -> PodDraftMatch:
    """Insert a pending match (no winner yet); returns the row with its generated id."""
    match = PodDraftMatch(
        event_id=event_id,
        round=round_num,
        pairing_index=pairing_index,
        player_a_name=player_a_name,
        player_b_name=player_b_name,
    )
    session.add(match)
    session.flush()
    return match


def set_match_result(
    session: Session,
    match_id: str,
    winner_name: str,
    score: str,
) -> PodDraftMatch:
    """Fill winner + score on a pending match. Raises if no row matches."""
    match = session.get(PodDraftMatch, match_id)
    if match is None:
        raise ValueError(f"pod_draft_match {match_id} not found")
    match.winner_name = winner_name
    match.score = score
    match.reported_at = datetime.now(timezone.utc)
    session.flush()
    return match


def record_match(
    session: Session,
    event_id: str,
    round_num: int,
    player_a_name: str,
    player_b_name: str,
    winner_name: str,
    score: str,
) -> PodDraftMatch:
    """Idempotent on (event_id, round, names) so debounce re-commits collapse to one row."""
    existing = session.execute(
        select(PodDraftMatch).where(
            PodDraftMatch.event_id == event_id,
            PodDraftMatch.round == round_num,
            PodDraftMatch.player_a_name == player_a_name,
            PodDraftMatch.player_b_name == player_b_name,
        )
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if existing is None:
        existing = PodDraftMatch(
            event_id=event_id,
            round=round_num,
            player_a_name=player_a_name,
            player_b_name=player_b_name,
            winner_name=winner_name,
            score=score,
            reported_at=now,
        )
        session.add(existing)
    else:
        existing.winner_name = winner_name
        existing.score = score
        existing.reported_at = now
    session.flush()
    return existing


def finalize_champion(
    session: Session,
    event_id: str,
    standings: Sequence[FinalStanding],
) -> PodDraftEvent:
    """Apply placements/records to participants and mark socket_status='complete'. Draft-log URLs
    are written mid-draft by pod_draft_manager and intentionally left untouched here."""
    event = session.get(PodDraftEvent, event_id)
    if event is None:
        raise ValueError(f"pod_draft_event {event_id} not found")

    for standing in standings:
        participant = upsert_participant(
            session,
            event_id,
            display_name=standing.draftmancer_name,
            draftmancer_name=standing.draftmancer_name,
        )
        participant.placement = standing.placement
        participant.record = standing.record
        participant.eliminated_round = standing.eliminated_round

    event.socket_status = "complete"
    if event.finalized_at is None:
        event.finalized_at = datetime.now(timezone.utc)
    session.flush()
    return event


def finalize_mock_event(session: Session, event_id: str) -> PodDraftEvent | None:
    """Mark a mock pod complete: no placements or records, just the done timestamp so the public view
    treats it as final. The site renders its seating + draft logs; there are no rounds to score."""
    event = session.get(PodDraftEvent, event_id)
    if event is None:
        return None
    event.socket_status = "complete"
    if event.finalized_at is None:
        event.finalized_at = datetime.now(timezone.utc)
    session.flush()
    return event


def upsert_dm_message(
    session: Session,
    *,
    event_id: str,
    participant_id: str,
    kind: str,
    round_num: int | None,
    match_id: str | None,
    dm_channel_id: str,
    dm_message_id: str,
) -> None:
    """Upsert a DM message ref. Unique key is (participant_id, kind, round_num)."""
    existing = session.execute(
        select(PodDraftDmMessage).where(
            PodDraftDmMessage.participant_id == participant_id,
            PodDraftDmMessage.kind == kind,
            PodDraftDmMessage.round_num.is_(round_num) if round_num is None
            else PodDraftDmMessage.round_num == round_num,
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.match_id = match_id
        existing.dm_channel_id = dm_channel_id
        existing.dm_message_id = dm_message_id
        return
    session.add(PodDraftDmMessage(
        event_id=event_id,
        participant_id=participant_id,
        kind=kind,
        round_num=round_num,
        match_id=match_id,
        dm_channel_id=dm_channel_id,
        dm_message_id=dm_message_id,
    ))


def dm_messages_for_match(session: Session, match_id: str) -> list[PodDraftDmMessage]:
    """All round_pairing DM messages tracked for a given match (both opponents)."""
    return list(session.execute(
        select(PodDraftDmMessage).where(
            PodDraftDmMessage.match_id == match_id,
            PodDraftDmMessage.kind == DM_KIND_ROUND,
        )
    ).scalars().all())


def dm_messages_for_round(session: Session, event_id: str, round_num: int) -> list[PodDraftDmMessage]:
    """All round_pairing DM messages tracked for a given (event, round)."""
    return list(session.execute(
        select(PodDraftDmMessage).where(
            PodDraftDmMessage.event_id == event_id,
            PodDraftDmMessage.round_num == round_num,
            PodDraftDmMessage.kind == DM_KIND_ROUND,
        )
    ).scalars().all())


def submit_deck_dm_for_participant(session: Session, participant_id: str) -> PodDraftDmMessage | None:
    return session.execute(
        select(PodDraftDmMessage).where(
            PodDraftDmMessage.participant_id == participant_id,
            PodDraftDmMessage.kind == DM_KIND_SUBMIT_DECK,
        )
    ).scalar_one_or_none()


def delete_submit_deck_dm(session: Session, participant_id: str) -> None:
    row = submit_deck_dm_for_participant(session, participant_id)
    if row is not None:
        session.delete(row)


def final_submit_deck_dm_for_participant(
    session: Session, participant_id: str,
) -> PodDraftDmMessage | None:
    return session.execute(
        select(PodDraftDmMessage).where(
            PodDraftDmMessage.participant_id == participant_id,
            PodDraftDmMessage.kind == DM_KIND_SUBMIT_DECK_FINAL,
        )
    ).scalar_one_or_none()


def participant_id_for_discord_user(
    session: Session, event_id: str, discord_id: str,
) -> str | None:
    return session.execute(
        select(PodDraftParticipant.id)
        .join(Player, Player.id == PodDraftParticipant.player_id)
        .where(
            PodDraftParticipant.event_id == event_id,
            Player.discord_id == discord_id,
        )
    ).scalar_one_or_none()


def participants_with_discord_for_event(session: Session, event_id: str) -> list[dict]:
    """Participant rows joined to Player.discord_id, with deck-state fields for Submit Deck DMs.
    Skips participants whose Player row isn't linked (no real Discord user)."""
    rows = session.execute(
        select(
            PodDraftParticipant.id,
            PodDraftParticipant.deck_colors,
            Player.discord_id,
        )
        .join(Player, Player.id == PodDraftParticipant.player_id)
        .where(PodDraftParticipant.event_id == event_id)
    ).all()
    return [
        {"participant_id": pid, "deck_colors": dc, "discord_id": did}
        for pid, dc, did in rows
        if did
    ]


def thread_id_for_event(session: Session, event_id: str) -> str | None:
    return session.execute(
        select(PodDraftEvent.discord_thread_id).where(PodDraftEvent.id == event_id)
    ).scalar_one_or_none()


DM_SUBMISSION_WINDOW = timedelta(hours=24)


def active_event_for_discord_user_in_dm(session: Session, discord_id: str) -> tuple[str, str] | None:
    """Return (event_id, discord_thread_id) for the most recent pod-draft this user is in within the
    DM submission window, so deck-color/screenshot DMs route to the right pod. Window is finalization-
    agnostic: late deck submissions stay accepted (and stored) after the tournament finalizes; newest
    pod wins so a stale pod can't shadow a fresh one."""
    cutoff = datetime.now(timezone.utc) - DM_SUBMISSION_WINDOW
    row = session.execute(
        select(PodDraftEvent.id, PodDraftEvent.discord_thread_id)
        .join(PodDraftParticipant, PodDraftParticipant.event_id == PodDraftEvent.id)
        .join(Player, Player.id == PodDraftParticipant.player_id)
        .where(
            Player.discord_id == discord_id,
            PodDraftEvent.event_time >= cutoff,
        )
        .order_by(PodDraftEvent.event_time.desc())
        .limit(1)
    ).first()
    return (row[0], row[1]) if row else None


class OwnMatch(NamedTuple):
    event_id: str
    round_num: int
    match_id: str


def own_open_matches(session: Session, discord_id: str) -> list[OwnMatch]:
    """Every unreported pairing the caller holds in the newest pod that has one, in round order.

    A Swiss or bracket pod yields exactly one, since round N+1 is not paired until N is reported. A team
    draft inserts all three rounds up front, so it yields all of them and the player reports whichever
    they actually played.
    """
    rows = _own_matches(session, discord_id, reported=False)
    if not rows:
        return []
    newest_event = rows[0].event_id
    return [row for row in rows if row.event_id == newest_event]


def latest_reported_match(session: Session, discord_id: str) -> OwnMatch | None:
    """The caller's most recently settled pairing, so a report attempt with nothing open can name the
    result that already stands."""
    rows = _own_matches(session, discord_id, reported=True)
    return rows[0] if rows else None


def _own_matches(session: Session, discord_id: str, *, reported: bool) -> list[OwnMatch]:
    cutoff = datetime.now(timezone.utc) - DM_SUBMISSION_WINDOW
    participant_name = _normalized_column(PodDraftParticipant.draftmancer_name)
    settled = PodDraftMatch.winner_name.is_not(None) if reported else PodDraftMatch.winner_name.is_(None)
    round_order = PodDraftMatch.round.desc() if reported else PodDraftMatch.round.asc()
    rows = session.execute(
        select(PodDraftMatch.event_id, PodDraftMatch.round, PodDraftMatch.id)
        .join(PodDraftEvent, PodDraftEvent.id == PodDraftMatch.event_id)
        .join(PodDraftParticipant, PodDraftParticipant.event_id == PodDraftEvent.id)
        .join(Player, Player.id == PodDraftParticipant.player_id)
        .where(
            Player.discord_id == discord_id,
            PodDraftEvent.event_time >= cutoff,
            settled,
            (_normalized_column(PodDraftMatch.player_a_name) == participant_name)
            | (_normalized_column(PodDraftMatch.player_b_name) == participant_name),
        )
        .order_by(PodDraftEvent.event_time.desc(), round_order)
    ).all()
    return [OwnMatch(event_id, round_num, match_id) for event_id, round_num, match_id in rows]


def is_pod_thread_champion(session: Session, thread_id: str, discord_id: str) -> bool:
    """True if (thread_id, discord_id) maps to a participant with placement=1."""
    row = session.execute(
        select(PodDraftParticipant.placement)
        .join(Player, Player.id == PodDraftParticipant.player_id)
        .join(PodDraftEvent, PodDraftEvent.id == PodDraftParticipant.event_id)
        .where(
            PodDraftEvent.discord_thread_id == thread_id,
            Player.discord_id == discord_id,
        )
    ).first()
    return bool(row and row[0] == 1)


def list_champions(session: Session, set_code: str | None = None) -> list[dict]:
    """Champions across all finalized events, ordered by event_date; caller partitions by set/format."""
    query = (
        select(PodDraftEvent, PodDraftParticipant, Player)
        .join(PodDraftParticipant, PodDraftParticipant.event_id == PodDraftEvent.id)
        .outerjoin(Player, Player.id == PodDraftParticipant.player_id)
        .where(PodDraftParticipant.placement == 1)
        .order_by(PodDraftEvent.event_date)
    )
    if set_code:
        query = query.where(func.upper(PodDraftEvent.set_code) == set_code.upper())

    rows = session.execute(query).all()
    return [
        {
            "event_name": event.name,
            "event_date": event.event_date,
            "set_code": event.set_code,
            "format_label": event.format_label,
            "champion_display_name": player.display_name if player else participant.display_name,
            "champion_draftmancer_name": participant.draftmancer_name,
            "player_slug": player.slug if player else None,
            "discord_id": player.discord_id if player else None,
        }
        for event, participant, player in rows
    ]


def participant_dm_info(session: Session, event_id: str) -> dict[str, ParticipantDmInfo]:
    """Map normalized draftmancer_name → ParticipantDmInfo for every participant in the event.

    display_name prefers Player.display_name (the resolved Discord server nickname) over the
    participant row's display_name, which can carry a stale Arena-style handle. Pod DMs have no
    guild context, so the opponent line renders this name as text rather than a `<@id>` mention —
    a mention would resolve to the global username instead of the LLU server nickname.

    arena_name sources from PodDraftParticipant.draftmancer_name — the handle the player actually
    set in the Draftmancer client for THIS session. For multi-account users this can differ from
    Player.arena_name (their stored display primary); the opponent DM should report the session-
    specific name so they look for the right Arena handle.
    """
    rows = session.execute(
        select(
            PodDraftParticipant.id,
            PodDraftParticipant.draftmancer_name,
            PodDraftParticipant.display_name,
            Player.display_name,
            Player.discord_id,
        )
        .outerjoin(Player, Player.id == PodDraftParticipant.player_id)
        .where(PodDraftParticipant.event_id == event_id)
    ).all()
    info: dict[str, ParticipantDmInfo] = {}
    for participant_id, dm_name, participant_dn, player_dn, discord_id in rows:
        key = normalize_player_name(dm_name) if dm_name else normalize_player_name(participant_dn)
        raw = player_dn or participant_dn
        info[key] = ParticipantDmInfo(
            participant_id=participant_id,
            discord_id=discord_id,
            display_name=strip_arena_suffix(raw) if raw else raw,
            arena_name=dm_name,
        )
    return info


def set_participant_deck_colors(
    session: Session,
    discord_thread_id: str,
    discord_id: str,
    deck_colors: str,
) -> bool:
    """Save deck_colors on the (event, player) participant row. Returns False if the user isn't in this pod."""
    participant = session.execute(
        select(PodDraftParticipant)
        .join(Player, Player.id == PodDraftParticipant.player_id)
        .join(PodDraftEvent, PodDraftEvent.id == PodDraftParticipant.event_id)
        .where(
            PodDraftEvent.discord_thread_id == discord_thread_id,
            Player.discord_id == discord_id,
        )
    ).scalar_one_or_none()
    if participant is None:
        return False
    participant.deck_colors = deck_colors
    session.flush()
    return True


def list_event_participants_sync(event_id: str) -> list[tuple[str, str, str | None]]:
    """(participant_id, display_name, deck_colors) for a pod, seat order then name — the roster the
    organizer color panel lists."""
    with SessionLocal() as session:
        rows = session.execute(
            select(PodDraftParticipant.id, PodDraftParticipant.display_name, PodDraftParticipant.deck_colors)
            .where(PodDraftParticipant.event_id == event_id)
            .order_by(PodDraftParticipant.seat_index, PodDraftParticipant.display_name)
        ).all()
    return [(pid, name, colors) for pid, name, colors in rows]


def set_participant_deck_colors_by_id_sync(participant_id: str, deck_colors: str) -> str | None:
    """Overwrite one participant's deck_colors by row id — an organizer setting colors for any player.
    Returns the event_id, or None when the participant is gone."""
    with SessionLocal() as session:
        participant = session.get(PodDraftParticipant, participant_id)
        if participant is None:
            return None
        participant.deck_colors = deck_colors
        event_id = participant.event_id
        session.commit()
        return event_id


_RECORD_PATTERN = re.compile(r"\b([0-3])\s*[-:\s]\s*([0-3])\b")


def caption_has_record_pattern(caption: str | None) -> bool:
    return parse_caption_record(caption) is not None


def parse_caption_record(caption: str | None) -> str | None:
    """Normalized 'W-L' record from a deck caption ('2-1 rakdos stuff' -> '2-1'), or None."""
    if not caption:
        return None
    m = _RECORD_PATTERN.search(caption)
    if m is None:
        return None
    return f"{m.group(1)}-{m.group(2)}"


def capture_deck_screenshot(
    session: Session,
    discord_thread_id: str,
    discord_id: str,
    image_url: str,
    caption: str | None = None,
    colors: str | None = None,
) -> str | None:
    """Capture (or overwrite) a participant's deck screenshot. Returns event_id on capture.

    Gating:
      - Picks must be done — tournament pods set current_round once pairings begin; mock pods never
        run rounds, so draft completion (socket_status draft_done/complete) opens the slot instead.
      - A stored caption that already matches the record-pattern locks the slot; a new image with
        no record-pattern is ignored. A new image WITH a record-pattern overwrites unconditionally
        (latest-record-wins).
      - Once the championship has posted, a participant with a deck already on file is done — new
        images are ignored unless the caption carries a record pattern (intentional replacement).
      - Otherwise last-wins.

    `colors` (parsed from the caption by the caller) backfills deck_colors only when the player
    hasn't already reported them — an explicit color report always wins over a caption guess.
    """
    row = session.execute(
        select(
            PodDraftParticipant,
            PodDraftEvent.id,
            PodDraftEvent.kind,
            PodDraftEvent.current_round,
            PodDraftEvent.socket_status,
            PodDraftEvent.championship_posted_at,
        )
        .join(Player, Player.id == PodDraftParticipant.player_id)
        .join(PodDraftEvent, PodDraftEvent.id == PodDraftParticipant.event_id)
        .where(
            PodDraftEvent.discord_thread_id == discord_thread_id,
            Player.discord_id == discord_id,
        )
    ).first()
    if row is None:
        return None
    participant, event_id, kind, current_round, socket_status, championship_posted_at = row
    if kind == "mock":
        picks_done = socket_status in ("draft_done", "complete")
    else:
        picks_done = current_round is not None
    if not picks_done:
        log.info(f"[DECK] screenshot.too_early event={event_id} discord_id={discord_id} caption={caption!r}")
        return None
    new_has_record = caption_has_record_pattern(caption)
    existing_locked = caption_has_record_pattern(participant.deck_screenshot_caption)
    if not new_has_record and existing_locked:
        log.info(
            f"[DECK] screenshot.locked_ignored event={event_id} discord_id={discord_id} "
            f"locked_caption={participant.deck_screenshot_caption!r} new_caption={caption!r}"
        )
        return None
    if not new_has_record and championship_posted_at is not None and participant.deck_screenshot_url is not None:
        log.info(
            f"[DECK] screenshot.post_championship_ignored event={event_id} discord_id={discord_id} "
            f"caption={caption!r}"
        )
        return None
    replaced = participant.deck_screenshot_url is not None
    participant.deck_screenshot_url = image_url
    participant.deck_screenshot_caption = caption or None
    if colors and not participant.deck_colors:
        participant.deck_colors = colors
    session.flush()
    log.info(
        f"[DECK] screenshot.stored event={event_id} discord_id={discord_id} round={current_round} "
        f"caption={caption!r} has_record={new_has_record} replaced={replaced}"
    )
    return event_id


def get_participant_deck_state(
    session: Session,
    discord_thread_id: str,
    discord_id: str,
) -> tuple[bool, str | None]:
    """Return (is_participant, deck_colors). is_participant=False short-circuits the gate."""
    row = session.execute(
        select(PodDraftParticipant.deck_colors)
        .join(Player, Player.id == PodDraftParticipant.player_id)
        .join(PodDraftEvent, PodDraftEvent.id == PodDraftParticipant.event_id)
        .where(
            PodDraftEvent.discord_thread_id == discord_thread_id,
            Player.discord_id == discord_id,
        )
    ).first()
    if row is None:
        return False, None
    return True, row[0]




class PodSetSummary(NamedTuple):
    """A player's pod results for one set. ``trophies`` counts a 3-0 record OR a pod win
    (placement 1) — multiple per large pod, and a small pod's 2-1 winner still earns one.
    A 2-1 that won the pod is a trophy, not a ``wins_2_1``. Team pods write no placement,
    so their trophies come from 3-0 records alone."""
    events: int
    wins: int
    losses: int
    trophies: int
    wins_2_1: int


def pod_scoring_counts(
    session: Session, set_code: str, before: datetime | None = None,
) -> dict[str, tuple[int, int]]:
    """Per active player: (trophy count, 2-1 count) for the set, keyed by player_id.
    Pods are always public, no opt-in gate. `before` counts only the pods played by that instant, for a
    board rebuilt as it stood at a past deadline."""
    query = (
        select(PodDraftParticipant.player_id, PodDraftParticipant.record, PodDraftParticipant.placement)
        .join(PodDraftEvent, PodDraftEvent.id == PodDraftParticipant.event_id)
        .join(Player, Player.id == PodDraftParticipant.player_id)
        .where(
            PodDraftEvent.set_code == set_code,
            Player.active.is_(True),
            PodDraftParticipant.record.isnot(None),
        )
    )
    if before is not None:
        query = query.where(PodDraftEvent.event_time < before)
    rows = session.execute(query).all()
    by_player: dict[str, list[tuple[str | None, int | None]]] = {}
    for player_id, record, placement in rows:
        by_player.setdefault(player_id, []).append((record, placement))
    summaries = {pid: _summarize_pod_records(finishes) for pid, finishes in by_player.items()}
    return {pid: (s.trophies, s.wins_2_1) for pid, s in summaries.items()}


def pod_summary_by_set_for_player(session: Session, player_id: str) -> dict[str, PodSetSummary]:
    """One player's pod summary per set_code; no opt-in filter since it's their own stats."""
    rows = session.execute(
        select(PodDraftEvent.set_code, PodDraftParticipant.record, PodDraftParticipant.placement)
        .join(PodDraftParticipant, PodDraftParticipant.event_id == PodDraftEvent.id)
        .where(
            PodDraftParticipant.player_id == player_id,
            PodDraftParticipant.record.isnot(None),
        )
    ).all()
    by_set: dict[str, list[tuple[str | None, int | None]]] = {}
    for set_code, record, placement in rows:
        by_set.setdefault(set_code, []).append((record, placement))
    return {sc: _summarize_pod_records(finishes) for sc, finishes in by_set.items()}


def _summarize_pod_records(finishes: list[tuple[str | None, int | None]]) -> PodSetSummary:
    """A trophy is a 3-0 record or a pod win (placement 1); a 2-1 that won is a trophy, not a 2-1."""
    wins = losses = trophies = wins_2_1 = 0
    for record, placement in finishes:
        won, lost = parse_record(record)
        wins += won
        losses += lost
        if record == "3-0" or placement == 1:
            trophies += 1
        elif record == "2-1":
            wins_2_1 += 1
    return PodSetSummary(len(finishes), wins, losses, trophies, wins_2_1)


def parse_record(record: str | None) -> tuple[int, int]:
    if not record or "-" not in record:
        return 0, 0
    w_str, l_str = record.split("-", 1)
    try:
        return int(w_str), int(l_str)
    except ValueError:
        return 0, 0
