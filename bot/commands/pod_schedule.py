"""`/pod-schedule` — the calendar of which formats the pods draft over the weeks ahead.

The grid ships as a rendered PNG (`pod_schedule_image`); everything a reader might want to select, click or
localize stays text. An embed rather than Components V2: mobile Pins, search results and reply previews
render content and embeds only, so a V2 layout shows as an empty message everywhere it is previewed.

The embed and image builders live in `pod_schedule_card`, shared with the daily tick. This command renders a
one-off snapshot carrying the same Vote and configure buttons, not pinned or kept fresh like the tick's card.
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot import audit
from bot.commands import descriptions as desc
from bot.commands.authorization import moderator_authorized_interaction
from bot.discord_helpers import posts_publicly, resolve_pod_chat_channel
from bot.services.pod_format_vote import post_vote_card, vote_ping_text
from bot.services.pod_schedule_card import DEFAULT_WEEKS, MAX_WEEKS, render_schedule
from bot.services.pod_schedule_controls import PodScheduleView

MSG_OPEN_VOTE_DENIED = "Only organizers can open the format vote"
MSG_NO_POD_CHAT = "Pod chat channel unavailable"
MSG_VOTE_POSTED = "Posted the format vote card in pod chat"


class PodSchedule(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="pod-schedule", description=desc.POD_SCHEDULE)
    @app_commands.describe(weeks="How many weeks to show")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def pod_schedule(
        self, interaction: discord.Interaction, weeks: app_commands.Range[int, 1, MAX_WEEKS] = DEFAULT_WEEKS,
    ) -> None:
        audit.event("pod_schedule_invoked", user_id=str(interaction.user.id), weeks=weeks)
        ephemeral = not posts_publicly(interaction)
        await interaction.response.defer(ephemeral=ephemeral, thinking=True)
        embed, file = await render_schedule(interaction.guild, weeks)
        await interaction.followup.send(
            embed=embed,
            file=file,
            view=PodScheduleView(),
            allowed_mentions=discord.AllowedMentions.none(),
            ephemeral=ephemeral,
        )

    @app_commands.command(name="openvote", description=desc.OPEN_VOTE)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def open_vote(self, interaction: discord.Interaction) -> None:
        if not await moderator_authorized_interaction(interaction):
            await interaction.response.send_message(MSG_OPEN_VOTE_DENIED, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        channel = resolve_pod_chat_channel(self.bot)
        if channel is None:
            await interaction.followup.send(MSG_NO_POD_CHAT, ephemeral=True)
            return
        await post_vote_card(channel, vote_ping_text(interaction.guild), force=True)
        audit.event("format_vote_opened", user_id=str(interaction.user.id))
        await interaction.followup.send(MSG_VOTE_POSTED, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PodSchedule(bot))
