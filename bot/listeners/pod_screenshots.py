"""Capture images a participant posts in a pod-draft thread → stash on participant row.

Active from the start of the final round, when the bot asks for decks. Images posted earlier are
ignored.
Last-image-wins, except a stored caption matching the record-pattern (e.g. "3-0", "2-1")
locks the slot — only another record-pattern image can replace it. Once the championship
has posted, participants with a deck on file are done: their later images are ignored
unless record-captioned.

On capture we re-run the championship trigger — swiss or team, live manager or the recovery
shim once finalize has evicted it — so a late screenshot completing the showcase decks posts
the announcement right away instead of waiting for the deadline. A captured screenshot from a
champion gets a 🏆 react on the message itself.
"""
from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands

from bot.database import SessionLocal
from bot.discord_helpers import first_image_url, message_caption
from bot.services.pod_active import ACTIVE_POD_MANAGERS
from bot.services.pod_drafts import (
    active_event_for_discord_user_in_dm,
    capture_deck_screenshot,
    is_pod_thread_champion,
)
from bot.services.pod_team_showcase import maybe_post_team_championship, maybe_post_team_trophy_hype
from bot.services.pod_thread_backfill import parse_caption_colors
from bot.services.pod_tournament import maybe_post_championship, refresh_standings_for_event


log = logging.getLogger(__name__)


class PodScreenshotListener(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        image_url = first_image_url(message)
        if image_url is None:
            return

        if isinstance(message.channel, discord.DMChannel):
            await self._redirect_dm_image(message)
            return

        if not isinstance(message.channel, discord.Thread):
            return

        thread_id = str(message.channel.id)
        discord_id = str(message.author.id)
        caption = message_caption(message)

        event_id = await asyncio.to_thread(_capture_sync, thread_id, discord_id, image_url, caption)
        if event_id is None:
            return

        is_champion_in_memory = False
        manager = ACTIVE_POD_MANAGERS.get(event_id)
        if manager is not None and manager.kind != "mock":
            if manager.pairing_mode == "team":
                await maybe_post_team_trophy_hype(manager)
                await maybe_post_team_championship(manager)
            else:
                await maybe_post_championship(manager)
            is_champion_in_memory = discord_id in manager.champion_discord_ids
        elif manager is None:
            await refresh_standings_for_event(self.bot, event_id, thread_id)

        is_champion_in_db = await asyncio.to_thread(_is_thread_champion_sync, thread_id, discord_id)
        if is_champion_in_memory or is_champion_in_db:
            log.info(
                f"[DECK] champion_screenshot event={event_id} discord_id={discord_id} "
                f"in_memory={is_champion_in_memory} in_db={is_champion_in_db}"
            )
            try:
                await message.add_reaction("🏆")
            except discord.HTTPException:
                log.info("could not add 🏆 reaction", exc_info=True)

    async def _redirect_dm_image(self, message: discord.Message) -> None:
        """User posted an image in DM — point them at the pod thread so the screenshot is publicly
        viewable. DM CDN URLs carry signed expiries and aren't reliably embeddable on the frontend."""
        discord_id = str(message.author.id)
        target = await asyncio.to_thread(_resolve_active_pod_thread_sync, discord_id)
        if target is None:
            return
        event_id, thread_id = target
        try:
            thread = self.bot.get_channel(int(thread_id)) or await self.bot.fetch_channel(int(thread_id))
            link = thread.jump_url
        except discord.HTTPException:
            return
        log.info(f"[DECK] dm_image_redirect event={event_id} discord_id={discord_id} thread={thread_id}")
        try:
            await message.reply(
                f"📸 Post your deck screenshot in the pod-draft thread so everyone can see it: {link}"
            )
        except discord.HTTPException:
            log.warning("could not reply to DM image", exc_info=True)


def _capture_sync(thread_id: str, discord_id: str, image_url: str, caption: str | None) -> str | None:
    with SessionLocal() as session:
        colors = parse_caption_colors(caption)
        event_id = capture_deck_screenshot(session, thread_id, discord_id, image_url, caption, colors)
        if event_id is not None:
            session.commit()
        return event_id


def _is_thread_champion_sync(thread_id: str, discord_id: str) -> bool:
    with SessionLocal() as session:
        return is_pod_thread_champion(session, thread_id, discord_id)


def _resolve_active_pod_thread_sync(discord_id: str) -> tuple[str, str] | None:
    with SessionLocal() as session:
        return active_event_for_discord_user_in_dm(session, discord_id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PodScreenshotListener(bot))
