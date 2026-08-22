"""Dev-only PostgREST-shaped proxy over docker postgres. See spec/pod-draft-replays.md for setup."""
from __future__ import annotations

import asyncio
import datetime
import decimal
import json
import logging
import os
import re
from collections.abc import Iterable
from typing import Any

from aiohttp import web
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

from bot.models import DraftEvent, MagicSet, Player
from bot.services.refresh import refresh_player
from bot.services.seventeenlands import SeventeenLandsClient
from bot.services.tracker_detail import DRAFT_GAP_S, present_detail, summarise_draft


log = logging.getLogger(__name__)

_ALLOWED_VIEWS = {
    "public_color_events",
    "public_colors_summary",
    "public_cube_seasons",
    "public_cube_season_breakdown",
    "public_cube_season_events",
    "public_episodes",
    "public_leaderboard",
    "public_p0p1_pick_stats",
    "public_player",
    "public_player_draft_events",
    "public_player_format_breakdown",
    "public_player_pod_stats",
    "public_pod_draft_event_matches",
    "public_pod_draft_event_participants",
    "public_pod_draft_events",
    "public_pod_draft_log",
    "public_pod_draft_replays",
    "public_pod_scoring",
    "public_recent_trophies",
    "public_self_reported_events",
    "public_sets",
}

_OP_PATTERN = re.compile(r"^(eq|neq|lt|lte|gt|gte|like|ilike|in)\.(.+)$", re.DOTALL)

# Writable tracker tables and their primary keys. Prod scopes these with RLS on auth.uid();
# there is no auth here, so every row is forced onto one dev user
_TRACKER_TABLES = {
    "tracker_draft_notes": ("user_id", "draft_event_id"),
    "tracker_match_notes": ("user_id", "draft_event_id", "match_number"),
    "tracker_collection": ("user_id", "set_code", "card_name"),
    "tracker_set_economy": ("user_id", "set_code"),
}
DEV_USER_ID = "00000000-0000-4000-8000-000000000001"
# public_my_player_accounts scopes itself with auth.jwt(), which does not exist here,
# so serve the same shape for whichever player the dev identity points at
DEV_DISCORD_ID = os.environ.get("DEV_DISCORD_ID", "237762740532412416")
MY_ACCOUNTS_SQL = """
    SELECT p.slug, pa.id AS account_id, pa.name AS account_name, count(de.id) AS events
    FROM player_accounts pa
    JOIN players p ON p.id = pa.player_id
    LEFT JOIN draft_events de ON de.account_id = pa.id
    WHERE p.discord_id = :discord_id
    GROUP BY p.slug, pa.id, pa.name
    ORDER BY count(de.id) DESC
"""


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _build_where(query: Iterable[tuple[str, str]]) -> tuple[str, dict[str, Any]]:
    """Every pair is ANDed, so a column filtered twice (a date range) keeps both bounds"""
    clauses: list[str] = []
    params: dict[str, Any] = {}
    for key, raw in query:
        if key in {"select", "order", "limit", "offset"}:
            continue
        m = _OP_PATTERN.match(raw)
        if not m:
            continue
        op, value = m.group(1), m.group(2)
        if op == "in":
            items = value.strip()
            if items.startswith("(") and items.endswith(")"):
                items = items[1:-1]
            parts = [p.strip().strip('"') for p in items.split(",") if p.strip()]
            if not parts:
                continue
            binds = []
            for part in parts:
                bind = f"p{len(params)}"
                params[bind] = part
                binds.append(f":{bind}")
            clauses.append(f'"{key}" IN ({", ".join(binds)})')
            continue
        sql_op = {"eq": "=", "neq": "!=", "lt": "<", "lte": "<=", "gt": ">", "gte": ">=",
                  "like": "LIKE", "ilike": "ILIKE"}[op]
        bind = f"p{len(params)}"
        clauses.append(f'"{key}" {sql_op} :{bind}')
        params[bind] = value
    return (" AND ".join(clauses), params)


