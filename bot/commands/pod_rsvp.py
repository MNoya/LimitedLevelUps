"""Scheduled pod RSVP card — the bot-owned replacement for sesh's weekly RSVP embed.

The channel card: a bare slot-role mention as the pinging content line, an embed with the localized
start time, a Google Calendar link, and Yes / Maybe / No columns. Every RSVP surface resolves per
message to the same signal, so a click anywhere records once and re-renders whichever surfaces show
the card. Thread membership follows the RSVP: Yes and Maybe pull the member in, No takes them back
out.

The thread hangs off the card, so a single edit to the card updates both the channel and the thread
starter. Because a starter's own buttons render dead in-thread, the "Pod Draft registered!" message
carries the labeled RSVP row (Sign Up / Maybe / Can't) for the thread.

`post_scheduled_card` is the single creation path the weekly poster and `!test rsvp` share: card,
signal, thread, PodDraftEvent, the native Discord scheduled event, and every timed job in one call.
The native event is a discovery mirror (Events tab, mobile surfacing, Discord's own start
notifications); the card stays the canonical RSVP surface.

Rescheduling a pod lives in the lobby Settings panel (scheduled pods, pre-draft), not on the card.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta, timezone
from typing import Awaitable, Callable
from urllib.parse import urlencode

import discord
from discord.ext import commands

from bot import audit, emojis
from bot.commands.messages import (
    MSG_DRAFT_STARTS,
    MSG_DRAFTMANCER_LINK_LEAD,
    MSG_POD_ADDED,
    MSG_POD_MAYBE,
    MSG_POD_REMOVED,
)
from bot.database import SessionLocal
from bot.discord_helpers import NBSP
from bot.services.lobby_embed import SettingsButton
from sqlalchemy import select

from bot.services.pod_active import ACTIVE_POD_MANAGERS
from bot.models import PodDraftEvent, PodSignal
from bot.services import pod_launch
from bot.services.pod_deck_color import format_deck_color_emojis
from bot.services.pod_draft_manager import notify_seeding_change
from bot.services.pod_tournament import champion_card_line, load_solo_card_drafters
from bot.services.ping_roles import (
    NOTICE_GRANT,
    announce_pod_grant,
    auto_grant_spec_for_event,
    display_emoji,
    pod_role_grant_text,
    send_join_confirmation_card,
    slot_grant_ping,
    spec_named,
)
from bot.services.pod_drafts import (
    is_championship,
    load_event_pairing_mode_sync,
    load_event_set_code_sync,
    record_ondemand_event,
)
from bot.services.pod_registration_embed import build_registered_embed
from bot.services.pod_roles import find_role, grant_pod_drafters, grant_role
from bot.services.pod_roster_fields import add_roster_fields
from bot.services import pod_team
from bot.services.pod_team_board import TeamBoardMember, load_team_board_data, team_result_headline
from bot.services.pod_schedule import LATE_POD_ROLE_NAME, SCHEDULE_TZ
from bot.services.pod_slot import pod_display_name, team_aware_pod_name
from bot.services.pod_signals import RSVP_EMOJI, RSVP_MAYBE, RSVP_NO, RSVP_STATES, RSVP_YES
from bot.sets import active_set_code
from bot.tasks.pod_draft_reminder import (
    REMINDER_LEAD_MIN,
    event_rsvps,
    refresh_roster_reminder_for_event,
)
from bot.tasks.pod_underfill import refresh_underfill_nudge_for_event


log = logging.getLogger(__name__)

EVENT_DURATION_H = 2
POD_CAPACITY = 8

CARD_INTRO = "{emoji} Please RSVP"
MULTIPOD_NOTICE = "🔥 Keep signing up to fire a second table"
CARD_STATUS_DRAFTING = "🎉 **Draft started!**"
CARD_STATUS_PLAYING = "⚔️ **Matches In Progress**"
TIME_LABEL = "Time"
NATIVE_EVENT_SIGNUP = "**Event Details and Signup Link: {jump_url}**"
RSVP_LABELS = {RSVP_YES: "Sign Up", RSVP_MAYBE: "Maybe", RSVP_NO: "Can't"}
RSVP_CONFIRM_COLOR = {
    RSVP_YES: discord.Color.green(),
    RSVP_MAYBE: discord.Color.orange(),
    RSVP_NO: discord.Color.red(),
}
MSG_CARD_INACTIVE = "This RSVP card is no longer active."
MSG_BAD_TIME = "Couldn't read that time. Use `+2h30m`, `21:00` (ET), or `2026-07-18 21:00` (ET), in the future."
THREAD_NOTE_TITLE = "🕐 Pod Draft Rescheduled by {actor}"
THREAD_NOTE_BODY = "New time: <t:{unix}:F> (<t:{unix}:R>)\n" + MSG_DRAFTMANCER_LINK_LEAD

LauncherRefresh = Callable[[commands.Bot, date], Awaitable[None]]

_launcher_refresh: LauncherRefresh | None = None


def register_launcher_refresh(handler: LauncherRefresh) -> None:
    """The daily-launcher task registers here so a card RSVP re-renders any launcher reflecting it,
    without pod_rsvp importing the task module and cycling back."""
    global _launcher_refresh
    _launcher_refresh = handler


OFFSET_RE = re.compile(r"^\+?(?:(\d+)h)?(?:(\d+)m)?$")
TIMESTAMP_RE = re.compile(r"^<t:(\d{1,15})(?::[a-z])?>$")
CLOCK_RE = re.compile(r"^(\d{1,2})(?::(\d{2}))?(am|pm)?$")
TZ_TOKENS = {"et", "est", "edt"}
FILLER_TOKENS = {"at", "on"}
WEEKDAYS = {
    "monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1, "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3, "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5, "sunday": 6, "sun": 6,
}


class RsvpButton(discord.ui.Button):
    def __init__(self, state: str, row: int | None = None, labeled: bool = False) -> None:
        super().__init__(
            emoji=RSVP_EMOJI[state], label=RSVP_LABELS[state] if labeled else None,
            style=discord.ButtonStyle.secondary, custom_id=f"pod_rsvp:{state}", row=row,
        )
        self.state = state

    async def callback(self, interaction: discord.Interaction) -> None:
        await _handle_rsvp(interaction, self.state)


class PodRsvpView(discord.ui.View):
    """Persistent — static custom_ids registered once at startup; state lives in the DB per message.
    The Settings gear trails the RSVP row so the channel card carries the same format/reschedule/cancel
    controls as the thread; its custom_id is dispatched by the globally-registered Settings button."""

    def __init__(self) -> None:
        super().__init__(timeout=None)
        for state in RSVP_STATES:
            self.add_item(RsvpButton(state))
        self.add_item(SettingsButton(label=None))


class ScheduledRegisteredView(discord.ui.View):
    """Registered-embed view for anchored-thread pods: the labeled RSVP row (Sign Up / Maybe / Can't)
    above the Settings button, so the thread has live controls where the starter card's own buttons
    render dead. The labels make it clear clicking also signs you up. Its custom_ids are already
    registered through PodRsvpView and the global Settings button, so it needs no registration."""

    def __init__(self) -> None:
        super().__init__(timeout=None)
        for state in RSVP_STATES:
            self.add_item(RsvpButton(state, row=0, labeled=True))
        settings = SettingsButton()
        settings.row = 0
        self.add_item(settings)


async def _apply_surface_rsvp(interaction: discord.Interaction, event_id: str, state: str) -> None:
    """Record an RSVP from a non-card surface (championship invite wave, roster reminder) by resolving
    the pod's card from its event id, then routing through the shared card path."""
    card = await asyncio.to_thread(pod_launch.scheduled_card_ref_sync, event_id)
    if card is None:
        await interaction.response.send_message(MSG_CARD_INACTIVE, ephemeral=True)
        return
    _, _, card_message_id, _ = card
    await apply_card_rsvp(interaction, card_message_id, state)


CHAMPIONSHIP_CONFIRM_PREFIX = "podchampconfirm"
MSG_CONFIRM_BUTTON = "Confirm"


class ChampionshipConfirmButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=rf"{CHAMPIONSHIP_CONFIRM_PREFIX}:(?P<event_id>.+)",
):
    """The Confirm button on a championship invite wave — a shorter, clearer path to the card's Yes
    than telling a player to RSVP on the card above. One registration dispatches every wave (the event
    id rides in the custom_id) and it keeps working after a restart. Records Yes against the pod's card
    and answers with the private confirmation, the same as Sign Up from any non-card surface."""

    def __init__(self, event_id: str) -> None:
        super().__init__(discord.ui.Button(
            style=discord.ButtonStyle.success, label=MSG_CONFIRM_BUTTON, emoji="✅",
            custom_id=f"{CHAMPIONSHIP_CONFIRM_PREFIX}:{event_id}",
        ))
        self.event_id = event_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match):
        return cls(match["event_id"])

    async def callback(self, interaction: discord.Interaction) -> None:
        await _apply_surface_rsvp(interaction, self.event_id, RSVP_YES)


