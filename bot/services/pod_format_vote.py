"""The community format vote for a set's season, backed by `pod_format_votes`.

Approval voting: a player toggles a vote for every format they would draft. The tally drives the weekly
allocator. One public card is pinned in pod chat when voting opens and edited in place as votes land; the
`/pod-schedule` Vote Formats button opens a private copy of the same card. The card shows shared counts only,
so a player reads their own picks through the My Votes button. The latest set and the championship are never
on the ballot; the cubes are always on it, everything else enters by a vote or a write-in.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date

import discord
from discord import ui
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from bot.commands.authorization import organizer_authorized_interaction
from bot.database import SessionLocal
from bot.discord_helpers import RenderQueue, extract_avatar_hash, resolve_pod_chat_channel, run_detached
from bot.models import PodFormatVote, Player
from bot.services.pod_format import custom_formats, is_custom
from bot.services.pod_format_poll import (
    MAX_ROWED_OPTIONS,
    ROW_WIDTH,
    add_button_emoji,
    normalize_write_ins,
)
from bot.services.pod_format_interest import cube_emoji, flashback_emoji
from bot.commands.messages import MSG_ORGANIZER_ONLY_SETTINGS
from bot.services.ping_roles import organizer_mention
from bot.services.pod_roles import role_mention
from bot.services.pod_schedule import POD_DRAFTERS_ROLE_NAME
from bot.services.self_reported_events import get_or_create_player
from bot import emojis
from bot.sets import active_set_code, flashback_picker_sets, released_sets, seed_for_code, set_name_for

log = logging.getLogger(__name__)

MSG_VOTE_OPEN = "{role} Vote for any formats you'd be interested in playing this season!"
MSG_VOTE_HEADING = "## 🗳️ Flashback Format Vote - {name} Edition"
MSG_VOTE_INTRO = "Select or add any formats you would be interested in playing this season"
MSG_VOTERS_HEADING = "## 📊 Format Votes"
MSG_YOUR_VOTES = "Your Votes: {codes}"
MSG_YOUR_VOTES_NONE = "Your Votes: none yet"
MSG_FORMATS_ADDED = "Added {codes} to the ballot"
MSG_FORMATS_ALREADY = "Those formats are already on the ballot"
ADD_BUTTON_LABEL = "Add Format"
VOTERS_LABEL = "Voters"
VOTERS_SHOWN = 20
ADD_MODAL_TITLE = "Add Format(s)"
ADD_MODAL_FIELD = "Set Codes"
ADD_MODAL_PLACEHOLDER = "e.g. DSK FIN MH3"
CARD_MARKER = "Flashback Format Vote"
BAR_WIDTH = 10
BALLOT_LABEL_MAX = 24
NBSP_FIELD = "​"

MSG_NO_REMOVABLE = "No written-in options to remove"
MSG_MANAGE_PROMPT = "Remove a written-in format from the ballot"
MSG_OPTION_REMOVED = "Removed {code} from the ballot"

VOTE_OPTION_ID = "podfmtvote"
ADD_FORMAT_ID = "podfmtaddfmt"
VOTERS_ID = "podfmtvoters"
MANAGE_ID = "podfmtmanage"
VOTE_OPEN_ID = "podfmtopen"
VOTE_OPEN_LABEL = "Vote Formats"

_card_queue = RenderQueue(delay_s=1.0)


def season_code(when=None) -> str:
    return active_set_code(when)


def seed_formats() -> list[str]:
    """The formats always on the ballot: the curated flashback sets, so a season opens with the community's
    candidates to click. The cubes are fixed on the schedule and are not up for a vote."""
    return [seed.code for seed in flashback_picker_sets()]


def toggle_vote(session: Session, voter: discord.abc.User, season: str, code: str) -> bool:
    """Toggle this voter's vote for `code`. Returns True when the vote is now on, False when retracted."""
    player = _voter_player(session, voter)
    existing = session.execute(
        select(PodFormatVote).where(
            PodFormatVote.player_id == player.id,
            PodFormatVote.season_set_code == season,
            PodFormatVote.format_code == code,
        )
    ).scalar_one_or_none()
    if existing is not None:
        session.delete(existing)
        session.flush()
        return False
    session.add(PodFormatVote(player_id=player.id, season_set_code=season, format_code=code))
    session.flush()
    return True