async def _handle_view(request: web.Request) -> web.Response:
    view = request.match_info["view"]
    if view in _TRACKER_TABLES:
        return await _handle_tracker(request, view)
    if view == "public_my_player_accounts":
        with request.app["engine"].connect() as conn:
            rows = conn.execute(text(MY_ACCOUNTS_SQL), {"discord_id": DEV_DISCORD_ID}).mappings().all()
        return web.Response(body=json.dumps([dict(r) for r in rows], default=_json_default),
                            content_type="application/json")
    if view not in _ALLOWED_VIEWS:
        return web.json_response({"error": f"view {view!r} not allowed"}, status=403)
    if request.method != "GET":
        return web.json_response({"error": f"{view!r} is read-only"}, status=405)

    engine = request.app["engine"]
    cols = request.query.get("select", "*")
    where_sql, params = _build_where(request.query.items())
    order = request.query.get("order")

    sql = f'SELECT {cols} FROM {view}'
    if where_sql:
        sql += f" WHERE {where_sql}"
    if order:
        col, _, direction = order.partition(".")
        direction = direction.upper() if direction.upper() in {"ASC", "DESC"} else "ASC"
        sql += f' ORDER BY "{col}" {direction}'
    limit = request.query.get("limit")
    if limit and limit.isdigit():
        sql += f" LIMIT {int(limit)}"
    # Without OFFSET a paging caller re-reads page one forever, so dropping it hangs the client
    offset = request.query.get("offset")
    if offset and offset.isdigit():
        sql += f" OFFSET {int(offset)}"

    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    body = json.dumps([dict(r) for r in rows], default=_json_default)
    return web.Response(body=body, content_type="application/json")


async def _handle_tracker(request: web.Request, table: str) -> web.Response:
    engine = request.app["engine"]
    pk = _TRACKER_TABLES[table]

    if request.method == "GET":
        where_sql, params = _build_where(request.query.items())
        sql = f'SELECT {request.query.get("select", "*")} FROM {table} WHERE "user_id" = :dev_user'
        params["dev_user"] = DEV_USER_ID
        if where_sql:
            sql += f" AND {where_sql}"
        with engine.connect() as conn:
            rows = conn.execute(text(sql), params).mappings().all()
        return web.Response(body=json.dumps([dict(r) for r in rows], default=_json_default),
                            content_type="application/json")

    if request.method == "DELETE":
        where_sql, params = _build_where(request.query.items())
        sql = f'DELETE FROM {table} WHERE "user_id" = :dev_user'
        params["dev_user"] = DEV_USER_ID
        if where_sql:
            sql += f" AND {where_sql}"
        with engine.begin() as conn:
            conn.execute(text(sql), params)
        return web.Response(status=204)

    payload = await request.json()
    rows = payload if isinstance(payload, list) else [payload]
    if not rows:
        return web.Response(status=204)

    with engine.begin() as conn:
        for row in rows:
            values = {**row, "user_id": DEV_USER_ID}
            cols = list(values)
            col_sql = ", ".join(f'"{c}"' for c in cols)
            bind_sql = ", ".join(f":{c}" for c in cols)
            updates = [c for c in cols if c not in pk]
            set_sql = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in updates)
            conflict_sql = ", ".join(f'"{c}"' for c in pk)
            sql = f"INSERT INTO {table} ({col_sql}) VALUES ({bind_sql}) ON CONFLICT ({conflict_sql}) "
            sql += f"DO UPDATE SET {set_sql}" if updates else "DO NOTHING"
            conn.execute(text(sql), values)
    return web.Response(status=204)


def _ingest_drafts(sessions: sessionmaker, set_code: str | None) -> int:
    """Pull the dev player's 17lands drafts into draft_events, returning how many rows are new"""
    with sessions() as session:
        player = session.execute(
            select(Player).where(Player.discord_id == DEV_DISCORD_ID)
        ).scalar_one_or_none()
        if player is None or not player.seventeenlands_token:
            return 0
        window = select(MagicSet.start_date).order_by(MagicSet.start_date.asc())
        known = (select(func.count()).select_from(DraftEvent)
                 .join(MagicSet, MagicSet.id == DraftEvent.set_id)
                 .where(DraftEvent.player_id == player.id))
        if set_code:
            window = window.where(MagicSet.code == set_code)
            known = known.where(MagicSet.code == set_code)
        before = session.execute(known).scalar_one()
        refresh_player(session, SeventeenLandsClient(), player,
                       fetch_start=session.execute(window).scalars().first())
        session.commit()
        return session.execute(known).scalar_one() - before


