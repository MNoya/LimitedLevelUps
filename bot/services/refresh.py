"""Pull 17lands drafts and refresh derived aggregates.

``draft_events`` is the source of truth (additive, keyed on
``(player_id, seventeenlands_event_id)``). ``player_stats`` and the score
tables are derived — rebuilt from ``draft_events`` after each ingest.

Entry points:

* ``refresh_active_players`` — periodic + ``!refresh`` DM. Fetch window
  is ``min(today - PERIODIC_WINDOW_DAYS, ACTIVE_SET.start_date)``.
* ``refresh_active_players_all_sets`` — console-only full-history pull
  via ``bot/scripts/refresh_stats.py``. Used for formula changes, backfills,
  or suspected drift.
"""
from __future__ import annotations

import logging
import time as _time
from datetime import date, timedelta
from typing import Iterable, Protocol, Sequence

import requests
from sqlalchemy import delete, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from bot.models import (
    DraftEvent,
    MagicSet,
    Player,
    PlayerAccount,
    PlayerStats,
)
from bot.scoring import DEFAULT_QUEUE_GROUPS
from bot.services.active_set import resolve_active_set
from bot.services.seventeenlands import SUPPORTED_FORMATS, extract_event_row
from bot.sets import active_set_code, set_code_for_expansion

PERIODIC_WINDOW_DAYS = 7

TRANSIENT_COOLDOWN_S = 60.0
TRANSIENT_MAX_RETRIES = 2


logger = logging.getLogger(__name__)


class _DraftClient(Protocol):
    def fetch_drafts(self, token: str, start_date=..., end_date=..., expansion=...) -> list[dict]: ...


def _resolve_set_id(expansion: str, codes: list[str], sets_by_code: dict[str, MagicSet]) -> str | None:
    """The set an expansion belongs to: an explicit route first (the cube variants, whose raw
    17lands names stay on the event), then the first registered set whose code substring-matches."""
    routed = set_code_for_expansion(expansion)
    if routed is not None and routed in sets_by_code:
        return sets_by_code[routed].id
    for code in codes:
        if code in expansion:
            return sets_by_code[code].id
    return None


def _resolve_account_ids(session: Session, player_id: str, names: set[str]) -> dict[str, int]:
    """Map each 17lands account name to a ``player_accounts`` id, registering any new ones."""
    if not names:
        return {}
    session.execute(
        pg_insert(PlayerAccount)
        .values([{"player_id": player_id, "name": name} for name in names])
        .on_conflict_do_nothing(index_elements=["player_id", "name"])
    )
    pairs = session.execute(
        select(PlayerAccount.name, PlayerAccount.id).where(
            PlayerAccount.player_id == player_id, PlayerAccount.name.in_(names)
        )
    ).all()
    return {name: account_id for name, account_id in pairs}


def bulk_upsert_draft_events(
    session: Session,
    player_id: str,
    drafts: Iterable[dict],
    sets: Iterable[MagicSet],
) -> dict:
    """Persist every draft 17lands returned for one player. Single round-trip.

    Routes each draft to a registered set when expansion substring-matches;
    leaves ``set_id`` NULL otherwise (claimed later by ``/add-set``). Format is
    never filtered — unknown formats are persisted and reported so the owner
    can decide whether to add them to a ``QueueGroup``.

    Returns:
        ``{"touched_pairs": set[(player_id, set_id)],
           "unknown_formats": {fmt: count, ...},
           "unrouted_expansions": {expansion: count, ...},
           "events": int}``
    """
    sets_list = list(sets)
    sets_by_code = {s.code: s for s in sets_list}
    codes = list(sets_by_code.keys())

    rows: list[dict] = []
    touched_pairs: set[tuple[str, str]] = set()
    unknown_formats: dict[str, int] = {}
    unrouted_expansions: dict[str, int] = {}

    for draft in drafts:
        row = extract_event_row(draft)
        if row is None:
            continue
        set_id = _resolve_set_id(row["expansion"], codes, sets_by_code)
        row["player_id"] = player_id
        row["set_id"] = set_id

        rows.append(row)

        if set_id is None:
            unrouted_expansions[row["expansion"]] = unrouted_expansions.get(row["expansion"], 0) + 1
        else:
            touched_pairs.add((player_id, set_id))

        fmt = row["format"]
        if fmt not in SUPPORTED_FORMATS and not fmt.startswith("MidWeek"):
            unknown_formats[fmt] = unknown_formats.get(fmt, 0) + 1

    account_ids = _resolve_account_ids(session, player_id, {r["account"] for r in rows if r["account"]})
    for row in rows:
        row["account_id"] = account_ids.get(row.pop("account"))

    if rows:
        stmt = pg_insert(DraftEvent).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["player_id", "seventeenlands_event_id"],
            set_={
                "set_id": stmt.excluded.set_id,
                "format": stmt.excluded.format,
                "expansion": stmt.excluded.expansion,
                "wins": stmt.excluded.wins,
                "losses": stmt.excluded.losses,
                "is_trophy": stmt.excluded.is_trophy,
                "colors": stmt.excluded.colors,
                "account_id": stmt.excluded.account_id,
                "start_rank": stmt.excluded.start_rank,
                "end_rank": stmt.excluded.end_rank,
                "started_at": stmt.excluded.started_at,
                "finished_at": stmt.excluded.finished_at,
                "fetched_at": func.now(),
            },
        )
        session.execute(stmt)

    return {
        "touched_pairs": touched_pairs,
        "unknown_formats": unknown_formats,
        "unrouted_expansions": unrouted_expansions,
        "events": len(rows),
    }


