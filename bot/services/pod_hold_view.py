"""The organizer's controls on a busy pod that holds for attendance.

📋 on the held card opens a private tick list of the roster, so someone in the room can record what the
buttons could not, and while the pod is holding it also carries a Feature On Table 1 picker that pins a
player to the first table the split opens. Open Tables ends the wait early, which is the same release the
start time would have run.

Both carry the event id in their custom_id, so they keep working after a restart. They are rendered greyed
out once the tables open, and a press that slips through the moment before that edit lands is acknowledged
and dropped.

What a picker records is news the channel sends itself. A followup would post as a reply to the private
picker, which the room reads as a reply to a deleted message.
"""
from __future__ import annotations

import asyncio
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
    MSG_FEATURE_DONE,
    MSG_FEATURE_PLACEHOLDER,
    MSG_NOT_ORGANIZER_ATTENDEES,
    MSG_NOT_ORGANIZER_TABLES,
    MSG_OPEN_TABLES_BUTTON,
    MSG_OPEN_TABLES_DONE,
)
from bot.discord_helpers import run_detached
from bot.services.pod_confirm import decline_players_sync, set_confirmations_sync
from bot.services.pod_launch import cancel_release, is_holding, release_attendance_hold
from bot.services.pod_staging import (
    Signup,
    confirmed_first_roster_sync,
    is_featured,
    set_feature_sync,
    unfeatured_name,
)
from bot.services.pod_tournament import is_pod_organizer
from bot.tasks.pod_draft_reminder import refresh_or_repost_roster_reminder


ATTENDEES_BUTTON_PREFIX = "podattendees"
OPEN_TABLES_BUTTON_PREFIX = "podopentables"
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
            MSG_ATTENDEES_LEAD,
            view=_AttendeesView(self.event_id, roster, featuring=is_holding(self.event_id)),
            ephemeral=True,
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

    The tick list spans the whole confirmation window and carries the Feature On Table 1 picker while the
    pod is holding; opening the tables is the hold's own act and needs a hold to end. Both grey out
    afterwards rather than vanishing, and Discord refuses a disabled press, so neither needs copy saying
    the moment has passed."""
    items: list[ui.Item] = []
    if confirming or held:
        items.append(AttendeesButton(event_id, disabled=held and not holding))
    if held:
        items.append(OpenTablesButton(event_id, disabled=not holding))
    return items


class _AttendeesView(ui.View):
    """The private tick list. It is ephemeral and short-lived, so it holds the roster in memory rather
    than in a custom_id, and a stale copy left open simply writes what it was showing."""

    def __init__(self, event_id: str, roster: list[Signup], *, featuring: bool) -> None:
        super().__init__(timeout=600)
        self.names = {signup.discord_id: unfeatured_name(signup.display_name) for signup in roster}
        self.add_item(_AttendeesSelect(event_id, roster))
        self.add_item(_DeclineSelect(event_id, roster))
        if featuring:
            self.add_item(_FeatureSelect(event_id, roster))


def _named(view: ui.View, discord_ids: list[str]) -> str:
    """The players a picker just wrote about, by name. An organizer's edit is the room's news, so the
    answer names them rather than counting them. Callers post nothing for an empty pick, since the
    ticks can be cleared and a message naming nobody is worse than silence."""
    return ", ".join(view.names.get(discord_id, discord_id) for discord_id in discord_ids)


def _and_named(view: ui.View, discord_ids: list[str]) -> str:
    """Like _named, joined for a sentence: one name alone, two with 'and', more with commas and a final 'and'"""
    names = [view.names.get(discord_id, discord_id) for discord_id in discord_ids]
    if len(names) <= 1:
        return names[0] if names else ""
    return f"{', '.join(names[:-1])} and {names[-1]}"


class _AttendeesSelect(ui.Select):
    def __init__(self, event_id: str, roster: list[Signup]) -> None:
        shown = roster[:SELECT_LIMIT]
        options = [
            discord.SelectOption(
                label=unfeatured_name(signup.display_name)[:100], value=signup.discord_id,
                default=signup.confirmed,
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
        await interaction.channel.send(
            MSG_ATTENDEES_SAVED.format(
                actor=interaction.user.display_name, players=_named(self.view, self.values),
            ),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        run_detached(
            refresh_or_repost_roster_reminder(self.event_id),
            f"the roster card after an attendance edit on {self.event_id}",
        )


class _FeatureSelect(ui.Select):
    """Pin players to Table 1 so the release seats them at the first table it opens. Carried by the tick
    list only while the pod is holding, since a pod that will not split has one table to seat everyone."""

    def __init__(self, event_id: str, roster: list[Signup]) -> None:
        shown = roster[:SELECT_LIMIT]
        super().__init__(
            placeholder=MSG_FEATURE_PLACEHOLDER,
            options=[
                discord.SelectOption(
                    label=unfeatured_name(signup.display_name)[:100], value=signup.discord_id,
                    default=is_featured(signup.display_name),
                )
                for signup in shown
            ],
            min_values=0, max_values=len(shown),
        )
        self.event_id = event_id

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await asyncio.to_thread(set_feature_sync, self.event_id, self.values)
        if not self.values:
            return
        await interaction.channel.send(
            MSG_FEATURE_DONE.format(
                actor=interaction.user.display_name, players=_and_named(self.view, self.values),
            ),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        run_detached(
            refresh_or_repost_roster_reminder(self.event_id),
            f"the roster card after a feature edit on {self.event_id}",
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
                discord.SelectOption(label=unfeatured_name(signup.display_name)[:100], value=signup.discord_id)
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
        await interaction.channel.send(
            MSG_DECLINE_DONE.format(
                actor=interaction.user.display_name, players=_named(self.view, self.values),
            ),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        run_detached(
            refresh_or_repost_roster_reminder(self.event_id),
            f"the roster card after a decline on {self.event_id}",
        )
