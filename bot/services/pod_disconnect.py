"""The cards a pod gets when someone drops mid-draft and Draftmancer holds the table for them.

The first says who went and counts down the reconnect window. When that window closes with nobody back, a
second one asks the table how to continue, shaped like the Team-Draft offer: two columns of voters, a
button per side, and a majority of the players still at the table decides. A return posts a third. A stall
that reached the vote stays in the thread as the record of it; a pair that only came and went is removed
when the next drop is announced, so a flapping connection never fills the thread with it.

The card message is the source of truth for the tally, the same way the Team-Draft card is: each voter is
stored in their column as a mention, so a click reads the columns straight off the message and a stalled
draft that outlives a bot restart still has a working vote. The click handler is registered by the manager
module; this module owns the cards, the buttons, and the reads so the live messages and the `!test` preview
can't drift.
"""
from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable

import discord
from discord import ui

from bot.services import pod_vote_card


DROP_EMOJI = "😐"
DROP_HEADING = "{emoji} {names} disconnected"
DROP_WAITING_BODY = "Vote opens {when} if they don't come back"
OFFER_HEADING = "{emoji} {names} disconnected {when}"
OFFER_BODY = "Choose how to continue"
OFFER_FOOTER = "{needed} vote{plural} needed"
BACK_EMOJI = "✅"
BACK_HEADING = "{emoji} {names} {verb} back!"
BACK_BODY = "Draft continues"

BOT_NOTICE = "🤖 Resuming the draft with a Bot"

BOT_COLUMN = "🤖 Replace With Bot"
RESTART_COLUMN = "♻️ Restart Draft"
BOT_LABEL = "Replace With Bot"
RESTART_LABEL = "Restart Draft"
BOT_EMOJI = "🤖"
RESTART_EMOJI = "♻️"

VOTE_BUTTON_PREFIX = "poddropvote"
SIDE_BOT = "bot"
SIDE_RESTART = "restart"

_NEEDED_RE = re.compile(r"(\d+) vote")


def votes_needed(players_left: int) -> int:
    """Votes to decide it: a majority of the players still at the table. The first side there wins."""
    return max(1, players_left // 2 + 1)


def countdown(unix_seconds: int) -> str:
    """Discord's own relative clock, which counts down live and reads back as "2 minutes ago" once past."""
    return f"<t:{unix_seconds}:R>"


def build_waiting_embed(names: list[str], *, opens_at: int) -> discord.Embed:
    heading = DROP_HEADING.format(emoji=DROP_EMOJI, names=_bold_names(names))
    return discord.Embed(
        color=discord.Color.orange(),
        description=f"### {heading}\n{DROP_WAITING_BODY.format(when=countdown(opens_at))}",
    )


def build_offer_embed(names: list[str], *, dropped_at: int, needed: int,
                      bot_votes: list[str] | None = None,
                      restart_votes: list[str] | None = None) -> discord.Embed:
    """The vote card. Its heading carries the timestamp, which an embed title could never render. The
    vote target sits in the footer, where the click handler reads it back."""
    heading = OFFER_HEADING.format(
        emoji=DROP_EMOJI, names=_bold_names(names), when=countdown(dropped_at))
    embed = discord.Embed(color=discord.Color.orange(), description=f"### {heading}\n{OFFER_BODY}")
    embed.set_footer(text=OFFER_FOOTER.format(needed=needed, plural="" if needed == 1 else "s"))
    _set_columns(embed, bot_votes or [], restart_votes or [])
    return embed


def build_back_embed(names: list[str]) -> discord.Embed:
    heading = BACK_HEADING.format(emoji=BACK_EMOJI, names=_bold_names(names), verb=_is_are(names))
    return discord.Embed(color=discord.Color.green(), description=f"### {heading}\n{BACK_BODY}")


def rerender_offer(embed: discord.Embed, bot_votes: list[str], restart_votes: list[str]) -> discord.Embed:
    """A copy of an offer card with its two columns refreshed, heading and target preserved, so the click
    handler re-renders without needing the names or the vote target again."""
    fresh = discord.Embed.from_dict(embed.to_dict())
    _set_columns(fresh, bot_votes, restart_votes)
    return fresh


def bot_voters_from_embed(embed: discord.Embed) -> list[str]:
    return pod_vote_card.voters_from_field(embed, BOT_COLUMN)


def restart_voters_from_embed(embed: discord.Embed) -> list[str]:
    return pod_vote_card.voters_from_field(embed, RESTART_COLUMN)


def needed_from_embed(embed: discord.Embed) -> int | None:
    """The vote target parsed back off the card's footer, None once the card carries an outcome."""
    match = _NEEDED_RE.search(embed.footer.text or "")
    return int(match.group(1)) if match else None


async def delete_cards(messages: list[discord.Message]) -> bool:
    """Remove a stall's cards in one round of calls. False if any of them stayed up."""
    results = await asyncio.gather(*(message.delete() for message in messages), return_exceptions=True)
    return not any(isinstance(result, Exception) for result in results)


def build_side_button(side: str, *, custom_id: str | None = None) -> ui.Button:
    """One side's button. Shared by the live card, whose buttons carry the pod in their custom_id and
    survive a restart, and the `!test` preview, whose buttons answer to itself."""
    fill = side == SIDE_BOT
    return ui.Button(
        style=discord.ButtonStyle.primary if fill else discord.ButtonStyle.danger,
        label=BOT_LABEL if fill else RESTART_LABEL,
        emoji=BOT_EMOJI if fill else RESTART_EMOJI,
        custom_id=custom_id,
    )


VoteClickHandler = Callable[[discord.Interaction, str, str], Awaitable[None]]

_click_handler: VoteClickHandler | None = None


def register_vote_click_handler(handler: VoteClickHandler) -> None:
    """Wire the vote-click logic. The manager module registers it at import so this module stays free of a
    manager import."""
    global _click_handler
    _click_handler = handler


class DisconnectVoteButton(
    ui.DynamicItem[ui.Button], template=rf"{VOTE_BUTTON_PREFIX}:(?P<side>bot|restart):(?P<event_id>.+)"
):
    """A side button on a disconnect offer card. One per side per pod, so a single registration dispatches
    every offer and the buttons keep working after a restart."""

    def __init__(self, event_id: str, side: str) -> None:
        super().__init__(build_side_button(side, custom_id=f"{VOTE_BUTTON_PREFIX}:{side}:{event_id}"))
        self.event_id = event_id
        self.side = side

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: ui.Button, match: re.Match):
        return cls(match["event_id"], match["side"])

    async def callback(self, interaction: discord.Interaction) -> None:
        if _click_handler is None:
            await interaction.response.send_message(
                "This pod is no longer taking votes.", ephemeral=(interaction.guild is not None),
            )
            return
        await _click_handler(interaction, self.event_id, self.side)


def build_offer_view(event_id: str) -> ui.View:
    view = ui.View(timeout=None)
    view.add_item(DisconnectVoteButton(event_id, SIDE_BOT))
    view.add_item(DisconnectVoteButton(event_id, SIDE_RESTART))
    return view


def _set_columns(embed: discord.Embed, bot_votes: list[str], restart_votes: list[str]) -> None:
    pod_vote_card.set_columns(embed, [(BOT_COLUMN, bot_votes), (RESTART_COLUMN, restart_votes)])


def _bold_names(names: list[str]) -> str:
    return ", ".join(f"**{name}**" for name in names)


def _is_are(names: list[str]) -> str:
    return "is" if len(names) == 1 else "are"
