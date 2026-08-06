"""Print the Set Awards from DATABASE_URL using the shared service logic. Read-only.

    DATABASE_URL=postgresql://... python -m bot.scripts.set_awards_results [--set CODE]

Runs the same `bot.services.set_awards` math the live `/set-awards` command uses, so the preview
here matches the ceremony.
"""
from __future__ import annotations

import argparse

from sqlalchemy import select

from bot.database import SessionLocal
from bot.models import MagicSet
from bot.services import set_awards as svc
from bot.sets import ALL_SETS, active_set_code

AWARD_NAMES = {
    "first_striker": "First Striker",
    "seize_the_day": "Seize the Day",
    "climber": "The Climber",
    "specialist": "The Specialist",
    "revel_in_riches": "Revel in Riches",
    "mvp": "Most Valuable Pod-Drafter",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", dest="set_code", default=None)
    args = parser.parse_args()

    code = (args.set_code or active_set_code()).upper()
    seed = next((s for s in ALL_SETS if s.code == code), None)
    if seed is None:
        raise SystemExit(f"set {code!r} not in ALL_SETS")

    with SessionLocal() as session:
        mset = session.execute(select(MagicSet).where(MagicSet.code == code)).scalar_one_or_none()
        if mset is None:
            raise SystemExit(f"set {code!r} not registered in DB")
        ranked = svc.compute_db_awards(session, mset, seed)

    winners, runners = svc.assign(ranked)
    print(f"\n{'='*78}\n  SET AWARDS — {code} ({seed.name})\n{'='*78}")
    for key in svc.CEREMONY_ORDER:
        print(f"\n  {AWARD_NAMES[key]}")
        winner = winners.get(key)
        print(f"    🥇 {winner.display_name} — {_plain(winner.detail)}" if winner else "    🥇 (no qualifier)")
        for runner in runners.get(key, []):
            print(f"    🥈 {runner.display_name} — {_plain(runner.detail)}")
    print()


def _plain(detail: str) -> str:
    return detail.replace("**", "")


if __name__ == "__main__":
    main()
