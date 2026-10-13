"""Mirror a fantasy event's field and Melee results into the fantasy tables, idempotently"""
from __future__ import annotations

import json
import logging
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from bot.models import FantasyEvent as FantasyEventRow
from bot.models import FantasyBracketPick, FantasyPick, FantasyPlayer, FantasyResult, FantasyRound
from bot.services.fantasy_event import (
    BRACKET_FEEDS,
    QUARTERFINAL_BY_LOWER_SEED,
    STAGE_FINAL,
    STAGE_QUARTERFINAL,
    STAGE_SEMIFINAL,
    FantasyEvent,
)
from bot.services.melee import MeleeClient, MeleeMatch, MeleeRound, round_number_for
from bot.slug import disambiguate_slug, slugify

log = logging.getLogger(__name__)


@dataclass
class SyncSummary:
    event_code: str
    rounds_synced: list[int] = field(default_factory=list)
    results_written: int = 0
    players_seeded: int = 0
    players_added: list[str] = field(default_factory=list)
    players_removed: list[str] = field(default_factory=list)
    unseeded_quarterfinals: bool = False


def sync_event(
    session: Session, event: FantasyEvent, client: MeleeClient, *, through_round: int | None = None,
    full: bool = False,
) -> SyncSummary:
    summary = SyncSummary(event_code=event.code)
    upsert_event_row(session, event)
    summary.players_seeded = seed_field(session, event)
    summary.players_removed = remove_withdrawn_players(session, event)
    roster = PlayerRoster.load(session, event.code)
    latest_stored = session.scalar(
        select(func.max(FantasyResult.round_number)).where(FantasyResult.event_code == event.code)
    ) or 0
    bracket_positions = _stored_bracket_positions(session, event.code)
    bracket_positions_before = bool(bracket_positions)
    melee_rounds = client.pairing_rounds(event.melee_tournament_id)

    for melee_round in melee_rounds:
        number = round_number_for(melee_round, event.swiss_rounds)
        if number is None or not melee_round.started:
            continue
        if through_round is not None and number > through_round:
            continue
        if not full and number < latest_stored:
            continue
        record_round_start(session, event, number)
        matches = client.round_matches(melee_round.round_id)
        is_quarterfinal = event.stage_for_round(number) == STAGE_QUARTERFINAL
        quarterfinal_positions = None
        if is_quarterfinal:
            quarterfinal_positions = _seeded_quarterfinals(event, client, melee_rounds, matches)
        rows = results_for_round(event, number, matches, roster, bracket_positions, quarterfinal_positions)
        if is_quarterfinal and quarterfinal_positions is None:
            summary.unseeded_quarterfinals = bool(rows) and not bracket_positions_before
        if matches and all(match.has_result for match in matches):
            record_round_completed(session, event.code, number)
        if number <= event.swiss_rounds and event.format_for_round(number) == "constructed":
            roster.record_decks(matches)
        _upsert_results(session, rows)
        summary.rounds_synced.append(number)
        summary.results_written += len(rows)

    summary.players_added = roster.added
    session.execute(
        FantasyEventRow.__table__.update()
        .where(FantasyEventRow.code == event.code)
        .values(synced_at=datetime.now(timezone.utc))
    )
    session.commit()
    log.info(
        f"fantasy-sync: {event.code} rounds={summary.rounds_synced} results={summary.results_written} "
        f"seeded={summary.players_seeded} added={len(summary.players_added)}"
    )
    return summary


def record_round_start(session: Session, event: FantasyEvent, round_number: int) -> None:
    columns = {event.cut_round + 1: "day_two_started_at", event.swiss_rounds + 1: "top8_started_at"}
    column = columns.get(round_number)
    if column is None:
        return
    session.execute(
        FantasyEventRow.__table__.update()
        .where(FantasyEventRow.code == event.code, getattr(FantasyEventRow, column).is_(None))
        .values({column: datetime.now(timezone.utc)})
    )


def record_round_completed(session: Session, event_code: str, round_number: int) -> None:
    statement = insert(FantasyRound).values(
        event_code=event_code, round_number=round_number, completed_at=datetime.now(timezone.utc),
    )
    session.execute(statement.on_conflict_do_nothing(index_elements=["event_code", "round_number"]))


def upsert_event_row(session: Session, event: FantasyEvent) -> None:
    values = {
        "code": event.code,
        "name": event.name,
        "melee_tournament_id": event.melee_tournament_id,
        "picks_lock_at": event.picks_lock_at,
        "swiss_rounds": event.swiss_rounds,
        "cut_round": event.cut_round,
        "draft_rounds": list(event.draft_rounds),
        "bracket_lock_at": event.bracket_lock_at,
    }
    statement = insert(FantasyEventRow).values(**values)
    updates = {key: statement.excluded[key] for key in values if key != "code"}
    session.execute(statement.on_conflict_do_update(index_elements=["code"], set_=updates))


