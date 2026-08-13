"""`!test sandbox` — one pod you drive by hand, from empty thread to open tables.

Every other `!test` surface seeds a fixed shape and shows you the result. This one hands you the levers
instead: add a player, confirm one, take one back, move the pod to its hold, release it. The roster card
re-renders after every press, so what a given roster makes the card say is answered by watching rather
than by running the command again with different numbers.

Adds go through the production RSVP path, so whether a new signup lands confirmed is decided the way it
is live: a Yes inside the confirmation hour confirms itself, one outside it does not.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import discord
from discord import ui
from discord.ext import commands
from sqlalchemy import delete, select

from bot.commands.pod_rsvp import post_scheduled_card, refresh_card_embed
from bot.commands.test_group import HALL_OF_FAME, test_group
from bot.database import SessionLocal
from bot.models import PodDraftEvent, PodSignal, PodSignalMember
from bot.services import pod_launch
from bot.services.pod_confirm import attendance_for_event_sync, seating_plan, set_confirmations_sync
from bot.services.pod_drafts import load_event_thread_id_sync
from bot.services.pod_schedule import SCHEDULE_TZ
from bot.services.pod_signals import RSVP_MAYBE, RSVP_NO, RSVP_YES
from bot.services.pod_staging import Signup, confirmed_first_roster_sync
from bot.sets import active_set_code
from bot.tasks.pod_draft_reminder import refresh_or_repost_roster_reminder, repost_roster_reminder


SANDBOX_LEAD_MIN = 90
SEED_PREFIX = "sandbox-"
TABLE_WORTH = 8

log = logging.getLogger(__name__)


async def setup(bot: commands.Bot) -> None:
    @test_group.command(name="sandbox")
    @commands.is_owner()
    async def test_sandbox(ctx: commands.Context, players: int = 0, confirmed: int = 0) -> None:
        """Owner-only. A pod you drive by hand, to watch the card answer one roster at a time.

        Opens a real pod ninety minutes out, so it starts outside the confirmation hour and a fresh
        signup lands unconfirmed until you confirm it. Posts the roster card and a panel of controls
        under it: add a player or a maybe, confirm one or all, take a confirmation back, decline
        somebody, then move the pod to its hold and open the tables.

        `players` and `confirmed` pre-fill it, so `!test sandbox 6 4` starts from six signups with four
        of them confirmed. With no arguments the pod starts empty. Clear it with `!test reset`."""
        if not isinstance(ctx.channel, discord.TextChannel):
            await ctx.send("Run `!test sandbox` in a server text channel")
            return
        event_time = datetime.now(SCHEDULE_TZ) + timedelta(minutes=SANDBOX_LEAD_MIN)
        set_code = active_set_code()
        name = await asyncio.to_thread(pod_launch.ondemand_event_name_sync, set_code, event_time)
        event_id = await post_scheduled_card(
            ctx.bot, ctx.channel, set_code=set_code, event_time=event_time, name=name,
        )
        if event_id is None:
            await ctx.send("Could not create the scheduled card. Check the logs")
            return
        for seat in range(players):
            await _seat_rsvp(event_id, seat, RSVP_YES)
        if confirmed:
            await asyncio.to_thread(
                set_confirmations_sync, event_id,
                [_seat_id(seat) for seat in range(min(confirmed, players))],
            )
        thread = await _pod_thread(ctx.bot, event_id)
        if thread is None:
            await ctx.send("Could not reach the pod thread. Check the logs")
            return
        await refresh_card_embed(ctx.bot, event_id)
        await repost_roster_reminder(event_id)
        await thread.send(await _panel_body(event_id), view=build_sandbox_panel(event_id))


BUTTON_PREFIX = "sandbox"


class SandboxButton(
    ui.DynamicItem[ui.Button], template=rf"{BUTTON_PREFIX}:(?P<action>[a-z]+):(?P<event_id>.+)",
):
    """One lever. The pod it drives rides in the custom_id rather than on the view, so the panel keeps
    working after the bot reloads instead of turning into nine dead buttons."""

    def __init__(self, action: str, event_id: str) -> None:
        lever = LEVERS[action]
        super().__init__(ui.Button(
            label=lever.label, emoji=lever.emoji, style=lever.style, row=lever.row,
            custom_id=f"{BUTTON_PREFIX}:{action}:{event_id}",
        ))
        self.action = action
        self.event_id = event_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: ui.Button, match: re.Match):
        return cls(match["action"], match["event_id"])

    async def callback(self, interaction: discord.Interaction) -> None:
        lever = LEVERS[self.action]
        await interaction.response.defer()
        await lever.run(interaction.client, self.event_id)
        if lever.renders_card:
            await refresh_card_embed(interaction.client, self.event_id)
            await refresh_or_repost_roster_reminder(self.event_id)
        with contextlib.suppress(discord.HTTPException):
            await interaction.message.edit(
                content=await _panel_body(self.event_id), view=build_sandbox_panel(self.event_id),
            )


def build_sandbox_panel(event_id: str) -> ui.View:
    view = ui.View(timeout=None)
    for action in LEVERS:
        view.add_item(SandboxButton(action, event_id))
    return view


@dataclass(frozen=True)
class Lever:
    label: str
    emoji: str
    style: discord.ButtonStyle
    row: int
    run: "Callable[[commands.Bot, str], Awaitable[None]]"
    renders_card: bool = True


async def _add_yes(_bot: commands.Bot, event_id: str) -> None:
    await _seat_rsvp(event_id, await asyncio.to_thread(_seats_taken_sync, event_id), RSVP_YES)


async def _add_eight(_bot: commands.Bot, event_id: str) -> None:
    """A table's worth in one press, since the interesting states all sit past eight."""
    taken = await asyncio.to_thread(_seats_taken_sync, event_id)
    for seat in range(taken, taken + TABLE_WORTH):
        await _seat_rsvp(event_id, seat, RSVP_YES)


