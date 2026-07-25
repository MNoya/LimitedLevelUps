# Pod Launcher Rolling — Implementation Handoff

**Status: implemented.** The render layer and the rolling backend are both built. The living record is now `spec/pod-workflow.md` (Rolling columns, under the Daily poll section) for the engineering map and `spec/pod-coordination.md` for the player-facing behavior; `spec/pod-launcher-rolling.md` keeps the design intent. This doc is kept as the point-in-time build map that produced it — the render → data contract below is still the accurate description of what the snapshot must return.

Design intent lives in `spec/pod-launcher-rolling.md` (read it first — the model, the locked decisions, the open questions). This handoff is the build map on top of it. Living lifecycle docs: `spec/pod-workflow.md` (engineering map) and `spec/pod-coordination.md` (player guide). The broader pod redesign framing is `spec/pod-handoff.md`.

## What rolling is, in one paragraph

Each launcher slot (Early, Late) carries its own date and rolls forward to the next day the moment its pod finishes, so the board is never stale and interest never resets to zero overnight. "Which day" is a per-slot property, not a board property: a column can already be gathering for tomorrow while the other column still plays today. The board stays two columns; each column stacks a finished pod above the next day's gathering slot. A card keeps its posting-day identity for life; the next 11:00 post reposts fresh and adopts the pre-collected signups.

## What is DONE (this session) — the render + preview layer

All in the working tree, uncommitted, no tests written yet (per request — verify visually first).

- **`bot/services/pod_launcher_copy.py` (new).** All launcher-facing copy in one editable place: title, intro, `ARCHIVE_INTRO` (`### On This Day`), `FINISHED_MARK` (🏆), `PLAYING_MARK` (⚔️), `SECTION_NEXT` (`**Next**`), `NEXT_EMOJI` (`chordoHello`, an app emoji resolved by name), the Format Preference / Rank copy, and the Play Again strings. The shared Format Preference button label stays in `bot/commands/messages.py`.
- **`bot/services/pod_launch.py`.** `LauncherSlot` gained two fields: `winner: str | None` and `winner_slug: str | None`.
- **`bot/tasks/pod_daily_poll.py` — render rewrite.** `build_poll_embed` now renders **one inline field per bucket** (two columns), each column via `_column_value`: a single slot-name header (`💫 @Early Pod`), a finished section (one `_finished_line` per finished pod), then a Next section per gathering slot. Helpers: `_bucket_order`, `_bucket_slots` (stack earliest first), `_representative_slot` (one launcher button per bucket, targeting the open slot), `_finished_pad` + the `pad_finished` arg (blank-line padding so the `Next` rows align across columns of unequal Played height), `_slot_block` (championship lane + plain gathering column), `_finished_line` / `_finished_link_text`, `_card_url` (Discord thread/card jump) and `_pod_page_url` (website `/pods/<event-slug>/<winner-slug>`), `_archive_embed` (closed card = compact description list, no columns). `build_play_again_prompt` + `PlayAgainView` render the next-day CTA. Copy is imported from `pod_launcher_copy`.
- **`bot/commands/testpolls.py` — `!test rolling`.** Static previews from fixtures through the production builders: A fresh morning · B finished · B(playing) · C full 2×2 · C multi-table · D handoff (archive history + fresh next-day card) · E Play Again. `_rolling_slot` builds fixture `LauncherSlot`s; sets `winner_slug` via `slugify`.

### Locked visual/copy decisions (already in the render)

- Slot header is `💫 @Early Pod` (emoji + role mention). Markdown headings (`###`) do **not** render inside embed field values — do not reintroduce them there.
- Finished line: `🏆 [POD NAME](discord thread)␣␣[**Winner**](website pod page at winner seat)`. The pod name links to the **Discord thread/card**; the **winner name** links to `limitedlevelups.com/pods/<event-slug>/<winner-slug>`. Two non-breaking spaces separate them (regular double spaces collapse in Discord). In-progress pods use `⚔️` and no winner link.
- Launcher columns strip the slot name from the pod link (reads `MSH Jul 24`); the archive keeps the full name (`MSH Jul 24 Early Pod`) so Early and Late stay distinguishable in the flat list.
- Next section: `<:chordoHello:…> **Next** <t:…:R>` (relative "in 3 hours") on the label line, full localized date + count on the next line, roster below.
- Archive/retired card: `### On This Day` + one finished line per pod, in the description, no fields, no `Signups Closed` footer.
- Multi-table: each finished table is its own line under the same header; the flashback second table keeps its `- Table 2` suffix.