async def _handle_refresh(request: web.Request) -> web.Response:
    engine = request.app["engine"]
    set_code = request.query.get("set_code")
    event_id = request.query.get("event_id")
    force = request.query.get("force") == "1" or event_id is not None

    ingested = 0 if event_id else await asyncio.to_thread(_ingest_drafts, request.app["sessions"], set_code)

    where = "de.seventeenlands_event_id IS NOT NULL"
    params: dict[str, Any] = {"discord_id": DEV_DISCORD_ID}
    if event_id:
        where += " AND de.seventeenlands_event_id = :event_id"
        params["event_id"] = event_id
    if set_code:
        where += " AND s.code = :set_code"
        params["set_code"] = set_code
    if not force:
        # A draft whose deck fetch landed but whose match detail did not is still incomplete
        where += " AND (de.pool_rares IS NULL OR (de.match_results IS NULL AND de.wins + de.losses > 0))"

    with engine.connect() as conn:
        pending = conn.execute(text(f"""
            SELECT de.id, de.seventeenlands_event_id
            FROM draft_events de
            JOIN players p ON p.id = de.player_id
            JOIN sets s ON s.id = de.set_id
            WHERE p.discord_id = :discord_id AND {where}
            ORDER BY de.finished_at DESC NULLS LAST
        """), params).mappings().all()

    filled = missed = 0
    for index, row in enumerate(pending):
        if index:
            await asyncio.sleep(DRAFT_GAP_S)
        log.info(f"tracker refresh: draft {index + 1} of {len(pending)}")
        summary = await asyncio.to_thread(summarise_draft, row["seventeenlands_event_id"])
        if summary is None:
            missed += 1
            continue
        present = present_detail(summary)
        casts = {"deck_cards": "CAST(:deck_cards AS jsonb)", "match_results": "CAST(:match_results AS jsonb)"}
        assignments = ", ".join(f"{col} = {casts.get(col, f':{col}')}" for col in present)
        values = {col: json.dumps(present[col]) if col in casts else present[col] for col in present}
        params = {"id": row["id"], **values}
        with engine.begin() as conn:
            conn.execute(text(f"UPDATE draft_events SET {assignments} WHERE id = :id"), params)
        filled += 1

    return web.json_response({"ingested": ingested, "pending": len(pending), "filled": filled, "missed": missed})


@web.middleware
async def _cors_middleware(request: web.Request, handler):
    if request.method == "OPTIONS":
        resp = web.Response(status=204)
    else:
        resp = await handler(request)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    requested = request.headers.get("Access-Control-Request-Headers")
    resp.headers["Access-Control-Allow-Headers"] = requested or "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
    return resp


def _ensure_dev_user(engine) -> None:
    """Satisfy the tracker tables' foreign key when the local database carries a Supabase auth schema"""
    with engine.begin() as conn:
        has_auth = conn.execute(text(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'auth' AND table_name = 'users')"
        )).scalar()
        if has_auth:
            conn.execute(text("INSERT INTO auth.users (id) VALUES (:id) ON CONFLICT DO NOTHING"),
                         {"id": DEV_USER_ID})


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL is required (point at docker postgres)")

    app = web.Application(middlewares=[_cors_middleware])
    app["engine"] = create_engine(db_url)
    app["sessions"] = sessionmaker(bind=app["engine"], autoflush=False, autocommit=False)
    _ensure_dev_user(app["engine"])
    app.router.add_post("/tracker/refresh", _handle_refresh)
    app.router.add_route("OPTIONS", "/tracker/refresh", _handle_refresh)
    app.router.add_get("/rest/v1/{view}", _handle_view)
    app.router.add_post("/rest/v1/{view}", _handle_view)
    app.router.add_delete("/rest/v1/{view}", _handle_view)
    app.router.add_route("OPTIONS", "/rest/v1/{view}", _handle_view)

    log.info("local supabase proxy → docker postgres, listening on http://0.0.0.0:3001")
    log.info("set VITE_SUPABASE_URL=http://localhost:3001 in frontend/.env.local")
    web.run_app(app, host="0.0.0.0", port=3001, print=None)


if __name__ == "__main__":
    main()
