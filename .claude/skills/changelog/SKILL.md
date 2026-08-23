---
name: changelog
description: Draft a player-facing changelog entry in the LLU patch-notes format and print it to chat, ready to paste into Discord. Covers both bot and website changes. Gathers recent commits, shows the entry, refines on request. Writes no file and does not commit.
---

# changelog

Produce a short, player-facing changelog entry (game patch-notes style) and print it to chat so the user can paste it into Discord. Covers both the **bot** and the **website**. This writes **no file** and touches nothing in the repo.

## Argument

`$ARGUMENTS` is an optional scope/focus hint. Examples: `bot`, `website`, `pod drafts`, `` (empty = whatever changed across the project). It only narrows which changes to summarize.

## Format (do not deviate)

```
## Jun 13, 2026
🪑 Live seeding table now updates instantly as players join, no refresh needed
✅ Added a Ready Check nudge once 8 linked players are in the lobby
🔁 Tournaments survive a bot restart, rounds and results stay safe
```

Rules:

- **Date heading** `## <Mon D, YYYY>` — short month, no leading zero on the day. Get today with `date +"%b %-d, %Y"`.
- **One line per change**, led by a single emoji that acts as the bullet. **No `-` bullet markers.**
- **Terse** — one line each, no trailing description sentences. Player-facing and non-technical: say what a player notices, never how it works internally.
- **Patch-notes voice** — mix proactive phrasings (`Added …`, `Fixed …`, `No more …`, `<thing> now …`). Do **not** force "now" onto every line; vary it.
- **No emdashes.** Avoid semicolons.
- **Only player-visible changes.** Omit internal refactors, tests, CI, migrations, infra, and deploy fixes.
- Pick an emoji that fits each change; keep them varied and meaningful.

## Workflow

### 1. Gather what changed

Collect recent commits on the scoped paths (`bot/` for bot, `frontend/` for website, both when there's no hint):

```
git log -15 --pretty="%h %s" -- <paths>
```

Take the last ~15 by default, or since a date the user names. Also fold in relevant staged/uncommitted work in the working tree. Translate the player-visible ones into the format above; drop everything internal.

### 2. Show the entry

Render the dated section as plain text in chat, inside a fenced block so it copies cleanly.

### 3. Refine on request (use AskUserQuestion)

Ask with options:

- **Good to post** — done, nothing more to do.
- **Refine** — the user adjusts wording, order, which items to include, or the emoji.

Tell the user they can type specific edits via the "Other" field. On any refinement, revise and re-show the entry, then ask again. Loop until they are happy.

### 4. Done

There is nothing to write and nothing to commit. The final chat output is the deliverable, ready to paste into Discord.

## Notes

- This is player-facing microcopy, not a developer changelog. The friendly `Mon D, YYYY` date is deliberate.
- Headings (`##`) render in a normal Discord message but show literally inside a code block, so the user posts the lines as plain text, not fenced.
- Keep entries scannable. If a release has many small changes, group or cut to the few players actually notice.
