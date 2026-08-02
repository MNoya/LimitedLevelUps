"""Pod-draft pairing-mode options: Swiss Tournament, Fast Bracket, Random, Team Draft, or Round Robin.

Surfaced through the lobby Settings panel (pod_settings_view). Fast Bracket is honored at start only
when the roster is 8 or 10 and Round Robin only when it is exactly 4; other sizes fall back to Swiss.
Random pairs round 1 at random (seats ignored), later rounds by record.
"""
from __future__ import annotations

import discord

from bot.services.pod_format import settings_change_message


PAIRING_MODES = (
    ("swiss", "Swiss Tournament", "Three rounds, each paired after the previous fully finishes."),
    ("bracket", "Fast Bracket", "Pairs players the moment two reach the same record. 8p, 10p"),
    ("random", "Random", "Round 1 randomized ignoring seats. Later rounds by record."),
    ("team", "Team Draft", "Group players into teams. Team with best score wins. 6p"),
    ("roundrobin", "Round Robin", "Play every player at the table, one per round. 4p"),
)
DEFAULT_PAIRING_MODE = "bracket"
SELECT_PLACEHOLDER = "Choose pairing mode"


def pairing_label(mode: str | None) -> str:
    """Display label for a pairing mode; defaults to Fast Bracket."""
    cur = (mode or DEFAULT_PAIRING_MODE).lower()
    return next((lbl for code, lbl, _ in PAIRING_MODES if code == cur), cur)


def pairing_change_message(actor: str, mode: str) -> str:
    """Public thread notice when the pairing mode changes, with the mode's description as subtext."""
    label = next((lbl for code, lbl, _ in PAIRING_MODES if code == mode), mode)
    desc = next((d for code, _, d in PAIRING_MODES if code == mode), "")
    return settings_change_message(actor, "Pairings", label, subtext=desc)


def pairing_options(current_mode: str | None) -> list[discord.SelectOption]:
    """The pairing-mode dropdown options, with the current mode defaulted. Labels are prefixed with
    'Pairings:' so the collapsed dropdown reads e.g. 'Pairings: Swiss Tournament', matching the Set and
    Seats dropdowns and disambiguating its Random option from the Seats one."""
    cur = (current_mode or DEFAULT_PAIRING_MODE).lower()
    return [
        discord.SelectOption(
            label=f"Pairings: {label}", value=code, description=desc, emoji="👥", default=(cur == code))
        for code, label, desc in PAIRING_MODES
    ]
