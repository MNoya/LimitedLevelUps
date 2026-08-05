"""Capture 17lands game-history records for pod participants."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Sequence
from uuid import uuid4

from sqlalchemy import or_, select

from bot.database import SessionLocal
from bot.models import PodDraftEvent, PodDraftMatch, PodDraftParticipant, PodDraftReplay, Player
from bot.services.pod_drafts import player_for_name
from bot.services.seventeenlands import SeventeenLandsClient


log = logging.getLogger(__name__)

_REPLAY_BASE_URL = "https://www.17lands.com"
POD_EVENT_NAMES = frozenset({"DirectGameTournamentLimited", "DirectGameLimited"})
MIN_TURNS = 3
MAX_GAMES_PER_MATCH = 3
_EVENT_WINDOW_HOURS = 6
POD_REPLAY_LOOKBACK = timedelta(days=3)


async def fetch_and_persist_replays_for_player(
    client: SeventeenLandsClient,
    event_id: str,
    player_id: str,
    player_seat_name: str,
    token: str,
) -> int:
    if not token:
        return 0
    try:
        games = await asyncio.to_thread(client.fetch_user_games, token)
    except Exception:
        log.warning(f"17lands fetch failed for player {player_id} in event {event_id}", exc_info=True)
        return 0
    if not games:
        return 0
    try:
        return await asyncio.to_thread(
            persist_replays_sync, event_id, player_id, player_seat_name, games,
        )
    except Exception:
        log.warning(f"persist_replays failed for player {player_id} in event {event_id}", exc_info=True)
        return 0


async def capture_event_replays(client: SeventeenLandsClient, event_id: str) -> int:
    """Fetch each participant's 17lands game history once and persist their replays. Called at
    finalize, when every round's games already exist, so a single pull per player covers the whole
    event — no re-fetching the same heavy history on every round's report."""
    targets = await asyncio.to_thread(_event_replay_targets_sync, event_id)
    total = 0
    for player_id, seat_name, token in targets:
        total += await fetch_and_persist_replays_for_player(client, event_id, player_id, seat_name, token)
    log.info(f"[REPLAYS] event_capture done event={event_id} players={len(targets)} replays={total}")
    return total


async def capture_recent_pod_replays_for_player(
    client: SeventeenLandsClient,
    player_id: str,
    lookback: timedelta = POD_REPLAY_LOOKBACK,
) -> int:
    """Pull 17lands replays for any pod this player drafted within `lookback`.

    Fired in the background off /join: a drafter who links their 17lands token after playing gets their
    recent pods' games captured without a manual backfill. A no-token player is a no-op."""
    targets = await asyncio.to_thread(_recent_pod_replay_targets_sync, player_id, lookback)
    total = 0
    for event_id, seat_name, token in targets:
        total += await fetch_and_persist_replays_for_player(client, event_id, player_id, seat_name, token)
    if targets:
        log.info(f"[REPLAYS] recent_capture player={player_id} events={len(targets)} replays={total}")
    return total


def schedule_recent_pod_replay_capture(
    player_id: str, client: SeventeenLandsClient | None = None,
) -> None:
    """Fire the recent-pod replay pull in the background so /join returns at once."""
    pull_client = client or SeventeenLandsClient()

    async def _run() -> None:
        try:
            await capture_recent_pod_replays_for_player(pull_client, player_id)
        except Exception:
            log.warning(f"recent pod replay capture failed for player {player_id}", exc_info=True)

    asyncio.create_task(_run())


def _event_replay_targets_sync(event_id: str) -> list[tuple[str, str, str]]:
    """(player_id, draftmancer_name, token) for every participant of the event with a 17lands token."""
    with SessionLocal() as session:
        rows = session.execute(
            select(
                PodDraftParticipant.player_id,
                PodDraftParticipant.draftmancer_name,
                Player.seventeenlands_token,
            )
            .join(Player, Player.id == PodDraftParticipant.player_id)
            .where(PodDraftParticipant.event_id == event_id)
        ).all()
    return [(pid, name, token) for pid, name, token in rows if pid and name and token]


