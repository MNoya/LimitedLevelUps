"""Capture the MTG Scribe calendar into ``scribe_calendar.json`` — the only request the repo ever makes
to mtgscribe.com.

The bot serves that file and never fetches, so this script is what puts a new season on the board.
mtgscribe.com is on SiteGround, whose account-level anti-bot challenges datacenter egress, so run it
from a machine that isn't challenged (a laptop), then commit and deploy:

    .venv/bin/python -m bot.scripts.snapshot_scribe

Worth a run whenever Scribe publishes an incoming set's queues, when it corrects a window, and when it
backfills the ``flashback`` tags it leaves off newly-published reruns.

Only events still running or upcoming are stored, plus the queues the active set already ran — its pin
freezes into the season's record at rotation and needs them. Everything else finished is weight the
schedule would discard anyway, so each capture replaces the file rather than growing it.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

from bot.commands.event_scribe import _slugify
from bot.services import mtgscribe
from bot.services.format_schedule import active_set_seed

REQUEST_LOOKBACK_DAYS = 150


def main() -> None:
    today = date.today()
    active_slug = _slugify(active_set_seed().name)
    raw = mtgscribe.fetch_raw_events(today - timedelta(days=REQUEST_LOOKBACK_DAYS))
    snapshot = [_trim(event) for event in raw if _worth_keeping(event, today, active_slug)]
    mtgscribe.CALENDAR_PATH.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(snapshot)} events to {mtgscribe.CALENDAR_PATH} ({len(raw) - len(snapshot)} dropped)")
    _print_coverage(snapshot)


def _worth_keeping(event: dict, today: date, active_slug: str) -> bool:
    """Everything still running or upcoming, plus every queue the active set has already run.

    ``partition_by_now`` discards a finished event at render, so storing one is normally dead weight.
    The active set is the exception: its channel pin freezes into the season's record when it rotates
    out, and a record of the season needs the queues that already closed. Those rows fall away on the
    first capture after the rotation, by which point the pin holds them.

    The request still reaches months back regardless, since an in-progress event started before today
    and would otherwise be missed — a set's draft queues run about seven weeks.
    """
    if date.fromisoformat(event["utc_end_date"][:10]) >= today:
        return True
    return active_slug in [tag.get("slug", "") for tag in event.get("tags", [])]


def _trim(event: dict) -> dict:
    """Keep only the fields ``mtgscribe._parse_event`` reads, so the snapshot stays small and stable."""
    return {
        "title": event.get("title", ""),
        "tags": [{"slug": tag.get("slug", "")} for tag in event.get("tags", [])],
        "utc_start_date": event["utc_start_date"],
        "utc_end_date": event["utc_end_date"],
        "start_date": event["start_date"],
        "end_date": event["end_date"],
    }


def _print_coverage(snapshot: list[dict]) -> None:
    """How far forward the board is now good for — the number to sanity-check before committing."""
    if not snapshot:
        print("no events kept; the request was probably challenged, or the calendar has run out")
        return
    latest_end = max(event["utc_end_date"] for event in snapshot)
    days = (date.fromisoformat(latest_end[:10]) - date.today()).days
    print(f"calendar covers events ending through {latest_end[:10]} ({days} days out)")


if __name__ == "__main__":
    main()