def add_votes(session: Session, voter: discord.abc.User, season: str, raw: str) -> list[str]:
    """Vote for every plausible code in a write-in, adding each to the ballot. Already-voted codes stay on."""
    added: list[str] = []
    player = _voter_player(session, voter)
    for code in normalize_write_ins(raw):
        exists = session.execute(
            select(PodFormatVote.id).where(
                PodFormatVote.player_id == player.id,
                PodFormatVote.season_set_code == season,
                PodFormatVote.format_code == code,
            )
        ).scalar_one_or_none()
        if exists is None:
            session.add(PodFormatVote(player_id=player.id, season_set_code=season, format_code=code))
            added.append(code)
    session.flush()
    return added


def tally(session: Session, season: str) -> dict[str, int]:
    rows = session.execute(
        select(PodFormatVote.format_code, func.count())
        .where(PodFormatVote.season_set_code == season)
        .group_by(PodFormatVote.format_code)
    ).all()
    return {code: count for code, count in rows}


def delete_format_votes(session: Session, season: str, code: str) -> int:
    """Purge every vote for one format this season, so an organizer can clear a bad write-in off the ballot"""
    result = session.execute(
        delete(PodFormatVote).where(
            PodFormatVote.season_set_code == season, PodFormatVote.format_code == code,
        )
    )
    return result.rowcount


def removable_options(session: Session, season: str) -> list[str]:
    """The written-in formats an organizer may drop: voted codes off the curated seed, newest release first"""
    seeded = set(seed_formats())
    written = [code for code in tally(session, season) if code not in seeded]
    written.sort(key=_release_sort_key, reverse=True)
    return written


def _removable_options(season: str) -> list[str]:
    with SessionLocal() as session:
        return removable_options(session, season)


def _delete_option_commit(season: str, code: str) -> None:
    with SessionLocal() as session:
        delete_format_votes(session, season, code)
        session.commit()


def player_votes(session: Session, discord_id: str, season: str) -> set[str]:
    player = session.execute(select(Player).where(Player.discord_id == discord_id)).scalar_one_or_none()
    if player is None:
        return set()
    return set(session.execute(
        select(PodFormatVote.format_code).where(
            PodFormatVote.player_id == player.id, PodFormatVote.season_set_code == season,
        )
    ).scalars().all())


def voters_by_format(session: Session, season: str) -> dict[str, list[str]]:
    rows = session.execute(
        select(PodFormatVote.format_code, Player.display_name)
        .join(Player, Player.id == PodFormatVote.player_id)
        .where(PodFormatVote.season_set_code == season)
    ).all()
    result: dict[str, list[str]] = {}
    for code, name in rows:
        result.setdefault(code, []).append(name)
    return result


def ballot_order(counts: dict[str, int]) -> list[str]:
    """The formats on the ballot: the seeded flashback sets plus every written-in format, newest release first.
    The order is fixed on release date, not votes, so a button never moves under a clicker as the tally shifts.
    Only when the list overruns the button grid does the tally matter: an option with votes is always kept and
    the unvoted ones are dropped oldest first, so no format a player picked is ever hidden."""
    codes = list(seed_formats())
    for code in counts:
        if code not in codes:
            codes.append(code)
    codes.sort(key=_release_sort_key, reverse=True)
    if len(codes) <= MAX_ROWED_OPTIONS:
        return codes
    voted = [code for code in codes if counts.get(code, 0) > 0]
    unvoted = [code for code in codes if counts.get(code, 0) == 0]
    kept = (voted + unvoted)[:MAX_ROWED_OPTIONS]
    kept.sort(key=_release_sort_key, reverse=True)
    return kept


def _release_sort_key(code: str) -> date:
    seed = seed_for_code(code)
    return seed.start_date if seed is not None else date.min


# --- the card, shared by the pinned public message and the ephemeral copy ---


def panel(season: str) -> tuple[discord.Embed, ui.View]:
    """The public card: shared counts, buttons neutral because a pinned message has no one player."""
    with SessionLocal() as session:
        counts = tally(session, season)
    codes = ballot_order(counts)
    return _vote_embed(season, codes, counts), build_vote_view(codes)


def voter_panel(season: str, voter: discord.abc.User) -> tuple[discord.Embed, ui.View]:
    """A private copy: the same counts, but this voter's picks show green since the copy is theirs alone."""
    with SessionLocal() as session:
        counts = tally(session, season)
        voted = player_votes(session, str(voter.id), season)
    codes = ballot_order(counts)
    return _vote_embed(season, codes, counts), build_vote_view(codes, voted)


