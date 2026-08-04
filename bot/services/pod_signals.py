"""Pure slot/day/threshold logic for on-demand pods — no Discord, no DB.

Feeds the daily poll (bot/tasks/pod_daily_poll.py) and the dynamic queue
(bot/commands/pod_queue.py). ET anchoring reuses pod_schedule.SCHEDULE_TZ so the
poll slots share one clock with the fixed weekly slots.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from bot.services.pod_schedule import (
    EARLY_POD_ROLE_NAME,
    LATE_POD_ROLE_NAME,
    SCHEDULE_TZ,
    WEEKEND_EARLY_POD_ROLE_NAME,
    WEEKEND_LATE_POD_ROLE_NAME,
)


SATURDAY = 5

POST_HOUR_ET = 10

KIND_POLL = "poll"
KIND_QUEUE = "queue"
KIND_SCHEDULED = "scheduled"

QUEUE_BUCKET = "queue"
SCHEDULED_BUCKET = "scheduled"

STATUS_OPEN = "open"
STATUS_FIRED = "fired"
STATUS_EXPIRED = "expired"

RSVP_YES = "yes"
RSVP_MAYBE = "maybe"
RSVP_NO = "no"
RSVP_STATES = (RSVP_YES, RSVP_MAYBE, RSVP_NO)
RSVP_EMOJI = {RSVP_YES: "✅", RSVP_MAYBE: "🤷", RSVP_NO: "❌"}


LANE_EARLY = "EARLY"
LANE_LATE = "LATE"
LANE_ORDER = (LANE_EARLY, LANE_LATE)


@dataclass(frozen=True)
class PollBucket:
    """One slot of one day. `lane` is the launcher column the slot belongs to for life: the weekday and
    weekend buckets of a time of day are two keys for one column, so a slot rolling from Friday to
    Saturday stays in its column and picks up the weekend ping role."""
    key: str
    name: str
    emoji: str
    start: time
    role_name: str
    lane: str


WEEKEND_EARLY_BUCKET = PollBucket(
    "AFTERNOON", "Early Pod", "💫", time(14, 0), WEEKEND_EARLY_POD_ROLE_NAME, LANE_EARLY)
WEEKEND_LATE_BUCKET = PollBucket(
    "EVENING", "Late Pod", "☄️", time(20, 0), WEEKEND_LATE_POD_ROLE_NAME, LANE_LATE)
SATURDAY_LATE_BUCKET = PollBucket(
    "SATURDAY_EVENING", "Late Pod", "☄️", time(21, 0), WEEKEND_LATE_POD_ROLE_NAME, LANE_LATE)

WEEKDAY_BUCKETS: tuple[PollBucket, ...] = (
    PollBucket("EARLY", "Early Pod", "💫", time(14, 0), EARLY_POD_ROLE_NAME, LANE_EARLY),
    PollBucket("LATE", "Late Pod", "☄️", time(20, 0), LATE_POD_ROLE_NAME, LANE_LATE),
)
WEEKEND_BUCKETS: tuple[PollBucket, ...] = (WEEKEND_EARLY_BUCKET, WEEKEND_LATE_BUCKET)
SATURDAY_BUCKETS: tuple[PollBucket, ...] = (WEEKEND_EARLY_BUCKET, SATURDAY_LATE_BUCKET)
ALL_BUCKETS: tuple[PollBucket, ...] = WEEKDAY_BUCKETS + WEEKEND_BUCKETS + (SATURDAY_LATE_BUCKET,)


def is_weekend(day: date) -> bool:
    return day.weekday() >= SATURDAY


def poll_buckets_for(day: date) -> tuple[PollBucket, ...]:
    """Saturday drafts its late pod an hour after every other day's, so it carries a bucket of its own. Same
    lane and same ping role as the rest of the weekend: only the hour differs."""
    if day.weekday() == SATURDAY:
        return SATURDAY_BUCKETS
    return WEEKEND_BUCKETS if is_weekend(day) else WEEKDAY_BUCKETS


FORMAT_SEP = "|"


def named_bucket_key(bucket_key: str, set_code: str) -> str:
    """One named pod's key: its time slot plus the format it opens on. A slot offering two formats needs
    two signal identities, and `PodSignal.bucket` already is that identity, so the format rides in the key
    instead of a new column the message/bucket/date unique constraint would have to grow."""
    return f"{bucket_key}{FORMAT_SEP}{set_code}"


def time_key_of(bucket_key: str) -> str:
    """The time-slot half of a key. Lanes, ping roles and slot times all belong to the time dimension, so
    every lookup resolves through here and a named key behaves exactly like its plain slot."""
    return bucket_key.split(FORMAT_SEP, 1)[0]


def format_of(bucket_key: str) -> str | None:
    """The format half of a named key, or None for a plain slot key."""
    return bucket_key.partition(FORMAT_SEP)[2] or None


def bucket_by_key(key: str) -> PollBucket | None:
    time_key = time_key_of(key)
    for bucket in ALL_BUCKETS:
        if bucket.key == time_key:
            return bucket
    return None


def lane_of(bucket_key: str) -> str | None:
    bucket = bucket_by_key(bucket_key)
    return bucket.lane if bucket else None


def bucket_for_lane(day: date, lane: str) -> PollBucket | None:
    """The bucket a lane resolves to on `day`, so a rolled slot re-reads its weekday or weekend identity
    from the day it now sits on."""
    for bucket in poll_buckets_for(day):
        if bucket.lane == lane:
            return bucket
    return None


def next_lane_start(lane: str, now: datetime) -> datetime | None:
    """When the lane's slot next comes around: today's start while it is still ahead, tomorrow's once it has
    passed. The hour is read off the day the slot lands on, so a day running its slot at its own hour is
    named at that hour. Rebuilt from the wall clock rather than shifted by a day, so a start stays at its ET
    hour across a daylight saving change."""
    today = now.astimezone(SCHEDULE_TZ).date()
    for day in (today, today + timedelta(days=1)):
        bucket = bucket_for_lane(day, lane)
        if bucket is None:
            continue
        start = datetime.combine(day, bucket.start, tzinfo=SCHEDULE_TZ)
        if start > now:
            return start
    return None


def slot_can_fire(slot_time: datetime, now: datetime) -> bool:
    """Whether a slot at threshold may graduate into a pod yet. A slot on a later day holds instead: a
    rolled column collects signups all evening, and the morning post is what lets them fire."""
    return slot_time.astimezone(SCHEDULE_TZ).date() <= now.astimezone(SCHEDULE_TZ).date()


def bucket_role_name(key: str) -> str | None:
    bucket = bucket_by_key(key)
    return bucket.role_name if bucket else None


def slot_role_name_for_event_time(event_time: datetime) -> str | None:
    """The slot ping role owning a pod at this instant, keyed on weekend and time-of-day off the poll
    buckets — the one source of truth for who a pod pings. An off-grid custom time matches no bucket
    and returns None, so such a pod pings nobody rather than mis-resolving to a neighbouring slot."""
    local = event_time.astimezone(SCHEDULE_TZ)
    for bucket in poll_buckets_for(local.date()):
        if bucket.start.hour == local.hour and bucket.start.minute == local.minute:
            return bucket.role_name
    return None


def slot_event_time(signal_date: date, bucket_key: str) -> datetime | None:
    """The ET wall-clock start for a poll slot on `signal_date`, or None for an unknown bucket."""
    bucket = bucket_by_key(bucket_key)
    if bucket is None:
        return None
    return datetime.combine(signal_date, bucket.start, tzinfo=SCHEDULE_TZ)


def should_fire(member_count: int, threshold: int) -> bool:
    return member_count >= threshold


def teardown_at(last_activity: datetime, minutes: int) -> datetime:
    return last_activity + timedelta(minutes=minutes)


def inactivity_window_text(minutes: int) -> str:
    if minutes % 60 == 0:
        hours = minutes // 60
        return f"{hours} hour" if hours == 1 else f"{hours} hours"
    return f"{minutes} minutes"
