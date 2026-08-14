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
    MSG_CARD_CREATED_BY,
    MSG_CONFIRM_BUTTON,
    MSG_CONFIRM_DONE,
    MSG_DRAFT_STARTS,
    MSG_DRAFTMANCER_LINK_LEAD,
    MSG_LINK_ARENA_PROMPT,
    MSG_POD_ADDED,
    MSG_POD_BOARD_COLUMN,
    MSG_TABLE_EMPTY_SEAT,
    MSG_TABLE_SEAT_CONFIRMED,
    MSG_POD_BOARD_THREAD,
    MSG_POD_BOARD_MAYBE,
    MSG_POD_ALREADY_ON,
    MSG_POD_ALREADY_ON_HINT,
    MSG_POD_MAYBE,
    MSG_POD_REMOVED,
)
from bot.database import SessionLocal
from bot.discord_helpers import NBSP, RenderQueue, ordinal, run_detached
from bot.services.lobby_embed import SettingsButton
from sqlalchemy import select

from bot.services.pod_active import ACTIVE_POD_MANAGERS
from bot.models import PodDraftEvent, PodSignal
from bot.services import championship
from bot.services import championship_copy as cc
from bot.services import pod_confirm
from bot.services import pod_format
from bot.services import pod_format_interest as fi
from bot.services import pod_launch
from bot.services.pod_deck_color import format_deck_color_emojis
from bot.services.pod_draft_manager import (
    notify_seeding_change,
)
from bot.services.pod_tournament import (
    build_podium_link_button,
    champion_card_line,
    load_solo_card_drafters,
)
from bot.services.ping_roles import (
    SET_CHAMPION_ROLE_NAME,
    PodCardState,
    announce_pod_grant,
    auto_grant_spec_for_event,
    champion_role_mention,
    build_link_arena_view,
    display_emoji,
    format_join_line,
    grant_pod_roles,
    pod_card_state,
    send_join_confirmation_card,
    spec_named,
)
from bot.services.pod_drafts import (
    arena_handle_for_sync,
    is_championship,
    load_event_description_sync,
    load_event_pairing_mode_sync,
    load_event_seating_mode_sync,
    load_event_set_code_sync,
    record_ondemand_event,
)
from bot.services.pod_registration_embed import build_registered_embed, update_registered_embed
from bot.services.pod_roles import find_role
from bot.services.championship_roster_card import (
    ChampionshipRoster,
    add_championship_roster_fields,
    championship_roster,
    championship_roster_for_event_sync,
)
from bot.services.pod_pairing_select import pairing_label
from bot.services.pod_roster_fields import add_roster_fields
from bot.services import pod_team
from bot.services.pod_team_board import TeamBoardMember, load_team_board_data, team_result_headline
from bot.services.pod_schedule import LATE_POD_ROLE_NAME, SCHEDULE_TZ
from bot.services.pod_slot import pod_display_name, pod_event_date
from bot.services.pod_staging import pod_family_sync, pod_is_numbered, pod_numeral
from bot.services.pod_signals import RSVP_EMOJI, RSVP_MAYBE, RSVP_NO, RSVP_STATES, RSVP_YES
from bot.sets import active_set_code
from bot.tasks.pod_draft_reminder import (
    REMINDER_LEAD_MIN,
    event_rsvps,
    event_rsvp_rosters,
    refresh_or_repost_roster_reminder,
    refresh_roster_reminder_for_event,
)
from bot.tasks.pod_underfill import refresh_underfill_nudge_for_event


log = logging.getLogger(__name__)

EVENT_DURATION_H = 2
POD_CAPACITY = 8

CARD_INTRO = "{emoji} {note}"
CARD_CUBE_LIST = "{emoji} Cube List: {link}"
CARD_RSVP_PROMPT = "Sign up for this draft ✅"
ROOM_NOTICE = "still room at this table 🔥"
TABLE_GATHERING_NOTICE = "{ordinal} table gathering 🔥"
TABLE_GATHERING_YES = 11
NOTICE_GAP = NBSP * 3
CARD_STATUS_DRAFTING = "🎉 **Draft started!**"
CARD_STATUS_PLAYING = "⚔️ **Matches In Progress**"
CARD_STATUS_LOBBY_OPEN = "{emoji} **Lobby is open**"
TIME_LABEL = "Time"
NATIVE_EVENT_SIGNUP = "**Event Details and Signup Link: {jump_url}**"
RSVP_LABELS = {RSVP_YES: "Sign Up", RSVP_MAYBE: "Maybe", RSVP_NO: "Leave"}
RSVP_CONFIRM_COLOR = {
    RSVP_YES: discord.Color.green(),
    RSVP_MAYBE: discord.Color.orange(),
    RSVP_NO: discord.Color.red(),
}
MSG_CARD_INACTIVE = "This RSVP card is no longer active"
MSG_BAD_TIME = "Enter a future time like +1h, 9 PM, 21:00, or tomorrow 8:30pm"
THREAD_NOTE_TITLE = "🕐 Pod Draft Rescheduled by {actor}"
THREAD_NOTE_BODY = "New time: <t:{unix}:F> (<t:{unix}:R>)\n" + MSG_DRAFTMANCER_LINK_LEAD
MSG_CLASHING_MAYBE = "🤷 {player} moved to Maybe here after confirming {other}"

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

    def __init__(self, maybe: bool = True) -> None:
        super().__init__(timeout=None)
        for state in offered_rsvp_states(maybe):
            self.add_item(RsvpButton(state))
        self.add_item(SettingsButton(label=None))


class ScheduledRegisteredView(discord.ui.View):
    """Registered-embed view for anchored-thread pods: the labeled RSVP row (Sign Up / Maybe / Can't)
    above the Settings button, so the thread has live controls where the starter card's own buttons
    render dead. The labels make it clear clicking also signs you up. Its custom_ids are already
    registered through PodRsvpView and the global Settings button, so it needs no registration."""

    def __init__(self, maybe: bool = True) -> None:
        super().__init__(timeout=None)
        for state in offered_rsvp_states(maybe):
            self.add_item(RsvpButton(state, row=0, labeled=True))
        settings = SettingsButton()
        settings.row = 0
        self.add_item(settings)


def offered_rsvp_states(maybe: bool) -> tuple[str, ...]:
    """The answers a pod's card takes. A pod past the first was opened because the night is busy, out of
    players who had already confirmed, so Maybe is not one of them: the question there is which table you
    are on, and an answer that commits to neither leaves a seat nobody can plan around."""
    return RSVP_STATES if maybe else (RSVP_YES, RSVP_NO)


async def _apply_surface_rsvp(
    interaction: discord.Interaction, event_id: str, state: str, confirming: bool = False,
) -> None:
    """Record an RSVP from a non-card surface (championship invite wave, roster reminder) by resolving
    the pod's card from its event id, then routing through the shared card path."""
    await interaction.response.defer(ephemeral=True, thinking=True)
    card = await asyncio.to_thread(pod_launch.scheduled_card_ref_sync, event_id)
    if card is None:
        await interaction.followup.send(MSG_CARD_INACTIVE, ephemeral=True)
        return
    _, _, card_message_id, _ = card
    await apply_card_rsvp(interaction, card_message_id, state, confirming=confirming)


