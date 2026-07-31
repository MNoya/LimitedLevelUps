"""The "Pod Draft Scheduled!" thread embed: built once at registration, then re-rendered in
place whenever Format, Pairings, or Seats change through the lobby Settings panel."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import discord

from bot import emojis
from bot.services import pod_format_interest as fi
from bot.services.lobby_embed import SettingsButton
from bot.services.pod_format import format_display
from bot.services.pod_pairing_select import pairing_label
from bot.services.pod_roles import role_holder_mention
from bot.services.pod_seating_select import seating_mode_label
from bot.services.ping_roles import SET_CHAMPION_ROLE_NAME
from bot.sets import previous_set_code, set_name_for
from bot.tasks.pod_draft_reminder import REMINDER_LEAD_MIN

log = logging.getLogger("bot.pod_registration_embed")

REGISTERED_TITLE_TEXT = "Pod Draft Scheduled!"
CHAMPIONSHIP_TITLE = "👑 Set Championship registered!"
HISTORY_SCAN_LIMIT = 25
RSVP_HINT_LEAD = "Sign up with the buttons below or on the"
EVENT_POST_LABEL = "event post"
LINK_POSTED_LEAD = "Draftmancer link will be posted"
LINK_POSTED_LINE = LINK_POSTED_LEAD + " {lead} minutes before the event starts"
TIME_LINE = "<t:{unix}:F> (<t:{unix}:R>)"
STARTED_TIME_LINE = "Started <t:{unix}:R>"
TIME_TOKEN_RE = re.compile(r"<t:(\d{1,15}):[a-zA-Z]>")


class RegisteredSettingsView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(SettingsButton())


def championship_flavor(set_code: str, reigning_champion: str | None = None) -> str:
    lines = [
        f"**{set_name_for(set_code)}** Season!",
        "Eight seats to the highest-ranked players who claim them.",
    ]
    if reigning_champion:
        lines.append("")
        lines.append(f"**Reigning Set Champion:** {_previous_set_symbol(set_code)}{reigning_champion}")
    return "\n".join(lines)


def rsvp_hint_line(channel_post_url: str | None) -> str:
    """The RSVP prompt for the trailing field below the columns, linking the event post when its jump
    url is known and trailing the tap glyph. It's a field value, so it renders a real link (a footer
    can't) but not `-#` subtext (fields don't), which is why it leans on the emoji for structure."""
    linked = f"[**{EVENT_POST_LABEL}**]({channel_post_url})" if channel_post_url else f"**{EVENT_POST_LABEL}**"
    tap = emojis.get("manat")
    suffix = f" {tap}" if tap else ""
    return f"{RSVP_HINT_LEAD} {linked}{suffix}"


def build_registered_embed(
    set_code: str, pairing_mode: str | None, seating_mode: str | None = None,
    *, championship: bool = False, rsvp_hint: bool = False, channel_post_url: str | None = None,
    guild: discord.Guild | None = None, event_time: datetime | None = None,
) -> discord.Embed:
    """`rsvp_hint` is on only for the bot-native scheduled card, which carries the RSVP buttons and a
    channel post; sesh pods reuse this embed as a config panel with neither, so they leave it off.
    `guild` resolves the reigning Set Champion mention for the championship flavor when known.
    `event_time` repeats the start time the channel card carries, so a reader who came straight to the
    thread does not have to climb back out to the card to see when the pod fires. A sesh config panel
    has no event of its own and leaves it off."""
    body = LINK_POSTED_LINE.format(lead=REMINDER_LEAD_MIN)
    if event_time is not None:
        body = f"{TIME_LINE.format(unix=int(event_time.timestamp()))}\n{body}"
    if championship:
        reigning_champion = role_holder_mention(guild, SET_CHAMPION_ROLE_NAME)
        body = f"{championship_flavor(set_code, reigning_champion)}\n\n{body}"
    title = CHAMPIONSHIP_TITLE if championship else f"{emojis.prefix('chordoHello')}{REGISTERED_TITLE_TEXT}"
    embed = discord.Embed(title=title, description=body, color=discord.Color.green())
    embed.add_field(name="Format", value=f"{fi.format_emoji(set_code)} {format_display(set_code)}", inline=True)
    embed.add_field(name="Pairings", value=pairing_label(pairing_mode), inline=True)
    embed.add_field(name="Seats", value=seating_mode_label(seating_mode), inline=True)
    if rsvp_hint:
        embed.add_field(name="​", value=rsvp_hint_line(channel_post_url), inline=False)
    return embed


async def update_registered_embed(
    channel: discord.abc.Messageable | None,
    *,
    client_user: discord.ClientUser | None,
    set_code: str,
    pairing_mode: str | None,
    seating_mode: str | None = None,
    championship: bool = False,
    event_time: datetime | None = None,
) -> None:
    """Walk the thread for the bot's registration embed and re-render it with the current settings.
    `event_time` is for a reschedule, which is the only caller that knows the time changed; every other
    caller leaves it off and the embed keeps the time it already shows."""
    if channel is None or client_user is None:
        return
    guild = getattr(channel, "guild", None)
    try:
        async for msg in channel.history(limit=HISTORY_SCAN_LIMIT, oldest_first=True):
            if msg.author.id == client_user.id and msg.embeds and _is_registered_title(msg.embeds[0].title):
                existing = msg.embeds[0]
                rsvp_hint = any(RSVP_HINT_LEAD in (f.value or "") for f in existing.fields)
                rebuilt = build_registered_embed(
                    set_code, pairing_mode, seating_mode, championship=championship,
                    rsvp_hint=rsvp_hint, channel_post_url=_card_url_from_thread(channel), guild=guild,
                    event_time=event_time or embed_event_time(existing))
                if _is_closed(existing):
                    rebuilt = closed_registered_embed(rebuilt)
                await msg.edit(embed=rebuilt)
                return
    except discord.HTTPException:
        log.warning("could not update Pod Draft registered embed", exc_info=True)


def closed_registered_embed(embed: discord.Embed) -> discord.Embed:
    """The registration embed once its pod stops taking signups. Format, Pairings, and Seats stay as the
    record of what was drafted; the lines that only hold while signups are open go."""
    unix = _time_token(embed.description)
    closed = discord.Embed(
        title=embed.title, description=_closed_time_line(unix) if unix else None, color=embed.color)
    for field in embed.fields:
        if RSVP_HINT_LEAD not in (field.value or ""):
            closed.add_field(name=field.name, value=field.value, inline=field.inline)
    return closed


def embed_event_time(embed: discord.Embed) -> datetime | None:
    """The start time a registration embed already carries, so a re-render keeps it without every caller
    having to load the event row."""
    unix = _time_token(embed.description)
    return datetime.fromtimestamp(unix, timezone.utc) if unix else None


def _time_token(text: str | None) -> int | None:
    match = TIME_TOKEN_RE.search(text or "")
    return int(match.group(1)) if match else None


def _closed_time_line(unix: int) -> str:
    """A pod closed after its start time ran; one closed before it never did, so it keeps the plain
    timestamp instead of claiming a start that did not happen."""
    if unix <= int(datetime.now(timezone.utc).timestamp()):
        return STARTED_TIME_LINE.format(unix=unix)
    return TIME_LINE.format(unix=unix)


def _is_closed(embed: discord.Embed) -> bool:
    return LINK_POSTED_LEAD not in (embed.description or "")


def _previous_set_symbol(set_code: str) -> str:
    prev = previous_set_code(set_code)
    return emojis.prefix(prev.lower()) if prev else ""


def _card_url_from_thread(channel: discord.abc.Messageable) -> str | None:
    """The scheduled card is the thread's starter, so it shares the thread id and lives in the thread's
    parent channel — enough to rebuild its jump link on re-render without another fetch. None when the
    surface isn't a thread (a plain settings panel), which drops the hint to unlinked text."""
    parent_id = getattr(channel, "parent_id", None)
    guild = getattr(channel, "guild", None)
    if parent_id is None or guild is None:
        return None
    return f"https://discord.com/channels/{guild.id}/{parent_id}/{channel.id}"


_MATCHABLE_TITLE_SUFFIXES = (REGISTERED_TITLE_TEXT, CHAMPIONSHIP_TITLE, "Pod Draft registered!")


def _is_registered_title(title: str | None) -> bool:
    """The registration embed's title carries the set symbol, so match on the stable text suffix.
    The legacy 'Pod Draft registered!' text is kept so a pod scheduled before this shipped still
    gets its embed refreshed on a settings change."""
    return bool(title) and title.endswith(_MATCHABLE_TITLE_SUFFIXES)