CHAMPIONSHIP_RSVP_PREFIX = "podchamprsvp"


class ChampionshipRsvpButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=rf"{CHAMPIONSHIP_RSVP_PREFIX}:(?P<state>[a-z]+):(?P<event_id>.+)",
):
    """Maybe / Can't on a championship invite wave, recording that state against the pod's card the
    same as choosing it from any non-card surface. The Yes seat is ChampionshipConfirmButton, styled as
    a green Confirm; these two carry the state in the custom_id and keep working after a restart."""

    def __init__(self, state: str, event_id: str) -> None:
        super().__init__(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label=RSVP_LABELS[state], emoji=RSVP_EMOJI[state],
            custom_id=f"{CHAMPIONSHIP_RSVP_PREFIX}:{state}:{event_id}",
        ))
        self.state = state
        self.event_id = event_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match):
        return cls(match["state"], match["event_id"])

    async def callback(self, interaction: discord.Interaction) -> None:
        await _apply_surface_rsvp(interaction, self.event_id, self.state)


REMINDER_RSVP_PREFIX = "podreminderrsvp"


class ReminderRsvpButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=rf"{REMINDER_RSVP_PREFIX}:(?P<state>[a-z]+):(?P<event_id>.+)",
):
    """Sign Up / Can't on the T-60 roster reminder. The reminder lives in the pod thread and is not a
    card surface, so the event id rides in the custom_id: one registration dispatches every reminder, it
    keeps working after a restart, and the click records against the pod's card the same as any non-card
    surface. The reminder confirms Yes or No only — Maybe belongs to the earlier gathering window."""

    def __init__(self, state: str, event_id: str) -> None:
        super().__init__(discord.ui.Button(
            style=discord.ButtonStyle.success if state == RSVP_YES else discord.ButtonStyle.secondary,
            label=RSVP_LABELS[state], emoji=RSVP_EMOJI[state],
            custom_id=f"{REMINDER_RSVP_PREFIX}:{state}:{event_id}",
        ))
        self.state = state
        self.event_id = event_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match):
        return cls(match["state"], match["event_id"])

    async def callback(self, interaction: discord.Interaction) -> None:
        await _apply_surface_rsvp(interaction, self.event_id, self.state)


def build_championship_wave_view(event_id: str) -> discord.ui.View:
    """The invite wave's RSVP row: Confirm / Maybe / Can't, each recording against the pod's card."""
    view = discord.ui.View(timeout=None)
    view.add_item(ChampionshipConfirmButton(event_id))
    view.add_item(ChampionshipRsvpButton(RSVP_MAYBE, event_id))
    view.add_item(ChampionshipRsvpButton(RSVP_NO, event_id))
    return view


@dataclass(frozen=True)
class DraftedPlayer:
    """One locked pod participant for the started / playing / complete card. Populated as the draft
    progresses: seat order at the start, deck colors once decks lock, then the W-L record and final
    placement once matches run. The card shows who actually drafted, in place of the RSVP columns."""
    display_name: str
    seat_index: int | None = None
    deck_colors: str | None = None
    record: str | None = None
    placement: int | None = None


def build_rsvp_embed(
    name: str, event_time: datetime, rosters: dict[str, list[str]], role_time: datetime | None = None,
    description: str | None = None, set_code: str | None = None, team_draft: bool = False,
    status_line: str | None = None, announcement: str | None = None,
    roster_interests: dict[str, list[tuple[str, tuple[str, ...]]]] | None = None,
    locked_roster: list[DraftedPlayer] | None = None, draft_complete: bool = False,
    team_rosters: dict[str, list[TeamBoardMember]] | None = None,
) -> discord.Embed:
    """The RSVP surface. Time and the roster columns are embed fields so sesh's vertical breathing
    room comes for free. `role_time` keys the slot emoji; it defaults to `event_time` and callers
    pass the signal's original slot time after a reschedule. `description` is the optional organizer
    note, shown between the intro and the multi-pod notice so a roster refresh preserves it.
    `set_code` trails the format's keyrune symbol after the name; `team_draft` marks the title once
    the pod locks into teams. `status_line` replaces the RSVP intro and the multi-pod notice once the
    pod is past gathering, so the card never asks for RSVPs into a draft that already started.
    `announcement` is a fixed body a championship card carries in place of the RSVP intro and the
    multi-pod notice, since a championship is not a lazy pod that fires a second table.
    `locked_roster` replaces the RSVP columns once the draft starts with the actual drafters, which
    fill in records through to the final standings when `draft_complete`. A locked card drops the
    absolute time and calendar link — those help someone deciding to sign up, not a draft in flight —
    and closes on how long ago the pod started, since the pod name already carries the date.
    `team_rosters` maps team key to its members and takes the same in-flight treatment for a team
    draft, rendering the two team columns in place of the RSVP columns. Once the draft finalizes the
    members carry each player's record and deck colors, which the column then shows beside the name."""
    unix = int(event_time.timestamp())
    note = f"\n> {description}" if description else ""
    symbol = emojis.get(set_code.lower()) if set_code else ""
    suffix = f"{NBSP}{symbol}" if symbol else ""
    title_name = team_aware_pod_name(name, "team" if team_draft else None)
    title = f"### {NBSP * 2}🗓️ {title_name}{suffix}"
    if team_rosters is not None:
        header = f"{title}\n{status_line}" if status_line else title
        embed = discord.Embed(description=f"{header}{note}", color=discord.Color.green())
        _add_team_columns(embed, team_rosters)
        embed.add_field(name=NBSP, value=f"<t:{unix}:R>", inline=False)
        return embed
    if locked_roster is not None:
        header = f"{title}\n{status_line}" if status_line else title
        roster_text = _locked_roster_text(locked_roster, draft_complete)
        embed = discord.Embed(
            description=f"{header}{note}\n\n{roster_text}\n<t:{unix}:R>",
            color=discord.Color.green(),
        )
        return embed
    calendar_url = google_calendar_url(name, event_time)
    if status_line is not None:
        middle = f"{status_line}{note}"
    elif announcement is not None:
        middle = f"{announcement}{note}"
    else:
        middle = f"{_intro_line(role_time or event_time)}{note}{_multipod_suffix(rosters)}"
    embed = discord.Embed(description=f"{title}\n{middle}", color=discord.Color.green())
    time_value = f"<t:{unix}:F> (<t:{unix}:R>) [[+]](<{calendar_url}>)"
    embed.add_field(name=TIME_LABEL, value=time_value, inline=False)
    add_roster_fields(embed, rosters, roster_interests, championship=announcement is not None)
    return embed


def _intro_line(role_time: datetime) -> str:
    spec = auto_grant_spec_for_event(role_time) or spec_named(LATE_POD_ROLE_NAME)
    return CARD_INTRO.format(emoji=display_emoji(spec) or "")


