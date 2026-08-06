"""Owner-only `!test formatschedule` — render the daily format-schedule output from the real calendar.

Routes the bundled MTG Scribe calendar through the same channel selection, pin view and announcement
builders the daily tick uses, so what posts here is what the tick would post. Synthetic fixtures used
to stand in because the tick fetched mtgscribe.com; the calendar is a committed file now, so the real
one costs nothing and reads like production. `!test scribe` keeps hand-built events for the layout
edge cases a live calendar rarely holds all at once.

The one departure from the tick: announcements are not gated on having opened since the previous
window, since real events almost never open in the minute you run this. Each pin previews the first
few callouts it would make instead.
"""
from __future__ import annotations

import asyncio

from discord.ext import commands

from bot.commands.event_scribe import build_schedule_payload, select_season_groups
from bot.commands.test_group import test_group
from bot.services import mtgscribe
from bot.services.format_schedule import ANNOUNCE_NONE, SCHEDULE_PINS
from bot.sets import active_set_code
from bot.tasks.format_schedule_post import announce_groups, announcement_for, select_pin, send_off_embeds

PREVIEW_ANNOUNCE_LIMIT = 3


async def setup(bot: commands.Bot) -> None:
    @test_group.command(name="formatschedule")
    @commands.is_owner()
    async def test_format_schedule(ctx: commands.Context) -> None:
        """Owner-only. Render each routed channel's pin and its announcements from the real calendar,
        through the same selection and dispatch the tick uses."""
        events = mtgscribe.load_events()
        emojis = {emoji.name: emoji for emoji in await ctx.bot.fetch_application_emojis()}
        for pin in SCHEDULE_PINS:
            heading = f"#{pin.channel_name}" if pin.channel_name else f"active set in “{pin.category}”"
            await ctx.send(f"__**{heading}**__")
            if pin.maintain_pin:
                in_progress, upcoming, scope = select_pin(events, pin)
                await ctx.send(**build_schedule_payload(in_progress, upcoming, emojis, scope))
                if not pin.pin_filters:
                    season = select_season_groups(events, scope)
                    await ctx.send(f"__**{heading} — final week, written once then frozen**__")
                    await ctx.send(**build_schedule_payload(season, [], emojis, scope, archival=True))
            if pin.announce == ANNOUNCE_NONE:
                continue
            groups = announce_groups(events, pin)
            if not groups:
                await ctx.send(f"_nothing for {heading} to announce in the current calendar_")
                continue
            for group in groups[:PREVIEW_ANNOUNCE_LIMIT]:
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
