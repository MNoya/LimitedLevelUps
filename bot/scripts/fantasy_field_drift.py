"""Compare a fantasy event's field seed with magic.gg's invitation list and print what changed

    .venv/bin/python -m bot.scripts.fantasy_field_drift WC32
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from dataclasses import dataclass

import requests

from bot.services.fantasy_event import EVENTS_JSON
from bot.services.fantasy_sync import fold_name


@dataclass(frozen=True)
class Invitee:
    first_name: str
    last_name: str
    country: str
    sources: tuple[str, ...]

    @property
    def key(self) -> str:
        return fold_name(f"{self.first_name} {self.last_name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("event_code")
    args = parser.parse_args()

    config = json.loads(EVENTS_JSON.read_text())[args.event_code.upper()]
    seed_path = EVENTS_JSON.parent / config["fieldSeed"]
    seed = json.loads(seed_path.read_text())
    response = requests.get(config["invitationListUrl"], headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    response.raise_for_status()
    invited = parse_invitation_list(response.text)
    if not invited:
        raise SystemExit("no invitation table found on the page, so the layout changed")

    findings = field_drift(seed, invited)
    print(f"{len(invited)} invited on magic.gg, {len(seed)} in {config['fieldSeed']}")
    for line in findings:
        print(line)
    sys.exit(1 if findings else 0)


def parse_invitation_list(page: str) -> list[Invitee]:
    table = page[page.find("<table"):page.find("</table>")]
    invitees = []
    for row in re.findall(r"<tr.*?</tr>", table, re.S)[1:]:
        cells = [_cell_text(cell) for cell in re.findall(r"<t[dh].*?</t[dh]>", row, re.S)]
        if len(cells) < 4:
            continue
        sources = tuple(source.strip() for source in cells[3].split(";") if source.strip())
        invitees.append(Invitee(first_name=cells[0], last_name=cells[1], country=cells[2], sources=sources))
    return invitees


def field_drift(seed: list[dict], invited: list[Invitee]) -> list[str]:
    seeded = {}
    for entry in seed:
        seeded[fold_name(f"{entry['firstName']} {entry['lastName']}")] = entry
    invited_keys = set()
    findings = []
    for invitee in invited:
        invited_keys.add(invitee.key)
        entry = seeded.get(invitee.key)
        name = f"{invitee.first_name} {invitee.last_name}"
        if entry is None:
            findings.append(f"added: {name}, {invitee.country}, {'; '.join(invitee.sources)}")
            continue
        if (entry.get("country") or "").casefold() != invitee.country.casefold():
            findings.append(f"country changed: {name}, {entry.get('country')} -> {invitee.country}")
        if tuple(entry.get("sources", [])) != invitee.sources:
            findings.append(f"sources changed: {name}, {'; '.join(invitee.sources)}")
    for key, entry in seeded.items():
        if key not in invited_keys:
            findings.append(f"removed: {entry['firstName']} {entry['lastName']}")
    return findings


def _cell_text(cell: str) -> str:
    return html.unescape(re.sub(r"<.*?>", "", cell)).replace("\xa0", " ").strip()


if __name__ == "__main__":
    main()
