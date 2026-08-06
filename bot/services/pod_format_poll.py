"""Flashback format tally posted as its own embed card in a pod thread: players vote for any set they
would draft, shown as a green-pip bar and a vote count per option, one button per option plus a write-in.
A distinct thread message, styled like the Team Draft vote card, so it reads as a call to action.

The card decides nothing and locks nothing — its one job is showing which concrete set has enough people
tonight. The card message is the source of truth for the tally, exactly like the Team Draft card: each
option field carries its set code and its voters as mentions, so a click reads the current votes straight
off the message and the poll survives a restart with no vote table. Multiple choice — a click toggles the
clicker's vote for one option, and Any Flashback signals openness to every flashback set. The click and
write-in handlers are registered by the manager module so this module stays free of a manager import and
the buttons work before any live manager exists.
"""
from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from datetime import datetime

import discord
from discord import ui

from bot import emojis
from bot.discord_helpers import NBSP
from bot.services import pod_format_interest as fi
from bot.sets import active_set_code, set_name_for


FORMAT_POLL_PROMPT = "🗳️ Format Vote!"
FORMAT_POLL_GATHERING = "Vote for anything you would play"
FORMAT_POLL_CLOSED = "Voting closed. The tally below is final"
MSG_VOTE_POSTED = "Format Vote posted."
MSG_VOTE_ALREADY_UP = "A Format Vote is already up here."
MSG_VOTE_POST_FAILED = "Could not post the Format Vote. Try again."
CHANNEL_POLL_ID_PREFIX = "channel-"
ANY_FLASHBACK_CODE = "FLASH"
ANY_FLASHBACK_LABEL = "Any Flashback"
LATEST_BUTTON_LABEL = "Latest"
ADDED_BY_TEMPLATE = "[_added by {name}_]"
VOTE_BUTTON_PREFIX = "podformatpoll"
ADD_BUTTON_PREFIX = "podformataddfmt"
ADD_BUTTON_LABEL = "Add Format"
ADD_BUTTON_EMOJI_NAME = "plus"
ADD_BUTTON_EMOJI_FALLBACK = "➕"
ADD_MODAL_TITLE = "Add Format(s)"
ADD_MODAL_FIELD = "Set Codes"
ADD_MODAL_PLACEHOLDER = "e.g. DSK FIN MH3"
ROW_WIDTH = 5
MAX_ROWED_OPTIONS = 20
BAR_WIDTH = 8
BAR_FILL = "🟩"
BAR_EMPTY = "⬛"

_WRITE_IN_RE = re.compile(r"^[A-Z0-9]{2,6}$")
_WRITE_IN_SPLIT_RE = re.compile(r"[,\s]+")

_MENTION_RE = re.compile(r"<@!?(\d+)>")
_CODE_RE = re.compile(r"\[([A-Z0-9]+)\]")
_ADDED_BY_RE = re.compile(r"\[_added by (.+?)_\]")


def build_options(when: datetime | None = None) -> list[str]:
    """The default options the poll opens with: the latest set so "stay on the latest set" is always a
    choice, and the Any-Flashback signal. Every other set enters the tally by a player's vote or write-in,
    and the highest-voted set floats to the top by ``order_options``."""
    return [active_set_code(when), ANY_FLASHBACK_CODE]


def order_options(options: list[str], votes: dict[str, list[str]]) -> list[str]:
    """The card order: the latest set first and the Any-Flashback signal second, both pinned, then every
    other option by descending vote count so the best-voted set sits right below them, ties keeping their
    current card order."""
    if not options:
        return []
    latest = options[0]
    pinned = [latest]
    if ANY_FLASHBACK_CODE in options:
        pinned.append(ANY_FLASHBACK_CODE)
    rest = [code for code in options if code not in pinned]
    rest.sort(key=lambda code: len(votes.get(code, [])), reverse=True)
    return pinned + rest


def option_display_name(code: str) -> str:
    """The human name for an option: the Any-Flashback label for the signal option, the set's name for a
    real code, the bare code for an unregistered write-in."""
    if code == ANY_FLASHBACK_CODE:
        return ANY_FLASHBACK_LABEL
    return set_name_for(code)


