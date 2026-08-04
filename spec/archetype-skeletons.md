# Archetype Skeletons

What the feature is, and the exact procedure for adding a set's skeletons. Read this before touching `frontend/src/data/skeletons.ts` — the sealeddeck endpoint it depends on is undocumented and two of its behaviors are easy to get wrong.

## What a skeleton is

Marc builds one sealeddeck pool per two-color archetype: the short list of cards that carry that pair. The cards above sealeddeck's horizontal divider are the core commons; the cards below are the signpost uncommons plus the commons that matter to the strategy. A skeleton is written once when the set previews and is never revised, which is why the lists are baked into the repo instead of fetched from sealeddeck on every page view.

## Where it renders

The Tier List page carries an `ARCHETYPES` button beside the set title, shown only for sets that have skeletons. It opens `/tier-list/:setCode/archetypes`, which is `SkeletonsModal`: mana value columns of fanned cards, the two halves of the split separated by a full-width divider, prev/next stepping the archetypes. Hovering a card lifts it; clicking or right-clicking one opens the big card with its 17lands grade, which appears once the set has an entry in `TIER_LIST_UIDS` or `TIER_LIST_GRADERS`.

A phone fits two mana values across, so the columns reflow into a two-wide grid there. Stepping the pairs sits under the panel in both layouts, as a pill bar holding one pip chip per archetype, with the prev/next arrows alongside them on desktop only.

Card art comes from `/api/card-images`, so nothing calls Scryfall at runtime.

## Adding a set

Marc supplies one sealeddeck URL per color pair:

```
UW: https://sealeddeck.tech/sets/hob/meuRkRJix5
RB: https://sealeddeck.tech/sets/hob/ywz5ZRxnz1
...
```

The trailing path segment is the pool ID. Fill in `POOLS` and `SET` below, run it, and paste the output as a new entry in `SKELETON_SEEDS` keyed by the set code. Nothing else needs to change — the button and route light up on their own.

```python
import json, urllib.request, time

SET = "hob"
POOLS = [("WU", "meuRkRJix5"), ("BR", "ywz5ZRxnz1"), ("BG", "mWKhTYSL5x"),
         ("WR", "1rsV9yhVb9"), ("UG", "kkBNLoDQBD")]

front = lambda n: n.split(" // ")[0].strip()

for pips, pool_id in POOLS:
    d = json.load(urllib.request.urlopen(f"https://sealeddeck.tech/api/pools/{pool_id}?columns=true"))
    names = {cid: front(c["name"]) for cid, c in d["cards"].items()}
    halves = {k: [names[cid] for col in d["deck"][k] for cid in col["cardIds"]]
              for k in ("columns", "splitColumns")}
    body = {"identifiers": [{"name": n, "set": SET} for n in {*halves["columns"], *halves["splitColumns"]}]}
    req = urllib.request.Request(
        "https://api.scryfall.com/cards/collection", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "User-Agent": "LimitedLevelUps/1.0"})
    res = json.load(urllib.request.urlopen(req)); time.sleep(0.3)
    assert not res.get("not_found"), res["not_found"]
    cmc = {front(c["name"]): int(c["cmc"]) for c in res["data"]}
    fmt = lambda key: "\n".join(f'        ["{n}", {cmc[n]}],' for n in halves[key])
    print(f'    {{\n      colors: "{pips}",\n      poolId: "{pool_id}",\n      cards: [\n{fmt("columns")}\n      ],'
          f'\n      splitCards: [\n{fmt("splitColumns")}\n      ],\n    }},')
```

`colors` is the pair in WUBRG order, which is how `Pips` expects it, so `UW` becomes `WU` and `RW` becomes `WR`. Keep the entries in the order Marc lists them, since that is the order prev/next walks.

## Why it is written this way

- **`?columns=true` is the whole point.** The plain `/api/pools/<id>` response returns one flat `deck` array with no divider, so the split is invisible. Adding the query parameter returns `deck.columns` (above the divider), `deck.splitColumns` (below), and a `cards` id-to-name table. There is no other way to recover the split.
- **A stored column index is not a mana value.** Sealeddeck saves whatever columns Marc left behind, trims leading empty ones inconsistently between pools, and happily holds a 1-drop in a 2 column. Only the split is trustworthy, so `skeletonLayout` rebuilds the columns from each card's mana value. That is what keeps the two halves aligned column for column: a mana value only one half plays still holds an empty slot in the other. A mana value neither half plays drops out, so a single 7-drop sits one column past the 5s instead of pushing itself off the side of the panel. The mobile grid drops every empty column, since two-wide rows cannot align the halves anyway.
- **Names need the front face.** Sealeddeck spells a double-faced card `Gollum, Silent Slinker // Meager Meal`; splitting on `//` is what both Scryfall lookups and `/api/card-images` key on.
- **Scryfall's collection endpoint 400s** without `Accept` and `User-Agent` headers.
