"""Owner-only `!test scribe` — render the event schedule from synthetic fixtures.

Runs the real grouping/partition/render path (bot.services.mtgscribe + event_scribe) on
hand-built events, so the layout can be eyeballed without hitting mtgscribe.com. The fixtures
give one set (Secrets of Strixhaven) several formats with mismatched windows on purpose: events
group by (set, start, end), so formats whose dates differ split into separate lines under
repeated set headers rather than merging into one.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from discord.ext import commands

from bot.commands.event_scribe import build_schedule_payload, process_events
from bot.commands.test_group import test_group
from bot.services import mtgscribe


async def setup(bot: commands.Bot) -> None:
    @test_group.command(name="scribe")
    @commands.is_owner()
    async def test_scribe(ctx: commands.Context) -> None:
        """Owner-only. Render the schedule embed from synthetic events through the real pipeline."""
        in_progress, upcoming = process_events(_fixture_events(datetime.now(timezone.utc)))
        emojis = {emoji.name: emoji for emoji in await ctx.bot.fetch_application_emojis()}
        await ctx.send(**build_schedule_payload(in_progress, upcoming, emojis, scope="Marvel Super Heroes"))


def _fixture_events(now: datetime) -> list:
    in_progress = [
        _scribe_event("Premier Draft", "premier-draft", now, -30, 26 / 24),
        _scribe_event("Pick-Two Draft", "pick-2-draft", now, -30, 26 / 24),
        _scribe_event("Traditional Draft", "traditional-draft", now, -30, 26 / 24),
        _scribe_event("Jump In", "jump-in", now, -30, 26 / 24),
        _scribe_event("Sealed", "sealed", now, -10, 5),
        _scribe_event("Quick Draft", "quick-draft", now, -5, 2),
        _arena_direct("Play Boosters", "play-boosters", now, -2, 4),
        _formatless_cube("Planar Cube Draft", now, -12, 9),
    ]
    coming_up = [
        _scribe_event("Premier Draft", "premier-draft", now, 33, 40),
        _scribe_event("Pick-Two Draft", "pick-2-draft", now, 33, 40),
        _scribe_event("Traditional Draft", "traditional-draft", now, 33, 40),
        _scribe_event("Premier Draft", "premier-draft", now, 9, 16),
        _arena_direct("Play Boosters", "play-boosters", now, 3, 6),
        _arena_direct("Play Boosters", "play-boosters", now, 10, 13),
        _arena_direct("Collector Boosters", "collector-booster", now, 5, 8),
        _arena_direct("Collector Boosters", "collector-booster", now, 17, 20),
        _flashback("Aetherdrift", now, 14, 21),
        _flashback("Duskmourn", now, 21, 28),
        _flashback("Bloomburrow", now, 28, 35),
        _quick_draft("Wilds of Eldraine", "quick-draft", now, 4, 11),
        _quick_draft("Outlaws of Thunder Junction", "quck-draft", now, 11, 18),
        _quick_draft("The Lost Caverns of Ixalan", "premier-draft", now, 43, 49),
        _midweek("Secrets of Strixhaven Phantom Sealed", "Phantom Sealed", ("sealed",), now, 6, 8),
        _cube("Some Kind of new Cube", now, 13, 16),
        _arena_open(now, 19, 21),
        _acq("Play-In", "Bo1", now, 20, 21),
        _acq("Play-In", "Bo3", now, 26, 27),
        _acq("Weekend", "", now, 27, 29),
    ]
    return in_progress + coming_up


def _scribe_event(fmt: str, format_tag: str, now: datetime,
                  start_offset_days: float, end_offset_days: float) -> mtgscribe.ScribeEvent:
    return _event(f"{fmt}: Secrets of Strixhaven", fmt, "Secrets of Strixhaven",
                  ("arena", "limited", format_tag, "secrets-of-strixhaven"),
                  now, start_offset_days, end_offset_days)


def _arena_direct(product: str, booster_slug: str, now: datetime,
                  start_off: int, end_off: int) -> mtgscribe.ScribeEvent:
    return _event(f"Arena Direct: Secrets of Strixhaven {product}", "Arena Direct",
                  f"Secrets of Strixhaven {product}",
                  ("arena", "arena-direct", "limited", "sealed", booster_slug, "secrets-of-strixhaven"),
                  now, start_off, end_off)


def _flashback(set_name: str, now: datetime, start_off: int, end_off: int) -> mtgscribe.ScribeEvent:
    return _event(f"Premier Draft: {set_name}", "Premier Draft", set_name,
                  ("arena", "limited", "flashback", "premier-draft"), now, start_off, end_off)


def _quick_draft(set_name: str, format_tag: str, now: datetime,
                 start_off: int, end_off: int) -> mtgscribe.ScribeEvent:
    """``format_tag`` varies on purpose: Scribe mistags Quick Draft often (a ``quck-draft`` typo, or
    ``premier-draft``), and the Quick filter keys on the title format so it survives that."""
    return _event(f"Quick Draft: {set_name}", "Quick Draft", set_name,
                  ("arena", "limited", format_tag), now, start_off, end_off)


def _midweek(label: str, fmt: str, extra_tags: tuple, now: datetime,
             start_off: int, end_off: int) -> mtgscribe.ScribeEvent:
    return _event(f"Midweek Magic: {label}", fmt, label,
                  ("arena", "limited", "midweek-magic", *extra_tags), now, start_off, end_off)


def _cube(set_name: str, now: datetime, start_off: int, end_off: int) -> mtgscribe.ScribeEvent:
    return _event(f"Premier Draft: {set_name}", "Premier Draft", set_name,
                  ("arena", "limited", "premier-draft", "cube"), now, start_off, end_off)


def _formatless_cube(name: str, now: datetime, start_off: int, end_off: int) -> mtgscribe.ScribeEvent:
    """Scribe titles some cube queues with no ``"<format>: "`` prefix, leaving the group no format at all."""
    return _event(name, "", name, ("arena", "cube", "limited", "planar-cube"), now, start_off, end_off)


def _arena_open(now: datetime, start_off: int, end_off: int) -> mtgscribe.ScribeEvent:
    return _event("Arena Open: Secrets of Strixhaven", "Arena Open", "Secrets of Strixhaven",
                  ("arena", "arena-open", "draft", "limited", "secrets-of-strixhaven"),
                  now, start_off, end_off)


def _acq(label: str, best_of: str, now: datetime, start_off: int, end_off: int) -> mtgscribe.ScribeEvent:
    tail = f"{best_of} Secrets of Strixhaven Sealed".strip()
    return _event(f"ACQ {label}: {tail}", f"ACQ {label}", tail,
                  ("arena", "limited", "play-in", "qualifier", "sealed", "secrets-of-strixhaven"),
                  now, start_off, end_off)


def _event(title: str, format_label: str, group_label: str, tag_slugs: tuple,
           now: datetime, start_off: int, end_off: int) -> mtgscribe.ScribeEvent:
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