def option_button_face(code: str) -> tuple[str | None, "discord.Emoji | str"]:
    """The (label, emoji) an option button wears: the set symbol alone when the set has an app emoji, the
    :flashback: glyph plus a label otherwise — "Any Flashback" for the signal option, the bare set code for
    any other. Shared by the live button and the testlobby preview so they cannot drift."""
    symbol = emojis.set_symbol(code)
    if symbol is not None:
        return (None, symbol)
    label = ANY_FLASHBACK_LABEL if code == ANY_FLASHBACK_CODE else code
    return (label, fallback_emoji())


def fallback_emoji() -> "discord.Emoji | str":
    """The glyph standing in for a set with no symbol app emoji: the :flashback: app emoji when loaded, the
    unicode ⏪ otherwise."""
    return fi.flashback_emoji()


def render_bar(count: int) -> str:
    """An eight-pip bar of one green square per vote — eight fills a full table. Filled and empty pips are
    both square emoji so every bar is the same width. The raw vote count follows, since the point is "this
    many would play it", not a share of a majority."""
    filled = max(0, min(BAR_WIDTH, count))
    bar = BAR_FILL * filled + BAR_EMPTY * (BAR_WIDTH - filled)
    unit = "Vote" if count == 1 else "Votes"
    return f"`{bar}` {NBSP}{count} {unit}"


def build_format_poll_embed(
    options: list[str], votes: dict[str, list[str]], adders: dict[str, str] | None = None,
) -> discord.Embed:
    """The tally card, green like the other pod cards. One field per option carries its bar and voters.
    Voters are display strings — mentions on the live card so the tally reads back off the message, plain
    names in previews."""
    embed = discord.Embed(
        color=discord.Color.green(),
        title=FORMAT_POLL_PROMPT,
        description=FORMAT_POLL_GATHERING,
    )
    _set_options(embed, options, votes, adders)
    return embed


def rerender_gathering(
    embed: discord.Embed, options: list[str], votes: dict[str, list[str]], adders: dict[str, str] | None = None,
) -> discord.Embed:
    fresh = discord.Embed.from_dict(embed.to_dict())
    _set_options(fresh, options, votes, adders)
    return fresh


def close_format_poll_embed(embed: discord.Embed) -> discord.Embed:
    """The tally frozen when the draft starts: the same fields, the description swapped to the closed note so
    the final vote stays on the thread instead of the card being deleted."""
    fresh = discord.Embed.from_dict(embed.to_dict())
    fresh.description = FORMAT_POLL_CLOSED
    return fresh


def _set_options(
    embed: discord.Embed, options: list[str], votes: dict[str, list[str]], adders: dict[str, str] | None = None,
) -> None:
    """One field per option: an eight-pip bar of one green square per vote, its voters, and an "added by"
    credit for a write-in."""
    embed.clear_fields()
    adders = adders or {}
    for code in options:
        voters = votes.get(code, [])
        value = render_bar(len(voters))
        roster = ", ".join(voters)
        if roster:
            value = f"{value}\n> {roster}"
        embed.add_field(name=_option_name(code, adders.get(code)), value=value, inline=False)


def _option_name(code: str, adder: str | None = None) -> str:
    if code == ANY_FLASHBACK_CODE:
        label = f"{_emoji_prefix(code)}{ANY_FLASHBACK_LABEL}"
    else:
        name = option_display_name(code)
        label = f"{_emoji_prefix(code)}[{code}]"
        if name and name != code:
            label = f"{label} {name}"
    if adder:
        label = f"{label} {ADDED_BY_TEMPLATE.format(name=adder)}"
    return label


def _emoji_prefix(code: str) -> str:
    symbol = emojis.set_symbol(code)
    return f"{symbol} " if symbol is not None else f"{fallback_emoji()} "


def _code_from_field(name: str | None) -> str | None:
    """The option's set code from its field name: the Any-Flashback signal by its label (it carries no
    bracket), any other option by the set code in brackets."""
    text = name or ""
    if ANY_FLASHBACK_LABEL in text:
        return ANY_FLASHBACK_CODE
    match = _CODE_RE.search(text)
    return match.group(1) if match else None


def votes_from_embed(embed: discord.Embed) -> dict[str, list[str]]:
    """Each option's voters read back off the card as ``<@id>`` mentions, keyed by its set code, deduped
    and in order."""
    tally: dict[str, list[str]] = {}
    for field in embed.fields:
        code = _code_from_field(field.name)
        if code is None:
            continue
        seen: set[str] = set()
        mentions: list[str] = []
        for user_id in _MENTION_RE.findall(field.value or ""):
            if user_id not in seen:
                seen.add(user_id)
                mentions.append(f"<@{user_id}>")
        tally[code] = mentions
    return tally


