"""`/pod-schedule` — the calendar of which formats the pods draft over the weeks ahead.

The grid ships as a rendered PNG (`pod_schedule_image`); everything a reader might want to select, click or
localize stays text. Components V2 rather than an embed, because an embed pins its image to the bottom and
the set-release note reads as a caption under the calendar it annotates.

The slot line reads off the poll buckets and answers with each slot's next start, so a call after midnight
names today's pods without the reader converting anything out of ET.
"""
from __future__ import annotations

import asyncio
import io
from datetime import date, datetime

import discord
from discord import app_commands
from discord.ext import commands

from bot import audit
from bot.commands import descriptions as desc
from bot.discord_helpers import EM_SPACE, NBSP, posts_publicly
from bot.services import championship
from bot.services import pod_format_interest as fi
from bot.services.ping_roles import SET_CHAMPION_ROLE_NAME
from bot.services.pod_format import is_custom
from bot.services.pod_format_schedule import calendar_days, extras_on, latest_on, rotation_in
from bot.services.pod_roles import role_mention
from bot.services.pod_schedule import SCHEDULE_TZ
from bot.services.pod_schedule_image import render_calendar_png
from bot.services.pod_signals import WEEKDAY_BUCKETS, is_weekend, next_lane_start
from bot.sets import active_set_code, release_instant, set_name_for

MSG_TITLE = "### 🗓️ Pod Format Schedule"
MSG_SLOT = "{emoji} {role} **<t:{unix}:t>**"
MSG_DAILY_SET = "{symbol} {role} **every day**"
MSG_EXTRA_FORMAT = "{symbol} {role} **{days}**"
MSG_EXTRA_FORMAT_ANY_DAY = "{symbol} {role}"
DAYS_WEEKDAY = "Mon-Fri"
DAYS_WEEKEND = "Weekends"
MSG_CHAMPIONSHIP = "👑 {role} <t:{unix}:R>"
MSG_ARRIVAL = "{symbol} **{name}** <t:{unix}:R>"

IMAGE_FILENAME = "pod-schedule.png"
IMAGE_URL = f"attachment://{IMAGE_FILENAME}"
DEFAULT_WEEKS = 4
COLUMN_GAP = EM_SPACE * 2
CAPTION_GAP = NBSP * 2


class PodSchedule(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="pod-schedule", description=desc.POD_SCHEDULE)
    @app_commands.describe(weeks="How many weeks to show")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def pod_schedule(
        self, interaction: discord.Interaction, weeks: app_commands.Range[int, 1, 6] = DEFAULT_WEEKS,
    ) -> None:
        now = datetime.now(SCHEDULE_TZ)
        audit.event("pod_schedule_invoked", user_id=str(interaction.user.id), weeks=weeks)
        plan = championship.plan_for(now)
        crown = plan.event_at if plan is not None else None
        png = await asyncio.to_thread(render_calendar_png, now.date(), weeks, crown.date() if crown else None)
        await interaction.response.send_message(
            view=build_schedule_view(interaction.guild, now, weeks, crown),
            file=discord.File(io.BytesIO(png), IMAGE_FILENAME),
            allowed_mentions=discord.AllowedMentions.none(),
            ephemeral=not posts_publicly(interaction),
        )


def build_schedule_view(guild: discord.Guild | None, now: datetime, weeks: int,
                        championship_at: datetime | None) -> discord.ui.LayoutView:
    days = calendar_days(now.date(), weeks)
    container = discord.ui.Container(accent_color=discord.Color.green())
    container.add_item(discord.ui.TextDisplay(MSG_TITLE))
    container.add_item(discord.ui.TextDisplay(slot_line(guild, now)))
    container.add_item(discord.ui.TextDisplay(daily_set_line(guild)))
    extras = extras_line(guild, days, now.date())
    if extras:
        container.add_item(discord.ui.TextDisplay(extras))
    container.add_item(discord.ui.MediaGallery(discord.MediaGalleryItem(media=IMAGE_URL)))
    marked = marked_days_line(guild, days, championship_at)
    if marked:
        container.add_item(discord.ui.TextDisplay(marked))
    view = discord.ui.LayoutView()
    view.add_item(container)
    return view


