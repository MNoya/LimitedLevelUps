# Episode inline transcript editing (admin)

## Resume status (built, awaiting deploy)
The feature is implemented and committed; it works locally but is not on prod yet, because the bot endpoint and the frontend build both need to ship. Until then, Save on the site returns "Not Authorized"/"Transcript Not Found" (the browser posts to the prod bot, which lacks the route). Where to look:
- Backend: `bot/http_server.py` (`POST /episodes/{key}/transcript`, `_require_admin`, `_save_transcript`); `bot/services/transcript_edit.py` (`merge_transcript_segments`, `relink_changed_segments`, `word_count`); `bot/services/transcript_cards.py` (`build_card_tagger`, returns None for setless so no card pass there); `bot/config.py` (`is_admin`, `admin_discord_ids`); `bot/scripts/local_supabase_proxy.py` (same route, no-auth, for local dev).
- Frontend: `frontend/src/pages/EpisodesPage.tsx` (`useTranscriptEdit`, `EditControls`, `MobileEditFab`, and the `contentEditable` block editor); `frontend/src/data/adminApi.ts` (`saveTranscript`, `errorMessage`); `frontend/src/data/admins.ts` (`isAdmin`, defaults Noya + ChordOCalls, override `VITE_ADMIN_DISCORD_IDS`).
- Done: desktop + mobile edit (pencil FAB to cancel/save), delete-subsection, single Title Case save error, timestamp/card-preserving merge.
- To do: deploy (push master so the bot serves the route and the frontend ships), verify on a phone as admin, then the optional add-subsection (promote a paragraph to a subheading, reusing its `t`).
- Test before deploy: run the dev server in local mode (proxy on :3001 + the episode present in local Postgres) to exercise Save end to end; prod-mode shows the UI but Save 404s until the bot deploys.
- Caveat: edits live only in the stored `episode_transcripts` row. A re-enhance reads raw captions from `cache/transcripts/`, so re-running the pipeline on an edited episode overwrites manual edits.

Handoff spec for a fresh session. Goal: a lightweight, admin-only way to make localized text edits to an episode transcript straight from the episode detail page on the site, to fix a card name, a person's name, punctuation, or a cringy Claude-generated title, without touching timestamps or segment structure.

This is the first site-modifying endpoint that writes public content. Keep it small and safe.

## Scope

In scope
- Edit the **text** of any paragraph, chapter title (`heading`), and section/subtopic title (`subheading`) in a transcript
- **Delete a subsection**: remove a segment's `subheading` so it stops being a subtopic boundary and its text folds into the preceding section as a normal paragraph. The text and timestamp stay; only the subtopic split goes away. This covers the common case where the structure pass invented subtopics that do not feel right.
- Admin-only, gated on the operator's Discord id (the admin allowlist below, not all organizers)
- One save for the whole transcript (single request with the full segments array), plus discard

Out of scope (do not build)
- Adding, removing, or reordering the underlying text segments. Deleting a subsection reclassifies a segment (drops its `subheading`), it does not delete the segment or its text.
- Editing or inserting card links (card names get fixed as plain text; the deterministic/LLM card pass handles linking on a later run)
- Editing timestamps (`t`, `head_t`) or the `cards` arrays: preserve them verbatim
- Per-field autosave

Possible later extension (symmetric, not required now): **add a subsection** by promoting an existing paragraph to a `subheading`. It reuses that paragraph's own `t`, so no new timestamp is needed and no boundary math is involved. This is the mirror of delete and is why delete is safe. Leave it out of the first pass unless it is cheap once delete works.

## Auth

Discord OAuth via Supabase is already wired (identity layer). The viewer's Discord id is available as `user?.discordId` (see `frontend/src/data/podDecklistAccess.ts`).

- Add an **admin** check, distinct from `isPodOrganizer` (`frontend/src/data/podOrganizers.ts`, which allows three organizers). Admins are Noya (`237762740532412416`) and Chord O Calls (`507301384979349526`), not the full organizer list (GatoDelFuego is excluded). Prefer a `VITE_ADMIN_DISCORD_IDS` env with those two as the built-in default, mirroring how `podOrganizers.ts` reads `VITE_POD_ORGANIZER_DISCORD_IDS`.
- The Edit button renders only when the viewer is admin. The server re-checks admin independently; the client gate is cosmetic.

