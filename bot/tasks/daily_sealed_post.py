from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands

from bot import audit
from bot.commands.messages import MSG_POD_ADDED, MSG_POD_REMOVED
from bot.config import settings
from bot.database import SessionLocal
from bot.discord_helpers import message_text
from bot.services.containers import as_view, build_container
from bot.services.daily_sealed import TURNOVER_TIME, TURNOVER_TZ, serving_day, turnover_instant
from bot.services.daily_sealed_post import (
    DAILY_SEALED_ROLE_NAME,
    PoolSummary,
    build_daily_sealed_post,
    pool_summary,
    pool_url,
)
from bot.services.format_schedule import latest_set_channel
from bot.services.mock_lobby_card import set_symbol_url
from bot.services.pod_roles import find_role, role_mention, toggle_role

log = logging.getLogger(__name__)

RETRY_HOURS = "10-14"
ROLE_BUTTON_ID = "daily_sealed:role"

MSG_ROLE_BUTTON = "Notify me"
MSG_ROLE_FAILED = "Couldn't update your role. Ask an Admin"

def init_daily_sealed_post(bot: commands.Bot) -> None:
    bot.pod_scheduler.add_job(
        fire_daily_sealed_post, "cron", args=[bot], hour=RETRY_HOURS, minute="0,30", timezone=TURNOVER_TZ,
        id="daily-sealed-post", replace_existing=True,
    )
    log.info(f"daily-sealed: armed from {TURNOVER_TIME:%H:%M} {TURNOVER_TZ.key}, retrying every 30 minutes")


async def fire_daily_sealed_post(bot: commands.Bot) -> None:
    if bot.user is None:
        return
    guild = bot.get_guild(settings.discord_guild_id) if settings.discord_guild_id else None
    if guild is None:
        return
    channel = latest_set_channel(guild.channels)
    if channel is None:
        log.warning("daily-sealed: no latest set channel, skipping")
        return
    today = serving_day(datetime.now(timezone.utc))
    today_summary, yesterday_summary = await asyncio.to_thread(_load_summaries, today)
    if today_summary is None:
        log.warning(f"daily-sealed: no pool stored for {today}, retrying later")
        return
    try:
        if await _already_posted(channel, bot.user, today_summary):
            return
        mention = role_mention(guild, DAILY_SEALED_ROLE_NAME)
        await send_daily_sealed_post(channel, today_summary, yesterday_summary, mention)
    except discord.HTTPException:
        log.warning(f"daily-sealed: post for {today} failed, retrying later", exc_info=True)
        return
    audit.event("daily_sealed_post", day=today.isoformat(), channel_id=str(channel.id))
    log.info(f"daily-sealed: posted {today} in #{channel.name}")


async def send_daily_sealed_post(
    channel: discord.abc.Messageable, today: PoolSummary, yesterday: PoolSummary | None, mention: str,
) -> discord.Message:
    return await channel.send(
        view=daily_sealed_view(today, yesterday, mention), allowed_mentions=discord.AllowedMentions(roles=True),
    )


def daily_sealed_view(today: PoolSummary, yesterday: PoolSummary | None, mention: str) -> discord.ui.LayoutView:
    text = build_daily_sealed_post(today, yesterday, mention)
    return as_view(
        build_container(text, set_symbol_url(today.set_code)), discord.ui.ActionRow(DailySealedRoleButton()),
    )


class DailySealedRoleButton(discord.ui.DynamicItem[discord.ui.Button], template=ROLE_BUTTON_ID):
    def __init__(self) -> None:
        super().__init__(discord.ui.Button(
            label=MSG_ROLE_BUTTON, emoji="🔔", style=discord.ButtonStyle.secondary, custom_id=ROLE_BUTTON_ID,
        ))

    @classmethod
    async def from_custom_id(
        cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match,
    ) -> "DailySealedRoleButton":
        return cls()

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        member = interaction.user
        role = find_role(interaction.guild, DAILY_SEALED_ROLE_NAME)
        if role is None or not isinstance(member, discord.Member):
            await interaction.followup.send(MSG_ROLE_FAILED, ephemeral=True)
            return
        held = await toggle_role(member, role)
        if held is None:
            await interaction.followup.send(MSG_ROLE_FAILED, ephemeral=True)
            return
        reply = MSG_POD_ADDED if held else MSG_POD_REMOVED
        await interaction.followup.send(
            reply.format(name=role.mention), ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
        )


def _load_summaries(today) -> tuple[PoolSummary | None, PoolSummary | None]:
    with SessionLocal() as session:
        return pool_summary(session, today), pool_summary(session, today - timedelta(days=1))


async def _already_posted(channel: discord.TextChannel, bot_user: discord.ClientUser, today: PoolSummary) -> bool:
    url = pool_url(today.day)
    async for message in channel.history(after=turnover_instant(today.day) - timedelta(minutes=5), limit=200):
        if message.author.id == bot_user.id and url in message_text(message):
            return True
    return False

