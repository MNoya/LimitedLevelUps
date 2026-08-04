"""Short display names for MTG Arena event formats.

Standalone by design — no bot imports — so another program can vendor this module as-is.
Unmapped labels fall through unchanged.
"""
from __future__ import annotations

FORMAT_SHORT_NAMES: dict[str, str] = {
    "Premier Draft": "Premier",
    "Traditional Draft": "Trad",
    "Quick Draft": "Quick",
    "Pick Two": "Pick2",
    "Pick 2 Draft": "Pick2",
    "Pick-Two Draft": "Pick2",
    "Sealed": "Sealed",
    "Midweek Magic": "Midweek",
}


def short_format(label: str) -> str:
    return FORMAT_SHORT_NAMES.get(label, label)
