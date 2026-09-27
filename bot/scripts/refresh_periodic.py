"""Standalone periodic 17lands refresh, run as a Railway cron service.

Decoupled from the bot process so a bot deploy can't interrupt a refresh in flight.
Same windowed logic as the in-bot tick (``refresh_active_players``); posts the report
to bot-spam and DMs newly-invalidated players, both via Discord REST using the bot
token, since this process has no live gateway connection.

    DATABASE_URL=... DISCORD_BOT_TOKEN=... DISCORD_BOTLOG_CHANNEL_ID=... \
        python -m bot.scripts.refresh_periodic
"""
from __future__ import annotations

import logging

from sqlalchemy import select

from bot.commands.messages import MSG_TOKEN_INVALIDATED
from bot.config import settings
from bot.database import SessionLocal
from bot.models import Player
from bot.services.card_stats import refresh_live_card_stats_if_configured
from bot.services.discord_rest import DiscordRest
from bot.services.refresh import refresh_active_players
from bot.services.refresh_report import build_refresh_report
from bot.services.seventeenlands import MinIntervalLimiter, SeventeenLandsClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("refresh_periodic")

REFRESH_17L_INTERVAL_S = 7.0


def main() -> None:
    if settings.discord_bot_token is None:
        raise SystemExit("DISCORD_BOT_TOKEN must be set for the refresh cron job")

    client = SeventeenLandsClient(limiter=MinIntervalLimiter(min_interval_s=REFRESH_17L_INTERVAL_S))
    refresh_live_card_stats_if_configured(client, settings)
    with SessionLocal() as session:
        log.info("starting periodic refresh (windowed)")
        summary = refresh_active_players(session, client)
        invalidated = _load_invalidated(session, summary.get("invalidated_players", []))

    rest = DiscordRest(settings.discord_bot_token.get_secret_value())
    _post_report(rest, summary)
    for player in invalidated:
        _notify_invalidated(rest, player)

    log.info(
        f"done. updated={summary.get('updated')} invalidated={summary.get('invalidated')} "
        f"errors={summary.get('errors')}"
    )


def _load_invalidated(session, player_ids: list) -> list[Player]:
    if not player_ids:
        return []
    players = list(session.execute(select(Player).where(Player.id.in_(player_ids))).scalars().all())
    for player in players:
        session.expunge(player)
    return players


def _post_report(rest: DiscordRest, summary: dict) -> None:
    if settings.discord_botlog_channel_id is None:
        return
    rest.post_channel_message(settings.discord_botlog_channel_id, build_refresh_report(summary, "auto"))


def _notify_invalidated(rest: DiscordRest, player: Player) -> None:
    if not player.discord_id:
        return
    dmed = rest.send_dm(int(player.discord_id), MSG_TOKEN_INVALIDATED)
    if settings.discord_botlog_channel_id is None:
        return
    status = "DMed" if dmed else "DM failed"
    copy = f"🔑 Token invalidated — **{player.display_name}** ({status}):\n{MSG_TOKEN_INVALIDATED}"
    rest.post_channel_message(settings.discord_botlog_channel_id, copy)


if __name__ == "__main__":
    main()