CHAMPIONSHIP_CONFIRM_PREFIX = "podchampconfirm"


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
REMINDER_CONFIRM_STATE = "confirm"


class ReminderRsvpButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=rf"{REMINDER_RSVP_PREFIX}:(?P<state>[a-z]+):(?P<event_id>.+)",
):
    """Sign Up / Leave on the roster reminder. The reminder lives in the pod thread and is not a
    card surface, so the event id rides in the custom_id: one registration dispatches every reminder, it
    keeps working after a restart, and the click records against the pod's card the same as any non-card
    surface. The reminder confirms Yes or No only — Maybe belongs to the earlier gathering window.

    On a confirming pod the Yes seat carries `confirm` as its state instead. It records the same Yes
    and additionally stamps the confirmation, so someone already on the roster gets a press that means
    something. Riding in the custom_id keeps that true across a restart."""

    def __init__(self, state: str, event_id: str, disabled: bool = False) -> None:
        confirming = state == REMINDER_CONFIRM_STATE
        rsvp = RSVP_YES if confirming else state
        super().__init__(discord.ui.Button(
            style=discord.ButtonStyle.success if rsvp == RSVP_YES else discord.ButtonStyle.secondary,
            label=MSG_CONFIRM_BUTTON if confirming else RSVP_LABELS[rsvp], emoji=RSVP_EMOJI[rsvp],
            disabled=disabled, custom_id=f"{REMINDER_RSVP_PREFIX}:{state}:{event_id}",
        ))
        self.state = rsvp
        self.confirming = confirming
        self.event_id = event_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match):
        return cls(match["state"], match["event_id"])

    async def callback(self, interaction: discord.Interaction) -> None:
        await _apply_surface_rsvp(interaction, self.event_id, self.state, confirming=self.confirming)


def build_championship_wave_view(event_id: str) -> discord.ui.View:
    """The invite wave's RSVP row: Confirm / Maybe / Leave, each recording against the pod's card."""
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
    championship_roster: ChampionshipRoster | None = None,
    created_by: str | None = None,
    starts_now: bool = False,
) -> discord.Embed:
    """The RSVP surface. Time and the roster columns are embed fields so sesh's vertical breathing
    room comes for free. `role_time` keys the slot emoji; it defaults to `event_time` and callers
    pass the signal's original slot time after a reschedule. `description` is the optional organizer
    note; it takes the RSVP prompt's line while the pod gathers, and sits quoted under a championship
    announcement, which owns that line itself.
    `set_code` trails the format's keyrune symbol after the name; `team_draft` marks the title once
    the pod locks into teams. `status_line` replaces the intro line and its notice once the
    pod is past gathering, so the card never asks for RSVPs into a draft that already started.
    `announcement` is a fixed body a championship card carries in place of the RSVP intro, since a
    championship seats a fixed eight.
    `locked_roster` replaces the RSVP columns once the draft starts with the actual drafters, which
    fill in records through to the final standings when `draft_complete`. A locked card drops the
    absolute time and calendar link — those help someone deciding to sign up, not a draft in flight —
    and closes on how long ago the pod started, since the pod name already carries the date.
    `team_rosters` maps team key to its members and takes the same in-flight treatment for a team
    draft, rendering the two team columns in place of the RSVP columns. Once the draft finalizes the
    members carry each player's record and deck colors, which the column then shows beside the name.
    `championship_roster` replaces the RSVP columns with the seeded Top 8, Alternates, and declined
    columns, and unlike every other roster surface it survives the locked phases, so the seeding record
    stays on the card once the pod is over.
    `created_by` credits whoever opened an out-of-schedule pod with `/draft`, on the footer of every card
    state. A card the launcher or a job posted has no one to credit and leaves the footer off.
    `starts_now` drops the RSVP prompt and the Time field, for a table staged at its own start time: there
    is nothing to sign up for and nothing to put in a calendar.
    """
    unix = int(event_time.timestamp())
    title = f"### {NBSP * 2}🗓️ {_card_title_name(name, set_code, team_draft)}"
    if team_rosters is not None:
        header = f"{title}\n{status_line}" if status_line else title
        embed = discord.Embed(description=header, color=discord.Color.green())
        _add_team_columns(embed, team_rosters)
        embed.add_field(name=NBSP, value=f"<t:{unix}:R>", inline=False)
        return _with_created_by(embed, created_by)
    if locked_roster is not None:
        header = f"{title}\n{status_line}" if status_line else title
        roster_text = _locked_roster_text(locked_roster, draft_complete)
        embed = discord.Embed(
            description=f"{header}\n\n{roster_text}\n<t:{unix}:R>",
            color=discord.Color.green(),
        )
        if championship_roster is not None:
            add_championship_roster_fields(embed, championship_roster)
        return _with_created_by(embed, created_by)
    calendar_url = google_calendar_url(name, event_time)
    if starts_now:
        middle = None
    elif status_line is not None:
        middle = status_line
    elif announcement is not None:
        middle = f"{announcement}\n> {description}" if description else announcement
    else:
        intro = _intro_line(role_time or event_time, description)
        middle = f"{intro}{_multipod_suffix(rosters)}{_cube_list_line(set_code)}"
    header = title if middle is None else f"{title}\n{middle}"
    embed = discord.Embed(description=header, color=discord.Color.green())
    if not starts_now:
        time_value = f"<t:{unix}:F> (<t:{unix}:R>) [[+]](<{calendar_url}>)"
        embed.add_field(name=TIME_LABEL, value=time_value, inline=False)
    if championship_roster is not None:
        add_championship_roster_fields(embed, championship_roster)
    else:
        add_roster_fields(
            embed, rosters, roster_interests, championship=announcement is not None,
            playing_only=starts_now,
        )
    return _with_created_by(embed, created_by)


def _with_created_by(embed: discord.Embed, created_by: str | None) -> discord.Embed:
    """Footers carry no markdown and no mention pills, so the credit is a plain display name."""
    if created_by:
        embed.set_footer(text=MSG_CARD_CREATED_BY.format(name=created_by))
    return embed


def _card_title_name(name: str, set_code: str | None, team_draft: bool) -> str:
    """The card's headline: the pod name, then the format symbol, which doubles as the separator in
    front of the Team Draft marker. A set with no uploaded emoji falls back to a dash"""
    symbol = emojis.get(set_code.lower()) if set_code else ""
    parts = [name]
    if symbol:
        parts.append(symbol)
    elif team_draft:
        parts.append("-")
    if team_draft:
        parts.append(pairing_label("team"))
    return NBSP.join(parts)


def _intro_line(role_time: datetime, description: str | None = None) -> str:
    """The line under the pod name: the organizer's note when there is one, else the RSVP prompt. The
    slot emoji leads either way, so the card still reads as Early / Late / Weekend at a glance."""
    spec = auto_grant_spec_for_event(role_time) or spec_named(LATE_POD_ROLE_NAME)
    return CARD_INTRO.format(emoji=display_emoji(spec) or "", note=description or CARD_RSVP_PROMPT)


def _cube_list_line(set_code: str | None) -> str:
    """Own line below the intro, empty for a set pod"""
    link = pod_format.cube_list_link(set_code)
    if link is None:
        return ""
    return f"\n{CARD_CUBE_LIST.format(emoji=fi.format_emoji(set_code), link=link)}"