def _recent_pod_replay_targets_sync(player_id: str, lookback: timedelta) -> list[tuple[str, str, str]]:
    with SessionLocal() as session:
        targets = _recent_pod_replay_targets(session, player_id, lookback)
        session.commit()
    return targets


def _recent_pod_replay_targets(
    session, player_id: str, lookback: timedelta,
) -> list[tuple[str, str, str]]:
    """(event_id, seat_name, token) for each pod the player joined within `lookback`, token permitting.

    A seat still unlinked (player_id null) but whose name resolves to this player is adopted here, so a
    first-time joiner's pod seat is linked when they /join and their games get attributed."""
    player = session.get(Player, player_id)
    if player is None or not player.seventeenlands_token:
        return []
    token = player.seventeenlands_token

    cutoff = datetime.now(timezone.utc) - lookback
    event_ids = session.execute(
        select(PodDraftEvent.id).where(PodDraftEvent.event_time >= cutoff)
    ).scalars().all()

    targets: list[tuple[str, str, str]] = []
    for event_id in event_ids:
        seat = _player_seat_in_event(session, event_id, player)
        if seat is not None:
            targets.append((event_id, seat.draftmancer_name or seat.display_name, token))
    return targets


def _player_seat_in_event(session, event_id: str, player: Player) -> PodDraftParticipant | None:
    rows = session.execute(
        select(PodDraftParticipant).where(PodDraftParticipant.event_id == event_id)
    ).scalars().all()
    for row in rows:
        if row.player_id == player.id:
            return row
    for row in rows:
        if row.player_id is not None:
            continue
        matched = player_for_name(session, row.draftmancer_name or row.display_name)
        if matched is not None and matched.id == player.id:
            row.player_id = player.id
            return row
    return None


def attribute_games_to_rounds(
    games: Sequence[dict],
    player_matches: Sequence[PodDraftMatch],
    event_time: datetime | None,
    claimed_game_ids: frozenset[str] = frozenset(),
) -> dict[str, int]:
    """Map game_id -> round for the games that are a real replay of one of this player's reported
    matches in this event.

    A game qualifies when it is a pod game with at least MIN_TURNS turns (restarts and quick
    concessions fall out in filter_and_sort_games), inside the event window, not already claimed by an
    earlier pod (the earliest pod owns a game, so drafting twice in one night doesn't double-count),
    and it falls in a match's report window: after the previous match's report, up to this one plus a
    minute of grace. Round 1's window starts at event_time so pre-draft and other-pod games can't leak
    in through an open-ended lower bound. At most MAX_GAMES_PER_MATCH games are kept per match, earliest
    first; extras from a rematch or a stray game are dropped. Reported scores aren't consulted — players
    misreport them and 17lands drops games, so the count is best-effort. Skipped matches form no window.
    """
    usable = [g for g in filter_and_sort_games(games) if is_in_event_window(g, event_time)]
    matches_in_round_order = sorted(player_matches, key=lambda m: m.round)

    out: dict[str, int] = {}
    lower = event_time
    for m in matches_in_round_order:
        if m.reported_at is None or not m.winner_name or not m.score or m.score == "0-0":
            continue
        upper_with_grace = m.reported_at + timedelta(minutes=1)
        window = [
            g for g in usable
            if extract_game_id(g) not in claimed_game_ids
            and extract_game_id(g) not in out
            and (lower is None or parse_game_time(g.get("game_time")) > lower)
            and parse_game_time(g.get("game_time")) <= upper_with_grace
        ]
        lower = upper_with_grace
        for g in window[:MAX_GAMES_PER_MATCH]:
            gid = extract_game_id(g)
            if gid:
                out[gid] = m.round
    return out


