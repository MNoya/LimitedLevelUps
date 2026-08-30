"""The buttons on the schedule card and the organizer override wizard behind the gear.

The Vote button opens the season format vote when the window is live. The gear opens the override for pod
organizers, who pick a day, a slot and the formats it runs, writing a manual overlay row the weekly allocator
never overwrites, so the card redraws with the change at once. Everyone else is pointed at the organizers.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import discord
from discord import ui

from bot import emojis
from bot.commands.messages import MSG_ORGANIZER_ONLY_SETTINGS
from bot.database import SessionLocal
from bot.discord_helpers import run_detached
from bot.services import pod_format_interest as fi
from bot.services.championship_dates import plan_for, vote_opens_at, voting_open
from bot.services.pod_format import custom_formats
from bot.services.pod_format_poll import normalize_write_ins
from bot.services.pod_format_schedule import LATEST, set_slot
from bot.services.pod_format_vote import send_vote_panel
from bot.services.pod_schedule import SCHEDULE_TZ
from bot.services.pod_schedule_card import refresh_schedule_post
from bot.services.pod_signals import SLOT_EARLY, SLOT_LATE
from bot.services.ping_roles import ORGANIZER_ROLE_NAME, organizer_mention
from bot.tasks.pod_daily_poll import retarget_launcher_day
from bot.sets import active_set_code, flashback_picker_sets, set_name_for

log = logging.getLogger(__name__)

SLOT_BOTH = "BOTH"
MSG_VOTE_SOON = "Format voting opens soon"
MSG_VOTE_OPENS_AT = "Format voting opens <t:{unix}:R>"
MSG_OVERRIDE_PROMPT = "Override the schedule for a pod"
MSG_OVERRIDE_WITH_WRITE_INS = "{prompt}\nWrite-ins: {codes}"
MSG_PICK_DAY_POD = "Choose a day and a pod first"
MSG_WRITE_IN_TITLE = "Add Format(s)"
MSG_WRITE_IN_FIELD = "Set Codes"
MSG_WRITE_IN_PLACEHOLDER = "e.g. DSK FIN MH3"

_SLOT_LABELS = {SLOT_EARLY: "Early Pod", SLOT_LATE: "Late Pod", SLOT_BOTH: "both pods"}


class PodScheduleView(ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @ui.button(label="Vote Formats", emoji="🗳️", style=discord.ButtonStyle.primary, custom_id="pod_schedule:vote")
    async def vote(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if not voting_open():
            await interaction.response.send_message(_vote_closed_message(), ephemeral=True)
            return
        await send_vote_panel(interaction)

    @ui.button(emoji="⚙️", style=discord.ButtonStyle.secondary, custom_id="pod_schedule:config")
    async def config(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if not await _is_organizer(interaction):
            await interaction.response.send_message(
                MSG_ORGANIZER_ONLY_SETTINGS.format(organizer=organizer_mention(interaction.guild)),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            MSG_OVERRIDE_PROMPT, view=PodScheduleOverrideView(), ephemeral=True,
        )


def _vote_closed_message() -> str:
    plan = plan_for()
    if plan is None:
        return MSG_VOTE_SOON
    return MSG_VOTE_OPENS_AT.format(unix=int(vote_opens_at(plan).timestamp()))


async def _is_organizer(interaction: discord.Interaction) -> bool:
    if await interaction.client.is_owner(interaction.user):
        return True
    member = interaction.user if isinstance(interaction.user, discord.Member) else None
    if member is None:
        return False
    if member.guild_permissions.administrator:
        return True
    return any(role.name == ORGANIZER_ROLE_NAME for role in member.roles)


class PodScheduleOverrideView(ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=300)
        self.day: str | None = None
        self.slot_key: str | None = None
        self.picked: list[str] = []
        self.written: list[str] = []
        self.add_item(DaySelect())
        self.add_item(SlotSelect())
        self.add_item(FormatsSelect())

    def formats(self) -> list[str]:
        return self.picked + [code for code in self.written if code not in self.picked]

    def prompt(self) -> str:
        if not self.written:
            return MSG_OVERRIDE_PROMPT
        chips = " ".join(_write_in_chip(code) for code in self.written)
        return MSG_OVERRIDE_WITH_WRITE_INS.format(prompt=MSG_OVERRIDE_PROMPT, codes=chips)

    @ui.button(label="Add Format", emoji="➕", style=discord.ButtonStyle.primary, row=3)
    async def add_format(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.send_modal(OverrideWriteInModal(self))

    @ui.button(label="Apply Override", emoji="✅", style=discord.ButtonStyle.success, row=3)
    async def apply(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if self.day is None or self.slot_key is None:
            await interaction.response.send_message(MSG_PICK_DAY_POD, ephemeral=True)
            return
        formats = self.formats()
        day = datetime.fromisoformat(self.day).date()
        slot_keys = (SLOT_EARLY, SLOT_LATE) if self.slot_key == SLOT_BOTH else (self.slot_key,)
        with SessionLocal() as session:
            for slot_key in slot_keys:
                set_slot(session, day, slot_key, formats, decided_by=str(interaction.user.id))
            session.commit()
        await interaction.response.edit_message(content=self._confirmation(day, formats), view=None)
        await refresh_schedule_post(interaction.channel, view=PodScheduleView())
        run_detached(retarget_launcher_day(interaction.client, day), label="schedule-override-retarget")

    def _confirmation(self, day, formats: list[str]) -> str:
        slot_label = _SLOT_LABELS[self.slot_key]
        day_label = day.strftime("%A %-d %b")
        if not formats:
            return f"Closed {slot_label} on {day_label}"
        names = ", ".join("Latest Set" if code == LATEST else code for code in formats)
        return f"Set {slot_label} on {day_label} to {names}"


class OverrideWriteInModal(ui.Modal, title=MSG_WRITE_IN_TITLE):
    codes = ui.TextInput(label=MSG_WRITE_IN_FIELD, placeholder=MSG_WRITE_IN_PLACEHOLDER, min_length=2, max_length=100)

    def __init__(self, view: PodScheduleOverrideView) -> None:
        super().__init__()
        self._view = view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        for code in normalize_write_ins(str(self.codes.value)):
            if code not in self._view.written:
                self._view.written.append(code)
        await interaction.response.edit_message(content=self._view.prompt(), view=self._view)


class DaySelect(ui.Select):
    def __init__(self) -> None:
        super().__init__(placeholder="Day", options=_day_options(), min_values=1, max_values=1, row=0)

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.day = self.values[0]
        await interaction.response.defer()


class SlotSelect(ui.Select):
    def __init__(self) -> None:
        options = [
            discord.SelectOption(label="Early Pod", value=SLOT_EARLY),
            discord.SelectOption(label="Late Pod", value=SLOT_LATE),
            discord.SelectOption(label="Both", value=SLOT_BOTH),
        ]
        super().__init__(placeholder="Slot", options=options, min_values=1, max_values=1, row=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.slot_key = self.values[0]
        await interaction.response.defer()


class FormatsSelect(ui.Select):
    def __init__(self) -> None:
        options = _format_options()
        super().__init__(
            placeholder="Formats (leave empty to close)", options=options,
            min_values=0, max_values=min(len(options), 4), row=2,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.picked = list(self.values)
        await interaction.response.defer()


def _write_in_chip(code: str) -> str:
    symbol = emojis.set_symbol(code)
    prefix = f"{symbol} " if symbol is not None else ""
    return f"{prefix}**{code}**"


def _day_options() -> list[discord.SelectOption]:
    today = datetime.now(SCHEDULE_TZ).date()
    return [
        discord.SelectOption(label=(today + timedelta(days=offset)).strftime("%A %-d %b"),
                             value=(today + timedelta(days=offset)).isoformat())
        for offset in range(14)
    ]


def _format_options() -> list[discord.SelectOption]:
    active = active_set_code()
    options = [discord.SelectOption(
        label="Latest Set", value=LATEST, description=set_name_for(active),
        emoji=emojis.set_symbol(active),
    )]
    for fmt in custom_formats():
        options.append(discord.SelectOption(
            label=fmt.label, value=fmt.code, description=f"CubeCobra: {fmt.cube_id}",
            emoji=emojis.set_symbol(fmt.code) or fi.cube_emoji(),
        ))
    for seed in flashback_picker_sets():
        options.append(discord.SelectOption(
            label=seed.code, value=seed.code, description=set_name_for(seed.code),
            emoji=emojis.set_symbol(seed.code),
        ))
    return options
