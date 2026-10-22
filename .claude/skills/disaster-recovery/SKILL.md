---
name: disaster-recovery
description: Walk the user through rotating every production secret after a breach, one step at a time, in recovery order. Use when the user wants to go through disaster recovery, rotate or roll the secret keys, tokens or credentials, or reacts to a leak at Railway, Supabase, Cloudflare, Discord or Google. Follows docs/disaster-recovery.md. The user does the dashboard work; the agent verifies each new value, pushes it to Railway and Cloudflare Pages and redeploys. Never commits.
---

# disaster-recovery

`docs/disaster-recovery.md` is the runbook. Read all of it before your first reply. It holds the inventory of every secret and copy, the recovery order, the bash helpers and, per step, a **User** part, an **Agent** part and a **Move on when** condition.

## How to run it

1. Run Step 0 yourself, without asking first. Report what it found in a few lines. If Railway can't deploy or a pod draft is running, say so and ask whether to wait or to continue with the local fallback.
2. Give the user one step at a time, in the file's order. For each step, send the **User** part: the exact URL, what to click and which `.env.prod` key gets the new value.
3. Then ask whether it's done with AskUserQuestion. Put the URL and the one-line action in the question text itself, because the mobile app collapses the message above a question into a summary.
4. When the user answers, run the step's **Agent** part: the checks, then the pushes and redeploys. Report each check with ✅ or ❌.
5. Go to the next step only when its **Move on when** condition holds. On a failure, explain the likely cause from the runbook's lessons, give the user the fix and check again.
6. After Step 5, close with a table of every secret and its verified state.

## Rules

- Never print a secret value. Show lengths, digest prefixes, usernames or HTTP codes.
- Read new values from `.env.prod`. Never ask the user to paste a secret into chat.
- Push to Railway with `--skip-deploys` and deploy each service once per step. Railway asks for no repeated deploys during incidents.
- Never reset or revoke anything yourself. Resets happen in the user's dashboards.
- If the user reports a secret or a copy the runbook lacks, finish the rotation, then offer to add it to the inventory.
- Leave the `docs/disaster-recovery.md` edits uncommitted. The user commits on their own timing.
