"""Lobby embed renderer for pod-draft events.

Shared between `!test` (sandbox) and the live `PodDraftManager` so both produce the same
visual. The Ready Check button is a persistent View (stable custom_id) registered once at
startup; clicks dispatch to the active manager for the thread.
"""
from __future__ import annotations

import asyncio
import logging
import re

import discord

from bot import emojis
from bot.commands import descriptions as desc
from bot.discord_helpers import add_two_column_field, command_line, plural, quote_block
from bot.services import pod_team
from bot.services.pod_active import active_manager_for_channel
from bot.services.ping_roles import format_join_line
from bot.services.pod_drafts import load_event_id_by_thread_sync, normalize_player_name
from bot.services.pod_roster_fields import marked_new
from bot.services.pod_team_board import TeamBoardMember, add_team_roster_fields
from bot.services.pod_tournament import actor_label, is_pod_organizer


log = logging.getLogger("bot.lobby_embed")

READY_CHECK_CUSTOM_ID = "pod-draft:ready-check"
SETTINGS_CUSTOM_ID = "pod-draft:settings"
FORCE_START_CUSTOM_ID = "pod-draft:force-start"
READY_NOW_CUSTOM_ID = "pod-draft:ready-now"
NOT_READY_CUSTOM_ID = "pod-draft:not-ready"
STOP_CHECK_CUSTOM_ID = "pod-draft:stop-check"

_NO_ACTIVE_POD_MSG = "No active pod-draft session in this thread"
RESUME_READY_CHECK_LABEL = "Resume Ready Check"

MSG_READY_RECORDED = "✅ Ready Check recorded"
MSG_NOT_READY_RECORDED = "⚠️ Ready Check on hold until you press Ready"
MSG_STOP_CHECK_CONFIRM = "Stop Ready Check?"
MSG_CLAIM_SEAT_PROMPT = "Nobody in the Draftmancer lobby matches your Discord name. Pick your seat:"
MSG_NO_SEAT_TO_CLAIM = "You are not in the Draftmancer lobby yet\n{join_line}"
MSG_PREVIEW_ONLY = "Preview only"


class LobbyReadyButtonView(discord.ui.View):
    """The lobby card's controls. `live_check` drops the kickoff button, since a running check is managed from
    its own card, and keeps the players' answers away from Force Start."""

    def __init__(
        self, draftmancer_url: str | None = None, live_check: bool = False,
        show_force_start: bool = False, spectate_url: str | None = None,
    ) -> None:
        super().__init__(timeout=None)
        if live_check:
            self.remove_item(self.ready_check)
        if show_force_start:
            self.add_item(ForceStartButton())
        self.add_item(SettingsButton())
        if draftmancer_url:
            self.add_item(discord.ui.Button(
                label="Join Draftmancer",
                style=discord.ButtonStyle.link,
                url=draftmancer_url,
                emoji=emojis.get_emoji("draftmancer"),
            ))
        if spectate_url:
            self.add_item(discord.ui.Button(
                label="Spectate",
                style=discord.ButtonStyle.link,
                url=spectate_url,
                emoji="👀",
            ))

    @discord.ui.button(
        label="Start Ready Check", style=discord.ButtonStyle.success,
        custom_id=READY_CHECK_CUSTOM_ID,
    )
    async def ready_check(
        self, interaction: discord.Interaction, button: discord.ui.Button,
    ) -> None:
        await start_ready_check_from_button(interaction)


async def start_ready_check_from_button(interaction: discord.Interaction) -> None:
    """Arm or resume a check from whichever card the presser used. Both are one action, since arming keeps
    every answer a seated player already gave."""
    actor = actor_label(interaction)
    manager = await manager_or_reply(interaction, "Ready Check")
    if manager is None:
        return
    log.info(f"[{manager.event_name}] {actor} clicked Ready Check")
    await interaction.response.defer(ephemeral=True)
    thread = await manager._fetch_thread()
    if thread is None:
        return
    if await guard_ready_check(interaction, manager, thread, initiated_by=actor):
        return
    err = await manager.initiate_ready_check(thread, initiated_by=actor, initiator=interaction.user)
    if err:
        await interaction.followup.send(f"⚠️ {err}", ephemeral=True)


