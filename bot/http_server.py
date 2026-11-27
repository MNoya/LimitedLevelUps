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
import time

import aiohttp
from aiohttp import web
from discord.ext import commands

from bot.config import is_admin, settings
from bot.database import SessionLocal
from bot.commands.authorization import deck_staff_authorized
from bot.services.pod_deck_correction import owned_seats, save_deck_edit
from bot.services.tracker_detail import is_tracker_player, run_tracker_refresh
from bot.services.transcript_cards import apply_transcript_edit

log = logging.getLogger(__name__)

_verified_tokens: dict[str, tuple[str, float]] = {}


def _cors_headers() -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": settings.public_site_url,
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
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
        return run_tracker_refresh(session, discord_id, set_code, event_id)


async def _handle_refresh(request: web.Request) -> web.Response:
    discord_id = await _require_user(request)
    if isinstance(discord_id, web.Response):
        return discord_id
    if not is_tracker_player(discord_id):
        return web.json_response({"error": "forbidden"}, status=403, headers=_cors_headers())

    set_code = request.query.get("set_code")
    event_id = request.query.get("event_id")
    result = await asyncio.to_thread(_run_refresh, discord_id, set_code, event_id)
    return web.json_response(result, headers=_cors_headers())


async def _cached_discord_id_for_token(token: str) -> str | None:
    now = time.monotonic()
    cached = _verified_tokens.get(token)
    if cached and cached[1] > now:
        return cached[0]
    discord_id = await _discord_id_for_token(token)
    if discord_id:
        for stale in [t for t, (_, expires) in _verified_tokens.items() if expires <= now]:
            del _verified_tokens[stale]
        _verified_tokens[token] = (discord_id, now + 300)
    return discord_id


async def _handle_options(request: web.Request) -> web.Response:
    return web.Response(status=204, headers=_cors_headers())


async def _require_user(request: web.Request) -> str | web.Response:
    auth = request.headers.get("Authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    discord_id = await _cached_discord_id_for_token(token) if token else None
    if not discord_id:
        return web.json_response({"error": "not signed in"}, status=401, headers=_cors_headers())
    return discord_id


async def _require_admin(request: web.Request) -> str | web.Response:
    discord_id = await _require_user(request)
    if isinstance(discord_id, web.Response):
        return discord_id
    if not is_admin(discord_id):
        return web.json_response({"error": "forbidden"}, status=403, headers=_cors_headers())
    return discord_id


def _save_transcript(key: str, incoming: list[dict]) -> tuple[str, int] | list[dict]:
    with SessionLocal() as session:
        return apply_transcript_edit(session, key, incoming)


async def _handle_transcript_edit(request: web.Request) -> web.Response:
    admin = await _require_admin(request)
    if isinstance(admin, web.Response):
        return admin
    try:
        incoming = await request.json()
    except Exception:
        return web.json_response({"error": "invalid body"}, status=400, headers=_cors_headers())
    if not isinstance(incoming, list):
        return web.json_response({"error": "expected a segments array"}, status=400, headers=_cors_headers())
    result = await asyncio.to_thread(_save_transcript, request.match_info["key"], incoming)
    if isinstance(result, tuple):
        message, status = result
        return web.json_response({"error": message}, status=status, headers=_cors_headers())
    return web.json_response({"ok": True, "segments": result}, headers=_cors_headers())


def _deck_target(request: web.Request) -> tuple[str, int]:
    return request.match_info["event_id"], int(request.match_info["seat"])


def _owned_seats(event_id: str, discord_id: str) -> list[int]:
    with SessionLocal() as session:
        return owned_seats(session, event_id, discord_id)


async def _handle_deck_access(request: web.Request) -> web.Response:
    user = await _require_user(request)
    if isinstance(user, web.Response):
        return user
    staff = deck_staff_authorized(request.app["bot"], user)
    seats = [] if staff else await asyncio.to_thread(_owned_seats, request.match_info["event_id"], user)
    return web.json_response({"staff": staff, "seats": seats}, headers=_cors_headers())


def _save_deck(event_id: str, seat: int, incoming: object, editor: str, staff: bool) -> dict | tuple[str, int]:
    with SessionLocal() as session:
        return save_deck_edit(session, event_id, seat, incoming, editor, staff)


async def _handle_deck_edit(request: web.Request) -> web.Response:
    user = await _require_user(request)
    if isinstance(user, web.Response):
        return user
    try:
        incoming = await request.json()
    except Exception:
        return web.json_response({"error": "invalid body"}, status=400, headers=_cors_headers())
    event_id, seat = _deck_target(request)
    staff = deck_staff_authorized(request.app["bot"], user)
    result = await asyncio.to_thread(_save_deck, event_id, seat, incoming, user, staff)
    if isinstance(result, tuple):
        message, status = result
        return web.json_response({"error": message}, status=status, headers=_cors_headers())
    log.info(f"deck edit: {user} saved seat {seat} of pod {event_id}")
    return web.json_response({"ok": True, **result}, headers=_cors_headers())


async def start_tracker_http_server(bot: commands.Bot) -> web.AppRunner | None:
    """Bind the tracker refresh endpoint when a port is set"""
    raw_port = settings.tracker_http_port or os.environ.get("PORT")
    if not raw_port:
        log.info("tracker HTTP server: no port set, not starting (dev uses the local proxy)")
        return None
    app = web.Application()
    app["bot"] = bot
    app.router.add_post("/tracker/refresh", _handle_refresh)
    app.router.add_route("OPTIONS", "/tracker/refresh", _handle_options)
    app.router.add_post("/episodes/{key}/transcript", _handle_transcript_edit)
    app.router.add_route("OPTIONS", "/episodes/{key}/transcript", _handle_options)
    app.router.add_post("/pods/{event_id}/decks/{seat:\\d+}", _handle_deck_edit)
    app.router.add_route("OPTIONS", "/pods/{event_id}/decks/{seat:\\d+}", _handle_options)
    app.router.add_get("/pods/{event_id}/decks/access", _handle_deck_access)
    app.router.add_route("OPTIONS", "/pods/{event_id}/decks/access", _handle_options)
    app.router.add_get("/health", lambda _r: web.json_response({"ok": True}))
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(raw_port)
    await web.TCPSite(runner, "0.0.0.0", port).start()
    log.info(f"tracker HTTP server listening on :{port}")
    return runner
