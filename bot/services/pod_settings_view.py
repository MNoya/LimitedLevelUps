"""Combined pod-draft lobby Settings panel: draft format + pairing mode + seats in one ephemeral view.

Picking an option applies it, re-renders the panel (all dropdowns kept, the changed one defaulted),
and posts a public thread notice — so the confirmation everyone sees lives in the channel, not in the
private ephemeral. The Seat Order button is contextual to Manual seats + a live lobby.
"""
from __future__ import annotations

from typing import Awaitable, Callable

import discord
from discord import ui

from bot import emojis
from bot.config import settings
from bot.services.pod_format import (
    default_pick_timer_for, format_change_message, settings_change_message, settings_notice_marker,
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
from bot.services.pod_tournament import actor_label
from bot.sets import active_set_code


Apply = Callable[[discord.Interaction, str], Awaitable[str | None]]
KickApply = Callable[[discord.Interaction, str], Awaitable[str | None]]
KickTargetsProvider = Callable[[], list[tuple[str, str]]]
LinkApply = Callable[[discord.Interaction, str, discord.abc.User], Awaitable[str | None]]
LinkTargetsProvider = Callable[[], Awaitable[list[str]]]
CancelApply = Callable[[discord.Interaction], Awaitable[str | None]]
DescriptionApply = Callable[[discord.Interaction, str | None], Awaitable[None]]

LINK_SEAT_PROMPT = "Pick the unlinked Draftmancer seat to assign:"

TIMER_MIN = 10
TIMER_MAX = 600

PICKS_PER_PACK_MIN = 1
PICKS_PER_PACK_MAX = 2

MAX_PLAYERS_OPTIONS = (8, 10)

DESCRIPTION_MAX_LEN = 300


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


def picks_per_pack_notice(actor: str, picks: int) -> str:
    return settings_change_message(actor, "Picks Per Pack", str(picks))


def pick_options_label(seconds: int | None, picks: int | None) -> str:
    """Button label for the pick controls. The pick count only shows once it leaves the standard one
    card per pack, so the common pod reads as a plain timer."""
    timer = seconds if seconds is not None else settings.pod_draft_pick_timer
    count = picks if picks is not None else settings.pod_draft_picks_per_pack
    if count > 1:
        return f"Pick Options: {timer}s, Pick {count}"
    return f"Pick Options: {timer}s"


def max_players_notice(actor: str, count: int) -> str:
    return settings_change_message(actor, "Max players", str(count))


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


class PodSettingsView(ui.View):
    def __init__(self, *, on_format: Apply | None = None, on_pairing: Apply | None = None,
                 current_code: str | None = None, current_mode: str | None = None,
                 on_seating_mode: Apply | None = None, current_seating: str | None = None,
                 on_seating: SeatingApply | None = None,
                 seat_order_provider: SeatOrderProvider | None = None,
                 on_seating_table: Callable[[discord.Interaction], Awaitable[None]] | None = None,
                 on_seated: SeatedNotify | None = None,
                 on_timer: Apply | None = None, current_timer: int | None = None,
                 on_picks_per_pack: Apply | None = None, current_picks_per_pack: int | None = None,
                 on_max_players: Apply | None = None, current_max_players: int | None = None,
                 kick_targets_provider: KickTargetsProvider | None = None,
                 on_kick: KickApply | None = None,
                 link_targets_provider: LinkTargetsProvider | None = None,
                 on_link: LinkApply | None = None,
                 on_cancel: CancelApply | None = None,
                 on_reschedule: Apply | None = None,
                 on_description: DescriptionApply | None = None, current_description: str | None = None,
                 on_closed_decklist: Apply | None = None, current_closed_decklist: bool = False,
                 event_name: str | None = None,
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
        self.on_picks_per_pack = on_picks_per_pack
        self.current_picks_per_pack = current_picks_per_pack
        self.on_max_players = on_max_players
        self.current_max_players = current_max_players
        self.kick_targets_provider = kick_targets_provider
        self.on_kick = on_kick
        self.link_targets_provider = link_targets_provider
        self.on_link = on_link
        self.on_cancel = on_cancel
        self.on_reschedule = on_reschedule
        self.on_description = on_description
        self.current_description = current_description
        self.on_closed_decklist = on_closed_decklist
        self.current_closed_decklist = current_closed_decklist
        self.event_name = event_name
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
            self.add_item(_PickOptionsButton(current_timer, current_picks_per_pack, row=3))
        if on_max_players is not None:
            self.add_item(_MaxPlayersButton(current_max_players, row=3))
        if link_targets_provider is not None and on_link is not None:
            self.add_item(_LinkPlayersButton(row=3))
        if kick_targets_provider is not None and on_kick is not None:
            self.add_item(_KickPlayerButton(row=3))
        if on_closed_decklist is not None:
            self.add_item(_ClosedDecklistButton(current_closed_decklist, row=4))
        if on_description is not None:
            self.add_item(_DescriptionButton(current_description, row=4))
        if on_reschedule is not None:
            self.add_item(_RescheduleButton(row=4))
        if on_cancel is not None:
            self.add_item(_CancelDraftButton(row=4))

    @property
    def pick_timer(self) -> int:
        return self.current_timer if self.current_timer is not None else settings.pod_draft_pick_timer

    @property
    def picks_per_pack(self) -> int:
        if self.current_picks_per_pack is not None:
            return self.current_picks_per_pack
        return settings.pod_draft_picks_per_pack

    async def apply(self, interaction: discord.Interaction, *, on_apply: Apply,
                    value: str, attr: str, notice: str, marker: str) -> None:
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
                      notices: list[tuple[str, str]]) -> None:
        """Rebuild the panel from the view's current state, post each thread notice, refresh the card."""
        await interaction.edit_original_response(view=PodSettingsView(
            on_format=self.on_format, on_pairing=self.on_pairing,
            current_code=self.current_code, current_mode=self.current_mode,
            on_seating_mode=self.on_seating_mode, current_seating=self.current_seating,
            on_seating=self.on_seating, seat_order_provider=self.seat_order_provider,
            on_seating_table=self.on_seating_table, on_seated=self.on_seated,
            on_timer=self.on_timer, current_timer=self.current_timer,
            on_picks_per_pack=self.on_picks_per_pack,
            current_picks_per_pack=self.current_picks_per_pack,
            on_max_players=self.on_max_players, current_max_players=self.current_max_players,
            kick_targets_provider=self.kick_targets_provider, on_kick=self.on_kick,
            link_targets_provider=self.link_targets_provider, on_link=self.on_link,
            on_cancel=self.on_cancel, on_reschedule=self.on_reschedule,
            on_description=self.on_description, current_description=self.current_description,
            on_closed_decklist=self.on_closed_decklist,
            current_closed_decklist=self.current_closed_decklist,
            event_name=self.event_name,
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

    async def _apply_description(self, interaction: discord.Interaction, text: str | None) -> None:
        await interaction.response.defer()
        await self.on_description(interaction, text)
        self.current_description = text
        notice = description_notice(actor_label(interaction), text)
        await self._render(interaction, [(notice, settings_notice_marker("Description"))])

    async def _apply_format_code(self, interaction: discord.Interaction, code: str) -> None:
        if not await self._commit(interaction, self.on_format, "current_code", code):
            return
        notices = [(format_change_message(actor_label(interaction), code), settings_notice_marker("Format"))]
        timer = await self._couple_pick_timer(interaction)
        if timer is not None:
            notices.append(timer)
        await self._render(interaction, notices)

    async def _couple_pick_timer(self, interaction: discord.Interaction) -> tuple[str, str] | None:
        """Move the pick timer to the switched-to format's default (75s for an older set, the standard
        clock for the latest set or a cube), so both controls track the format together. No-op when the
        timer control is absent or already at the target."""
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

    async def _apply_pick_options(self, interaction: discord.Interaction,
                                  seconds: int, picks: int | None) -> None:
        """Apply both pick controls from the one modal, noticing only the values that moved. The panel
        re-renders around whatever was accepted, so a failure on the second control still shows the
        first one applied."""
        await interaction.response.defer()
        notices: list[tuple[str, str]] = []
        error = None
        if seconds != self.pick_timer:
            error = await self.on_timer(interaction, str(seconds))
            if error is None:
                self.current_timer = seconds
                notices.append((timer_notice(actor_label(interaction), seconds),
                                settings_notice_marker("Pick timer")))
        if error is None and picks is not None and picks != self.picks_per_pack:
            error = await self.on_picks_per_pack(interaction, str(picks))
            if error is None:
                self.current_picks_per_pack = picks
                notices.append((picks_per_pack_notice(actor_label(interaction), picks),
                                settings_notice_marker("Picks Per Pack")))
        await self._render(interaction, notices)
        if error:
            await interaction.followup.send(f"⚠️ {error}", ephemeral=True)


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
                         marker=settings_notice_marker("Pairings"))


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


class _PickOptionsButton(ui.Button):
    def __init__(self, current_timer: int | None, current_picks: int | None,
                 row: int | None = None) -> None:
        super().__init__(label=pick_options_label(current_timer, current_picks), emoji="⏱️",
                         style=discord.ButtonStyle.grey, row=row)

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(_PickOptionsModal(self.view))


class _PickOptionsModal(ui.Modal, title="Pick Options"):
    """Both pick controls in one modal. Picks Per Pack only appears when the panel can apply it, so a
    pod without a live session never offers a field that would refuse."""

    def __init__(self, view: PodSettingsView) -> None:
        super().__init__()
        self.view = view
        self.seconds = ui.TextInput(
            label="Seconds Per Pick", placeholder="e.g. 60", default=str(view.pick_timer),
            min_length=1, max_length=3)
        self.add_item(self.seconds)
        self.picks: ui.TextInput | None = None
        if view.on_picks_per_pack is not None:
            self.picks = ui.TextInput(
                label="Picks Per Pack", placeholder="1 or 2", default=str(view.picks_per_pack),
                min_length=1, max_length=1)
            self.add_item(self.picks)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        seconds = self.seconds.value.strip()
        if not seconds.isdigit() or not (TIMER_MIN <= int(seconds) <= TIMER_MAX):
            await interaction.response.send_message(
                f"⚠️ Enter a whole number of seconds between {TIMER_MIN} and {TIMER_MAX}.", ephemeral=True,
            )
            return
        picks = None
        if self.picks is not None:
            raw = self.picks.value.strip()
            if not raw.isdigit() or not (PICKS_PER_PACK_MIN <= int(raw) <= PICKS_PER_PACK_MAX):
                await interaction.response.send_message(
                    f"⚠️ Enter {PICKS_PER_PACK_MIN} or {PICKS_PER_PACK_MAX} picks per pack.", ephemeral=True,
                )
                return
            picks = int(raw)
        await self.view._apply_pick_options(interaction, int(seconds), picks)


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


class _DescriptionButton(ui.Button):
    def __init__(self, current: str | None, row: int | None = None) -> None:
        super().__init__(label=description_label(current), emoji="📝",
                         style=discord.ButtonStyle.grey, row=row)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: PodSettingsView = self.view
        await interaction.response.send_modal(
            PodDescriptionModal(view.current_description, view._apply_description))


class PodDescriptionModal(ui.Modal, title="Pod description"):
    """The organizer's note on a pod card. Shared by the /draft launcher, which holds the text until the
    pod exists, and the Settings panel, which persists it on a live pod."""

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


class _RescheduleButton(ui.Button):
    def __init__(self, row: int | None = None) -> None:
        super().__init__(label="Reschedule", emoji="🕐", style=discord.ButtonStyle.grey, row=row)

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(_RescheduleModal(self.view))


class _RescheduleModal(ui.Modal, title="Reschedule pod"):
    new_time = ui.TextInput(
        label="New start (time from now, or ET time)", placeholder="1h, 21:00, or 2026-07-18 21:00")

    def __init__(self, view: PodSettingsView) -> None:
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        err = await self.view.on_reschedule(interaction, self.new_time.value)
        if err:
            await interaction.followup.send(f"⚠️ {err}", ephemeral=True)


class _KickPlayerButton(ui.Button):
    def __init__(self, row: int | None = None) -> None:
        super().__init__(label="Kick Player", emoji="🔨", style=discord.ButtonStyle.grey, row=row)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: PodSettingsView = self.view
        targets = view.kick_targets_provider()
        if not targets:
            await interaction.response.send_message(
                "No players or spectators in the Draftmancer session.", ephemeral=True,
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
        if interaction.channel is not None:
            await interaction.channel.send(kick_notice(actor_label(interaction), name))


class _LinkPlayersButton(ui.Button):
    def __init__(self, row: int | None = None) -> None:
        super().__init__(label="Link Players", emoji="🔗", style=discord.ButtonStyle.grey, row=row)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: PodSettingsView = self.view
        targets = await view.link_targets_provider()
        if not targets:
            await interaction.response.send_message(
                "Everyone in the Draftmancer session is already linked.", ephemeral=True,
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
                "Pick a seat and a member first.", ephemeral=True,
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
            content=f"🔗 **{member.display_name}** linked as `{arena_name}`.", view=None,
        )
        if interaction.channel is not None:
            await interaction.channel.send(
                link_notice(actor_label(interaction), member.mention, arena_name),
                allowed_mentions=discord.AllowedMentions(users=True),
            )


class _CancelDraftButton(ui.Button):
    def __init__(self, row: int | None = None) -> None:
        super().__init__(label="Cancel Draft", emoji="🗑️", style=discord.ButtonStyle.danger, row=row)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: PodSettingsView = self.view
        event_name = view.event_name or "this pod draft"
        await interaction.response.send_message(
            f"This permanently deletes **{event_name}** — participants, matches, replays, and the "
            "leaderboard page. This can't be undone.",
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
        await interaction.response.defer()
        err = await self.on_cancel(interaction)
        if err:
            await interaction.followup.send(f"⚠️ {err}", ephemeral=True)
            return
        await interaction.edit_original_response(content=f"🗑️ **{self.event_name}** deleted.", view=None)
        channel = self.notice_channel or interaction.channel
        if channel is not None:
            await channel.send(cancel_notice(actor_label(interaction)))