async def _add_maybe(_bot: commands.Bot, event_id: str) -> None:
    await _seat_rsvp(event_id, await asyncio.to_thread(_seats_taken_sync, event_id), RSVP_MAYBE)


async def _decline_one(_bot: commands.Bot, event_id: str) -> None:
    """Drop the last confirmed player if there is one, else the last still pending. Confirmed first,
    because declining somebody who was never seated changes nothing on the card and reads as a dead
    button."""
    roster = await asyncio.to_thread(confirmed_first_roster_sync, event_id)
    held = [signup for signup in roster if signup.confirmed]
    target = held[-1] if held else (roster[-1] if roster else None)
    if target is not None:
        await _seat_rsvp(event_id, _seat_of(target), RSVP_NO)


async def _confirm_one(_bot: commands.Bot, event_id: str) -> None:
    await _shift_confirmations(event_id, 1)


async def _confirm_all(_bot: commands.Bot, event_id: str) -> None:
    await _shift_confirmations(event_id, None)


async def _take_one_back(_bot: commands.Bot, event_id: str) -> None:
    await _shift_confirmations(event_id, -1)


async def _shift_confirmations(event_id: str, by: int | None) -> None:
    """The roster comes back confirmed-first, so only the boundary between the two groups moves and
    nobody's place in the queue changes."""
    roster = await asyncio.to_thread(confirmed_first_roster_sync, event_id)
    held = sum(1 for signup in roster if signup.confirmed)
    wanted = len(roster) if by is None else max(0, min(len(roster), held + by))
    await asyncio.to_thread(
        set_confirmations_sync, event_id, [signup.discord_id for signup in roster[:wanted]],
    )


async def _hold_now(bot: commands.Bot, event_id: str) -> None:
    await asyncio.to_thread(_bring_forward_sync, event_id)
    await pod_launch.open_ondemand_lobby(bot, event_id)


async def _open_tables(bot: commands.Bot, event_id: str) -> None:
    pod_launch.cancel_release(bot, event_id)
    await pod_launch.release_attendance_hold(bot, event_id)


async def _restart(bot: commands.Bot, event_id: str) -> None:
    pod_launch.cancel_release(bot, event_id)
    await asyncio.to_thread(_wipe_roster_sync, event_id)


LEVERS: dict[str, Lever] = {
    "player": Lever("Player", "\u2795", discord.ButtonStyle.success, 0, _add_yes),
    "eight": Lever("Add 8p", "\u2795", discord.ButtonStyle.success, 0, _add_eight),
    "maybe": Lever("Maybe", "\U0001f937", discord.ButtonStyle.secondary, 0, _add_maybe),
    "decline": Lever("Decline One", "\u274c", discord.ButtonStyle.secondary, 0, _decline_one),
    "confirm": Lever("Confirm One", "\u2705", discord.ButtonStyle.success, 1, _confirm_one),
    "confirmall": Lever("Confirm All", "\u2705", discord.ButtonStyle.success, 1, _confirm_all),
    "unconfirm": Lever("Take One Back", "\u2611\ufe0f", discord.ButtonStyle.secondary, 1, _take_one_back),
    "hold": Lever("Hold Now", "\u23f1\ufe0f", discord.ButtonStyle.primary, 2, _hold_now, False),
    "release": Lever("Open Tables", "\U0001f680", discord.ButtonStyle.primary, 2, _open_tables, False),
    "restart": Lever("Restart", "\U0001f504", discord.ButtonStyle.danger, 2, _restart),
}


