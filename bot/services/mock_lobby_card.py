"""The /mock-draft anchor card: the channel message the draft thread hangs off, edited in place from
lobby open through draft finished.

It is the only mock-draft surface people outside the thread see, so it carries the live Draftmancer
roster and exactly one call to action per phase. The site link rides the card as text while the draft
is pending and graduates to a Draft Recap button once there is something to read.

The ask reads on the message content, not inside the embed, because that line is also where the Mock
Draft role is tagged and only content delivers a ping; the embed carries the lobby's own phase.
Content, embed, and view are built together so the two can never contradict each other.

`MOCK_CARD_PING` and `MOCK_CARD_QUIET` are the two ways a copy of the card can carry that tag. The
allowed list also drives Discord's mention highlight, so a card has to be edited under the same one it
was posted with: the anchor announced the lobby and stays highlighted, a `!mock` repost stays quiet.
"""
from __future__ import annotations

import re

import discord

from bot import emojis
from bot.commands.messages import (
    MSG_CARD_CREATED_BY,
    MSG_MOCK_CARD_CANCELED,
    MSG_MOCK_CARD_CANCELED_IDLE,
    MSG_MOCK_CARD_CANCELED_NO_ACTOR,
    MSG_MOCK_CARD_CLOSES,
    MSG_MOCK_CARD_COMPLETE,
    MSG_MOCK_CARD_CONTENT,
    MSG_MOCK_CARD_DISCORD_NAME,
    MSG_MOCK_CARD_DRAFTERS,
    MSG_MOCK_CARD_DRAFTING,
    MSG_MOCK_CARD_EMPTY_TABLE,
    MSG_MOCK_CARD_FULL,
    MSG_MOCK_CARD_LOGS_PENDING,
    MSG_MOCK_CARD_NEEDS,
    MSG_MOCK_CARD_NEEDS_ONE,
    MSG_MOCK_CARD_OPEN,
    MSG_MOCK_CARD_OPENING,
    MSG_MOCK_CARD_PLAYERS,
    MSG_MOCK_CARD_RECAP_BUTTON,
    MSG_MOCK_CARD_SPECTATE_BUTTON,
    MSG_MOCK_CARD_THREAD_BUTTON,
)
from bot.config import settings
from bot.discord_helpers import NBSP, quote_block
from bot.services.lobby_embed import event_title
from bot.services.pod_format import is_custom, symbol_glyph_for
from bot.services.pod_join_button import build_mock_join_view
from bot.services.pod_signals import inactivity_window_text
from bot.sets import is_cube_board_code


MOCK_CARD_PING = discord.AllowedMentions(roles=True)
MOCK_CARD_QUIET = discord.AllowedMentions.none()

STATE_OPENING = "opening"
STATE_OPEN = "open"
STATE_DRAFTING = "drafting"
STATE_COMPLETE = "complete"
STATE_CANCELED = "canceled"

CUBE_SYMBOL = "cube"

_COLORS = {
    STATE_OPENING: discord.Color.green(),
    STATE_OPEN: discord.Color.green(),
    STATE_DRAFTING: discord.Color.blurple(),
    STATE_COMPLETE: discord.Color.green(),
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
    role_mention: str,
    state: str = STATE_OPEN,
    spectate_url: str | None = None,
    canceled_by: str | None = None,
    canceled_idle: bool = False,
    thread_url: str | None = None,
    created_by: str | None = None,
) -> tuple[str, discord.Embed, discord.ui.View | None]:
    """The card as (content, embed, view). `roster` is Draftmancer session users as (arena_name,
    linked_display_name_or_None), the same shape the in-thread lobby card renders. A canceled card drops
    the seat list and the site link: nobody drafted, and cancelling deletes the event row, which takes
    its page with it. `canceled_idle` names the inactivity sweep as the closer, since no player did it.

    `thread_url` adds a button into the draft thread, and is passed by the `!mock` repost only: the
    anchor has its thread hanging off it, while a repost is a plain message with no way in.

    STATE_OPENING withholds the session link and the Join button: Draftmancer makes whoever enters an
    empty session first its owner, so a player reaching the lobby before the bot would take it.

    `created_by` credits whoever ran `/mock-draft`, the same footer credit an out-of-schedule pod carries.
    A card rebuilt after a restart has nobody to credit and leaves the name off."""
    embed = discord.Embed(
        title=event_title(set_code, card_name(event_name)),
        description=_description(state, session_url, canceled_by, canceled_idle),
        color=_COLORS.get(state, discord.Color.green()),
    )
    thumbnail = set_symbol_url(set_code)
    if thumbnail and state != STATE_CANCELED:
        embed.set_thumbnail(url=thumbnail)
    if state != STATE_CANCELED:
        seats = _seat_list(roster)
        if state != STATE_COMPLETE:
            pending = MSG_MOCK_CARD_LOGS_PENDING.format(url=site_url, llu=emojis.get("llu")).rstrip()
            seats = f"{seats}\n{pending}"
        embed.add_field(
            name=_seat_label(state).format(count=len(roster)),
            value=seats,
            inline=False,
        )
    if state in (STATE_OPENING, STATE_OPEN):
        embed.set_footer(text=f"{MSG_MOCK_CARD_DISCORD_NAME}\n{_closes_line(created_by)}")
    content = _content(state, role_mention, seated=len(roster), max_players=max_players)
    return content, embed, _view(state, session_id, site_url, spectate_url, thread_url)


