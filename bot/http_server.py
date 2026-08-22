"""Owner-only HTTP endpoint the tracker calls to pull fresh 17lands detail on demand.

Runs inside the bot process on Railway's ``$PORT``. The site sends the signed-in user's Supabase
access token; this validates it against Supabase, gates on the tracker allowlist, and refreshes only
that user's own drafts. Every write is public draft data, so the token check exists to stop spoofed
triggers, not to protect secrets.
"""
from __future__ import annotations

import asyncio
import logging
import os

import aiohttp
from aiohttp import web
from sqlalchemy import select

from bot.config import settings
from bot.database import SessionLocal
from bot.models import MagicSet, Player
from bot.services.active_set import resolve_active_set
from bot.services.refresh import refresh_player
from bot.services.seventeenlands import SeventeenLandsClient
from bot.services.tracker_detail import fill_pending_draft_detail, is_tracker_player, refetch_draft_detail

log = logging.getLogger(__name__)


def _cors_headers() -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": settings.public_site_url,
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "authorization, content-type",
        "Access-Control-Max-Age": "86400",
    }


async def _discord_id_for_token(token: str) -> str | None:
    url = f"{settings.supabase_url.rstrip('/')}/auth/v1/user"
    headers = {"Authorization": f"Bearer {token}", "apikey": settings.supabase_anon_key}
    try:
        async with aiohttp.ClientSession() as http:
            async with http.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return None
                user = await resp.json()
    except Exception:
        log.warning("tracker refresh: token validation failed", exc_info=True)
        return None
    meta = user.get("user_metadata") or {}
    if meta.get("provider_id"):
        return str(meta["provider_id"])
    for identity in user.get("identities") or []:
        pid = identity.get("provider_id") or (identity.get("identity_data") or {}).get("provider_id")
        if pid:
            return str(pid)
    return None


def _run_refresh(discord_id: str, set_code: str | None, event_id: str | None) -> dict:
    with SessionLocal() as session:
        player = session.execute(
            select(Player).where(Player.discord_id == discord_id)
        ).scalar_one_or_none()
        if player is None or not player.seventeenlands_token:
            return {"ingested": 0, "filled": 0, "missed": 0}

        if event_id:
            written = refetch_draft_detail(session, player.id, event_id)
            return {"ingested": 0, "filled": int(written), "missed": int(not written)}

        code = set_code or (resolve_active_set(session).code if resolve_active_set(session) else None)
        start = session.execute(select(MagicSet.start_date).where(MagicSet.code == code)).scalar_one_or_none()
        before = refresh_player(session, SeventeenLandsClient(), player, fetch_start=start)
        session.commit()
        result = fill_pending_draft_detail(session, player.id, set_code=code, cap=None)
        return {"ingested": before.get("events", 0), "filled": result["filled"], "missed": result["missed"]}


async def _handle_refresh(request: web.Request) -> web.Response:
    auth = request.headers.get("Authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    if not token:
        return web.json_response({"error": "missing token"}, status=401, headers=_cors_headers())

    discord_id = await _discord_id_for_token(token)
    if not is_tracker_player(discord_id):
        return web.json_response({"error": "forbidden"}, status=403, headers=_cors_headers())

    set_code = request.query.get("set_code")
    event_id = request.query.get("event_id")
    result = await asyncio.to_thread(_run_refresh, discord_id, set_code, event_id)
    return web.json_response(result, headers=_cors_headers())


async def _handle_options(request: web.Request) -> web.Response:
    return web.Response(status=204, headers=_cors_headers())


async def start_tracker_http_server() -> web.AppRunner | None:
    """Bind the tracker refresh endpoint when a port is set"""
    raw_port = settings.tracker_http_port or os.environ.get("PORT")
    if not raw_port:
        log.info("tracker HTTP server: no port set, not starting (dev uses the local proxy)")
        return None
    app = web.Application()
    app.router.add_post("/tracker/refresh", _handle_refresh)
    app.router.add_route("OPTIONS", "/tracker/refresh", _handle_options)
    app.router.add_get("/health", lambda _r: web.json_response({"ok": True}))
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(raw_port)
    await web.TCPSite(runner, "0.0.0.0", port).start()
    log.info(f"tracker HTTP server listening on :{port}")
    return runner