def render_panel(season: str, codes: list[str], counts: dict[str, int]) -> tuple[discord.Embed, ui.View]:
    """The embed and view for given data, without a DB read — for previews."""
    return _vote_embed(season, codes, counts), build_vote_view(codes)


def preview_codes(count: int) -> list[str]:
    """A `count`-long list of real codes for a density preview, minus the latest set, the bare cube row and a
    couple of long-named unpopular sets."""
    skip = {active_set_code(), "CUBE", "TMT", "SPM"}
    codes = list(seed_formats())
    for seed in released_sets():
        if seed.code not in skip and seed.code not in codes:
            codes.append(seed.code)
    return codes[:count]


def build_vote_view(codes: list[str], voted: set[str] | None = None) -> ui.View:
    voted = voted or set()
    view = ui.View(timeout=None)
    view.add_item(AddFormatItem())
    view.add_item(VotersItem())
    view.add_item(ManageVotesItem())
    for index, code in enumerate(codes):
        view.add_item(VoteOptionItem(code, voted=code in voted, row=min(1 + index // ROW_WIDTH, 4)))
    return view


def _vote_embed(season: str, codes: list[str], counts: dict[str, int]) -> discord.Embed:
    heading = MSG_VOTE_HEADING.format(name=set_name_for(season))
    embed = discord.Embed(color=discord.Color.green(), description=f"{heading}\n\n{MSG_VOTE_INTRO}")
    top = max(counts.values(), default=0)
    for code in codes:
        embed.add_field(name=f"{_emoji_prefix(code)}{_option_label(code)}",
                        value=_vote_bar(counts.get(code, 0), top), inline=True)
    for _ in range((-len(codes)) % 3):
        embed.add_field(name=NBSP_FIELD, value=NBSP_FIELD, inline=True)
    return embed


def _voters_panel(season: str, discord_id: str) -> discord.Embed:
    with SessionLocal() as session:
        voters = voters_by_format(session, season)
        mine = player_votes(session, discord_id, season)
    return _voters_embed(season, voters, mine)


def _voters_embed(season: str, voters: dict[str, list[str]], mine: set[str]) -> discord.Embed:
    your_votes = MSG_YOUR_VOTES.format(codes=", ".join(sorted(mine))) if mine else MSG_YOUR_VOTES_NONE
    embed = discord.Embed(color=discord.Color.green(), description=f"{MSG_VOTERS_HEADING}\n\n{your_votes}")
    counts = {code: len(names) for code, names in voters.items()}
    for code in ballot_order(counts):
        names = voters.get(code, [])
        if not names:
            continue
        value = ", ".join(names[:VOTERS_SHOWN])
        if len(names) > VOTERS_SHOWN:
            value += f" +{len(names) - VOTERS_SHOWN} more"
        embed.add_field(name=f"{_emoji_prefix(code)}{_option_label(code)} ({len(names)})", value=value, inline=False)
    return embed


def _vote_bar(count: int, top: int) -> str:
    """A bar filled to the leading format's count, so the top choice fills it and the rest read against it"""
    filled = round(BAR_WIDTH * count / top) if top > 0 else 0
    bar = "█" * filled + " " * (BAR_WIDTH - filled)
    return f"`{bar}` {count}"


def _option_label(code: str) -> str:
    cube = _custom_label(code)
    if cube is not None:
        return cube
    name = _short_name(code)
    if not name or len(name) > BALLOT_LABEL_MAX:
        return code
    return name


def _custom_label(code: str) -> str | None:
    """A cube's own name (Peasant Cube, Middle-Earth Masters), or None for a real set."""
    for fmt in custom_formats():
        if fmt.code == code:
            return fmt.label
    return None


def _short_name(code: str) -> str:
    """The set name trimmed to fit a three-column card: the colon subtitle and a leading The dropped"""
    name = set_name_for(code)
    if not name:
        return code
    return name.split(":")[0].strip().removeprefix("The ")


def _emoji_prefix(code: str) -> str:
    symbol = emojis.set_symbol(code)
    if symbol is not None:
        return f"{symbol} "
    return f"{cube_emoji() if is_custom(code) else flashback_emoji()} "


def _button_face(code: str) -> "discord.Emoji | str":
    """A vote button's glyph, icon only: its set or cube symbol, the cube glyph for a cube without one, the
    flashback glyph otherwise. The embed field beside it carries the name, so the button needs no label."""
    symbol = emojis.set_symbol(code)
    if symbol is not None:
        return symbol
    return cube_emoji() if is_custom(code) else flashback_emoji()


# --- posting and keeping the public card fresh ---


def vote_ping_text(guild: discord.Guild) -> str:
    """The opening ping that heads the public vote card, shared by `/openvote` and the `!test` preview"""
    return MSG_VOTE_OPEN.format(role=role_mention(guild, POD_DRAFTERS_ROLE_NAME))


async def post_vote_card(channel: discord.abc.Messageable, content: str, *, force: bool = False) -> None:
    """Post the season's public vote card and pin it, pinging with `content`. A card already up for this
    season is left alone unless `force`, so a same-day repost does not re-ping."""
    season = season_code()
    existing = await _existing_card(channel)
    if existing is not None and not force and _is_current_card(existing, season):
        return
    if existing is not None:
        await _delete_quietly(existing)
    embed, view = await asyncio.to_thread(panel, season)
    try:
        message = await channel.send(
            content=content, embed=embed, view=view, allowed_mentions=discord.AllowedMentions(roles=True),
        )
    except discord.HTTPException:
        log.warning("format vote: could not post the vote card", exc_info=True)
        return
    try:
        await message.pin()
    except discord.HTTPException:
        log.warning("format vote: could not pin the vote card", exc_info=True)


async def refresh_vote_card(channel: discord.abc.Messageable) -> None:
    existing = await _existing_card(channel)
    if existing is None:
        return
    embed, view = await asyncio.to_thread(panel, season_code())
    try:
        await existing.edit(embed=embed, view=view)
    except discord.HTTPException:
        log.warning("format vote: could not edit the vote card", exc_info=True)


def request_public_repaint(client: discord.Client) -> None:
    async def render() -> None:
        channel = resolve_pod_chat_channel(client)
        if channel is not None:
            await refresh_vote_card(channel)

    _card_queue.request("format-vote-card", render)


async def send_vote_panel(interaction: discord.Interaction) -> None:
    embed, view = await asyncio.to_thread(voter_panel, season_code(), interaction.user)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def _existing_card(channel: discord.abc.Messageable) -> discord.Message | None:
    if not isinstance(channel, discord.TextChannel):
        return None
    try:
        async for message in channel.pins():
            if message.author.bot and message.embeds and CARD_MARKER in (message.embeds[0].description or ""):
                return message
    except discord.HTTPException:
        log.warning("format vote: could not read pins", exc_info=True)
    return None


def _is_current_card(message: discord.Message, season: str) -> bool:
    """Whether an existing card is this season's, read off the set name in its heading, so an old season's
    card is replaced while the current one is left alone. No hidden footer marker needed."""
    if not message.embeds:
        return False
    return set_name_for(season) in (message.embeds[0].description or "")


async def _delete_quietly(message: discord.Message) -> None:
    try:
        await message.delete()
    except discord.HTTPException:
        log.warning("format vote: could not remove the old vote card", exc_info=True)


# --- the buttons, persistent so a pinned card keeps working after a restart ---


def _is_ephemeral(message: discord.Message | None) -> bool:
    return message is not None and message.flags.ephemeral


def _toggle_vote_commit(voter: discord.abc.User, season: str, code: str) -> None:
    with SessionLocal() as session:
        toggle_vote(session, voter, season, code)
        session.commit()


def _add_votes_commit(voter: discord.abc.User, season: str, raw: str) -> list[str]:
    with SessionLocal() as session:
        added = add_votes(session, voter, season, raw)
        session.commit()
        return added


async def _apply_toggle(interaction: discord.Interaction, code: str, ephemeral: bool) -> None:
    """The write behind a vote click, off the interaction that already answered and off the event loop, so a
    crowd clicking at once never blocks the loop past the interaction ack window. The public card repaints
    through the queue so a burst collapses to one edit; a private copy edits itself."""
    season = season_code()
    await asyncio.to_thread(_toggle_vote_commit, interaction.user, season, code)
    request_public_repaint(interaction.client)
    if ephemeral:
        embed, view = await asyncio.to_thread(voter_panel, season, interaction.user)
        await interaction.edit_original_response(embed=embed, view=view)


async def _apply_add(interaction: discord.Interaction, raw: str) -> None:
    added = await asyncio.to_thread(_add_votes_commit, interaction.user, season_code(), raw)
    request_public_repaint(interaction.client)
    message = MSG_FORMATS_ADDED.format(codes=", ".join(added)) if added else MSG_FORMATS_ALREADY
    await interaction.followup.send(message, ephemeral=True)


class VoteOptionItem(ui.DynamicItem[ui.Button], template=rf"{VOTE_OPTION_ID}:(?P<code>.+)"):
    def __init__(self, code: str, voted: bool = False, row: int | None = None) -> None:
        super().__init__(ui.Button(
            style=discord.ButtonStyle.success if voted else discord.ButtonStyle.secondary,
            emoji=_button_face(code), custom_id=f"{VOTE_OPTION_ID}:{code}", row=row,
        ))
        self.code = code

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: ui.Button, match: re.Match):
        return cls(match["code"])

    async def callback(self, interaction: discord.Interaction) -> None:
        ephemeral = _is_ephemeral(interaction.message)
        await interaction.response.defer()
        run_detached(_apply_toggle(interaction, self.code, ephemeral), label="format-vote-toggle")


class VotersItem(ui.DynamicItem[ui.Button], template=VOTERS_ID):
    def __init__(self) -> None:
        super().__init__(ui.Button(
            style=discord.ButtonStyle.secondary, label=VOTERS_LABEL, emoji="📊", custom_id=VOTERS_ID, row=0,
        ))

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: ui.Button, match: re.Match):
        return cls()

    async def callback(self, interaction: discord.Interaction) -> None:
        season = season_code()
        embed = await asyncio.to_thread(_voters_panel, season, str(interaction.user.id))
        await interaction.response.send_message(embed=embed, ephemeral=True)


class AddFormatItem(ui.DynamicItem[ui.Button], template=ADD_FORMAT_ID):
    def __init__(self) -> None:
        super().__init__(ui.Button(
            style=discord.ButtonStyle.secondary, label=ADD_BUTTON_LABEL, emoji=add_button_emoji(),
            custom_id=ADD_FORMAT_ID, row=0,
        ))

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: ui.Button, match: re.Match):
        return cls()

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(AddFormatModal())