def _multipod_suffix(rosters: dict[str, list[str]]) -> str:
    """The multi-pod heads-up only earns a line once one pod's worth of Yes has signed up."""
    yes = rosters.get(RSVP_YES) or []
    return f"\n{MULTIPOD_NOTICE}" if len(yes) >= POD_CAPACITY else ""


def google_calendar_url(name: str, event_time: datetime) -> str:
    start = event_time.astimezone(timezone.utc)
    end = start + timedelta(hours=EVENT_DURATION_H)
    query = urlencode({
        "action": "TEMPLATE",
        "text": name,
        "dates": f"{start:%Y%m%dT%H%M%SZ}/{end:%Y%m%dT%H%M%SZ}",
    })
    return f"https://www.google.com/calendar/event?{query}"


LOCKED_DRAFTERS_LABEL = "Players"
LOCKED_STANDINGS_LABEL = "Final Standings"
_LOCKED_MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}
ROSTER_GAP = NBSP * 2


def _locked_roster_text(players: list[DraftedPlayer], draft_complete: bool) -> str:
    """The locked-roster block the card shows once the draft starts, in place of the RSVP columns:
    the actual drafters under a bold header. While the pod runs they list in seat order by name alone —
    the card re-renders only on lifecycle transitions, not per match report, so a running record would
    freeze at its draft-done value and drift as results come in. On completion the roster reorders by
    placement and reads as the final standings, with medals, records, and colors."""
    ordered = _order_locked_roster(players, draft_complete)
    if draft_complete:
        rows = [_final_standings_row(rank, player) for rank, player in enumerate(ordered, 1)]
        header = f"**{LOCKED_STANDINGS_LABEL}**"
    else:
        rows = [_drafter_row(player) for player in ordered]
        header = f"**{LOCKED_DRAFTERS_LABEL} ({len(ordered)})**"
    return f"{header}\n" + ("\n".join(rows) or "-")


def _order_locked_roster(players: list[DraftedPlayer], draft_complete: bool) -> list[DraftedPlayer]:
    if draft_complete and all(player.placement is not None for player in players):
        return sorted(players, key=lambda player: player.placement)
    return sorted(players, key=lambda player: (player.seat_index is None, player.seat_index or 0))


def _drafter_row(player: DraftedPlayer) -> str:
    return f"> {player.display_name}"


def _final_standings_row(rank: int, player: DraftedPlayer) -> str:
    medal = _LOCKED_MEDALS.get(rank)
    prefix = f"{rank}. {medal} " if medal else f"{rank}. "
    parts = [f"{prefix}{player.display_name}"]
    if player.record:
        parts.append(player.record)
    glyph = format_deck_color_emojis(player.deck_colors)
    if glyph:
        parts.append(glyph)
    return ROSTER_GAP.join(parts)


def _add_team_columns(
    embed: discord.Embed, team_rosters: dict[str, list[TeamBoardMember]],
) -> None:
    """Green / Blue roster columns for a team draft in flight, Discord names only. Mirrors the team
    board's roster header, the surface these players report on, so the two never drift. Once the draft
    finalizes each row also carries the player's record and deck colors."""
    for team in (pod_team.TEAM_A, pod_team.TEAM_B):
        members = team_rosters.get(team) or []
        header = f"{pod_team.team_emoji(team)} {pod_team.team_label(team)}"
        value = "\n".join(_team_member_row(member) for member in members) or "—"
        embed.add_field(name=header, value=value, inline=True)


def _team_member_row(member: TeamBoardMember) -> str:
    """One team-column row: the Discord name, then the record and deck colors once the draft finalizes."""
    parts = [member.display]
    if member.record:
        parts.append(member.record)
    glyph = format_deck_color_emojis(member.deck_colors)
    if glyph:
        parts.append(glyph)
    return f"> {ROSTER_GAP.join(parts)}"


def refresh_roster_fields(
    embed: discord.Embed, rosters: dict[str, list[str]], status_line: str | None = None,
    roster_interests: dict[str, list[tuple[str, tuple[str, ...]]]] | None = None,
    championship: bool = False,
) -> None:
    """Swap the roster columns on a fetched surface while keeping its Time field untouched, so a
    click never needs a DB round trip for the event row. The multi-pod notice toggles with the Yes
    count on the same click, without touching the header or intro; a `status_line` replaces both
    once the pod is past gathering. A `championship` card keeps its fixed announcement body across
    refreshes and never grows the multi-pod notice, since it is not a lazy pod."""
    time_field = None
    for field in embed.fields:
        if field.name == TIME_LABEL:
            time_field = field
            break
    embed.clear_fields()
    if time_field is not None:
        embed.add_field(name=TIME_LABEL, value=time_field.value, inline=False)
    add_roster_fields(embed, rosters, roster_interests, championship=championship)
    if status_line is not None:
        embed.description = _swap_status_line(embed.description or "", status_line)
    elif not championship:
        embed.description = _strip_multipod_notice(embed.description or "") + _multipod_suffix(rosters)


def _strip_multipod_notice(description: str) -> str:
    """Peel every trailing notice, self-healing cards that stacked copies before the marker matched."""
    marker = f"\n{MULTIPOD_NOTICE}"
    while description.endswith(marker):
        description = description[: -len(marker)]
    return description


def _swap_status_line(description: str, status_line: str) -> str:
    """Rebuild a fetched card description around the lifecycle status: the title line, the status,
    then any organizer note — dropping the RSVP intro, the multi-pod notice, and any earlier status."""
    lines = description.split("\n")
    notes = [line for line in lines[1:] if line.startswith("> ")]
    return "\n".join([lines[0], status_line, *notes])


def card_status_line(event_id: str | None) -> str | None:
    """The lifecycle status the card shows in place of the RSVP intro once the pod is past gathering:
    Drafting during picks, Playing through the match rounds, the champion headline at the end. None
    while RSVPs still matter — a draft restart lands back here and the card reverts on its own. Reads
    the live manager only; `resolve_card_status_line` adds the persisted fallback for finished pods."""
    if event_id is None:
        return None
    manager = ACTIVE_POD_MANAGERS.get(event_id)
    if manager is None:
        return None
    if manager.card_result_line:
        return manager.card_result_line
    if manager.draft_complete:
        return CARD_STATUS_PLAYING
    if manager.drafting:
        return CARD_STATUS_DRAFTING
    return None


async def resolve_card_status_line(event_id: str | None) -> str | None:
    """Card lifecycle status from the live manager while one exists, else rebuilt from the persisted
    event row. Without this fallback a finished pod or a post-restart card drops back to the RSVP intro
    once its manager is gone, since the status was memory-only."""
    status_line, _ = await resolve_card_render_state(event_id)
    return status_line


async def resolve_card_render_state(event_id: str | None) -> tuple[str | None, bool]:
    """The card's status line plus whether it is a Set Championship still gathering RSVPs. The
    championship flag keeps a roster refresh from re-growing the multi-pod notice on the frozen
    announcement body; it only matters while no status line applies, which is exactly the gathering
    window a live manager has not opened yet."""
    if event_id is None:
        return None, False
    if ACTIVE_POD_MANAGERS.get(event_id) is not None:
        return card_status_line(event_id), False
    return await _persisted_card_render_state(event_id)


async def _persisted_card_render_state(event_id: str) -> tuple[str | None, bool]:
    row = await asyncio.to_thread(_load_card_lifecycle_sync, event_id)
    if row is None:
        return None, False
    socket_status, championship_posted, is_championship, pairing_mode = row
    if championship_posted or socket_status == "complete":
        if pairing_mode == "team":
            line = await asyncio.to_thread(_persisted_team_result_line_sync, event_id)
            return line or CARD_STATUS_PLAYING, False
        return await champion_card_line(event_id), False
    if socket_status == "draft_done":
        return CARD_STATUS_PLAYING, False
    if socket_status == "connected":
        return CARD_STATUS_DRAFTING, False
    return None, is_championship


def _persisted_team_result_line_sync(event_id: str) -> str | None:
    return team_result_headline(load_team_board_data(event_id))


