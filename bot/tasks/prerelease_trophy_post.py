from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta

import discord
from discord.ext import commands

from bot import audit, emojis
from bot.commands.trophy import PLATFORM_EMOJI_NAME
from bot.config import settings
from bot.discord_helpers import channel_matching_name, message_text
from bot.services.containers import as_view, build_container
from bot.services.format_schedule import OPEN_TZ
from bot.services.mock_lobby_card import set_symbol_url
from bot.sets import ALL_SETS, SetSeed, prerelease_friday

log = logging.getLogger(__name__)

POST_TIME = time(8, 0)
PRERELEASE_LABEL = "Prerelease"
MSG_HEADER = "## 🏆 Save your {label} Decks!"
MSG_BODY = (
    "Type `/trophy` to record a deck on your [**Limited Level-Ups profile**]({profile_url}) {llu}\n\n"
    "or right-click and select **Apps →** {bot_mention} **→ 🏆 Record Event**\n\n"
    "-# works for any {paper} Tabletop event, {mtgo} MTGO or other platforms"
)

_bot: commands.Bot | None = None


def init_prerelease_trophy_post(bot: commands.Bot) -> None:
    global _bot
    _bot = bot
    bot.pod_scheduler.add_job(
        fire_prerelease_post, "cron", hour=f"{POST_TIME.hour}-20", minute=POST_TIME.minute,
        timezone=OPEN_TZ, id="prerelease-trophy-post", replace_existing=True,
    )
    log.info(f"prerelease-trophy: hourly tick armed from {POST_TIME:%H:%M} {OPEN_TZ.key} on prerelease Fridays")


async def fire_prerelease_post() -> None:
    if _bot is None or _bot.user is None:
        return
    today = datetime.now(OPEN_TZ).date()
    seed = prerelease_set_on(today)
    if seed is None:
        return
    guild = _bot.get_guild(settings.discord_guild_id) if settings.discord_guild_id else None
    if guild is None:
        log.warning("prerelease-trophy: no configured guild, skipping")
        return
    channel = channel_matching_name(guild, settings.pod_draft_trophy_hype_channel_name)
    if channel is None:
        log.warning(f"prerelease-trophy: no {settings.pod_draft_trophy_hype_channel_name} channel, skipping")
        return
    try:
        if await _already_posted(channel, _bot.user, today):
            return
        await send_trophy_card(channel, seed.code, _bot.user, PRERELEASE_LABEL)
    except discord.HTTPException:
        log.warning(f"prerelease-trophy: {seed.code} post failed, retrying next hour", exc_info=True)
        return
    audit.event("prerelease_trophy_post", set=seed.code, channel_id=str(channel.id))
    log.info(f"prerelease-trophy: posted the {seed.code} reminder in #{channel.name}")


def prerelease_set_on(day: date) -> SetSeed | None:
    for seed in ALL_SETS:
        if prerelease_friday(seed) == day:
            return seed
    return None


async def send_trophy_card(
    channel: discord.abc.Messageable, set_code: str, bot_user: discord.ClientUser, label: str
) -> None:
    header = MSG_HEADER.format(label=label)
    profile_url = f"{settings.player_base_url}/profile"
    body = MSG_BODY.format(
        profile_url=profile_url,
        llu=emojis.get("llu"),
        bot_mention=bot_user.mention,
        paper=emojis.get(PLATFORM_EMOJI_NAME["Paper"]),
        mtgo=emojis.get(PLATFORM_EMOJI_NAME["MTGO"]),
    )
    view = as_view(build_container(f"{header}\n{body}", set_symbol_url(set_code)))
    await channel.send(view=view, allowed_mentions=discord.AllowedMentions.none())


async def _already_posted(channel: discord.TextChannel, bot_user: discord.ClientUser, today: date) -> bool:
    since = datetime.combine(today, POST_TIME, tzinfo=OPEN_TZ) - timedelta(hours=1)
    header = MSG_HEADER.format(label=PRERELEASE_LABEL).removeprefix("## ")
    async for message in channel.history(after=since, limit=200):
        if message.author.id == bot_user.id and header in message_text(message):
            return True
    return False
