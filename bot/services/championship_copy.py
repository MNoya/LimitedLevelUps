"""Set Championship user-facing copy — the one place the live flow and `!test championship` both
render from, so the preview always matches what ships.

Plain declarative voice. Callers pass mention tokens rather than ids, so the same builder serves the
live flow (a real `<@id>` / `<@&roleid>`) and the preview (a synthetic `**@name**` that shows the
shape without pinging anyone).
"""
from __future__ import annotations

from datetime import datetime

import discord
from discord import ui

from bot import emojis
from bot.config import settings
from bot.services.championship import INVITE_WAVE_TIERS
from bot.services.containers import build_container
from bot.services.mock_lobby_card import set_symbol_url
from bot.services.ping_roles import SYNTHETIC_CHAMPION_TAG
from bot.services.pod_signals import RSVP_EMOJI

TWITCH_URL = "https://twitch.tv/GatoDelFuego"


def standings_url(set_code: str) -> str:
    return f"{settings.public_site_url.rstrip('/')}/leaderboard/{set_code.upper()}"


def champion_mention_for_wave(wave_index: int, role: discord.Role | None) -> str:
    """Wave 0 carries the real role tag so it renders the sky-blue pill; later waves carry the
    synthetic label so the champion is not pinged on every wave. A missing role falls back too."""
    if wave_index == 0 and role is not None:
        return role.mention
    return SYNTHETIC_CHAMPION_TAG


def wave_recipient_line(rsvp_state: str | None, *, mention: str, display_name: str) -> str:
    """One wave recipient: their ping when they have not answered yet, or their RSVP status emoji and
    name once they have, so a wave never re-pings someone who already RSVP'd."""
    if rsvp_state is None:
        return mention
    return f"{RSVP_EMOJI[rsvp_state]} {display_name}"


def card_content(
    *, set_name: str, set_code: str, next_set_name: str, next_set_code: str,
    next_release_at: datetime, champion_mention: str,
) -> str:
    """The announcement inside the RSVP card, closing off the set and pointing at standings and stream."""
    arrival = int(next_release_at.timestamp())
    next_symbol = emojis.prefix(next_set_code.lower())
    return (
        f"{_closing_lines(set_name, champion_mention)}\n\n"
        f"📊 **Standings:** [limitedlevelups.com/leaderboard](<{standings_url(set_code)}>)\n"
        f"📺 **Streamed live:** [twitch.tv/GatoDelFuego](<{TWITCH_URL}>)\n\n"
        "**How it works**\n"
        "• RSVP here if you can make it. The eight highest-ranked players who show up take the seats, "
        "the rest are alternates for no-shows.\n"
        "• Best of 3, Swiss, three rounds, one Champion.\n\n"
        f"{next_symbol}**{next_set_name}** arrives <t:{arrival}:R>"
    )


def native_event_body(*, set_name: str, set_code: str, champion_mention: str) -> str:
    """The card's opening, for the native scheduled event's description. The Events tab renders no
    masked links, so the standings and stream addresses are written out, and the seat rules stay on
    the card where the RSVP buttons are."""
    return (
        f"{_closing_lines(set_name, champion_mention)}\n\n"
        f"📊 **Standings:** {bare_url(standings_url(set_code))}\n"
        f"📺 **Streamed live:** {bare_url(TWITCH_URL)}"
    )


def explainer(
    *, set_code: str, event_at: datetime | None, signup_at: datetime | None, champion_mention: str,
    card_url: str | None, coordination_channel: str,
) -> ui.Container:
    """The `!championship` container. Evergreen: the date shows only while an edition is ahead, and the
    signup line either links the posted card or says when it arrives."""
    symbol = emojis.prefix(set_code.lower())
    header = (
        "## 👑 Set Championship\n"
        "Each set we host a tournament where top performing Discord members draft for the privilege of being crowned "
        f"{champion_mention}"
    )
    lines = []
    if event_at is not None:
        lines.append(f"{symbol}**{set_code} Championship:** <t:{int(event_at.timestamp())}:F>")
        lines.append("")
    lines.append(f"{emojis.prefix('llu')}[**Leaderboard**](<{standings_url(set_code)}>) standings decide who plays. "
                 f"Matches streamed at [**twitch.tv/GatoDelFuego**](<{TWITCH_URL}>)")
    if card_url is not None:
        lines.append(f"\n[**Event signup**]({card_url}) is now open at {coordination_channel}")
    elif signup_at is not None:
        lines.append(f"\nEvent signup will be posted on {coordination_channel} "
                     f"<t:{int(signup_at.timestamp())}:R>")
    return build_container(header, set_symbol_url(set_code), "\n".join(lines))


def wave_invite_ping(
    wave_index: int, set_code: str, mention_tokens: list[str], event_at: datetime, post_url: str,
    champion_mention: str,
) -> str:
    """One invite wave posted in the thread: the tier headline linking back to the championship card,
    the tier's mentions one per line, and the confirm instructions. The Confirm button beside it
    records the same Yes as the card."""
    headline = _wave_headline(wave_index, set_code, post_url)
    mentions = "\n".join(mention_tokens)
    when = f"<t:{int(event_at.timestamp())}:F>"
    return (
        f"{headline}\n\n"
        f"{mentions}\n\n"
        f"Please **Confirm** if you can make it {when}\n"
        f"Seats go to the top players in the [**leaderboard**](<{standings_url(set_code)}>) who show up, "
        "the rest are alternates.\n\n"
        "-# 8-player Pod Draft, Best-of-Three, three Swiss rounds paired by record. "
        "You can play all rounds even after a loss. "
        f"Winner is crowned {champion_mention}"
    )


def bare_url(url: str) -> str:
    return url.removeprefix("https://")


def _closing_lines(set_name: str, champion_mention: str) -> str:
    return (
        f"Closing off **{set_name}**!\n"
        f"The leaderboard decides who plays for the championship, and the winner is crowned {champion_mention}"
    )


def _wave_headline(wave_index: int, set_code: str, post_url: str) -> str:
    top_n = INVITE_WAVE_TIERS[wave_index][1]
    championship = f"[**{set_code} Set Championship**]({post_url})"
    if wave_index == 0:
        return f"Inviting Top {top_n} Leaderboard Players to the {championship}!"
    return f"Extending the invitation to the {championship} to the Top {top_n} Players"
