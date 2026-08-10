from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot import audit, emojis
from bot.commands import descriptions as desc
from bot.database import SessionLocal
from bot.services.active_set import resolve_board_set
from bot.services.leaderboard_visibility import set_opt_in
from bot.services.player_stats import StatsData, process_stats, profile_url, render_embed
from bot.sets import ALL_SETS, active_set_code

logger = logging.getLogger(__name__)

SET_CODES = {s.code.upper(): s for s in ALL_SETS}


def _profile_button(data: StatsData, own: bool) -> discord.ui.Button:
    return discord.ui.Button(
        label="My Profile" if own else f"{data.player_name}'s Profile",
        url=profile_url(data),
        style=discord.ButtonStyle.link,
        emoji=emojis.get_emoji("llu"),
    )


class LeaderboardVisibilityView(discord.ui.View):
    def __init__(self, bot: commands.Bot, user_id: str, data: StatsData) -> None:
        super().__init__(timeout=600)
        self.bot = bot
        self.user_id = user_id
        self.data = data
        self.opted_in = not data.opted_out
        self._render_buttons()

    def _render_buttons(self) -> None:
        self.clear_items()
        label = "Hide My Rank" if self.opted_in else "Show My Rank"
        style = discord.ButtonStyle.secondary if self.opted_in else discord.ButtonStyle.success
        button = discord.ui.Button(label=label, style=style)
        button.callback = self._toggle
        self.add_item(button)
        self.add_item(_profile_button(self.data, own=True))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return str(interaction.user.id) == self.user_id

    async def _toggle(self, interaction: discord.Interaction) -> None:
        self.opted_in = not self.opted_in
        with SessionLocal() as session:
            set_opt_in(session, self.user_id, self.opted_in)
            data = process_stats(session, player_name=None, viewer_discord_id=self.user_id)
        audit.event("leaderboard_visibility_button", user_id=self.user_id, opt_in=self.opted_in)
        if data is not None:
            self.data = data
        self._render_buttons()
        if data is not None:
            await interaction.response.edit_message(embed=render_embed(data), view=self)
        else:
            await interaction.response.edit_message(view=self)


class Stats(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="stats", description=desc.STATS)
    @app_commands.describe(
        player="Player display name to look up (defaults to you)",
        set="Set to look up (defaults to the current set)",
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def stats(
        self, interaction: discord.Interaction, player: str | None = None, set: str | None = None
    ) -> None:
        user_id = str(interaction.user.id)
        username = str(interaction.user)
        ephemeral = interaction.guild is not None
        await interaction.response.defer(ephemeral=ephemeral, thinking=True)
        audit.event("stats_invoked", user_id=user_id, player=player, set=set)

        set_code: str | None = None
        if set is not None:
            seed = SET_CODES.get(set.upper())
            if seed is None:
                await interaction.followup.send(f"Unknown set `{set}`", ephemeral=ephemeral)
                return
            set_code = seed.code

        with SessionLocal() as session:
            if set_code is None:
                board = resolve_board_set(session)
                set_code = board.code if board is not None else active_set_code()
            data = process_stats(session, player_name=player, viewer_discord_id=user_id, set_code=set_code)

        target = player or "self"
        logger.info(f"stats: {username} looked up {target!r} for {set_code}")

        if data is None:
            logger.info(f"stats: not found for {target!r}")
            if player:
                msg = f"No active player found with display name `{player}`."
            else:
                msg = "You're not on the leaderboard. Run `/join` to get started."
            await interaction.followup.send(msg, ephemeral=ephemeral)
            return

        logger.info(f"stats: {data.player_name} rank={data.rank} score={data.total_score:.1f}")
        kwargs = {"embed": render_embed(data), "ephemeral": ephemeral}
        if player is None and data.has_token:
            kwargs["view"] = LeaderboardVisibilityView(self.bot, user_id, data)
        else:
            view = discord.ui.View(timeout=600)
            view.add_item(_profile_button(data, own=player is None))
            kwargs["view"] = view
        await interaction.followup.send(**kwargs)

    @stats.autocomplete("set")
    async def _set_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        q = current.upper()
        return [
            app_commands.Choice(name=f"{s.code} — {s.name}", value=s.code)
            for s in reversed(ALL_SETS)
            if q in s.code.upper() or q in s.name.upper()
        ][:25]


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Stats(bot))
