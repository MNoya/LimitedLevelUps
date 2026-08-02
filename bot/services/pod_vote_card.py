"""Shared body of the pod vote cards: the columns of voters that carry the tally, and the `!pod` nudge under
them.

The Team Draft and Pick 2 offers ask different questions and lock different settings, but they render the
same card and read their tally back the same way. Each module owns its copy and its outcome; the shape lives
here so the two can't drift.
"""
from __future__ import annotations

import re

import discord

from bot.commands.messages import MSG_POD_RALLY_HINT
from bot.discord_helpers import ZWSP


EMPTY_COLUMN = "-"


def set_columns(embed: discord.Embed, columns: list[tuple[str, list[str]]]) -> None:
    """Replace the card's fields with one side-by-side column per (name, voters) pair. Voters are display
    strings — mentions on a live card so the tally reads back off the message, plain names in previews."""
    embed.clear_fields()
    for name, voters in columns:
        embed.add_field(name=_column_name(name, len(voters)), value=_column_value(voters), inline=True)


def add_rally_line(embed: discord.Embed) -> None:
    """The `!pod` nudge under the columns, for a card still gathering votes. A field rather than the footer,
    since footers render no markdown and the hint names a command."""
    embed.add_field(name=ZWSP, value=MSG_POD_RALLY_HINT, inline=False)


def voters_from_field(embed: discord.Embed, marker: str) -> list[str]:
    """One column's voters read back off the card as `<@id>` mentions, in order, deduped. `marker` matches
    the column name as a prefix, so a renamed column still finds the voters on cards already posted."""
    mentions: list[str] = []
    seen: set[str] = set()
    for field in embed.fields:
        if marker not in field.name:
            continue
        for user_id in _MENTION_RE.findall(field.value or ""):
            if user_id not in seen:
                seen.add(user_id)
                mentions.append(f"<@{user_id}>")
    return mentions


_MENTION_RE = re.compile(r"<@!?(\d+)>")


def _column_name(base: str, count: int) -> str:
    return f"{base} ({count})" if count else base


def _column_value(voters: list[str]) -> str:
    return "\n".join(f"> {voter}" for voter in voters) if voters else EMPTY_COLUMN
