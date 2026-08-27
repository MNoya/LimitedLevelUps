"""Dynamic pod queue (Feature B) — the present-tense counterpart to the daily poll.

`/pod-queue` posts a live "who's around right now" queue. The instant the fire threshold is reached
the bot creates the thread + Draftmancer lobby immediately (open_now). Staleness follows Amelas/
DraftBot: no per-entry expiry, one inactivity window that resets on each join.

The queue message is one Components V2 card and the single interactive surface. A V2 card and an
embed look identical, but text in a V2 TextDisplay counts as message content for notifications
while an embed's does not, so the role ping lives inside the card and needs no bare content line
above it. The persistent view re-attaches on restart, and closure is enforced in the DB, so a
stale button goes inert on click and never becomes a dead duplicate card.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from bot import emojis
from bot.commands import descriptions as desc
from bot.commands.messages import MSG_LOBBY_GATHERING, MSG_PLAYERS_JOINED
from bot.commands.pod_rsvp import parse_new_time, post_scheduled_card
from bot.config import settings
from bot.discord_helpers import NBSP, resolve_pod_chat_channel
from bot.services import pod_format_interest as fi
from bot.services import pod_launch
from bot.services.pod_draft_manager import set_event_pick_timer
from bot.services.pod_format import custom_formats, default_pick_timer_for, format_display
from bot.services.pod_format_select import WRITE_IN_VALUE, set_select_option, write_in_option
from bot.services.pod_pairing_select import SELECT_PLACEHOLDER as PAIRING_PLACEHOLDER
from bot.services.pod_pairing_select import pairing_options
from bot.services.ping_roles import announce_pod_grant
from bot.services.pod_roles import find_role, grant_pod_drafters
from bot.services.pod_schedule import CHAT_ANNOUNCE_MARKER, POD_QUEUE_ROLE_NAME
from bot.services.pod_slot import pod_display_name, queue_display_name
from bot.services.pod_settings_view import (
    TIMER_MAX, TIMER_MIN, PodDescriptionModal, description_label, pick_timer_label,
)
from bot.services.pod_signals import (
    KIND_QUEUE,
    LANE_EARLY,
    LANE_LATE,
    QUEUE_BUCKET,
    SCHEDULE_TZ,
    STATUS_FIRED,
    bucket_for_lane,
    inactivity_window_text,
    next_lane_start,
    should_fire,
    slot_role_name_for_event_time,
    teardown_at,
)
from bot.sets import active_set_code, recent_released_sets, set_name_for


log = logging.getLogger(__name__)

QUEUE_TITLE = "Pod Draft Queue"
QUEUE_FIRED = "Join {thread}"
QUEUE_CREATING = "Creating the lobby..."
QUEUE_CLOSED_INACTIVE = "**Closed** after {window} of inactivity"
QUEUE_CLOSED_MANUAL = "**Closed** {when}"
QUEUE_CANCEL_CONFIRM = "Last one in the queue, please confirm"
QUEUE_CANCEL_KEPT = "Still in the queue"
QUEUE_CANCEL_LEFT = "Someone else joined, so you left and the queue stays open"
QUEUE_INSTRUCTIONS = (
    "- Hit **Join** if you can draft right now. **Leave** when you no longer can\n"
    f"- {MSG_LOBBY_GATHERING}"
)
QUEUE_CLOSES = "Closes after {window} of inactivity"
QUEUE_OPENED = "Queue opened by {opener} {when}"
QUEUE_OPENED_ANON = "Queue opened {when}"
QUEUE_THREAD_INTRO = "💬 Chat while it fills\n[**Queue here**]({jump}) {manat}"
QUEUE_THREAD_CLOSED = "🎉 Draft started in {thread}"
QUEUE_NUDGE = "⚡ {count} players in queue! {mention}"
QUEUE_NUDGE_QUIET_MINUTES = 30
QUEUE_PLAYERS_EMPTY = "Players"

JOINABLE_WINDOW = timedelta(hours=6)
MAX_JOINABLE_LINES = 3
SET_PLACEHOLDER = "Choose the set"
WHEN_PLACEHOLDER = "When to draft"
LAUNCHER_TITLE = "### Start a Pod Draft"
LAUNCHER_PROMPT = "Set your options below, then open a queue now or schedule a pod for later"
LAUNCHER_JOIN_HINT = "Join an existing pod instead of starting a new one:"
LAUNCHER_QUEUE_NAME = "{set_code} Pod Draft Queue"
LAUNCHER_JOINABLE_LINE = "⚡ **[{name}]({url})**{emoji} {count} waiting"
LAUNCHER_MORE_LINE = "And {count} more"
CHAT_ANNOUNCE_SCHEDULED = (
    f"{{mention}} {CHAT_ANNOUNCE_MARKER} {{symbol}} **{{name}}** <t:{{unix}}:R> {{manat}} "
    "[**Sign up here**]({url})"
)
CHAT_ANNOUNCE_QUEUE = f"{{mention}} {CHAT_ANNOUNCE_MARKER} {{symbol}} **{{name}}** {{manat}} [**Join here**]({{url}})"
LAUNCHER_OPENING = "⏳ Opening the queue..."
LAUNCHER_SCHEDULING = "⏳ Creating the pod..."
LAUNCHER_SCHEDULED = "Scheduled for {when}. RSVP card posted: {url}"
LAUNCHER_SCHEDULE_FAILED = "The scheduled pod card could not be posted. Try again"
LAUNCHER_SCHEDULE_NO_CHANNEL = "The pod coordination channel could not be reached"
WHEN_MODAL_BAD_TIME = "Enter a future time like Today 7pm, tomorrow 8:30pm, Fri 9pm, or +3h"


class PodQueueActions(discord.ui.ActionRow):
    @discord.ui.button(label="Join", emoji="⚡", style=discord.ButtonStyle.success, custom_id="pod_queue:join")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await _handle_click(interaction, "join")

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.danger, custom_id="pod_queue:leave")
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        context = await asyncio.to_thread(
            pod_launch.queue_member_count_sync, str(interaction.message.id), str(interaction.user.id),
        )
        if context is not None and context == (True, 1):
            await interaction.response.send_message(
                QUEUE_CANCEL_CONFIRM, view=_QueueCancelConfirm(interaction.message), ephemeral=True,
            )
            return
        await _handle_click(interaction, "leave")


class _QueueCancelConfirm(discord.ui.View):
    """Ephemeral last-player prompt: close the queue, or stay in it. Closing self-corrects if someone
    joined during the prompt — the confirmer just leaves and the card stays live."""

    def __init__(self, card: discord.Message) -> None:
        super().__init__(timeout=120)
        self.card = card

    @discord.ui.button(label="Close Queue", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        resolution = await asyncio.to_thread(
            pod_launch.resolve_last_leave_sync, str(self.card.id), str(interaction.user.id),
        )
        if resolution.outcome == pod_launch.LEAVE_GONE:
            await interaction.response.edit_message(content="This queue already closed", view=None)
            return
        mention = role_mention_for(interaction.guild, resolution.notify_role)
        if resolution.outcome == pod_launch.LEAVE_LEFT:
            view = PodQueueView(
                names=resolution.names, role_mention=mention, set_code=resolution.set_code,
                opened_at=resolution.created_at, opened_by=resolution.opened_by,
                description=resolution.description,
            )
            await self.card.edit(view=view)
            await _remove_from_discussion_thread(
                str(self.card.id), interaction.guild, interaction.client, interaction.user,
            )
            await interaction.response.edit_message(content=QUEUE_CANCEL_LEFT, view=None)
            return
        reason = QUEUE_CLOSED_MANUAL.format(when=f"<t:{int(datetime.now(timezone.utc).timestamp())}:R>")
        view = PodQueueView(
            role_mention=mention, close_reason=reason, set_code=resolution.set_code,
            opened_at=resolution.created_at, opened_by=resolution.opened_by,
        )
        await self.card.edit(view=view)
        await interaction.response.edit_message(content=reason, view=None)

    @discord.ui.button(label="Stay in Queue", style=discord.ButtonStyle.secondary)
    async def keep(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(content=QUEUE_CANCEL_KEPT, view=None)


class PodQueueView(discord.ui.LayoutView):
    """The whole queue message: one Components V2 container plus the Join / Leave row. Persistent —
    the buttons carry static custom_ids and the no-arg form is registered at startup."""

    def __init__(
        self, names: list[str] | None = None, role_mention: str | None = None,
        fired: bool = False, thread_mention: str | None = None, close_reason: str | None = None,
        set_code: str | None = None, opened_at: datetime | None = None,
        opened_by: str | None = None, description: str | None = None,
    ) -> None:
        super().__init__(timeout=None)
        names = names or []
        threshold = settings.pod_signal_fire_threshold
        container = discord.ui.Container(accent_colour=discord.Colour.green())
        self.add_item(container)
        container.add_item(discord.ui.TextDisplay(f"## {NBSP * 2}⚡ {_queue_title(role_mention, set_code)}"))
        if description and close_reason is None:
            container.add_item(discord.ui.TextDisplay(f"> {description}"))
        if close_reason is not None:
            container.add_item(discord.ui.TextDisplay(close_reason))
            if names:
                roster = "\n".join(f"> {name}" for name in names)
                container.add_item(discord.ui.TextDisplay(
                    f"**{MSG_PLAYERS_JOINED.format(count=len(names))}**\n{roster}"))
            opened = _opened_line(opened_at, opened_by)
            if opened is not None:
                container.add_item(discord.ui.TextDisplay(opened))
            return
        roster_name = MSG_PLAYERS_JOINED.format(count=len(names)) if names else QUEUE_PLAYERS_EMPTY
        roster = "\n".join(f"> {name}" for name in names) if names else "-"
        if fired:
            body = QUEUE_FIRED.format(thread=thread_mention) if thread_mention else QUEUE_CREATING
            container.add_item(discord.ui.TextDisplay(f"**{roster_name}**\n{roster}"))
            container.add_item(discord.ui.TextDisplay(body))
            return
        instructions = QUEUE_INSTRUCTIONS.format(threshold=emojis.mana_number(threshold))
        container.add_item(discord.ui.TextDisplay(instructions))
        opened = _opened_line(opened_at, opened_by)
        if opened is not None:
            container.add_item(discord.ui.TextDisplay(opened))
        container.add_item(discord.ui.TextDisplay(f"**{roster_name}**\n{roster}"))
        window = inactivity_window_text(settings.pod_queue_inactivity_minutes)
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"-# {QUEUE_CLOSES.format(window=window)}"))
        self.add_item(PodQueueActions())


def _opened_line(opened_at: datetime | None, opened_by: str | None) -> str | None:
    if opened_at is None:
        return None
    when = f"<t:{int(opened_at.timestamp())}:R>"
    if opened_by is not None:
        return QUEUE_OPENED.format(opener=f"<@{opened_by}>", when=when)
    return QUEUE_OPENED_ANON.format(when=when)


def _queue_title(role_mention: str | None, set_code: str | None) -> str:
    """`SET Pod Draft Queue {emoji}` so a non-default queue is legible before anyone joins. The queue
    role is itself named "Pod Draft Queue", so its mention doubles as the label and the ping."""
    code = (set_code or active_set_code()).upper()
    return f"{format_display(code)} {role_mention or QUEUE_TITLE} {fi.format_emoji(code)}"


def queue_inactivity_close_reason() -> str:
    window = inactivity_window_text(settings.pod_queue_inactivity_minutes)
    return QUEUE_CLOSED_INACTIVE.format(window=window)


def queue_role_mention(guild: discord.Guild | None) -> str | None:
    role = find_role(guild, POD_QUEUE_ROLE_NAME)
    return role.mention if role else None


def role_mention_for(guild: discord.Guild | None, role_name: str | None) -> str | None:
    if role_name is None:
        return None
    role = find_role(guild, role_name)
    return role.mention if role else None


def derived_notify_role(scheduled_time: datetime | None, notify: bool) -> str | None:
    """Who a launched pod pings, derived from its time rather than a free choice so a slot always
    reaches the people who subscribed to it: nobody when the bell is off, the slot's role when the
    scheduled time lands on a named slot, otherwise the general Pod Draft Queue role."""
    if not notify:
        return None
    if scheduled_time is None:
        return POD_QUEUE_ROLE_NAME
    return slot_role_name_for_event_time(scheduled_time) or POD_QUEUE_ROLE_NAME


async def _handle_click(interaction: discord.Interaction, action: str) -> None:
    message_id = str(interaction.message.id)
    result = await asyncio.to_thread(
        pod_launch.set_membership_sync,
        message_id, QUEUE_BUCKET, str(interaction.user.id), interaction.user.display_name, action,
    )
    if result is None:
        await interaction.response.send_message("This queue is no longer active", ephemeral=True)
        return
    if result.closed:
        await interaction.response.send_message("This queue already closed", ephemeral=True)
        return
    if not result.changed:
        note = "You're already in the queue." if action == "join" else "You're not in the queue."
        await interaction.response.send_message(note, ephemeral=True)
        return

    if action == "join":
        teardown = teardown_at(datetime.now(timezone.utc), settings.pod_queue_inactivity_minutes)
        pod_launch.arm_queue_teardown(interaction.client, result.state.signal_id, teardown)

    fired = await _claim_fire_if_ready(result)
    mention = role_mention_for(interaction.guild, result.state.notify_role)
    if not fired and result.state.status == STATUS_FIRED:
        thread_id = None
        if result.state.event_id is not None:
            thread_id = await asyncio.to_thread(pod_launch.event_thread_id_sync, result.state.event_id)
        view = PodQueueView(
            names=result.names, role_mention=mention, fired=True,
            thread_mention=f"<#{thread_id}>" if thread_id else None, set_code=result.state.set_code,
            description=result.state.description,
        )
    else:
        view = PodQueueView(
            names=result.names, role_mention=mention, set_code=result.state.set_code,
            opened_at=result.state.created_at, opened_by=result.state.opened_by,
            description=result.state.description,
        )
    await interaction.response.edit_message(view=view)
    if action == "leave":
        await _remove_from_discussion_thread(
            message_id, interaction.guild, interaction.client, interaction.user,
        )
    await _post_join_followups(interaction, result, fired)


async def _claim_fire_if_ready(result) -> bool:
    if not (result.joined and should_fire(result.state.count, settings.pod_signal_fire_threshold)):
        return False
    return await asyncio.to_thread(pod_launch.claim_fire_sync, result.state.signal_id)


async def _post_join_followups(interaction: discord.Interaction, result, fired: bool) -> None:
    first_pod = False
    if result.joined and isinstance(interaction.user, discord.Member):
        await _add_to_discussion_thread(interaction)
        first_pod = await grant_pod_drafters(interaction.user)
    await announce_pod_grant(interaction, first_pod=first_pod)
    if result.joined and not fired:
        await _maybe_nudge(interaction, result.state)
    if fired:
        asyncio.create_task(_launch_pod(interaction.client, result.state))


async def _launch_pod(bot: commands.Bot, state) -> None:
    presets = await asyncio.to_thread(pod_launch.queue_presets_sync, state.signal_id)
    set_code = presets.set_code or active_set_code()
    now = datetime.now(timezone.utc)
    name = await asyncio.to_thread(pod_launch.ondemand_event_name_sync, set_code, now)
    event_id = await pod_launch.launch_from_signal(
        bot, state.signal_id, set_code=set_code, event_time=now, name=name, open_now=True,
    )
    if event_id is None:
        await asyncio.to_thread(pod_launch.release_fire_sync, state.signal_id)
        log.warning(f"queue fire for {state.signal_id} failed to launch; reverted to open")
        return
    await _apply_queue_presets(event_id, presets)
    await _link_thread_on_card(
        bot, state.signal_id, event_id, set_code, state.notify_role, state.description,
    )
    await _close_discussion_thread(bot, state.signal_id, event_id)


async def _close_discussion_thread(bot: commands.Bot, signal_id: str, event_id: str) -> None:
    """Archive the queue's discussion thread when the pod fires, after pointing its chatters at the draft room."""
    ref = await asyncio.to_thread(pod_launch.signal_message_ref_sync, signal_id)
    if ref is None:
        return
    _, card_message_id = ref
    thread = await _resolve_discussion_thread(card_message_id, None, bot)
    if thread is None or thread.archived:
        return
    event_thread_id = await asyncio.to_thread(pod_launch.event_thread_id_sync, event_id)
    try:
        if event_thread_id is not None:
            await thread.send(QUEUE_THREAD_CLOSED.format(thread=f"<#{event_thread_id}>"))
        await thread.edit(archived=True)
    except discord.HTTPException:
        log.warning(f"could not close discussion thread for queue {signal_id}", exc_info=True)