def seed_field(session: Session, event: FantasyEvent) -> int:
    if event.field_seed is None or not event.field_seed.exists():
        return 0
    invitees = json.loads(event.field_seed.read_text())
    taken = set(session.scalars(select(FantasyPlayer.slug).where(FantasyPlayer.event_code == event.code)))
    seeded = 0
    for invitee in invitees:
        slug = slugify(fold_name(f"{invitee['firstName']} {invitee['lastName']}"))
        values = {
            "first_name": invitee["firstName"],
            "last_name": invitee["lastName"],
            "country": invitee.get("country"),
            "country_code": invitee.get("countryCode"),
            "sources": invitee.get("sources", []),
            "photo_url": invitee.get("photoUrl"),
            "melee_username": invitee.get("meleeUsername"),
        }
        statement = insert(FantasyPlayer).values(event_code=event.code, slug=slug, **values)
        updates = {key: statement.excluded[key] for key in values}
        updates["melee_username"] = func.coalesce(statement.excluded.melee_username, FantasyPlayer.melee_username)
        session.execute(statement.on_conflict_do_update(index_elements=["event_code", "slug"], set_=updates))
        if slug not in taken:
            taken.add(slug)
            seeded += 1
    session.flush()
    return seeded


def remove_withdrawn_players(session: Session, event: FantasyEvent) -> list[str]:
    if event.field_seed is None or not event.field_seed.exists():
        return []
    seeded_slugs = set()
    for invitee in json.loads(event.field_seed.read_text()):
        seeded_slugs.add(slugify(fold_name(f"{invitee['firstName']} {invitee['lastName']}")))
    candidates = session.scalars(
        select(FantasyPlayer).where(
            FantasyPlayer.event_code == event.code,
            FantasyPlayer.slug.not_in(seeded_slugs),
            ~exists().where(FantasyPick.event_code == event.code, FantasyPick.player_id == FantasyPlayer.id),
            ~exists().where(
                FantasyBracketPick.event_code == event.code, FantasyBracketPick.winner_id == FantasyPlayer.id,
            ),
            ~exists().where(FantasyResult.event_code == event.code, FantasyResult.player_id == FantasyPlayer.id),
        )
    ).all()
    removed = []
    for player in candidates:
        removed.append(f"{player.first_name} {player.last_name}")
        session.delete(player)
    session.flush()
    if removed:
        log.info(f"fantasy-sync: {event.code} removed players no longer in the seed: {', '.join(removed)}")
    return removed


def results_for_round(
    event: FantasyEvent, round_number: int, matches: list[MeleeMatch], roster: "PlayerRoster",
    bracket_positions: dict[int, str], quarterfinal_positions: dict[str, str] | None = None,
) -> list[dict]:
    stage = event.stage_for_round(round_number)
    match_format = event.format_for_round(round_number)
    rows = []
    for match in matches:
        if not match.has_result or not match.competitors:
            continue
        player_ids = [roster.resolve(competitor.username, competitor.display_name) for competitor in match.competitors]
        position = _bracket_position(stage, match, player_ids, bracket_positions, quarterfinal_positions)
        for index, competitor in enumerate(match.competitors):
            opponent = match.competitors[1 - index] if not match.is_bye else None
            opponent_wins = opponent.game_wins if opponent is not None else 0
            row = {
                "event_code": event.code,
                "round_number": round_number,
                "player_id": player_ids[index],
                "opponent_id": player_ids[1 - index] if opponent is not None else None,
                "stage": stage,
                "format": match_format,
                "result": _result(competitor.game_wins, opponent_wins, match.is_bye),
                "game_wins": competitor.game_wins,
                "game_losses": opponent_wins,
                "game_draws": match.game_draws,
                "is_bye": match.is_bye,
                "bracket_position": position,
                "melee_match_guid": match.guid,
            }
            rows.append(row)
            if position is not None:
                bracket_positions[player_ids[index]] = position
    return rows