class AddFormatModal(ui.Modal, title=ADD_MODAL_TITLE):
    code = ui.TextInput(label=ADD_MODAL_FIELD, placeholder=ADD_MODAL_PLACEHOLDER, min_length=2, max_length=100)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        run_detached(_apply_add(interaction, str(self.code.value)), label="format-vote-add")


class VoteFormatsButton(ui.DynamicItem[ui.Button], template=VOTE_OPEN_ID):
    def __init__(self, row: int | None = None) -> None:
        super().__init__(ui.Button(
            style=discord.ButtonStyle.primary, label=VOTE_OPEN_LABEL, emoji="🗳️", custom_id=VOTE_OPEN_ID, row=row,
        ))

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: ui.Button, match: re.Match):
        return cls()

    async def callback(self, interaction: discord.Interaction) -> None:
        await send_vote_panel(interaction)


class ManageVotesItem(ui.DynamicItem[ui.Button], template=MANAGE_ID):
    def __init__(self) -> None:
        super().__init__(ui.Button(
            style=discord.ButtonStyle.secondary, emoji="⚙️", custom_id=MANAGE_ID, row=0,
        ))

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: ui.Button, match: re.Match):
        return cls()

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await organizer_authorized_interaction(interaction):
            await interaction.response.send_message(
                MSG_ORGANIZER_ONLY_SETTINGS.format(organizer=organizer_mention(interaction.guild)), ephemeral=True,
            )
            return
        codes = await asyncio.to_thread(_removable_options, season_code())
        if not codes:
            await interaction.response.send_message(MSG_NO_REMOVABLE, ephemeral=True)
            return
        await interaction.response.send_message(MSG_MANAGE_PROMPT, view=DeleteOptionView(codes), ephemeral=True)


class DeleteOptionView(ui.View):
    def __init__(self, codes: list[str]) -> None:
        super().__init__(timeout=120)
        self.add_item(DeleteOptionSelect(codes))


class DeleteOptionSelect(ui.Select):
    def __init__(self, codes: list[str]) -> None:
        options = [
            discord.SelectOption(label=_option_label(code), value=code, emoji=emojis.set_symbol(code))
            for code in codes
        ]
        super().__init__(placeholder=MSG_MANAGE_PROMPT, options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        code = self.values[0]
        await asyncio.to_thread(_delete_option_commit, season_code(), code)
        request_public_repaint(interaction.client)
        await interaction.response.edit_message(content=MSG_OPTION_REMOVED.format(code=code), view=None)


def _voter_player(session: Session, voter: discord.abc.User) -> Player:
    return get_or_create_player(
        session, discord_id=str(voter.id), discord_username=voter.name,
        display_name=getattr(voter, "display_name", voter.name), avatar_hash=extract_avatar_hash(voter),
    )
