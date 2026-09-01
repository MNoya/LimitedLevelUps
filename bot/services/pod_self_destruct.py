"""The card a stalled pod gets when it sat under-filled and idle: an offer to close it, with a Keep it
Open button anyone at the table can press to stop the close.

The card is one Components V2 message. A V2 card and an embed look the same, but text in a V2 TextDisplay
counts as message content for notifications while an embed's does not, so the ping to whoever opened the
pod lives inside the card and reaches them. The button carries the pod in its custom_id so a stalled lobby
that outlives a bot restart still has a working Keep. The click handler is registered by the manager
module; this module owns the card, the button, and the reads so the live message and the `!test` preview
can't drift.
"""
from __future__ import annotations

import re
from collections.abc import Awaitable, Callable

import discord
from discord import ui


FIRECRACKER_EMOJI = "🧨"
OFFER_HEADING = "{emoji} Inactive pod will close {when}"
KEEP_EMOJI = "✅"
KEPT_HEADING = "{emoji} {actor} kept this pod open"
CLOSE_EMOJI = "❌"
CLOSED_HEADING = "{emoji} {actor} closed this pod"

KEEP_LABEL = "Keep it Open"
CLOSE_LABEL = "Close it"
KEEP_BUTTON_PREFIX = "podkeep"
CLOSE_BUTTON_PREFIX = "podclose"


def countdown(unix_seconds: int) -> str:
    """Discord's own relative clock, which counts down live and reads back as "2 minutes ago" once past."""
    return f"<t:{unix_seconds}:R>"


def offer_heading(closes_at: int) -> str:
    return f"### {OFFER_HEADING.format(emoji=FIRECRACKER_EMOJI, when=countdown(closes_at))}"


def kept_heading(actor: str) -> str:
    return f"### {KEPT_HEADING.format(emoji=KEEP_EMOJI, actor=actor)}"


def closed_heading(actor: str) -> str:
    return f"### {CLOSED_HEADING.format(emoji=CLOSE_EMOJI, actor=actor)}"


def build_offer_card(event_id: str, *, closes_at: int, mention: str | None = None) -> ui.LayoutView:
    return _OfferCard(event_id, closes_at=closes_at, mention=mention)


def build_kept_card(actor: str) -> ui.LayoutView:
    return _OutcomeCard(kept_heading(actor), discord.Colour.green())


def build_closed_card(actor: str) -> ui.LayoutView:
    return _OutcomeCard(closed_heading(actor), discord.Colour.dark_grey())


ClickHandler = Callable[[discord.Interaction, str], Awaitable[None]]

_keep_handler: ClickHandler | None = None
_close_handler: ClickHandler | None = None


def register_keep_click_handler(handler: ClickHandler) -> None:
    """Wire the Keep-click logic. The manager module registers it at import so this module stays free of a
    manager import."""
    global _keep_handler
    _keep_handler = handler


def register_close_click_handler(handler: ClickHandler) -> None:
    global _close_handler
    _close_handler = handler


class KeepPodButton(ui.DynamicItem[ui.Button], template=rf"{KEEP_BUTTON_PREFIX}:(?P<event_id>.+)"):
    """The Keep button on a self-destruct offer card. One registration dispatches every offer and the
    button keeps working after a restart."""

    def __init__(self, event_id: str) -> None:
        super().__init__(ui.Button(
            style=discord.ButtonStyle.success,
            label=KEEP_LABEL,
            emoji=KEEP_EMOJI,
            custom_id=f"{KEEP_BUTTON_PREFIX}:{event_id}",
        ))
        self.event_id = event_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: ui.Button, match: re.Match):
        return cls(match["event_id"])

    async def callback(self, interaction: discord.Interaction) -> None:
        if _keep_handler is None:
            await interaction.response.send_message(
                "This pod is no longer open", ephemeral=(interaction.guild is not None),
            )
            return
        await _keep_handler(interaction, self.event_id)


class ClosePodButton(ui.DynamicItem[ui.Button], template=rf"{CLOSE_BUTTON_PREFIX}:(?P<event_id>.+)"):
    """The Close it button on a self-destruct offer card, shown only when the pod has a creator to ping.
    It closes the pod now instead of waiting out the countdown."""

    def __init__(self, event_id: str) -> None:
        super().__init__(ui.Button(
            style=discord.ButtonStyle.secondary,
            label=CLOSE_LABEL,
            emoji=CLOSE_EMOJI,
            custom_id=f"{CLOSE_BUTTON_PREFIX}:{event_id}",
        ))
        self.event_id = event_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: ui.Button, match: re.Match):
        return cls(match["event_id"])

    async def callback(self, interaction: discord.Interaction) -> None:
        if _close_handler is None:
            await interaction.response.send_message(
                "This pod is no longer open", ephemeral=(interaction.guild is not None),
            )
            return
        await _close_handler(interaction, self.event_id)


class _OfferCard(ui.LayoutView):
    def __init__(self, event_id: str, *, closes_at: int, mention: str | None = None) -> None:
        super().__init__(timeout=None)
        container = ui.Container(accent_colour=discord.Colour.orange())
        self.add_item(container)
        text = offer_heading(closes_at)
        if mention:
            text = f"{text}\n{mention}"
        container.add_item(ui.TextDisplay(text))
        row = ui.ActionRow()
        row.add_item(KeepPodButton(event_id))
        if mention:
            row.add_item(ClosePodButton(event_id))
        self.add_item(row)


class _OutcomeCard(ui.LayoutView):
    def __init__(self, heading: str, colour: discord.Colour) -> None:
        super().__init__(timeout=None)
        container = ui.Container(accent_colour=colour)
        self.add_item(container)
        container.add_item(ui.TextDisplay(heading))