def slot_line(guild: discord.Guild | None, now: datetime) -> str:
    """Both slots on one row, each naming the role to hold and when it next drafts. The weekday roles carry
    the line: a reader wants the role to pick up, and the weekend variants are the launcher's bookkeeping."""
    slots = []
    for bucket in WEEKDAY_BUCKETS:
        start = next_lane_start(bucket.lane, now)
        if start is None:
            continue
        slots.append(MSG_SLOT.format(
            emoji=bucket.emoji, role=role_mention(guild, bucket.role_name), unix=int(start.timestamp()),
        ))
    return COLUMN_GAP.join(slots)


def daily_set_line(guild: discord.Guild | None) -> str:
    """The set every pod drafts, named by its ping role rather than by code, which keeps the line true across
    a rotation and lets the days after one stay blank on the calendar."""
    code = active_set_code()
    return MSG_DAILY_SET.format(symbol=fi.format_emoji(code), role=role_mention(guild, fi.LATEST_SET_ROLE_NAME))


def extras_line(guild: discord.Guild | None, days: list[date], today: date) -> str:
    """The formats that run beside the daily set, in the same columns the slots use. Empty until a set cycle
    has days written for them."""
    items = []
    for role_name, symbol, when in scheduled_extras(days, today):
        template = MSG_EXTRA_FORMAT if when else MSG_EXTRA_FORMAT_ANY_DAY
        items.append(template.format(symbol=symbol, role=role_mention(guild, role_name), days=when))
    return COLUMN_GAP.join(items)


def scheduled_extras(days: list[date], today: date) -> list[tuple[str, object, str]]:
    """The flashback and cube roles that have pods still to come in the rendered span, each with the days it
    runs on. A cadence a set cycle has not been written yet, the weeks straight after a rotation, drops off
    the line rather than promising pods no day carries."""
    weekends: dict[str, set[bool]] = {}
    for day in days:
        if day < today:
            continue
        for code in extras_on(day):
            role_name = fi.CUBE_ROLE_NAME if is_custom(code) else fi.FLASHBACK_ROLE_NAME
            weekends.setdefault(role_name, set()).add(is_weekend(day))
    ordered = ((fi.FLASHBACK_ROLE_NAME, fi.flashback_emoji()), (fi.CUBE_ROLE_NAME, fi.cube_emoji()))
    return [
        (role_name, symbol, _days_label(weekends[role_name]))
        for role_name, symbol in ordered if role_name in weekends
    ]


def _days_label(weekends: set[bool]) -> str:
    """Named as the week half a role's pods sit in, and left unnamed once they sit in both, so the label
    never promises a day the table does not carry."""
    if weekends == {False}:
        return DAYS_WEEKDAY
    if weekends == {True}:
        return DAYS_WEEKEND
    return ""


def marked_days_line(guild: discord.Guild | None, days: list[date], championship_at: datetime | None) -> str:
    """Caption for the days the calendar flags, soonest first, in the same two columns the rows above the
    image use. These items run longer, so they take a narrower gap to land under the same column. Empty in
    an ordinary span, where every day is the daily set plus whatever its cell shows."""
    lines = []
    if championship_at is not None and championship_at.date() in days:
        lines.append(MSG_CHAMPIONSHIP.format(
            role=role_mention(guild, SET_CHAMPION_ROLE_NAME), unix=int(championship_at.timestamp()),
        ))
    arrival = rotation_in(days)
    if arrival is not None:
        code = latest_on(arrival)
        lines.append(MSG_ARRIVAL.format(
            symbol=fi.format_emoji(code),
            name=set_name_for(code),
            unix=int(release_instant(arrival).timestamp()),
        ))
    return CAPTION_GAP.join(lines)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PodSchedule(bot))
