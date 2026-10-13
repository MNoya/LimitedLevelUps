"""Fantasy events from the shared `fantasy_events.json`, the registry the site reads too"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from bot.config import SITE_URL

EVENTS_JSON = Path(__file__).resolve().parents[2] / "fantasy_events.json"

STAGE_QUARTERFINAL = "quarterfinal"
STAGE_SEMIFINAL = "semifinal"
STAGE_FINAL = "final"

BRACKET_FEEDS = {"SF1": ("QF1", "QF3"), "SF2": ("QF2", "QF4"), "F": ("SF1", "SF2")}
QUARTERFINAL_BY_LOWER_SEED = {8: "QF1", 7: "QF2", 5: "QF3", 6: "QF4"}


@dataclass(frozen=True)
class FantasyEvent:
    code: str
    name: str
    melee_tournament_id: int
    picks_lock_at: datetime
    swiss_rounds: int
    cut_round: int
    draft_rounds: tuple[int, ...]
    bracket_lock_at: datetime
    schedule_name: str | None
    field_seed: Path | None
    replay_only: bool
    live: bool
    slug: str
    short_name: str
    crest_url: str | None
    set_code: str

    def stage_for_round(self, round_number: int) -> str:
        if round_number <= self.swiss_rounds:
            return "swiss"
        top8_stages = (STAGE_QUARTERFINAL, STAGE_SEMIFINAL, STAGE_FINAL)
        return top8_stages[min(round_number - self.swiss_rounds, len(top8_stages)) - 1]

    def format_for_round(self, round_number: int) -> str:
        if round_number in self.draft_rounds:
            return "draft"
        return "constructed"


def all_events() -> list[FantasyEvent]:
    raw = json.loads(EVENTS_JSON.read_text())
    events = []
    for code, config in raw.items():
        if "meleeTournamentId" not in config:
            continue
        events.append(_event_from_config(code, config))
    events.sort(key=_lock_key, reverse=True)
    return events


def event_for(code: str) -> FantasyEvent | None:
    for event in all_events():
        if event.code == code.upper():
            return event
    return None


def _event_from_config(code: str, config: dict) -> FantasyEvent:
    field_seed = config.get("fieldSeed")
    return FantasyEvent(
        code=code,
        name=config["name"],
        melee_tournament_id=config["meleeTournamentId"],
        picks_lock_at=_parse(config["picksLockAt"]),
        swiss_rounds=config["swissRounds"],
        cut_round=config["cutRound"],
        draft_rounds=tuple(config["draftRounds"]),
        bracket_lock_at=_parse(config["bracketLockAt"]),
        schedule_name=config.get("scheduleName"),
        field_seed=EVENTS_JSON.parent / field_seed if field_seed else None,
        replay_only=config.get("replayOnly", False),
        live=config.get("live", False),
        slug=config["slug"],
        short_name=config["shortName"],
        crest_url=f"{SITE_URL}{config['crest']}" if config.get("crest") else None,
        set_code=config["setCode"],
    )


def pro_play_url(event: FantasyEvent, view: str | None = None) -> str:
    base = f"{SITE_URL}/pro-play/{event.slug}"
    return f"{base}/{view}" if view else base


def melee_url(event: FantasyEvent) -> str:
    return f"https://melee.gg/Tournament/View/{event.melee_tournament_id}"


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _lock_key(event: FantasyEvent) -> datetime:
    return event.picks_lock_at
