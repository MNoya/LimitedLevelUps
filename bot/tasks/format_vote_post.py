"""Opens the flashback format vote in pod chat and reminds the players who have not voted, on the vote's own dates.

One tick a day at the ballot hour, plus a pass at startup so a deploy across either instant still lands its post.
The pinned card and the reminder's role mention keep each to one post.
"""
from __future__ import annotations

import logging
from datetime import datetime

from discord.ext import commands

from bot.config import settings
from bot.discord_helpers import resolve_pod_chat_channel
from bot.services.championship_dates import BALLOT_OPENS_AT, vote_ping_due, vote_reminder_due
from bot.services.pod_format_vote import post_vote_card, post_vote_reminder, vote_ping_text
from bot.services.pod_schedule import SCHEDULE_TZ

log = logging.getLogger(__name__)

_bot: commands.Bot | None = None


def init_format_vote(bot: commands.Bot) -> None:
    global _bot
    _bot = bot
    if not settings.pod_schedule_enabled:
        log.info("POD_SCHEDULE_ENABLED=false; format vote tick disabled")
        return
    bot.pod_scheduler.add_job(
        fire_format_vote_tick, "cron", hour=BALLOT_OPENS_AT.hour, minute=BALLOT_OPENS_AT.minute,
        timezone=SCHEDULE_TZ, id="format-vote-tick", replace_existing=True,
    )
    log.info(f"format vote tick armed at {BALLOT_OPENS_AT:%H:%M} {SCHEDULE_TZ.key}")


async def fire_format_vote_tick() -> None:
    if _bot is None or not settings.pod_schedule_enabled:
        return
    now = datetime.now(SCHEDULE_TZ)
    opening = vote_ping_due(now)
    reminding = vote_reminder_due(now)
    if opening is None and reminding is None:
        return
    channel = resolve_pod_chat_channel(_bot)
    if channel is None:
        log.warning("format vote: no pod chat channel; skipping tick")
        return
    if opening is not None:
        await post_vote_card(channel, vote_ping_text(channel.guild))
    if reminding is not None:
        outcome = await post_vote_reminder(channel)
        if outcome is not None:
            log.info(f"format vote: {reminding.set_code} reminder pinged {outcome.pinged}/{outcome.targeted}")
            await _post_debug(reminding.set_code, outcome.pinged, outcome.targeted)


async def _post_debug(set_code: str, pinged: int, targeted: int) -> None:
    """The role is emptied after the ping, so this is the only record of who was reached"""
    bot_log = getattr(_bot, "bot_log", None)
    if bot_log is None:
        return
    await bot_log.post(f"Flashback vote reminder for `{set_code}` pinged **{pinged}** of {targeted} in pod chat",
                       tag="VOTE", fingerprint=f"format-vote-reminder-{set_code}")