def adders_from_embed(embed: discord.Embed) -> dict[str, str]:
    """The write-in credit for each option, keyed by set code, read back off the "added by" tag in the
    field name so the attribution survives a re-render and a restart. Preset options have no credit."""
    adders: dict[str, str] = {}
    for field in embed.fields:
        code = _code_from_field(field.name)
        if code is None:
            continue
        adder_match = _ADDED_BY_RE.search(field.name or "")
        if adder_match is not None:
            adders[code] = adder_match.group(1)
    return adders


def options_from_embed(embed: discord.Embed) -> list[str]:
    codes: list[str] = []
    for field in embed.fields:
        code = _code_from_field(field.name)
        if code is not None and code not in codes:
            codes.append(code)
    return codes


def toggle_vote(votes: dict[str, list[str]], options: list[str], mention: str, code: str) -> None:
    """Add or retract one voter's vote for a single option. Multiple choice: their votes on other options
    are untouched, so a player can back several formats. ``options`` is unused, kept for call-site symmetry
    with the single-select era. Mutates ``votes`` in place."""
    del options
    voters = votes.setdefault(code, [])
    if mention in voters:
        voters.remove(mention)
    else:
        voters.append(mention)


async def find_format_poll_card(channel: discord.abc.Messageable, poll_id: str) -> discord.Message | None:
    """The format poll card for ``poll_id`` in this channel, located by any option button's keyed custom_id,
    so a restart or a manager takeover adopts the existing card instead of posting a second one."""
    suffix = f":{poll_id}"
    try:
        async for message in channel.history(limit=50):
            for row in message.components:
                for child in getattr(row, "children", []):
                    custom_id = getattr(child, "custom_id", "") or ""
                    if custom_id.startswith(f"{VOTE_BUTTON_PREFIX}:") and custom_id.endswith(suffix):
                        return message
    except discord.HTTPException:
        return None
    return None


FormatPollClickHandler = Callable[[discord.Interaction, str, str], Awaitable[None]]

_click_handler: FormatPollClickHandler | None = None


def register_format_poll_click_handler(handler: FormatPollClickHandler) -> None:
    """Wire the vote-click logic. The manager module registers it at import so this module stays free of a
    manager import and the buttons work whether or not a live manager backs the pod."""
    global _click_handler
    _click_handler = handler


def add_button_emoji() -> "discord.Emoji | str":
    """The write-in button glyph: the custom :plus: app emoji when loaded, the unicode ➕ otherwise."""
    return emojis.get_emoji(ADD_BUTTON_EMOJI_NAME) or ADD_BUTTON_EMOJI_FALLBACK


def normalize_write_in(raw: str | None) -> str | None:
    """A player-typed set code cleaned to the on-card form, or None when it is not a plausible code. Any
    two-to-six-character alphanumeric code is accepted; Draftmancer drafts by the lowercased code, and the
    card shows a set emoji when one exists for it."""
    if not raw:
        return None
    code = raw.strip().upper()
    return code if _WRITE_IN_RE.match(code) else None


def normalize_write_ins(raw: str | None) -> list[str]:
    """The plausible set codes in a comma or space separated write-in, in order and deduped, so a player can
    add or vote several formats at once (``DSK FIN MH3``). Unparseable tokens are dropped."""
    if not raw:
        return []
    codes: list[str] = []
    for token in _WRITE_IN_SPLIT_RE.split(raw.strip()):
        code = normalize_write_in(token)
        if code is not None and code not in codes:
            codes.append(code)
    return codes


class FormatPollButton(
    ui.DynamicItem[ui.Button], template=rf"{VOTE_BUTTON_PREFIX}:(?P<code>[^:]+):(?P<event_id>.+)"
):
    """One option button on a format poll card (set code + event id in the custom_id), so a single
    registration dispatches every poll and the buttons keep working after a restart. Icon only when the set
    has an emoji, the code as a label otherwise. A click toggles the clicker's vote for that option against
    the card message."""

    def __init__(
        self, event_id: str, code: str, label_override: str | None = None, row: int | None = None,
    ) -> None:
        label, emoji = option_button_face(code)
        if label_override is not None:
            label = label_override
        super().__init__(ui.Button(
            style=discord.ButtonStyle.secondary,
            label=label,
            emoji=emoji,
            custom_id=f"{VOTE_BUTTON_PREFIX}:{code}:{event_id}",
            row=row,
        ))
        self.event_id = event_id
        self.code = code

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: ui.Button, match: re.Match):
        return cls(match["event_id"], match["code"])

    async def callback(self, interaction: discord.Interaction) -> None:
        if _click_handler is None:
            await interaction.response.send_message(
                "This pod is no longer taking format votes.", ephemeral=(interaction.guild is not None),
            )
            return
        await _click_handler(interaction, self.event_id, self.code)


