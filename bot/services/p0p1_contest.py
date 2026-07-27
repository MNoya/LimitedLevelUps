"""Contest windows from the shared `p0p1_contests.json`, the same file the frontend imports. Phases
mirror `frontend/src/data/p0p1Slots.ts`, by the clock alone: the site's reveal also reads the ratings
fixture, so `PHASE_FINAL` here means only that the scoring window has elapsed.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

CONTESTS_JSON = Path(__file__).resolve().parents[2] / "p0p1_contests.json"

SCORING_WINDOW = timedelta(days=28)
REVEAL_WINDOW = timedelta(days=28)

PHASE_PRE = "pre"
PHASE_VOTING = "voting"
PHASE_LOCKED = "locked"
PHASE_FINAL = "final"


@dataclass(frozen=True)
class Contest:
    code: str
    name: str
    release: datetime
    previews_open: datetime
    voting_deadline: datetime

    @property
    def scoring_date(self) -> datetime:
        return self.voting_deadline + SCORING_WINDOW

    @property
    def reveal_end(self) -> datetime:
        return self.release + REVEAL_WINDOW

    def phase(self, when: datetime) -> str:
        if when < self.previews_open:
            return PHASE_PRE
        if when < self.voting_deadline:
            return PHASE_VOTING
        if when < self.scoring_date:
            return PHASE_LOCKED
        return PHASE_FINAL


def all_contests() -> list[Contest]:
    """Newest release first. A contest without its own deadline closes at the Arena release."""
    raw = json.loads(CONTESTS_JSON.read_text())
    contests = []
    for code, config in raw.items():
        release = _parse(config["release"])
        deadline = _parse(config["votingDeadline"]) if config.get("votingDeadline") else release
        contests.append(Contest(
            code=code, name=config["name"], release=release,
            previews_open=_parse(config["previewsOpen"]), voting_deadline=deadline,
        ))
    contests.sort(key=_release_key, reverse=True)
    return contests


def contest_for(code: str) -> Contest | None:
    for contest in all_contests():
        if contest.code == code.upper():
            return contest
    return None


def featured_contest(when: datetime) -> Contest | None:
    """The contest a bare `/p0p1` serves, mirroring `resolveFeaturedContest`."""
    contests = all_contests()
    if not contests:
        return None
    for contest in contests:
        if contest.previews_open <= when < contest.voting_deadline:
            return contest
    for contest in contests:
        if contest.voting_deadline <= when < contest.reveal_end:
            return contest
    for contest in contests:
        if when >= contest.reveal_end:
            return contest
    return contests[-1]


def contest_to_advertise(when: datetime) -> Contest | None:
    """The one taking votes, else the one waiting on results, else the one opening soonest. A contest
    still in previews outranks a finished one, so a teaser can run before the pool goes live."""
    contests = all_contests()
    if not contests:
        return None
    closing_soonest = None
    for contest in contests:
        if contest.phase(when) != PHASE_VOTING:
            continue
        if closing_soonest is None or contest.voting_deadline < closing_soonest.voting_deadline:
            closing_soonest = contest
    if closing_soonest is not None:
        return closing_soonest
    for contest in contests:
        if contest.phase(when) == PHASE_LOCKED:
            return contest
    opening_soonest = None
    for contest in contests:
        if contest.phase(when) != PHASE_PRE:
            continue
        if opening_soonest is None or contest.previews_open < opening_soonest.previews_open:
            opening_soonest = contest
    if opening_soonest is not None:
        return opening_soonest
    return contests[0]


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _release_key(contest: Contest) -> datetime:
    return contest.release