def _load_card_lifecycle_sync(event_id: str) -> tuple[str, bool, bool, str | None] | None:
    with SessionLocal() as session:
        row = session.execute(
            select(
                PodDraftEvent.socket_status, PodDraftEvent.championship_posted_at,
                PodDraftEvent.name, PodDraftEvent.pairing_mode,
            )
            .where(PodDraftEvent.id == event_id)
        ).one_or_none()
    if row is None:
        return None
    return row[0], row[1] is not None, is_championship(row[2]), row[3]


def slot_role_mention(guild: discord.Guild | None, event_time: datetime) -> str | None:
    """Bare role mention as the card's content line, sesh-style — only content pings, embeds never
    do. The slot role is resolved off the poll buckets by weekend and time-of-day; an off-grid custom
    time resolves to no slot and pings nobody rather than mis-tagging a neighbouring slot."""
    spec = auto_grant_spec_for_event(event_time)
    if spec is None:
        return None
    role = find_role(guild, spec.name)
    return role.mention if role else None


def _card_ping(
    guild: discord.Guild | None, event_time: datetime, ping_role: bool, notify_role_name: str | None,
) -> str | None:
    """The card's content ping. An explicit notify role overrides the slot-derived one; otherwise the
    slot role fires when ping_role is set, and nobody is pinged when it is not."""
    if notify_role_name is not None:
        role = find_role(guild, notify_role_name)
        return role.mention if role else None
    if ping_role:
        return slot_role_mention(guild, event_time)
    return None


async def post_scheduled_card(
    bot: commands.Bot, channel: discord.TextChannel, *, set_code: str, event_time: datetime, name: str,
    preseed_yes: list[tuple[str, str]] | None = None, ping_role: bool = True,
    notify_role_name: str | None = None, description: str | None = None,
    pairing_mode: str | None = None, seating_mode: str | None = None, pick_timer: int | None = None,
    content_override: str | None = None, card_body: str | None = None, format_locked: bool = True,
) -> str | None:
    """Create a scheduled pod end to end and return its event id, or None when the thread or the
    card could not be posted. The signal is born fired, so the RSVP buttons never close.

    `format_locked` defaults on: the organizer chose the set, so the card shows a plain Yes / Maybe
    roster and every preference surface stays off. A graduated launcher slot passes False, since it is
    the flex surface that resolves its format from the roster's Latest/Flashback preferences.

    The thread hangs off the card, so a single edit to the card updates both the channel and the
    thread starter. A starter's own buttons render dead in-thread, so the registered embed carries
    the labeled RSVP row for the thread.

    `preseed_yes` is (user_id, display_name) of players who already committed — daily-poll signups
    graduating to a card. They start in the Yes column, are recorded Yes on the signal, and are
    pulled into the thread; Maybe and No start empty.

    `content_override` replaces the card's content ping outright — a fired launcher slot's creation
    announcement, carrying its own role mention. `card_body` is a fixed announcement rendered inside
    the embed in place of the RSVP intro, for a championship card that never fires a second table."""
    preseed_yes = preseed_yes or []
    rosters = {state: [] for state in RSVP_STATES}
    rosters[RSVP_YES] = [display for _, display in preseed_yes]
    guild = channel.guild
    name = await pod_launch.dedupe_pod_name(channel, name)
    content = content_override if content_override is not None else _card_ping(
        guild, event_time, ping_role, notify_role_name)
    try:
        message = await channel.send(
            content=content,
            embed=build_rsvp_embed(
                name, event_time, rosters, description=description, set_code=set_code,
                team_draft=pairing_mode == "team", announcement=card_body,
            ),
            view=PodRsvpView(),
            allowed_mentions=discord.AllowedMentions(roles=True),
        )
        thread = await message.create_thread(name=name[:100])
    except discord.HTTPException:
        log.warning("post_scheduled_card: could not post the card or create its thread", exc_info=True)
        return None

    signal_id = await asyncio.to_thread(
        pod_launch.create_scheduled_signal_sync,
        guild_id=str(guild.id), channel_id=str(channel.id), message_id=str(message.id),
        event_time=event_time, pick_timer=pick_timer, format_locked=format_locked,
    )
    if preseed_yes:
        await asyncio.to_thread(pod_launch.seed_yes_members_sync, signal_id, preseed_yes)
    native_event_id = await _create_native_event(channel, name, event_time, message.jump_url, rosters)
    event_id, created_at, pairing_mode, seating_mode = await asyncio.to_thread(
        _record_scheduled_event, set_code, event_time, name, str(thread.id), native_event_id,
        pairing_mode, seating_mode, description,
    )
    await asyncio.to_thread(pod_launch.link_event_sync, signal_id, event_id)

    try:
        registered = await thread.send(
            embed=build_registered_embed(
                set_code.upper(), pairing_mode, seating_mode,
                championship=is_championship(name), rsvp_hint=True,
                channel_post_url=message.jump_url, guild=guild,
            ),
            view=ScheduledRegisteredView(),
        )
        await asyncio.to_thread(pod_launch.set_thread_message_sync, signal_id, str(registered.id))
        if description:
            await thread.send(description)
    except discord.HTTPException:
        log.warning(f"could not post the registered embed in thread {thread.id}", exc_info=True)

    await _add_members_to_thread(thread, preseed_yes)
    pod_launch.arm_scheduled_pod_jobs(bot, event_id, event_time, created_at)
    log.info(f"posted scheduled pod card for {name} as message {message.id} (event {event_id})")
    await _refresh_launcher(bot, event_time)
    return event_id


async def _add_members_to_thread(thread: discord.Thread, members: list[tuple[str, str]]) -> None:
    """Pull preseeded Yes players into the thread so coordination reaches them from the start."""
    for user_id, _ in members:
        if not user_id.isdigit():
            continue
        try:
            await thread.add_user(discord.Object(id=int(user_id)))
        except discord.HTTPException:
            log.warning(f"could not add {user_id} to thread {thread.id}", exc_info=True)


async def _handle_rsvp(interaction: discord.Interaction, state: str) -> None:
    await apply_card_rsvp(interaction, str(interaction.message.id), state)


async def apply_card_rsvp(
    interaction: discord.Interaction, surface_message_id: str, state: str,
    *, refresh_launcher: bool = True,
) -> None:
    """Record an RSVP on the card behind `surface_message_id` and run every follow-on: the grant, the
    confirmation, thread membership, surface re-renders, the native-event tally, and the nudge and
    launcher refreshes. The clicked surface may be the card, the thread's registered embed, or a
    launcher slot that resolves to the card, so `surface_message_id` is the card the write targets while
    `interaction.message` is whatever was clicked. A launcher-slot caller passes `refresh_launcher=False`
    and re-renders the clicked launcher itself, so the board updates in whatever channel it lives in.

    Every answer names the pod it landed on, since a click can come from the card, its thread, the roster
    reminder, or a launcher button, and only the pod's own name reads the same from all four."""
    result = await asyncio.to_thread(
        pod_launch.set_rsvp_sync,
        surface_message_id, str(interaction.user.id), interaction.user.display_name, state,
    )
    if result is None or result.closed:
        await interaction.response.send_message(MSG_CARD_INACTIVE, ephemeral=True)
        return

    status_line, championship = await resolve_card_render_state(result.state.event_id)
    if _is_card_surface(interaction.message):
        embed = interaction.message.embeds[0]
        refresh_roster_fields(
            embed, result.rosters, status_line, result.roster_interests, championship=championship,
        )
        await interaction.response.edit_message(embed=embed)
    else:
        await interaction.response.defer(ephemeral=True)

    first_pod = False
    granted_role = None
    slot_spec = slot_ping = None
    if result.joined and isinstance(interaction.user, discord.Member):
        first_pod = await grant_pod_drafters(interaction.user)
        if not championship:
            slot_spec = auto_grant_spec_for_event(result.state.slot_time)
            slot_ping = slot_grant_ping(slot_spec) if slot_spec is not None else None
            granted_role = await _grant_slot_role(interaction.user, result.state.slot_time)
    notice = await announce_pod_grant(
        interaction, first_pod=first_pod, granted_role=granted_role, spec=slot_spec, ping=slot_ping,
        card_lead=await _confirmation_card_lead(result),
    )
    if notice != NOTICE_GRANT:
        if result.rsvp in (RSVP_YES, RSVP_MAYBE):
            lead = await _confirmation_lead_text(result)
            if granted_role is not None and slot_ping is not None:
                lead = f"{lead}\n{pod_role_grant_text(granted_role.mention, slot_ping)}"
            await send_join_confirmation_card(
                interaction, lead=lead, accent=RSVP_CONFIRM_COLOR[result.rsvp],
            )
        else:
            await interaction.followup.send(embed=await _confirmation_embed(result), ephemeral=True)

    if result.state.event_id is not None:
        join = result.rsvp in (RSVP_YES, RSVP_MAYBE)
        await _set_thread_membership(interaction, result.state.event_id, join=join)
        await _sync_other_surfaces(
            interaction.client, result.state.event_id, str(interaction.message.id),
            result.rosters, result.roster_interests,
        )
        await _sync_native_event_tally(interaction.guild, surface_message_id, result.rosters)
        yes = result.rosters.get(RSVP_YES) or []
        maybe = result.rosters.get(RSVP_MAYBE) or []
        await refresh_underfill_nudge_for_event(interaction.client, result.state.event_id, len(yes), len(maybe))
        await refresh_roster_reminder_for_event(result.state.event_id)
        if championship and result.yes_changed:
            notify_seeding_change(interaction.client, result.state.event_id)
        if result.yes_changed and refresh_launcher:
            await _refresh_launcher(interaction.client, result.state.slot_time)


