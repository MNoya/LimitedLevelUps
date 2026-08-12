# Pod Seeding — round-table image

Replace the ASCII "octagon" seating diagram with a **generated PNG**, attached to the seeding message.
Resume-from-cold spec. Nothing here is committed yet; the user commits at the end.

## Why

The seeding embed shows a monospace ASCII octagon of the 8 seats. It renders fine on desktop but
**breaks on mobile**: the arrow glyphs (`↗ ↘ ↙ ↖ ↑ ↓ → ←`) render wider than ASCII and mobile's code
block is narrower, so lines wrap (`3 jimbo` splits) and the box borders mangle. Monospace art can't be
made reliable across Discord clients. A rasterized image renders identically everywhere.

## Decision (locked)

- **Approach:** generate a PNG server-side with **Pillow**, attach it to the message.
- **Fanciness:** "round table + rank styling" — a circular/octagonal table with 8 seat nodes, each
  showing **name + #seed**, **arrows** tracing seat order (clockwise from seat 1), plus visual seed cues
  (medal colors / highlight for the top seeds) and a subtle table-felt background. **No avatars** (that
  was a separate, more-work option we did not pick).
- **Font:** do **not** rely on system fonts (Railway prod may lack them). **Commit a TTF** into the repo
  (e.g. `DejaVuSans.ttf` + a bold variant, ~700 KB each, already present on the dev box at
  `/usr/share/fonts/truetype/dejavu/`) and load by path.
- **Dependency:** add `Pillow` to `requirements.txt`.

## Current state (what exists now, all in `bot/commands/pod_draft.py` unless noted)

The seeding table and the (to-be-replaced) ASCII octagon share one builder, used by `/pod-seeding`, the
Settings → Leaderboard trigger, and `!test seeding`.

- `_build_seeding_embed(yes, maybe) -> discord.Embed` — the **table** embed (title `🏆 Pod Seeding · SOS`).
  Yes list is seated by rank (top-8 fill the ring via `seated_ring_order`), shows a leading **🪑 seat**
  column + `Rnk/Player/Pts/🏆`, cut line after 8. Maybe list has no seat column. **Keep this.**
- `_seating_octagon_text(yes) -> str | None` — returns the boxed ASCII octagon as a ``` code block ```,
  or `None` unless exactly 8 seated. **This is what the image replaces.**
- `_seating_octagon(seated) -> str` — builds the ASCII octagon (the thing that breaks on mobile).
  **Remove once the image lands.** `_ring_trunc` is only used by it.
- `build_seeding_message_from_names(yes, maybe) -> (content, embed)` — public; used by `!test seeding`.
- `seating_message_for_event(bot, event_id) -> (content, embed)` — fetches sesh RSVPs, seeds, returns the
  octagon text + table embed. `(None, None)` on no sesh / no RSVPs.
- `SeededAttendee` (`bot/services/player_stats.py`): `slug, display_name, rank, score, trophies`.
- `seated_ring_order(items)` (`player_stats.py`): pure ring permutation — top half in order, bottom half
  reversed, swap seats 3↔4 / 5↔6 for an 8-pod. Works on any list (names or `SeededAttendee`).
- `seed_attendees(session, names)` (`player_stats.py`): names → `SeededAttendee` list, rank order,
  unranked to the bottom.

### Send sites (today: embed first, then octagon text as a SECOND message)

1. `/pod-seeding` command — `pod_draft.py` (search `pod-seeding:` log line): `followup.send(embed=...)`
   then `followup.send(content=octagon)`.
2. `on_seating_table` closure in `pod_settings` command — `pod_draft.py:136`.
3. `on_seating_table` closure in the lobby Settings button — `bot/services/lobby_embed.py` (local import
   of `seating_message_for_event` to dodge the import cycle).
4. `_post_test_seeding` in `bot/commands/testlobby.py` (the `!test seeding` state).

## Implementation plan

1. **Dep + font.** Add `Pillow>=10,<12` to `requirements.txt`. Commit `DejaVuSans.ttf` (+ `-Bold`) under
   e.g. `bot/assets/fonts/`. `.venv/bin/pip install -r requirements.txt`.

2. **New module `bot/services/pod_seating_image.py`:**
   - `render_seating_png(seated: list[SeededAttendee]) -> bytes | None` — returns PNG bytes for a clean
     8-seat table; `None` for non-8 (same gating as the octagon today, multi-pod is out of scope).
   - Pure Pillow: fixed canvas (e.g. ~900×600 @ 2x for crispness), draw the table background, place 8 seat
     nodes evenly on a circle (seat 1 at top, clockwise), each node = name + `#seed`, arrows between
     consecutive seats, medal/﻿highlight styling for the top seeds. Load fonts by path from the bundled TTF.
   - Keep it deterministic and side-effect free (no network, no avatar fetch).

3. **Wire into the message.** Recommended: drop the separate text message and put the image **inside the
   table embed at the bottom** via `embed.set_image(url="attachment://seating.png")` + send the
   `discord.File(io.BytesIO(png), "seating.png")` with the embed — single message, image renders after the
   table. (Alternative kept for reference: a second message with just the file.)
   - Change `seating_message_for_event` / `build_seeding_message_from_names` to return
     `(discord.File | None, discord.Embed)` instead of `(text, embed)`; set the embed image when a file
     exists. Update all 4 send sites to `send(embed=embed, file=file)` (guard `file is None`).
   - `discord.File` precedent: `bot/commands/signup.py:281`.

4. **Remove** `_seating_octagon`, `_seating_octagon_text`, `_ring_trunc` once the image path works.

5. **Tests.** Logic only (per repo convention — no pixel asserts): a smoke test that
   `render_seating_png(<8 seeded>)` returns non-empty `bytes` and `None` for non-8. Existing
   `test_pod_seeding.py` covers the table/`_seeding_block`; keep it green.

## Verify locally

`!test seeding` (owner-only, local DB) posts the seeding message from the local top-8 leaderboard — now
with the image. Confirm it renders on **both desktop and mobile** (the whole point). `/pod-seeding` needs
a real sesh with RSVPs; `!test seeding` bypasses that.

## Notes / caveats

- Image generation is trivial CPU for 8 nodes; generate on demand, nothing persisted.
- Verify Pillow installs cleanly on Railway (Linux wheel; it does). Fonts come from the repo, not the OS.
- Keep the table embed as the source of truth for names/seeds; the image is the spatial view.
- The seat-ordering math (`seated_ring_order`) is done — the image just draws whatever order it returns.