FormatPollAddHandler = Callable[[discord.Interaction, str, str, discord.Message], Awaitable[None]]

_add_handler: FormatPollAddHandler | None = None


def register_format_poll_add_handler(handler: FormatPollAddHandler) -> None:
    """Wire the write-in logic, registered by the manager at import for the same reason as the click
    handler: the button and modal stay free of a manager import."""
    global _add_handler
    _add_handler = handler


class AddFormatModal(ui.Modal, title=ADD_MODAL_TITLE):
    """The write-in dialog: a player types a set code to add it to the poll and vote for it in one step."""

    code = ui.TextInput(label=ADD_MODAL_FIELD, placeholder=ADD_MODAL_PLACEHOLDER, min_length=2, max_length=100)

    def __init__(self, event_id: str, message: discord.Message) -> None:
        super().__init__()
        self.event_id = event_id
        self.message = message

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if _add_handler is None:
            await interaction.response.send_message(
                "This pod is no longer taking new formats.", ephemeral=(interaction.guild is not None),
            )
            return
        await _add_handler(interaction, self.event_id, str(self.code.value), self.message)


class AddFormatButton(ui.DynamicItem[ui.Button], template=rf"{ADD_BUTTON_PREFIX}:(?P<event_id>.+)"):
    """The write-in button on a format poll card. Opens the AddFormatModal on the card it sits on, so the
    submitted code is added to that poll."""

    def __init__(self, event_id: str) -> None:
        super().__init__(ui.Button(
            style=discord.ButtonStyle.secondary, emoji=add_button_emoji(), label=ADD_BUTTON_LABEL,
            custom_id=f"{ADD_BUTTON_PREFIX}:{event_id}", row=0,
        ))
        self.event_id = event_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: ui.Button, match: re.Match):
        return cls(match["event_id"])

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(AddFormatModal(self.event_id, interaction.message))


def format_poll_button_layout(options: list[str]) -> list[tuple[str, str | None, int]]:
    """The (code, label, row) for each option button, shared by the live view and the testlobby preview so
    they keep the same shape: the latest set labeled "Latest" and the Any-Flashback signal sit in the top
    row beside the Add Format button, and every other option is an icon-only button flowing across the rows
    below, five to a row."""
    latest = options[0] if options else None
    layout: list[tuple[str, str | None, int]] = []
    rest: list[str] = []
    for code in options:
        if code == ANY_FLASHBACK_CODE:
            layout.append((code, None, 0))
        elif code == latest:
            layout.append((code, LATEST_BUTTON_LABEL, 0))
        else:
            rest.append(code)
    for index, code in enumerate(rest[:MAX_ROWED_OPTIONS]):
        layout.append((code, None, 1 + index // ROW_WIDTH))
    return layout


def build_format_poll_view(event_id: str, options: list[str]) -> ui.View:
    view = ui.View(timeout=None)
    view.add_item(AddFormatButton(event_id))
    for code, label_override, row in format_poll_button_layout(options):
        view.add_item(FormatPollButton(event_id, code, label_override=label_override, row=row))
    return view


def build_closed_format_poll_view(options: list[str]) -> ui.View:
    """The card's buttons after the draft starts: the same layout, every button disabled, so the final tally
    stays readable but no further votes land."""
    view = ui.View(timeout=None)
    view.add_item(ui.Button(
        style=discord.ButtonStyle.secondary, emoji=add_button_emoji(), label=ADD_BUTTON_LABEL,
        disabled=True, row=0,
    ))
    for code, label_override, row in format_poll_button_layout(options):
        label, emoji = option_button_face(code)
        if label_override is not None:
            label = label_override
        view.add_item(ui.Button(
            style=discord.ButtonStyle.secondary, label=label, emoji=emoji, disabled=True, row=row,
        ))
    return view