def _multipod_suffix(rosters: dict[str, list[str]]) -> str:
    """Tail on the intro line, empty below one table's worth of signups"""
    signed_up = len(rosters.get(pod_confirm.CONFIRMED) or []) + len(rosters.get(RSVP_YES) or [])
    if signed_up >= TABLE_GATHERING_YES:
        notice = TABLE_GATHERING_NOTICE.format(ordinal=_gathering_ordinal(signed_up))
    elif signed_up >= POD_CAPACITY:
        notice = ROOM_NOTICE
    else:
        return ""
    return f"{NOTICE_GAP}{notice}"


def _gathering_ordinal(signed_up: int) -> str:
    """Which table the next signups are filling: the one past the plan, or the last one when it waits"""
    plan = pod_confirm.plan_tables(signed_up)
    gathering = len(plan.tables) + 1 if plan.waiting else len(plan.tables)
    return ordinal(max(gathering, 2))


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
    championship: bool = False, championship_roster: ChampionshipRoster | None = None,
) -> None:
    """Swap the roster columns on a fetched surface while keeping its Time field untouched, so a
    click never needs a DB round trip for the event row. The intro's notice tail follows the Yes count on
    the same click; a `status_line` replaces the whole line once the pod is past gathering. A
    `championship` card keeps its fixed announcement body across refreshes and takes no notice."""
    keep_only_time_field(embed)
    if championship_roster is not None:
        add_championship_roster_fields(embed, championship_roster)
    else:
        add_roster_fields(embed, rosters, roster_interests, championship=championship)
    if status_line is not None:
        embed.description = _swap_status_line(embed.description or "", status_line)
    elif not championship:
        embed.description = _renoticed(embed.description or "", rosters)


async def resolve_championship_card_roster(
    event_id: str | None, rosters: dict[str, list[str]],
) -> ChampionshipRoster | None:
    """The seeded columns for a Set Championship card, off the main thread. None for any other pod."""
    return await asyncio.to_thread(championship_roster_for_event_sync, event_id, rosters)


async def move_pod_to_its_own_card(
    bot: commands.Bot, event_id: str, name: str, event_time: datetime, set_code: str,
) -> "discord.Thread | None":
    """Give a pod that already exists a fresh card and a thread of its own, and hand back the thread.

    The first table needs both when its signup splits: the card it was created from becomes the board of
    every table, and the thread it gathered in holds players who now sit elsewhere. Its event and signal
    are untouched apart from where they point, so its roster, its timed jobs and its Draftmancer session
    all carry over.

    The signal's message id is what every RSVP press resolves through, so moving it is what makes the new
    card the live one and leaves the old message inert."""
    card = await asyncio.to_thread(pod_launch.scheduled_card_ref_sync, event_id)
    if card is None:
        return None
    channel = await fetch_channel(bot, card[1])
    if not isinstance(channel, discord.TextChannel):
        return None
    rosters, roster_interests = await event_rsvp_rosters(event_id)
    starts_now = pod_is_numbered(name)
    try:
        message = await channel.send(
            embed=build_rsvp_embed(
                name, event_time, rosters, set_code=set_code, roster_interests=roster_interests,
                starts_now=starts_now,
            ),
            view=discord.utils.MISSING if starts_now else PodRsvpView(),
        )
        thread = await message.create_thread(name=name[:100])
    except discord.HTTPException:
        log.warning(f"could not move pod {event_id} onto a card of its own", exc_info=True)
        return None
    await asyncio.to_thread(
        pod_launch.move_scheduled_card_sync, event_id, str(message.id), str(thread.id),
    )
    return thread


async def render_pod_overview(bot: commands.Bot, event_id: str, message_id: str) -> None:
    """Turn the card a split signup was created from into the board of the tables it became.

    It is the one card everybody already has in front of them and it no longer belongs to any single
    table, so it stops carrying a roster and starts carrying all of them. Its RSVP row goes with them:
    the pods it points at own the signups now, and a press here would land on whichever table happened to
    keep the signal."""
    family = await asyncio.to_thread(pod_family_sync, event_id)
    if len(family) < 2:
        return
    card = await asyncio.to_thread(pod_launch.scheduled_card_ref_sync, event_id)
    channel = await fetch_channel(bot, card[1]) if card else None
    if channel is None:
        return
    try:
        message = await channel.fetch_message(int(message_id))
    except discord.HTTPException:
        return
    if not _is_card_surface(message):
        return
    embed = message.embeds[0]
    keep_only_time_field(embed)
    embed.description = _swap_status_line(embed.description or "", "")
    guild_id = getattr(channel, "guild", None) and channel.guild.id
    for pod in family:
        embed.add_field(
            name=MSG_POD_BOARD_COLUMN.format(index=pod_numeral(pod.index), size=pod.capacity),
            value=_pod_board_value(pod, guild_id), inline=True,
        )
    maybes = [name for pod in family for name in pod.maybe_names]
    if maybes:
        embed.add_field(name=MSG_POD_BOARD_MAYBE.format(count=len(maybes)),
                        value="\n".join(f"> {name}" for name in maybes), inline=True)
    try:
        await message.edit(embed=embed, view=None)
    except discord.HTTPException:
        log.warning(f"could not render the overview card {message_id}", exc_info=True)


def _pod_board_value(pod, guild_id: int | None = None) -> str:
    """One table's column on the board: the players on it, the seats it is still short of, and a link into
    its thread. Names rather than a count, since the board is the one card that shows the tables beside
    each other and the question it answers is which one somebody is on."""
    lines = [MSG_TABLE_SEAT_CONFIRMED.format(name=name) for name in pod.member_names]
    lines += [MSG_TABLE_EMPTY_SEAT] * max(0, pod.capacity - pod.seated)
    if guild_id and pod.thread_id:
        url = f"https://discord.com/channels/{guild_id}/{pod.thread_id}"
        link = MSG_POD_BOARD_THREAD.format(index=pod.index, url=url)
        manat = emojis.get("manat")
        lines.append(f"{link} {manat}" if manat else link)
    return "\n".join(lines)


def keep_only_time_field(embed: discord.Embed) -> None:
    """Drop every field but the Time one, so a caller can render fresh roster columns onto a card it
    already has in hand."""
    time_field = None
    for field in embed.fields:
        if field.name == TIME_LABEL:
            time_field = field
            break
    embed.clear_fields()
    if time_field is not None:
        embed.add_field(name=TIME_LABEL, value=time_field.value, inline=False)


def _renoticed(description: str, rosters: dict[str, list[str]]) -> str:
    """Rewrite the intro line to carry the notice this roster earns, peeling every notice already on it"""
    lines = description.split("\n")
    if len(lines) < 2:
        return description
    lines[1] = _unnoticed(lines[1]) + _multipod_suffix(rosters)
    return "\n".join(lines)


def _unnoticed(intro: str) -> str:
    return intro.split(NOTICE_GAP)[0]


