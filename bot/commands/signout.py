from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select
from sqlalchemy.orm import Session

from bot import audit
from bot.commands import descriptions as desc
from bot.commands.messages import MSG_NOT_ON_BOARD
from bot.database import SessionLocal
from bot.models import Player
from bot.services import bot_log

logger = logging.getLogger(__name__)

MSG_SIGNED_OUT = (
    "🧎‍♂️ You've retired from the leaderboard. Run `/join` anytime to return. To wipe your data entirely, run `/exile`."
)
MSG_ALREADY_INACTIVE = "You're already retired. Run `/join` to return"


SignoutKind = Literal["signed_out", "not_registered", "already_inactive"]


@dataclass
class SignoutResult:
    kind: SignoutKind
    player_id: str | None = None


def process_signout(session: Session, discord_id: str) -> SignoutResult:
    player = session.execute(
        select(Player).where(Player.discord_id == discord_id)
    ).scalar_one_or_none()
    if player is None:
        return SignoutResult(kind="not_registered")
    if not player.active:
        return SignoutResult(kind="already_inactive", player_id=player.id)
    player.active = False
    session.commit()
    return SignoutResult(kind="signed_out", player_id=player.id)


class Signout(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="retire", description=desc.RETIRE)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def signout(self, interaction: discord.Interaction) -> None:
        user_id = str(interaction.user.id)
        username = str(interaction.user)
        ephemeral = interaction.guild is not None
        await interaction.response.defer(ephemeral=ephemeral, thinking=True)
        audit.event("signout_invoked", user_id=user_id, username=username)

        with SessionLocal() as session:
            result = process_signout(session, user_id)

        audit.event("signout_result", user_id=user_id, kind=result.kind, player_id=result.player_id)
        logger.info(f"retire: {username} → {result.kind}")

        if result.kind == "signed_out":
            await bot_log.get(self.bot).post_plain(
                f"🧎‍♂️ **{interaction.user.display_name}** retired from the leaderboard"
            )
            await interaction.followup.send(MSG_SIGNED_OUT, ephemeral=ephemeral)
        elif result.kind == "already_inactive":
            await interaction.followup.send(MSG_ALREADY_INACTIVE, ephemeral=ephemeral)
        else:
            await interaction.followup.send(MSG_NOT_ON_BOARD, ephemeral=ephemeral)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Signout(bot))