async def _refresh_launcher(bot: commands.Bot, slot_time: datetime | None) -> None:
    if _launcher_refresh is None or slot_time is None:
        return
    await _launcher_refresh(bot, slot_time.astimezone(SCHEDULE_TZ).date())


async def _refresh_launcher_for_event(bot: commands.Bot, event_id: str) -> None:
    """Repaint the launcher for a pod whose own identity moved: the board renders a fired pod's start time
    and its format off the event, and keys its button on that format, so a reschedule, a format change or a
    draft start leaves the column stale until something else happens to repaint it.

    Keyed on the signal's `slot_time`, the slot the pod was gathered in, not on the pod's new start: that is
    the board carrying it, and a pod moved across midnight would otherwise refresh the wrong day."""
    ref = await asyncio.to_thread(pod_launch.scheduled_card_ref_sync, event_id)
    if ref is None:
        return
    await _refresh_launcher(bot, ref[3])


async def _grant_slot_role(member: discord.Member, slot_time: datetime | None) -> discord.Role | None:
    """Returns the role only on a fresh grant, so the ephemeral confirmation fires once per member.
    The signal's slot_time keys the role, so a postponed pod still grants its original slot."""
    if slot_time is None:
        return None
    spec = auto_grant_spec_for_event(slot_time)
    if spec is None:
        return None
    role = find_role(member.guild, spec.name)
    if role is None:
        return None
    granted = await grant_role(member, role)
    return role if granted else None


def _is_card_surface(message: discord.Message) -> bool:
    """Whether a clicked message renders the card embed itself (the channel card) versus a
    controls-only surface like the thread's registered embed."""
    if not message.embeds:
        return False
    return any(field.name == TIME_LABEL for field in message.embeds[0].fields)


def pod_removed_embed(pod_name: str) -> discord.Embed:
    """The bare red note for leaving a pod, named after the pod itself. The start time and the pod controls
    are moot once you're not in, so an add answers with the full card and a removal with this."""
    return discord.Embed(title=MSG_POD_REMOVED.format(name=pod_name), color=discord.Color.red())


async def _confirmation_embed(result: pod_launch.RsvpResult) -> discord.Embed:
    """The one-line acknowledgement for No and a cleared RSVP. Yes and Maybe answer with the full
    confirmation card via `send_join_confirmation_card` instead."""
    name, _event_time = await _pod_identity(result)
    if result.rsvp is None:
        return pod_removed_embed(name)
    title = _rsvp_headline(result.rsvp, name)
    return discord.Embed(title=title, color=RSVP_CONFIRM_COLOR[result.rsvp])


async def _confirmation_lead_text(result: pod_launch.RsvpResult) -> str:
    """The Yes/Maybe acknowledgement as card text: the pod that was joined over its start time."""
    name, event_time = await _pod_identity(result)
    lead = f"### {_rsvp_headline(result.rsvp, name)}"
    if event_time is None:
        return lead
    return f"{lead}\n{MSG_DRAFT_STARTS.format(unix=int(event_time.timestamp()))}"


async def _confirmation_card_lead(result: pod_launch.RsvpResult) -> str | None:
    """The RSVP acknowledgement as grant-card text, so a click that also grants a role delivers one
    message instead of an embed plus a card. Only a fresh Yes can grant, so other states return None."""
    if not result.joined or result.rsvp is None:
        return None
    return await _confirmation_lead_text(result)


def _rsvp_headline(rsvp: str, pod_name: str) -> str:
    return (MSG_POD_ADDED if rsvp == RSVP_YES else MSG_POD_MAYBE).format(name=pod_name)


async def _pod_identity(result: pod_launch.RsvpResult) -> tuple[str, datetime | None]:
    """(pod name, start time) for an acknowledgement, read off the pod in one query. A signal with no pod on
    it yet is named for the format and slot it will carry, which is the name the pod takes when it fires."""
    if result.state.event_id is not None:
        loaded = await asyncio.to_thread(_load_event, result.state.event_id)
        if loaded is not None:
            return loaded[0], loaded[1]
    return pod_display_name(
        result.state.set_code or active_set_code(), result.state.slot_time or datetime.now(timezone.utc),
    ), result.state.slot_time


async def _set_thread_membership(interaction: discord.Interaction, event_id: str, *, join: bool) -> None:
    """Thread membership follows the RSVP: Yes and Maybe pull the member in so coordination reaches
    them, No takes them back out."""
    await _move_member_thread(interaction.client, event_id, interaction.user, join=join)


async def _move_member_thread(
    bot: commands.Bot, event_id: str, user: discord.abc.User, *, join: bool,
) -> None:
    thread = await _resolve_event_thread(bot, event_id)
    if thread is None:
        return
    try:
        if join:
            await thread.add_user(user)
        else:
            await thread.remove_user(user)
    except discord.HTTPException:
        action = "add" if join else "remove"
        log.warning(f"could not {action} {user} on thread {thread.id}", exc_info=True)


async def _resolve_event_thread(bot: commands.Bot, event_id: str | None) -> discord.Thread | None:
    if event_id is None:
        return None
    thread_id = await asyncio.to_thread(pod_launch.event_thread_id_sync, event_id)
    if thread_id is None:
        return None
    thread = await fetch_channel(bot, thread_id)
    return thread if isinstance(thread, discord.Thread) else None


async def _sync_other_surfaces(
    bot: commands.Bot, event_id: str, clicked_message_id: str, rosters: dict[str, list[str]],
    roster_interests: dict[str, list[tuple[str, tuple[str, ...]]]] | None = None,
) -> None:
    """Re-render the channel card when a thread-side button was clicked. The card is the thread
    starter, so editing it updates the thread view too; the registered embed carries no card fields
    and needs no roster sync."""
    card = await asyncio.to_thread(pod_launch.scheduled_card_ref_sync, event_id)
    if card is None:
        return
    _, _, message_id, _ = card
    if message_id == clicked_message_id:
        return
    await _render_channel_card(bot, event_id, rosters, roster_interests)