def _swap_status_line(description: str, status_line: str) -> str:
    """Rebuild a fetched card description around the lifecycle status: the title line, the status,
    then any organizer note, dropping the RSVP intro with its notice and any earlier status."""
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
    championship flag keeps a roster refresh from growing a notice on the frozen
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
    preseed_yes: list[tuple[str, str]] | None = None,
    preseed_confirmed: list[tuple[str, str]] | None = None,
    preseed_maybe: list[tuple[str, str]] | None = None, ping_role: bool = True,
    notify_role_name: str | None = None, description: str | None = None,
    pairing_mode: str | None = None, seating_mode: str | None = None, pick_timer: int | None = None,
    content_override: str | None = None, card_body: str | None = None, native_body: str | None = None,
    format_locked: bool = True, opener: discord.abc.User | None = None,
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
    pulled into the thread; No always starts empty.

    `preseed_confirmed` is the same for players who already confirmed they are coming, the seated roster
    a split hands to a table. Confirmation has to survive the move: reseeded as a plain Yes they would read
    as an answer this table is still waiting for.

    `preseed_maybe` is the same for the maybes a split hands to its last table. They join the thread too,
    since the seat they might take is here, and being dealt to a table does not turn Maybe into a Yes.

    `content_override` replaces the card's content ping outright — a fired launcher slot's creation
    announcement, carrying its own role mention. `card_body` is a fixed announcement rendered inside
    the embed in place of the RSVP intro, for a championship card that never fires a second table, and
    `native_body` is its counterpart on the native event, above the signup link.

    `opener` is the player who ran `/draft`. It lands on the signal and on the card footer, so an
    out-of-schedule pod shows who organized it. A card a job or the launcher posts leaves it None.

    A numbered name means a table staged at its own start time, whose card carries the roster with no
    RSVP prompt, no Time and no buttons, since nobody is being asked to sign up. It opens no native
    scheduled event either: the signup it split from already holds the one the server shows.

    Such a table also posts no registered embed and pulls nobody into its thread. Both exist to gather a
    roster over the hour before a pod, and this one is drafting in seconds: its lobby post mentions the
    players it seated, which is what joins them to the thread, silently and in one message instead of one
    Discord call and one system line per player."""
    preseed_yes = preseed_yes or []
    preseed_confirmed = preseed_confirmed or []
    preseed_maybe = preseed_maybe or []
    rosters = {state: [] for state in RSVP_STATES}
    rosters[pod_confirm.CONFIRMED] = [display for _, display in preseed_confirmed]
    rosters[RSVP_YES] = [display for _, display in preseed_yes]
    rosters[RSVP_MAYBE] = [display for _, display in preseed_maybe]
    guild = channel.guild
    name = await pod_launch.dedupe_pod_name(channel, name)
    starts_now = pod_is_numbered(name)
    championship_card_roster = championship_roster((), (), ()) if is_championship(name) else None
    content = content_override if content_override is not None else _card_ping(
        guild, event_time, ping_role, notify_role_name)
    try:
        message = await channel.send(
            content=content,
            embed=build_rsvp_embed(
                name, event_time, rosters, description=description, set_code=set_code,
                team_draft=pairing_mode == "team", announcement=card_body,
                championship_roster=championship_card_roster,
                created_by=opener.display_name if opener is not None else None,
                starts_now=starts_now,
            ),
            view=discord.utils.MISSING if starts_now else PodRsvpView(),
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
        opened_by=str(opener.id) if opener is not None else None,
    )
    if preseed_yes:
        await asyncio.to_thread(pod_launch.seed_members_sync, signal_id, preseed_yes, RSVP_YES)
    if preseed_confirmed:
        await asyncio.to_thread(
            pod_launch.seed_members_sync, signal_id, preseed_confirmed, RSVP_YES, True)
    if preseed_maybe:
        await asyncio.to_thread(pod_launch.seed_members_sync, signal_id, preseed_maybe, RSVP_MAYBE)
    native_event_id = None
    if not starts_now:
        native_event_id = await _create_native_event(
            channel, name, event_time, message.jump_url, native_body)
    event_id, created_at, pairing_mode, seating_mode = await asyncio.to_thread(
        _record_scheduled_event, set_code, event_time, name, str(thread.id), native_event_id,
        pairing_mode, seating_mode, description,
    )
    await asyncio.to_thread(pod_launch.link_event_sync, signal_id, event_id)

    try:
        if not starts_now:
            registered = await thread.send(
                embed=build_registered_embed(
                    set_code.upper(), pairing_mode, seating_mode,
                    championship=is_championship(name), rsvp_hint=True,
                    channel_post_url=message.jump_url, guild=guild, event_time=event_time,
                ),
                view=ScheduledRegisteredView(),
            )
            await asyncio.to_thread(pod_launch.set_thread_message_sync, signal_id, str(registered.id))
        if description:
            await thread.send(description)
    except discord.HTTPException:
        log.warning(f"could not post the registered embed in thread {thread.id}", exc_info=True)

    if not starts_now:
        await add_members_to_thread(thread, preseed_confirmed + preseed_yes + preseed_maybe)
    pod_launch.arm_scheduled_pod_jobs(bot, event_id, event_time, created_at)
    log.info(f"posted scheduled pod card for {name} as message {message.id} (event {event_id})")
    await _refresh_launcher(bot, event_time)
    return event_id


async def post_pod_card(
    channel: discord.abc.Messageable, *, name: str, event_time: datetime, set_code: str,
    roster: list[str] | None = None,
) -> discord.Message | None:
    """The card for a pod no scheduled signal created: a fired queue, a table. No RSVP row, since the
    roster settled on the surface that fired the pod. The caller anchors the pod thread on the returned
    message and records it with `record_pod_card_sync`, which is what later re-renders it to standings."""
    players = [DraftedPlayer(display_name=display) for display in roster or []]
    try:
        return await channel.send(embed=build_rsvp_embed(
            name, event_time, {}, set_code=set_code, status_line=_lobby_open_status_line(),
            locked_roster=players,
        ))
    except discord.HTTPException:
        log.warning(f"could not post the pod card for {name}", exc_info=True)
        return None


def _lobby_open_status_line() -> str:
    return CARD_STATUS_LOBBY_OPEN.format(emoji=emojis.get("draftmancer"))


async def add_members_to_thread(thread: discord.Thread, members: list[tuple[str, str]]) -> None:
    """Pull a roster into a pod thread so coordination reaches them from the start. Adding is silent, so
    it costs a member who is busy elsewhere nothing."""
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
    *, refresh_launcher: bool = True, confirming: bool = False,
) -> None:
    """Record an RSVP on the card behind `surface_message_id` and run every follow-on: the grant, the
    confirmation, thread membership, surface re-renders, the native-event tally, and the nudge and
    launcher refreshes. The clicked surface may be the card, the thread's registered embed, or a
    launcher slot that resolves to the card, so `surface_message_id` is the card the write targets while
    `interaction.message` is whatever was clicked. A launcher-slot caller passes `refresh_launcher=False`
    and re-renders the clicked launcher itself, so the board updates in whatever channel it lives in.

    Every answer names the pod it landed on, since a click can come from the card, its thread, the roster
    reminder, or a launcher button, and only the pod's own name reads the same from all four.

    Only the roster write and the presser's own answer run on the click. Everything the RSVP moves besides
    that settles after, so the press never waits on a card render, a role grant, or a launcher repaint.

    The acknowledgement is a thinking one, which puts the pending answer on screen the instant the button
    is pressed. A silent acknowledgement holds the click open just as safely but shows the presser nothing
    until the confirmation lands, so a slow answer reads as a button that did nothing.

    The card state the answer renders with does not depend on the write, so it is read alongside it and not
    after. A press used to wait on three database round trips in a row before anything reached the screen."""
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True, thinking=True)
    result, card_state = await asyncio.gather(
        asyncio.to_thread(
            pod_launch.set_rsvp_sync,
            surface_message_id, str(interaction.user.id), interaction.user.display_name, state,
            confirming,
        ),
        pod_card_state(str(interaction.user.id)),
    )
    if result is None or result.closed:
        await interaction.followup.send(MSG_CARD_INACTIVE, ephemeral=True)
        return

    await _answer_presser(interaction, result, card_state, confirming=confirming)
    run_detached(
        _settle_card_rsvp(interaction, result, refresh_launcher=refresh_launcher),
        f"the RSVP on card {surface_message_id}",
    )


async def _answer_presser(
    interaction: discord.Interaction, result: pod_launch.RsvpResult, card_state: PodCardState,
    confirming: bool = False,
) -> None:
    """The presser's private acknowledgement, sent off the roster write alone so it lands before any
    surface re-renders.

    A confirmation is never the already-signed-up answer. Confirming is the second press by design, and
    telling someone their press did nothing is the fastest way to stop them pressing it."""
    if confirming and result.rsvp == RSVP_YES:
        answer, view = await _confirm_answer(interaction, result)
        await interaction.followup.send(answer, view=view, ephemeral=True)
        return
    if result.rsvp == RSVP_YES and not result.joined:
        name, _event_time = _pod_identity(result)
        await interaction.followup.send(embed=pod_already_on_embed(name), ephemeral=True)
    elif result.rsvp in (RSVP_YES, RSVP_MAYBE):
        await send_join_confirmation_card(
            interaction, lead=_confirmation_lead_text(result),
            accent=RSVP_CONFIRM_COLOR[result.rsvp], state=card_state,
        )
    else:
        await interaction.followup.send(embed=_decline_embed(result), ephemeral=True)


async def _settle_card_rsvp(
    interaction: discord.Interaction, result: pod_launch.RsvpResult, *, refresh_launcher: bool,
) -> None:
    """Everything an RSVP moves once the presser has an answer: the clicked card, the pod roles and the
    first-pod welcome, thread membership, then everything any roster change moves, and for a confirmation
    the pods it clashes with.

    The clicked card is repainted first because it is the one on the presser's screen. A press from the
    thread's own surfaces renders nothing here, since those carry no roster columns, and the thread's
    roster card is the first thing `settle_roster_change` touches."""
    (status_line, championship), champ_roster = await asyncio.gather(
        resolve_card_render_state(result.state.event_id),
        resolve_championship_card_roster(result.state.event_id, result.rosters),
    )
    if _is_card_surface(interaction.message):
        embed = interaction.message.embeds[0]
        refresh_roster_fields(
            embed, result.rosters, status_line, result.roster_interests, championship=championship,
            championship_roster=champ_roster,
        )
        try:
            await interaction.message.edit(embed=embed)
        except discord.HTTPException:
            log.warning(f"could not render the clicked card {interaction.message.id}", exc_info=True)

    first_pod = False
    if result.joined and isinstance(interaction.user, discord.Member):
        slot_role_name = None if championship else _auto_grant_role_name(result.state.slot_time)
        first_pod = await grant_pod_roles(interaction.user, slot_role_name)
    await announce_pod_grant(interaction, first_pod=first_pod)

    if result.state.event_id is None:
        return
    if result.rsvp in (RSVP_YES, RSVP_MAYBE):
        await _add_member_to_thread(interaction.client, result.state.event_id, interaction.user)
    await settle_roster_change(
        interaction.client, result, clicked_message_id=str(interaction.message.id),
        refresh_launcher=refresh_launcher,
    )
    if championship and result.yes_changed:
        notify_seeding_change(interaction.client, result.state.event_id)
    if result.confirmed:
        pod_name, _event_time = _pod_identity(result)
        run_detached(
            demote_clashing_signups(
                interaction.client, interaction.user, result.state.event_id, pod_name,
            ),
            f"the pods clashing with {result.state.event_id}",
        )


SHARED_RENDER_DEBOUNCE_S = 1.5

_roster_renders = RenderQueue(SHARED_RENDER_DEBOUNCE_S)
_card_renders = RenderQueue(SHARED_RENDER_DEBOUNCE_S)
_launcher_renders = RenderQueue(SHARED_RENDER_DEBOUNCE_S)


async def settle_roster_change(
    bot: commands.Bot, result: pod_launch.RsvpResult, *, clicked_message_id: str = "",
    refresh_launcher: bool = True,
) -> "asyncio.Task | None":
    """Everything a roster change moves besides whoever pressed.

    Every shared surface is queued rather than rendered here. A pod confirming at its ten minute mark
    turns its whole roster over in seconds, and one repaint per press is a queue of edits to the three
    messages everybody is looking at. The presser already has their own answer, so nothing here is on
    the click.

    The task is returned for a caller that has to read the settled state. Shared by the RSVP click and by
    `!test crowd`, so a simulated signup lands exactly where a real one does."""
    event_id = result.state.event_id
    if event_id is None:
        return None
    _roster_renders.request(event_id, lambda: refresh_or_repost_roster_reminder(event_id))
    return run_detached(
        _settle_beyond_the_thread(
            bot, result, event_id, clicked_message_id=clicked_message_id,
            refresh_launcher=refresh_launcher,
        ),
        f"the roster change on pod {event_id}",
    )


async def _settle_beyond_the_thread(
    bot: commands.Bot, result: pod_launch.RsvpResult, event_id: str, *,
    clicked_message_id: str, refresh_launcher: bool,
) -> None:
    """The rest of what a roster change moves: the channel card, the standing nudges, the lobby's
    capacity, the next pod, and the launcher board. The board is repainted after staging, since staging
    may have just created the pod it has to show."""
    _card_renders.request(event_id, lambda: _render_channel_card_fresh(bot, event_id))
    yes = result.rosters.get(RSVP_YES) or []
    maybe = result.rosters.get(RSVP_MAYBE) or []
    await refresh_underfill_nudge_for_event(bot, event_id, len(yes), len(maybe))
    slot_time = result.state.slot_time
    if result.yes_changed and refresh_launcher and slot_time is not None:
        day = slot_time.astimezone(SCHEDULE_TZ).date()
        _launcher_renders.request(str(day), lambda: _refresh_launcher(bot, slot_time))


async def set_card_rsvp(
    bot: commands.Bot, user: discord.abc.User, card_message_id: str, state: str,
) -> str | None:
    """Record an RSVP on a pod's card for a press that landed on something else, then re-render everything
    that carries the roster. The launcher's Leave button drops one player from every pod at once, and a
    confirmation moves them to Maybe on every pod it clashes with, so the write cannot own the interaction
    the way `apply_card_rsvp` does and the caller answers for all of them.
    Returns the pod's name, or None when the card is gone or closed."""
    result = await asyncio.to_thread(
        pod_launch.set_rsvp_sync, card_message_id, str(user.id), user.display_name, state,
    )
    if result is None or result.closed:
        return None
    name, _event_time = _pod_identity(result)
    event_id = result.state.event_id
    if event_id is None:
        return name
    await _render_channel_card(bot, event_id, result.rosters, result.roster_interests)
    yes = result.rosters.get(RSVP_YES) or []
    maybe = result.rosters.get(RSVP_MAYBE) or []
    await refresh_underfill_nudge_for_event(bot, event_id, len(yes), len(maybe))
    await refresh_or_repost_roster_reminder(event_id)
    if result.yes_changed:
        _status_line, championship = await resolve_card_render_state(event_id)
        if championship:
            notify_seeding_change(bot, event_id)
    return name


