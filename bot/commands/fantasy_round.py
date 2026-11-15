from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from bot import audit
from bot.commands import descriptions as desc
from bot.commands.authorization import moderator_authorized_interaction
from bot.database import SessionLocal
from bot.models import FantasyPlayer
from bot.services.fantasy_event import STAGE_FINAL, STAGE_QUARTERFINAL, STAGE_SEMIFINAL, FantasyEvent, all_events
from bot.services.fantasy_reveal import reveal_through, round_number_for_reveal
from bot.services.fantasy_sync import fold_name, record_top8_result
from bot.services.melee import MeleeClient
from bot.tasks.pro_play_posts import announce_reveal, round_label

MSG_ROUND_NOT_MODERATOR = "Only moderators can reveal Fantasy rounds"
MSG_ROUND_NO_EVENT = "There is no Fantasy event to reveal"
MSG_ROUND_UNKNOWN = "Use a round number from 0 to {swiss_rounds}, or quarterfinals, semifinals or final"
MSG_ROUND_REVEALED = "**{event}** results now show through {label}"
MSG_RESULT_NOT_MODERATOR = "Only moderators can enter Top 8 results"
MSG_RESULT_SAME_PLAYER = "Pick two different players"
MSG_RESULT_UNKNOWN_PLAYER = "Pick both players from the list"
MSG_RESULT_NOT_PAIRED = "These two players did not meet in this round of the bracket"
MSG_RESULT_SAVED = "**{event}** {position}: {winner} beat {loser} {score}"

TOP8_STAGE_CHOICES = [
    app_commands.Choice(name="Quarterfinal", value=STAGE_QUARTERFINAL),
    app_commands.Choice(name="Semifinal", value=STAGE_SEMIFINAL),
    app_commands.Choice(name="Final", value=STAGE_FINAL),
]
GAME_SCORE_CHOICES = [app_commands.Choice(name=score, value=score) for score in ("3-0", "3-1", "3-2")]


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

    @app_commands.command(name="top8-result", description=desc.FANTASY_TOP8_RESULT)
    @app_commands.describe(
        match="The bracket round", winner="The player who won", loser="The player who lost",
        score="Games won by the winner and the loser",
    )
    @app_commands.choices(match=TOP8_STAGE_CHOICES, score=GAME_SCORE_CHOICES)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def top8_result(
        self, interaction: discord.Interaction, match: app_commands.Choice[str], winner: str, loser: str,
        score: app_commands.Choice[str],
    ) -> None:
        if not await moderator_authorized_interaction(interaction):
            await interaction.response.send_message(MSG_RESULT_NOT_MODERATOR, ephemeral=True)
            return
        event = live_event(datetime.now(timezone.utc))
        if event is None:
            await interaction.response.send_message(MSG_ROUND_NO_EVENT, ephemeral=True)
            return
        if winner == loser:
            await interaction.response.send_message(MSG_RESULT_SAME_PLAYER, ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        winner_games, loser_games = (int(games) for games in score.value.split("-"))
        try:
            saved = await asyncio.to_thread(
                _save_top8_result, event, match.value, winner, loser, (winner_games, loser_games),
            )
        except LookupError:
            await interaction.followup.send(MSG_RESULT_UNKNOWN_PLAYER, ephemeral=True)
            return
        except ValueError:
            await interaction.followup.send(MSG_RESULT_NOT_PAIRED, ephemeral=True)
            return
        position, winner_name, loser_name = saved
        audit.event(
            "fantasy_top8_result", user_id=str(interaction.user.id), event=event.code, position=position,
            winner=winner, loser=loser, score=score.value,
        )
        await interaction.followup.send(MSG_RESULT_SAVED.format(
            event=event.name, position=position, winner=winner_name, loser=loser_name, score=score.value,
        ))

    @top8_result.autocomplete("winner")
    @top8_result.autocomplete("loser")
    async def top8_player_autocomplete(
        self, interaction: discord.Interaction, current: str,
    ) -> list[app_commands.Choice[str]]:
        event = live_event(datetime.now(timezone.utc))
        if event is None:
            return []
        players = await asyncio.to_thread(_event_players, event.code)
        typed = fold_name(current)
        choices = []
        for player in players:
            name = f"{player.first_name} {player.last_name}"
            if typed in fold_name(name):
                choices.append(app_commands.Choice(name=name, value=player.slug))
        return choices[:25]


def live_event(now: datetime) -> FantasyEvent | None:
    soonest_upcoming = None
    for event in all_events():
        if event.replay_only:
            continue
        if event.picks_lock_at <= now:
            return event
        soonest_upcoming = event
    return soonest_upcoming


def _save_top8_result(
    event: FantasyEvent, stage: str, winner_slug: str, loser_slug: str, score: tuple[int, int],
) -> tuple[str, str, str]:
    with SessionLocal() as session:
        players = {}
        for player in session.scalars(
            select(FantasyPlayer).where(
                FantasyPlayer.event_code == event.code, FantasyPlayer.slug.in_([winner_slug, loser_slug]),
            )
        ):
            players[player.slug] = player
        if winner_slug not in players or loser_slug not in players:
            raise LookupError(winner_slug if winner_slug not in players else loser_slug)
        winner, loser = players[winner_slug], players[loser_slug]
        position = record_top8_result(session, event, MeleeClient(), stage, winner, loser, score)
        session.commit()
        return position, f"{winner.first_name} {winner.last_name}", f"{loser.first_name} {loser.last_name}"


def _event_players(event_code: str) -> list[FantasyPlayer]:
    with SessionLocal() as session:
        statement = (
            select(FantasyPlayer)
            .where(FantasyPlayer.event_code == event_code)
            .order_by(FantasyPlayer.last_name, FantasyPlayer.first_name)
        )
        return list(session.scalars(statement))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(FantasyRound(bot))