async def _render_channel_card(
    bot: commands.Bot, event_id: str, rosters: dict[str, list[str]],
    roster_interests: dict[str, list[tuple[str, tuple[str, ...]]]] | None = None,
) -> None:
    card = await asyncio.to_thread(pod_launch.scheduled_card_ref_sync, event_id)
    if card is None:
        return
    _, channel_id, message_id, _ = card
    channel = await fetch_channel(bot, channel_id)
    if channel is None:
        return
    try:
        message = await channel.fetch_message(int(message_id))
    except discord.HTTPException:
        return
    if not _is_card_surface(message):
        return
    embed = message.embeds[0]
    status_line, championship = await resolve_card_render_state(event_id)
    refresh_roster_fields(embed, rosters, status_line, roster_interests, championship=championship)
    try:
        await message.edit(embed=embed)
    except discord.HTTPException:
        log.warning(f"could not render the channel card {message_id}", exc_info=True)


async def fetch_channel(bot: commands.Bot, channel_id: str) -> discord.abc.Messageable | None:
    channel = bot.get_channel(int(channel_id))
    if channel is not None:
        return channel
    try:
        return await bot.fetch_channel(int(channel_id))
    except discord.HTTPException:
        return None


def native_event_description(rosters: dict[str, list[str]], jump_url: str) -> str:
    """The native event's body: a live RSVP tally over the card's link. Discord exposes no read/write
    interest API for a guild scheduled event, so this text is the only surface that can carry the
    counts the card holds."""
    tally = " ".join(
        f"{RSVP_EMOJI[state]} {len(rosters.get(state) or [])}" for state in (RSVP_YES, RSVP_MAYBE)
    )
    return f"{tally}\n\n{NATIVE_EVENT_SIGNUP.format(jump_url=jump_url)}"


async def _create_native_event(
    channel: discord.TextChannel, name: str, event_time: datetime, jump_url: str,
    rosters: dict[str, list[str]],
) -> str | None:
    if event_time <= datetime.now(timezone.utc):
        return None
    try:
        native = await channel.guild.create_scheduled_event(
            name=name,
            start_time=event_time,
            end_time=event_time + timedelta(hours=EVENT_DURATION_H),
            entity_type=discord.EntityType.external,
            privacy_level=discord.PrivacyLevel.guild_only,
            location=jump_url,
            description=native_event_description(rosters, jump_url),
        )
    except discord.HTTPException:
        log.warning("could not create the native scheduled event", exc_info=True)
        return None
    return str(native.id)


async def _sync_native_event_tally(
    guild: discord.Guild | None, message_id: str, rosters: dict[str, list[str]],
) -> None:
    """Re-render the native event's tally after a click on any RSVP surface. The card stays the
    canonical roster; this keeps the Events tab's count honest."""
    if guild is None:
        return
    ref = await asyncio.to_thread(pod_launch.native_event_ref_by_surface_sync, message_id)
    if ref is None:
        return
    native_event_id, guild_id, channel_id, card_message_id = ref
    jump_url = f"https://discord.com/channels/{guild_id}/{channel_id}/{card_message_id}"
    try:
        event_id_int = int(native_event_id)
        native = guild.get_scheduled_event(event_id_int) or await guild.fetch_scheduled_event(event_id_int)
        await native.edit(description=native_event_description(rosters, jump_url))
    except discord.HTTPException:
        log.warning(f"could not sync native event tally {native_event_id}", exc_info=True)


async def purge_native_events(guild: discord.Guild, bot_user_id: int) -> int:
    """Delete every scheduled event this bot created in the guild, clearing the Events calendar. Backs
    `!test reset`; other creators' events (sesh, humans) are left alone."""
    try:
        events = await guild.fetch_scheduled_events()
    except discord.HTTPException:
        log.warning("could not fetch scheduled events for purge", exc_info=True)
        return 0
    deleted = 0
    for event in events:
        if event.creator_id != bot_user_id:
            continue
        try:
            await event.delete()
            deleted += 1
        except discord.HTTPException:
            log.warning(f"could not delete scheduled event {event.id}", exc_info=True)
    return deleted


def _record_scheduled_event(
    set_code: str, event_time: datetime, name: str, thread_id: str, native_event_id: str | None,
    pairing_mode: str | None = None, seating_mode: str | None = None, description: str | None = None,
) -> tuple[str, datetime, str, str]:
    with SessionLocal() as session:
        event = record_ondemand_event(
            session, set_code=set_code, event_time=event_time, name=name, discord_thread_id=thread_id,
        )
        event.discord_scheduled_event_id = native_event_id
        event.description = description
        if pairing_mode is not None:
            event.pairing_mode = pairing_mode
        if seating_mode is not None:
            event.seating_mode = seating_mode
        session.commit()
        session.refresh(event)
        return event.id, event.created_at, event.pairing_mode, event.seating_mode


async def reschedule_event(
    bot: commands.Bot, event_id: str, raw: str, *, guild: discord.Guild | None, actor_id: str,
) -> str | None:
    """Move a scheduled pod to a new time and re-sync everything hanging off the old one: the event
    row, every timed job, the card timestamps, any live nudge or roster reminder, and a thread note.
    The native Discord scheduled event moves in a detached task since its edit is slow and rate-limited
    and need not block the interaction. Returns an error string for the caller to surface, or None on
    success. Reachable from the lobby Settings panel; there is no 'too late' cutoff by design."""
    loaded = await asyncio.to_thread(_load_event, event_id)
    if loaded is None:
        return MSG_CARD_INACTIVE
    name, event_time, _status, thread_id, native_event_id, created_at = loaded
    new_time = parse_new_time(raw, event_time, datetime.now(timezone.utc))
    if new_time is None:
        return MSG_BAD_TIME
    await asyncio.to_thread(_apply_new_time, event_id, new_time)
    pod_launch.arm_scheduled_pod_jobs(bot, event_id, new_time, created_at)
    yes_roster, maybe_roster = await asyncio.gather(
        asyncio.to_thread(pod_launch.roster_for_event_sync, event_id),
        asyncio.to_thread(pod_launch.maybe_roster_for_event_sync, event_id),
    )
    mention_block = _reschedule_mentions(yes_roster, maybe_roster)
    actor_name = _actor_display_name(guild, actor_id)
    asyncio.create_task(_update_native_event(guild, native_event_id, new_time))
    await asyncio.gather(
        _edit_scheduled_card(bot, event_id, name, new_time),
        _refresh_live_messages(bot, event_id),
        _post_thread_note(bot, thread_id, new_time, actor_name, mention_block),
        _refresh_launcher_for_event(bot, event_id),
    )
    audit.event(
        "pod_postpone", user_id=actor_id, event_id=event_id,
        old_time=event_time.isoformat(), new_time=new_time.isoformat(),
    )
    return None


async def _edit_scheduled_card(bot: commands.Bot, event_id: str, name: str, event_time: datetime) -> None:
    """Re-render the channel card from scratch — name, set symbol, time, description, rosters. It is
    the thread starter, so the thread view moves with it. Poll and queue-born pods have no card at
    all. Shared by reschedule (new time) and a format change (new name + symbol)."""
    ref = await asyncio.to_thread(pod_launch.scheduled_card_ref_sync, event_id)
    if ref is None:
        return
    _, channel_id, message_id, slot_time = ref
    roster_interests = await asyncio.to_thread(pod_launch.rsvp_rosters_with_interest_sync, message_id)
    if roster_interests is None:
        return
    rosters = {state: [name for name, _ in members] for state, members in roster_interests.items()}
    if await asyncio.to_thread(pod_launch.format_locked_for_event_sync, event_id):
        roster_interests = None
    channel = await fetch_channel(bot, channel_id)
    if channel is None:
        return
    description = await asyncio.to_thread(_event_description, event_id)
    set_code = await asyncio.to_thread(load_event_set_code_sync, event_id)
    pairing_mode = await asyncio.to_thread(load_event_pairing_mode_sync, event_id)
    status_line = await resolve_card_status_line(event_id)
    team_rosters = await _team_card_rosters(event_id, pairing_mode, status_line)
    locked_roster, draft_complete = await _solo_card_roster(event_id, pairing_mode, status_line)
    try:
        message = await channel.fetch_message(int(message_id))
        await message.edit(embed=build_rsvp_embed(
            name, event_time, rosters, slot_time, description, set_code=set_code,
            team_draft=pairing_mode == "team", status_line=status_line,
            roster_interests=roster_interests, team_rosters=team_rosters,
            locked_roster=locked_roster, draft_complete=draft_complete))
    except discord.HTTPException:
        log.warning(f"could not edit scheduled card {message_id}", exc_info=True)


