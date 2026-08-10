"""The organizer's controls on a busy pod: two while it holds, one after it has split.

📋 on the held card opens a private tick list of the roster, so someone in the room can record what the
buttons could not. Open Tables ends the wait early, which is the same release the start time would
have run. 📋 on the overview card moves players between the tables the split made.

All three carry the event id in their custom_id, so they keep working after a restart. The hold pair is
rendered greyed out once the tables open, and a press that slips through the moment before that edit
lands is acknowledged and dropped.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import re

import discord
from discord import ui

from bot.commands.messages import (
    MSG_ATTENDEES_EMPTY,
    MSG_ATTENDEES_LEAD,
    MSG_ATTENDEES_PLACEHOLDER,
    MSG_ATTENDEES_SAVED,
    MSG_DECLINE_DONE,
    MSG_DECLINE_PLACEHOLDER,
    MSG_NOT_ORGANIZER_ATTENDEES,
    MSG_NOT_ORGANIZER_TABLES,
    MSG_MOVE_BUTTON,
    MSG_MOVE_DONE,
    MSG_MOVE_LEAD,
    MSG_MOVE_NOTHING_PICKED,
    MSG_MOVE_PLAYERS_BUTTON,
    MSG_MOVE_PLAYERS_PLACEHOLDER,
    MSG_MOVE_TABLE_PLACEHOLDER,
    MSG_NOT_ORGANIZER_MOVE,
    MSG_OPEN_TABLES_BUTTON,
    MSG_OPEN_TABLES_DONE,
    MSG_STAGED_POD_SEATS,
    MSG_TABLE_SEATED,
)
from bot.discord_helpers import run_detached
from bot.services.pod_confirm import decline_players_sync, set_confirmations_sync
from bot.services.pod_launch import cancel_release, is_holding, release_attendance_hold
from bot.services.pod_staging import (
    FamilyPod,
    Signup,
    confirmed_first_roster_sync,
    move_players_sync,
    pod_family_sync,
)
from bot.services.pod_tournament import is_pod_organizer
from bot.tasks.pod_draft_reminder import refresh_or_repost_roster_reminder


ATTENDEES_BUTTON_PREFIX = "podattendees"
OPEN_TABLES_BUTTON_PREFIX = "podopentables"
MOVE_BUTTON_PREFIX = "podmoveplayers"
SELECT_LIMIT = 25

log = logging.getLogger(__name__)


class AttendeesButton(ui.DynamicItem[ui.Button], template=rf"{ATTENDEES_BUTTON_PREFIX}:(?P<event_id>.+)"):
    """Label-less and grey, because it is not for the players reading the card. It answers with a private
    tick list rather than changing anything, so a press by the wrong person costs them one notice.

    Live for the whole confirmation window, not only while the tables are held: whether a press is allowed
    is already decided by whether the card drew the button enabled."""

    def __init__(self, event_id: str, disabled: bool = False) -> None:
        super().__init__(ui.Button(
            style=discord.ButtonStyle.secondary, emoji="📋", disabled=disabled,
            custom_id=f"{ATTENDEES_BUTTON_PREFIX}:{event_id}",
        ))
        self.event_id = event_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: ui.Button, match: re.Match):
        return cls(match["event_id"])

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await is_pod_organizer(interaction.client, interaction.user):
            await interaction.response.send_message(MSG_NOT_ORGANIZER_ATTENDEES, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        roster = await asyncio.to_thread(confirmed_first_roster_sync, self.event_id)
        if not roster:
            await interaction.followup.send(MSG_ATTENDEES_EMPTY, ephemeral=True)
            return
        await interaction.followup.send(
            MSG_ATTENDEES_LEAD, view=_AttendeesView(self.event_id, roster), ephemeral=True,
        )


class OpenTablesButton(
    ui.DynamicItem[ui.Button], template=rf"{OPEN_TABLES_BUTTON_PREFIX}:(?P<event_id>.+)",
):
    """End the wait now. The release is the same one the start time would have run, so pressing early
    only means the room stopped expecting anybody else."""

    def __init__(self, event_id: str, disabled: bool = False) -> None:
        super().__init__(ui.Button(
            style=discord.ButtonStyle.primary, label=MSG_OPEN_TABLES_BUTTON, emoji="🚀", disabled=disabled,
            custom_id=f"{OPEN_TABLES_BUTTON_PREFIX}:{event_id}",
        ))
        self.event_id = event_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: ui.Button, match: re.Match):
        return cls(match["event_id"])

    async def callback(self, interaction: discord.Interaction) -> None:
        if not is_holding(self.event_id):
            await interaction.response.defer()
            return
        if not await is_pod_organizer(interaction.client, interaction.user):
            await interaction.response.send_message(MSG_NOT_ORGANIZER_TABLES, ephemeral=True)
            return
        await interaction.response.send_message(
            MSG_OPEN_TABLES_DONE.format(actor=interaction.user.display_name),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        cancel_release(interaction.client, self.event_id)
        run_detached(
            release_attendance_hold(interaction.client, self.event_id),
            f"the early release of {self.event_id}",
        )
        log.info(f"attendance hold on {self.event_id}: opened early by {interaction.user}")


def build_hold_items(
    event_id: str, *, confirming: bool, held: bool, holding: bool,
) -> list[ui.Item]:
    """The organizer controls a roster card carries beyond its RSVP row.

    The tick list spans the whole confirmation window; opening the tables is the hold's own act and needs
    a hold to end. Both grey out afterwards rather than vanishing, and Discord refuses a disabled press,
    so neither needs copy saying the moment has passed."""
    items: list[ui.Item] = []
    if confirming or held:
        items.append(AttendeesButton(event_id, disabled=held and not holding))
    if held:
        items.append(OpenTablesButton(event_id, disabled=not holding))
    return items


class _AttendeesView(ui.View):
    """The private tick list. It is ephemeral and short-lived, so it holds the roster in memory rather
    than in a custom_id, and a stale copy left open simply writes what it was showing."""

    def __init__(self, event_id: str, roster: list[Signup]) -> None:
        super().__init__(timeout=600)
        self.names = {signup.discord_id: signup.display_name for signup in roster}
        self.add_item(_AttendeesSelect(event_id, roster))
        self.add_item(_DeclineSelect(event_id, roster))


def _named(view: ui.View, discord_ids: list[str]) -> str:
    """The players a picker just wrote about, by name. An organizer's edit is the room's news, so the
    answer names them rather than counting them. Callers post nothing for an empty pick, since the
    ticks can be cleared and a message naming nobody is worse than silence."""
    return ", ".join(view.names.get(discord_id, discord_id) for discord_id in discord_ids)


class _AttendeesSelect(ui.Select):
    def __init__(self, event_id: str, roster: list[Signup]) -> None:
        shown = roster[:SELECT_LIMIT]
        options = [
            discord.SelectOption(
                label=signup.display_name[:100], value=signup.discord_id, default=signup.confirmed,
            )
            for signup in shown
        ]
        super().__init__(
            placeholder=MSG_ATTENDEES_PLACEHOLDER, options=options,
            min_values=0, max_values=len(options),
        )
        self.event_id = event_id
        self.asked_about = [signup.discord_id for signup in shown]
        if len(roster) > SELECT_LIMIT:
            log.warning(
                f"pod-attendees: {self.event_id} has {len(roster)} signups; "
                f"the picker shows the first {SELECT_LIMIT}"
            )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await asyncio.to_thread(
            set_confirmations_sync, self.event_id, self.values, self.asked_about,
        )
        if not self.values:
            return
        await interaction.followup.send(
            MSG_ATTENDEES_SAVED.format(
                actor=interaction.user.display_name, players=_named(self.view, self.values),
            ),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        run_detached(
            refresh_or_repost_roster_reminder(self.event_id),
            f"the roster card after an attendance edit on {self.event_id}",
        )


class MovePlayersButton(
    ui.DynamicItem[ui.Button], template=rf"{MOVE_BUTTON_PREFIX}:(?P<event_id>.+)",
):
    """The overview card's one control, once a pod has split. The tick list on the held card decided who
    was coming; this one decides where they sit, which is only a question once there is more than one
    table to sit at. Labelled, since an unlabelled 📋 on a card of finished tables reads as decoration."""

    def __init__(self, event_id: str) -> None:
        super().__init__(ui.Button(
            style=discord.ButtonStyle.secondary, emoji="📋", label=MSG_MOVE_PLAYERS_BUTTON,
            custom_id=f"{MOVE_BUTTON_PREFIX}:{event_id}",
        ))
        self.event_id = event_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: ui.Button, match: re.Match):
        return cls(match["event_id"])

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await is_pod_organizer(interaction.client, interaction.user):
            await interaction.response.send_message(MSG_NOT_ORGANIZER_MOVE, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        family = await asyncio.to_thread(pod_family_sync, self.event_id)
        seated = await asyncio.gather(*(
            asyncio.to_thread(confirmed_first_roster_sync, pod.event_id) for pod in family
        ))
        players = [
            (signup, pod.index) for pod, roster in zip(family, seated) for signup in roster
        ]
        if len(family) < 2 or not players:
            await interaction.followup.send(MSG_ATTENDEES_EMPTY, ephemeral=True)
            return
        await interaction.followup.send(
            MSG_MOVE_LEAD, view=_MoveView(family, players), ephemeral=True,
        )


def build_tables_map_items(event_id: str) -> list[ui.Item]:
    """Move Players, carried by the map of the tables in the thread everybody is in. It sat on the
    overview card in the channel, a scroll away from the tables it moves people between."""
    return [MovePlayersButton(event_id)]


class _MoveView(ui.View):
    """Players, then a table, then Move. Two selects cannot answer together, so each one records what it
    was given and the button is what reads both."""

    def __init__(self, family: list[FamilyPod], players: list[tuple[Signup, int]]) -> None:
        super().__init__(timeout=600)
        self.family = family
        self.names = {signup.discord_id: signup.display_name for signup, _ in players}
        self.chosen_players: list[str] = []
        self.chosen_table: str | None = None
        self.add_item(_MovePlayerSelect(players))
        self.add_item(_MoveTableSelect(family))
        self.add_item(_MoveApplyButton())


class _MovePlayerSelect(ui.Select):
    def __init__(self, players: list[tuple[Signup, int]]) -> None:
        super().__init__(
            placeholder=MSG_MOVE_PLAYERS_PLACEHOLDER,
            options=[
                discord.SelectOption(
                    label=signup.display_name[:100], value=signup.discord_id,
                    description=MSG_TABLE_SEATED.format(index=index),
                )
                for signup, index in players[:SELECT_LIMIT]
            ],
            min_values=1, max_values=min(len(players), SELECT_LIMIT),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.chosen_players = list(self.values)
        await interaction.response.defer()


class _MoveTableSelect(ui.Select):
    def __init__(self, family: list[FamilyPod]) -> None:
        super().__init__(
            placeholder=MSG_MOVE_TABLE_PLACEHOLDER,
            options=[
                discord.SelectOption(label=pod.name[:100], value=pod.event_id)
                for pod in family[:SELECT_LIMIT]
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.chosen_table = self.values[0]
        await interaction.response.defer()


class _MoveApplyButton(ui.Button):
    def __init__(self) -> None:
        super().__init__(style=discord.ButtonStyle.primary, label=MSG_MOVE_BUTTON)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: _MoveView = self.view
        if not view.chosen_players or view.chosen_table is None:
            await interaction.response.send_message(MSG_MOVE_NOTHING_PICKED, ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        target = next(pod for pod in view.family if pod.event_id == view.chosen_table)
        await asyncio.to_thread(
            move_players_sync, [pod.event_id for pod in view.family], target.event_id,
            view.chosen_players,
        )
        await interaction.followup.send(
            MSG_MOVE_DONE.format(
                actor=interaction.user.display_name, players=_named(view, view.chosen_players),
                index=target.index,
            ),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        run_detached(
            _tell_the_table_who_joined(interaction, target, view.chosen_players),
            f"the move onto table {target.index}",
        )


async def _tell_the_table_who_joined(
    interaction: discord.Interaction, target: FamilyPod, discord_ids: list[str],
) -> None:
    """Name the moved players in the table they now belong to, which both tells them and subscribes them
    to its thread. A move nobody is told about is a roster edit the players never act on."""
    if not target.thread_id:
        return
    thread = interaction.client.get_channel(int(target.thread_id))
    if not isinstance(thread, discord.Thread):
        return
    mentions = " ".join(f"<@{discord_id}>" for discord_id in discord_ids if discord_id.isdigit())
    if not mentions:
        return
    with contextlib.suppress(discord.HTTPException):
        await thread.send(
            MSG_STAGED_POD_SEATS.format(index=target.index, mentions=mentions),
            allowed_mentions=discord.AllowedMentions(users=True),
        )


class _DeclineSelect(ui.Select):
    """The answer only a player normally gives, in the organizer's hands.

    Somebody who says in the thread that they cannot make it and never presses Leave otherwise holds a
    seat nobody can take. Ticking them here records the No they meant, which is a different act from
    unticking them above: unticking says the pod has not heard from them, this says it has."""

    def __init__(self, event_id: str, roster: list[Signup]) -> None:
        super().__init__(
            placeholder=MSG_DECLINE_PLACEHOLDER,
            options=[
                discord.SelectOption(label=signup.display_name[:100], value=signup.discord_id)
                for signup in roster[:SELECT_LIMIT]
            ],
            min_values=0, max_values=min(len(roster), SELECT_LIMIT),
        )
        self.event_id = event_id

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await asyncio.to_thread(decline_players_sync, self.event_id, self.values)
        if not self.values:
            return
        await interaction.followup.send(
            MSG_DECLINE_DONE.format(
                actor=interaction.user.display_name, players=_named(self.view, self.values),
            ),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        run_detached(
            refresh_or_repost_roster_reminder(self.event_id),
            f"the roster card after a decline on {self.event_id}",
        )
