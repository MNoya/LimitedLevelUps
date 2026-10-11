"""`/pod-guide` — the pinned Pod Draft walkthrough, sourced from bot/pod-draft-guide.md."""
from __future__ import annotations

from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from bot import audit, emojis
from bot.commands import descriptions as desc
from bot.services.pod_roles import role_label
from bot.services.pod_schedule import ORGANIZER_ROLE_NAME, POD_DRAFTERS_ROLE_NAME

GUIDE_PATH = Path(__file__).resolve().parents[1] / "pod-draft-guide.md"
GUIDE_MARKER = "Pod Draft Guide"
GUIDE_SIGNOFF = "Thank you for playing!"
GUIDE_AFTER_DRAFTING = "**After Drafting:**"


def render_pod_guide(guild: discord.Guild | None) -> str:
    text = GUIDE_PATH.read_text(encoding="utf-8").strip().replace(":mtga:", emojis.get("mtga"))
    for role_name in (POD_DRAFTERS_ROLE_NAME, ORGANIZER_ROLE_NAME):
        text = text.replace(f"@{role_name}", role_label(guild, role_name))
    return text


def render_pod_guide_embed_body(guild: discord.Guild | None, setup_only: bool = False) -> str:
    guide = render_pod_guide(guild)
    if setup_only:
        guide = guide.split(GUIDE_AFTER_DRAFTING, 1)[0]
    guide = guide.replace(GUIDE_SIGNOFF, "").rstrip()
    return f"{guide} {emojis.get('chordo_love')}"


class PodGuide(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="pod-guide", description=desc.POD_GUIDE)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def pod_guide(self, interaction: discord.Interaction) -> None:
        is_owner = await self.bot.is_owner(interaction.user)
        audit.event("pod_guide_invoked", user_id=str(interaction.user.id))
        public = interaction.guild is not None and is_owner
        body = render_pod_guide_embed_body(interaction.guild, setup_only=public)
        await interaction.response.send_message(
            embed=discord.Embed(description=body, color=discord.Color.green()),
            allowed_mentions=discord.AllowedMentions.none(),
            ephemeral=not public,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PodGuide(bot))
