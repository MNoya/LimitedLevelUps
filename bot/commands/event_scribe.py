from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands
from discord.utils import format_dt

from bot import audit
from bot.commands import descriptions as desc
from bot.discord_helpers import NBSP, posts_publicly
from bot.services import mtgscribe
from bot.services.scribe_formats import short_format
from bot.sets import ALL_SETS

logger = logging.getLogger(__name__)

LOOKBACK = timedelta(days=90)
UPCOMING_HORIZON = timedelta(days=45)

IN_PROGRESS_EMOJI = "⚡"
COMING_UP_EMOJI = "🗓️"
FLASHBACK_HEADING = "🪦 Flashback"
QUICK_DRAFT_HEADING = "🤖 Quick Draft"

MTGA_EMOJI_NAME = "mtga"
CUBE_LIST_URLS: dict[str, str] = {"Arena Powered Cube": "https://cubecobra.com/cube/about/mtgapc"}

LINE_MAX_WIDTH = 50
SAFE_STARTS_WIDTH = 44
TREE_PREFIX_WIDTH = 4
TIMESTAMP_TOKEN = re.compile(r"<t:(\d+):[a-zA-Z]>")
CUSTOM_EMOJI_TOKEN = re.compile(r"<a?:\w+:\d+>")
BEST_OF_TOKEN = re.compile(r"\bBo\d\b")
LEADING_ARTICLES = {"the", "a", "an"}

ARENA_DIRECT_TAG = "arena-direct"
MIDWEEK_TAG = "midweek-magic"
PREMIER_FORMATS = ("Premier Draft", "Contender Draft")
BOOSTER_LABELS = {"play-boosters": "Play", "collector-booster": "Collector"}
PACKAGE_EMOJI = "📦"
COLLECTOR_EMOJI_NAME = "8000gems"
ARENA_CHAMP_TEXT = "Arena Championship"
ARENA_CHAMP_EMOJI_NAME = "arenachamp"

SCRIBE_EMOJI_NAME = "scribe"
SCRIBE_URL = "https://mtgscribe.com/events/"


class EventScribe(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="event-scribe", description=desc.EVENT_SCRIBE)
    @app_commands.describe(format="Only show this format family", set="Only show this set")
    @app_commands.choices(format=[
        app_commands.Choice(name="Premier", value="premier"),
        app_commands.Choice(name="Quick", value="quick"),
        app_commands.Choice(name="Flashback", value="flashback"),
        app_commands.Choice(name="Draft (all draft formats)", value="draft"),
        app_commands.Choice(name="Sealed (incl. Arena Direct)", value="sealed"),
        app_commands.Choice(name="Midweek", value="midweek"),
        app_commands.Choice(name="Competitive (play-in, qualifiers)", value="competitive"),
    ])
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def event_scribe(self, interaction: discord.Interaction,
                           format: app_commands.Choice[str] | None = None,
                           set: str | None = None) -> None:
        await interaction.response.defer(ephemeral=not posts_publicly(interaction))
        start_date = date.today() - LOOKBACK
        selected = format.value if format else None
        try:
            events = await asyncio.to_thread(mtgscribe.fetch_events, start_date)
        except Exception:
            logger.exception(f"event-scribe fetch failed for start_date={start_date}")
            await interaction.followup.send("MTG Scribe events are unavailable right now. Try again later.")
            return
        in_progress, upcoming = process_events(events, selected, set)
        emojis = {emoji.name: emoji for emoji in await self.bot.fetch_application_emojis()}
        audit.event(
            "event_scribe_invoked",
            user_id=str(interaction.user.id),
            format=selected or "all",
            set=set or "all",
            in_progress=len(in_progress),
            upcoming=len(upcoming),
        )
        scope = _heading_scope(set, selected)
        await interaction.followup.send(**build_schedule_payload(in_progress, upcoming, emojis, scope))

    @event_scribe.autocomplete("set")
    async def event_scribe_set_autocomplete(
        self, interaction: discord.Interaction, current: str,
    ) -> list[app_commands.Choice[str]]:
        lowered = current.lower()
        matches = [app_commands.Choice(name=seed.name, value=seed.name)
                   for seed in ALL_SETS if lowered in seed.name.lower()]
        return matches[:25]


