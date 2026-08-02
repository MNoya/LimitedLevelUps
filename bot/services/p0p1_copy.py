"""Copy for the `!p0p1` advertisement, worded from the contest's phase."""
from __future__ import annotations

from datetime import datetime

import discord
from discord import ui

from bot import emojis
from bot.config import settings
from bot.services.containers import as_view, build_container
from bot.services.mock_lobby_card import set_symbol_url
from bot.services.p0p1_contest import Contest, PHASE_LOCKED, PHASE_PRE, PHASE_VOTING
from bot.services.ping_roles import P0P1_COLOR, TOP_P0P1_CHALLENGER_ROLE_NAME

SAVED_PICKS = "Log in with Discord, your picks save automatically."
CHANGE_PICKS_EARLY_ACCESS = "Update anytime before the Early Access deadline"
SYNTHETIC_CHALLENGER_TAG = f"**@{TOP_P0P1_CHALLENGER_ROLE_NAME}**"
P0P1_ACCENT = discord.Color.from_str(P0P1_COLOR)
REMINDER_ADDRESS = "{role_mention} if you haven't made your P0P1 picks yet!"


def challenger_mention(role: discord.Role | None) -> str:
    """Mention pill for the top challengers, or plain text when the guild has no such role yet."""
    return role.mention if role is not None else SYNTHETIC_CHALLENGER_TAG


def contest_url(code: str, featured_code: str | None) -> str:
    """The site serves 404 for a contest still in previews, so only the featured one gets the bare URL."""
    if featured_code is not None and code.upper() == featured_code.upper():
        return f"{settings.public_site_url.rstrip('/')}/p0p1"
    return archive_url(code)


def archive_url(code: str) -> str:
    """A contest's own page, which keeps pointing at it once a newer contest takes over the bare URL."""
    return f"{settings.public_site_url.rstrip('/')}/p0p1/{code.upper()}"


def advertisement(
    contest: Contest, when: datetime, *, featured_code: str | None, challenger_mention: str,
) -> ui.Container:
    url = contest_url(contest.code, featured_code)
    phase = contest.phase(when)
    title = f"{contest.code} Pack 0 Pick 1 Challenge"
    deadline = _stamp(contest.voting_deadline, "R")
    llu = emojis.prefix("llu")

    if phase == PHASE_PRE:
        lines = [f"## {title} is coming soon!",
                 f"Opens when previews end {_stamp(contest.previews_open, 'R')}, "
                 f"{_stamp(contest.previews_open, 'F')}",
                 f"Voting closes when Early Access starts {deadline}, "
                 f"{_stamp(contest.voting_deadline, 'D')}"]
        if featured_code is not None and featured_code.upper() != contest.code.upper():
            featured = featured_code.upper()
            lines.append(f"\n{llu}{challenger_mention} "
                         f"[**{featured} final standings**]({archive_url(featured)})")
    elif phase == PHASE_VOTING:
        lines = [f"## [{title}]({url}) is now open!",
                 f"{SAVED_PICKS}\n{CHANGE_PICKS_EARLY_ACCESS} {deadline}",
                 f"### {llu}[**Pick your team**]({url})"]
    elif phase == PHASE_LOCKED:
        lines = [f"## [{title}]({url}) voting closed",
                 f"Results {_stamp(contest.scoring_date, 'R')}, {_stamp(contest.scoring_date, 'D')}",
                 f"### {llu}[**See the most popular picks**]({url})"]
    else:
        lines = [f"## [{title}]({url}) results are in!",
                 f"### {llu}[**See the final standings**]({url})",
                 f"Who are the new {challenger_mention}?"]

    return build_container("\n".join(lines), set_symbol_url(contest.code))


def reminder_view(contest: Contest, *, featured_code: str | None, role_mention: str, voter_count: int) -> ui.LayoutView:
    """The T-1 nudge as it is sent: the addressed line as a bare text block above the card, so the ping
    reads as an address to the reader instead of as part of the post."""
    address = REMINDER_ADDRESS.format(role_mention=role_mention)
    return as_view(ui.TextDisplay(address), reminder(contest, featured_code=featured_code,
                                                     voter_count=voter_count))


def reminder(contest: Contest, *, featured_code: str | None, voter_count: int) -> ui.Container:
    """The T-1 day nudge. Turnout rides as subtext, where it reads as encouragement instead of as a
    scoreboard the reader is missing from."""
    url = contest_url(contest.code, featured_code)
    lines = [f"## {contest.name} Pack 0 Pick 1 Challenge closes soon"]
    turnout = _turnout_line(voter_count)
    if turnout:
        lines.append(turnout)
    lines.append(f"Voting closes {_stamp(contest.voting_deadline, 'R')}, {_stamp(contest.voting_deadline, 'F')}")
    lines.append(f"### {emojis.prefix('llu')}[**Pick your team**]({url})")
    return build_container("\n".join(lines), set_symbol_url(contest.code), accent=P0P1_ACCENT)


def _turnout_line(voter_count: int) -> str:
    """Empty at zero, where naming the count would advertise that nobody has played."""
    if voter_count <= 0:
        return ""
    players = "player has" if voter_count == 1 else "players have"
    return f"-# {voter_count} {players} voted so far"


def _stamp(when: datetime, style: str) -> str:
    return f"<t:{int(when.timestamp())}:{style}>"
