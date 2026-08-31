"""The community pod schedule for a flashback season, laid down from the running format vote.

The unit is the day, not the slot: each scheduled day offers exactly two formats, and each runs in both the
Early and Late slot, so the calendar shows two icons a day. The two picks come from two rotating pools by
weekday:

- Flashback days (Mon/Wed/Fri/Sun): the featured custom set plus one voted flashback set.
- Staple days (Tue/Thu/Sat): the latest set plus the staple cube.

A flashback set needs `VOTE_FLOOR` raw votes to be eligible, and the top `TOP_N` by vote count earn days, with
ties broken by voter pod attendance. Each set's season day budget is its vote share of the whole season's
flashback days. Every sweep counts the days a set already played or has locked on the launcher and fills only
the deficit onto the still-open days, so a set never runs more than its budget and a late vote reshapes only
the days not yet played. One sweep fills the window from a start day to the day before the next set rotates in;
it writes `source='auto'` overlay rows, never touches an organizer's manual override, and skips the championship
day so its own machinery keeps it.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bot.models import PodDraftEvent, PodDraftParticipant, PodFormatVote, PodScheduleSlot, PodSignal
from bot.services.championship_dates import championship_date_for
from bot.services.pod_format import MEMA_CODE, PEASANT_CODE, is_custom
from bot.services.pod_format_schedule import (
    FLASHBACK,
    auto_slots,
    clear_auto_slots,
    latest_on,
    manual_slots,
    set_slot,
)
from bot.services.pod_format_vote import season_code
from bot.services.pod_signals import KIND_POLL, SLOT_EARLY, SLOT_LATE
from bot.sets import is_known_set, previous_set_code, seed_for_code

STAPLE_FORMAT = PEASANT_CODE
FLASHBACK_WEEKDAYS = frozenset({0, 2, 4, 6})
VOTE_FLOOR = 6
TOP_N = 12
HORIZON_CAP_DAYS = 70
FLASHBACK_REVEAL_DELAY = timedelta(hours=24)

FEATURED_BY_SEASON: dict[str, str] = {"HOB": MEMA_CODE}


def featured_format(season: str) -> str | None:
    return FEATURED_BY_SEASON.get(season)


def day_picks(day: date, flashback_set: str | None, latest: str, featured: str | None) -> tuple[str, ...]:
    """The formats a scheduled day offers. A flashback day pairs the season's featured pick with the voted
    flashback set, falling back to the `FLASHBACK` placeholder when no set is eligible and dropping the featured
    pick when the season has none; a staple day pairs the latest set with the staple cube."""
    if day.weekday() in FLASHBACK_WEEKDAYS:
        picks = (featured, flashback_set or FLASHBACK)
    else:
        picks = (latest, STAPLE_FORMAT)
    return tuple(code for code in picks if code)


def assign_flashbacks(days: list[date], scores: dict[str, float]) -> list[str | None]:
    """Which flashback set fills each flashback day, in day order. Sets earn days in proportion to their vote
    count, no set lands two flashback days in a row while another set has days left, and a set's days spread
    across different weekdays so a popular one does not settle onto one weekday every week. A day with nothing
    eligible left stays `None` and falls back to the placeholder."""
    if not days or not scores:
        return [None] * len(days)
    return _spread(_quota_counts(scores, len(days)), [day.weekday() for day in days])


def _quota_counts(scores: dict[str, float], total_days: int) -> dict[str, int]:
    """Largest-remainder split of `total_days` across the sets by vote share."""
    if total_days <= 0 or not scores:
        return {code: 0 for code in scores}
    total = sum(scores.values())
    if total <= 0:
        return {code: 0 for code in scores}
    quota = {code: total_days * score / total for code, score in scores.items()}
    counts = {code: int(quota[code]) for code in scores}
    while sum(counts.values()) < total_days:
        counts[_largest_remainder(list(scores), quota, counts)] += 1
    return counts


def run_allocation(
    session: Session, start: date, *, rewrite: bool = True, now: datetime | None = None,
) -> dict[tuple[date, str], tuple[str, ...]]:
    """Fill the flashback season from `start` to the day before the next rotation and return the written rows.
    `rewrite` clears the allocator's prior rows first and lays the whole window fresh; without it the sweep only
    fills days that carry no overlay row yet, so a re-run adds newly-in-range days without moving announced ones.
    A manual override, a day already on the launcher and the championship day are always left alone, so a fresh
    vote never changes a format players are already looking at."""
    days = _horizon(start)
    if not days:
        return {}
    launched = _launched_days(session, days[0], days[-1])
    if rewrite:
        clear_auto_slots(session, days[0], days[-1], except_days=frozenset(launched))
    reserved = manual_slots(session, days[0], days[-1])
    kept = reserved if rewrite else reserved | auto_slots(session, days[0], days[-1])
    latest = latest_on(days[0])
    season = season_code()
    featured = featured_format(season)
    revealed = _flashback_revealed(session, season, now or datetime.now(timezone.utc))
    scores = _flashback_scores(session, season, latest) if revealed else {}
    assignments, _ = _season_allocation(session, days[0], scores)

    result: dict[tuple[date, str], tuple[str, ...]] = {}
    for day in days:
        if _is_championship(day) or day in launched:
            continue
        picks = day_picks(day, assignments.get(day), latest, featured)
        for slot in (SLOT_EARLY, SLOT_LATE):
            if (day, slot) in kept:
                continue
            set_slot(session, day, slot, picks, source="auto")
            result[(day, slot)] = picks
    return result


def vote_results(session: Session, start: date) -> list[tuple[str, int, int]]:
    """Each top-12 flashback set as (code, votes, days), most days then most votes first. Days are the set's
    season total under the same budget `run_allocation` writes: what it already played or has locked, plus its
    share of the days still open."""
    days = _horizon(start)
    if not days:
        return []
    latest = latest_on(days[0])
    votes = _flashback_scores(session, season_code(), latest)
    _, per_set_days = _season_allocation(session, days[0], votes)
    kept = [(code, int(count), per_set_days.get(code, 0)) for code, count in votes.items()]
    kept.sort(key=lambda row: (row[2], row[1]), reverse=True)
    return kept


def _season_allocation(
    session: Session, today: date, scores: dict[str, float],
) -> tuple[dict[date, str | None], dict[str, int]]:
    """The flashback pick for each still-open day, and each set's total season days. A set's budget is its vote
    share of the season's flashback days; the days it already played or has locked are subtracted, and only the
    deficit is laid onto the open days, so no set exceeds its budget across the season."""
    days = _horizon(today)
    if not days:
        return {}, {}
    latest = latest_on(today)
    launched = _launched_days(session, days[0], days[-1])
    reserved = manual_slots(session, days[0], days[-1])
    open_days = [
        day for day in days
        if _is_flashback_day(day) and day not in launched and (day, SLOT_EARLY) not in reserved
    ]
    committed = _committed_counts(session, _season_start(today), days[-1], today, launched, reserved, latest)
    budget = _quota_counts(scores, sum(committed.values()) + len(open_days))
    deficit = {code: max(0, budget.get(code, 0) - committed.get(code, 0)) for code in scores}
    picks = _spread(deficit, [day.weekday() for day in open_days])
    per_set_days: dict[str, int] = defaultdict(int)
    for code, count in committed.items():
        per_set_days[code] += count
    for code in picks:
        if code:
            per_set_days[code] += 1
    return dict(zip(open_days, picks)), dict(per_set_days)


def _season_start(today: date) -> date:
    base = latest_on(today)
    start = today
    for _ in range(HORIZON_CAP_DAYS):
        previous = start - timedelta(days=1)
        if latest_on(previous) != base:
            break
        start = previous
    return start


def _committed_counts(
    session: Session, season_start: date, end: date, today: date,
    launched: set[date], reserved: set[tuple[date, str]], latest: str,
) -> dict[str, int]:
    """How many flashback days each set already holds that the sweep will not move: days already played, plus
    launched or manually overridden days ahead. Read off the Early slot's stored pick."""
    rows = session.execute(
        select(PodScheduleSlot.day, PodScheduleSlot.formats)
        .where(PodScheduleSlot.slot == SLOT_EARLY, PodScheduleSlot.day >= season_start, PodScheduleSlot.day <= end)
    ).all()
    counts: dict[str, int] = defaultdict(int)
    for day, formats in rows:
        locked = day < today or day in launched or (day, SLOT_EARLY) in reserved
        if not (_is_flashback_day(day) and locked):
            continue
        for code in formats:
            if _is_flashback_candidate(code, latest):
                counts[code] += 1
                break
    return dict(counts)