def refresh_player(
    session: Session,
    client: _DraftClient,
    player: Player,
    drafts: list[dict] | None = None,
    fetch_start: date | None = None,
) -> dict:
    if drafts is None:
        try:
            drafts = client.fetch_drafts(
                player.seventeenlands_token,
                start_date=fetch_start,
            )
        except requests.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else None
            if status_code == 404:
                player.token_invalid = True
                return {"status": "invalidated"}
            if status_code == 403:
                logger.warning(f"refresh: rate limited (403) for player {player.id}")
                return {"status": "transient", "error": str(e)}
            logger.warning(f"refresh: HTTP error for player {player.id}: {e}")
            return {"status": "error", "error": str(e)}
        except ValueError as e:
            # Signup verifies tokens, so a malformed 200 is a 17lands-side issue, not a bad token
            logger.warning(f"refresh: malformed response for player {player.id}: {e}")
            return {"status": "error", "error": str(e)}
        except requests.Timeout as e:
            logger.warning(f"refresh: timeout for player {player.id}: {e}")
            return {"status": "error", "error": str(e)}
        except requests.ConnectionError as e:
            logger.warning(f"refresh: connection dropped for player {player.id}: {e}")
            return {"status": "transient", "error": str(e)}
        except requests.RequestException as e:
            logger.warning(f"refresh: network error for player {player.id}: {e}")
            return {"status": "error", "error": str(e)}

    sets = session.execute(select(MagicSet)).scalars().all()

    upsert = bulk_upsert_draft_events(session, player.id, drafts, sets)
    touched_set_ids = {set_id for (_pid, set_id) in upsert["touched_pairs"]}

    active_code = active_set_code()
    active = next((s for s in sets if s.code == active_code), None)
    if active is not None:
        touched_set_ids.add(active.id)

    session.flush()
    for set_id in touched_set_ids:
        rebuild_player_stats(session, player.id, set_id)

    return {
        "status": "updated",
        "events": upsert["events"],
        "rows": len(touched_set_ids),
        "unknown_formats": upsert["unknown_formats"],
        "unrouted_expansions": upsert["unrouted_expansions"],
    }


def claim_orphan_drafts(
    session: Session,
    magic_set: MagicSet,
    expansion_alias: str | None = None,
    expansion_matches: Sequence[str] = (),
) -> set[str]:
    """Attach unrouted ``draft_events`` rows to ``magic_set`` when their expansion now matches.

    Run this after adding a set to ``bot/sets.py`` (and seeding it). Returns
    the set of player_ids that gained events, so the caller can rebuild
    ``player_stats`` and scores for each.

    Match rule mirrors the ingest path: an exact ``expansion_matches`` name, or ``magic_set.code``
    as a substring of the expansion. A row ingested before its ``expansion_alias`` existed still
    holds the raw 17lands string (``OM1`` for SPM), so the alias is rewritten to the code first,
    restoring the invariant and letting the substring claim pick it up.
    """
    if expansion_alias is not None:
        session.execute(
            text("UPDATE draft_events SET expansion = :code WHERE set_id IS NULL AND expansion = :alias"),
            {"code": magic_set.code, "alias": expansion_alias},
        )

    matches = list(expansion_matches)
    criteria = DraftEvent.expansion.contains(magic_set.code)
    if matches:
        criteria = or_(criteria, DraftEvent.expansion.in_(matches))

    affected = session.execute(
        select(DraftEvent.player_id).where(DraftEvent.set_id.is_(None), criteria).distinct()
    ).scalars().all()

    session.execute(
        update(DraftEvent)
        .where(DraftEvent.set_id.is_(None), criteria)
        .values(set_id=magic_set.id, fetched_at=func.now())
    )
    session.expire_all()  # raw UPDATE bypassed the identity map
    return set(affected)


