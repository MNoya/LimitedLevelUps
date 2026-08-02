"""Parse a Draftmancer draft log.

Two modes:
    dump   — print every booster as human-readable card names
    pack   — emit a compact JSON form suitable for archival

Usage:
    python -m bot.scripts.draftmancer_log dump  /path/to/DraftLog.txt
    python -m bot.scripts.draftmancer_log pack  /path/to/DraftLog.txt  out.json[.gz]
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path


def load(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def name_of(card: dict) -> str:
    return card.get("name", "?")


def cmd_dump(log: dict) -> None:
    cards = log["carddata"]
    for seat_idx, (_, user) in enumerate(log["users"].items()):
        print(f"\n=== Seat {seat_idx}: {user['userName']} ===")
        for pick in user["picks"]:
            pack, num = pick["packNum"], pick["pickNum"]
            booster = [name_of(cards[cid]) for cid in pick["booster"]]
            chosen = [booster[i] for i in pick["pick"]]
            print(f"P{pack + 1}P{num + 1:02d}  pool({len(booster):2d})  pick={', '.join(chosen)}")
            for i, name in enumerate(booster):
                marker = "*" if i in pick["pick"] else " "
                print(f"        {marker} [{i:2d}] {name}")


PASS_DIRS = (+1, -1, +1)


def build_compact(log: dict) -> dict:
    """Self-sufficient draft artifact: card table indexed by position, plus packs, picks, and built
    decks expressed as those indices. The 36-char Draftmancer id is intentionally omitted — every
    reference is positional, and the high-entropy id roughly doubles the gzipped size."""
    cards = log["carddata"]
    ids = sorted(cards.keys())
    idx = {cid: i for i, cid in enumerate(ids)}

    seats: list[str] = []
    picks_by_seat: list[list[list[int]]] = []
    decks: list[dict[str, list[int]]] = []
    for user in log["users"].values():
        seats.append(user["userName"])
        per_pack: list[list[int]] = [[] for _ in range(3)]
        for p in user["picks"]:
            per_pack[p["packNum"]].extend(p["pick"])
        picks_by_seat.append(per_pack)
        decklist = user.get("decklist") or {}
        main = [idx[cid] for cid in (decklist.get("main") or []) if cid in idx]
        side = [idx[cid] for cid in (decklist.get("side") or []) if cid in idx]
        decks.append({"main": main, "side": side})

    packs = [[idx[cid] for cid in b] for b in log["boosters"]]
    card_table = [
        {
            "n": cards[cid].get("name"),
            "cn": cards[cid].get("collector_number"),
            "s": cards[cid].get("set"),
            "r": cards[cid].get("rarity"),
            "c": cards[cid].get("colors"),
            "cmc": cards[cid].get("cmc"),
            "type": cards[cid].get("type"),
        }
        for cid in ids
    ]
    return {
        "v": 2,
        "sid": log.get("sessionID"),
        "t": log.get("time"),
        "set": (log.get("setRestriction") or [None])[0],
        "seats": seats,
        "cards": card_table,
        "packs": packs,
        "picks": picks_by_seat,
        "pp": picks_per_turn(log),
        "decks": decks,
    }


def picks_per_turn(log: dict) -> int:
    """Cards each seat takes before passing. A Pick 2 turn records two positions in one booster, and
    picks_by_seat flattens them, so the count is what tells the two forms apart when replaying."""
    most = 1
    for user in log["users"].values():
        for p in user["picks"]:
            most = max(most, len(p["pick"]))
    return most


def simulate(compact: dict) -> list[list[list[int]]]:
    n_seats = len(compact["seats"])
    packs = compact["packs"]
    picks = compact["picks"]
    per_turn = compact.get("pp", 1)
    out: list[list[list[int]]] = [[[] for _ in range(3)] for _ in range(n_seats)]
    for pack_num in range(3):
        booster_at: list[list[int]] = [list(packs[seat + pack_num * n_seats]) for seat in range(n_seats)]
        direction = PASS_DIRS[pack_num]
        turns = len(picks[0][pack_num]) // per_turn
        for turn in range(turns):
            taken: list[list[int]] = []
            for seat in range(n_seats):
                positions = picks[seat][pack_num][turn * per_turn:(turn + 1) * per_turn]
                taken.append([booster_at[seat][pos] for pos in positions])
                for pos in sorted(positions, reverse=True):
                    booster_at[seat].pop(pos)
            for seat, cards in enumerate(taken):
                out[seat][pack_num].extend(cards)
            booster_at = [booster_at[(seat - direction) % n_seats] for seat in range(n_seats)]
    return out


def cmd_pack(log: dict, out: Path) -> None:
    compact = build_compact(log)
    data = json.dumps(compact, separators=(",", ":")).encode()
    if out.suffix == ".gz":
        out.write_bytes(gzip.compress(data, compresslevel=9))
    else:
        out.write_bytes(data)
    print(f"wrote {out} ({out.stat().st_size:,} bytes)", file=sys.stderr)


def cmd_verify(log: dict) -> int:
    compact = build_compact(log)
    ids = sorted(log["carddata"].keys())
    seats = list(log["users"].values())
    n_seats = len(seats)

    original: list[list[list[str]]] = [[[] for _ in range(3)] for _ in range(n_seats)]
    for i, user in enumerate(seats):
        for p in sorted(user["picks"], key=lambda pick: (pick["packNum"], pick["pickNum"])):
            original[i][p["packNum"]].extend(p["booster"][k] for k in p["pick"])

    sim = simulate(compact)
    fails = 0
    for i, user in enumerate(seats):
        for pn in range(3):
            for k, want in enumerate(original[i][pn]):
                got = ids[sim[i][pn][k]]
                if got != want:
                    fails += 1
                    print(f"  seat {i} ({user['userName']}) P{pn + 1}P{k + 1:02d}: want {want[:8]} got {got[:8]}")
        picked_ids = sorted(ids[card] for pn in range(3) for card in sim[i][pn])
        pool_ids = sorted(user["cards"])
        if picked_ids != pool_ids:
            fails += 1
            print(f"  seat {i} ({user['userName']}): final pool multiset mismatch")
    if fails == 0:
        picks_per_pack = len(original[0][0])
        print(f"OK — {n_seats} seats × 3 packs × {picks_per_pack} picks reconstructed losslessly")
    else:
        print(f"FAIL — {fails} mismatch(es)")
    return fails


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    pd = sub.add_parser("dump")
    pd.add_argument("path", type=Path)
    pp = sub.add_parser("pack")
    pp.add_argument("path", type=Path)
    pp.add_argument("out", type=Path)
    pv = sub.add_parser("verify")
    pv.add_argument("path", type=Path)
    args = p.parse_args()

    log = load(args.path)
    if args.cmd == "dump":
        cmd_dump(log)
    elif args.cmd == "pack":
        cmd_pack(log, args.out)
    else:
        sys.exit(1 if cmd_verify(log) else 0)


if __name__ == "__main__":
    main()