def _horizon(start: date) -> list[date]:
    base = latest_on(start)
    days: list[date] = []
    day = start
    while latest_on(day) == base and len(days) < HORIZON_CAP_DAYS:
        days.append(day)
        day += timedelta(days=1)
    return days


def _launched_days(session: Session, start: date, end: date) -> set[date]:
    """The days in the window whose launcher already opened poll signals, so a re-sweep leaves their format alone"""
    rows = session.execute(
        select(PodSignal.signal_date)
        .where(PodSignal.kind == KIND_POLL, PodSignal.signal_date >= start, PodSignal.signal_date <= end)
        .distinct()
    )
    return {signal_date for (signal_date,) in rows}


def _is_flashback_day(day: date) -> bool:
    return day.weekday() in FLASHBACK_WEEKDAYS and not _is_championship(day)


def _is_championship(day: date) -> bool:
    return championship_date_for(day) == day


def _flashback_revealed(session: Session, season: str, now: datetime) -> bool:
    """Whether the flashback picks are due to appear yet: `FLASHBACK_REVEAL_DELAY` after the season's first
    vote, so a fresh vote holds every day at TBD for a day before the sets fill in."""
    opened = session.execute(
        select(func.min(PodFormatVote.voted_at)).where(PodFormatVote.season_set_code == season)
    ).scalar_one_or_none()
    return opened is not None and now >= opened + FLASHBACK_REVEAL_DELAY


