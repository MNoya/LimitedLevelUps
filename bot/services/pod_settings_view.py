"""Combined pod-draft lobby Settings panel: draft format + pairing mode + seats in one ephemeral view.

Picking an option applies it, re-renders the panel (all dropdowns kept, the changed one defaulted),
and posts a public thread notice — so the confirmation everyone sees lives in the channel, not in the
private ephemeral. The Seat Order button is contextual to Manual seats + a live lobby.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Awaitable, Callable

import discord
from discord import ui

from bot import emojis
from bot.commands.messages import MSG_RESTART_NOT_ORGANIZER
from bot.config import settings
from bot.services.pod_format import (
    default_pick_timer_for, format_change_message, settings_change_message, settings_notice_marker,
    settings_notice_markers,
)
from bot.services.pod_notices import send_settings_notice
from bot.services.pod_drafts import is_championship
from bot.services.pod_registration_embed import update_registered_embed
from bot.services.pod_format_select import SELECT_PLACEHOLDER as FORMAT_PLACEHOLDER
from bot.services.pod_format_select import WRITE_IN_VALUE as FORMAT_WRITE_IN_VALUE
from bot.services.pod_format_select import FormatWriteInModal, format_options
from bot.services.pod_pairing_select import SELECT_PLACEHOLDER as PAIRING_PLACEHOLDER
from bot.services.pod_pairing_select import pairing_change_message, pairing_options
from bot.services.pod_seating_select import (
    SEATING_SELECT_PLACEHOLDER,
    SeatedNotify,
    SeatingApply,
    SeatOrderButton,
    SeatOrderProvider,
    seating_mode_change_message,
    seating_mode_options,
)
from bot.services.pod_tournament import actor_label, is_pod_organizer
from bot.services.pod_schedule import SCHEDULE_TZ
from bot.discord_helpers import run_detached
from bot.sets import active_set_code


Apply = Callable[[discord.Interaction, str], Awaitable[str | None]]
KickApply = Callable[[discord.Interaction, str], Awaitable[str | None]]
KickTargetsProvider = Callable[[], list[tuple[str, str]]]
LinkApply = Callable[[discord.Interaction, str, discord.abc.User], Awaitable[str | None]]
LinkTargetsProvider = Callable[[], Awaitable[list[str]]]
CancelApply = Callable[[discord.Interaction], Awaitable[str | None]]
DescriptionApply = Callable[[discord.Interaction, str | None], Awaitable[None]]
EventNameApply = Callable[[discord.Interaction, str], Awaitable[None]]

LINK_SEAT_PROMPT = "Pick the unlinked Draftmancer seat to assign:"

CANCEL_PROMPT = (
    "This permanently deletes **{name}**: participants, matches, replays and the leaderboard page. "
    "This can't be undone"
)
CANCEL_PROMPT_MOCK = "This closes **{name}** and deletes its draft page"

RESTART_PROMPT = "This stops the draft and reopens the lobby. Every pick made so far is lost"

TIMER_FIELD = "Seconds Per Pick"
PACKS_FIELD = "Packs Per Player"
CARDS_PER_PACK_FIELD = "Cards Per Pack"

TIMER_MIN = 10
TIMER_MAX = 600

PICKS_PER_PACK_MIN = 1
PICKS_PER_PACK_MAX = 2

PACKS_MIN = 1
PACKS_MAX = 12

CARDS_PER_PACK_MIN = 1
CARDS_PER_PACK_MAX = 30

MAX_PLAYERS_OPTIONS = (6, 8, 10)

DESCRIPTION_MAX_LEN = 300

EVENT_NAME_MAX_LEN = 100


def kick_notice(actor: str, name: str) -> str:
    return f"🔨 **{name}** was removed by {actor}"


def link_notice(actor: str, member_mention: str, arena_name: str) -> str:
    return f"🔗 {member_mention} linked to `{arena_name}` by {actor}"


def cancel_notice(actor: str) -> str:
    return f"{actor} canceled the draft"


def timer_notice(actor: str, seconds: int) -> str:
    return settings_change_message(actor, "Pick timer", f"{seconds}s")


def pick_timer_label(seconds: int | None) -> str:
    """Button label for a pod's pick timer, always showing a concrete number: an unset timer falls
    back to the configured default that a set/cube pod draws at session open."""
    return f"Pick Timer: {seconds if seconds is not None else settings.pod_draft_pick_timer}s"


def draft_setup_label(seconds: int | None) -> str:
    return f"Draft Setup: {seconds if seconds is not None else settings.pod_draft_pick_timer}s"


def draft_setup_notice(actor: str, changed: list[tuple[str, int]]) -> str:
    """One notice per submit, however many fields moved, in the order the modal asks for them."""
    parts = ", ".join(f"**{value}** {label}" for label, value in changed)
    return f"⚙️ **{actor}** set {parts}"


def pick_mode_name(picks: int | None) -> str:
    """How many cards a player takes from each pack, named the way the pod is announced."""
    count = picks if picks is not None else settings.pod_draft_picks_per_pack
    return "Pick Two" if count > PICKS_PER_PACK_MIN else "Pick One"


def picks_per_pack_label(picks: int | None) -> str:
    return f"Mode: {pick_mode_name(picks)}"


def picks_per_pack_notice(actor: str, picks: int) -> str:
    return settings_change_message(actor, "Mode", pick_mode_name(picks))


def max_players_notice(actor: str, count: int) -> str:
    return settings_change_message(actor, "Max Players", str(count))


def closed_decklist_notice(actor: str, closed: bool) -> str:
    subtext = ("Decklists and the draft logs stay hidden on the website until the pod finishes"
               if closed else "Decklists and the draft log show on the website now")
    return settings_change_message(actor, "Closed Decklist", "On" if closed else "Off", subtext=subtext)


def description_notice(actor: str, text: str | None) -> str:
    """The note can be several lines; the notice collapses it to one so the thread reads as a log."""
    value = " ".join(text.split()) if text else "none"
    return settings_change_message(actor, "Description", value)


def description_label(current: str | None) -> str:
    return "Description ✓" if current else "Description"


def event_name_notice(actor: str, name: str) -> str:
    return settings_change_message(actor, "Name", name)


class PodSettingsView(ui.View):
    def __init__(self, *, on_format: Apply | None = None, on_pairing: Apply | None = None,
                 current_code: str | None = None, current_mode: str | None = None,
                 on_seating_mode: Apply | None = None, current_seating: str | None = None,
                 on_seating: SeatingApply | None = None,
                 seat_order_provider: SeatOrderProvider | None = None,
                 on_seating_table: Callable[[discord.Interaction], Awaitable[None]] | None = None,
                 on_seated: SeatedNotify | None = None,
                 on_timer: Apply | None = None, current_timer: int | None = None,
                 on_packs: Apply | None = None, current_packs: int | None = None,
                 on_cards_per_pack: Apply | None = None, current_cards_per_pack: int | None = None,
                 cube_format: bool = False,
                 on_picks_per_pack: Apply | None = None, current_picks_per_pack: int | None = None,
                 on_max_players: Apply | None = None, current_max_players: int | None = None,
                 kick_targets_provider: KickTargetsProvider | None = None,
                 on_kick: KickApply | None = None,
                 link_targets_provider: LinkTargetsProvider | None = None,
                 on_link: LinkApply | None = None,
                 on_manage_rounds: Callable[[discord.Interaction], Awaitable[None]] | None = None,
                 on_restart: CancelApply | None = None,
                 on_cancel: CancelApply | None = None,
                 on_reschedule: Apply | None = None, current_start: datetime | None = None,
                 on_description: DescriptionApply | None = None, current_description: str | None = None,
                 on_event_name: EventNameApply | None = None,
                 on_closed_decklist: Apply | None = None, current_closed_decklist: bool = False,
                 event_name: str | None = None, mock: bool = False,
                 notice_channel: discord.abc.Messageable | None = None) -> None:
        super().__init__(timeout=300)
        self.notice_channel = notice_channel
        self.on_format = on_format
        self.on_pairing = on_pairing
        self.current_code = current_code
        self.current_mode = current_mode
        self.on_seating_mode = on_seating_mode
        self.current_seating = current_seating
        self.on_seating = on_seating
        self.seat_order_provider = seat_order_provider
        self.on_seating_table = on_seating_table
        self.on_seated = on_seated
        self.on_timer = on_timer
        self.current_timer = current_timer
        self.on_packs = on_packs
        self.current_packs = current_packs
        self.on_cards_per_pack = on_cards_per_pack
        self.current_cards_per_pack = current_cards_per_pack
        self.cube_format = cube_format
        self.on_picks_per_pack = on_picks_per_pack
        self.current_picks_per_pack = current_picks_per_pack
        self.on_max_players = on_max_players
        self.current_max_players = current_max_players
        self.kick_targets_provider = kick_targets_provider
        self.on_kick = on_kick
        self.link_targets_provider = link_targets_provider
        self.on_link = on_link
        self.on_manage_rounds = on_manage_rounds
        self.on_restart = on_restart
        self.on_cancel = on_cancel
        self.on_reschedule = on_reschedule
        self.current_start = current_start
        self.on_description = on_description
        self.current_description = current_description
        self.on_event_name = on_event_name
        self.on_closed_decklist = on_closed_decklist
        self.current_closed_decklist = current_closed_decklist
        self.event_name = event_name
        self.mock = mock
        if on_format is not None:
            self.add_item(_FormatSetting(current_code))
        if on_pairing is not None:
            self.add_item(_PairingSetting(current_mode))
        if on_seating_mode is not None:
            self.add_item(_SeatingSetting(current_seating))
        if (on_seating is not None and seat_order_provider is not None
                and (current_seating or "random") == "manual"):
            self.add_item(SeatOrderButton(
                seat_order_provider=seat_order_provider, on_seating=on_seating, on_seated=on_seated, row=3))
        if on_timer is not None:
            self.add_item(_DraftSetupButton(current_timer, row=3))
        if on_max_players is not None:
            self.add_item(_MaxPlayersButton(current_max_players, row=3))
        if link_targets_provider is not None and on_link is not None:
            self.add_item(_LinkPlayersButton(row=3))
        if kick_targets_provider is not None and on_kick is not None:
            self.add_item(_KickPlayerButton(row=3))
        if on_picks_per_pack is not None:
            self.add_item(_PicksPerPackButton(current_picks_per_pack, row=4))
        if on_manage_rounds is not None:
            self.add_item(_ManageRoundsButton(row=4))
        if on_closed_decklist is not None:
            self.add_item(_ClosedDecklistButton(current_closed_decklist, row=self._settings_row))
        if on_description is not None:
            self.add_item(_DetailsButton(row=4))
        if on_reschedule is not None:
            self.add_item(_RescheduleButton(row=4))
        if on_restart is not None:
            self.add_item(_RestartDraftButton(row=4))
        if on_cancel is not None:
            self.add_item(_CancelDraftButton(row=4))

    @property
    def _settings_row(self) -> int:
        """Where a plain setting sits. The pick-options row empties out when the draft starts, so once it
        does the settings move up to it and leave the last row to the two buttons that end a draft."""
        return 4 if self.on_timer is not None else 3

    @property
    def pick_timer(self) -> int:
        return self.current_timer if self.current_timer is not None else settings.pod_draft_pick_timer

    @property
    def picks_per_pack(self) -> int:
        if self.current_picks_per_pack is not None:
            return self.current_picks_per_pack
        return settings.pod_draft_picks_per_pack

    async def apply(self, interaction: discord.Interaction, *, on_apply: Apply,
                    value: str, attr: str, notice: str, marker: str | Sequence[str]) -> None:
        if await self._commit(interaction, on_apply, attr, value):
            await self._render(interaction, [(notice, marker)])

    async def _commit(self, interaction: discord.Interaction, on_apply: Apply,
                      attr: str, value: str) -> bool:
        """Defer, persist one setting, and store it on the view. False on error so the caller stops."""
        await interaction.response.defer()
        err = await on_apply(interaction, value)
        if err:
            await interaction.followup.send(f"⚠️ {err}", ephemeral=True)
            return False
        setattr(self, attr, value)
        return True

    async def _render(self, interaction: discord.Interaction,
                      notices: list[tuple[str, str | Sequence[str]]]) -> None:
        """Rebuild the panel from the view's current state, post each thread notice, refresh the card."""
        await interaction.edit_original_response(view=PodSettingsView(
            on_format=self.on_format, on_pairing=self.on_pairing,
            current_code=self.current_code, current_mode=self.current_mode,
            on_seating_mode=self.on_seating_mode, current_seating=self.current_seating,
            on_seating=self.on_seating, seat_order_provider=self.seat_order_provider,
            on_seating_table=self.on_seating_table, on_seated=self.on_seated,
            on_timer=self.on_timer, current_timer=self.current_timer,
            on_packs=self.on_packs, current_packs=self.current_packs,
            on_cards_per_pack=self.on_cards_per_pack,
            current_cards_per_pack=self.current_cards_per_pack,
            cube_format=self.cube_format,
            on_picks_per_pack=self.on_picks_per_pack,
            current_picks_per_pack=self.current_picks_per_pack,
            on_max_players=self.on_max_players, current_max_players=self.current_max_players,
            kick_targets_provider=self.kick_targets_provider, on_kick=self.on_kick,
            link_targets_provider=self.link_targets_provider, on_link=self.on_link,
            on_manage_rounds=self.on_manage_rounds, on_restart=self.on_restart,
            on_cancel=self.on_cancel, on_reschedule=self.on_reschedule, current_start=self.current_start,
            on_description=self.on_description, current_description=self.current_description,
            on_event_name=self.on_event_name,
            on_closed_decklist=self.on_closed_decklist,
            current_closed_decklist=self.current_closed_decklist,
            event_name=self.event_name, mock=self.mock,
            notice_channel=self.notice_channel,
        ))
        channel = self.notice_channel or interaction.channel
        if channel is not None:
            for text, mark in notices:
                await send_settings_notice(channel, interaction.client.user, text, marker=mark)
        await update_registered_embed(
            channel,
            client_user=interaction.client.user,
            set_code=self.current_code or active_set_code(),
            pairing_mode=self.current_mode,
            seating_mode=self.current_seating,
            championship=is_championship(self.event_name),
        )

    async def _apply_closed_decklist(self, interaction: discord.Interaction, closed: bool) -> None:
        await interaction.response.defer()
        err = await self.on_closed_decklist(interaction, "1" if closed else "0")
        if err:
            await interaction.followup.send(f"⚠️ {err}", ephemeral=True)
            return
        self.current_closed_decklist = closed
        notice = closed_decklist_notice(actor_label(interaction), closed)
        await self._render(interaction, [(notice, settings_notice_marker("Closed Decklist"))])

    async def _apply_details(self, interaction: discord.Interaction, name: str | None,
                             text: str | None) -> None:
        """Commit the Details modal: rename the pod when the name changed, and store the note. Each part
        posts its own thread notice so a change reads as one line whichever field moved."""
        await interaction.response.defer()
        actor = actor_label(interaction)
        notices: list[tuple[str, str]] = []
        if self.on_event_name is not None and name and name != self.event_name:
            await self.on_event_name(interaction, name)
            self.event_name = name
            notices.append((event_name_notice(actor, name), settings_notice_marker("Name")))
        if text != self.current_description:
            await self.on_description(interaction, text)
            self.current_description = text
            notices.append((description_notice(actor, text), settings_notice_marker("Description")))
        if notices:
            await self._render(interaction, notices)

    async def _apply_format_code(self, interaction: discord.Interaction, code: str) -> None:
        if not await self._commit(interaction, self.on_format, "current_code", code):
            return
        notices = [(format_change_message(actor_label(interaction), code), settings_notice_marker("Format"))]
        timer = await self._couple_pick_timer(interaction)
        if timer is not None:
            notices.append(timer)
        await self._render(interaction, notices)

    async def _couple_pick_timer(self, interaction: discord.Interaction) -> tuple[str, str] | None:
        """Move the pick timer to the switched-to format's default, so both controls track the format
        together. No-op when the timer control is absent or already at the target."""
        if self.on_timer is None:
            return None
        target = default_pick_timer_for(self.current_code, standard=settings.pod_draft_pick_timer)
        if target == self.current_timer:
            return None
        err = await self.on_timer(interaction, str(target))
        if err is not None:
            return None
        self.current_timer = target
        return timer_notice(actor_label(interaction), target), settings_notice_marker("Pick timer")

    async def _apply_draft_setup(self, interaction: discord.Interaction, *, seconds: int | None,
                                 packs: int | None, cards_per_pack: int | None) -> None:
        """Commit whatever the Draft Setup modal changed. Each setting is pushed on its own so one that
        Draftmancer refuses leaves the others applied, and the ones that land are reported together on a
        single line, which retires the earlier notice of every setting it names."""
        await interaction.response.defer()
        pending = [
            (seconds, self.on_timer, "current_timer", TIMER_FIELD),
            (packs, self.on_packs, "current_packs", PACKS_FIELD),
            (cards_per_pack, self.on_cards_per_pack, "current_cards_per_pack", CARDS_PER_PACK_FIELD),
        ]
        changed: list[tuple[str, int]] = []
        for value, apply, attr, label in pending:
            if value is None or apply is None:
                continue
            error = await apply(interaction, str(value))
            if error:
                await interaction.followup.send(f"⚠️ {error}", ephemeral=True)
                continue
            setattr(self, attr, value)
            changed.append((label, value))
        if not changed:
            return
        notice = draft_setup_notice(actor_label(interaction), changed)
        await self._render(interaction, [(notice, [label for label, _ in changed])])

    async def _apply_picks_per_pack(self, interaction: discord.Interaction, picks: int) -> None:
        await interaction.response.defer()
        error = await self.on_picks_per_pack(interaction, str(picks))
        if error:
            await interaction.followup.send(f"⚠️ {error}", ephemeral=True)
            return
        self.current_picks_per_pack = picks
        notice = picks_per_pack_notice(actor_label(interaction), picks)
        await self._render(interaction, [(notice, settings_notice_marker("Mode"))])


