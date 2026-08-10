"""Channel routing and selection logic for the daily Scribe-driven format-schedule tick.

Pure data/date logic — no Discord, no DB. The APScheduler wiring and Discord I/O live in
bot/tasks/format_schedule_post.py; the rendering builders are reused from bot/commands/event_scribe.

Each pinned schedule is one filtered /event-scribe view living in a community channel (matched by a
name substring). A channel can host more than one: the quick-or-flashback channel carries a separate
Quick Draft pin and Flashback pin. Limited Competitive events route to the active set's channel, matched
by name within the MTG Strategy category, so routing follows the rotation with no config edit.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import bot.services.mtgscribe as mtgscribe
from bot.sets import ALL_SETS, SetSeed, active_set_code

OPEN_TZ = ZoneInfo("America/Los_Angeles")
EVENT_DAY_TZ = ZoneInfo("America/New_York")
ANNOUNCE_WINDOWS: tuple[time, ...] = (time(6, 0), time(8, 0), time(14, 0))
DEDUP_LOOKBACK = timedelta(hours=24)
SET_PIN_FREEZE_LEAD = timedelta(days=7)

PERMANENT_CUBE_CODE = "CUBE"
LATEST_SET_CATEGORY = "MTG Strategy"
FORMAT_ARCHIVE_CATEGORY = "Format Archive"
SET_NAME_STOPWORDS = frozenset({"a", "an", "and", "at", "in", "of", "the"})


ANNOUNCE_NONE = "none"
ANNOUNCE_ROTATION = "rotation"
ANNOUNCE_COMPETITIVE = "competitive"


@dataclass(frozen=True)
class SchedulePin:
    """A channel's schedule policy. ``maintain_pin`` keeps a pinned /event-scribe fresh: ``pin_filters``
    selects its formats (empty → the whole active set, the set channel) and ``scope_label`` is its title
    scope (``None`` → the active set's name). ``announce_filters`` selects which start-today events get a
    callout — independent of the pin, so the set channel shows the full set but announces competitive
    only, and an announce-only channel (cube) keeps no pin at all. Routing is by ``channel_name``
    substring, except the set pin leaves it ``None`` and sets ``category``, which resolves the active
    set's own channel there so routing follows the rotation without a config edit.
    Pins are human-seeded and the bot only keeps them fresh; ``auto_pin`` would have it post and pin the
    schedule itself when none exists, off for every pin today and reserved for when that's wanted."""
    key: str
    channel_name: str | None
    pin_filters: tuple[str, ...]
    scope_label: str | None = None
    announce: str = ANNOUNCE_ROTATION
    announce_filters: tuple[str, ...] = ()
    maintain_pin: bool = True
    category: str | None = None
    auto_pin: bool = False


SCHEDULE_PINS: tuple[SchedulePin, ...] = (
    SchedulePin("quick", "quick-or-flashback-draft", ("quick",), "Quick Draft", ANNOUNCE_ROTATION, ("quick",)),
    SchedulePin(
        "flashback", "quick-or-flashback-draft", ("flashback",), "Flashback", ANNOUNCE_ROTATION, ("flashback",)
    ),
    SchedulePin("cube", "cube-talk", (), None, ANNOUNCE_ROTATION, ("cube",), maintain_pin=False),
    SchedulePin("sealed", "sealed-discussion", ("sealed",), "Sealed", ANNOUNCE_NONE),
    SchedulePin("set", None, (), None, ANNOUNCE_COMPETITIVE, ("competitive",), category=LATEST_SET_CATEGORY),
)


def newest_set():
    candidates = [seed for seed in ALL_SETS if seed.code != PERMANENT_CUBE_CODE]
    newest = candidates[0]
    for seed in candidates[1:]:
        if seed.start_date > newest.start_date:
            newest = seed
    return newest


def channel_words(name: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", name.lower()))


def significant_set_words(set_name: str) -> set[str]:
    return channel_words(set_name) - SET_NAME_STOPWORDS


def channel_matches_set(channel_name: str, set_name: str) -> bool:
    """Whether a discussion channel belongs to a set, by word overlap in either direction so a full
    channel name matches its set ("marvel-super-heroes" ↔ "Marvel Super Heroes") and a shortened one
    still resolves ("strixhaven" ↔ "Strixhaven: School of Mages"). Deliberately conservative — a
    channel matching no set is left alone."""
    channel = channel_words(channel_name)
    set_words = significant_set_words(set_name)
    if not channel or not set_words:
        return False
    return set_words <= channel or channel <= set_words


def active_set_seed(when: datetime | None = None) -> SetSeed:
    code = active_set_code(when)
    for seed in ALL_SETS:
        if seed.code == code:
            return seed
    return ALL_SETS[-1]


def archive_candidates(text_channels, when: datetime | None = None) -> list:
    """MTG Strategy channels belonging to sets older than the active one — what a rotation leaves
    behind for the Format Archive. The upcoming set's mod-created channel and the permanent strategy
    channels match no stale set, so they stay put."""
    active = active_set_seed(when)
    stale_sets = [seed for seed in ALL_SETS
                  if seed.code != PERMANENT_CUBE_CODE and seed.start_date < active.start_date]
    candidates = []
    for channel in text_channels:
        if channel.category is None or channel.category.name != LATEST_SET_CATEGORY:
            continue
        if channel_matches_set(channel.name, active.name):
            continue
        if any(channel_matches_set(channel.name, seed.name) for seed in stale_sets):
            candidates.append(channel)
    return candidates


def channel_for_set(channels, seed: SetSeed, category: str | None = LATEST_SET_CATEGORY):
    """The discussion channel for a set within ``category``, matched by name — MTG Strategy for the live
    set, Format Archive for one that rotated out. ``category=None`` matches anywhere, for a preview-season
    channel a mod created before it was filed. ``None`` when none matches."""
    for channel in channels:
        if category is not None and (channel.category is None or channel.category.name != category):
            continue
        if channel_matches_set(channel.name, seed.name):
            return channel
    return None


def latest_set_channel(channels, category_name: str = LATEST_SET_CATEGORY):
    """The most recently created set channel in ``category_name`` — during preview season the incoming
    set's mod-created channel, where discussion moves before the set goes live. The permanent strategy
    channels sitting in the same category match no set, so a new one of those never wins. ``None`` when
    the category holds no set channel."""
    registered = [seed for seed in ALL_SETS if seed.code != PERMANENT_CUBE_CODE]
    newest = None
    for channel in channels:
        if channel.category is None or channel.category.name != category_name:
            continue
        if not any(channel_matches_set(channel.name, seed.name) for seed in registered):
            continue
        if newest is None or channel.created_at > newest.created_at:
            newest = channel
    return newest


def set_tracking_todo_index(actions, channels) -> int | None:
    """Index of the Server Guide 'New Member To-Do' that follows the live set — the action whose linked
    channel matches a registered set by name, so it re-targets on renames without depending on the
    To-Do's copy. ``None`` when no action points at a set channel."""
    by_id = {str(channel.id): channel for channel in channels}
    registered = [seed for seed in ALL_SETS if seed.code != PERMANENT_CUBE_CODE]
    for index, action in enumerate(actions):
        channel = by_id.get(str(action.get("channel_id")))
        if channel is None:
            continue
        if any(channel_matches_set(channel.name, seed.name) for seed in registered):
            return index
    return None


def set_before(seed: SetSeed) -> SetSeed | None:
    """The set that rotated out just before ``seed`` — the newest-started set whose start precedes it,
    excluding the permanent cube. ``None`` when ``seed`` is the earliest."""
    previous: SetSeed | None = None
    for candidate in ALL_SETS:
        if candidate.code == PERMANENT_CUBE_CODE or candidate.start_date >= seed.start_date:
            continue
        if previous is None or candidate.start_date > previous.start_date:
            previous = candidate
    return previous


def season_archived(seed: SetSeed, when: datetime | None = None) -> bool:
    """Whether a set's schedule reads as a record instead of a countdown: inside the final week of its
    window, or past it. A relative countdown is noise once a season stops moving and wrong once it has
    ended, so the frozen pin and an explicit /event-scribe set query both switch on this."""
    if seed.end_date is None:
        return False
    now = when or datetime.now(timezone.utc)
    return seed.end_date - now.astimezone(EVENT_DAY_TZ).date() <= SET_PIN_FREEZE_LEAD


def set_pin_frozen(when: datetime | None = None) -> bool:
    """Whether the set channel's pinned schedule should be left alone from here on.

    True inside the final week of the active set's window. Refreshing right up to rotation would leave
    the pin holding an emptied board, every queue ended — and the channel is archived days later, so
    that pin becomes the season's record. Freezing early keeps it a full picture instead.
    """
    return season_archived(active_set_seed(when), when)


def awards_eve_set(when: datetime | None = None) -> SetSeed | None:
    """The outgoing set to run a send-off ceremony for — the active set — when a new set releases the
    next day, else ``None``. Awards run the day before a rotation, so this returns a set only on that
    eve. The date is read in Eastern, the release clock, so ``8 AM`` Pacific still resolves to the same
    calendar day as the noon-ET flip it precedes."""
    now = when or datetime.now(timezone.utc)
    tomorrow = (now.astimezone(EVENT_DAY_TZ) + timedelta(days=1)).date()
    for seed in ALL_SETS:
        if seed.code != PERMANENT_CUBE_CODE and seed.start_date == tomorrow:
            return active_set_seed(now)
    return None


AWARDS_CEREMONY_TIME = time(8, 0)


def set_after(seed: SetSeed) -> SetSeed | None:
    """The set that rotates in just after ``seed`` — the earliest-started set whose start follows it,
    excluding the permanent cube. ``None`` when ``seed`` is the newest registered."""
    following: SetSeed | None = None
    for candidate in ALL_SETS:
        if candidate.code == PERMANENT_CUBE_CODE or candidate.start_date <= seed.start_date:
            continue
        if following is None or candidate.start_date < following.start_date:
            following = candidate
    return following


def awards_ceremony_instant(seed: SetSeed) -> datetime | None:
    """When ``seed``'s Set Awards ceremony runs: ``AWARDS_CEREMONY_TIME`` Pacific on the eve of the next
    set's release. ``None`` while no later set is registered, since the eve is unknown until one is."""
    following = set_after(seed)
    if following is None:
        return None
    eve = following.start_date - timedelta(days=1)
    return datetime.combine(eve, AWARDS_CEREMONY_TIME, tzinfo=OPEN_TZ)


def awards_posted_set(when: datetime | None = None) -> SetSeed | None:
    """The set whose Set Awards are the most recent ones already posted, which is the set `/set-awards`
    answers for. It stays put for the whole of the next set, so the awards a player can look up are always
    ones that exist. ``None`` before any ceremony has run."""
    now = when or datetime.now(timezone.utc)
    posted: SetSeed | None = None
    for seed in ALL_SETS:
        if seed.code == PERMANENT_CUBE_CODE:
            continue
        instant = awards_ceremony_instant(seed)
        if instant is None or instant > now:
            continue
        if posted is None or seed.start_date > posted.start_date:
            posted = seed
    return posted


def set_seed_for_channel(channel_name: str, when: datetime | None = None) -> SetSeed | None:
    """The stale set a to-be-archived channel belongs to — the outgoing set whose send-off standings
    the channel should carry before it moves. Matches the same stale seeds ``archive_candidates`` uses,
    newest-started first so an overlapping range resolves to the later set. ``None`` when none match."""
    active = active_set_seed(when)
    matched: SetSeed | None = None
    for seed in ALL_SETS:
        if seed.code == PERMANENT_CUBE_CODE or seed.start_date >= active.start_date:
            continue
        if not channel_matches_set(channel_name, seed.name):
            continue
        if matched is None or seed.start_date > matched.start_date:
            matched = seed
    return matched


def previous_window_start(now: datetime) -> datetime:
    """The announce window immediately before ``now`` (UTC). A tick announces events that opened since
    this instant — a span that ends at the current window, so consecutive ticks never overlap and each
    event is announced exactly once. Windows are Pacific (MTGA's clock) so they hold across DST."""
    now_local = now.astimezone(OPEN_TZ)
    fired: list[datetime] = []
    for day_offset in (0, -1):
        day = (now_local + timedelta(days=day_offset)).date()
        for window in ANNOUNCE_WINDOWS:
            moment = datetime.combine(day, window, tzinfo=OPEN_TZ)
            if moment <= now_local + timedelta(minutes=1):
                fired.append(moment)
    fired.sort()
    previous = fired[-2] if len(fired) >= 2 else now_local - timedelta(days=1)
    return previous.astimezone(timezone.utc)


def newly_opened(groups: list[mtgscribe.EventGroup], since: datetime, now: datetime) -> list:
    """Groups whose go-live falls in ``(since, now]`` — events that opened since the previous window,
    timed by ``effective_start`` so a midnight-ET placeholder announces at its real morning open."""
    return [group for group in groups if since < effective_start(group) <= now]


def effective_start(group: mtgscribe.EventGroup) -> datetime:
    """The go-live used to time a group's announcement. Scribe stamps multi-day competitive events
    (Qualifier Weekend, ACQ) at midnight ET — a whole-day placeholder, not a queue-open time — which
    sits the evening before in the Americas and would fire a window early. Normalize those to the first
    announce window that day (6 AM Pacific), the same open the Play-Ins carry. Other groups keep their
    start verbatim."""
    if group.competitive and _is_event_day_midnight(group.start):
        event_day = group.start.astimezone(EVENT_DAY_TZ).date()
        return datetime.combine(event_day, ANNOUNCE_WINDOWS[0], tzinfo=OPEN_TZ)
    return group.start


def _is_event_day_midnight(moment: datetime) -> bool:
    local = moment.astimezone(EVENT_DAY_TZ)
    return local.hour == 0 and local.minute == 0


def next_rotation(groups: list[mtgscribe.EventGroup], current: mtgscribe.EventGroup):
    """The soonest group that begins after ``current`` — the next rotation of the same pin's format,
    used for the announcement's "Next Up" preview. ``None`` when nothing follows."""
    upcoming = None
    for group in groups:
        if group.start <= current.start:
            continue
        if upcoming is None or group.start < upcoming.start:
            upcoming = group
    return upcoming


def announcement_format(group: mtgscribe.EventGroup) -> str:
    """The rotation-type word in an announcement heading ("**<set>** <word> is live!"), keyed on the
    group's tags rather than the routed channel so a quick-or-flashback channel labels its Flashback
    and Quick posts distinctly. Empty for a cube, whose set name already names the format."""
    if group.flashback:
        return "Flashback"
    if group.competitive:
        return "Competitive"
    if group.cube:
        return ""
    if "Quick Draft" in group.formats:
        return "Quick Draft"
    return "Sealed"


def already_announced(recent_contents: list[str], lead: str, label: str) -> bool:
    """An announcement is a repeat when the day's own messages already carry its type lead and set
    label — the table-free dedup that survives a restart or a re-tick on the same day."""
    for content in recent_contents:
        if lead in content and label in content:
            return True
    return False