def _flashback_scores(session: Session, season: str, latest: str) -> dict[str, float]:
    rows = session.execute(
        select(PodFormatVote.format_code, PodFormatVote.player_id)
        .where(PodFormatVote.season_set_code == season)
    ).all()
    voter_ids = {player_id for _, player_id in rows if player_id is not None}
    weights = _voter_weights(session, voter_ids, _attendance_window_start(season))

    raw: dict[str, int] = defaultdict(int)
    weighted: dict[str, float] = defaultdict(float)
    for code, player_id in rows:
        if not _is_flashback_candidate(code, latest):
            continue
        raw[code] += 1
        weighted[code] += weights.get(player_id, 1)
    eligible = [code for code in raw if raw[code] >= VOTE_FLOOR]
    eligible.sort(key=lambda code: (raw[code], weighted[code]), reverse=True)
    return {code: float(raw[code]) for code in eligible[:TOP_N]}


def _is_flashback_candidate(code: str, latest: str) -> bool:
    if code in (latest, STAPLE_FORMAT) or code in FEATURED_BY_SEASON.values():
        return False
    if is_custom(code):
        return False
    return is_known_set(code)


def _attendance_window_start(season: str) -> date:
    """The first day of the last two seasons: the start of the set before this one, so weighting reads the whole
    of both the current and the previous set's pod attendance. Falls back to this season's own start."""
    previous = previous_set_code(season)
    seed = seed_for_code(previous) if previous else None
    if seed is None:
        seed = seed_for_code(season)
    return seed.start_date if seed is not None else date.today()


def _voter_weights(session: Session, voter_ids: set[str], since: date) -> dict[str, int]:
    """Weight one to three by pod attendance over the window, split at the terciles of the drafters who showed up
    at all. A voter who has not drafted floors at one, so a new player still moves the tally."""
    if not voter_ids:
        return {}
    rows = session.execute(
        select(PodDraftParticipant.player_id, func.count(func.distinct(PodDraftEvent.id)))
        .join(PodDraftEvent, PodDraftEvent.id == PodDraftParticipant.event_id)
        .where(PodDraftParticipant.player_id.in_(voter_ids), PodDraftEvent.event_date >= since)
        .group_by(PodDraftParticipant.player_id)
    ).all()
    attendance = {player_id: count for player_id, count in rows}
    positive = sorted(count for count in attendance.values() if count > 0)
    if not positive:
        return {player_id: 1 for player_id in voter_ids}
    low = positive[len(positive) // 3]
    high = positive[2 * len(positive) // 3]

    weights: dict[str, int] = {}
    for player_id in voter_ids:
        count = attendance.get(player_id, 0)
        if count >= high:
            weights[player_id] = 3
        elif count >= low:
            weights[player_id] = 2
        else:
            weights[player_id] = 1
    return weights


def _largest_remainder(candidates: list[str], quota: dict[str, float], counts: dict[str, int]) -> str:
    best = candidates[0]
    for code in candidates[1:]:
        if (quota[code] - counts[code]) > (quota[best] - counts[best]):
            best = code
    return best


def _spread(counts: dict[str, int], weekdays: list[int]) -> list[str | None]:
    """Lay the per-set day counts across the flashback days in weekday order. Each day picks the set that is not
    a back-to-back repeat, has run fewest times on this weekday, then has the most days left, so a set spreads
    across weekdays and weeks."""
    remaining = dict(counts)
    used_on_weekday: dict[str, dict[int, int]] = {code: defaultdict(int) for code in counts}
    result: list[str | None] = []
    last: str | None = None
    for weekday in weekdays:
        best: str | None = None
        best_key: tuple[int, int, int] | None = None
        for code in remaining:
            if remaining[code] <= 0:
                continue
            key = (1 if code == last else 0, used_on_weekday[code][weekday], -remaining[code])
            if best_key is None or key < best_key:
                best = code
                best_key = key
        result.append(best)
        if best is not None:
            remaining[best] -= 1
            used_on_weekday[best][weekday] += 1
            last = best
    return result
