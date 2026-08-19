"""Team-Draft vote offer posted as its own embed card on a settled six-player pod: the pod picks between a
Team Draft now and waiting for eight, shown as two side-by-side columns of voters with a button per side. A
distinct thread message, not an edit to the lobby card, so it reads as a call to action — styled like the
/pod-table card.

The card message is the source of truth for the tally: each voter is stored in their column as a mention,
which Discord renders as a name but keeps machine-readable. A click reads the columns straight off the
message, so the vote survives a restart and works before any live manager exists — the T-60 offer runs an
hour before the lobby opens. The click handler is registered by the manager module; this module owns the
card, the buttons, and the reads so the live message and the `!test` preview can't drift.
"""
from __future__ import annotations

import re
from collections.abc import Awaitable, Callable

import discord
from discord import ui

from bot import emojis
from bot.services import pod_vote_card


TEAM_VOTE_POD_SIZE = 6
TEAM_VOTE_WAIT_SIZE = 8
TEAM_VOTE_PROMPT = "{count} Players in Draftmancer! Make it a Team Draft or Wait?"
TEAM_VOTE_GATHERING = "Turns into a Team Draft with {needed} votes"
TEAM_VOTE_SETTINGS_HINT = "Change it in ⚙️ **Settings** anytime"
TEAM_VOTE_LOCKED_HEADING = "👥 Team Draft is on!"
TEAM_VOTE_WAITED_HEADING = "⏳ Waiting for {wait} players"
TEAM_VOTE_TEAM_COLUMN = "🤝 Team Draft"
TEAM_VOTE_WAIT_COLUMN = "⏳ Wait"
TEAM_VOTE_TEAM_LABEL = "Team Draft"
TEAM_VOTE_WAIT_LABEL = "Wait"
TEAM_VOTE_TEAM_EMOJI = "🤝"
TEAM_VOTE_WAIT_EMOJI = "⏳"
VOTE_BUTTON_PREFIX = "podteamvote"
SIDE_TEAM = "team"
SIDE_WAIT = "wait"

_NEEDED_RE = re.compile(r"with (\d+) vote")


def team_vote_needed(pod_size: int) -> int:
    """Votes to decide the pod: a majority. The first side to reach it wins."""
    return pod_size // 2 + 1


def build_team_vote_offer_embed(team: list[str], wait: list[str], pod_size: int) -> discord.Embed:
    """The gathering-state offer card, shaped like the pod-table card: the description carries the prompt and
    the vote target, two side-by-side columns carry the voters. Green, like the other pod cards. Voters are
    display strings — mentions on the live card so the tally reads back off the message, plain names in
    previews."""
    embed = discord.Embed(color=discord.Color.green(), description=offer_description(pod_size))
    _set_columns(embed, team, wait)
    pod_vote_card.add_rally_line(embed)
    return embed


def offer_description(pod_size: int) -> str:
    """The prompt and what a majority does, as the card's opening lines.

    The card carries no title. A mana glyph in an embed title hangs off the em box instead of sitting on
    the text, and the count is the first thing anybody reads here."""
    return (f"### {TEAM_VOTE_PROMPT.format(count=emojis.mana_number(pod_size))}\n"
            f"{TEAM_VOTE_GATHERING.format(needed=team_vote_needed(pod_size))}")


def build_team_vote_locked_embed(team: list[str], wait: list[str]) -> discord.Embed:
    """The Team-Draft outcome: the heading flips to the "on" line, the columns stay as the record, and the
    hint says the pairing is still changeable in Settings."""
    embed = discord.Embed(
        color=discord.Color.green(),
        description=f"### {TEAM_VOTE_LOCKED_HEADING}\n{TEAM_VOTE_SETTINGS_HINT}")
    _set_columns(embed, team, wait)
    return embed


def build_team_vote_waited_embed(team: list[str], wait: list[str]) -> discord.Embed:
    """The wait-for-eight outcome: the pod stays a bracket and keeps filling, the columns stay as the
    record, and the hint says the pairing is still changeable in Settings."""
    heading = TEAM_VOTE_WAITED_HEADING.format(wait=emojis.mana_number(TEAM_VOTE_WAIT_SIZE))
    embed = discord.Embed(
        color=discord.Color.green(), description=f"### {heading}\n{TEAM_VOTE_SETTINGS_HINT}")
    _set_columns(embed, team, wait)
    return embed


