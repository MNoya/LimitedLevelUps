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
from bot.discord_helpers import add_two_column_field, command_line, quote_block
from bot.services import pod_team
from bot.services.pod_drafts import load_event_id_by_thread_sync, normalize_player_name
from bot.services.pod_team_board import TeamBoardMember, add_team_roster_fields
from bot.services.pod_tournament import actor_label


log = logging.getLogger("bot.lobby_embed")

READY_CHECK_CUSTOM_ID = "pod-draft:ready-check"
SETTINGS_CUSTOM_ID = "pod-draft:settings"
FORCE_START_CUSTOM_ID = "pod-draft:force-start"

_NO_ACTIVE_POD_MSG = "No active pod-draft session in this thread."


def _active_manager_for_channel(channel_id: int | None):
    from bot.services.pod_active import ACTIVE_POD_MANAGERS
    return next((m for m in ACTIVE_POD_MANAGERS.values() if m.thread_id == channel_id), None)


class LobbyReadyButtonView(discord.ui.View):
    def __init__(
        self, draftmancer_url: str | None = None, ready_disabled: bool = False,
        show_force_start: bool = False, spectate_url: str | None = None,
    ) -> None:
        super().__init__(timeout=None)
        if ready_disabled:
            self.ready_check.disabled = True
        self.add_item(SettingsButton())
        if show_force_start:
            self.add_item(ForceStartButton())
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
        channel = interaction.channel
        channel_id = channel.id if channel else None
        actor = actor_label(interaction)
        manager = _active_manager_for_channel(channel_id)
        if manager is None:
            log.info(f"{actor} clicked Ready Check in channel={channel_id} (no active pod)")
            await interaction.response.send_message(_NO_ACTIVE_POD_MSG, ephemeral=True)
            return
        log.info(f"[{manager.event_name}] {actor} clicked Ready Check")
        await interaction.response.defer(ephemeral=True)
        thread = await interaction.client.fetch_channel(manager.thread_id)
        if await guard_ready_check(interaction, manager, thread, initiated_by=actor):
            return
        err = await manager.initiate_ready_check(thread, initiated_by=actor)
        if err:
            await interaction.followup.send(f"⚠️ {err}", ephemeral=True)


