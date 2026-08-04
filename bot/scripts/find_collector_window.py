"""Print the Collector Booster Arena Direct window for a set, from the MTG Scribe calendar.

The collector premiere pays one box per trophy instead of the play direct's two, so
``boxes_for_event`` needs the window recorded in ``COLLECTOR_BOOSTER_WINDOWS`` (bot/sets.py)
and its frontend mirror. This resolves the range from Scribe and prints paste-ready rows for
both. Run it while adding a set (via the add-set skill) or whenever a set's Arena Direct lands:

    .venv/bin/python -m bot.scripts.find_collector_window MSH

Reads the bundled calendar, so run ``snapshot_scribe`` first if the set is newer than it. Scribe
schedules Arena Directs partway into a set's cycle, so a just-released set may have no window yet;
re-run once it appears.
"""
from __future__ import annotations

import sys

from bot.commands.event_scribe import normalize_event
from bot.services import mtgscribe
from bot.sets import active_set_code, is_known_set, set_name_for

COLLECTOR_FORMAT = "Arena Direct Collector"


def main() -> None:
    code = (sys.argv[1] if len(sys.argv) > 1 else active_set_code()).upper()
    if not is_known_set(code):
        print(f"unknown set code: {code} (add it to ALL_SETS first)")
        raise SystemExit(1)

    name = set_name_for(code)
    events = mtgscribe.load_events()
    windows = [(e.start_local.date(), e.end_local.date()) for e in map(normalize_event, events)
               if e.format_label == COLLECTOR_FORMAT and e.group_label == name]
    if not windows:
        print(f"no Collector Booster Arena Direct found for {code} on MTG Scribe yet; re-run once it is scheduled")
        return

    start = min(w[0] for w in windows)
    end = max(w[1] for w in windows)
    print(f"Collector Booster Arena Direct for {code} ({name}): {start} to {end}\n")
    print("bot/sets.py — add to COLLECTOR_BOOSTER_WINDOWS:")
    print(f'    CollectorBoosterWindow("{code}", '
          f"date({start.year}, {start.month}, {start.day}), date({end.year}, {end.month}, {end.day})),\n")
    print("frontend/src/data/scoring.ts — add to COLLECTOR_BOOSTER_WINDOWS:")
    print(f'  {{ setCode: "{code}", startDate: "{start.isoformat()}", endDate: "{end.isoformat()}" }},')


if __name__ == "__main__":
    main()
