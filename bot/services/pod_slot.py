"""Date + time-of-day naming for pods — the identity a pod carries from creation.

A pod's Discord name is `SET Mon Day Slot Pod` (`MSH Jul 16 Early Pod`), fixed when the card is
posted and never renumbered: the slot label comes from the poll buckets by weekend and time of day,
so a launcher pod and a weekly-schedule pod at the same slot read the same. The website's `#N`
milestone is a separate, execution-ordered projection computed in `public_pod_draft_events`, not
part of this name. Pure — no Discord, no DB.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date, datetime

from bot.services.pod_format import format_display
from bot.services.pod_schedule import SCHEDULE_TZ
from bot.services.pod_signals import BONUS_BUCKET, PollBucket, is_bonus_time, poll_buckets_for


COLLISION_INDEX_RE = re.compile(r"#(\d+)\s*$")


def pod_event_date(event_time: datetime) -> date:
    """The calendar day a pod belongs to in Eastern time, never the UTC day a Late Pod rolls into"""
    return event_time.astimezone(SCHEDULE_TZ).date()


def pod_display_name(set_code: str, event_time: datetime) -> str:
    local = event_time.astimezone(SCHEDULE_TZ)
    return f"{format_display(set_code)} {local:%b %-d} {pod_slot_label(event_time)}"


def queue_display_name(set_code: str, event_time: datetime) -> str:
    local = event_time.astimezone(SCHEDULE_TZ)
    return f"{format_display(set_code)} {local:%b %-d} Pod Draft Queue"


def next_collision_index(names: Iterable[str], index_re: re.Pattern[str] = COLLISION_INDEX_RE) -> int:
    """Next free trailing index across `names`; an unindexed name counts as 1, so the first collision
    yields 2. `index_re` captures the integer in group 1. Shared by the ` - Table N` split naming and
    the ` #N` disambiguation of same-named concurrent pods and queues."""
    highest = 1
    for name in names:
        match = index_re.search(name or "")
        if match:
            highest = max(highest, int(match.group(1)))
    return highest + 1


def pod_slot_label(event_time: datetime) -> str:
    return slot_bucket_for(event_time).name


def slot_bucket_for(event_time: datetime) -> PollBucket:
    """The poll bucket a pod at this instant belongs to, by weekend and nearest start time. An
    exact-grid pod lands on its own slot; an off-grid `/draft` snaps to the closest slot, ties going
    to the later one so a mid-afternoon pod reads Late rather than Early. A pod two hours or more from
    every slot belongs to no slot and reads Bonus."""
    if is_bonus_time(event_time):
        return BONUS_BUCKET
    local = event_time.astimezone(SCHEDULE_TZ)
    buckets = poll_buckets_for(local.date())
    minutes = local.hour * 60 + local.minute
    best = buckets[0]
    best_delta = abs(minutes - (best.start.hour * 60 + best.start.minute))
    for bucket in buckets[1:]:
        delta = abs(minutes - (bucket.start.hour * 60 + bucket.start.minute))
        if delta <= best_delta:
            best_delta = delta
            best = bucket
    return best
