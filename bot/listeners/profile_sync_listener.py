from __future__ import annotations

import discord
from discord.ext import commands
from sqlalchemy import select

from bot.database import SessionLocal
from bot.discord_helpers import extract_avatar_hash, is_deleted_account_name, resolve_display_name
from bot.models import Player


class ProfileSyncListener(commands.Cog):
    """Keep stored Discord profile fields fresh reactively, so the 17lands refresh never has to.

    Avatar and global username/name arrive on on_user_update; server nickname on on_member_update.
    Each event updates only the one Player row that changed, with no REST calls. The weekly
    reconcile in main.py backstops anything changed while the bot was offline.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User) -> None:
        unchanged = (
            before.avatar == after.avatar
            and before.name == after.name
            and before.global_name == after.global_name
        )
        if unchanged:
            return
        display_name = await resolve_display_name(self.bot, after)
        await self._persist(
            after.id,
            avatar_hash=extract_avatar_hash(after),
            display_name=display_name,
            discord_username=str(after),
        )

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if before.display_name == after.display_name:
            return
        await self._persist(after.id, display_name=after.display_name)

    async def _persist(self, discord_id: int, **fields: object) -> None:
        fields = {
            name: value for name, value in fields.items() if not is_deleted_account_name(value)
        }
        if not fields:
            return
        with SessionLocal() as session:
            player = session.execute(
                select(Player).where(Player.discord_id == str(discord_id))
            ).scalar_one_or_none()
            if player is None:
                return
            changed = False
            for attr, value in fields.items():
                if getattr(player, attr) != value:
                    setattr(player, attr, value)
                    changed = True
            if changed:
                session.commit()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ProfileSyncListener(bot))