async def demote_clashing_signups(
    bot: commands.Bot, user: discord.abc.User, confirmed_event_id: str, confirmed_name: str,
) -> None:
    """Move a player who has just confirmed to Maybe on every pod that clashes with the one they confirmed,
    and say so in each clashing pod's thread.

    Nothing about a confirmation waits on this. It answers a question about the other pods, which the player
    who pressed Confirm is not asking, and a night with nothing clashing costs one read to find that out.

    Maybe rather than No: the player has said which pod they are playing, not that they are unavailable, and
    a clashing pod that ends up not firing should still find them on its roster."""
    clashing = await asyncio.to_thread(
        pod_confirm.clashing_signups_sync, confirmed_event_id, str(user.id),
    )
    if not clashing:
        return
    log.info(f"{user} confirmed {confirmed_name}, demoting {len(clashing)} clashing signups to Maybe")
    confirmed_link = await _pod_thread_link(bot, confirmed_event_id, confirmed_name)
    for pod in clashing:
        await set_card_rsvp(bot, user, pod.card_message_id, RSVP_MAYBE)
        await _announce_clashing_maybe(bot, pod, user, confirmed_link)
        await _refresh_launcher_for_event(bot, pod.event_id)


async def _announce_clashing_maybe(
    bot: commands.Bot, pod: pod_confirm.ClashingSignup, user: discord.abc.User, confirmed_link: str,
) -> None:
    """Tell the clashing pod's thread who moved and why. The roster columns show the move on their own, but
    only the thread can say it was a clash and not a change of mind, which is what stops the pod chasing a
    player who is already sitting at another table.

    By display name, not by mention: the player made this happen and knows it, and the people who need it
    are the ones planning the table around them."""
    thread = await _resolve_event_thread(bot, pod.event_id)
    if thread is None:
        return
    try:
        await thread.send(MSG_CLASHING_MAYBE.format(player=user.display_name, other=confirmed_link))
    except discord.HTTPException:
        log.warning(f"could not post the clash notice in thread {thread.id}", exc_info=True)