def select_groups(events: list, filters: list | None, set_query: str | None = None,
                  *, apply_horizon: bool) -> tuple[list, list]:
    """Run the event-scribe pipeline for an OR'd set of format filters, or the unfiltered Limited view
    when ``filters`` is falsy: normalize → scope → filter → group → partition. ``apply_horizon`` drops
    upcoming groups past ``UPCOMING_HORIZON`` — the command keeps everything an explicit filter matches,
    the daily schedule tick always trims."""
    normalized = [normalize_event(event) for event in events]
    kept = [event for event in normalized
            if _scope_matches(event, filters) and _format_matches(event, filters)
            and _passes_set(event, set_query)]
    groups = mtgscribe.group_events(kept)
    now = datetime.now(timezone.utc)
    in_progress, upcoming = mtgscribe.partition_by_now(groups, now)
    if apply_horizon:
        horizon = now + UPCOMING_HORIZON
        upcoming = [group for group in upcoming if group.start <= horizon]
    return in_progress, upcoming


def process_events(events: list, selected: str | None = None, set_query: str | None = None) -> tuple[list, list]:
    """The shared /event-scribe + `!test scribe` entry: a single optional filter, with the horizon
    trim applied only to the fully unfiltered view."""
    filters = [selected] if selected else None
    apply_horizon = selected is None and set_query is None
    return select_groups(events, filters, set_query, apply_horizon=apply_horizon)


def _scope_matches(event: mtgscribe.ScribeEvent, filters: list | None) -> bool:
    if not filters:
        return _in_scope(event, None)
    return any(_in_scope(event, selected) for selected in filters)


def _format_matches(event: mtgscribe.ScribeEvent, filters: list | None) -> bool:
    if not filters:
        return True
    return any(_passes_format(event, selected) for selected in filters)


def _in_scope(event: mtgscribe.ScribeEvent, selected: str | None) -> bool:
    """The schedule is Limited-only, except the Midweek filter, which surfaces every Midweek
    queue (Brawl, Pauper, Momir included)."""
    if selected == "midweek":
        return True
    return "limited" in event.tag_slugs


def build_schedule_payload(in_progress: list, upcoming: list, emojis: dict, scope: str = "Limited") -> dict:
    return {"view": build_schedule_view(in_progress, upcoming, emojis, scope)}


def build_schedule_view(in_progress: list, upcoming: list, emojis: dict,
                        scope: str = "Limited") -> discord.ui.LayoutView:
    """A Components V2 layout: a divider underlines the title before the schedule body."""
    container = discord.ui.Container(accent_color=discord.Color.green())
    container.add_item(discord.ui.TextDisplay(_title_text(emojis, scope)))
    container.add_item(discord.ui.Separator(visible=True))
    container.add_item(discord.ui.TextDisplay(_schedule_body(in_progress, upcoming, emojis)))
    view = discord.ui.LayoutView()
    view.add_item(container)
    view.add_item(discord.ui.ActionRow(discord.ui.Button(
        style=discord.ButtonStyle.link,
        label="View on MTG Scribe",
        url=SCRIBE_URL,
        emoji=emojis.get(SCRIBE_EMOJI_NAME),
    )))
    return view


def build_announcement(group: mtgscribe.EventGroup, emojis: dict, *, format_word: str,
                       next_group: mtgscribe.EventGroup | None = None) -> discord.Embed:
    """A single rotation callout for the daily schedule tick: a "**<set>** <format> is live!" heading
    over the availability window, with the set logo as the embed thumbnail. ``format_word`` is the
    rotation type ("Flashback", "Quick Draft", …); empty for self-naming sets like a cube. When
    ``next_group`` is set, a "Next Up" line previews the rotation already scheduled after this one."""
    suffix = f" {format_word}" if format_word else ""
    lines = [
        f"### **{group.label}**{suffix} is live!",
        f"Ends {group.end_local:%B %-d} ({format_dt(group.end, 'R')})",
    ]
    if next_group is not None:
        lines.append(f"\n**Next Up:** {_set_emoji_prefix(next_group, emojis)}{next_group.label}")
    cube_url = _cube_list_url(group)
    if cube_url is not None:
        lines.append(f"<{cube_url}>")
    embed = discord.Embed(description="\n".join(lines), color=discord.Color.green())
    emoji = _set_emoji(group, emojis)
    if emoji is not None:
        embed.set_thumbnail(url=emoji.url)
    return embed


