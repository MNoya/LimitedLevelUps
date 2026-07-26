"""`/report-results` — a player's own open matches, on demand instead of only in a round DM.

The command is the one reporting surface that spans pairing modes, so it is where the commit path gets
chosen: `pod_team_board` imports from `pod_tournament`, which leaves this module the only place able to
reach both. Every other surface belongs to exactly one mode and stays wired straight to its own path.
"""
from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.commands import descriptions as desc
from bot.services.pod_team_board import handle_team_report
from bot.services.pod_tournament import build_own_match_report


log = logging.getLogger(__name__)


class ReportResults(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="report-results", description=desc.REPORT_RESULTS)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def report_results(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        report = await build_own_match_report(str(interaction.user.id), team_submit=handle_team_report)
        if report.notice is not None:
            log.info(f"report-results: {interaction.user} has nothing to report")
            await interaction.followup.send(report.notice, ephemeral=True)
            return
        log.info(f"report-results: {interaction.user} opened a card of {len(report.view.children)} match(es)")
        await interaction.followup.send(embed=report.embed, view=report.view, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ReportResults(bot))