async def _pod_thread_link(bot: commands.Bot, event_id: str, name: str) -> str:
    """A pod named as a link to its own thread, so the clash notice puts the pod that took the player one
    click away. Falls back to the bare name for a pod whose thread the bot cannot reach."""
    thread = await _resolve_event_thread(bot, event_id)
    if thread is None:
        return f"**{name}**"
    return f"[**{name}**]({thread.jump_url})"


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


def _auto_grant_role_name(slot_time: datetime | None) -> str | None:
    """The slot role an RSVP earns, keyed on the signal's slot_time so a postponed pod still grants the
    slot it was gathered in."""
    if slot_time is None:
        return None
    spec = auto_grant_spec_for_event(slot_time)
    return spec.name if spec is not None else None


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


def pod_already_on_embed(pod_name: str) -> discord.Embed:
    """The answer to a sign up by someone the pod already holds. A press that changed nothing gets the bare
    note, not the full card: the presser is asking whether the first press landed, and the hint names the one
    press that would change it. ❌ is the launcher's Leave and the card's Can't, so one line serves both."""
    return discord.Embed(
        title=MSG_POD_ALREADY_ON.format(name=pod_name), description=MSG_POD_ALREADY_ON_HINT,
        color=discord.Color.green(),
    )


def _decline_embed(result: pod_launch.RsvpResult) -> discord.Embed:
    """The one-line acknowledgement for No and for a cleared RSVP. Both read as a removal to the player,
    including a championship's No, which the roster keeps as a tracked state. Yes and Maybe answer with
    the full confirmation card through `send_join_confirmation_card`."""
    name, _event_time = _pod_identity(result)
    return pod_removed_embed(name)


def _confirmation_lead_text(result: pod_launch.RsvpResult) -> str:
    """The Yes/Maybe acknowledgement as card text: the pod that was joined over its start time."""
    name, event_time = _pod_identity(result)
    lead = f"### {_rsvp_headline(result.rsvp, name)}"
    if event_time is None:
        return lead
    return f"{lead}\n{MSG_DRAFT_STARTS.format(unix=int(event_time.timestamp()))}"


def _rsvp_headline(rsvp: str, pod_name: str) -> str:
    """Yes or Maybe only. A No and a cleared RSVP are acknowledged by `_decline_embed`."""
    return (MSG_POD_ADDED if rsvp == RSVP_YES else MSG_POD_MAYBE).format(name=pod_name)


async def _confirm_answer(
    interaction: discord.Interaction, result: pod_launch.RsvpResult,
) -> tuple[str, "discord.ui.View"]:
    """The presser's answer to Confirm Seat, which is the one press worth asking anything of.

    Somebody who has just raised their hand an hour before the draft has nothing else competing for their
    attention, and it is the last moment where a missing Arena handle can still be fixed calmly. So an
    unlinked confirmation is where the ask goes: linking there hands the link straight back through
    `active_lobby_link_for`, and it is what turns their name on the lobby card from 🆕 into a live link.
    Left to the lobby opening, the same ask arrives ten minutes out, in the middle of everyone arriving.

    A linked confirmation gets the link itself, but only once the bot holds the room. The claim runs an hour
    out for exactly this, and a session it does not own can still be abandoned and reseated, which would
    invalidate every address already handed out."""
    name, _event_time = _pod_identity(result)
    confirmed = MSG_CONFIRM_DONE.format(name=name)
    handle = await asyncio.to_thread(arena_handle_for_sync, str(interaction.user.id))
    if handle is None:
        return f"{confirmed}\n{MSG_LINK_ARENA_PROMPT}", build_link_arena_view()
    session_id = _owned_lobby_session(result.state.event_id)
    if session_id is None:
        return confirmed, discord.utils.MISSING
    return f"{confirmed}\n{format_join_line(session_id, handle)}", discord.utils.MISSING


def _owned_lobby_session(event_id: str | None) -> str | None:
    """The Draftmancer session of a pod whose room the bot is already holding, else None."""
    if event_id is None:
        return None
    manager = ACTIVE_POD_MANAGERS.get(event_id)
    if manager is None or not manager.is_owner:
        return None
    return manager.session_id


def _pod_identity(result: pod_launch.RsvpResult) -> tuple[str, datetime | None]:
    """(pod name, start time) for an acknowledgement, carried out of the roster write itself. A signal with
    no pod on it yet is named for the format and slot it will carry, which is the name the pod takes when
    it fires."""
    if result.event_name is not None:
        return result.event_name, result.event_time
    return pod_display_name(
        result.state.set_code or active_set_code(), result.state.slot_time or datetime.now(timezone.utc),
    ), result.state.slot_time


