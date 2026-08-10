"""Round Robin vote offer posted as its own embed card when a lobby settles at four players: the pod picks
between playing now as a Pick 2 Round Robin and waiting for more players, shown as two side-by-side columns
of voters with a button per side. Styled like the Team Draft vote card.

Every player has to agree, so the card has one outcome and no deadline. Wait is not a verdict, it is "not
yet": the card stays open, votes stay changeable, and a player who wanted to wait can move to Round Robin
once it is clear nobody else is coming.

The card message is the tally, exactly like the Team Draft card: each voter is stored in their column as a
mention, which Discord renders as a name but keeps machine-readable. A click reads the columns straight off
the message, so the vote survives a restart.

Players read this offer as the Pick 2 one, so the button and the column say Pick 2 even though the pairing
mode it turns on is Round Robin.

The card also points at `!pod` under the columns, since four players sitting in a lobby is exactly when
someone should be rallying the channel for a fifth and sixth.
"""
from __future__ import annotations

import re
from collections.abc import Awaitable, Callable

import discord
from discord import ui

from bot import emojis
from bot.services import pod_vote_card


ROUND_ROBIN_PROMPT = "{count} Players locked in! Make it Pick 2 or Wait?"
ROUND_ROBIN_GATHERING = "Turns into Pick 2 (Round Robin) with all {needed} votes"
ROUND_ROBIN_SETTINGS_HINT = "Change it in ⚙️ **Settings** anytime"
ROUND_ROBIN_LOCKED_TITLE = "🔄 Pick 2 is on!"
ROUND_ROBIN_COLUMN = "🔄 Pick 2"
WAIT_COLUMN = "⏳ Wait"
ROUND_ROBIN_LABEL = "Pick 2"
WAIT_LABEL = "Wait"
ROUND_ROBIN_EMOJI = "🔄"
WAIT_EMOJI = "⏳"
VOTE_BUTTON_PREFIX = "podrrvote"
SIDE_ROUND_ROBIN = "rr"
SIDE_WAIT = "wait"


def votes_needed(pod_size: int) -> int:
    """Unanimous: every player at the table plays every other one, so every player agrees to it."""
    return pod_size


def build_offer_embed(round_robin: list[str], wait: list[str], pod_size: int) -> discord.Embed:
    """The open offer card: the bar in the description, the rally hint below it, and the voters in two
    columns. Voters are display strings — mentions on the live card so the tally reads back off the message,
    plain names in previews."""
    embed = discord.Embed(
        color=discord.Color.green(),
        title=ROUND_ROBIN_PROMPT.format(count=emojis.mana_number(pod_size)),
        description=ROUND_ROBIN_GATHERING.format(needed=votes_needed(pod_size)),
    )
    _set_columns(embed, round_robin, wait)
    pod_vote_card.add_rally_line(embed)
    return embed


def build_locked_embed(round_robin: list[str], wait: list[str]) -> discord.Embed:
    """The one outcome: everybody agreed, so the pod plays now and the counts stay as the record."""
    embed = discord.Embed(
        color=discord.Color.green(), title=ROUND_ROBIN_LOCKED_TITLE, description=ROUND_ROBIN_SETTINGS_HINT)
    _set_columns(embed, round_robin, wait)
    return embed


def rerender_gathering(embed: discord.Embed, round_robin: list[str], wait: list[str]) -> discord.Embed:
    """A copy of an open card with its counts refreshed, title and description preserved."""
    fresh = discord.Embed.from_dict(embed.to_dict())
    _set_columns(fresh, round_robin, wait)
    pod_vote_card.add_rally_line(fresh)
    return fresh


def _set_columns(embed: discord.Embed, round_robin: list[str], wait: list[str]) -> None:
    pod_vote_card.set_columns(embed, [(ROUND_ROBIN_COLUMN, round_robin), (WAIT_COLUMN, wait)])


def round_robin_voters_from_embed(embed: discord.Embed) -> list[str]:
    """The Pick 2 voters read back off the card, in order."""
    return pod_vote_card.voters_from_field(embed, ROUND_ROBIN_COLUMN)


def wait_voters_from_embed(embed: discord.Embed) -> list[str]:
    """The wait voters read back off the card, in order."""
    return pod_vote_card.voters_from_field(embed, WAIT_COLUMN)


VoteClickHandler = Callable[[discord.Interaction, str, str], Awaitable[None]]

_click_handler: VoteClickHandler | None = None


def register_vote_click_handler(handler: VoteClickHandler) -> None:
    """Wire the vote-click logic. The manager module registers it at import so this module stays free of a
    manager import."""
    global _click_handler
    _click_handler = handler


class RoundRobinVoteButton(
    ui.DynamicItem[ui.Button], template=rf"{VOTE_BUTTON_PREFIX}:(?P<side>rr|wait):(?P<event_id>.+)"
):
    """A side button on a Round Robin offer card. One per side per pod, so a single registration dispatches
    every offer and the buttons keep working after a restart."""

    def __init__(self, event_id: str, side: str) -> None:
        round_robin = side == SIDE_ROUND_ROBIN
        super().__init__(ui.Button(
            style=discord.ButtonStyle.success if round_robin else discord.ButtonStyle.secondary,
            label=ROUND_ROBIN_LABEL if round_robin else WAIT_LABEL,
            emoji=ROUND_ROBIN_EMOJI if round_robin else WAIT_EMOJI,
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


def build_vote_view(event_id: str) -> ui.View:
    view = ui.View(timeout=None)
    view.add_item(RoundRobinVoteButton(event_id, SIDE_ROUND_ROBIN))
    view.add_item(RoundRobinVoteButton(event_id, SIDE_WAIT))
    return view
