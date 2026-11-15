from __future__ import annotations

from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from bot import audit
from bot.commands import descriptions as desc
from bot.commands.authorization import moderator_authorized_interaction
from bot.database import SessionLocal
from bot.services.fantasy_event import FantasyEvent, all_events
from bot.services.fantasy_reveal import reveal_through, round_number_for_reveal
from bot.tasks.pro_play_posts import announce_reveal, round_label

MSG_ROUND_NOT_MODERATOR = "Only moderators can reveal Fantasy rounds"
MSG_ROUND_NO_EVENT = "There is no Fantasy event to reveal"
MSG_ROUND_UNKNOWN = "Use a round number from 0 to {swiss_rounds}, or quarterfinals, semifinals or final"
MSG_ROUND_REVEALED = "**{event}** results now show through {label}"


class FantasyRound(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="round", description=desc.FANTASY_ROUND)
    @app_commands.describe(round="A round number, or quarterfinals, semifinals or final")
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def round(self, interaction: discord.Interaction, round: str) -> None:
        if not await moderator_authorized_interaction(interaction):
            await interaction.response.send_message(MSG_ROUND_NOT_MODERATOR, ephemeral=True)
            return
        event = live_event(datetime.now(timezone.utc))
        if event is None:
            await interaction.response.send_message(MSG_ROUND_NO_EVENT, ephemeral=True)
            return
        number = round_number_for_reveal(round, event.swiss_rounds)
        if number is None:
            await interaction.response.send_message(
                MSG_ROUND_UNKNOWN.format(swiss_rounds=event.swiss_rounds), ephemeral=True,
            )
            return
        await interaction.response.defer(thinking=True)
        with SessionLocal() as session:
            previous = reveal_through(session, event.code, number)
            session.commit()
        audit.event("fantasy_round_revealed", user_id=str(interaction.user.id), event=event.code, round=number)
        label, _ = round_label(event, number)
        shown_through = label if number <= event.swiss_rounds else f"the {label}"
        message = MSG_ROUND_REVEALED.format(event=event.name, label=shown_through)
        await interaction.followup.send(message)
        await announce_reveal(event, previous, number)


def live_event(now: datetime) -> FantasyEvent | None:
    soonest_upcoming = None
    for event in all_events():
        if event.replay_only:
            continue
        if event.picks_lock_at <= now:
            return event
        soonest_upcoming = event
    return soonest_upcoming


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(FantasyRound(bot))