def rebuild_player_stats(session: Session, player_id: str, set_id: str) -> int:
    """Rebuild ``player_stats`` for one (player, set) from ``draft_events``.

    Source of truth for aggregates is ``draft_events``; this DELETE+INSERT-FROM-SELECT
    keeps the derived table fully consistent and is the only safe way to recompute
    after a partial-window fetch. Returns the row count written.
    """
    session.execute(
        delete(PlayerStats).where(
            PlayerStats.player_id == player_id,
            PlayerStats.set_id == set_id,
        )
    )
    result = session.execute(
        text(
            f"""
            INSERT INTO player_stats
                (id, player_id, set_id, format, expansion, events, wins, losses, games_played,
                 trophies, weighted_trophies, last_fetched_at)
            SELECT gen_random_uuid()::text, player_id, set_id, format, expansion,
                   COUNT(*)::int, SUM(wins)::int, SUM(losses)::int, SUM(wins + losses)::int,
                   SUM(CASE WHEN is_trophy THEN 1 ELSE 0 END)::int,
                   SUM(CASE WHEN is_trophy THEN {trophy_weight_sql()} ELSE 0 END),
                   now()
            FROM draft_events
            WHERE player_id = :pid AND set_id = :sid
            GROUP BY player_id, set_id, format, expansion
            """
        ),
        {"pid": player_id, "sid": set_id},
    )
    return result.rowcount or 0


def trophy_weight_sql(format_column: str = "format", rank_column: str = "end_rank") -> str:
    """SQL for one trophy's rank weight, built from the groups that carry ``rank_points``.

    Generated off ``scoring_buckets.json`` so the weights have one source of truth rather than a
    copy frozen into a migration. Formats in no weighted group, and events 17lands gave no rank,
    fall through to 1.0.
    """
    branches = []
    for group in DEFAULT_QUEUE_GROUPS:
        if not group.rank_points:
            continue
        formats = ", ".join(f"'{fmt}'" for fmt in group.formats)
        tiers = " ".join(
            f"WHEN '{tier}' THEN {group.trophy_weight(tier)}" for tier in group.rank_points
        )
        branches.append(
            f"WHEN {format_column} IN ({formats}) THEN "
            f"CASE split_part(COALESCE({rank_column}, ''), '-', 1) {tiers} ELSE 1.0 END"
        )
    if not branches:
        return "1.0"
    return f"CASE {' '.join(branches)} ELSE 1.0 END"


def refresh_one_player_for_all_sets(session: Session, client: _DraftClient, player_id: str) -> dict:
    """Refresh a single player across every registered set in one 17lands fetch."""
    player = session.execute(select(Player).where(Player.id == player_id)).scalar_one_or_none()
    if player is None:
        return {"status": "no_player"}
    sets = session.execute(select(MagicSet).order_by(MagicSet.start_date.asc())).scalars().all()
    if not sets:
        return {"status": "no_sets"}
    return refresh_player(session, client, player, fetch_start=sets[0].start_date)


def refresh_active_players(session: Session, client: _DraftClient) -> dict:
    """Periodic refresh. Window: ``max(today - PERIODIC_WINDOW_DAYS, ACTIVE_SET.start_date)`` so a fresh
    rotation doesn't widen the fetch. Flashback drafts in that window route to their own set's rows.
    """
    active = resolve_active_set(session)
    if active is None:
        return {
            "updated": 0, "invalidated": 0, "errors": 0,
            "invalidated_players": [], "per_player": [], "unknown_formats": {},
            "unrouted_expansions": {}, "elapsed_s": 0.0,
            "status": "no_active_set",
        }
    fetch_start = min(date.today() - timedelta(days=PERIODIC_WINDOW_DAYS), active.start_date)
    summary = _refresh_active_with_window(session, client, fetch_start)
    active.last_refreshed_at = func.now()
    session.commit()
    refresh_public_matviews(session, ingested_rows=summary["events"] > 0)
    return summary


def refresh_active_players_all_sets(session: Session, client: _DraftClient) -> dict:
    """Full-history rebuild from the earliest registered set. Expensive — used by ``!refresh`` and the seed
    script when schema or scoring logic changes; not the scheduled tick.
    """
    sets = session.execute(select(MagicSet).order_by(MagicSet.start_date.asc())).scalars().all()
    if not sets:
        return {
            "updated": 0, "invalidated": 0, "errors": 0,
            "invalidated_players": [], "per_player": [], "unknown_formats": {},
            "unrouted_expansions": {}, "elapsed_s": 0.0,
            "status": "no_sets",
        }
    summary = _refresh_active_with_window(session, client, sets[0].start_date)
    session.execute(text(
        "UPDATE sets SET last_refreshed_at = now() "
        "WHERE EXISTS (SELECT 1 FROM player_stats ps WHERE ps.set_id = sets.id)"
    ))
    session.commit()
    refresh_public_matviews(session, ingested_rows=summary["events"] > 0)
    return summary


PUBLIC_MATVIEWS = ("public_cube_seasons", "public_colors_summary")