def persist_replays_sync(
    event_id: str,
    player_id: str,
    player_seat_name: str,
    games: Sequence[dict],
) -> int:
    with SessionLocal() as session:
        event = session.get(PodDraftEvent, event_id)
        if event is None:
            log.warning(f"persist_replays: event {event_id} not found")
            return 0

        player_matches = session.execute(
            select(PodDraftMatch).where(
                PodDraftMatch.event_id == event_id,
                or_(
                    PodDraftMatch.player_a_name == player_seat_name,
                    PodDraftMatch.player_b_name == player_seat_name,
                ),
            )
        ).scalars().all()

        claimed = _claimed_game_ids_for_player(session, player_id, event.event_time)
        attribution = attribute_games_to_rounds(games, player_matches, event.event_time, claimed)
        games_by_id: dict[str, dict] = {}
        for g in games:
            gid = extract_game_id(g)
            if gid:
                games_by_id.setdefault(gid, g)

        count = 0
        for gid, round_num in attribution.items():
            g = games_by_id.get(gid)
            if g is None:
                continue
            gt = parse_game_time(g.get("game_time"))
            if gt is None:
                continue
            raw_link = g.get("link") or ""
            full_link = (
                f"{_REPLAY_BASE_URL}{raw_link}" if raw_link.startswith("/") else raw_link
            )
            turns = g.get("turns") if isinstance(g.get("turns"), int) else None
            on_play = g.get("on_play") if isinstance(g.get("on_play"), bool) else None

            existing = session.execute(
                select(PodDraftReplay).where(
                    PodDraftReplay.event_id == event_id,
                    PodDraftReplay.player_id == player_id,
                    PodDraftReplay.game_id == gid,
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(PodDraftReplay(
                    id=str(uuid4()),
                    event_id=event_id, player_id=player_id, game_id=gid,
                    link=full_link, game_time=gt,
                    won=bool(g.get("won")), turns=turns, on_play=on_play,
                    inferred_round=round_num,
                ))
                count += 1
            else:
                if existing.inferred_round != round_num:
                    existing.inferred_round = round_num
                    count += 1
        session.commit()
        return count


def _claimed_game_ids_for_player(
    session, player_id: str, event_time: datetime | None,
) -> frozenset[str]:
    """Game ids already stored for this player under a pod that started earlier. The earliest pod owns
    a game, so a player who drafts a second pod the same night doesn't get its ±6h window re-capturing
    the first pod's games."""
    if event_time is None:
        return frozenset()
    rows = session.execute(
        select(PodDraftReplay.game_id)
        .join(PodDraftEvent, PodDraftEvent.id == PodDraftReplay.event_id)
        .where(
            PodDraftReplay.player_id == player_id,
            PodDraftEvent.event_time < event_time,
        )
    ).scalars().all()
    return frozenset(rows)


def filter_and_sort_games(games: Sequence[dict]) -> list[dict]:
    out: list[tuple[datetime, dict]] = []
    for g in games:
        if g.get("event_name") not in POD_EVENT_NAMES:
            continue
        turns = g.get("turns")
        if not isinstance(turns, int) or turns < MIN_TURNS:
            continue
        gt = parse_game_time(g.get("game_time"))
        if gt is None:
            continue
        out.append((gt, g))
    out.sort(key=lambda x: x[0])
    return [g for _, g in out]


def is_in_event_window(game: dict, event_time: datetime | None) -> bool:
    if event_time is None:
        return True
    gt = parse_game_time(game.get("game_time"))
    if gt is None:
        return False
    delta = abs((gt - event_time).total_seconds()) / 3600.0
    return delta <= _EVENT_WINDOW_HOURS


def extract_game_id(game: dict) -> str | None:
    link = game.get("link") or ""
    parts = link.split("/")
    return parts[-2] if len(parts) >= 2 and parts[-2] else None


def parse_game_time(raw: str | None) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