class PlayerRoster:
    def __init__(self, session: Session, event_code: str, players: list[FantasyPlayer]):
        self.session = session
        self.event_code = event_code
        self.added: list[str] = []
        self._by_username: dict[str, FantasyPlayer] = {}
        self._by_name: dict[str, FantasyPlayer] = {}
        self._slugs = {player.slug for player in players}
        for player in players:
            self._index(player)

    @classmethod
    def load(cls, session: Session, event_code: str) -> "PlayerRoster":
        players = list(session.scalars(select(FantasyPlayer).where(FantasyPlayer.event_code == event_code)))
        return cls(session, event_code, players)

    def resolve(self, username: str, display_name: str) -> int:
        player = self._by_username.get(username.lower())
        if player is None:
            player = self._by_name.get(fold_name(display_name))
            if player is not None and player.melee_username is None:
                player.melee_username = username
                self._by_username[username.lower()] = player
        if player is None:
            player = self._add(username, display_name)
        return player.id

    def record_decks(self, matches: list[MeleeMatch]) -> None:
        for match in matches:
            for competitor in match.competitors:
                player = self._by_username.get(competitor.username.lower())
                if player is None or competitor.decklist is None:
                    continue
                player.deck_name = competitor.decklist.name
                player.decklist_id = competitor.decklist.decklist_id

    def _add(self, username: str, display_name: str) -> FantasyPlayer:
        first_name, _, last_name = display_name.strip().rpartition(" ")
        if not first_name:
            first_name, last_name = last_name, ""
        slug = disambiguate_slug(slugify(fold_name(display_name)), self._slugs)
        player = FantasyPlayer(
            event_code=self.event_code, slug=slug, first_name=first_name, last_name=last_name,
            melee_username=username,
        )
        self.session.add(player)
        self.session.flush()
        self._slugs.add(slug)
        self._index(player)
        self.added.append(display_name)
        log.info(f"fantasy-sync: {self.event_code} added {display_name!r} ({username}) from Melee")
        return player

    def _index(self, player: FantasyPlayer) -> None:
        if player.melee_username:
            self._by_username[player.melee_username.lower()] = player
        self._by_name[fold_name(f"{player.first_name} {player.last_name}")] = player


def fold_name(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(ascii_only.lower().split())


def _result(game_wins: int, opponent_wins: int, is_bye: bool) -> str:
    if is_bye or game_wins > opponent_wins:
        return "W"
    if game_wins < opponent_wins:
        return "L"
    return "D"


def _bracket_position(
    stage: str, match: MeleeMatch, player_ids: list[int], bracket_positions: dict[int, str],
    quarterfinal_positions: dict[str, str] | None,
) -> str | None:
    if stage == STAGE_QUARTERFINAL:
        if quarterfinal_positions is not None:
            return quarterfinal_positions[match.guid]
        return f"QF{match.table_number}"
    if stage == STAGE_FINAL:
        return "F"
    if stage != STAGE_SEMIFINAL:
        return None
    for player_id in player_ids:
        quarterfinal = bracket_positions.get(player_id)
        for semifinal in ("SF1", "SF2"):
            if quarterfinal in BRACKET_FEEDS[semifinal]:
                return semifinal
    return f"SF{match.table_number}"


def _seeded_quarterfinals(
    event: FantasyEvent, client: MeleeClient, melee_rounds: list[MeleeRound], matches: list[MeleeMatch],
) -> dict[str, str] | None:
    last_swiss = None
    for melee_round in melee_rounds:
        if round_number_for(melee_round, event.swiss_rounds) == event.swiss_rounds:
            last_swiss = melee_round
    if last_swiss is None:
        return None
    ranks = client.standings_ranks(last_swiss.round_id, top=8)
    positions = {}
    for match in matches:
        lower_seed = 0
        for competitor in match.competitors:
            lower_seed = max(lower_seed, ranks.get(competitor.username, 0))
        position = QUARTERFINAL_BY_LOWER_SEED.get(lower_seed)
        if position is None or position in positions.values():
            log.warning(f"fantasy-sync: {event.code} lower seed {lower_seed} fits no quarterfinal, using tables")
            return None
        positions[match.guid] = position
    return positions


def _stored_bracket_positions(session: Session, event_code: str) -> dict[int, str]:
    rows = session.execute(
        select(FantasyResult.player_id, FantasyResult.bracket_position)
        .where(FantasyResult.event_code == event_code, FantasyResult.stage == STAGE_QUARTERFINAL)
    ).all()
    positions = {}
    for player_id, position in rows:
        positions[player_id] = position
    return positions


def _upsert_results(session: Session, rows: list[dict]) -> None:
    if not rows:
        return
    statement = insert(FantasyResult).values(rows)
    keys = ("event_code", "round_number", "player_id")
    updates = {column: statement.excluded[column] for column in rows[0] if column not in keys}
    updates["updated_at"] = func.now()
    session.execute(statement.on_conflict_do_update(index_elements=list(keys), set_=updates))