_CARD_NUMBER_RE = re.compile(r"\s+\d+$")


def card_name(event_name: str) -> str:
    """The event name without its trailing per-set number. The thread beside the card already carries
    the numbered name, so repeating it in the title reads as noise."""
    return _CARD_NUMBER_RE.sub("", event_name)


def set_symbol_url(set_code: str) -> str | None:
    """The set symbol the website serves, used as the card thumbnail. Every cube board and custom cube
    shares the one cube symbol, matching how `pod_schedule_image` and the app emojis resolve them."""
    glyph = symbol_glyph_for(set_code)
    if glyph is not None:
        name = glyph
    elif is_cube_board_code(set_code) or is_custom(set_code):
        name = CUBE_SYMBOL
    else:
        name = set_code.lower()
    base = settings.public_site_url.rstrip("/")
    return f"{base}/set-symbols/{name}.png" if base else None


def build_mock_complete_view(site_url: str, thread_url: str) -> discord.ui.View:
    """Recap + Thread buttons for the channel-level finish announcement, built from the same pair the
    anchor card carries once it flips to complete."""
    return _view(STATE_COMPLETE, "", site_url, None, thread_url)


def _seat_label(state: str) -> str:
    """The check mark answers the question a gathering lobby is asking, which is who has actually turned
    up in Draftmancer. Once the draft is under way they are simply the players at the table."""
    if state in (STATE_DRAFTING, STATE_COMPLETE):
        return MSG_MOCK_CARD_PLAYERS
    return MSG_MOCK_CARD_DRAFTERS


def _closes_line(created_by: str | None) -> str:
    """The window an open lobby stands down after, so a card nobody answers reads as temporary, led by
    whoever opened it."""
    closes = MSG_MOCK_CARD_CLOSES.format(window=inactivity_window_text(settings.pod_idle_offer_minutes))
    if not created_by:
        return closes
    gap = NBSP * 3
    return f"{MSG_CARD_CREATED_BY.format(name=created_by)}{gap}|{gap}{closes}"


def _description(state: str, session_url: str, canceled_by: str | None, canceled_idle: bool) -> str:
    """The card's own line about where the lobby is. An open lobby shows the link instead: the content
    line above already asks for drafters, and the link is the only thing left to act on."""
    if state == STATE_OPEN:
        return session_url
    phase = _phase_line(state, canceled_by, canceled_idle)
    return f"### {phase[:1].upper()}{phase[1:]}"


def _content(state: str, role_mention: str, *, seated: int, max_players: int) -> str:
    """The line above the card, which is where the role tag lives. Only a lobby taking drafters carries
    one: the tag asks the role to come and draft, and once the lobby stops taking them the card heading
    says where it stands on its own. A lobby still gathering asks for drafters even while it opens."""
    if state not in (STATE_OPENING, STATE_OPEN):
        return ""
    return MSG_MOCK_CARD_CONTENT.format(role=role_mention, state=_open_line(seated, max_players))


def _phase_line(state: str, canceled_by: str | None, canceled_idle: bool) -> str:
    """Where a lobby that is not taking drafters stands. Written lowercase because its other home is
    mid-sentence, after the role tag on the content line; the card heading capitalizes it."""
    return {
        STATE_OPENING: MSG_MOCK_CARD_OPENING,
        STATE_DRAFTING: MSG_MOCK_CARD_DRAFTING,
        STATE_COMPLETE: MSG_MOCK_CARD_COMPLETE,
        STATE_CANCELED: _canceled_line(canceled_by, canceled_idle),
    }[state]


def _open_line(seated: int, max_players: int) -> str:
    """An empty lobby asks for drafters; a lobby with someone in it counts the seats left, which is what
    a repost into live chat needs to say. The count is what makes a bump worth reading."""
    if seated >= max_players:
        return MSG_MOCK_CARD_FULL
    if seated == 0:
        return MSG_MOCK_CARD_OPEN
    missing = max_players - seated
    if missing == 1:
        return MSG_MOCK_CARD_NEEDS_ONE
    return MSG_MOCK_CARD_NEEDS.format(count=missing)


def _canceled_line(canceled_by: str | None, canceled_idle: bool) -> str:
    if canceled_idle:
        window = inactivity_window_text(settings.pod_idle_offer_minutes)
        return MSG_MOCK_CARD_CANCELED_IDLE.format(window=window)
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
    state: str, session_id: str, site_url: str, spectate_url: str | None, thread_url: str | None,
) -> discord.ui.View | None:
    view = _state_view(state, session_id, site_url, spectate_url)
    if thread_url is None:
        return view
    if view is None:
        view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(
        label=MSG_MOCK_CARD_THREAD_BUTTON, style=discord.ButtonStyle.link, url=thread_url,
    ))
    return view


def _state_view(
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