class _FormatSetting(ui.Select):
    def __init__(self, current_code: str | None) -> None:
        super().__init__(placeholder=FORMAT_PLACEHOLDER, options=format_options(current_code),
                         min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: PodSettingsView = self.view
        code = self.values[0]
        if code == FORMAT_WRITE_IN_VALUE:
            await interaction.response.send_modal(FormatWriteInModal(view._apply_format_code))
            return
        await view._apply_format_code(interaction, code)


class _PairingSetting(ui.Select):
    def __init__(self, current_mode: str | None) -> None:
        super().__init__(placeholder=PAIRING_PLACEHOLDER, options=pairing_options(current_mode),
                         min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: PodSettingsView = self.view
        mode = self.values[0]
        await view.apply(interaction, on_apply=view.on_pairing, value=mode, attr="current_mode",
                         notice=pairing_change_message(actor_label(interaction), mode),
                         marker=settings_notice_markers("Pairings"))


class _SeatingSetting(ui.Select):
    def __init__(self, current_seating: str | None) -> None:
        super().__init__(placeholder=SEATING_SELECT_PLACEHOLDER, options=seating_mode_options(current_seating),
                         min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: PodSettingsView = self.view
        mode = self.values[0]
        await view.apply(interaction, on_apply=view.on_seating_mode, value=mode, attr="current_seating",
                         notice=seating_mode_change_message(actor_label(interaction), mode),
                         marker=settings_notice_marker("Seats"))
        if mode == "leaderboard" and view.on_seating_table is not None:
            await view.on_seating_table(interaction)


class _DraftSetupButton(ui.Button):
    def __init__(self, current_timer: int | None, row: int | None = None) -> None:
        super().__init__(label=draft_setup_label(current_timer), emoji="🎛️",
                         style=discord.ButtonStyle.grey, row=row)

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(_DraftSetupModal(self.view))


def parse_setting_field(raw: str, current: int | None, *, minimum: int, maximum: int,
                        label: str) -> tuple[int | None, str | None]:
    """Read one Draft Setup field as (value to apply, error). A blank field and a field left at its
    prefilled value both apply nothing, the second so a pod already configured outside the range does
    not trap the organizer in a modal it refuses to submit."""
    text = raw.strip()
    if not text:
        return None, None
    if not text.isdigit():
        return None, f"{label} takes a number between {minimum} and {maximum}."
    value = int(text)
    if value == current:
        return None, None
    if not minimum <= value <= maximum:
        return None, f"{label} takes a number between {minimum} and {maximum}."
    return value, None


class _DraftSetupModal(ui.Modal, title="Draft Setup"):
    """Cards Per Pack is a cube-only field: Draftmancer reads it from the custom card list, and a set
    draft takes its pack from the set's own collation. Both pack fields open blank on a pod nobody has
    set them on, since the number in force is Draftmancer's and prefilling ours would state a value we
    don't know."""

    def __init__(self, view: PodSettingsView) -> None:
        super().__init__()
        self.view = view
        self.seconds = ui.TextInput(
            label=TIMER_FIELD, placeholder="e.g. 60", default=str(view.pick_timer),
            min_length=1, max_length=3)
        self.add_item(self.seconds)
        self.packs = ui.TextInput(
            label=PACKS_FIELD, placeholder="e.g. 4", required=False, max_length=2,
            default=str(view.current_packs) if view.current_packs is not None else None)
        self.add_item(self.packs)
        self.cards = None
        if view.cube_format:
            self.cards = ui.TextInput(
                label=CARDS_PER_PACK_FIELD, placeholder="e.g. 12", required=False, max_length=2,
                default=str(view.current_cards_per_pack) if view.current_cards_per_pack is not None else None)
            self.add_item(self.cards)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        seconds, timer_error = parse_setting_field(
            self.seconds.value, self.view.pick_timer,
            minimum=TIMER_MIN, maximum=TIMER_MAX, label=TIMER_FIELD)
        packs, packs_error = parse_setting_field(
            self.packs.value, self.view.current_packs,
            minimum=PACKS_MIN, maximum=PACKS_MAX, label=PACKS_FIELD)
        cards, cards_error = (None, None)
        if self.cards is not None:
            cards, cards_error = parse_setting_field(
                self.cards.value, self.view.current_cards_per_pack,
                minimum=CARDS_PER_PACK_MIN, maximum=CARDS_PER_PACK_MAX, label=CARDS_PER_PACK_FIELD)
        errors = [error for error in (timer_error, packs_error, cards_error) if error]
        if errors:
            await interaction.response.send_message("⚠️ " + "\n".join(errors), ephemeral=True)
            return
        await self.view._apply_draft_setup(
            interaction, seconds=seconds, packs=packs, cards_per_pack=cards)


class _PicksPerPackButton(ui.Button):
    """Pick One / Pick Two as a toggle, since two is the only alternative to the standard one card per
    pack. Green while on, so a pod running the variant reads as changed at a glance."""

    def __init__(self, current_picks: int | None, row: int | None = None) -> None:
        pick_two = pick_mode_name(current_picks) == "Pick Two"
        super().__init__(
            label=picks_per_pack_label(current_picks), emoji="🃏", row=row,
            style=discord.ButtonStyle.success if pick_two else discord.ButtonStyle.grey,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: PodSettingsView = self.view
        toggled = PICKS_PER_PACK_MIN if view.picks_per_pack > PICKS_PER_PACK_MIN else PICKS_PER_PACK_MAX
        await view._apply_picks_per_pack(interaction, toggled)


class _MaxPlayersButton(ui.Button):
    def __init__(self, current_max_players: int | None, row: int | None = None) -> None:
        count = current_max_players if current_max_players is not None else settings.pod_draft_max_players
        super().__init__(label="Max Players", emoji=emojis.get_emoji(f"mana{int(count)}"),
                         style=discord.ButtonStyle.grey, row=row)

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            "Table Size", view=_MaxPlayersSelectView(self.view), ephemeral=True,
        )


class _MaxPlayersSelectView(ui.View):
    def __init__(self, panel: PodSettingsView) -> None:
        super().__init__(timeout=120)
        self.add_item(_MaxPlayersSelect(panel))


class _MaxPlayersSelect(ui.Select):
    def __init__(self, panel: PodSettingsView) -> None:
        current = panel.current_max_players
        options = [
            discord.SelectOption(
                label=f"{count} Players", value=str(count), emoji=emojis.get_emoji(f"mana{count}"),
                default=str(count) == str(current),
            )
            for count in MAX_PLAYERS_OPTIONS
        ]
        super().__init__(placeholder="Table Size", options=options, min_values=1, max_values=1)
        self.panel = panel

    async def callback(self, interaction: discord.Interaction) -> None:
        count = int(self.values[0])
        await interaction.response.defer()
        err = await self.panel.on_max_players(interaction, str(count))
        if err:
            await interaction.followup.send(f"⚠️ {err}", ephemeral=True)
            return
        self.panel.current_max_players = count
        await interaction.delete_original_response()
        channel = self.panel.notice_channel or interaction.channel
        if channel is not None:
            await send_settings_notice(
                channel, interaction.client.user,
                max_players_notice(actor_label(interaction), count),
                marker=settings_notice_marker("Max Players"),
            )


class _ClosedDecklistButton(ui.Button):
    def __init__(self, closed: bool, row: int | None = None) -> None:
        super().__init__(
            label=f"Closed Decklist: {'On' if closed else 'Off'}",
            emoji="🔒" if closed else "🔓", style=discord.ButtonStyle.grey, row=row,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.view._apply_closed_decklist(interaction, not self.view.current_closed_decklist)


class PodDescriptionModal(ui.Modal, title="Pod description"):
    """The organizer's note held by the /draft launcher until the pod exists. The live Settings panel
    edits the note through PodDetailsModal, which also renames the pod."""

    text = ui.TextInput(
        label="Description", style=discord.TextStyle.paragraph, required=False,
        max_length=DESCRIPTION_MAX_LEN,
        placeholder="Optional note shown on the pod card and its discussion thread")

    def __init__(self, current: str | None, apply: DescriptionApply) -> None:
        super().__init__()
        self.apply = apply
        if current:
            self.text.default = current

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.apply(interaction, self.text.value.strip() or None)


class _DetailsButton(ui.Button):
    def __init__(self, row: int | None = None) -> None:
        super().__init__(label="Details", emoji="📝", style=discord.ButtonStyle.grey, row=row)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: PodSettingsView = self.view
        await interaction.response.send_modal(PodDetailsModal(view))


class PodDetailsModal(ui.Modal, title="Pod details"):
    """Rename a pod and edit its note before the draft starts. The discussion thread follows the name."""

    def __init__(self, view: "PodSettingsView") -> None:
        super().__init__()
        self.view = view
        self.name: ui.TextInput | None = None
        if view.on_event_name is not None:
            self.name = ui.TextInput(
                label="Name", style=discord.TextStyle.short, required=True,
                max_length=EVENT_NAME_MAX_LEN, default=view.event_name or None,
                placeholder="Shown on the pod card and its discussion thread")
            self.add_item(self.name)
        self.description = ui.TextInput(
            label="Description", style=discord.TextStyle.paragraph, required=False,
            max_length=DESCRIPTION_MAX_LEN, default=view.current_description or None,
            placeholder="Optional note shown on the pod card and its discussion thread")
        self.add_item(self.description)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        name = " ".join(self.name.value.split()) if self.name is not None else None
        text = self.description.value.strip() or None
        await self.view._apply_details(interaction, name, text)


class _RescheduleButton(ui.Button):
    def __init__(self, row: int | None = None) -> None:
        super().__init__(label="Reschedule", emoji="🕐", style=discord.ButtonStyle.grey, row=row)

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(_RescheduleModal(self.view))


def reschedule_help(current_start: datetime | None = None) -> str:
    hours = int(datetime.now(SCHEDULE_TZ).utcoffset().total_seconds() // 3600)
    current = ""
    if current_start is not None:
        local = current_start.astimezone(SCHEDULE_TZ)
        current = f" ({local.strftime('%-I:%M %p')})"
    return (
        f"**Set the new start in Eastern Time (GMT {hours:+d})**\n"
        f"- `+1h` or `-30m` to move the current start{current}\n"
        "- `11am`, `9 PM`, `21:00` sets a time today\n"
        "- `today 11am`, `tomorrow 8:30pm`, `fri 7pm` sets day and time"
    )


class _RescheduleModal(ui.Modal, title="Reschedule pod"):
    new_time = ui.TextInput(
        label="New start (ET)", placeholder="+1h, -30m, 11am, today 9pm, tomorrow 8:30pm", max_length=32)

    def __init__(self, view: PodSettingsView) -> None:
        super().__init__()
        self.view = view
        self.remove_item(self.new_time)
        self.add_item(ui.TextDisplay(reschedule_help(view.current_start)))
        self.add_item(self.new_time)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        err = await self.view.on_reschedule(interaction, self.new_time.value)
        if err:
            await interaction.followup.send(f"⚠️ {err}", ephemeral=True)


class _ManageRoundsButton(ui.Button):
    """Post-draft route into the round pairing editor. The round messages carry the same editor behind
    a 🔧, except on a ten-player pod, whose rounds fill every dropdown row and leave it no space."""

    def __init__(self, row: int | None = None) -> None:
        super().__init__(label="Manage Rounds", emoji="🔧", style=discord.ButtonStyle.grey, row=row)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: PodSettingsView = self.view
        await view.on_manage_rounds(interaction)


class _KickPlayerButton(ui.Button):
    def __init__(self, row: int | None = None) -> None:
        super().__init__(label="Kick Player", emoji="🔨", style=discord.ButtonStyle.grey, row=row)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: PodSettingsView = self.view
        targets = view.kick_targets_provider()
        if not targets:
            await interaction.response.send_message(
                "No players or spectators in the Draftmancer session", ephemeral=True,
            )
            return
        await interaction.response.send_message(
            view=_KickSelectView(targets, view.on_kick), ephemeral=True,
        )


class _KickSelectView(ui.View):
    def __init__(self, targets: list[tuple[str, str]], on_kick: KickApply) -> None:
        super().__init__(timeout=120)
        self.add_item(_KickSelect(targets, on_kick))


class _KickSelect(ui.Select):
    def __init__(self, targets: list[tuple[str, str]], on_kick: KickApply) -> None:
        options = [discord.SelectOption(label=name, value=user_id) for user_id, name in targets[:25]]
        super().__init__(placeholder="Remove a player or spectator from the table", options=options,
                         min_values=1, max_values=1)
        self.names = dict(targets)
        self.on_kick = on_kick

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        user_id = self.values[0]
        name = self.names.get(user_id, "player")
        err = await self.on_kick(interaction, user_id)
        if err:
            await interaction.followup.send(f"⚠️ {err}", ephemeral=True)
            return
        await interaction.delete_original_response()
        await interaction.channel.send(kick_notice(actor_label(interaction), name))


class _LinkPlayersButton(ui.Button):
    def __init__(self, row: int | None = None) -> None:
        super().__init__(label="Link Players", emoji="🔗", style=discord.ButtonStyle.grey, row=row)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: PodSettingsView = self.view
        targets = await view.link_targets_provider()
        if not targets:
            await interaction.response.send_message(
                "Everyone in the Draftmancer session is already linked", ephemeral=True,
            )
            return
        await interaction.response.send_message(
            LINK_SEAT_PROMPT,
            view=LinkSeatSelectView(targets, view.on_link), ephemeral=True,
        )


class LinkSeatSelectView(ui.View):
    """Single-panel seat→member link picker, shared by the Settings 'Link Players' button and the
    ready-check unlinked-seat confirm so an organizer can bind a stray seat from either spot. Picking a
    seat reveals the guild-wide member picker and a Confirm button below it — both dropdowns stay visible
    and the link commits only on Confirm, so a misclick can't silently bind the wrong person."""

    def __init__(self, targets: list[str], on_link: LinkApply) -> None:
        super().__init__(timeout=120)
        self.targets = targets
        self.on_link = on_link
        self.selected_seat: str | None = None
        self.selected_member: discord.abc.User | None = None
        self._render()

    def _render(self) -> None:
        self.clear_items()
        self.add_item(_LinkSeatSelect(self.targets, self.selected_seat))
        if self.selected_seat is not None:
            self.add_item(_LinkMemberSelect(self.selected_member))
            self.add_item(_LinkConfirmButton())

    def _content(self) -> str:
        if self.selected_seat is None:
            return LINK_SEAT_PROMPT
        return f"Pick who `{self.selected_seat}` is, then press Confirm."

    async def refresh(self, interaction: discord.Interaction) -> None:
        self._render()
        await interaction.response.edit_message(
            content=self._content(), view=self, allowed_mentions=discord.AllowedMentions.none(),
        )


class _LinkSeatSelect(ui.Select):
    def __init__(self, targets: list[str], selected: str | None) -> None:
        options = [
            discord.SelectOption(label=name, value=name, default=name == selected) for name in targets[:25]
        ]
        super().__init__(placeholder="Unlinked Draftmancer seat", options=options,
                         min_values=1, max_values=1, row=0)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: LinkSeatSelectView = self.view
        view.selected_seat = self.values[0]
        await view.refresh(interaction)


class _LinkMemberSelect(ui.UserSelect):
    def __init__(self, selected: discord.abc.User | None) -> None:
        super().__init__(placeholder="Pick the Discord member", min_values=1, max_values=1, row=1,
                         default_values=[selected] if selected is not None else [])

    async def callback(self, interaction: discord.Interaction) -> None:
        view: LinkSeatSelectView = self.view
        view.selected_member = self.values[0]
        await interaction.response.defer()


class _LinkConfirmButton(ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Confirm", style=discord.ButtonStyle.success, emoji="🔗", row=2)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: LinkSeatSelectView = self.view
        if view.selected_seat is None or view.selected_member is None:
            await interaction.response.send_message(
                "Pick a seat and a member first", ephemeral=True,
            )
            return
        member = view.selected_member
        arena_name = view.selected_seat
        await interaction.response.defer()
        err = await view.on_link(interaction, arena_name, member)
        if err:
            await interaction.followup.send(f"⚠️ {err}", ephemeral=True)
            return
        await interaction.edit_original_response(
            content=f"🔗 **{member.display_name}** linked as `{arena_name}`", view=None,
        )
        await interaction.channel.send(
            link_notice(actor_label(interaction), member.mention, arena_name),
            allowed_mentions=discord.AllowedMentions(users=True),
        )


class _RestartDraftButton(ui.Button):
    """Stop a draft that went wrong and deal the table again. Open to anyone on a mock draft, the same
    way its Cancel Draft is, and to organizers on a pod whose matches other people are waiting on."""

    def __init__(self, row: int | None = None) -> None:
        super().__init__(label="Restart Draft", emoji="♻️", style=discord.ButtonStyle.danger, row=row)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: PodSettingsView = self.view
        if not view.mock and not await is_pod_organizer(interaction.client, interaction.user):
            await interaction.response.send_message(MSG_RESTART_NOT_ORGANIZER, ephemeral=True)
            return
        await interaction.response.send_message(
            RESTART_PROMPT,
            view=_RestartConfirmView(view.on_restart, view.notice_channel),
            ephemeral=True,
        )


class _RestartConfirmView(ui.View):
    """The restart itself announces the actor in the thread, so the confirm only reports back."""

    def __init__(self, on_restart: CancelApply,
                 notice_channel: discord.abc.Messageable | None = None) -> None:
        super().__init__(timeout=60)
        self.on_restart = on_restart
        self.notice_channel = notice_channel

    @ui.button(label="Restart Draft", style=discord.ButtonStyle.danger, emoji="♻️")
    async def confirm(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.defer()
        err = await self.on_restart(interaction)
        if err:
            await interaction.followup.send(f"⚠️ {err}", ephemeral=True)
            return
        await interaction.edit_original_response(content="♻️ Draft stopped", view=None)


class _CancelDraftButton(ui.Button):
    def __init__(self, row: int | None = None) -> None:
        super().__init__(label="Cancel Draft", emoji="🗑️", style=discord.ButtonStyle.danger, row=row)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: PodSettingsView = self.view
        event_name = view.event_name or "this pod draft"
        prompt = CANCEL_PROMPT_MOCK if view.mock else CANCEL_PROMPT
        await interaction.response.send_message(
            prompt.format(name=event_name),
            view=_CancelConfirmView(view.on_cancel, event_name, view.notice_channel),
            ephemeral=True,
        )


class _CancelConfirmView(ui.View):
    def __init__(
        self, on_cancel: CancelApply, event_name: str,
        notice_channel: discord.abc.Messageable | None = None,
    ) -> None:
        super().__init__(timeout=60)
        self.on_cancel = on_cancel
        self.event_name = event_name
        self.notice_channel = notice_channel

    @ui.button(label="Delete Event", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.edit_message(content=f"🗑️ **{self.event_name}** deleted", view=None)
        run_detached(self._tear_down(interaction), f"the pod cancel from {interaction.user.id}")

    async def _tear_down(self, interaction: discord.Interaction) -> None:
        err = await self.on_cancel(interaction)
        if err:
            await interaction.followup.send(f"⚠️ {err}", ephemeral=True)
            return
        channel = self.notice_channel or interaction.channel
        if channel is not None:
            await channel.send(cancel_notice(actor_label(interaction)))