async def _panel_body(event_id: str) -> str:
    """What the levers currently add up to, so the panel says the same thing the card above it draws."""
    attendance = await asyncio.to_thread(attendance_for_event_sync, event_id)
    plan = seating_plan(attendance)
    tables = " + ".join(str(table.seated) for table in plan.tables) or "nothing yet"
    waiting = f", {plan.waiting} waiting" if plan.waiting else ""
    return (
        f"🧪 **Sandbox** — {len(attendance.confirmed)} confirmed, {len(attendance.yes)} pending, "
        f"{len(attendance.maybe)} maybe, {len(attendance.declined)} declined\n"
        f"Opening **{tables}**{waiting}"
    )


async def _seat_rsvp(event_id: str, seat: int, rsvp: str) -> None:
    card = await asyncio.to_thread(pod_launch.scheduled_card_ref_sync, event_id)
    if card is None:
        return
    await asyncio.to_thread(
        pod_launch.set_rsvp_sync, card[2], _seat_id(seat), _seat_name(seat), rsvp,
    )


def _seat_id(seat: int) -> str:
    return f"{SEED_PREFIX}{seat}"


def _seat_name(seat: int) -> str:
    """A hall of famer per seat, numbered once the hall runs out."""
    name = HALL_OF_FAME[seat % len(HALL_OF_FAME)]
    return name if seat < len(HALL_OF_FAME) else f"{name} {seat}"


def _seat_of(signup: Signup) -> int:
    return int(signup.discord_id.removeprefix(SEED_PREFIX)) if _is_seed(signup.discord_id) else 0


def _is_seed(discord_id: str) -> bool:
    return discord_id.startswith(SEED_PREFIX) and discord_id.removeprefix(SEED_PREFIX).isdigit()


def _seats_taken_sync(event_id: str) -> int:
    """How many seats the sandbox has handed out, declines included, so the next add gets a fresh one."""
    with SessionLocal() as session:
        signal = session.execute(
            select(PodSignal).where(PodSignal.event_id == event_id)
        ).scalar_one_or_none()
        if signal is None:
            return 0
        rows = session.execute(
            select(PodSignalMember.discord_user_id).where(PodSignalMember.signal_id == signal.id)
        ).all()
    seats = [int(row[0].removeprefix(SEED_PREFIX)) for row in rows if _is_seed(row[0])]
    return max(seats) + 1 if seats else 0


def _wipe_roster_sync(event_id: str) -> None:
    """Take every signup off the pod and put its clock back, which is a fresh sandbox in everything but
    the thread it is already sitting in."""
    with SessionLocal() as session:
        signal = session.execute(
            select(PodSignal).where(PodSignal.event_id == event_id)
        ).scalar_one_or_none()
        if signal is not None:
            session.execute(
                delete(PodSignalMember).where(PodSignalMember.signal_id == signal.id)
            )
        event = session.get(PodDraftEvent, event_id)
        if event is not None:
            event.event_time = datetime.now(timezone.utc) + timedelta(minutes=SANDBOX_LEAD_MIN)
            event.socket_status = "pending"
        session.commit()
    pod_launch.forget_hold(event_id)


def _bring_forward_sync(event_id: str) -> None:
    """Move the pod to ten minutes out, which is the clock the hold reads."""
    with SessionLocal() as session:
        event = session.get(PodDraftEvent, event_id)
        if event is not None:
            event.event_time = datetime.now(timezone.utc) + timedelta(minutes=10)
            session.commit()


async def _pod_thread(bot: commands.Bot, event_id: str) -> "discord.Thread | None":
    thread_id = await asyncio.to_thread(load_event_thread_id_sync, event_id)
    if not thread_id or thread_id == "pending":
        return None
    thread = bot.get_channel(int(thread_id))
    return thread if isinstance(thread, discord.Thread) else None