def _cube_list_url(group: mtgscribe.EventGroup) -> str | None:
    """The cube's decklist URL, or ``None`` for a non-cube event or a cube without a known list.

    Keyed on the cube variant the schedule names ("Arena Powered Cube", "Planar Cube") — every
    variant shares the one CUBE seed, so the seed cannot tell them apart.
    """
    if not group.cube:
        return None
    lowered = group.label.lower()
    for variant, url in CUBE_LIST_URLS.items():
        if variant.lower() in lowered:
            return url
    return None


def build_competitive_reminder(group: mtgscribe.EventGroup, emojis: dict) -> discord.Embed:
    """A reminder for a competitive event (Qualifier Play-In, ACQ, Arena Championship), distinct from
    the rotation announcements: the event type heads it, the full Sealed/Bo format and closing date
    follow. Limited-scoped competitive events are Sealed (the Constructed ones fall out of scope)."""
    event_type, best_of = _competitive_parts(group)
    heading_type = _competitive_heading_type(event_type, emojis)
    best_of_suffix = f" {best_of}" if best_of else ""
    seed = _seed_for_label(group.label)
    set_code = seed.code if seed else group.label
    lines = [
        f"### {heading_type} is now open",
        f"Format: **{set_code} Sealed{best_of_suffix}**",
        f"\nEnds {group.end_local:%B %-d} ({format_dt(group.end, 'R')})",
    ]
    embed = discord.Embed(description="\n".join(lines), color=discord.Color.green())
    emoji = _set_emoji(group, emojis)
    if emoji is not None:
        embed.set_thumbnail(url=emoji.url)
    return embed


def _competitive_parts(group: mtgscribe.EventGroup) -> tuple[str, str]:
    """Split a competitive group's format into the event type and its best-of(s): "Qualifier Play-In
    Bo3" → ("Qualifier Play-In", "Bo3"). Bo1 and Bo3 queues sharing a window collapse to "Bo1/Bo3"."""
    best_ofs: list[str] = []
    event_type = ""
    for fmt in group.formats:
        for token in BEST_OF_TOKEN.findall(fmt):
            if token not in best_ofs:
                best_ofs.append(token)
        if not event_type:
            event_type = BEST_OF_TOKEN.sub("", fmt).strip()
    return event_type or "Competitive event", "/".join(best_ofs)


def _competitive_heading_type(event_type: str, emojis: dict) -> str:
    """The event type as it leads the reminder heading. An Arena Championship event swaps the literal
    "Arena Championship" for its :arenachamp: emoji and drops the generic mtga lead; everything else
    keeps the mtga lead."""
    if ARENA_CHAMP_TEXT in event_type:
        return _decorate_arena_champ(event_type, emojis)
    mtga = emojis.get(MTGA_EMOJI_NAME)
    return f"{mtga} {event_type}" if mtga else event_type


def schedule_title_marker(scope: str) -> str:
    """The stable text inside a schedule title, used to recognise an already-pinned schedule on edit."""
    return f"{scope} Event Schedule"


def _title_text(emojis: dict, scope: str) -> str:
    mtga = emojis.get(MTGA_EMOJI_NAME)
    scribe = emojis.get(SCRIBE_EMOJI_NAME)
    lead = f"{mtga} " if mtga else ""
    mark = f" {scribe}" if scribe else ""
    return f"## {lead}{schedule_title_marker(scope)}{mark}"


def _schedule_body(in_progress: list, upcoming: list, emojis: dict) -> str:
    sections: list[str] = []
    if in_progress:
        sections.append(f"### {IN_PROGRESS_EMOJI} In Progress")
        sections.extend(_section_blocks(in_progress, emojis, upcoming=False))
    if upcoming:
        sections.append(f"### {COMING_UP_EMOJI} Coming Up")
        sections.extend(_section_blocks(upcoming, emojis, upcoming=True))
    if not sections:
        return "No Limited events right now."
    return "\n".join(sections)


