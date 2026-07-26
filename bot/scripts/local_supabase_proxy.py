"""Dev-only PostgREST-shaped proxy over docker postgres. See spec/pod-draft-replays.md for setup."""
from __future__ import annotations

import datetime
import decimal
import json
import logging
import os
import re
from typing import Any

from aiohttp import web
from sqlalchemy import create_engine, text


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


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _build_where(query: dict[str, str]) -> tuple[str, dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    for key, raw in query.items():
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
    if view not in _ALLOWED_VIEWS:
        return web.json_response({"error": f"view {view!r} not allowed"}, status=403)

    engine = request.app["engine"]
    cols = request.query.get("select", "*")
    where_sql, params = _build_where(dict(request.query))
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


@web.middleware
async def _cors_middleware(request: web.Request, handler):
    if request.method == "OPTIONS":
        resp = web.Response(status=204)
    else:
        resp = await handler(request)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    requested = request.headers.get("Access-Control-Request-Headers")
    resp.headers["Access-Control-Allow-Headers"] = requested or "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    return resp


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL is required (point at docker postgres)")

    app = web.Application(middlewares=[_cors_middleware])
    app["engine"] = create_engine(db_url)
    app.router.add_get("/rest/v1/{view}", _handle_view)
    app.router.add_route("OPTIONS", "/rest/v1/{view}", _handle_view)

    log.info("local supabase proxy → docker postgres, listening on http://0.0.0.0:3001")
    log.info("set VITE_SUPABASE_URL=http://localhost:3001 in frontend/.env.local")
    web.run_app(app, host="0.0.0.0", port=3001, print=None)


if __name__ == "__main__":
    main()