## UX (episode detail, `frontend/src/pages/EpisodesPage.tsx`, `TranscriptView`)

- Add an **Edit** button to the right of the reading-options controls. Admin only.
- Click Edit: enter edit mode. Nothing looks editable by default. On hover, an editable block (paragraph, `heading`, `subheading`) shows a subtle box highlight signalling it is editable.
- Click a block: it becomes inline-editable with the existing text, cursor placed at the clicked position. Use `contenteditable` on the block so the caret lands where clicked. Capture `innerText` on blur into local edit state, keyed by segment index and field.
- The block-to-segment mapping must be exact: carry the segment index and field name on each editable node so edits write back to the right segment. Do not run the card-link renderer in edit mode (edit raw text, not the linked spans).
- Each subtopic title (`subheading` block) shows a small delete affordance in edit mode (a trash or x icon on hover). Clicking it removes the `subheading` from that segment in the working copy: the block re-renders as a normal paragraph folded into the section above it, its text and `t` unchanged. This is a working-copy change like any edit, so it enables Save; nothing is written until Save.
- Edit button becomes **Save** plus **Discard** while in edit mode. Save is disabled (grayed) when the working copy equals the original (deep compare). Discard restores the original and exits edit mode.
- Save sends the whole segments array once (see endpoint). On success, update the local query cache and exit edit mode.

Suggested state: hold a working copy of `segments` (deep clone). Editable blocks write `working[i].text|heading|subheading`. `dirty = !deepEqual(working, original)`.

## Backend endpoint (reuse `bot/http_server.py`)

`bot/http_server.py` already binds an aiohttp app for the tracker refresh and validates a Supabase access token in `_discord_id_for_token(token)` (GET Supabase `auth/user` with the Bearer token plus anon apikey, returns the Discord id). Reuse it.

- Add a route, e.g. `POST /episodes/{key}/transcript`, Bearer token in `Authorization`.
- Resolve `discord_id = await _discord_id_for_token(token)`; reject unless it equals the admin id (add an admin constant/allowlist in `bot/config.py`, do not reuse `is_tracker_player`).
- Body: the full `segments` array. Match incoming to stored segments by index (same length and order, since segments are never added/removed/reordered) and reject if the count differs. For each, take `text`, `heading`, `subheading` from the incoming copy, treating **absence as removal** so a deleted `subheading` is dropped, and keep `t`, `head_t`, `cards` and any other keys from the stored row (defense against a client dropping timestamp or card fields). Recompute `word_count`. Keep `source` unchanged.
- `key` is the transcript primary key: `youtube_id` for video episodes, `guid` for audio-only. The frontend already knows which (the reader loads the transcript by that key).
- Return `{ ok: true }`.

Frontend call: mirror `trackerRefresh` in `frontend/src/data/trackerApi.ts` — local mode hits the `local_supabase_proxy`, prod sends `Authorization: Bearer <supabase access_token>` to the bot host (same base as `PUBLIC_TRACKER_REFRESH_URL`). Add the new path there.

## Data model

`episode_transcripts` (`bot/models.py`): `youtube_id` PK, `segments` JSONB, `word_count`, `source`, `generated_at`. Segment shape: `{ t, head_t?, heading?, subheading?, text, cards? }`. Only `text`/`heading`/`subheading` are editable.

## Acceptance criteria

- Non-admin viewer never sees the Edit button and cannot write (server rejects a forged request).
- Admin enters edit mode, hovers to see editable blocks, clicks to edit with the caret at the click point, edits several blocks, and saves once.
- Timestamps, `cards`, segment count, and order are byte-identical before and after a text-only edit.
- Deleting a subsection removes only that segment's `subheading`; its `text`, `t`, and every other segment are unchanged, and the block renders as a paragraph under the preceding section.
- Save is disabled with no changes and enabled after any change; Discard restores the original.
- `word_count` reflects the edited text after save.

## Notes

- The card-fix and structure passes read raw captions from `cache/transcripts/<key>.json`, not from the stored row. A re-enhance of an edited episode would overwrite manual edits. These are done episodes not in the sweep, so it will not happen on its own, but a future card backfill on setless episodes should re-apply from the stored row, not the cache, or skip edited rows.
- This endpoint is the template for future admin site edits, so keep the auth and the field-preserving write clean.