def _section_blocks(groups: list, emojis: dict, *, upcoming: bool) -> list:
    """One block per set, plus a collapsed roster for formats that rotate one-set-per-window —
    Flashback reruns and (upcoming only) Quick Draft. Those would otherwise scatter a header per set,
    so they fold into a single "<format>" block listing each set."""
    rosters: dict[str, list] = {}
    standalone: list = []
    for group in groups:
        heading = _roster_heading(group, upcoming=upcoming)
        if heading:
            rosters.setdefault(heading, []).append(group)
        else:
            standalone.append(group)
    blocks = [_set_block(label, windows, emojis, upcoming=upcoming)
              for label, windows in _by_set(standalone).items()]
    blocks.extend(_roster_block(heading, members, emojis, upcoming=upcoming)
                  for heading, members in rosters.items())
    return blocks


def _roster_heading(group: mtgscribe.EventGroup, *, upcoming: bool) -> str | None:
    if group.flashback:
        return FLASHBACK_HEADING
    if upcoming and group.formats == ["Quick Draft"]:
        return QUICK_DRAFT_HEADING
    return None


def _by_set(groups: list) -> dict:
    """Collapse same-set windows under one header; insertion order keeps sets start-sorted."""
    ordered: dict[str, list] = {}
    for group in groups:
        ordered.setdefault(group.label, []).append(group)
    return ordered


def _roster_block(heading: str, members: list, emojis: dict, *, upcoming: bool) -> str:
    members = sorted(members, key=lambda group: group.start)
    lines = [f"**{heading}**"]
    for index, group in enumerate(members):
        corner = "└" if index == len(members) - 1 else "├"
        lines.append(f"{NBSP}{corner}{NBSP}{NBSP}{_roster_line(group, emojis, upcoming=upcoming)}")
    return "\n".join(lines)


def _roster_line(group: mtgscribe.EventGroup, emojis: dict, *, upcoming: bool) -> str:
    prefix = _set_emoji_prefix(group, emojis)
    name = _fit_set_name(group, prefix, _timing(group, upcoming=upcoming, compact=True))
    lead = f"{prefix}{name} · "
    return f"{lead}{_fit_timing(group, _estimate_cols(lead), upcoming=upcoming)}"


def _fit_set_name(group: mtgscribe.EventGroup, emoji_prefix: str, timing: str) -> str:
    """Keep a roster line from wrapping: prefer the full set name, fall back to the name with its colon
    subtitle and any leading article dropped, then to the set code as a last resort. "Duskmourn: House
    of Horror" trims to "Duskmourn"; "The Lost Caverns of Ixalan" trims to a name that still wraps, so
    it collapses to "LCI"."""
    name = group.label
    if not _would_wrap(emoji_prefix, name, timing):
        return name
    trimmed = _trim_set_name(name)
    if trimmed != name and not _would_wrap(emoji_prefix, trimmed, timing):
        return trimmed
    seed = _seed_for_label(name)
    return seed.code if seed else trimmed


def _trim_set_name(name: str) -> str:
    head = name.split(":", 1)[0].strip()
    words = head.split()
    if len(words) > 1 and words[0].lower() in LEADING_ARTICLES:
        words = words[1:]
    return " ".join(words)


def _would_wrap(emoji_prefix: str, name: str, timing: str) -> bool:
    return _estimate_cols(f"{emoji_prefix}{name} · {timing}") > LINE_MAX_WIDTH


def _text_cols(text: str) -> int:
    """Estimated rendered width of a fragment. A ``<t::R>`` token renders as its current relative
    phrase (the widest it will be, since a countdown only shrinks as the event nears), and a custom
    emoji renders ~2 columns."""
    text = TIMESTAMP_TOKEN.sub(lambda match: _countdown_phrase(int(match.group(1))), text)
    text = CUSTOM_EMOJI_TOKEN.sub("xx", text)
    return len(text)


