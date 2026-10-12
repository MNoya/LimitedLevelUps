"""Public melee.gg tournament pages: round list, pairings and results, no login needed"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

import requests


@dataclass(frozen=True)
class MeleeRound:
    round_id: int
    name: str
    started: bool


@dataclass(frozen=True)
class MeleeDecklist:
    decklist_id: str
    name: str


@dataclass(frozen=True)
class MeleeCompetitor:
    username: str
    display_name: str
    game_wins: int
    decklist: MeleeDecklist | None = None


@dataclass(frozen=True)
class MeleeMatch:
    guid: str
    round_name: str
    table_number: int | None
    has_result: bool
    game_draws: int
    competitors: tuple[MeleeCompetitor, ...]

    @property
    def is_bye(self) -> bool:
        return len(self.competitors) == 1


class MeleeClient:
    def __init__(self, cache_dir: Path | None = None, min_interval_s: float = 1.5, offline: bool = False):
        self.cache_dir = cache_dir
        self.min_interval_s = min_interval_s
        self.offline = offline
        self._last_request = 0.0
        self._http = requests.Session()
        self._http.headers["User-Agent"] = (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
        )

    def pairing_rounds(self, tournament_id: int) -> list[MeleeRound]:
        page = self._cached(f"tournament_{tournament_id}.html", lambda: self._get(f"/Tournament/View/{tournament_id}"))
        return parse_pairing_rounds(page)

    def round_matches(self, round_id: int) -> list[MeleeMatch]:
        body = self._cached(f"round_{round_id}.json", lambda: self._post_matches(round_id))
        return parse_matches(json.loads(body))

    def standings_ranks(self, round_id: int, top: int) -> dict[str, int]:
        body = self._cached(f"standings_{round_id}.json", lambda: self._post_standings(round_id, top))
        return parse_standings_ranks(json.loads(body))

    def _post_standings(self, round_id: int, top: int) -> str:
        return self._request("POST", "/Standing/GetRoundStandings", data=_standings_form(round_id, top),
                             headers={"X-Requested-With": "XMLHttpRequest"})

    def _post_matches(self, round_id: int) -> str:
        return self._request("POST", f"/Match/GetRoundMatches/{round_id}", data=_matches_form(),
                             headers={"X-Requested-With": "XMLHttpRequest"})

    def _get(self, path: str) -> str:
        return self._request("GET", path)

    def _request(self, method: str, path: str, **kwargs) -> str:
        wait = self.min_interval_s - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        response = self._http.request(method, f"https://melee.gg{path}", timeout=30, **kwargs)
        self._last_request = time.monotonic()
        response.raise_for_status()
        return response.text

    def _cached(self, name: str, fetch) -> str:
        path = self.cache_dir / name if self.cache_dir else None
        if self.offline and path is not None and path.exists():
            return path.read_text()
        body = fetch()
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body)
        return body


def parse_pairing_rounds(page: str) -> list[MeleeRound]:
    start = page.find('id="pairings-round-selector-container"')
    if start < 0:
        return []
    end = page.find("</div>", start)
    buttons = re.findall(r'<button[^>]*class="[^"]*round-selector[^"]*"[^>]*>', page[start:end], re.S)
    rounds = []
    for button in buttons:
        attributes = dict(re.findall(r'data-([a-z-]+)="([^"]*)"', button))
        rounds.append(MeleeRound(
            round_id=int(attributes["id"]),
            name=attributes.get("name", ""),
            started=attributes.get("is-started") == "True",
        ))
    return rounds


def parse_matches(payload: dict) -> list[MeleeMatch]:
    matches = []
    for row in payload.get("data", []):
        competitors = []
        for competitor in row.get("Competitors", []):
            players = competitor.get("Team", {}).get("Players", [])
            if not players:
                continue
            competitors.append(MeleeCompetitor(
                username=players[0]["Username"],
                display_name=players[0]["DisplayName"],
                game_wins=competitor.get("GameWins") or 0,
                decklist=_first_decklist(competitor),
            ))
        matches.append(MeleeMatch(
            guid=row["Guid"],
            round_name=row.get("RoundDescription") or "",
            table_number=row.get("TableNumber"),
            has_result=bool(row.get("HasResult")),
            game_draws=row.get("GameDraws") or 0,
            competitors=tuple(competitors),
        ))
    return matches


def parse_standings_ranks(payload: dict) -> dict[str, int]:
    ranks = {}
    for row in payload.get("data", []):
        for player in row.get("Team", {}).get("Players", []):
            ranks[player["Username"]] = row["Rank"]
    return ranks


def round_number_for(melee_round: MeleeRound, swiss_rounds: int) -> int | None:
    top8_round_names = ("Quarterfinals", "Semifinals", "Finals")
    if melee_round.name in top8_round_names:
        return swiss_rounds + top8_round_names.index(melee_round.name) + 1
    match = re.fullmatch(r"Round (\d+)", melee_round.name)
    if match is None:
        return None
    return int(match.group(1))


def _first_decklist(competitor: dict) -> MeleeDecklist | None:
    for decklist in competitor.get("Decklists") or []:
        if decklist.get("DecklistId"):
            return MeleeDecklist(decklist_id=decklist["DecklistId"], name=decklist.get("DecklistName") or "")
    return None


def _matches_form() -> dict[str, str]:
    form = {
        "draw": "1", "start": "0", "length": "500",
        "search[value]": "", "search[regex]": "false",
        "order[0][column]": "0", "order[0][dir]": "asc",
    }
    for index, column in enumerate(("TableNumber", "PodNumber", "Teams", "Decklists", "ResultString")):
        form[f"columns[{index}][data]"] = column
        form[f"columns[{index}][name]"] = column
        form[f"columns[{index}][searchable]"] = "true"
        form[f"columns[{index}][orderable]"] = "true"
        form[f"columns[{index}][search][value]"] = ""
        form[f"columns[{index}][search][regex]"] = "false"
    return form


def _standings_form(round_id: int, top: int) -> dict[str, str]:
    return {
        "draw": "1", "start": "0", "length": str(top), "roundId": str(round_id),
        "search[value]": "", "search[regex]": "false",
        "order[0][column]": "0", "order[0][dir]": "asc",
        "columns[0][data]": "Rank", "columns[0][name]": "Rank", "columns[0][searchable]": "true",
        "columns[0][orderable]": "true", "columns[0][search][value]": "", "columns[0][search][regex]": "false",
    }