async def _link_thread_on_card(
    bot: commands.Bot, signal_id: str, event_id: str, set_code: str,
    notify_role: str | None = None, description: str | None = None,
) -> None:
    """The fired card's only update: same roster, the thread link added, buttons gone. The card is
    left untouched between the fire and the thread existing."""
    thread_id = await asyncio.to_thread(pod_launch.event_thread_id_sync, event_id)
    ref = await asyncio.to_thread(pod_launch.signal_message_ref_sync, signal_id)
    if thread_id is None or ref is None:
        return
    channel_id, message_id = ref
    channel = bot.get_channel(int(channel_id))
    guild = getattr(channel, "guild", None)
    if channel is None or guild is None:
        return
    roster = await asyncio.to_thread(pod_launch.roster_for_event_sync, event_id)
    names = [name for _, name in roster]
    try:
        message = await channel.fetch_message(int(message_id))
        view = PodQueueView(
            names=names, role_mention=role_mention_for(guild, notify_role), fired=True,
            thread_mention=f"<#{thread_id}>", set_code=set_code, description=description,
        )
        await message.edit(view=view)
    except discord.HTTPException:
        log.warning(f"could not link pod thread on queue message {message_id}", exc_info=True)


async def _maybe_nudge(interaction: discord.Interaction, state) -> None:
    """One ping when the queue reaches one short of firing, DraftBot-style: only once per queue and
    only after the quiet window, so a queue that fills quickly never pings at all."""
    if state.count != settings.pod_signal_fire_threshold - 1:
        return
    claimed = await asyncio.to_thread(
        pod_launch.claim_one_more_ping_sync, state.signal_id, QUEUE_NUDGE_QUIET_MINUTES,
    )
    if not claimed:
        return
    mention = queue_role_mention(interaction.guild)
    if mention is None:
        return
    try:
        await interaction.channel.send(
            QUEUE_NUDGE.format(count=state.count, mention=mention),
            allowed_mentions=discord.AllowedMentions(roles=True),
        )
    except discord.HTTPException:
        log.warning("queue nudge send failed", exc_info=True)


