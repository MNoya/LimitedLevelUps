from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace

import discord
from discord import app_commands, ui
from discord.ext import commands

from bot.commands import descriptions as desc
from bot.discord_helpers import run_detached
from bot.services.pod_drafts import TOTAL_ROUNDS, normalize_player_name
from bot.services.pod_tournament import (
    DROP_EMOJI,
    DropScene,
    actor_label,
    drop_player,
    is_pod_organizer,
    load_drop_scene,
)

MSG_NOT_POD_THREAD = "Run `/drop` inside a pod-draft thread"
MSG_NO_ROUNDS = "Drops open once Round 1 is paired"
MSG_ROUND_NOT_STARTED = "Round {round} has not started"
MSG_NOT_IN_POD = "Only players in this pod can use `/drop`"
MSG_POD_FINISHED = "This pod is finished. Ask an Organizer to record a drop"
MSG_UNKNOWN_PLAYER = "No player named {player} in this pod"
MSG_PICK_PLAYER = "Pick the `player` to drop"
MSG_ROUND_ORGANIZER_ONLY = "Only Organizers can pick a `round`"
MSG_ONLY_OPPONENT = "You can only drop your Round {round} opponent"
MSG_ALREADY_DROPPED = "{player} has already dropped"
MSG_CONFIRM_SELF = "Drop from this pod starting Round {round}?"
MSG_CONFIRM_OTHER = "Drop **{player}** from this pod starting Round {round}?"
MSG_DONE_SELF = f"{DROP_EMOJI} You dropped from this pod"
MSG_DONE_OTHER = f"{DROP_EMOJI} **{{player}}** dropped from this pod"
MSG_CANCELLED = "No changes made"
MSG_NO_OPPONENT = "You have no opponent in Round {round}"
MSG_POD_GONE = "This pod no longer exists"


class PodDrop(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="drop", description=desc.POD_DROP)
    @app_commands.describe(
        player="Who dropped; defaults to you",
        round="Organizers only: the first round they miss, defaults to the current round",
    )
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def drop(
        self, interaction: discord.Interaction, player: str | None = None,
        round: app_commands.Range[int, 1, TOTAL_ROUNDS] | None = None,
    ) -> None:
        scene, organizer = await asyncio.gather(
            asyncio.to_thread(load_drop_scene, str(interaction.channel_id), str(interaction.user.id)),
            is_pod_organizer(self.bot, interaction.user),
        )
        if scene is None:
            await interaction.response.send_message(MSG_NOT_POD_THREAD, ephemeral=True)
            return
        await send_drop_prompt(interaction, scene, plan_drop(scene, organizer, player, round))

    @drop.autocomplete("player")
    async def _player_autocomplete(
        self, interaction: discord.Interaction, current: str,
    ) -> list[app_commands.Choice[str]]:
        scene = await asyncio.to_thread(load_drop_scene, str(interaction.channel_id), str(interaction.user.id))
        if scene is None:
            return []
        typed = current.strip().lower()
        choices = []
        for name, display in scene.roster:
            if normalize_player_name(name) in scene.dropped or typed not in display.lower():
                continue
            choices.append(app_commands.Choice(name=display[:100], value=name[:100]))
        return choices[:25]


def add_drop_buttons(view: ui.View, thread_id: str) -> None:
    drop_me = ui.Button(label="Drop Me", emoji=DROP_EMOJI, style=discord.ButtonStyle.danger)
    opponent_drop = ui.Button(label="Opponent Drop", style=discord.ButtonStyle.secondary)

    async def on_drop_me(interaction: discord.Interaction) -> None:
        scene = await asyncio.to_thread(load_drop_scene, thread_id, str(interaction.user.id))
        if scene is None:
            await interaction.response.send_message(MSG_POD_GONE, ephemeral=True)
            return
        await send_drop_prompt(interaction, scene, plan_drop(scene, False, None, None))

    async def on_opponent_drop(interaction: discord.Interaction) -> None:
        scene = await asyncio.to_thread(load_drop_scene, thread_id, str(interaction.user.id))
        if scene is None:
            await interaction.response.send_message(MSG_POD_GONE, ephemeral=True)
            return
        opponent = scene.caller_opponents.get(scene.current_round)
        if opponent is None:
            await interaction.response.send_message(MSG_NO_OPPONENT.format(round=scene.current_round), ephemeral=True)
            return
        await send_drop_prompt(interaction, scene, plan_drop(scene, False, opponent, None))

    drop_me.callback = on_drop_me
    opponent_drop.callback = on_opponent_drop
    view.add_item(drop_me)
    view.add_item(opponent_drop)


async def send_drop_prompt(interaction: discord.Interaction, scene: DropScene, plan: DropPlan | str) -> None:
    if isinstance(plan, str):
        await interaction.response.send_message(plan, ephemeral=True)
        return
    if plan.dropped_by is None:
        prompt, done = MSG_CONFIRM_SELF.format(round=plan.round_num), MSG_DONE_SELF
    else:
        target = scene.display(plan.target)
        prompt = MSG_CONFIRM_OTHER.format(player=target, round=plan.round_num)
        done = MSG_DONE_OTHER.format(player=target)
        plan = replace(plan, dropped_by=f"{plan.dropped_by} ({actor_label(interaction)})")
    await interaction.response.send_message(prompt, view=ConfirmDropView(scene, plan, done), ephemeral=True)


@dataclass(frozen=True)
class DropPlan:
    target: str
    round_num: int
    dropped_by: str | None
    replace_reported: bool


def plan_drop(scene: DropScene, organizer: bool, player: str | None, round_num: int | None) -> DropPlan | str:
    if scene.current_round == 0:
        return MSG_NO_ROUNDS
    if round_num is not None and not organizer:
        return MSG_ROUND_ORGANIZER_ONLY
    round_num = round_num or scene.current_round
    if round_num > scene.current_round:
        return MSG_ROUND_NOT_STARTED.format(round=round_num)
    if scene.caller is None and not organizer:
        return MSG_NOT_IN_POD
    if scene.finalized and not organizer:
        return MSG_POD_FINISHED
    if player is None:
        if scene.caller is None:
            return MSG_PICK_PLAYER
        target = scene.caller
    else:
        target = scene.find(player)
        if target is None:
            return MSG_UNKNOWN_PLAYER.format(player=player)
    if normalize_player_name(target) in scene.dropped:
        return MSG_ALREADY_DROPPED.format(player=scene.display(target))
    if target == scene.caller:
        return DropPlan(target, round_num, None, replace_reported=organizer)
    opponent = scene.caller_opponents.get(round_num)
    if opponent is not None and normalize_player_name(opponent) == normalize_player_name(target):
        return DropPlan(target, round_num, "Opponent", replace_reported=True)
    if organizer:
        return DropPlan(target, round_num, "Organizer", replace_reported=True)
    return MSG_ONLY_OPPONENT.format(round=round_num)


class ConfirmDropView(ui.View):
    def __init__(self, scene: DropScene, plan: DropPlan, done: str):
        super().__init__(timeout=300)
        self.scene = scene
        self.plan = plan
        self.done = done

    @ui.button(label="Confirm Drop", emoji=DROP_EMOJI, style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _button: ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(content=self.done, view=None)
        plan = self.plan
        run_detached(
            drop_player(interaction.client, self.scene, plan.target, plan.round_num, plan.dropped_by,
                        replace_reported=plan.replace_reported),
            f"drop {plan.target} from {self.scene.event_id}",
        )

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _button: ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(content=MSG_CANCELLED, view=None)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PodDrop(bot))