def refresh_public_matviews(session: Session, ingested_rows: bool = True) -> None:
    """Recompute the matviews the site reads on load, unless the run ingested nothing.

    A REFRESH rebuilds the whole view, so a tick that wrote no events rebuilds tallies that cannot
    have moved. Most scheduled ticks are that case, and much of what they rebuild is frozen history:
    the original Arena Cube has not been played since 2025 and still costs a full recompute. Callers
    that cannot tell pass nothing and keep the unconditional behaviour.
    """
    if not ingested_rows:
        return
    for name in PUBLIC_MATVIEWS:
        _refresh_matview(session, name)


def _refresh_matview(session: Session, name: str) -> None:
    """CONCURRENTLY keeps the view readable during the refresh; it needs the unique index the
    matview's migration creates. The guard lets the model-built test schema, which has no public_*
    objects, run the refresh path as a no-op.
    """
    if session.execute(text(f"SELECT to_regclass('public.{name}')")).scalar() is None:
        return
    session.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {name}"))
    session.commit()


def _refresh_player_retrying_transient(
    session: Session, client: _DraftClient, player: Player, fetch_start: date, idx: int, n_total: int
) -> dict:
    """Refresh one player, treating 403s and dropped connections as a run-wide cooldown signal.

    17lands sheds load after a sustained run by throttling the connection — a 403 or an abruptly
    closed socket — not by rejecting a single token, so either means pause the whole sequential run
    and retry rather than skip the player. Exhausted retries fall through as an error so the player
    can recover on the next tick.
    """
    for attempt in range(TRANSIENT_MAX_RETRIES + 1):
        result = refresh_player(session, client, player, fetch_start=fetch_start)
        if result.get("status") != "transient":
            return result
        if attempt == TRANSIENT_MAX_RETRIES:
            logger.warning(f"refresh: [{idx}/{n_total}] still failing after {attempt} retries, skipping")
            return {"status": "error", "error": result.get("error", "transient failure")}
        logger.warning(
            f"refresh: transient failure at [{idx}/{n_total}], pausing {TRANSIENT_COOLDOWN_S:.0f}s before retry"
        )
        _time.sleep(TRANSIENT_COOLDOWN_S)
    return result


def _refresh_active_with_window(session: Session, client: _DraftClient, fetch_start: date) -> dict:
    players = session.execute(
        select(Player).where(
            Player.active.is_(True),
            Player.token_invalid.is_(False),
            Player.seventeenlands_token.isnot(None),
        )
    ).scalars().all()

    summary: dict = {
        "updated": 0,
        "invalidated": 0,
        "errors": 0,
        "events": 0,
        "invalidated_players": [],
        "per_player": [],
        "unknown_formats": {},
        "unrouted_expansions": {},
        "elapsed_s": 0.0,
    }
    n_total = len(players)
    logger.info(f"refresh: {n_total} active player(s), fetch_start={fetch_start}")
    t_total = _time.monotonic()
    for idx, player in enumerate(players, start=1):
        t0 = _time.monotonic()
        result = _refresh_player_retrying_transient(session, client, player, fetch_start, idx, n_total)
        # Commit per-player so a mid-run crash keeps fetched data and the token_invalid flag persists
        session.commit()
        elapsed = _time.monotonic() - t0
        status = result.get("status") or "error"
        if status == "updated":
            summary["updated"] += 1
        elif status == "invalidated":
            summary["invalidated"] += 1
            summary["invalidated_players"].append(player.id)
        else:
            summary["errors"] += 1
        for fmt, count in (result.get("unknown_formats") or {}).items():
            summary["unknown_formats"][fmt] = summary["unknown_formats"].get(fmt, 0) + count
        for exp, count in (result.get("unrouted_expansions") or {}).items():
            summary["unrouted_expansions"][exp] = summary["unrouted_expansions"].get(exp, 0) + count
        events_count = result.get("events", 0)
        summary["events"] += events_count
        extra = "" if status == "updated" else f" ({result.get('error', '')})".rstrip()
        logger.info(
            f"refresh: [{idx}/{n_total}] {player.display_name} "
            f"status={status} events={events_count} {elapsed:.1f}s{extra}"
        )
        summary["per_player"].append({
            "display_name": player.display_name,
            "status": status,
            "seconds": round(elapsed, 2),
        })
    summary["elapsed_s"] = round(_time.monotonic() - t_total, 2)
    logger.info(
        f"refresh: done. updated={summary['updated']} "
        f"invalidated={summary['invalidated']} errors={summary['errors']} "
        f"elapsed={summary['elapsed_s']:.1f}s "
        f"unknown_formats={summary['unknown_formats'] or '{}'} "
        f"unrouted_expansions={summary['unrouted_expansions'] or '{}'}"
    )
    return summary