def _countdown_phrase(unix: int) -> str:
    """Approximate Discord's ``:R`` rendering of a timestamp, for width estimation only."""
    delta = unix - datetime.now(timezone.utc).timestamp()
    seconds = abs(delta)
    if seconds < 3600:
        count, unit, article = round(seconds / 60), "minute", "a"
    elif seconds < 86400:
        count, unit, article = round(seconds / 3600), "hour", "an"
    elif seconds < 2629800:
        count, unit, article = round(seconds / 86400), "day", "a"
    elif seconds < 31557600:
        count, unit, article = round(seconds / 2629800), "month", "a"
    else:
        count, unit, article = round(seconds / 31557600), "year", "a"
    count = max(1, count)
    phrase = f"{article} {unit}" if count == 1 else f"{count} {unit}s"
    return f"in {phrase}" if delta >= 0 else f"{phrase} ago"


def _estimate_cols(text: str) -> int:
    return TREE_PREFIX_WIDTH + _text_cols(text)


def _set_block(label: str, windows: list, emojis: dict, *, upcoming: bool) -> str:
    items = [_format_line(group, emojis, upcoming=upcoming) for group in _by_format(windows)]
    lines = [f"{_set_emoji_prefix(windows[0], emojis)}**{label}**"]
    for index, item in enumerate(items):
        corner = "└" if index == len(items) - 1 else "├"
        lines.append(f"{NBSP}{corner}{NBSP}{NBSP}{item}")
    return "\n".join(lines)


def _by_format(windows: list) -> list:
    """Collapse same-format windows (e.g. several Arena Direct Play) onto one line."""
    grouped: dict[str, list] = {}
    for window in windows:
        grouped.setdefault(_format_label(window), []).append(window)
    return list(grouped.values())


def _format_line(windows: list, emojis: dict, *, upcoming: bool) -> str:
    """Render one format's line content. When a format recurs across several windows, only the
    soonest is shown, with its countdown. The Arena Direct product word is dropped in favour of its
    booster emoji, and an overflowing Midweek line shortens its prefix to ``MWM``."""
    first = windows[0]
    label = _decorate_arena_champ(_format_label(first), emojis).replace("Traditional", "Trad")
    suffix = _booster_emoji_suffix(first, emojis)
    if suffix:
        label = "Arena Direct"
    if label.startswith("Midweek") and _midweek_overflows(label, first, upcoming=upcoming):
        label = label.replace("Midweek", "MWM", 1)
    lead = _lead(label, suffix)
    return f"{lead}{_fit_timing(first, _estimate_cols(lead), upcoming=upcoming)}"


def _lead(label: str, suffix: str) -> str:
    if not label:
        return ""
    if suffix:
        return f"{label}{suffix} "
    return f"{label} · "


def _midweek_overflows(label: str, group: mtgscribe.EventGroup, *, upcoming: bool) -> bool:
    compact = _timing(group, upcoming=upcoming, compact=True)
    return _estimate_cols(f"{label} · ") + _text_cols(compact) > LINE_MAX_WIDTH


def _timing(group: mtgscribe.EventGroup, *, upcoming: bool, compact: bool = False) -> str:
    if upcoming:
        window = _date_range(group.start_local, group.end_local)
        countdown = format_dt(group.start, "R")
        if compact:
            return f"{window} · {countdown}"
        return f"{window} · starts {countdown}"
    countdown = format_dt(group.end, "R")
    if compact:
        return f"ends {countdown}"
    return f"ends {group.end_local:%B %-d} {countdown}"