async def _add_member_to_thread(bot: commands.Bot, event_id: str, user: discord.abc.User) -> None:
    """Pull a member into the pod's thread so coordination reaches them.

    Thread membership only ever grows. Leaving a pod takes the seat back, not the conversation: somebody
    who dropped out still wants to read whether the pod fired, and may well come back to it. Ejecting them
    is also the one thing here a player cannot undo for themselves, since a thread they were removed from
    is harder to find again than one they chose to leave."""
    thread = await _resolve_event_thread(bot, event_id)
    if thread is None:
        return
    try:
        await thread.add_user(user)
    except discord.HTTPException:
        log.warning(f"could not add {user} to thread {thread.id}", exc_info=True)


async def _resolve_event_thread(bot: commands.Bot, event_id: str | None) -> discord.Thread | None:
    if event_id is None:
        return None
    thread_id = await asyncio.to_thread(pod_launch.event_thread_id_sync, event_id)
    if thread_id is None:
        return None
    thread = await fetch_channel(bot, thread_id)
    return thread if isinstance(thread, discord.Thread) else None


async def _render_channel_card_fresh(bot: commands.Bot, event_id: str) -> None:
    """The channel card off the roster it holds now. The queued render runs after the press that asked
    for it, so it reads the roster rather than carrying that press's copy of it."""
    rosters, roster_interests = await event_rsvp_rosters(event_id)
    await _render_channel_card(bot, event_id, rosters, roster_interests)


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
    champ_roster = await resolve_championship_card_roster(event_id, rosters)
    refresh_roster_fields(
        embed, rosters, status_line, roster_interests, championship=championship,
        championship_roster=champ_roster,
    )
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


def native_event_description(jump_url: str, body: str | None = None) -> str:
    """The native event's body: an optional announcement over the card's link. Static by design. Discord
    exposes no interest API for a guild scheduled event, so a live roster there could only be a tally the
    bot re-renders, and editing a scheduled event is one of the slowest and most rate-limited calls
    Discord has. The card holds the roster; the event holds the banner and a way back to the card."""
    sections = [NATIVE_EVENT_SIGNUP.format(jump_url=jump_url)]
    if body:
        sections.insert(0, body)
    return "\n\n".join(sections)


def native_event_window(event_time: datetime) -> tuple[datetime, datetime]:
    """The native event runs from the pod's confirmation ping to the end of play, so the server's
    Happening Now banner turns on when players have to be in the thread instead of when the draft is
    already starting. Never opens in the past, which Discord rejects."""
    earliest = datetime.now(timezone.utc) + timedelta(minutes=1)
    start = event_time - timedelta(minutes=REMINDER_LEAD_MIN)
    return max(start, earliest), event_time + timedelta(hours=EVENT_DURATION_H)


async def _create_native_event(
    channel: discord.TextChannel, name: str, event_time: datetime, jump_url: str, body: str | None,
) -> str | None:
    if event_time <= datetime.now(timezone.utc):
        return None
    start_time, end_time = native_event_window(event_time)
    try:
        native = await channel.guild.create_scheduled_event(
            name=name,
            start_time=start_time,
            end_time=end_time,
            entity_type=discord.EntityType.external,
            privacy_level=discord.PrivacyLevel.guild_only,
            location=jump_url,
            description=native_event_description(jump_url, body),
        )
    except discord.HTTPException:
        log.warning("could not create the native scheduled event", exc_info=True)
        return None
    return str(native.id)


async def purge_native_events(guild: discord.Guild, bot_user_id: int) -> int:
    """Delete every scheduled event this bot created in the guild, clearing the Events calendar. Backs
    `!test reset`; other creators' events (sesh, humans) are left alone."""
    try:
        events = await guild.fetch_scheduled_events()
    except discord.HTTPException:
        log.warning("could not fetch scheduled events for purge", exc_info=True)
        return 0
    async def delete(event: discord.ScheduledEvent) -> bool:
        try:
            await event.delete()
        except discord.HTTPException:
            log.warning(f"could not delete scheduled event {event.id}", exc_info=True)
            return False
        return True

    ours = [event for event in events if event.creator_id == bot_user_id]
    return sum(await asyncio.gather(*(delete(event) for event in ours)))


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
        _retime_registered_embed(bot, event_id, thread_id, name, new_time),
        _refresh_launcher_for_event(bot, event_id),
    )
    audit.event(
        "pod_postpone", user_id=actor_id, event_id=event_id,
        old_time=event_time.isoformat(), new_time=new_time.isoformat(),
    )
    return None


async def _retime_registered_embed(
    bot: commands.Bot, event_id: str, thread_id: str | None, name: str, event_time: datetime,
) -> None:
    """Re-render the thread's registration embed so the start time it repeats follows the reschedule."""
    if thread_id is None:
        return
    thread = await fetch_channel(bot, thread_id)
    if thread is None:
        return
    set_code = await asyncio.to_thread(load_event_set_code_sync, event_id)
    pairing_mode = await asyncio.to_thread(load_event_pairing_mode_sync, event_id)
    seating_mode = await asyncio.to_thread(load_event_seating_mode_sync, event_id)
    await update_registered_embed(
        thread, client_user=bot.user, set_code=(set_code or active_set_code()).upper(),
        pairing_mode=pairing_mode, seating_mode=seating_mode,
        championship=is_championship(name), event_time=event_time,
    )


async def _edit_scheduled_card(bot: commands.Bot, event_id: str, name: str, event_time: datetime) -> None:
    """Re-render the channel card from scratch — name, set symbol, time, description, rosters. It is
    the thread starter, so the thread view moves with it. A pod with no scheduled card renders on its
    own card, which never falls back to the RSVP prompt since nothing on it takes a click. Shared by
    reschedule (new time) and a format change (new name + symbol)."""
    ref = await asyncio.to_thread(pod_launch.pod_card_ref_sync, event_id)
    if ref is None:
        return
    starts_now = pod_is_numbered(name)
    channel_id, message_id, slot_time = ref
    roster_interests = await asyncio.to_thread(pod_launch.rsvp_rosters_with_interest_sync, message_id)
    own_card = roster_interests is None
    rosters: dict[str, list[str]] = {}
    if not own_card:
        rosters = {state: [name for name, _ in members] for state, members in roster_interests.items()}
        if await asyncio.to_thread(pod_launch.format_locked_for_event_sync, event_id):
            roster_interests = None
    channel = await fetch_channel(bot, channel_id)
    if channel is None:
        return
    description = await asyncio.to_thread(load_event_description_sync, event_id)
    set_code = await asyncio.to_thread(load_event_set_code_sync, event_id)
    pairing_mode = await asyncio.to_thread(load_event_pairing_mode_sync, event_id)
    status_line = await resolve_card_status_line(event_id)
    if status_line is None and own_card:
        status_line = _lobby_open_status_line()
    team_rosters = await _team_card_rosters(event_id, pairing_mode, status_line)
    locked_roster, draft_complete = await _solo_card_roster(event_id, pairing_mode, status_line)
    if own_card and locked_roster is None and team_rosters is None:
        locked_roster = await asyncio.to_thread(_own_card_lobby_roster_sync, event_id)
    guild = getattr(channel, "guild", None)
    opener_id = await asyncio.to_thread(pod_launch.scheduled_card_opener_sync, event_id)
    try:
        message = await channel.fetch_message(int(message_id))
        await message.edit(embed=build_rsvp_embed(
            name, event_time, rosters, slot_time, description, set_code=set_code,
            announcement=_championship_announcement(guild, set_code, name),
            team_draft=pairing_mode == "team", status_line=status_line,
            roster_interests=roster_interests, team_rosters=team_rosters,
            locked_roster=locked_roster, draft_complete=draft_complete,
            championship_roster=await resolve_championship_card_roster(event_id, rosters),
            created_by=_opener_display_name(guild, opener_id), starts_now=starts_now))
    except discord.HTTPException:
        log.warning(f"could not edit scheduled card {message_id}", exc_info=True)