class SettingsButton(discord.ui.Button):
    def __init__(self, label: str | None = "Settings") -> None:
        super().__init__(
            label=label, style=discord.ButtonStyle.grey,
            custom_id=SETTINGS_CUSTOM_ID, emoji="⚙️",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await open_settings_panel(interaction)


class ForceStartButton(discord.ui.Button):
    """On the active ready-check card: an understated escape hatch to skip the remaining ready checks
    and start the draft, behind a confirmation so a stray click can't launch the pod with players away."""

    def __init__(self) -> None:
        super().__init__(
            label="Force Start", style=discord.ButtonStyle.secondary,
            custom_id=FORCE_START_CUSTOM_ID, emoji="⏭️",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        actor = actor_label(interaction)
        manager = _active_manager_for_channel(interaction.channel_id)
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
            await interaction.response.edit_message(content="Preview only — no live pod to start.", view=None)
            return
        actor = actor_label(interaction)
        log.info(f"[{self.manager.event_name}] {actor} confirmed Force Start")
        await interaction.response.defer()
        err = await self.manager.force_start()
        message = f"⚠️ {err}" if err else "Force-starting the draft, watch the thread."
        await interaction.edit_original_response(content=message, view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(content="Force start canceled.", view=None)


READY_CHECK_CONFIRM_PROMPT = "Start the ready check anyway?"


def ready_check_confirm_text(seated: int, floor: int, unlinked: list[str]) -> str:
    """Warn-but-allow prompt shown to the initiator when a ready check is unusual but permitted: a roster
    under the floor, an odd roster that cannot pair, unrecognized seats, or any combination. Shared by the
    live Ready Check button and the `!test` preview so the copy never drifts."""
    lines: list[str] = []
    if seated < floor:
        lines.append(
            f"🛑 Only {seated} players in the Draftmancer lobby. A pod needs {floor} or more."
        )
    if seated % 2 != 0:
        lines.append(
            f"⚠️ {seated} players is an odd number. Pairings need an even number, so the draft will be "
            "refused at start until a player joins or drops."
        )
    if unlinked:
        names = ", ".join(f"`{name}`" for name in unlinked)
        verb = "is" if len(unlinked) == 1 else "are"
        lines.append(
            f"⚠️ {names} {verb} unrecognized. Bot won't be able to send them pairings.\n"
            "Have them run `/link-arena`, or use Link Players below."
        )
    lines.append(READY_CHECK_CONFIRM_PROMPT)
    return "\n\n".join(lines)


class ReadyCheckConfirmView(discord.ui.View):
    """Ephemeral warn-but-allow gate shown to the initiator when a ready check is unusual but permitted, so a
    short or odd roster can still be readied on purpose instead of leaving Force Start as the only way in."""

    def __init__(
        self, manager, thread, initiated_by: str | None, *, show_link_players: bool = True,
    ) -> None:
        super().__init__(timeout=60)
        self.manager = manager
        self.thread = thread
        self.initiated_by = initiated_by
        if not show_link_players:
            self.remove_item(self.link_players)

    @discord.ui.button(label="Start Anyway", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.manager is None:
            await interaction.response.edit_message(content="Preview only — no live pod to start.", view=None)
            return
        actor = actor_label(interaction)
        log.info(f"[{self.manager.event_name}] {actor} confirmed Ready Check past warnings")
        await interaction.response.defer()
        err = await self.manager.initiate_ready_check(self.thread, initiated_by=self.initiated_by)
        message = f"⚠️ {err}" if err else "Ready check started, watch the thread."
        await interaction.edit_original_response(content=message, view=None)

    @discord.ui.button(label="Link Players", style=discord.ButtonStyle.primary, emoji="🔗")
    async def link_players(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        from bot.services.pod_settings_view import LINK_SEAT_PROMPT, LinkSeatSelectView
        if self.manager is None:
            await interaction.response.edit_message(content="Preview only — linking needs a live pod.", view=None)
            return
        targets = await self.manager.unrecognized_lobby_names()
        if not targets:
            await interaction.response.edit_message(
                content="Everyone's linked now. Press Start Ready Check again.", view=None,
            )
            return
        manager = self.manager

        async def on_link(inter: discord.Interaction, arena_name: str, member: discord.abc.User) -> str | None:
            return await manager.link_seat(member, arena_name)

        await interaction.response.edit_message(content=LINK_SEAT_PROMPT, view=LinkSeatSelectView(targets, on_link))

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(content="Ready check canceled.", view=None)


async def guard_ready_check(interaction, manager, thread, *, initiated_by, min_players=None) -> bool:
    """Shared ready-check kickoff guard for the lobby button and /pod-ready. Runs the hard blockers, then the
    warn-but-allow confirm covering a short roster, an odd roster and unrecognized seats in one prompt, so
    confirming never leads straight into a second one. Returns True if the interaction was handled here
    (blocked or awaiting confirm) and the caller should stop; False if the pod is clear to start now.
    Runs before /pod-ready acknowledges, so that command can answer publicly once it knows the check will
    actually fire, and every answer from here stays private to the initiator either way."""
    blocker = manager.ready_check_blocker()
    if blocker:
        await reply_private(interaction, content=f"⚠️ {blocker}")
        return True
    unlinked = [] if manager.kind == "mock" else await manager.unrecognized_lobby_names()
    if manager.ready_check_needs_confirm(unlinked, min_players=min_players):
        await reply_private(
            interaction,
            content=ready_check_confirm_text(
                len(manager.player_session_users()), manager.ready_check_floor(min_players), unlinked,
            ),
            view=ReadyCheckConfirmView(manager, thread, initiated_by, show_link_players=bool(unlinked)),
        )
        return True
    return False


async def reply_private(interaction: discord.Interaction, **kwargs) -> None:
    """Answer the presser alone whether or not the interaction is already acknowledged. A followup inherits
    the flags of the response that opened it, so an ephemeral answer is only guaranteed when it is itself
    the first response."""
    if interaction.response.is_done():
        await interaction.followup.send(**kwargs, ephemeral=True)
    else:
        await interaction.response.send_message(**kwargs, ephemeral=True)


async def open_settings_panel(interaction: discord.Interaction) -> None:
    """Resolve the thread's pod-draft event and open the ephemeral Settings panel. Resolution goes
    through the DB rather than ACTIVE_POD_MANAGERS so the button works from registration onward,
    before the Draftmancer session launches. From inside the thread the interaction channel is the
    thread; from the channel card the interaction channel is the parent, so it falls back to the
    clicked message id — the starter message and its thread share the same id.

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
        log.info(f"{actor} clicked Settings in channel={channel_id} (no pod-draft event)")
        await interaction.followup.send(_NO_ACTIVE_POD_MSG, ephemeral=True)
        return
    log.info(f"{actor} clicked Settings for event {event_id}")
    is_owner = await interaction.client.is_owner(interaction.user)
    await interaction.followup.send(
        view=await build_pod_settings_view(interaction.client, event_id, is_owner=is_owner),
        ephemeral=True,
    )


def build_not_ready_view() -> discord.ui.View:
    """Controls on the Not Ready card so the retry doesn't require scrolling back to the pinned lobby
    card. The resume button carries the persistent Ready Check custom_id, so clicks dispatch through
    the registered view."""
    view = LobbyReadyButtonView()
    view.ready_check.label = "Resume Ready Check"
    return view


def build_drafting_view(spectate_url: str | None) -> discord.ui.View | None:
    """The lobby cards' controls once drafting starts: Spectate plus a Settings button so an unlinked
    seat can still be fixed mid-draft. Settings routes through the registered LobbyReadyButtonView."""
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
    set_code: str | None = None,
    draftmancer_url: str | None = None,
    decliner_name: str | None = None,
    cancel_reason: str | None = None,
    initiated_by: str | None = None,
    display_name_by_mention_id: dict[int, str] | None = None,
    spectators: list[str] | None = None,
    format_label: str | None = None,
    pairing_label: str | None = None,
    seating_label: str | None = None,
    teams: dict[str, str] | None = None,
    mock: bool = False,
) -> discord.Embed:
    """Lobby embed. `title` is the thread/event name; `rsvps_yes` / `rsvps_maybe` are sesh display
    names by RSVP type; `in_session` is Draftmancer sessionUsers as (arena_name,
    linked_display_name_or_None). `draftmancer_url` appears under the header, hidden once the ready
    check fires so a latecomer can't join mid-check and break the roster.

    Buckets: In Draftmancer (counts every session user; lists the linked ones), Unrecognized (in
    session, no Player row), Waiting on (Yes RSVP not in session), Maybe (Maybe RSVP not in session).
    Waiting + Maybe are hidden once ready check fires; the live Ready/Pending split lives on the
    separate ready-check progress card, not here. `spectators` lists Draftmancer sessionSpectators
    comma-separated below Maybe whenever any are present, regardless of state.

    `mock` drops everything a mock draft has no use for: an unrecognized seat is normal there (a
    Discord name is enough, nobody links an Arena handle), and no matches are paired, so the
    Unrecognized bucket, `/link-arena`, and `/report-results` all go."""
    in_draftmancer = [(arena, dn) for arena, dn in in_session if dn is not None]
    unrecognized = [arena for arena, dn in in_session if dn is None]
    mention_map = display_name_by_mention_id or {}
    in_session_keys = {dn.lower() for _, dn in in_session if dn}
    in_session_keys |= {arena.lower() for arena, _ in in_session}
    waiting_yes = [
        name for name in rsvps_yes
        if _rsvp_dedup_key(name, mention_map) not in in_session_keys
    ]
    waiting_maybe = [
        name for name in rsvps_maybe
        if _rsvp_dedup_key(name, mention_map) not in in_session_keys
    ]
    title = event_title(set_code, title)
    show_pending = state not in ("ready", "drafting", "complete")

    banner_state = state
    if state not in ("ready", "notready", "drafting", "complete") and unrecognized and not mock:
        banner_state = "has_unlinked"
    status_lines, color = ready_status_banner(
        banner_state, decliner_name=decliner_name, cancel_reason=cancel_reason,
        initiated_by=initiated_by,
    )

    header_lines: list[str] = []
    if draftmancer_url and state != "ready":
        header_lines.append(f"### {draftmancer_url}")
    header_lines.extend(status_lines)
    description = "\n".join(header_lines) if header_lines else None

    embed = discord.Embed(title=title, description=description, color=color)
    _set_settings_footer(embed, format_label, pairing_label, seating_label)

    if in_session:
        in_drft_label = "Players" if state == "complete" else "In Draftmancer"
        seat_label = f"✅ {in_drft_label} ({len(in_session)})"
        if teams and state in ("drafting", "complete"):
            _team_columns(embed, in_draftmancer, teams)
        elif mock:
            embed.add_field(name=seat_label, value=quote_block(_mock_seat_labels(in_session)), inline=False)
        else:
            _player_columns(
                embed, seat_label, in_draftmancer,
                trailing="\n​" if show_pending else "", spacer=show_pending,
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
        if rsvps_yes or rsvps_maybe:
            waiting_trailing = "\n​" if len(waiting_yes) > len(waiting_maybe) else ""
            embed.add_field(
                name=f"⌛ Waiting on ({len(waiting_yes)})",
                value=quote_block(waiting_yes, trailing=waiting_trailing),
                inline=True,
            )
            embed.add_field(
                name=f"🤷 Maybe ({len(waiting_maybe)})",
                value=quote_block(waiting_maybe),
                inline=True,
            )
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
        return lines
    return [
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
    decliner_name: str | None = None,
    cancel_reason: str | None = None,
    superseded: bool = False,
    initiated_by: str | None = None,
    timed_out: bool = False,
    ready_count: int | None = None,
    total_count: int | None = None,
    format_label: str | None = None,
    pairing_label: str | None = None,
    seating_label: str | None = None,
    mock: bool = False,
) -> discord.Embed:
    """Compact ready-check progress card.

    Posted fresh each ready check and updated in place as players respond, so the active card
    stays at the bottom of the thread even when the main lobby card has scrolled away.
    `state` mirrors the lobby state machine: 'ready', 'notready', 'drafting', 'complete', and
    falls through to a neutral header otherwise.

    A declined card ('notready', including the `superseded` stale variant) titles `Ready Check
    Canceled` with an `❌ <reason>` line + `✅ ready_count/total_count Ready`; the `timed_out` variant
    titles `Ready Check Timed Out` and drops the reason line. The live declined card carries the
    Resume Ready Check + Settings view; a superseded card carries none.
    """
    title = event_title(set_code, title)
    roster = _seat_rows(in_session, mock=mock)

    declined = state == "notready"
    resume = declined and not superseded
    if declined and timed_out:
        header_lines = _started_subtext(initiated_by, resume=resume)
        color = discord.Color.red()
        card_title = "⚠️ Ready Check Timed Out"
    else:
        status_lines, color = ready_status_banner(
            state, decliner_name=decliner_name, cancel_reason=cancel_reason,
            initiated_by=initiated_by, retry_hint=False if declined else not superseded,
            resume_hint=resume,
        )
        header_lines = list(status_lines) if status_lines else ["### Ready Check"]
        card_title = "⚠️ Ready Check Canceled" if declined else title
    if declined and ready_count is not None and total_count is not None:
        header_lines.append(f"### ✅ {ready_count}/{total_count} Ready")
    embed = discord.Embed(title=card_title, description="\n".join(header_lines), color=color)
    _set_settings_footer(embed, format_label, pairing_label, seating_label)

    if declined or superseded:
        return embed

    if state in ("drafting", "complete"):
        ready_players = roster
        pending_players = []
    elif ready_arena_names is not None:
        ready_players = [(a, dn) for a, dn in roster if a in ready_arena_names]
        pending_players = [(a, dn) for a, dn in roster if a not in ready_arena_names]
    else:
        ready_players = []
        pending_players = roster

    ready_label = "Players" if state == "complete" else "Ready"
    two_groups = bool(pending_players) or state == "ready"
    _player_columns(embed, f"✅ {ready_label} ({len(ready_players)})", ready_players, spacer=two_groups)
    if two_groups:
        _player_columns(embed, f"⏳ Pending ({len(pending_players)})", pending_players, spacer=True)
    return embed


READY_RESUME_HINT = "Resume when all players are present"


def _started_subtext(initiated_by: str | None, *, resume: bool) -> list[str]:
    """The `-# Started by <name>` subtext, with the resume hint appended on a live declined card."""
    tail = READY_RESUME_HINT if resume else ""
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
    decliner_name: str | None = None,
    cancel_reason: str | None = None,
    initiated_by: str | None = None,
    retry_hint: bool = True,
    resume_hint: bool = False,
) -> tuple[list[str], discord.Color]:
    """Status banner lines + color shared by the lobby card and the ready-check progress card so
    their wording never drifts. `retry_hint` appends the retry tail on a live failed check; pass
    False on a stale superseded card. `resume_hint` appends the resume line to the Started-by subtext
    on a live declined card. Returns ([], blurple) for states with no banner."""
    if state == "ready":
        lines = ["### 🔔 Ready Check initiated! Accept on Draftmancer to start the draft"]
        if initiated_by:
            lines.append(f"-# Started by {initiated_by}")
        return lines, discord.Color.gold()
    if state == "drafting":
        return ["### 🎉 All players ready! Draft started"], discord.Color.green()
    if state == "complete":
        return [f"### {emojis.get('draftmancer')} Draft complete!"], discord.Color.green()
    if state == "notready":
        retry = "! Click Start Ready Check to retry" if retry_hint else ""
        if decliner_name:
            reason = f"❌ `{decliner_name}` is Not Ready"
        else:
            reason = cancel_reason or "❌ Ready Check canceled"
        lines = [f"### {reason}{retry}"]
        lines.extend(_started_subtext(initiated_by, resume=resume_hint))
        return lines, discord.Color.red()
    if state == "has_unlinked":
        return ["### ⚠️ Some players aren't recognized yet"], discord.Color.orange()
    return [], discord.Color.blurple()


_ARENA_SUFFIX_RE = re.compile(r"#[0-9?]+$")


def _mock_seat_labels(in_session: list[tuple[str, str | None]]) -> list[str]:
    """One name per mock-draft seat: the linked player when known, else the Draftmancer name itself.
    A mock never links Arena handles, so an unmatched seat is ordinary and needs no marker or column."""
    return [dn or arena for arena, dn in in_session]


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


def _player_columns(
    embed: discord.Embed, label: str, players: list[tuple[str, str]], *,
    trailing: str = "", spacer: bool = False,
) -> None:
    """Two columns from `players` (arena_name, display_name): blockquoted names | code Arena
    handles. `spacer` closes the inline row when another group follows."""
    add_two_column_field(
        embed, label,
        [dn for _, dn in players],
        [f"`{arena}`" for arena, _ in players],
        trailing=trailing, spacer=spacer,
    )


def _team_columns(
    embed: discord.Embed, in_draftmancer: list[tuple[str, str]], teams: dict[str, str],
) -> None:
    """Two side-by-side team fields for a team-draft lobby, replacing the flat player list once teams
    are assigned. Delegates to add_team_roster_fields so the columns match the board's roster header."""
    normalized = {normalize_player_name(name): team for name, team in teams.items()}
    rosters: dict[str, list[TeamBoardMember]] = {pod_team.TEAM_A: [], pod_team.TEAM_B: []}
    for arena, dn in in_draftmancer:
        team = normalized.get(normalize_player_name(arena))
        if team in rosters:
            rosters[team].append(TeamBoardMember(display=dn, arena=arena))
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