def rerender_gathering(embed: discord.Embed, team: list[str], wait: list[str]) -> discord.Embed:
    """A copy of a gathering card with its two columns refreshed, prompt and target preserved, so the click
    handler re-renders without needing the original pod size."""
    fresh = discord.Embed.from_dict(embed.to_dict())
    _set_columns(fresh, team, wait)
    pod_vote_card.add_rally_line(fresh)
    return fresh


def _set_columns(embed: discord.Embed, team: list[str], wait: list[str]) -> None:
    pod_vote_card.set_columns(embed, [(TEAM_VOTE_TEAM_COLUMN, team), (TEAM_VOTE_WAIT_COLUMN, wait)])


def team_voters_from_embed(embed: discord.Embed) -> list[str]:
    """The Team-Draft voters read back off the card, in order."""
    return pod_vote_card.voters_from_field(embed, TEAM_VOTE_TEAM_COLUMN)


def wait_voters_from_embed(embed: discord.Embed) -> list[str]:
    """The wait voters read back off the card, in order."""
    return pod_vote_card.voters_from_field(embed, TEAM_VOTE_WAIT_COLUMN)


def needed_from_embed(embed: discord.Embed) -> int | None:
    """The vote target parsed back off the card's description, None when the card is not in gathering state."""
    match = _NEEDED_RE.search(embed.description or "")
    return int(match.group(1)) if match else None


async def find_team_vote_card(thread: discord.Thread, event_id: str) -> discord.Message | None:
    """The pod's Team-Draft card in a thread, located by the vote buttons' event-keyed custom_id so a
    manager taking over at T-10, or a restart, adopts the existing card instead of posting a second one."""
    target = f"{VOTE_BUTTON_PREFIX}:{SIDE_TEAM}:{event_id}"
    try:
        async for message in thread.history(limit=50):
            for row in message.components:
                for child in getattr(row, "children", []):
                    if getattr(child, "custom_id", None) == target:
                        return message
    except discord.HTTPException:
        return None
    return None


TeamVoteClickHandler = Callable[[discord.Interaction, str, str], Awaitable[None]]

_click_handler: TeamVoteClickHandler | None = None


def register_team_vote_click_handler(handler: TeamVoteClickHandler) -> None:
    """Wire the vote-click logic. The manager module registers it at import so this module stays free of a
    manager import and the buttons work whether or not a live manager backs the pod."""
    global _click_handler
    _click_handler = handler


class TeamVoteButton(ui.DynamicItem[ui.Button], template=rf"{VOTE_BUTTON_PREFIX}:(?P<side>team|wait):(?P<event_id>.+)"):
    """A side button on a Team-Draft offer card. One per side per pod (side + event id in the custom_id), so
    a single registration dispatches every offer and the buttons keep working after a restart. A click moves
    the clicker to that side against the card message."""

    def __init__(self, event_id: str, side: str) -> None:
        team = side == SIDE_TEAM
        super().__init__(ui.Button(
            style=discord.ButtonStyle.primary if team else discord.ButtonStyle.secondary,
            label=TEAM_VOTE_TEAM_LABEL if team else TEAM_VOTE_WAIT_LABEL,
            emoji=TEAM_VOTE_TEAM_EMOJI if team else TEAM_VOTE_WAIT_EMOJI,
            custom_id=f"{VOTE_BUTTON_PREFIX}:{side}:{event_id}",
        ))
        self.event_id = event_id
        self.side = side

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: ui.Button, match: re.Match):
        return cls(match["event_id"], match["side"])

    async def callback(self, interaction: discord.Interaction) -> None:
        if _click_handler is None:
            await interaction.response.send_message(
                "This pod is no longer taking votes", ephemeral=(interaction.guild is not None),
            )
            return
        await _click_handler(interaction, self.event_id, self.side)


def build_team_vote_view(event_id: str) -> ui.View:
    view = ui.View(timeout=None)
    view.add_item(TeamVoteButton(event_id, SIDE_TEAM))
    view.add_item(TeamVoteButton(event_id, SIDE_WAIT))
    return view