def _fit_timing(group: mtgscribe.EventGroup, lead_cols: int, *, upcoming: bool) -> str:
    """The timing tail for an event line, trimmed to fit. Upcoming: keep ``starts`` only while the
    whole line stays well clear of the wrap point, then drop it, then drop the date range. Competitive
    events invert that — their short window is the point, so the range is kept and the countdown is
    dropped instead. In progress: drop the explicit end date (keeping ``ends {countdown}``) on overflow."""
    if upcoming:
        with_range = _timing(group, upcoming=True, compact=True)
        if group.competitive:
            if lead_cols + _text_cols(with_range) <= LINE_MAX_WIDTH:
                return with_range
            return _date_range(group.start_local, group.end_local)
        with_starts = _timing(group, upcoming=True, compact=False)
        if lead_cols + _text_cols(with_starts) <= SAFE_STARTS_WIDTH:
            return with_starts
        if lead_cols + _text_cols(with_range) <= LINE_MAX_WIDTH:
            return with_range
        return format_dt(group.start, "R")
    full = _timing(group, upcoming=False, compact=False)
    if lead_cols + _text_cols(full) <= LINE_MAX_WIDTH:
        return full
    return _timing(group, upcoming=False, compact=True)


def _decorate_arena_champ(formats: str, emojis: dict) -> str:
    emoji = emojis.get(ARENA_CHAMP_EMOJI_NAME)
    return formats.replace(ARENA_CHAMP_TEXT, str(emoji)) if emoji else formats


def _booster_emoji_suffix(group: mtgscribe.EventGroup, emojis: dict) -> str:
    joined = " ".join(group.formats)
    if "Arena Direct Play" in joined:
        return f" {PACKAGE_EMOJI}"
    if "Arena Direct Collector" in joined:
        emoji = emojis.get(COLLECTOR_EMOJI_NAME)
        return f" {emoji}" if emoji else ""
    return ""


FORMAT_PRIORITY = {"Premier Draft": 0, "Traditional Draft": 1, "Pick Two": 2, "Pick 2 Draft": 2, "Quick Draft": 3}


def _format_label(group: mtgscribe.EventGroup) -> str:
    if not group.formats:
        return ""
    if len(group.formats) == 1:
        return group.formats[0]
    if len(group.formats) > 3:
        ranked = sorted(group.formats, key=lambda label: FORMAT_PRIORITY.get(label, 99))
        names = [short_format(label).removesuffix(" Draft") for label in ranked[:2]]
        return f"{', '.join(names)} and others"
    return _join_formats(group.formats)


def _join_formats(formats: list) -> str:
    joined = ", ".join(short_format(label) for label in formats)
    return joined if "Draft" in joined else f"{joined} Draft"


def _date_range(start: datetime, end: datetime) -> str:
    if (start.year, start.month) == (end.year, end.month):
        return f"{start:%B %-d}–{end:%-d}"
    return f"{start:%b %-d}–{end:%b %-d}"


def _set_emoji_prefix(group: mtgscribe.EventGroup, emojis: dict) -> str:
    emoji = _set_emoji(group, emojis)
    return f"{emoji} " if emoji else ""


def _set_emoji(group: mtgscribe.EventGroup, emojis: dict):
    code = _emoji_code(group)
    return emojis.get(code.lower()) if code else None


def _emoji_code(group: mtgscribe.EventGroup) -> str | None:
    if group.cube:
        return "CUBE"
    seed = _seed_for_label(group.label)
    return seed.code if seed else None


def _clean_set_label(label: str) -> str:
    """Collapse a set name buried in qualifier words (e.g. "Sealed Marvel Super Heroes Bo3") to
    the bare set, so every queue for a set groups under one header."""
    seed = _seed_for_label(label)
    return seed.name if seed else label


def _seed_for_label(label: str):
    """Match either way: a queue label may carry the full set name ("Secrets of Strixhaven") or, on
    flashback/quick reruns, just the short name Arena uses ("Duskmourn" for "Duskmourn: House of
    Horror"), which is a substring of the seed name rather than a superstring of it."""
    lowered = label.lower()
    for seed in ALL_SETS:
        name = seed.name.lower()
        if name in lowered or lowered in name:
            return seed
    return None


def _passes_format(event: mtgscribe.ScribeEvent, selected: str | None) -> bool:
    if selected is None:
        return True
    if selected == "premier":
        return event.format_label in PREMIER_FORMATS
    if selected == "quick":
        return event.format_label == "Quick Draft"
    if selected == "flashback":
        return mtgscribe.FLASHBACK_TAG in event.tag_slugs
    if selected == "draft":
        return any("draft" in tag for tag in event.tag_slugs)
    if selected == "sealed":
        return any(tag in ("sealed", "traditional-sealed") for tag in event.tag_slugs)
    if selected == "cube":
        return any(mtgscribe.CUBE_TAG in tag for tag in event.tag_slugs)
    if selected == "midweek":
        return MIDWEEK_TAG in event.tag_slugs
    if selected == "competitive":
        return _is_competitive(event.tag_slugs)
    return True