class ResumeReadyCheckButton(discord.ui.Button):
    """On a paused check's card, so the way out sits where the pause is explained."""

    def __init__(self) -> None:
        super().__init__(
            label=RESUME_READY_CHECK_LABEL, style=discord.ButtonStyle.primary,
            custom_id=READY_CHECK_CUSTOM_ID,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await start_ready_check_from_button(interaction)


class SettingsButton(discord.ui.Button):
    def __init__(self, label: str | None = "Settings") -> None:
        super().__init__(
            label=label, style=discord.ButtonStyle.grey,
            custom_id=SETTINGS_CUSTOM_ID, emoji="⚙️",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await open_settings_panel(interaction)


class ReadyCheckAnswerView(discord.ui.View):
    """The running check's own card. Force Start stays off it: it ends the check outright, and one row from a
    button eight players are aiming at is the worst place for it."""

    def __init__(self, paused: bool = False) -> None:
        super().__init__(timeout=None)
        self.add_item(ReadyNowButton())
        self.add_item(NotReadyButton())
        if paused:
            self.add_item(ResumeReadyCheckButton())
        self.add_item(StopCheckButton())
        self.add_item(SettingsButton(label=None))


async def manager_or_reply(interaction: discord.Interaction, label: str):
    """The pod behind a click, or None once the presser has been told there isn't one. A card outliving its
    pod is ordinary rather than an error."""
    actor = actor_label(interaction)
    manager = active_manager_for_channel(interaction.channel_id)
    if manager is None:
        log.info(f"{actor} clicked {label} in channel={interaction.channel_id} (no active pod)")
        await interaction.response.send_message(_NO_ACTIVE_POD_MSG, ephemeral=True)
    return manager


class SeatAnswerButton(discord.ui.Button):
    """One player's answer to a running check. Subclasses set `ready`, their own label, and the line the
    presser gets back.

    The answer is confirmed back to the presser rather than left to the check card. A component defer shows
    them nothing, and the card is a shared message the whole pod edits, so under the answer traffic of a full
    table it can trail the press by long enough that players read it as a button that did not work."""

    ready: bool
    recorded: str

    async def callback(self, interaction: discord.Interaction) -> None:
        actor = actor_label(interaction)
        manager = await manager_or_reply(interaction, self.label)
        if manager is None:
            return
        await interaction.response.defer()
        seat_id = await manager.seat_id_for_discord_user(interaction.user)
        if seat_id is None:
            await _offer_seat_claim(interaction, manager, actor)
            return
        log.info(f"[{manager.event_name}] {actor} pressed {self.label}")
        err = await manager.mark_seat(seat_id, ready=self.ready, actor=actor)
        if err:
            await interaction.followup.send(f"⚠️ {err}", ephemeral=True)
            return
        await interaction.followup.send(self.recorded, ephemeral=True)


class ReadyNowButton(SeatAnswerButton):
    """A player's own readiness. Draftmancer's prompt still fires, but its replies arrive over a socket that
    reports a stray Not Ready whenever another popup replaces it, so this is the answer the bot trusts."""

    ready = True
    recorded = MSG_READY_RECORDED

    def __init__(self) -> None:
        super().__init__(
            label="I'm Ready", style=discord.ButtonStyle.success,
            custom_id=READY_NOW_CUSTOM_ID, emoji="✅",
        )


class NotReadyButton(SeatAnswerButton):
    """Say 'wait for me' without killing the check."""

    ready = False
    recorded = MSG_NOT_READY_RECORDED

    def __init__(self) -> None:
        super().__init__(
            label="Not Ready", style=discord.ButtonStyle.danger,
            custom_id=NOT_READY_CUSTOM_ID,
        )


class StopCheckButton(discord.ui.Button):
    """Call the check off, open to anyone in the thread and behind a confirm. Draftmancer exposes no way to
    withdraw its prompt, so a modal left open there answers into a check that is already gone."""

    def __init__(self) -> None:
        super().__init__(
            label="Stop", style=discord.ButtonStyle.grey,
            custom_id=STOP_CHECK_CUSTOM_ID, emoji="⛔",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        manager = await manager_or_reply(interaction, "Stop")
        if manager is None:
            return
        await interaction.response.send_message(
            MSG_STOP_CHECK_CONFIRM, view=StopCheckConfirmView(manager), ephemeral=True,
        )


class StopCheckConfirmView(discord.ui.View):
    def __init__(self, manager) -> None:
        super().__init__(timeout=60)
        self.manager = manager

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        actor = actor_label(interaction)
        log.info(f"[{self.manager.event_name}] {actor} stopped the ready check")
        await interaction.response.defer()
        err = await self.manager.stop_ready_check(actor=actor)
        if err:
            await interaction.edit_original_response(content=f"⚠️ {err}", view=None)
            return
        await interaction.delete_original_response()

    @discord.ui.button(label="Keep Waiting", style=discord.ButtonStyle.grey)
    async def keep(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer()
        await interaction.delete_original_response()


async def _offer_seat_claim(interaction, manager, actor: str) -> None:
    """Nobody matched this presser, so let them name their own seat. Only seats matching no player at all are
    offered, so nobody claims a seat that is already someone's."""
    seats = await manager.unrecognized_lobby_names()
    log.info(f"[{manager.event_name}] {actor} answered the check with no matching seat")
    if not seats:
        join_line = format_join_line(
            manager.session_id, interaction.user.display_name, arena=manager.kind != "mock",
        )
        await interaction.followup.send(
            MSG_NO_SEAT_TO_CLAIM.format(join_line=join_line), ephemeral=True,
        )
        return
    await interaction.followup.send(
        MSG_CLAIM_SEAT_PROMPT, view=ClaimSeatSelectView(manager, seats), ephemeral=True,
    )


class ClaimSeatSelectView(discord.ui.View):
    """Ephemeral 'which seat is you' picker: links the chosen seat to the presser, then counts it ready."""

    def __init__(self, manager, seats: list[str]) -> None:
        super().__init__(timeout=120)
        self.manager = manager
        self.add_item(_ClaimSeatSelect(seats))


class _ClaimSeatSelect(discord.ui.Select):
    def __init__(self, seats: list[str]) -> None:
        super().__init__(
            placeholder="Your Draftmancer Seat",
            options=[discord.SelectOption(label=name, value=name) for name in seats[:25]],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        manager = self.view.manager
        arena_name = self.values[0]
        actor = actor_label(interaction)
        await interaction.response.defer()
        err = await manager.link_seat(interaction.user, arena_name)
        if err:
            await interaction.edit_original_response(content=f"⚠️ {err}", view=None)
            return
        log.info(f"[{manager.event_name}] {actor} claimed seat {arena_name!r} from the ready check")
        seat_id = await manager.seat_id_for_discord_user(interaction.user)
        ready_err = await manager.mark_seat(seat_id, ready=True, actor=actor) if seat_id else None
        if ready_err:
            await interaction.edit_original_response(content=f"⚠️ {ready_err}", view=None)
            return
        await interaction.delete_original_response()


class ForceStartButton(discord.ui.Button):
    """On the lobby card: an understated escape hatch to skip the remaining answers and start the draft,
    behind a confirmation so a stray click can't launch the pod with players away. Deliberately not on the
    ready-check card, which is where players are clicking."""

    def __init__(self) -> None:
        super().__init__(
            label="Force Start", style=discord.ButtonStyle.secondary,
            custom_id=FORCE_START_CUSTOM_ID, emoji="⏭️",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        actor = actor_label(interaction)
        manager = active_manager_for_channel(interaction.channel_id)
        if manager is None:
            if _force_start_preview_factory is not None:
                ready, total, pending = _force_start_preview_factory()
                await interaction.response.send_message(
                    force_start_confirm_text(ready, total, pending),
                    view=ForceStartConfirmView(None), ephemeral=True,
                )
                return
            log.info(f"{actor} clicked Force Start in channel={interaction.channel_id} (no active pod)")
            await interaction.response.send_message(_NO_ACTIVE_POD_MSG, ephemeral=True)
            return
        non_bot = manager.player_session_users()
        total = len(non_bot)
        pending = [u.get("userName") for u in non_bot
                   if u.get("userID") not in manager.ready_users and u.get("userName")]
        ready = total - len(pending)
        log.info(f"[{manager.event_name}] {actor} opened Force Start confirm ({ready}/{total} ready)")
        await interaction.response.send_message(
            force_start_confirm_text(ready, total, pending),
            view=ForceStartConfirmView(manager),
            ephemeral=True,
        )


def force_start_confirm_text(ready: int, total: int, pending: list[str]) -> str:
    """Confirmation prompt for skipping the ready check, naming who'd be left behind. Shared by the live
    Force Start button and the `!test forcestart` preview so the copy never drifts."""
    if pending:
        return (
            f"⏭️ {ready}/{total} ready — still waiting on {', '.join(pending)}.\n"
            "Start the draft now without them?"
        )
    return f"⏭️ {ready}/{total} ready. Start the draft now?"


class ForceStartConfirmView(discord.ui.View):
    def __init__(self, manager) -> None:
        super().__init__(timeout=60)
        self.manager = manager

    @discord.ui.button(label="Start Now", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.manager is None:
            await interaction.response.edit_message(content=MSG_PREVIEW_ONLY, view=None)
            return
        actor = actor_label(interaction)
        log.info(f"[{self.manager.event_name}] {actor} confirmed Force Start")
        await interaction.response.defer()
        err = await self.manager.force_start()
        if err:
            await interaction.edit_original_response(content=f"⚠️ {err}", view=None)
            return
        await interaction.delete_original_response()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(content="Force start canceled", view=None)


READY_CHECK_CONFIRM_PROMPT = "Start the ready check anyway?"
READY_CHECK_TEAM_OFFER = "{count} Players in the Draftmancer lobby, make it a Team Draft?"
KEEP_PAIRINGS_LABEL = "Keep Pairings"


def ready_check_confirm_text(
    seated: int, floor: int, unlinked: list[str], *, pairs: bool = True, team_offer: bool = False,
) -> str:
    """Warn-but-allow prompt shown to the initiator when a ready check is unusual but permitted: a roster
    under the floor, an odd roster that cannot pair, unrecognized seats, or any combination. Shared by the
    live Ready Check button and the `!test` preview so the copy never drifts. `pairs` is False for a mock,
    which plays no rounds and drafts happily at seven. `team_offer` closes on the Team Draft question
    instead, which the buttons answer, so the initiator is never asked two things at once."""
    lines: list[str] = []
    if seated < floor:
        lines.append(f"🛑 Only {seated} player{plural(seated)} in the Draftmancer lobby.")
    if pairs and seated % 2 != 0:
        lines.append(
            "⚠️ Pairings need an even number, so the draft will be refused at start until a player joins "
            "or drops."
        )
    if unlinked:
        names = ", ".join(f"`{name}`" for name in unlinked)
        verb = "is" if len(unlinked) == 1 else "are"
        lines.append(
            f"⚠️ {names} {verb} unrecognized. Bot won't be able to send them pairings.\n"
            "Have them run `/link-arena`, or use Link Players below."
        )
    if team_offer:
        lines.append(READY_CHECK_TEAM_OFFER.format(count=emojis.mana_number(seated)))
    else:
        lines.append(READY_CHECK_CONFIRM_PROMPT)
    return "\n\n".join(lines)


class ReadyCheckConfirmView(discord.ui.View):
    """Ephemeral warn-but-allow gate shown to the initiator when a ready check is unusual but permitted, so a
    short or odd roster can still be readied on purpose instead of leaving Force Start as the only way in.
    `team_offer` adds the Team Draft button a six-player lobby is asked about, which sets the pairings and
    starts the same check; Keep Pairings is the same button as Start Anyway wearing the answer to that
    question."""

    def __init__(
        self, manager, thread, initiated_by: str | None, *, show_link_players: bool = True,
        team_offer: bool = False,
    ) -> None:
        super().__init__(timeout=60)
        self.manager = manager
        self.thread = thread
        self.initiated_by = initiated_by
        if not show_link_players:
            self.remove_item(self.link_players)
        if team_offer:
            self.confirm.label = KEEP_PAIRINGS_LABEL
        else:
            self.remove_item(self.team_draft)

    @discord.ui.button(label="Team Draft", style=discord.ButtonStyle.primary, emoji="🤝")
    async def team_draft(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.manager is None:
            await interaction.response.edit_message(content=MSG_PREVIEW_ONLY, view=None)
            return
        actor = actor_label(interaction)
        log.info(f"[{self.manager.event_name}] {actor} took the Team Draft at the Ready Check")
        await interaction.response.defer()
        err = await self.manager.take_team_draft(actor)
        if err:
            await interaction.edit_original_response(content=f"⚠️ {err}", view=None)
            return
        await self._start_check(interaction)

    @discord.ui.button(label="Start Anyway", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.manager is None:
            await interaction.response.edit_message(content=MSG_PREVIEW_ONLY, view=None)
            return
        actor = actor_label(interaction)
        log.info(f"[{self.manager.event_name}] {actor} confirmed Ready Check past warnings")
        await interaction.response.defer()
        await self._start_check(interaction)

    @discord.ui.button(label="Link Players", style=discord.ButtonStyle.primary, emoji="🔗")
    async def link_players(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        from bot.services.pod_settings_view import LINK_SEAT_PROMPT, LinkSeatSelectView
        if self.manager is None:
            await interaction.response.edit_message(content=MSG_PREVIEW_ONLY, view=None)
            return
        targets = await self.manager.unrecognized_lobby_names()
        if not targets:
            await interaction.response.edit_message(
                content="Everyone's linked now. Press Start Ready Check again", view=None,
            )
            return
        manager = self.manager

        async def on_link(inter: discord.Interaction, arena_name: str, member: discord.abc.User) -> str | None:
            return await manager.link_seat(member, arena_name)

        await interaction.response.edit_message(content=LINK_SEAT_PROMPT, view=LinkSeatSelectView(targets, on_link))

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(content="Ready check canceled", view=None)

    async def _start_check(self, interaction: discord.Interaction) -> None:
        """Fire the check the prompt was gating and clear the prompt, on an already-deferred interaction"""
        err = await self.manager.initiate_ready_check(
            self.thread, initiated_by=self.initiated_by, initiator=interaction.user,
        )
        if err:
            await interaction.edit_original_response(content=f"⚠️ {err}", view=None)
            return
        await interaction.delete_original_response()


async def guard_ready_check(interaction, manager, thread, *, initiated_by, min_players=None) -> bool:
    """Shared ready-check kickoff guard for the lobby button and /pod-ready. Runs the hard blockers, then the
    warn-but-allow confirm covering a short roster, an odd roster, unrecognized seats and the Team Draft a
    six-player lobby is offered, all in one prompt, so confirming never leads straight into a second one.
    Returns True if the interaction was handled here (blocked or awaiting confirm) and the caller should
    stop; False if the pod is clear to start now.
    Runs before /pod-ready acknowledges, so that command can answer publicly once it knows the check will
    actually fire."""
    blocker = manager.ready_check_blocker()
    if blocker:
        await reply_public(interaction, content=f"⚠️ {blocker}")
        return True
    unlinked = [] if manager.kind == "mock" else await manager.unrecognized_lobby_names()
    team_offer = manager.offers_team_draft()
    if manager.ready_check_needs_confirm(unlinked, min_players=min_players) or team_offer:
        await reply_private(
            interaction,
            content=ready_check_confirm_text(
                len(manager.player_session_users()), manager.ready_check_floor(min_players), unlinked,
                pairs=manager.kind != "mock", team_offer=team_offer,
            ),
            view=ReadyCheckConfirmView(
                manager, thread, initiated_by, show_link_players=bool(unlinked), team_offer=team_offer,
            ),
        )
        return True
    return False


async def reply_public(interaction: discord.Interaction, **kwargs) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(**kwargs)
    else:
        await interaction.response.send_message(**kwargs)


async def reply_private(interaction: discord.Interaction, **kwargs) -> None:
    """Answer the presser alone whether or not the interaction is already acknowledged. A followup inherits
    the flags of the response that opened it, so an ephemeral answer is only guaranteed when it is itself
    the first response."""
    if interaction.response.is_done():
        await interaction.followup.send(**kwargs, ephemeral=True)
    else:
        await interaction.response.send_message(**kwargs, ephemeral=True)


async def open_settings_panel(interaction: discord.Interaction) -> None:
    """Resolve the thread's pod-draft event and open the ephemeral Settings panel. Shared by the lobby
    Settings button and /pod-settings. Resolution goes through the DB rather than ACTIVE_POD_MANAGERS
    so it works from registration onward, before the Draftmancer session launches. From inside the
    thread the interaction channel is the thread; from the channel card the interaction channel is the
    parent, so it falls back to the clicked message id — the starter message and its thread share the
    same id.

    Acknowledged before the lookups, which together can run past the three seconds Discord allows a
    first response."""
    from bot.commands.pod_draft import build_pod_settings_view
    await interaction.response.defer(ephemeral=True, thinking=True)
    channel_id = interaction.channel_id
    actor = actor_label(interaction)
    thread_id = str(channel_id) if channel_id else None
    event_id = await asyncio.to_thread(load_event_id_by_thread_sync, thread_id) if thread_id else None
    if event_id is None and interaction.message is not None:
        event_id = await asyncio.to_thread(load_event_id_by_thread_sync, str(interaction.message.id))
    if event_id is None:
        if _settings_preview_factory is not None:
            await interaction.followup.send(view=_settings_preview_factory(), ephemeral=True)
            return
        log.info(f"{actor} opened Settings in channel={channel_id} (no pod-draft event)")
        await interaction.followup.send(_NO_ACTIVE_POD_MSG, ephemeral=True)
        return
    log.info(f"{actor} opened Settings for event {event_id}")
    is_organizer = await is_pod_organizer(interaction.client, interaction.user)
    await interaction.followup.send(
        view=await build_pod_settings_view(interaction.client, event_id, is_organizer=is_organizer),
        ephemeral=True,
    )


def build_not_ready_view() -> discord.ui.View:
    """Controls on a closed card, so the retry doesn't need the pinned lobby card."""
    view = discord.ui.View(timeout=None)
    view.add_item(ResumeReadyCheckButton())
    view.add_item(SettingsButton())
    return view


def build_live_lobby_view(
    draftmancer_url: str | None = None, spectate_url: str | None = None,
) -> discord.ui.View:
    """The lobby card while a check runs. The players' answers live on the check's own card."""
    return LobbyReadyButtonView(
        draftmancer_url=draftmancer_url, spectate_url=spectate_url,
        live_check=True, show_force_start=True,
    )


def build_started_lobby_view(spectate_url: str | None) -> discord.ui.View:
    """The lobby card's controls from the start of the draft to the end of the pod: a Settings button,
    plus Spectate while the draft is live. Settings routes through the registered
    LobbyReadyButtonView.

    The card keeps it after the draft finishes because that panel is where the organizer fixes an
    unlinked seat and reorganizes a round, and the finished card is the one message that stays up for
    the whole match phase."""
    view = discord.ui.View(timeout=None)
    view.add_item(SettingsButton())
    if spectate_url:
        view.add_item(discord.ui.Button(
            label="Spectate", style=discord.ButtonStyle.link, url=spectate_url, emoji="👀",
        ))
    return view


def event_title(set_code: str | None, event_name: str) -> str:
    """Lobby / ready-check card title: the event name with the set's keyrune symbol prefixed when its
    app emoji is loaded. Custom emoji render in embed titles, so the fancy symbol lives here while the
    plain thread name stays symbol-free. A cube code or an unloaded symbol yields the bare name."""
    prefix = emojis.prefix(set_code.lower()) if set_code else ""
    return f"{prefix}{event_name}"


def render(
    title: str,
    rsvps_yes: list[str],
    rsvps_maybe: list[str],
    in_session: list[tuple[str, str | None]],
    *,
    state: str,
    rsvps_unconfirmed: list[str] | None = None,
    set_code: str | None = None,
    draftmancer_url: str | None = None,
    cancel_reason: str | None = None,
    initiated_by: str | None = None,
    display_name_by_mention_id: dict[int, str] | None = None,
    spectators: list[str] | None = None,
    format_label: str | None = None,
    pairing_label: str | None = None,
    seating_label: str | None = None,
    teams: dict[str, str] | None = None,
    mock: bool = False,
    new_drafters: frozenset[str] = frozenset(),
) -> discord.Embed:
    """Lobby embed. `title` is the thread/event name; `rsvps_yes` / `rsvps_maybe` are sesh display
    names by RSVP type; `in_session` is Draftmancer sessionUsers as (arena_name,
    linked_display_name_or_None). `draftmancer_url` appears under the header, hidden once the ready
    check fires so a latecomer can't join mid-check and break the roster.

    Buckets: In Draftmancer (counts every session user; lists the linked ones), Unrecognized (in
    session, no Player row), Waiting on (Yes RSVP not in session), Unconfirmed (asked to confirm at the
    hold and did not), Maybe (Maybe RSVP not in session). Waiting on carries only the players this table
    holds a seat for, so the room never reads as short of somebody it is not waiting for. Waiting +
    Unconfirmed + Maybe are hidden once ready check fires; the live Ready/Pending split lives on the
    separate ready-check progress card, not here. `spectators` lists Draftmancer sessionSpectators
    comma-separated below Maybe whenever any are present, regardless of state.

    A live check gets one status line and no more: the detail lives on the check's own card.

    `mock` drops everything a mock draft has no use for: an unrecognized seat is normal there (a
    Discord name is enough, nobody links an Arena handle), and no matches are paired, so the
    Unrecognized bucket, `/link-arena`, and `/report-results` all go.

    `new_drafters` marks the seats yet to finish a pod, so the room knows who to walk through it. Seats
    only: somebody the pod is still waiting on is not in front of anybody to help yet."""
    in_draftmancer = [(arena, dn) for arena, dn in in_session if dn is not None]
    unrecognized = [arena for arena, dn in in_session if dn is None]
    mention_map = display_name_by_mention_id or {}
    in_session_keys = {dn.lower() for _, dn in in_session if dn}
    in_session_keys |= {arena.lower() for arena, _ in in_session}
    waiting_yes = [
        name for name in rsvps_yes
        if _rsvp_dedup_key(name, mention_map) not in in_session_keys
    ]
    waiting_unconfirmed = [
        name for name in (rsvps_unconfirmed or [])
        if _rsvp_dedup_key(name, mention_map) not in in_session_keys
    ]
    waiting_maybe = [
        name for name in rsvps_maybe
        if _rsvp_dedup_key(name, mention_map) not in in_session_keys
    ]
    title = event_title(set_code, title)
    live_check = state in ("ready", "held", "overdue")
    show_pending = not live_check and state not in ("drafting", "complete")
    show_link = state != "ready"  # a pause is usually waiting on somebody who dropped

    banner_state = state
    if state not in ("ready", "held", "overdue", "notready", "drafting", "complete") and unrecognized and not mock:
        banner_state = "has_unlinked"
    status_lines, color = ready_status_banner(
        banner_state, cancel_reason=cancel_reason, initiated_by=initiated_by,
    )

    header_lines: list[str] = [f"### {title}"]
    if draftmancer_url and show_link:
        header_lines.append(f"### {draftmancer_url}")
    header_lines.extend(status_lines)
    description = "\n".join(header_lines) if header_lines else None

    embed = discord.Embed(description=description, color=color)
    _set_settings_footer(embed, format_label, pairing_label, seating_label)

    if in_session:
        in_drft_label = "Players" if state == "complete" else "In Draftmancer"
        seat_label = f"✅ {in_drft_label} ({len(in_session)})"
        if teams and state in ("drafting", "complete"):
            _team_columns(embed, in_draftmancer, teams, new_drafters)
        elif mock:
            embed.add_field(
                name=seat_label,
                value=quote_block(_mock_seat_labels(in_session, new_drafters)),
                inline=False,
            )
        else:
            _player_columns(
                embed, seat_label, in_draftmancer,
                trailing="\n​" if show_pending else "", spacer=show_pending,
                new_drafters=new_drafters,
            )

    if show_pending:
        if unrecognized and not mock:
            embed.add_field(
                name=f"⚠️ Unrecognized ({len(unrecognized)})",
                value="\n".join(f"`{arena}`" for arena in unrecognized) + "\n​",
                inline=True,
            )
            embed.add_field(
                name="👉 How to fix",
                value="Run `/link-arena` with your Arena handle\n​",
                inline=True,
            )
            embed.add_field(name="​", value="​", inline=True)
        if rsvps_yes or rsvps_unconfirmed or rsvps_maybe:
            longest = max(len(waiting_yes), len(waiting_unconfirmed), len(waiting_maybe))
            columns = [(f"⌛ Waiting on ({len(waiting_yes)})", waiting_yes)]
            if waiting_unconfirmed:
                columns.append((f"❓ Unconfirmed ({len(waiting_unconfirmed)})", waiting_unconfirmed))
            if waiting_maybe:
                columns.append((f"🤷 Maybe ({len(waiting_maybe)})", waiting_maybe))
            for header, names in columns:
                embed.add_field(
                    name=header,
                    value=quote_block(names, trailing="\n​" if len(names) == longest else ""),
                    inline=True,
                )
            for _ in range(-len(columns) % 3):
                embed.add_field(name="​", value="​", inline=True)

    if spectators:
        embed.add_field(
            name=f"👀 Spectators ({len(spectators)})",
            value=", ".join(spectators),
            inline=False,
        )

    if state != "complete":
        embed.add_field(name="🤖 Commands", value="\n".join(_command_lines(mock)), inline=False)
    return embed


def _command_lines(mock: bool) -> list[str]:
    lines = [command_line("/pod-ready", desc.POD_READY), command_line("/pod-start", desc.POD_START)]
    if mock:
        return [command_line("!mock", desc.MOCK_REPOST), *lines]
    return [
        command_line("!pod", desc.POD_RALLY),
        command_line("/link-arena", desc.LINK_ARENA_LOBBY),
        *lines,
        command_line("/report-results", desc.REPORT_RESULTS_LOBBY),
    ]


def _set_settings_footer(
    embed: discord.Embed,
    format_label: str | None,
    pairing_label: str | None,
    seating_label: str | None,
) -> None:
    """Sticky Format / Pairings / Seats footer shared by the lobby card and the ready-check progress
    card so the pod's settings stay visible through every state."""
    parts = []
    if format_label:
        parts.append(f"Format: {format_label}")
    if pairing_label:
        parts.append(f"Pairings: {pairing_label}")
    if seating_label:
        parts.append(f"Seats: {seating_label}")
    if parts:
        embed.set_footer(text="  •  ".join(parts))


def render_ready_check_progress(
    title: str,
    in_session: list[tuple[str, str | None]],
    *,
    state: str,
    set_code: str | None = None,
    ready_arena_names: set[str] | None = None,
    not_ready_arena_names: set[str] | None = None,
    cancel_reason: str | None = None,
    hold_detail: str | None = None,
    hold_hint: str | None = None,
    draftmancer_url: str | None = None,
    initiated_by: str | None = None,
    format_label: str | None = None,
    pairing_label: str | None = None,
    seating_label: str | None = None,
    teams: dict[str, str] | None = None,
    mock: bool = False,
) -> discord.Embed:
    """Compact ready-check progress card, one per check, updated in place as players respond. `state` mirrors
    the lobby state machine: 'ready', 'held', 'notready', 'drafting', 'complete'.

    Every state keeps the Ready/Pending split, closed ones included: answers outlive the check that collected
    them, so the split is live state rather than history, and the pinned lobby card gets buried.

    A closed check carries no embed title, because Discord hangs an emoji in a title off the em box and one in
    the body off the message-content size, so a `###` line sits straight where a title overhangs. Nothing
    looks this card up by title, unlike the lobby and round cards."""
    title = event_title(set_code, title)
    roster = _seat_rows(in_session, mock=mock)

    closed = state == "notready"
    if closed:
        reason = cancel_reason or READY_STOPPED_TITLE
        card_title = None
        color = discord.Color.red()
        header_lines = [f"### {reason}", *_started_subtext(initiated_by, resume=True)]
    elif state == "held":
        card_title = None
        color = discord.Color.orange()
        header_lines = [f"### {READY_PAUSED_TITLE}", f"### {hold_detail}" if hold_detail else "", hold_hint or ""]
        if draftmancer_url:
            header_lines.append(f"[**{REJOIN_LABEL}**]({draftmancer_url})")
    elif state == "overdue":
        card_title = title
        color = discord.Color.orange()
        header_lines = [f"### ⏳ {READY_OVERDUE_LINE}"]
        header_lines.extend(_started_subtext(initiated_by, resume=False))
    elif state == "ready":
        card_title = title
        color = discord.Color.gold()
        header_lines = [f"### 🔔 {READY_LIVE_LINE}"]
        header_lines.extend(_started_subtext(initiated_by, resume=False))
    else:
        status_lines, color = ready_status_banner(state, initiated_by=initiated_by)
        header_lines = list(status_lines) if status_lines else ["### Ready Check"]
        card_title = title
    header = "\n".join(line for line in header_lines if line)
    embed = discord.Embed(title=card_title, description=header, color=color)
    _set_settings_footer(embed, format_label, pairing_label, seating_label)

    if teams and state in ("drafting", "complete"):
        _team_columns(embed, roster, teams)
        return embed

    if state in ("drafting", "complete"):
        ready_players = roster
        pending_players = []
    elif ready_arena_names is not None:
        ready_players = [(a, dn) for a, dn in roster if a in ready_arena_names]
        pending_players = [
            (a, _not_ready_label(dn, a, not_ready_arena_names)) for a, dn in roster
            if a not in ready_arena_names
        ]
    else:
        ready_players = []
        pending_players = roster

    ready_label = "Players" if state == "complete" else "Ready"
    two_groups = bool(pending_players) or state in ("ready", "held", "overdue")
    _player_columns(embed, f"✅ {ready_label} ({len(ready_players)})", ready_players, spacer=two_groups)
    if two_groups:
        _player_columns(embed, f"⏳ Pending ({len(pending_players)})", pending_players, spacer=True)
    return embed



READY_LIVE_LINE = "Ready Check initiated - press Ready here or in Draftmancer"
READY_RUNNING_LINE = "Ready Check in progress"
READY_STOPPED_TITLE = "🛑 Ready Check Stopped"
READY_PAUSED_TITLE = "⏸️ Ready Check Paused"
READY_OVERDUE_TITLE = "⏳ Ready Check Still Open"
READY_OVERDUE_LINE = "Ready Check still open - press Ready here or in Draftmancer"
REJOIN_LABEL = "Rejoin Draftmancer"
RESUME_WHEN_PRESENT = f"{RESUME_READY_CHECK_LABEL} when all players are present"
RESUME_ON_RETURN = "Check will resume when they are back"


def _started_subtext(initiated_by: str | None, *, resume: bool) -> list[str]:
    """The `-# Started by <name>` subtext, with the resume hint appended on a live declined card."""
    tail = RESUME_WHEN_PRESENT if resume else ""
    if initiated_by and tail:
        return [f"-# Started by {initiated_by}. {tail}"]
    if initiated_by:
        return [f"-# Started by {initiated_by}"]
    if tail:
        return [f"-# {tail}"]
    return []


def ready_status_banner(
    state: str,
    *,
    cancel_reason: str | None = None,
    initiated_by: str | None = None,
) -> tuple[list[str], discord.Color]:
    """The lobby card's status line, plus the two end-of-draft banners the check card shares. A live check
    gets one line here: the detail belongs on the check's own card. Returns ([], blurple) for no banner."""
    if state == "ready":
        return [f"### 🔔 {READY_RUNNING_LINE}", *_started_subtext(initiated_by, resume=False)], discord.Color.gold()
    if state == "held":
        return [f"### {READY_PAUSED_TITLE}"], discord.Color.orange()
    if state == "overdue":
        return [f"### {READY_OVERDUE_TITLE}"], discord.Color.orange()
    if state == "drafting":
        return ["### 🎉 All players ready! Draft started"], discord.Color.green()
    if state == "complete":
        return [f"### {emojis.get('draftmancer')} Draft complete!"], discord.Color.green()
    if state == "notready":
        lines = [f"### {cancel_reason or READY_STOPPED_TITLE}! Click Start Ready Check to retry"]
        lines.extend(_started_subtext(initiated_by, resume=False))
        return lines, discord.Color.red()
    if state == "has_unlinked":
        return ["### ⚠️ Some players aren't recognized yet"], discord.Color.orange()
    return [], discord.Color.blurple()


def roster_change_detail(names: list[str], verb: str) -> str:
    """Phrase for who joined or left mid-check, shown on the lobby banner and the thread notice."""
    icon = "📥" if verb == "joined" else "📤"
    if len(names) == 1:
        return f"{icon} `{names[0]}` {verb} the lobby"
    if names:
        return f"{icon} {len(names)} players {verb} the lobby"
    return f"{icon} A player {verb} the lobby"


def roster_hold_detail(joined: list[str], left: list[str]) -> str:
    """Banner phrase for the roster change that parked a check. A player leaving and another arriving in the
    same broadcast is one event to the pod, so both halves stay on one line."""
    parts = []
    if left:
        parts.append(roster_change_detail(left, "left"))
    if joined:
        parts.append(roster_change_detail(joined, "joined"))
    return ", ".join(parts)


def roster_hold_hint(joined: list[str], left: list[str]) -> str:
    """What to do about a parked check. A seat that left comes back and the check carries on by itself, so
    one line for both directions said the wrong thing half the time."""
    if left and not joined:
        return RESUME_ON_RETURN
    return RESUME_WHEN_PRESENT


def ready_check_overdue_text(mentions: list[str]) -> str:
    if len(mentions) > 1:
        waiting_on = f"{', '.join(mentions[:-1])} and {mentions[-1]}"
    else:
        waiting_on = mentions[0]
    return f"{waiting_on}, the pod is waiting on your Ready Check"


def stopped_reason(actor: str | None) -> str:
    """Heads the stopped card and the lobby banner."""
    return f"{READY_STOPPED_TITLE} by {actor}" if actor else READY_STOPPED_TITLE


_ARENA_SUFFIX_RE = re.compile(r"#[0-9?]+$")


def _mock_seat_labels(
    in_session: list[tuple[str, str | None]], new_drafters: frozenset[str] = frozenset(),
) -> list[str]:
    """One name per mock-draft seat: the linked player when known, else the Draftmancer name itself.
    A mock never links Arena handles, so an unmatched seat is ordinary and needs no marker or column."""
    return [marked_new(dn or arena, new_drafters) for arena, dn in in_session]


def _seat_rows(in_session: list[tuple[str, str | None]], *, mock: bool = False) -> list[tuple[str, str]]:
    """(arena_handle, display_label) for every Draftmancer seat. An unlinked seat keeps its place in
    the roster with a ⚠️ marker rather than being dropped, so the lobby never hides who is present.
    `mock` drops the marker: a mock draft matches seats by Discord name and links no Arena handles."""
    rows: list[tuple[str, str]] = []
    for arena, dn in in_session:
        if dn is not None:
            rows.append((arena, dn))
        else:
            stripped = _ARENA_SUFFIX_RE.sub("", arena) or arena
            rows.append((arena, stripped if mock else f"{stripped} ⚠️"))
    return rows


def _not_ready_label(display: str, arena: str, not_ready_arena_names: set[str] | None) -> str:
    """A pending seat's label, marked ❌ once it has answered Not Ready. Silence and a refusal read the same
    in a bare Pending list, and only one is worth waiting on."""
    if not_ready_arena_names and arena in not_ready_arena_names:
        return f"{display} ❌"
    return display


def _player_columns(
    embed: discord.Embed, label: str, players: list[tuple[str, str]], *,
    trailing: str = "", spacer: bool = False, new_drafters: frozenset[str] = frozenset(),
) -> None:
    """Two columns from `players` (arena_name, display_name): blockquoted names | code Arena
    handles. `spacer` closes the inline row when another group follows."""
    add_two_column_field(
        embed, label,
        [marked_new(dn, new_drafters) for _, dn in players],
        [f"`{arena}`" for arena, _ in players],
        trailing=trailing, spacer=spacer,
    )


def _team_columns(
    embed: discord.Embed, in_draftmancer: list[tuple[str, str]], teams: dict[str, str],
    new_drafters: frozenset[str] = frozenset(),
) -> None:
    """Two side-by-side team fields for a team-draft lobby, replacing the flat player list once teams
    are assigned. Delegates to add_team_roster_fields so the columns match the board's roster header."""
    normalized = {normalize_player_name(name): team for name, team in teams.items()}
    rosters: dict[str, list[TeamBoardMember]] = {pod_team.TEAM_A: [], pod_team.TEAM_B: []}
    for arena, dn in in_draftmancer:
        team = normalized.get(normalize_player_name(arena))
        if team in rosters:
            rosters[team].append(TeamBoardMember(display=marked_new(dn, new_drafters), arena=arena))
    add_team_roster_fields(embed, rosters)


def _rsvp_dedup_key(rsvp: str, display_name_by_mention_id: dict[int, str]) -> str:
    """Normalize an rsvp line to a lowercase comparison key. Handles both sesh formats:
    when sesh's `Display Usernames as Plain Text` is on, lines are bare display names;
    when off, lines are `<@id>` mention strings — we resolve those via the guild map."""
    text = rsvp.strip()
    mention_regex = re.compile(r"^<@!?(\d+)>$")
    m = mention_regex.match(text)
    if m:
        resolved = display_name_by_mention_id.get(int(m.group(1)))
        if resolved:
            return resolved.lower()
    return text.lower()

# testlobby injects a no-op Settings panel factory so the UI is previewable without a live pod
_settings_preview_factory = None


def register_settings_preview(factory) -> None:
    """Let the testlobby sandbox preview the Settings panel even though it has no live pod manager."""
    global _settings_preview_factory
    _settings_preview_factory = factory


# testlobby injects a (ready, total, pending) factory so the Force Start confirm is previewable
_force_start_preview_factory = None


def register_force_start_preview(factory) -> None:
    """Let the testlobby sandbox preview the Force Start confirm dialog without a live pod manager."""
    global _force_start_preview_factory
    _force_start_preview_factory = factory
