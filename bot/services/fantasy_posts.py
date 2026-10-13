"""The #watch-party posts for a Pro Play event, shared by the fantasy tick and `!test proplay`"""
from __future__ import annotations

import discord
from discord.utils import format_dt

from bot import emojis
from bot.services.fantasy_event import FantasyEvent, melee_url, pro_play_url
from bot.services.fantasy_podium import FantasyWinner

MSG_PICKS_OPEN_TITLE = "Pro Play Fantasy picks are open for **{event}**"
MSG_PICKS_OPEN_PREMISE = "Put together a team of four Pro Players and score points every time they win a match!"
MSG_SELECTION_CLOSES = "Selection closes {when} ({relative})"
MSG_CLOSE_REMINDER_TITLE = "**{event}** Fantasy picks close {relative}"
MSG_PICK_TEAM = "[**Pick your Team**]({url})"
MSG_DAY_LIVE_TITLE = "**{event}** {day} is live"
MSG_DAY_LIVE_BODY = "Follow your team after each round"
MSG_OPEN_PRO_PLAY = "[**Open Pro Play**]({url})"
MSG_DAY_ONE_DONE_TITLE = "**{event}** Day 1 is complete"
MSG_DAY_ONE_DONE_BODY = "Put in your subs for anyone who missed Day 2"
MSG_CHECK_TEAM = "[**Check your Team**]({url})"
MSG_BRACKET_OPEN_TITLE = "**{event}** Top 8 Bracket is open"
MSG_BRACKET_OPEN_BODY = "Predict who wins each Top 8 match before it starts"
MSG_TOP8_BRACKET = "[**Top 8 Bracket**]({url})"
MSG_ROUND_DONE_TITLE = "**{event}** {round} results available on [**Melee**]({url})"
MSG_ROUND_DONE_COMMAND = "Moderator command: `/round {argument}`"
MSG_CEREMONY_TITLE = "### 🏆 **{event}** Fantasy Magic results"
MSG_CEREMONY_LINE = "{medal} {name} {points} points"
MSG_FINAL_LEADERBOARD = "[**See the final Leaderboard**]({url})"

MEDALS = ("🥇", "🥈", "🥉")


def picks_open_embed(event: FantasyEvent) -> discord.Embed:
    when, relative = format_dt(event.picks_lock_at, "f"), format_dt(event.picks_lock_at, "R")
    return _embed(event, [
        _heading(event, MSG_PICKS_OPEN_TITLE.format(event=event.short_name)),
        MSG_PICKS_OPEN_PREMISE,
        MSG_SELECTION_CLOSES.format(when=when, relative=relative),
        "",
        MSG_PICK_TEAM.format(url=pro_play_url(event)),
    ])


def close_reminder_embed(event: FantasyEvent) -> discord.Embed:
    relative = format_dt(event.picks_lock_at, "R")
    return _embed(event, [
        _heading(event, MSG_CLOSE_REMINDER_TITLE.format(event=event.short_name, relative=relative)),
        MSG_PICKS_OPEN_PREMISE,
        "",
        MSG_PICK_TEAM.format(url=pro_play_url(event)),
    ])


def day_live_embed(event: FantasyEvent, day: str) -> discord.Embed:
    return _embed(event, [
        _heading(event, MSG_DAY_LIVE_TITLE.format(event=event.short_name, day=day)),
        MSG_DAY_LIVE_BODY,
        "",
        MSG_OPEN_PRO_PLAY.format(url=pro_play_url(event)),
    ])


def day_one_complete_embed(event: FantasyEvent) -> discord.Embed:
    return _embed(event, [
        _heading(event, MSG_DAY_ONE_DONE_TITLE.format(event=event.short_name)),
        MSG_DAY_ONE_DONE_BODY,
        "",
        MSG_CHECK_TEAM.format(url=pro_play_url(event)),
    ])


def bracket_open_embed(event: FantasyEvent) -> discord.Embed:
    return _embed(event, [
        _heading(event, MSG_BRACKET_OPEN_TITLE.format(event=event.short_name)),
        MSG_BRACKET_OPEN_BODY,
        "",
        MSG_TOP8_BRACKET.format(url=pro_play_url(event, "top-8")),
    ])


def round_complete_embed(event: FantasyEvent, round_label: str, argument: str) -> discord.Embed:
    return _embed(event, [
        _heading(event, MSG_ROUND_DONE_TITLE.format(event=event.short_name, round=round_label, url=melee_url(event))),
        MSG_ROUND_DONE_COMMAND.format(argument=argument),
    ])


def ceremony_embed(event: FantasyEvent, winners: list[FantasyWinner], champion_role: str) -> discord.Embed:
    lines = [MSG_CEREMONY_TITLE.format(event=event.short_name)]
    for medal, winner in zip(MEDALS, winners):
        name = f"<@{winner.discord_id}>" if winner.discord_id else f"**{winner.name}**"
        line = MSG_CEREMONY_LINE.format(medal=medal, name=name, points=winner.points)
        lines.append(f"{line} {champion_role}" if winner.rank == 1 else line)
    lines.extend(["", MSG_FINAL_LEADERBOARD.format(url=pro_play_url(event, "leaderboard"))])
    return _embed(event, lines)


def _heading(event: FantasyEvent, title: str) -> str:
    symbol = emojis.set_symbol(event.set_code)
    return f"### {symbol} {title}" if symbol else f"### {title}"


def _embed(event: FantasyEvent, lines: list[str]) -> discord.Embed:
    embed = discord.Embed(description="\n".join(lines), color=discord.Color.green())
    if event.crest_url:
        embed.set_thumbnail(url=event.crest_url)
    return embed
