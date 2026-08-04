"""Owner-only `!test formatschedule` — render the daily format-schedule output from fixtures.

Routes synthetic events through the same channel selection, pin view, and announcement builders the
daily tick uses, so the per-channel pin and the rotation callouts can be eyeballed without waiting on
the cron or hitting mtgscribe.com. One event per routed channel starts "today" to exercise the
announcement path alongside the pinned schedule.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from discord.ext import commands

from bot.commands.event_scribe import build_schedule_payload
from bot.commands.test_group import test_group
from bot.services import mtgscribe
from bot.services.format_schedule import (
    ANNOUNCE_NONE,
    SCHEDULE_PINS,
    newly_opened,
    previous_window_start,
)
from bot.sets import active_set_code
from bot.tasks.format_schedule_post import announce_groups, announcement_for, select_pin, send_off_embeds


async def setup(bot: commands.Bot) -> None:
    @test_group.command(name="formatschedule")
    @commands.is_owner()
    async def test_format_schedule(ctx: commands.Context) -> None:
        """Owner-only. Render each routed channel's pin and just-opened announcements from fixtures,
        through the same selection and dispatch the tick uses."""
        now = datetime.now(timezone.utc)
        events = _fixture_events(now)
        emojis = {emoji.name: emoji for emoji in await ctx.bot.fetch_application_emojis()}
        since = previous_window_start(now)
        for pin in SCHEDULE_PINS:
            heading = f"#{pin.channel_name}" if pin.channel_name else f"newest in “{pin.category}”"
            await ctx.send(f"__**{heading}**__")
            if pin.maintain_pin:
                in_progress, upcoming, scope = select_pin(events, pin)
                await ctx.send(**build_schedule_payload(in_progress, upcoming, emojis, scope))
            if pin.announce == ANNOUNCE_NONE:
                continue
            groups = announce_groups(events, pin)
            for group in newly_opened(groups, since, now):
                embed, _ = announcement_for(pin, group, groups, emojis)
                await ctx.send(embed=embed)

    @test_group.command(name="sendoff")
    @commands.is_owner()
    async def test_send_off(ctx: commands.Context, set_code: str = "") -> None:
        """Owner-only. Post the set send-off boards (overall + Premier/Trad/Direct/LCQ) in this channel,
        the same embeds the rotation tick posts before archiving. Defaults to the active set; pass a
        code to preview another set's boards."""
        code = (set_code or active_set_code()).upper()
        embeds = await asyncio.to_thread(send_off_embeds, code)
        if not embeds:
            await ctx.send(f"No send-off boards for {code} — set not in the database or no scored players.")
            return
        for embed in embeds:
            await ctx.send(embed=embed)


def _fixture_events(now: datetime) -> list:
    return [
        _flashback("Aetherdrift", now, 0, 7),
        _flashback("Bloomburrow", now, 7, 14),
        _quick_draft("Wilds of Eldraine", now, 0, 7),
        _quick_draft("Outlaws of Thunder Junction", now, 7, 14),
        _cube("Arena Powered Cube", now, 0, 6),
        _sealed("Marvel Super Heroes", now, 0, 30),
        _sealed("Marvel Super Heroes", now, 32, 60),
        _acq_play_in("Bo1", now, 0, 1),
        _acq_play_in("Bo3", now, 0, 1),
        _acq_weekend(now, 0, 3),
        _acq_weekend(now, 21, 24),
    ]


def _flashback(set_name: str, now: datetime, start_off: float, end_off: float) -> mtgscribe.ScribeEvent:
    return _event(f"Premier Draft: {set_name}", "Premier Draft", set_name,
                  ("arena", "limited", "flashback", "premier-draft"), now, start_off, end_off)


def _quick_draft(set_name: str, now: datetime, start_off: float, end_off: float) -> mtgscribe.ScribeEvent:
    return _event(f"Quick Draft: {set_name}", "Quick Draft", set_name,
                  ("arena", "limited", "quick-draft"), now, start_off, end_off)


def _cube(set_name: str, now: datetime, start_off: float, end_off: float) -> mtgscribe.ScribeEvent:
    return _event(f"Premier Draft: {set_name}", "Premier Draft", set_name,
                  ("arena", "limited", "premier-draft", "cube"), now, start_off, end_off)


def _sealed(set_name: str, now: datetime, start_off: float, end_off: float) -> mtgscribe.ScribeEvent:
    return _event(f"Sealed: {set_name}", "Sealed", set_name,
                  ("arena", "limited", "sealed"), now, start_off, end_off)


def _acq_play_in(best_of: str, now: datetime, start_off: float, end_off: float) -> mtgscribe.ScribeEvent:
    return _event(f"ACQ Play-In: Marvel Super Heroes Sealed {best_of}", "ACQ Play-In",
                  f"Marvel Super Heroes Sealed {best_of}",
                  ("arena", "limited", "marvel-super-heroes", "play-in", "qualifier", "sealed"),
                  now, start_off, end_off)


def _acq_weekend(now: datetime, start_off: float, end_off: float) -> mtgscribe.ScribeEvent:
    return _event("Arena Championship Qualifier Weekend: Sealed Marvel Super Heroes",
                  "Arena Championship Qualifier Weekend", "Sealed Marvel Super Heroes",
                  ("arena", "limited", "marvel-super-heroes", "qualifier", "sealed"),
                  now, start_off, end_off)


def _event(title: str, format_label: str, group_label: str, tag_slugs: tuple,
           now: datetime, start_off: float, end_off: float) -> mtgscribe.ScribeEvent:
    start = now + timedelta(days=start_off)
    end = now + timedelta(days=end_off)
    return mtgscribe.ScribeEvent(
        title=title,
        format_label=format_label,
        group_label=group_label,
        start=start,
        end=end,
        start_local=start.replace(tzinfo=None),
        end_local=end.replace(tzinfo=None),
        tag_slugs=tag_slugs,
    )
