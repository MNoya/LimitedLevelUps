"""The /mock-draft anchor card: the channel message the draft thread hangs off, edited in place from
lobby open through draft finished.

It is the only mock-draft surface people outside the thread see, so it carries the live Draftmancer
roster and exactly one call to action per phase. The site link rides the card as text while the draft
is pending and graduates to a Draft Recap button once there is something to read.
"""
from __future__ import annotations

import discord

from bot import emojis
from bot.commands.messages import (
    MSG_MOCK_CARD_CANCELED,
    MSG_MOCK_CARD_CANCELED_NO_ACTOR,
    MSG_MOCK_CARD_COMPLETE,
    MSG_MOCK_CARD_DISCORD_NAME,
    MSG_MOCK_CARD_DRAFTING,
    MSG_MOCK_CARD_EMPTY_TABLE,
    MSG_MOCK_CARD_FULL,
    MSG_MOCK_CARD_LOGS_PENDING,
    MSG_MOCK_CARD_OPEN,
    MSG_MOCK_CARD_PLAYERS,
    MSG_MOCK_CARD_RECAP_BUTTON,
    MSG_MOCK_CARD_SPECTATE_BUTTON,
)
from bot.config import settings
from bot.discord_helpers import quote_block
from bot.services.lobby_embed import event_title
from bot.services.pod_format import is_custom
from bot.services.pod_join_button import build_mock_join_view
from bot.sets import is_cube_board_code


STATE_OPEN = "open"
STATE_DRAFTING = "drafting"
STATE_COMPLETE = "complete"
STATE_CANCELED = "canceled"

CUBE_SYMBOL = "cube"

_COLORS = {
    STATE_OPEN: discord.Color.green(),
    STATE_DRAFTING: discord.Color.blurple(),
    STATE_COMPLETE: discord.Color.gold(),
    STATE_CANCELED: discord.Color.light_grey(),
}


def build_mock_card(
    *,
    event_name: str,
    set_code: str,
    session_id: str,
    session_url: str,
    site_url: str,
    roster: list[tuple[str, str | None]],
    max_players: int,
    state: str = STATE_OPEN,
    spectate_url: str | None = None,
    canceled_by: str | None = None,
) -> tuple[discord.Embed, discord.ui.View | None]:
    """`roster` is Draftmancer session users as (arena_name, linked_display_name_or_None), the same
    shape the in-thread lobby card renders. A canceled card drops the site link because cancelling
    deletes the event row, which takes its page with it."""
    embed = discord.Embed(
        title=event_title(set_code, event_name),
        description=_description(state, session_url, canceled_by, table_full=len(roster) >= max_players),
        color=_COLORS.get(state, discord.Color.green()),
    )
    thumbnail = set_symbol_url(set_code)
    if thumbnail and state != STATE_CANCELED:
        embed.set_thumbnail(url=thumbnail)
    seats = _seat_list(roster)
    if state in (STATE_OPEN, STATE_DRAFTING):
        pending = MSG_MOCK_CARD_LOGS_PENDING.format(url=site_url, llu=emojis.get("llu")).rstrip()
        seats = f"{seats}\n{pending}"
    embed.add_field(
        name=MSG_MOCK_CARD_PLAYERS.format(count=len(roster)),
        value=seats,
        inline=False,
    )
    if state == STATE_OPEN:
        embed.set_footer(text=MSG_MOCK_CARD_DISCORD_NAME)
    return embed, _view(state, session_id, site_url, spectate_url)


def set_symbol_url(set_code: str) -> str | None:
    """The set symbol the website serves, used as the card thumbnail. Every cube board and custom cube
    shares the one cube symbol, matching how `pod_schedule_image` and the app emojis resolve them."""
    cube = is_cube_board_code(set_code) or is_custom(set_code)
    name = CUBE_SYMBOL if cube else set_code.lower()
    base = settings.public_site_url.rstrip("/")
    return f"{base}/set-symbols/{name}.png" if base else None


def _description(state: str, session_url: str, canceled_by: str | None, *, table_full: bool) -> str:
    if state == STATE_OPEN:
        heading = MSG_MOCK_CARD_FULL if table_full else MSG_MOCK_CARD_OPEN
        return f"### {heading}\n{session_url}"
    heading = {
        STATE_DRAFTING: MSG_MOCK_CARD_DRAFTING,
        STATE_COMPLETE: MSG_MOCK_CARD_COMPLETE,
        STATE_CANCELED: _canceled_heading(canceled_by),
    }[state]
    return f"### {heading}"


def _canceled_heading(canceled_by: str | None) -> str:
    if canceled_by is None:
        return MSG_MOCK_CARD_CANCELED_NO_ACTOR
    return MSG_MOCK_CARD_CANCELED.format(actor=canceled_by)


def _seat_list(roster: list[tuple[str, str | None]]) -> str:
    """A seat with no matching player shows its Draftmancer name plainly: a mock draft is drafted under
    Discord names and links no Arena handles, so an unmatched seat is ordinary, not a problem to flag."""
    if not roster:
        return quote_block([MSG_MOCK_CARD_EMPTY_TABLE])
    return quote_block([display_name or arena_name for arena_name, display_name in roster])


def _view(
    state: str, session_id: str, site_url: str, spectate_url: str | None,
) -> discord.ui.View | None:
    if state == STATE_OPEN:
        return build_mock_join_view(session_id)
    if state == STATE_DRAFTING:
        if spectate_url is None:
            return None
        return _link_view(MSG_MOCK_CARD_SPECTATE_BUTTON, spectate_url, "👀")
    if state == STATE_COMPLETE:
        return _link_view(MSG_MOCK_CARD_RECAP_BUTTON, site_url, emojis.get_emoji("llu"))
    return None


def _link_view(label: str, url: str, emoji) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(
        label=label, style=discord.ButtonStyle.link, url=url, emoji=emoji,
    ))
    return view
