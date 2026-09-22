import json
import re
import sys
import time
import urllib.request

USAGE = """Bake sealeddeck archetype pools into a SKELETON_SEEDS block for skeletons.ts.

Reads "COLORS: URL_OR_POOLID" lines from stdin, one per color pair, and prints
the TypeScript block for the given set code. Color codes are normalized to WUBRG.

    python bake_skeletons.py FRA < pools.txt

Each line looks like:
    UW: https://sealeddeck.tech/sets/fra/bWzk9SpyZv
    UB: pdFsnuxH13
"""

POOL_API = "https://sealeddeck.tech/api/pools/{pool}?columns=true"
SCRYFALL_COLLECTION = "https://api.scryfall.com/cards/collection"
HEADERS = {"User-Agent": "llu-skeleton-baker", "Accept": "application/json"}


def wubrg(colors):
    order = {c: i for i, c in enumerate("WUBRG")}
    return "".join(sorted(colors.upper(), key=lambda c: order[c]))


def pool_id(value):
    match = re.search(r"([A-Za-z0-9]+)\s*$", value.strip().rstrip("/"))
    return match.group(1) if match else value.strip()


def parse_lines(text):
    pairs = []
    for line in text.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        colors, value = line.split(":", 1)
        pairs.append((wubrg(colors.strip()), pool_id(value)))
    return pairs


def get_json(url, data=None):
    headers = dict(HEADERS)
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req) as response:
        return json.load(response)


def flatten(columns, cards):
    names = []
    for column in columns:
        for card_id in column["cardIds"]:
            names.append(cards[card_id]["name"])
    return names


def scryfall_cmc(names):
    front = {name: name.split(" // ")[0].strip() for name in names}
    unique = sorted(set(front.values()))
    cmc = {}
    for i in range(0, len(unique), 75):
        chunk = unique[i:i + 75]
        body = json.dumps({"identifiers": [{"name": n} for n in chunk]}).encode()
        data = get_json(SCRYFALL_COLLECTION, data=body)
        for card in data.get("data", []):
            cmc[card["name"].split(" // ")[0].strip()] = int(card.get("cmc", 0))
        for miss in data.get("not_found", []):
            print(f"NOT FOUND on Scryfall: {miss}", file=sys.stderr)
        time.sleep(0.1)
    return {name: cmc.get(front[name], 0) for name in names}


def emit_rows(names, cmc):
    rows = []
    for name in names:
        escaped = name.replace('"', '\\"')
        rows.append(f'        ["{escaped}", {cmc[name]}],')
    return "\n".join(rows)


def bake(set_code, pairs):
    blocks = []
    for colors, pool in pairs:
        pool_data = get_json(POOL_API.format(pool=pool))
        cards = pool_data["cards"]
        top = flatten(pool_data["deck"]["columns"], cards)
        split = flatten(pool_data["deck"]["splitColumns"], cards)
        cmc = scryfall_cmc(top + split)
        blocks.append(
            f"""    {{
      colors: "{colors}",
      poolId: "{pool}",
      cards: [
{emit_rows(top, cmc)}
      ],
      splitCards: [
{emit_rows(split, cmc)}
      ],
    }},"""
        )
    body = "\n".join(blocks)
    return f"  {set_code.upper()}: [\n{body}\n  ],"


def main():
    if len(sys.argv) != 2:
        print(USAGE, file=sys.stderr)
        sys.exit(1)
    pairs = parse_lines(sys.stdin.read())
    if not pairs:
        print("No 'COLORS: URL' lines on stdin", file=sys.stderr)
        sys.exit(1)
    print(bake(sys.argv[1], pairs))


if __name__ == "__main__":
    main()
