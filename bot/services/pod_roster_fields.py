"""The Yes / Maybe roster columns shared by the scheduled card and the T-60 roster reminder, so both
surfaces group by format the same way. Once a signup wants flashback the roster splits into Latest Set
and Flashback columns; otherwise it stays a plain Yes / Maybe pair."""
from __future__ import annotations

import discord

from bot.services import pod_format_interest as fi
from bot.services.pod_signals import RSVP_MAYBE, RSVP_NO, RSVP_YES


_ATTENDANCE = ((RSVP_YES, "✅", "Yes"), (RSVP_MAYBE, "🤷", "Maybe"))
_ATTENDANCE_WITH_NO = _ATTENDANCE + ((RSVP_NO, "❌", "No"),)


def add_roster_fields(
    embed: discord.Embed, rosters: dict[str, list[str]],
    roster_interests: dict[str, list[tuple[str, tuple[str, ...]]]] | None,
    championship: bool = False,
) -> None:
    """Yes / Maybe columns while the pod gathers, grouped by format once a signup wants flashback,
    plain otherwise. No is normally not a column — the ❌ button removes the signup instead of tracking
    a decline — but a championship shows it so declines read at a glance, and skips the format split
    since it is a single-set event."""
    if championship:
        _add_plain_rsvp_fields(embed, rosters, include_no=True)
        return
    if roster_interests is None:
        _add_plain_rsvp_fields(embed, rosters)
        return
    yes = roster_interests.get(RSVP_YES) or []
    maybe = roster_interests.get(RSVP_MAYBE) or []
    comp = fi.composition([codes for _, codes in yes] + [codes for _, codes in maybe])
    if comp.flashback_only > 0:
        _add_format_split_fields(embed, yes, maybe)
    else:
        _add_plain_rsvp_fields(embed, rosters)


def _add_plain_rsvp_fields(
    embed: discord.Embed, rosters: dict[str, list[str]], include_no: bool = False,
) -> None:
    attendance = _ATTENDANCE_WITH_NO if include_no else _ATTENDANCE
    for state, emoji, word in attendance:
        names = rosters.get(state) or []
        value = "\n".join(f"> {name}" for name in names) if names else "-"
        embed.add_field(name=f"{emoji} {word} ({len(names)})", value=value, inline=True)


def _add_format_split_fields(
    embed: discord.Embed, yes: list[tuple[str, tuple[str, ...]]], maybe: list[tuple[str, tuple[str, ...]]],
) -> None:
    """Latest Set / Flashback columns, each sub-grouped into Yes then Maybe with counts. Flexible
    players carry the flexible marker and fill whichever team needs bodies, same as the launcher board."""
    tagged = [(name, state, codes) for state, members in ((RSVP_YES, yes), (RSVP_MAYBE, maybe))
              for name, codes in members]
    latest_team, flashback_team = fi.format_teams([(entry, entry[2]) for entry in tagged])
    for emoji, label, team in (
        (fi.latest_emoji(), "Latest Set", latest_team), (fi.flashback_emoji(), "Flashback", flashback_team),
    ):
        blocks = []
        for state, status_emoji, word in _ATTENDANCE:
            members = [(name, codes) for (name, st, codes) in team if st == state]
            if members:
                lines = "\n".join(
                    f"> {fi.FLEXIBLE_MARKER + ' ' if fi.is_flexible(codes) else ''}{name}"
                    for name, codes in members
                )
                blocks.append(f"{status_emoji} {word} ({len(members)})\n{lines}")
        embed.add_field(name=f"{emoji} {label} ({len(team)})", value="\n".join(blocks) or "-", inline=True)