def _is_competitive(tag_slugs: tuple) -> bool:
    return any(tag in tag_slugs for tag in mtgscribe.COMPETITIVE_TAGS)


def _passes_set(event: mtgscribe.ScribeEvent, set_query: str | None) -> bool:
    return not set_query or set_query.lower() in event.group_label.lower()


FORMAT_TITLES = {
    "premier": "Premier Draft",
    "quick": "Quick Draft",
    "flashback": "Flashback",
    "draft": "Draft",
    "sealed": "Sealed",
    "midweek": "Midweek",
    "competitive": "Competitive",
}


def _heading_scope(set_query: str | None, selected: str | None) -> str:
    """The descriptor before "Event Schedule": the set, the format, both, or "Limited" when neither
    is filtered. The Midweek and Competitive filters surface Constructed queues, so the default
    Limited framing only holds when nothing is selected."""
    parts = []
    if set_query:
        parts.append(set_query)
    if selected:
        parts.append(FORMAT_TITLES.get(selected, selected.capitalize()))
    return " ".join(parts) if parts else "Limited"


def normalize_event(event: mtgscribe.ScribeEvent) -> mtgscribe.ScribeEvent:
    """Clean the set label so every queue groups under one header, and fix up the format label for
    event families whose title structure hides it:
    - Arena Direct ("Arena Direct: <set> <product>") → set from tags, product as format.
    - Midweek Magic ("Midweek Magic: <set> <format>") → the real format (Quick Draft, Phantom Sealed).
    - Competitive (play-in / qualifier) → keep the Bo1/Bo3 differentiator from the title.
    """
    if ARENA_DIRECT_TAG in event.tag_slugs:
        set_name = _set_name_from_tags(event.tag_slugs) or _clean_set_label(event.group_label)
        booster = next((label for slug, label in BOOSTER_LABELS.items() if slug in event.tag_slugs), None)
        format_label = f"Arena Direct {booster}" if booster else "Arena Direct"
        return replace(event, group_label=set_name, format_label=format_label)
    if MIDWEEK_TAG in event.tag_slugs:
        return _normalize_midweek(event)
    set_name = _clean_set_label(event.group_label)
    format_label = event.format_label
    if _is_competitive(event.tag_slugs):
        format_label = _with_best_of(format_label, event.title)
    if set_name == event.group_label and format_label == event.format_label:
        return event
    return replace(event, group_label=set_name, format_label=format_label)


def _normalize_midweek(event: mtgscribe.ScribeEvent) -> mtgscribe.ScribeEvent:
    """Set-bearing Midweeks ("Midweek Magic: SoS Phantom Sealed") group under the set, with the format
    kept "Midweek"-prefixed so a Midweek never reads as a regular queue; set-less ones
    ("Midweek Magic: Brawl", crossovers) group under a "Midweek Magic" header."""
    label = event.group_label
    seed = None if "+" in label else _seed_for_label(label)
    if seed:
        leftover = label.replace(seed.name, "").strip()
        format_label = f"Midweek {leftover}" if leftover else "Midweek Magic"
        return replace(event, group_label=seed.name, format_label=format_label)
    return replace(event, group_label="Midweek Magic", format_label=label)


def _with_best_of(format_label: str, title: str) -> str:
    for best_of in ("Bo1", "Bo3"):
        if best_of in title and best_of not in format_label:
            return f"{format_label} {best_of}"
    return format_label


def _set_name_from_tags(tag_slugs: tuple) -> str | None:
    for seed in ALL_SETS:
        if _slugify(seed.name) in tag_slugs:
            return seed.name
    return None


def _slugify(name: str) -> str:
    return name.lower().replace(":", "").replace(" ", "-")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EventScribe(bot))
