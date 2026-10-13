"""Stage a finished event's real field and results as another event, frozen at any round, on a local database

    DATABASE_URL=postgresql://postgres:devpw@localhost:5433/dischord \\
        python -m bot.scripts.fantasy_dry_run --through-round 11 --revealed 10

Round 0 stages the picking phase, with the lock a day ahead.
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from bot.commands.test_group import HALL_OF_FAME
from bot.config import settings
from bot.database import SessionLocal
from bot.scripts.local_supabase_proxy import DEV_USER_ID
from bot.services.fantasy_event import BRACKET_FEEDS, FantasyEvent, event_for
from bot.services.fantasy_sync import seed_field, upsert_event_row

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("fantasy_dry_run")

SLOTS = ("captain", "drafter", "constructed", "player")
QUARTERFINALS = ("QF1", "QF2", "QF3", "QF4")
GAME_SCORES = ("3-0", "3-1", "3-2")
PLAYER_COLUMNS = (
    "slug, first_name, last_name, short_name, country, country_code, sources, photo_url, melee_username, "
    "deck_name, decklist_id"
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="WC31")
    parser.add_argument("--target", default="WC32")
    parser.add_argument("--through-round", type=int)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--revealed", type=int, default=None)
    parser.add_argument("--members", type=int, default=30)
    parser.add_argument("--field-seed", type=Path, default=Path("spec/fantasy-data/wc31_field.json"))
    args = parser.parse_args()

    if not any(host in settings.database_url for host in ("localhost", "127.0.0.1")):
        raise SystemExit("fantasy_dry_run rewrites an event's data, so it only runs against a local database")
    target = event_for(args.target)
    if target is None:
        raise SystemExit(f"no fantasy event {args.target!r} in fantasy_events.json")
    if args.reset:
        with SessionLocal() as session:
            seeded = reset_to_registry(session, target)
            session.commit()
        log.info(f"{args.target} reset to its registry entry and field seed: {seeded} players, no results or picks")
        return
    if args.through_round is None:
        parser.error("--through-round is required unless --reset is given")
    revealed = args.through_round if args.revealed is None else min(args.revealed, args.through_round)

    with SessionLocal() as session:
        id_map = copy_field(session, args.source, args.target)
        unmatched = apply_field_seed(session, args.target, args.field_seed)
        copied = copy_results(session, args.source, args.target, id_map, args.through_round)
        stage_timeline(session, target, args.through_round, revealed)
        rng = random.Random(args.through_round)
        names = {
            "captain": "Ha Pham",
            "sub": "Javier Dominguez",
            "drafter": "Arne Huschenbeth",
            "constructed": "Jean-Emmanuel Depraz",
            "player": "Simon Nielsen",
        }
        fixture = {role: player_named(session, args.target, name) for role, name in names.items()}
        seed_members(session, args.source, args.target, id_map, args.members, args.through_round, target, rng, fixture)
        session.commit()
    for name in unmatched:
        log.info(f"no Melee player for seed entry {name}")
    log.info(f"{args.target} now holds {args.source}'s field and {copied} results through round {args.through_round}, "
             f"revealed through {revealed}, with {args.members} members plus the dev user")


def reset_to_registry(session: Session, event: FantasyEvent) -> int:
    for table in ("fantasy_bracket_picks", "fantasy_picks", "fantasy_rounds", "fantasy_results", "fantasy_players"):
        session.execute(text(f"DELETE FROM {table} WHERE event_code = :target"), {"target": event.code})
    upsert_event_row(session, event)
    session.execute(
        text("UPDATE fantasy_events SET revealed_through_round = 0, day_two_started_at = NULL, top8_started_at = NULL "
             "WHERE code = :target"),
        {"target": event.code},
    )
    return seed_field(session, event)


def copy_field(session: Session, source: str, target: str) -> dict[int, int]:
    session.execute(text("DELETE FROM fantasy_bracket_picks WHERE event_code = :target"), {"target": target})
    session.execute(text("DELETE FROM fantasy_picks WHERE event_code = :target"), {"target": target})
    session.execute(text("DELETE FROM fantasy_rounds WHERE event_code = :target"), {"target": target})
    session.execute(text("DELETE FROM fantasy_players WHERE event_code = :target"), {"target": target})
    rows = session.execute(
        text(f"SELECT id, {PLAYER_COLUMNS} FROM fantasy_players WHERE event_code = :source ORDER BY id"),
        {"source": source},
    ).mappings().all()
    id_map = {}
    for row in rows:
        values = {key: row[key] for key in row.keys() if key != "id"}
        new_id = session.execute(
            text(f"INSERT INTO fantasy_players (event_code, {PLAYER_COLUMNS}) VALUES (:event_code, "
                 + ", ".join(f":{column.strip()}" for column in PLAYER_COLUMNS.split(",")) + ") RETURNING id"),
            {"event_code": target, **values},
        ).scalar_one()
        id_map[row["id"]] = new_id
    return id_map


def apply_field_seed(session: Session, target: str, seed_path: Path) -> list[str]:
    unmatched = []
    for entry in json.loads(seed_path.read_text()):
        name = f"{entry['firstName']} {entry['lastName']}"
        updated = session.execute(
            text("UPDATE fantasy_players SET first_name = :first, last_name = :last, country = :country, "
                 "country_code = :code, sources = :sources, photo_url = :photo "
                 "WHERE event_code = :target AND lower(melee_username) = lower(:username)"),
            {"first": entry["firstName"], "last": entry["lastName"], "country": entry["country"],
             "code": entry["countryCode"], "sources": entry["sources"], "photo": entry["photoUrl"],
             "username": entry["meleeUsername"] or "", "target": target},
        ).rowcount
        if not updated:
            unmatched.append(name)
    return unmatched


def copy_results(session: Session, source: str, target: str, id_map: dict[int, int], through_round: int) -> int:
    rows = session.execute(
        text("SELECT * FROM fantasy_results WHERE event_code = :source AND round_number <= :through"),
        {"source": source, "through": through_round},
    ).mappings().all()
    columns = (
        "event_code, round_number, player_id, opponent_id, stage, format, result, game_wins, game_losses, game_draws, "
        "is_bye, bracket_position, melee_match_guid"
    )
    placeholders = ", ".join(f":{column.strip()}" for column in columns.split(","))
    for row in rows:
        session.execute(
            text(f"INSERT INTO fantasy_results ({columns}) VALUES ({placeholders})"),
            {
                **row,
                "event_code": target,
                "player_id": id_map[row["player_id"]],
                "opponent_id": id_map.get(row["opponent_id"]) if row["opponent_id"] else None,
            },
        )
    return len(rows)


def stage_timeline(session: Session, event: FantasyEvent, through_round: int, revealed: int) -> None:
    now = datetime.now(timezone.utc)
    picking = through_round == 0
    for round_number in range(1, through_round + 1):
        completed_at = now - timedelta(hours=through_round - round_number + 1)
        session.execute(
            text("INSERT INTO fantasy_rounds (event_code, round_number, completed_at) VALUES (:target, :round, :at)"),
            {"target": event.code, "round": round_number, "at": completed_at},
        )
    top8_started = through_round > event.swiss_rounds
    session.execute(
        text("UPDATE fantasy_events SET picks_lock_at = :lock, revealed_through_round = :revealed, "
             "day_two_started_at = :day_two, top8_started_at = :top8, "
             "bracket_lock_at = :closes WHERE code = :target"),
        {
            "target": event.code,
            "lock": event.picks_lock_at if picking else now - timedelta(hours=through_round + 2),
            "revealed": revealed,
            "day_two": now if through_round > event.cut_round else None,
            "top8": now if top8_started else None,
            "closes": now - timedelta(minutes=10) if top8_started else bracket_lock(event, picking, now),
        },
    )


def bracket_lock(event: FantasyEvent, picking: bool, now: datetime) -> datetime:
    return event.bracket_lock_at if picking else now + timedelta(days=2)


def seed_members(
    session: Session, source: str, target: str, id_map: dict[int, int], count: int, through_round: int, event, rng,
    fixture: dict[str, int | None],
) -> None:
    standings = day_one_standings(session, target, event.cut_round)
    players = list(id_map.values())
    day_two = sorted(player for player, made_it in standings.items() if made_it)
    pairings = quarterfinal_pairings(session, source, id_map)
    names = rng.sample(HALL_OF_FAME, min(count, len(HALL_OF_FAME)))
    dev_user = uuid.UUID(DEV_USER_ID)
    members = [(uuid.uuid4(), name) for name in names] + [(dev_user, "Noya")]
    lock = datetime.now(timezone.utc) - timedelta(hours=through_round + 3)
    for order, (user_id, name) in enumerate(members):
        is_dev_user = user_id == dev_user and through_round > event.cut_round and day_two
        lineup = dev_user_lineup(day_two, rng, fixture) if is_dev_user else rng.sample(players, len(SLOTS))
        saved_at = lock - timedelta(minutes=order)
        for index, (slot, player_id) in enumerate(zip(SLOTS, lineup)):
            save_pick(session, user_id, target, slot, 1, player_id, saved_at)
            missed_day_two = through_round > event.cut_round and not standings.get(player_id, False)
            if not missed_day_two or not day_two:
                continue
            replaces = index == 0 if is_dev_user else rng.random() < 5 / 6
            if replaces:
                candidates = [player for player in day_two if player not in lineup]
                dev_sub = fixture["sub"]
                replacement = dev_sub if is_dev_user and dev_sub in candidates else rng.choice(candidates)
                save_pick(session, user_id, target, slot, event.cut_round + 1, replacement, saved_at)
        if through_round >= event.swiss_rounds and pairings:
            seed_bracket(session, user_id, target, pairings, rng, saved_at)
        session.execute(
            text("INSERT INTO fantasy_members (user_id, name) VALUES (:user_id, :name) "
                 "ON CONFLICT (user_id) DO UPDATE SET name = excluded.name"),
            {"user_id": user_id, "name": name},
        )


def dev_user_lineup(day_two: list[int], rng, fixture: dict[str, int | None]) -> list[int]:
    lineup = []
    for slot in SLOTS:
        others = [player for player in day_two if player not in fixture.values() and player not in lineup]
        lineup.append(fixture[slot] or rng.choice(others))
    return lineup


def player_named(session: Session, target: str, name: str) -> int | None:
    return session.execute(
        text("SELECT id FROM fantasy_players WHERE event_code = :target AND first_name || ' ' || last_name = :name"),
        {"target": target, "name": name},
    ).scalar()


def save_pick(session: Session, user_id, target: str, slot: str, from_round: int, player_id: int, at) -> None:
    session.execute(
        text("INSERT INTO fantasy_picks (user_id, event_code, slot, from_round, player_id, created_at, updated_at) "
             "VALUES (:user_id, :target, :slot, :from_round, :player_id, :at, :at)"),
        {"user_id": user_id, "target": target, "slot": slot, "from_round": from_round, "player_id": player_id,
         "at": at},
    )


def day_one_standings(session: Session, target: str, cut_round: int) -> dict[int, bool]:
    rows = session.execute(
        text("SELECT player_id, bool_or(round_number > :cut) AS made_it FROM fantasy_results "
             "WHERE event_code = :target GROUP BY player_id"),
        {"target": target, "cut": cut_round},
    ).all()
    return {player_id: made_it for player_id, made_it in rows}


def quarterfinal_pairings(session: Session, source: str, id_map: dict[int, int]) -> dict[str, tuple[int, int]]:
    rows = session.execute(
        text("SELECT bracket_position, player_id, opponent_id FROM fantasy_results "
             "WHERE event_code = :source AND stage = 'quarterfinal' AND player_id < opponent_id"),
        {"source": source},
    ).all()
    return {position: (id_map[player], id_map[opponent]) for position, player, opponent in rows}


def seed_bracket(session: Session, user_id, target: str, pairings: dict[str, tuple[int, int]], rng, at) -> None:
    winners = {}
    for position in QUARTERFINALS:
        if position in pairings:
            winners[position] = rng.choice(pairings[position])
    for position, feeders in BRACKET_FEEDS.items():
        if all(feeder in winners for feeder in feeders):
            winners[position] = rng.choice([winners[feeder] for feeder in feeders])
    for position, winner in winners.items():
        session.execute(
            text("INSERT INTO fantasy_bracket_picks (user_id, event_code, position, winner_id, games, created_at, "
                 "updated_at) VALUES (:user_id, :target, :position, :winner, :games, :at, :at)"),
            {"user_id": user_id, "target": target, "position": position, "winner": winner,
             "games": rng.choice(GAME_SCORES), "at": at},
        )


if __name__ == "__main__":
    main()