## The render → data contract (what the backend must produce)

`build_poll_embed(slots, guild)` and `PodPollView(slots, guild)` consume a `list[LauncherSlot]`. Everything below is what `launcher_snapshot_sync` (`bot/services/pod_launch.py`) must return once rolling is real. **Today it returns exactly one slot per bucket for a single `signal_date`** — that is the core gap.

For rolling, the snapshot for a board must return, per bucket, **all** of:
- each **finished/committed** pod at that bucket's past slot(s) for the board's own day — `committed=True`, `thread_name`, `set_code`, thread/card ids for the Discord link, and **`winner` + `winner_slug`** populated from the pod result (champion display name and the winner's `Player.slug`; fall back to `slugify(name)` only if unlinked — the render already prefers `winner_slug`). Multiple tables at one slot each become their own `LauncherSlot`.
- the **next day's gathering** slot for that bucket — `committed=False`, the pre-created signal's roster, `slot_time` on the next date.

The render groups by `bucket_key`, orders by `slot_time`, and stacks. The board title is `min(slot_time)` = the posting day, so it stays fixed as columns roll forward. No render change is needed to support multi-table or straddling dates — only the snapshot returning the right slots.

## The rolling backend (all shipped; each item names where it landed)

1. **Per-slot flip on completion.** `pod_active.notify_pod_complete` fires from `finalize_tournament`, `finalize_team_tournament`, and `_finalize_mock` into `roll_lane_after_pod`, which opens the next day's slot and re-renders. Completion, not the championship post, is the trigger: the championship embed waits on decks and screenshots, so keying off it would have held the flip for hours.
2. **Pre-create next-day signals + adopt-or-create.** `roll_slot_forward_sync` opens the row and binds it to the launcher already posted; `create_poll_signals` adopts any open row for the day it is binding. Migration `r0l1i2n3g4s5` widens the pod_signals unique key to (`message_id`, `bucket`, `signal_date`) so one message can carry two rows of a bucket.
3. **`launcher_snapshot_sync` returns multiple slots per lane** through `_lane_snapshot`, with `_event_ids_for_slot` gathering a slot's extra ` - Table N` pods. `finished` / `winner` / `winner_slug` come from `_pod_winner`.
4. **Hold-and-show firing.** `pod_signals.slot_can_fire` gates the join-path fire; `_graduate_held_slots` re-checks at the morning post.
5. **Play Again CTA.** `_schedule_play_again` posts `post_play_again_prompt` five minutes after completion; the button resolves its target at click time (`open_slot_for_bucket_sync`) and writes through `join_slot_signal_sync`. `PlayAgainView()` registers persistently in `bot/main.py`.
6. **Expired-slot roll.** `fire_slot_expiry` calls the roll hook; `reconcile_rolled_lanes` covers a restart across a missed expiry or completion.
7. **Handoff at 11:00.** Adoption rebinds the day's rows to the fresh message before `close_recent_launchers` runs, so the retiring board carries only its own played pods.
8. **Weekend/role re-resolution.** Lanes (`PollBucket.lane`) group the two bucket keys of a time of day, so the rolled column resolves the weekend role and its own button key from the day it landed on.

## Validated during the build

- Fired state keys off the pod behind the slot (`_event_id_for_slot` → `committed`), not off link presence; played state keys off `PodDraftEvent.finalized_at`. The links are affordances only.
- `winner_slug` is the winner's real `Player.slug`; the `slugify(winner)` fallback is gone from the production path, so an unlinked winner and a team draft link the pod page without a seat.
- Team drafts credit the winning side (`pod_team.team_label`), no seat; a draw shows the trophy with no name.
- The flip runs at finalize, never at draft done, so a pod mid-rounds keeps its slot.

## How to preview

Run the local bot (`dchord-bot watch`), then in a test guild: `!test rolling` for the static render situations, `!test poll` for the live board. `chordoHello` renders only if it is uploaded as an application emoji (`python -m bot.scripts.upload_app_emojis`, once per app).