async def _team_card_rosters(
    event_id: str, pairing_mode: str | None, status_line: str | None,
) -> dict[str, list[TeamBoardMember]] | None:
    """Green / Blue rosters for a team draft past gathering, read from the same board rows the players
    report on. None while the pod still gathers or before teams are assigned, so the card keeps its
    RSVP columns until the draft locks the teams in. Records and deck colors ride the members only once
    the draft finalizes, so an opponent can't scout colors while matches are live."""
    if pairing_mode != "team" or status_line is None:
        return None
    board = await asyncio.to_thread(load_team_board_data, event_id)
    if board.finalized:
        rosters = board.rosters
    else:
        rosters = {
            team: [member._replace(record=None, deck_colors=None) for member in members]
            for team, members in board.rosters.items()
        }
    if not any(rosters.values()):
        return None
    return rosters


async def _solo_card_roster(
    event_id: str, pairing_mode: str | None, status_line: str | None,
) -> tuple[list[DraftedPlayer] | None, bool]:
    """The locked drafters that replace a non-team pod's RSVP columns once the draft starts, and whether
    the pod is finalized. None while the pod still gathers or before the draft seeds its seats, so the
    card keeps its RSVP columns until real drafters exist. In flight the rows carry seat order and the
    running record only; deck colors ride along but stay hidden until the final standings render."""
    if pairing_mode == "team" or status_line is None:
        return None, False
    drafters, finalized = await asyncio.to_thread(load_solo_card_drafters, event_id)
    if not drafters:
        return None, False
    roster = [
        DraftedPlayer(
            display_name=drafter.display_name, seat_index=drafter.seat_index,
            record=drafter.record, placement=drafter.placement, deck_colors=drafter.deck_colors,
        )
        for drafter in drafters
    ]
    return roster, finalized


async def refresh_scheduled_card(bot: commands.Bot, event_id: str) -> None:
    """Surface a mid-lobby pairing change on every scheduling surface — the channel card title, the
    thread name, and the native event. Fired when a pod locks into a Team Draft."""
    loaded = await asyncio.to_thread(_load_event, event_id)
    if loaded is None:
        return
    name, event_time, _status, thread_id, native_event_id, _created_at = loaded
    pairing_mode = await asyncio.to_thread(load_event_pairing_mode_sync, event_id)
    display_name = team_aware_pod_name(name, pairing_mode)
    await _edit_scheduled_card(bot, event_id, name, event_time)
    await _rename_thread(bot, thread_id, display_name)
    await _rename_native_event(bot, thread_id, native_event_id, display_name)


async def refresh_card_phase(bot: commands.Bot, event_id: str) -> None:
    """Re-render the channel card for a lifecycle change — draft start, a restart, draft done, the
    champion post — picking up the current status line. Embed only: no thread or native-event renames,
    so frequent transitions never touch Discord's slow rename limits. Once the championship post is
    known, both card surfaces also gain a jump button to it. The launcher board repaints with it, since draft
    start is where a pod stops taking signups and its slot has to collapse to one line then rather than
    whenever the next click happens."""
    loaded = await asyncio.to_thread(_load_event, event_id)
    if loaded is None:
        return
    name, event_time, _status, _thread_id, _native_event_id, _created_at = loaded
    await _edit_scheduled_card(bot, event_id, name, event_time)
    await _attach_result_link(bot, event_id)
    await _refresh_launcher_for_event(bot, event_id)


HEAL_LOOKBACK_DAYS = 3


async def heal_finished_cards(bot: commands.Bot) -> None:
    """Re-render recently finished pods' channel cards on startup so any that reverted to the RSVP
    intro while their manager was gone pick up the persisted status. No-op for pods without a card."""
    event_ids = await asyncio.to_thread(_recent_finished_event_ids_sync)
    for event_id in event_ids:
        await refresh_card_phase(bot, event_id)


def _recent_finished_event_ids_sync() -> list[str]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=HEAL_LOOKBACK_DAYS)
    with SessionLocal() as session:
        rows = session.execute(
            select(PodDraftEvent.id).where(
                PodDraftEvent.socket_status.in_(("connected", "draft_done", "complete")),
                PodDraftEvent.event_time >= cutoff,
            )
        ).all()
    return [row[0] for row in rows]


async def heal_format_locked_cards(bot: commands.Bot) -> None:
    """Re-render the still-gathering cards of format-locked pods on startup, so a card posted before the
    format lock existed drops its stale Latest/Flashback split for a plain roster. Also refreshes the
    roster reminder, which no-ops when the pod has not reached its T-60 reminder yet."""
    event_ids = await asyncio.to_thread(_pending_format_locked_event_ids_sync)
    for event_id in event_ids:
        await refresh_event_rsvp_surfaces(bot, event_id)


def _pending_format_locked_event_ids_sync() -> list[str]:
    with SessionLocal() as session:
        rows = session.execute(
            select(PodDraftEvent.id)
            .join(PodSignal, PodSignal.event_id == PodDraftEvent.id)
            .where(
                PodSignal.format_locked.is_(True),
                PodDraftEvent.socket_status.in_(("pending", "reminded")),
            )
        ).all()
    return [row[0] for row in rows]


RESULT_LINK_LABEL = "Championship Post"


async def _attach_result_link(bot: commands.Bot, event_id: str) -> None:
    """Put a jump button to the championship post on the channel card and on the registered embed in
    the event thread, whose own controls dropped at draft_done. No-op until the post exists."""
    manager = ACTIVE_POD_MANAGERS.get(event_id)
    url = manager.card_result_url if manager is not None else None
    if not url:
        return
    surfaces = await asyncio.to_thread(pod_launch.event_card_surfaces_sync, event_id)
    if surfaces is None:
        return
    channel_id, message_id, thread_id, thread_message_id = surfaces
    await _edit_message_view(bot, channel_id, message_id, _result_link_view(url))
    if thread_id and thread_message_id:
        await _edit_message_view(bot, thread_id, thread_message_id, _result_link_view(url))


def _result_link_view(url: str) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(
        label=RESULT_LINK_LABEL, style=discord.ButtonStyle.link, url=url, emoji="🏆",
    ))
    return view


async def _edit_message_view(bot: commands.Bot, channel_id: str, message_id: str, view: discord.ui.View) -> None:
    channel = await fetch_channel(bot, channel_id)
    if channel is None:
        return
    try:
        await channel.get_partial_message(int(message_id)).edit(view=view)
    except discord.HTTPException:
        log.warning(f"could not attach the result link to message {message_id}", exc_info=True)


async def reflect_format_change(bot: commands.Bot, event_id: str) -> None:
    """Mirror a pre-draft format change onto the surfaces addressed by stored ids: the channel card
    title (new name + set symbol) and the native scheduled event's name, both carrying the Team-Draft
    marker when the pod has locked into teams. The thread rename lives in set_event_format; the
    in-thread registered embed re-renders through the Settings panel. Called after the format persists,
    so the pod reads as its new format wherever the gear was clicked."""
    loaded = await asyncio.to_thread(_load_event, event_id)
    if loaded is None:
        return
    name, event_time, _status, thread_id, native_event_id, _created_at = loaded
    pairing_mode = await asyncio.to_thread(load_event_pairing_mode_sync, event_id)
    await _edit_scheduled_card(bot, event_id, name, event_time)
    await _refresh_launcher_for_event(bot, event_id)
    await _rename_native_event(bot, thread_id, native_event_id, team_aware_pod_name(name, pairing_mode))