async def _apply_queue_presets(event_id: str, presets) -> None:
    """Apply the launcher choice the event row does not already carry. The set, the pairing and the
    seating are written at creation, so a card never renders one value and then corrects itself; the pick
    timer is what is left, and no card shows it."""
    if presets.pick_timer is not None:
        await set_event_pick_timer(event_id, presets.pick_timer)


class DraftLauncherView(discord.ui.View):
    """Ephemeral pre-draft config for /draft: set, when, and pairings as dropdowns plus a notify bell,
    pick-timer, and description buttons, all on one panel, then Start Draft. Rebuilds itself on each
    choice so every control shows the current selection, like the lobby Settings panel. The chosen set
    rides into the pod name and Draftmancer session when the queue fires; the default is the active
    set. Notify is a plain on/off bell; the ping role follows the pod's time via derived_notify_role,
    so a slot always reaches the people who subscribed to it.

    The bell starts off. /draft is open to every player, so a default-on ping lets someone who does not
    know the slot roles wake a few hundred people at a bad hour on their first try. Turning it on is one
    click for whoever means it, and a quiet pod still reaches the channel through the one-short nudge and
    the underfill reminder once it needs players."""

    def __init__(self, *, set_code: str | None = None, pairing_mode: str | None = None,
                 pick_timer: int | None = None, scheduled_time: datetime | None = None,
                 notify: bool = False, description: str | None = None) -> None:
        super().__init__(timeout=300)
        self.set_code = set_code
        self.pairing_mode = pairing_mode
        self.pick_timer = pick_timer
        self.scheduled_time = scheduled_time
        self.notify = notify
        self.description = description
        self.add_item(_LauncherSetSelect(set_code, row=0))
        self.add_item(_LauncherWhenSelect(scheduled_time, row=1))
        self.add_item(_LauncherPairingSelect(pairing_mode, row=2))
        self.add_item(_LauncherNotifyButton(notify, row=4))
        self.add_item(_LauncherTimerButton(pick_timer, row=4))
        self.add_item(_LauncherDescriptionButton(description, row=4))
        self.add_item(_LauncherStartButton(scheduled=scheduled_time is not None, row=4))

    def set_format(self, code: str) -> None:
        """Choose the set and default the pick timer to match it, so both controls move together."""
        self.set_code = code
        self.pick_timer = default_pick_timer_for(code)

    async def rerender(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(view=DraftLauncherView(
            set_code=self.set_code, pairing_mode=self.pairing_mode,
            pick_timer=self.pick_timer, scheduled_time=self.scheduled_time,
            notify=self.notify, description=self.description,
        ))


def _set_options(current: str | None) -> list[discord.SelectOption]:
    """The set dropdown: the active set (default), the registered cubes, the most recent released sets,
    then a write-in for any other code — each carrying its keyrune emoji when one is loaded. Cubes are
    always offered right under the latest set. Unreleased upcoming sets are left out; they have no card
    pool to draft. A written-in current outside the known list shows as its own defaulted option so it
    survives re-render."""
    active = active_set_code()
    active_upper = active.upper()
    chosen = (current or active).upper()
    recent = [seed.code for seed in recent_released_sets()]
    cubes = custom_formats()
    known = {active_upper} | {fmt.code for fmt in cubes} | {code.upper() for code in recent}

    options: list[discord.SelectOption] = [write_in_option("Set")]
    if chosen not in known:
        options.append(set_select_option(
            chosen, label=f"Set: {chosen}", description=set_name_for(chosen), default=True))
    options.append(set_select_option(
        active, label=f"Set: {active}", description="The latest set", default=(chosen == active_upper)))
    for fmt in cubes:
        options.append(discord.SelectOption(
            label=f"Set: {fmt.label}", value=fmt.code, description=f"CubeCobra: {fmt.cube_id}",
            emoji=fi.cube_emoji(), default=(chosen == fmt.code)))
    for code in recent:
        options.append(set_select_option(
            code, label=f"Set: {code}", description=set_name_for(code), default=(chosen == code)))
    return options


class _LauncherSetSelect(discord.ui.Select):
    def __init__(self, current: str | None, row: int | None = None) -> None:
        super().__init__(placeholder=SET_PLACEHOLDER, options=_set_options(current),
                         min_values=1, max_values=1, row=row)

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.values[0] == WRITE_IN_VALUE:
            await interaction.response.send_modal(_LauncherSetModal(self.view))
            return
        self.view.set_format(self.values[0])
        await self.view.rerender(interaction)


class _LauncherSetModal(discord.ui.Modal, title="Draft a different set"):
    code = discord.ui.TextInput(label="Set code", placeholder="e.g. FIN", min_length=2, max_length=8)

    def __init__(self, view: "DraftLauncherView") -> None:
        super().__init__()
        self.launcher = view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.launcher.set_format(self.code.value.strip().upper())
        await self.launcher.rerender(interaction)


def _when_day_label(when: datetime, now: datetime) -> str:
    local = when.astimezone(SCHEDULE_TZ)
    today = now.astimezone(SCHEDULE_TZ).date()
    if local.date() == today:
        return "Today"
    if local.date() == today + timedelta(days=1):
        return "Tomorrow"
    return local.strftime("%b %-d")


def _when_clock(when: datetime) -> str:
    return when.astimezone(SCHEDULE_TZ).strftime("%-I:%M %p ET")


def _when_options(scheduled_time: datetime | None, now: datetime) -> list[discord.SelectOption]:
    """Right now (default) plus the two named slots at their next occurrence, then a custom write-in.
    A custom time shows as its own defaulted option."""
    today = now.astimezone(SCHEDULE_TZ).date()
    early = next_lane_start(LANE_EARLY, now)
    late = next_lane_start(LANE_LATE, now)
    options = [discord.SelectOption(
        label="When: Right now", value="now", emoji="⚡", description="Open a live queue now",
        default=(scheduled_time is None))]
    for lane, slot in ((LANE_EARLY, early), (LANE_LATE, late)):
        bucket = bucket_for_lane(today, lane)
        options.append(discord.SelectOption(
            label=f"When: {bucket.name}", value=lane, emoji=bucket.emoji,
            description=f"{_when_day_label(slot, now)} {_when_clock(slot)}",
            default=(scheduled_time is not None and scheduled_time == slot)))
    is_custom = scheduled_time is not None and scheduled_time not in (early, late)
    if is_custom:
        label = f"When: {_when_day_label(scheduled_time, now)} {_when_clock(scheduled_time)}"
        description = "Change the custom time"
    else:
        label = "When: Schedule for later…"
        description = "Pick a custom date and time"
    options.append(discord.SelectOption(
        label=label, value=WRITE_IN_VALUE, description=description, default=is_custom))
    return options


class _LauncherWhenSelect(discord.ui.Select):
    def __init__(self, current: datetime | None, row: int | None = None) -> None:
        super().__init__(placeholder=WHEN_PLACEHOLDER, min_values=1, max_values=1, row=row,
                         options=_when_options(current, datetime.now(timezone.utc)))

    async def callback(self, interaction: discord.Interaction) -> None:
        value = self.values[0]
        if value == WRITE_IN_VALUE:
            await interaction.response.send_modal(_LauncherWhenModal(self.view))
            return
        if value == "now":
            self.view.scheduled_time = None
        else:
            self.view.scheduled_time = next_lane_start(value, datetime.now(timezone.utc))
        await self.view.rerender(interaction)


class _LauncherWhenModal(discord.ui.Modal, title="Schedule a Pod"):
    when = discord.ui.TextInput(
        label="When (ET)", placeholder="Today 7pm, tomorrow 8:30pm, Fri 9pm, +3h", min_length=2, max_length=32)

    def __init__(self, view: "DraftLauncherView") -> None:
        super().__init__()
        self.launcher = view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        now = datetime.now(timezone.utc)
        parsed = parse_new_time(self.when.value.strip(), now, now)
        if parsed is None:
            await self.launcher.rerender(interaction)
            await interaction.followup.send(f"⚠️ {WHEN_MODAL_BAD_TIME}", ephemeral=True)
            return
        self.launcher.scheduled_time = parsed
        await self.launcher.rerender(interaction)


class _LauncherPairingSelect(discord.ui.Select):
    def __init__(self, current: str | None, row: int | None = None) -> None:
        super().__init__(placeholder=PAIRING_PLACEHOLDER, options=pairing_options(current),
                         min_values=1, max_values=1, row=row)

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.pairing_mode = self.values[0]
        await self.view.rerender(interaction)


class _LauncherNotifyButton(discord.ui.Button):
    def __init__(self, notify: bool, row: int | None = None) -> None:
        label = "Notify: On" if notify else "Notify: Off"
        emoji = "🔔" if notify else "🔕"
        super().__init__(label=label, emoji=emoji, style=discord.ButtonStyle.grey, row=row)

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.notify = not self.view.notify
        await self.view.rerender(interaction)


class _LauncherTimerButton(discord.ui.Button):
    def __init__(self, current: int | None, row: int | None = None) -> None:
        super().__init__(label=pick_timer_label(current), emoji="⏱️",
                         style=discord.ButtonStyle.grey, row=row)

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(_LauncherTimerModal(self.view))


class _LauncherTimerModal(discord.ui.Modal, title="Pick timer"):
    seconds = discord.ui.TextInput(label="Seconds per pick", placeholder="e.g. 60", min_length=1, max_length=3)

    def __init__(self, view: DraftLauncherView) -> None:
        super().__init__()
        self.launcher = view
        if view.pick_timer is not None:
            self.seconds.default = str(view.pick_timer)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raw = self.seconds.value.strip()
        if not raw.isdigit() or not (TIMER_MIN <= int(raw) <= TIMER_MAX):
            await interaction.response.send_message(
                f"⚠️ Enter a whole number of seconds between {TIMER_MIN} and {TIMER_MAX}", ephemeral=True,
            )
            return
        self.launcher.pick_timer = int(raw)
        await self.launcher.rerender(interaction)


class _LauncherDescriptionButton(discord.ui.Button):
    def __init__(self, current: str | None, row: int | None = None) -> None:
        super().__init__(label=description_label(current), emoji="📝",
                         style=discord.ButtonStyle.grey, row=row)

    async def callback(self, interaction: discord.Interaction) -> None:
        launcher: DraftLauncherView = self.view
        await interaction.response.send_modal(
            PodDescriptionModal(launcher.description, self._apply))

    async def _apply(self, interaction: discord.Interaction, text: str | None) -> None:
        launcher: DraftLauncherView = self.view
        launcher.description = text
        await launcher.rerender(interaction)


class _LauncherStartButton(discord.ui.Button):
    def __init__(self, scheduled: bool = False, row: int | None = None) -> None:
        label = "Confirm Draft" if scheduled else "Open Queue"
        emoji = "🗓️" if scheduled else "⚡"
        super().__init__(label=label, emoji=emoji, style=discord.ButtonStyle.success, row=row)

    async def callback(self, interaction: discord.Interaction) -> None:
        """Strip the panel down to a progress line before the work starts. Creating a pod takes several
        seconds of card, thread, and native-event calls, and a plain defer leaves every control live and
        unchanged for all of it, so the press reads as a button that did nothing and invites a second
        one."""
        view: DraftLauncherView = self.view
        scheduled = view.scheduled_time is not None
        await interaction.response.edit_message(
            content=LAUNCHER_SCHEDULING if scheduled else LAUNCHER_OPENING, view=None)
        if scheduled:
            await _schedule_pod(
                interaction, view.set_code, view.pairing_mode, view.pick_timer,
                view.scheduled_time, view.notify, view.description,
            )
            return
        await _open_queue(
            interaction, view.set_code, view.pairing_mode, view.pick_timer,
            view.notify, view.description,
        )


async def _open_queue(
    interaction: discord.Interaction, set_code: str | None, pairing_mode: str | None,
    pick_timer: int | None, notify: bool, description: str | None,
) -> None:
    """Post the public queue card from the launcher and wire its signal, carrying the chosen set and
    presets. Dismisses the ephemeral launcher and runs the opener's own join through the normal path."""
    role = derived_notify_role(None, notify)
    mention = role_mention_for(interaction.guild, role)
    message = await interaction.channel.send(
        view=PodQueueView(
            names=[interaction.user.display_name], role_mention=mention, set_code=set_code,
            opened_at=datetime.now(timezone.utc), opened_by=str(interaction.user.id), description=description,
        ),
        allowed_mentions=discord.AllowedMentions(roles=True, users=False),
    )
    signal_id = await asyncio.to_thread(
        pod_launch.create_queue_signal_sync,
        guild_id=str(interaction.guild_id or ""), channel_id=str(interaction.channel_id),
        message_id=str(message.id), signal_date=datetime.now(SCHEDULE_TZ).date(),
        opened_by=str(interaction.user.id),
        set_code=set_code, pairing_mode=pairing_mode, pick_timer=pick_timer,
        notify_role=role, description=description,
    )
    await _open_discussion_thread(message, set_code, description, interaction.user, signal_id)
    resolved_set = (set_code or active_set_code()).upper()
    queue_name = LAUNCHER_QUEUE_NAME.format(set_code=format_display(resolved_set))
    await _announce_pod(interaction, message.channel.id, CHAT_ANNOUNCE_QUEUE.format(
        mention=interaction.user.mention, symbol=_announce_symbol(resolved_set), name=queue_name,
        manat=emojis.get("manat"), url=message.jump_url,
    ))
    result = await asyncio.to_thread(
        pod_launch.set_membership_sync,
        str(message.id), QUEUE_BUCKET, str(interaction.user.id), interaction.user.display_name, "join",
    )
    teardown = teardown_at(datetime.now(timezone.utc), settings.pod_queue_inactivity_minutes)
    pod_launch.arm_queue_teardown(interaction.client, signal_id, teardown)
    log.info(f"opened pod queue as message {message.id} (signal {signal_id})")
    await interaction.delete_original_response()
    if result is not None:
        fired = await _claim_fire_if_ready(result)
        await _post_join_followups(interaction, result, fired)


async def _open_discussion_thread(
    message: discord.Message, set_code: str | None, description: str | None,
    opener: discord.abc.User, signal_id: str,
) -> None:
    """Open a standalone discussion thread for the queue, tracked on the signal by its own id.

    Deliberately not hung off the card message: a message-anchored thread mirrors the card as its
    starter, so its role ping and Join instructions read as confusing noise inside the thread. A
    standalone thread carries a clean intro linking back to the card instead. The opener joins it,
    matching how the Join button pulls every other joiner in.
    """
    channel = message.channel
    if not isinstance(channel, discord.TextChannel):
        return
    resolved_set = (set_code or active_set_code()).upper()
    base_name = queue_display_name(resolved_set, datetime.now(timezone.utc))
    thread_name = pod_launch.dedupe_thread_name(channel, base_name)
    try:
        thread = await channel.create_thread(name=thread_name[:100], type=discord.ChannelType.public_thread)
    except discord.HTTPException:
        log.warning(f"could not open discussion thread for queue {message.id}", exc_info=True)
        return
    await asyncio.to_thread(pod_launch.set_discussion_thread_sync, signal_id, str(thread.id))
    intro = QUEUE_THREAD_INTRO.format(jump=message.jump_url, manat=emojis.get("manat"))
    if description:
        intro = f"{intro}\n> {description}"
    try:
        await thread.send(intro)
        await thread.add_user(opener)
    except discord.HTTPException:
        log.warning(f"could not seed discussion thread {thread.id}", exc_info=True)


async def _resolve_discussion_thread(
    card_message_id: str, guild: discord.Guild | None, client: discord.Client,
) -> discord.Thread | None:
    thread_id = await asyncio.to_thread(pod_launch.discussion_thread_id_sync, card_message_id)
    if thread_id is None:
        return None
    thread = guild.get_thread(int(thread_id)) if guild is not None else None
    if thread is None:
        try:
            fetched = await client.fetch_channel(int(thread_id))
            thread = fetched if isinstance(fetched, discord.Thread) else None
        except discord.HTTPException:
            thread = None
    return thread


async def _add_to_discussion_thread(interaction: discord.Interaction) -> None:
    """Pull a joiner into the queue's discussion thread so they follow the "who's around" chatter."""
    thread = await _resolve_discussion_thread(
        str(interaction.message.id), interaction.guild, interaction.client,
    )
    if thread is None:
        return
    try:
        await thread.add_user(interaction.user)
    except discord.HTTPException:
        log.warning(f"could not add {interaction.user} to queue thread {thread.id}", exc_info=True)


async def _remove_from_discussion_thread(
    card_message_id: str, guild: discord.Guild | None, client: discord.Client, user: discord.abc.User,
) -> None:
    """Drop a leaver from the discussion thread, so its member list tracks the live queue roster."""
    thread = await _resolve_discussion_thread(card_message_id, guild, client)
    if thread is None:
        return
    try:
        await thread.remove_user(user)
    except discord.HTTPException:
        log.warning(f"could not remove {user} from queue thread {thread.id}", exc_info=True)


async def _schedule_pod(
    interaction: discord.Interaction, set_code: str | None, pairing_mode: str | None,
    pick_timer: int | None, when: datetime, notify: bool, description: str | None,
) -> None:
    """Post a scheduled RSVP card in the coordination channel for a future pod, carrying the launcher's
    set and presets, with the opener seeded as the first Yes. The bell picks the slot's ping role off
    the pod's time; Notify off silences the card."""
    channel = interaction.client.get_channel(settings.pod_draft_channel_id)
    if not isinstance(channel, discord.TextChannel):
        await interaction.edit_original_response(content=LAUNCHER_SCHEDULE_NO_CHANNEL, view=None)
        return
    role = derived_notify_role(when, notify)
    resolved_set = (set_code or active_set_code()).upper()
    name = await asyncio.to_thread(pod_launch.ondemand_event_name_sync, resolved_set, when)
    opener = [(str(interaction.user.id), interaction.user.display_name)]
    event_id = await post_scheduled_card(
        interaction.client, channel, set_code=resolved_set, event_time=when, name=name,
        preseed_yes=opener, ping_role=False, notify_role_name=role, description=description,
        pairing_mode=pairing_mode, pick_timer=pick_timer, format_locked=True,
        opener=interaction.user,
    )
    if event_id is None:
        await interaction.edit_original_response(content=LAUNCHER_SCHEDULE_FAILED, view=None)
        return
    ref = await asyncio.to_thread(pod_launch.scheduled_card_ref_sync, event_id)
    card_url = f"https://discord.com/channels/{interaction.guild_id}/{ref[1]}/{ref[2]}" if ref else None
    log.info(f"scheduled pod {name} for {when.isoformat()} (event {event_id})")
    announced = card_url is not None and await _announce_pod(
        interaction, channel.id, CHAT_ANNOUNCE_SCHEDULED.format(
            mention=interaction.user.mention, symbol=_announce_symbol(resolved_set), name=name,
            unix=int(when.timestamp()), manat=emojis.get("manat"), url=card_url))
    if announced:
        await interaction.delete_original_response()
        return
    when_tag = f"<t:{int(when.timestamp())}:F>"
    await interaction.edit_original_response(
        content=LAUNCHER_SCHEDULED.format(when=when_tag, url=card_url or channel.mention), view=None)


async def _announce_pod(
    interaction: discord.Interaction, card_channel_id: int, content: str,
) -> bool:
    """Say publicly that someone started a pod, and whether any channel took it.

    A scheduled pod's own confirmation, so it lands where the player ran /draft and the people around
    them see both the pod and the command that made it. An ephemeral reply cannot be turned public, so
    the caller deletes it once this succeeds.

    pod-draft-chat is announced too whenever /draft ran somewhere else, since that is the channel
    watching for pods. The card's own channel is left out: a line beside the card only repeats it, which
    is why a queue opened in the channel it posts to announces only in pod-draft-chat.

    Nothing is pinged. The announcement is a heads-up and the bell on the card owns the ping.
    """
    posted = False
    seen = {card_channel_id}
    for destination in (interaction.channel, resolve_pod_chat_channel(interaction.client)):
        channel_id = getattr(destination, "id", None)
        if destination is None or channel_id in seen:
            continue
        seen.add(channel_id)
        try:
            await destination.send(content, allowed_mentions=discord.AllowedMentions.none())
            posted = True
        except discord.HTTPException:
            log.warning(f"could not announce the /draft pod in {channel_id}", exc_info=True)
    return posted


def _announce_symbol(set_code: str) -> str:
    symbol = emojis.set_symbol(set_code)
    return str(symbol) if symbol is not None else "➡️"


def _joinable_line(guild: discord.Guild, signal) -> str:
    url = f"https://discord.com/channels/{guild.id}/{signal.channel_id}/{signal.message_id}"
    set_code = (signal.set_code or active_set_code()).upper()
    if signal.kind == KIND_QUEUE or signal.slot_time is None:
        name = LAUNCHER_QUEUE_NAME.format(set_code=format_display(set_code))
    else:
        name = pod_display_name(set_code, signal.slot_time)
    return LAUNCHER_JOINABLE_LINE.format(
        name=name, url=url, emoji=f" {fi.format_emoji(set_code)}", count=signal.count)


def _launcher_content(guild: discord.Guild | None, joinable: list) -> str:
    if guild is None or not joinable:
        return f"{LAUNCHER_TITLE}\n{LAUNCHER_PROMPT}"
    lines = [_joinable_line(guild, signal) for signal in joinable[:MAX_JOINABLE_LINES]]
    if len(joinable) > MAX_JOINABLE_LINES:
        lines.append(LAUNCHER_MORE_LINE.format(count=len(joinable) - MAX_JOINABLE_LINES))
    joined = "\n".join(lines)
    return f"{LAUNCHER_TITLE}\n{LAUNCHER_JOIN_HINT}\n{joined}\n\n{LAUNCHER_PROMPT}"


class PodQueue(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="draft", description=desc.POD_QUEUE)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def pod_queue(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        joinable = await asyncio.to_thread(
            pod_launch.joinable_signals_sync, str(interaction.guild_id or ""),
            now=datetime.now(timezone.utc), within=JOINABLE_WINDOW,
        )
        await interaction.followup.send(
            content=_launcher_content(interaction.guild, joinable), view=DraftLauncherView(),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PodQueue(bot))