def _own_card_lobby_roster_sync(event_id: str) -> list[DraftedPlayer]:
    """Who the card lists before the draft seats anyone. A table has no signal to read, so it falls
    back to the live lobby."""
    names = [name for _, name in pod_launch.roster_for_event_sync(event_id)]
    if not names:
        manager = ACTIVE_POD_MANAGERS.get(event_id)
        names = [name for name in manager.non_bot_session_names() if name] if manager else []
    return [DraftedPlayer(display_name=name) for name in names]


def _championship_announcement(
    guild: discord.Guild | None, set_code: str | None, name: str,
) -> str | None:
    """The fixed body a championship card carries, rebuilt so a full re-render puts it back in place of
    the RSVP intro. Nothing stores the text, so it comes off the plan the card was posted for, and only
    while that plan still names the set the card closes."""
    if not is_championship(name) or set_code is None:
        return None
    plan = championship.plan_for()
    if plan is None or plan.set_code.upper() != set_code.upper():
        return None
    return cc.card_content(
        set_name=plan.set_name, set_code=plan.set_code, next_set_name=plan.next_set_name,
        next_set_code=plan.next_set_code, next_release_at=plan.next_release_at,
        champion_mention=champion_role_mention(find_role(guild, SET_CHAMPION_ROLE_NAME)),
    )


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


async def refresh_card_embed(bot: commands.Bot, event_id: str) -> None:
    """Re-render the channel card embed in place, leaving the thread and native-event names alone"""
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
        await refresh_card_embed(bot, event_id)


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


async def _attach_result_link(bot: commands.Bot, event_id: str) -> None:
    """Put a jump button to the podium post on the channel card and on the registered embed in the event
    thread, whose own controls dropped at draft_done. No-op until the post exists."""
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
    view.add_item(build_podium_link_button(url))
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
    title (new name + set symbol) and the native scheduled event's name. The thread rename lives in
    set_event_format; the in-thread registered embed re-renders through the Settings panel. Called
    after the format persists, so the pod reads as its new format wherever the gear was clicked."""
    loaded = await asyncio.to_thread(_load_event, event_id)
    if loaded is None:
        return
    name, event_time, _status, thread_id, native_event_id, _created_at = loaded
    await _edit_scheduled_card(bot, event_id, name, event_time)
    await _refresh_launcher_for_event(bot, event_id)
    await _rename_native_event(bot, thread_id, native_event_id, name, event_time)


async def refresh_event_rsvp_surfaces(bot: commands.Bot, event_id: str) -> None:
    """Re-render a pod's scheduled card and roster reminder so their format-split columns pick up a
    changed signup preference. Each surface reads the roster fresh and edits in place, so an update that
    overlaps another RSVP or preference change converges instead of racing."""
    await _refresh_rsvp_surfaces(bot, event_id, reminder=True)


async def refresh_event_scheduled_card(bot: commands.Bot, event_id: str) -> None:
    """The card alone, for a caller that is about to repost the reminder itself. Editing a card that is
    then deleted is a round trip nobody sees."""
    await _refresh_rsvp_surfaces(bot, event_id, reminder=False)


async def _refresh_rsvp_surfaces(bot: commands.Bot, event_id: str, *, reminder: bool) -> None:
    loaded = await asyncio.to_thread(_load_event, event_id)
    if loaded is None:
        return
    name, event_time, _status, _thread_id, _native_event_id, _created_at = loaded
    work = [_edit_scheduled_card(bot, event_id, name, event_time)]
    if reminder:
        work.append(refresh_roster_reminder_for_event(event_id))
    await asyncio.gather(*work)


def native_event_still_matters(event_time: datetime | None) -> bool:
    """Whether the native event has yet to open its window. It is a discovery surface: somebody browsing
    the Events tab days out, deciding whether to come. Once the banner is up everyone it could reach is
    already in the thread, and a guild scheduled event is one of the slowest and most rate-limited things
    Discord lets a bot touch. Moving the event to a new time is the exception and goes through its own
    path, since that is the event itself changing."""
    if event_time is None:
        return False
    return event_time - datetime.now(timezone.utc) > timedelta(minutes=REMINDER_LEAD_MIN)


async def _rename_native_event(
    bot: commands.Bot, thread_id: str | None, native_event_id: str | None, name: str,
    event_time: datetime | None,
) -> None:
    if native_event_id is None or thread_id is None or not native_event_still_matters(event_time):
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
        start_time, end_time = native_event_window(new_time)
        await native.edit(start_time=start_time, end_time=end_time)
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
    return _opener_display_name(guild, actor_id) or "an Organizer"


def _opener_display_name(guild: discord.Guild | None, user_id: str | None) -> str | None:
    """The member's current display name, so a re-rendered card follows a nickname change. None when
    there is nobody to credit, which is what keeps the footer off a launcher-created card."""
    if guild is None or user_id is None:
        return None
    try:
        member = guild.get_member(int(user_id))
    except ValueError:
        return None
    return member.display_name if member is not None else None


def parse_new_time(raw: str, current: datetime, now: datetime) -> datetime | None:
    """A future event time (ET) from a sesh-style phrase. Understood forms:
    a pasted Discord timestamp token ('<t:1752624000:F>', in the viewer's own zone); an 'NhNm' offset
    from the current time with an optional leading '+'; 'YYYY-MM-DD HH:MM'; a day word ('today',
    'tonight', 'tomorrow', or a weekday like 'fri') optionally with 'at'/'on'/'ET' filler, followed by a
    clock ('9 PM', '10pm', '8:30pm', '20:00'); or a bare clock. A bare clock or weekday already past today
    rolls forward. None when unreadable or not in the future.

    Clocks and day words resolve against the later of the pod's start and the present, so a pod whose
    start already passed still takes 'tomorrow 9pm'. Offsets stay relative to the pod's own start, which
    is what makes '1h' mean 'one hour later than planned'."""
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
    parsed = _parse_natural_time(raw, max(current, now), now)
    return parsed if parsed is not None and parsed > now else None


def _parse_natural_time(raw: str, base: datetime, now: datetime) -> datetime | None:
    tokens = [t for t in raw.replace(",", " ").split() if t not in FILLER_TOKENS and t not in TZ_TOKENS]
    if not tokens:
        return None

    base_date = base.astimezone(SCHEDULE_TZ).date()
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
    match = CLOCK_RE.match(token.replace(".", ""))
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


def _apply_new_time(event_id: str, new_time: datetime) -> None:
    with SessionLocal() as session:
        event = session.get(PodDraftEvent, event_id)
        event.event_time = new_time
        event.event_date = pod_event_date(new_time)
        session.commit()