async def refresh_event_rsvp_surfaces(bot: commands.Bot, event_id: str) -> None:
    """Re-render a pod's scheduled card and roster reminder so their format-split columns pick up a
    changed signup preference. Each surface reads the roster fresh and edits in place, so an update that
    overlaps another RSVP or preference change converges instead of racing."""
    loaded = await asyncio.to_thread(_load_event, event_id)
    if loaded is None:
        return
    name, event_time, _status, _thread_id, _native_event_id, _created_at = loaded
    await asyncio.gather(
        _edit_scheduled_card(bot, event_id, name, event_time),
        refresh_roster_reminder_for_event(event_id),
    )


async def _rename_thread(bot: commands.Bot, thread_id: str | None, name: str) -> None:
    if thread_id is None:
        return
    thread = await fetch_channel(bot, thread_id)
    if not isinstance(thread, discord.Thread):
        return
    try:
        await thread.edit(name=name[:100])
    except discord.HTTPException:
        log.warning(f"could not rename thread {thread_id}", exc_info=True)


async def _rename_native_event(
    bot: commands.Bot, thread_id: str | None, native_event_id: str | None, name: str,
) -> None:
    if native_event_id is None or thread_id is None:
        return
    thread = await fetch_channel(bot, thread_id)
    guild = getattr(thread, "guild", None)
    if guild is None:
        return
    try:
        native = await guild.fetch_scheduled_event(int(native_event_id))
        await native.edit(name=name)
    except discord.HTTPException:
        log.warning(f"could not rename native event {native_event_id}", exc_info=True)


async def _update_native_event(
    guild: discord.Guild | None, native_event_id: str | None, new_time: datetime,
) -> None:
    if guild is None or native_event_id is None:
        return
    try:
        native = await guild.fetch_scheduled_event(int(native_event_id))
        await native.edit(start_time=new_time, end_time=new_time + timedelta(hours=EVENT_DURATION_H))
    except discord.HTTPException:
        log.warning(f"postpone: could not move native event {native_event_id}", exc_info=True)


async def _refresh_live_messages(bot: commands.Bot, event_id: str) -> None:
    """The posted underfill nudge and roster reminder carry the old time; re-render them in place."""
    yes, maybe = await event_rsvps(event_id)
    await refresh_underfill_nudge_for_event(bot, event_id, len(yes), len(maybe))
    await refresh_roster_reminder_for_event(event_id)


async def _post_thread_note(
    bot: commands.Bot, thread_id: str, new_time: datetime, actor_name: str, mention_block: str = "",
) -> None:
    """The reschedule note, pinging the Yes roster so opted-in players catch the new time. Embeds never
    notify, so the mentions ride as message content beside the embed."""
    thread = await fetch_channel(bot, thread_id)
    if thread is None:
        log.warning(f"postpone: could not fetch thread {thread_id}")
        return
    unix = int(new_time.timestamp())
    embed = discord.Embed(
        title=THREAD_NOTE_TITLE.format(actor=actor_name),
        description=THREAD_NOTE_BODY.format(unix=unix, lead=REMINDER_LEAD_MIN),
        color=discord.Color.blue(),
    )
    try:
        await thread.send(
            content=mention_block or None, embed=embed,
            allowed_mentions=discord.AllowedMentions(users=True),
        )
    except discord.HTTPException:
        log.warning(f"postpone: could not post in thread {thread_id}", exc_info=True)


def _reschedule_mentions(
    yes_roster: list[tuple[str, str]], maybe_roster: list[tuple[str, str]],
) -> str:
    """Ping content beside the note: a ✅ line for the Yes roster and a 🤷 line for Maybes. Either line
    is dropped when its roster is empty."""
    lines = []
    if yes_roster:
        lines.append("✅ " + " ".join(f"<@{did}>" for did, _ in yes_roster))
    if maybe_roster:
        lines.append("🤷 " + " ".join(f"<@{did}>" for did, _ in maybe_roster))
    return "\n".join(lines)


def _actor_display_name(guild: discord.Guild | None, actor_id: str) -> str:
    if guild is not None:
        try:
            member = guild.get_member(int(actor_id))
        except ValueError:
            member = None
        if member is not None:
            return member.display_name
    return "an Organizer"


def parse_new_time(raw: str, current: datetime, now: datetime) -> datetime | None:
    """A future event time (ET) from a sesh-style phrase. Understood forms:
    a pasted Discord timestamp token ('<t:1752624000:F>', in the viewer's own zone); an 'NhNm' offset
    from the current time with an optional leading '+'; 'YYYY-MM-DD HH:MM'; a day word ('today',
    'tonight', 'tomorrow', or a
    weekday like 'fri') optionally with 'at'/'on'/'ET' filler, followed by a clock ('10pm', '8:30pm',
    '20:00'); or a bare clock. A bare clock or weekday already past today rolls forward. None when
    unreadable or not in the future."""
    raw = raw.strip().lower()
    if not raw:
        return None
    stamp = TIMESTAMP_RE.match(raw)
    if stamp:
        parsed = datetime.fromtimestamp(int(stamp.group(1)), tz=timezone.utc)
        return parsed if parsed > now else None
    offset = OFFSET_RE.match(raw)
    if offset and (offset.group(1) or offset.group(2)):
        parsed = current + timedelta(hours=int(offset.group(1) or 0), minutes=int(offset.group(2) or 0))
        return parsed if parsed > now else None
    try:
        parsed = datetime.strptime(raw, "%Y-%m-%d %H:%M").replace(tzinfo=SCHEDULE_TZ)
        return parsed if parsed > now else None
    except ValueError:
        pass
    parsed = _parse_natural_time(raw, current, now)
    return parsed if parsed is not None and parsed > now else None


def _parse_natural_time(raw: str, current: datetime, now: datetime) -> datetime | None:
    tokens = [t for t in raw.replace(",", " ").split() if t not in FILLER_TOKENS and t not in TZ_TOKENS]
    if not tokens:
        return None

    base_date = current.astimezone(SCHEDULE_TZ).date()
    day = base_date
    day_word, weekday_word = False, False
    next_week = tokens[0] == "next" and len(tokens) > 1
    if next_week:
        tokens = tokens[1:]
    head = tokens[0]
    if head in ("today", "tonight"):
        tokens, day_word = tokens[1:], True
    elif head == "tomorrow":
        day, tokens, day_word = base_date + timedelta(days=1), tokens[1:], True
    elif head in WEEKDAYS:
        ahead = (WEEKDAYS[head] - base_date.weekday()) % 7
        day, tokens, weekday_word = base_date + timedelta(days=ahead + (7 if next_week else 0)), tokens[1:], True

    clock = _parse_clock("".join(tokens))
    if clock is None:
        return None
    parsed = datetime.combine(day, clock, tzinfo=SCHEDULE_TZ)
    if parsed <= now and not day_word:
        parsed += timedelta(days=7) if weekday_word else timedelta(days=1)
    return parsed


def _parse_clock(token: str) -> dtime | None:
    match = CLOCK_RE.match(token)
    if match is None:
        return None
    hour, minute, meridiem = int(match.group(1)), int(match.group(2) or 0), match.group(3)
    if minute > 59:
        return None
    if meridiem:
        if not 1 <= hour <= 12:
            return None
        if meridiem == "pm" and hour != 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
    elif hour > 23:
        return None
    return dtime(hour, minute)


def _load_event(event_id: str) -> tuple[str, datetime, str, str, str | None, datetime] | None:
    with SessionLocal() as session:
        event = session.get(PodDraftEvent, event_id)
        if event is None:
            return None
        return (
            event.name, event.event_time, event.socket_status,
            event.discord_thread_id, event.discord_scheduled_event_id, event.created_at,
        )


def _event_description(event_id: str) -> str | None:
    with SessionLocal() as session:
        event = session.get(PodDraftEvent, event_id)
        return event.description if event is not None else None


def _apply_new_time(event_id: str, new_time: datetime) -> None:
    with SessionLocal() as session:
        event = session.get(PodDraftEvent, event_id)
        event.event_time = new_time
        event.event_date = new_time.astimezone(SCHEDULE_TZ).date()
        session.commit()
