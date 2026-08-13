"""Discord-specific helpers shared across signup, linking, and refresh.

Keeping these in one place so the avatar capture logic doesn't drift between
the three entry points that touch it.
"""
from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Iterable

import discord

from bot.config import settings


if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from discord.ext import commands

    from bot.models import Player

logger = logging.getLogger(__name__)

NBSP = "\u00a0"  # Discord collapses runs of regular spaces; non-breaking spaces survive
ZWSP = "\u200b"  # anchors a -# subtext line so Discord keeps the NBSP indent that follows
BLANK_LINE = f"{NBSP}{ZWSP}"  # a line Discord won't collapse, for spacing before a trailing button
EM_SPACE = " "  # wide gap between items sharing one line, where a run of spaces would collapse


_detached: set["asyncio.Task"] = set()


class RenderQueue:
    """Collapse a burst of re-render requests for one key into a single pass.

    A pod's surfaces are shared by everyone answering at once, and one render per press outruns what
    Discord lets the bot edit a message: the queue that builds up puts the card players are watching
    seconds behind the state it is meant to show, which they read as their press not registering.

    The render is re-read from the database when it runs, so a coalesced burst renders once off the
    settled roster rather than replaying whichever press happened to be last."""

    def __init__(self, delay_s: float) -> None:
        self.delay_s = delay_s
        self._pending: set[str] = set()
        self._tasks: dict[str, asyncio.Task] = {}

    def request(self, key: str, render: "Callable[[], Coroutine]") -> None:
        self._pending.add(key)
        running = self._tasks.get(key)
        if running is not None and not running.done():
            return
        self._tasks[key] = asyncio.create_task(self._drain(key, render))

    async def _drain(self, key: str, render: "Callable[[], Coroutine]") -> None:
        try:
            while key in self._pending:
                await asyncio.sleep(self.delay_s)
                if key not in self._pending:
                    break
                self._pending.discard(key)
                try:
                    await render()
                except Exception:  # noqa: BLE001 - a queued render must never die silently
                    logger.warning(f"could not render {key}", exc_info=True)
        finally:
            self._tasks.pop(key, None)


def run_detached(coro: "Coroutine", label: str) -> "asyncio.Task":
    """Run follow-on work off the interaction that started it, for a click already answered. A failure
    has no one left to tell and is logged. The task is held until it finishes: the event loop keeps only
    a weak reference and would otherwise collect it mid-flight. Returned for a caller that has to know
    when the work landed; a caller that does not can drop it."""
    async def runner() -> None:
        try:
            await coro
        except Exception:  # noqa: BLE001 - a detached task must never die silently
            logger.warning(f"could not finish {label}", exc_info=True)

    task = asyncio.create_task(runner())
    _detached.add(task)
    task.add_done_callback(_detached.discard)
    return task


def command_line(cmd: str, blurb: str) -> str:
    """One `/command` + description line, shared by /help and the lobby embed."""
    return f"`{cmd}` - {blurb}"


def posts_publicly(interaction: "discord.Interaction") -> bool:
    """A moderator (Manage Messages) posts to the channel for everyone; everyone else gets an ephemeral
    copy. Permission rather than a role name so it holds across guilds. In a DM there is no one to shield
    it from, so the reply is never ephemeral."""
    if interaction.guild is None:
        return True
    permissions = getattr(interaction.user, "guild_permissions", None)
    return bool(permissions and permissions.manage_messages)


def in_pod_coordination(channel: "discord.interactions.InteractionChannel | None") -> bool:
    if channel is None:
        return False
    if channel.id == settings.pod_draft_channel_id:
        return True
    return getattr(channel, "parent_id", None) == settings.pod_draft_channel_id


def is_pod_coordination_channel(channel: "discord.interactions.InteractionChannel | None") -> bool:
    """The coordination channel itself, excluding its threads."""
    return channel is not None and channel.id == settings.pod_draft_channel_id


async def send_welcome(
    client: "commands.Bot", member: "discord.abc.User", view: "discord.ui.LayoutView",
) -> bool:
    """Post the welcome publicly in pod-draft-chat so the community sees a new drafter, pinging the
    newcomer — a Components V2 text block notifies where an embed mention would not, and role pills
    stay silent. False when the channel can't be resolved or the send fails."""
    channel = resolve_pod_chat_channel(client)
    if channel is None:
        return False
    mentions = discord.AllowedMentions(users=[member], roles=False, everyone=False)
    try:
        await channel.send(view=view, allowed_mentions=mentions)
        return True
    except discord.HTTPException:
        logger.warning("could not post welcome in pod-draft-chat", exc_info=True)
        return False


async def post_welcome(interaction: "discord.Interaction", view: "discord.ui.LayoutView") -> None:
    """The interaction-path welcome: public in pod-draft-chat, falling back to an ephemeral reply when
    the channel can't be resolved."""
    if not await send_welcome(interaction.client, interaction.user, view):
        await interaction.followup.send(view=view, ephemeral=True)


def in_pod_chat(channel: "discord.interactions.InteractionChannel | None") -> bool:
    name = getattr(channel, "name", "") or ""
    return settings.pod_draft_chat_channel_name.lower() in name.lower()


def channel_matching_name(guild: "discord.Guild", name_fragment: str) -> "discord.abc.GuildChannel | None":
    """First text channel in guild whose name contains name_fragment, case-insensitively."""
    fragment = name_fragment.lower()
    for channel in guild.text_channels:
        if fragment in channel.name.lower():
            return channel
    return None


def resolve_pod_chat_channel(bot: "commands.Bot") -> "discord.abc.Messageable | None":
    """The pod-draft-chat channel, falling back to the coordination channel when it isn't present.

    Resolved by name so a mod can create the channel without a config change. The underfill nudges
    and the weekly schedule post land here, keeping the coordination channel to signups and event
    threads only.
    """
    guild_id = settings.discord_guild_id
    guild = bot.get_guild(guild_id) if guild_id else None
    if guild is not None:
        chat = channel_matching_name(guild, settings.pod_draft_chat_channel_name)
        if chat is not None:
            return chat
    return bot.get_channel(settings.pod_draft_channel_id)

def extract_avatar_hash(user: "discord.abc.User | discord.User | discord.Member | None") -> str | None:
    """Return the Discord avatar hash for a user, or None if they use the default avatar.

    `user.avatar` is an `Optional[Asset]`; the asset's `.key` is the hash that
    composes into the CDN URL. We persist the hash, not the URL, so changes to
    the CDN host (e.g. a Discord-side migration) don't require a backfill.
    """
    if user is None:
        return None
    avatar = getattr(user, "avatar", None)
    if avatar is None:
        return None
    return getattr(avatar, "key", None)


async def refresh_player_profiles(
    bot: "commands.Bot",
    session: "Session",
    players: "Iterable[Player]",
) -> dict:
    """Reconcile each linked player's avatar, display name, and username, gateway cache first.

    The reactive listeners in profile_sync_listener keep these fresh in real time; this sweep is
    the weekly backstop for changes made while the bot was offline. It prefers `get_user` so a
    full pass costs almost no REST calls. Players without a `discord_id` are skipped; players we
    can't resolve (banned, or an id Discord no longer knows) keep their last-known values, and so does a
    deleted account, which does resolve but only under a placeholder name.
    """
    summary = {"checked": 0, "updated": 0, "skipped": 0, "errors": 0}
    for player in players:
        if not player.discord_id:
            summary["skipped"] += 1
            continue
        summary["checked"] += 1
        try:
            user = bot.get_user(int(player.discord_id)) or await bot.fetch_user(int(player.discord_id))
        except Exception:  # noqa: BLE001 - Discord can throw a wide variety
            logger.warning(f"profile refresh: could not fetch user {player.discord_id}", exc_info=True)
            summary["errors"] += 1
            continue
        if is_deleted_account_name(str(user)):
            summary["skipped"] += 1
            continue
        changed = False
        new_hash = extract_avatar_hash(user)
        if player.avatar_hash != new_hash:
            player.avatar_hash = new_hash
            changed = True
        new_display_name = await resolve_display_name(bot, user)
        if player.display_name != new_display_name:
            player.display_name = new_display_name
            changed = True
        new_username = str(user)
        if player.discord_username != new_username:
            player.discord_username = new_username
            changed = True
        if changed:
            summary["updated"] += 1
    session.commit()
    return summary


def display_width(s: str) -> int:
    """Monospace column width, counting wide CJK glyphs as 2 cells where len() counts 1."""
    return sum(2 if unicodedata.east_asian_width(ch) == "W" else 1 for ch in s)


def plural(count: int) -> str:
    return "" if count == 1 else "s"


ORDINAL_SUFFIXES = {1: "st", 2: "nd", 3: "rd"}


def ordinal(number: int) -> str:
    if 11 <= number % 100 <= 13:
        return f"{number}th"
    return f"{number}{ORDINAL_SUFFIXES.get(number % 10, 'th')}"


def quote_block(lines: list[str], *, trailing: str = "") -> str:
    """`> `-prefix each line so Discord renders the blockquote vertical bar; a ZWSP when empty."""
    if not lines:
        return ZWSP
    return "\n".join(f"> {line}" for line in lines) + trailing


def add_two_column_field(
    embed: "discord.Embed", label: str, left_lines: list[str], right_lines: list[str],
    *, trailing: str = "", spacer: bool = False,
) -> None:
    """A labelled two-column embed row: blockquoted `left_lines` beside `right_lines`, aligned
    line-for-line. `spacer` adds an empty third inline field so the following group starts on a fresh
    row. Shared by the lobby player list and the team-draft rosters so both render identically."""
    embed.add_field(name=label, value=quote_block(left_lines, trailing=trailing), inline=True)
    right = "\n".join(right_lines)
    embed.add_field(name=ZWSP, value=(right or ZWSP) + trailing, inline=True)
    if spacer:
        embed.add_field(name=ZWSP, value=ZWSP, inline=True)


def player_url(slug: str, set_code: str | None = None) -> str:
    """Public site URL for a player's page, set-scoped when set_code is given."""
    base = settings.player_base_url
    return f"{base}/{slug}/{set_code}" if set_code else f"{base}/{slug}"


def player_deck_url(slug: str, set_code: str, source_message_id: str) -> str:
    """Set-scoped player URL that opens a specific saved deck in the profile popup."""
    return f"{player_url(slug, set_code)}?deck={source_message_id}"


async def fetch_dm_user(bot: "commands.Bot", discord_id: str | None) -> "discord.User | None":
    """The Discord user behind a stored `players.discord_id`, or None when it can't be one: fictional
    test rosters carry placeholder ids like `testlobby-cara`, and `int()` on those raises out of
    whatever round-advance step was sending the DM."""
    if not discord_id or not str(discord_id).isdigit():
        return None
    user_id = int(discord_id)
    return bot.get_user(user_id) or await bot.fetch_user(user_id)


PIN_NOTICE_SCAN = 5


async def pin_quietly(message: "discord.Message", *, reason: str | None = None) -> None:
    """Pin, then take down the "pinned a message" line Discord posts for it.

    That notice is a real message in the channel, so in a pod thread it lands between two surfaces people
    are reading and pushes them apart for nothing. Only the notice pointing at this message is removed, and
    a Discord that sent no reference with it keeps its line rather than risking somebody else's."""
    await message.pin(reason=reason)
    try:
        async for recent in message.channel.history(limit=PIN_NOTICE_SCAN):
            if recent.type is not discord.MessageType.pins_add:
                continue
            if recent.reference is not None and recent.reference.message_id == message.id:
                await recent.delete()
                return
    except discord.HTTPException:
        logger.warning(f"could not clear the pin notice for message {message.id}", exc_info=True)


DELETED_ACCOUNT_RE = re.compile(r"^deleted_user_[0-9a-f]+$", re.IGNORECASE)


def is_deleted_account_name(value: object) -> bool:
    """Whether Discord handed back the placeholder it gives an account that no longer exists.

    A deleted account keeps resolving through the API as `deleted_user_<hash>` with no avatar, so a sync
    that trusts the response replaces a real name with the placeholder and every board carrying that
    player's results shows it from then on. Their own results stay valid, so the name is kept instead."""
    return isinstance(value, str) and bool(DELETED_ACCOUNT_RE.match(value))


async def resolve_display_name(bot: "commands.Bot", user: "discord.User") -> str:
    """Prefer the LLU guild nickname, falling back to the user's global display name.

    `bot.fetch_user` only knows the global account, so `User.display_name` is the
    global name. The server-specific nickname lives on the guild `Member`, which we
    resolve from the configured guild and fall back off of when the player has left.
    """
    guild_id = settings.discord_guild_id
    if guild_id:
        guild = bot.get_guild(guild_id)
        if guild is not None:
            member = guild.get_member(user.id)
            if member is None:
                try:
                    member = await guild.fetch_member(user.id)
                except Exception:  # noqa: BLE001 - not in guild, or Discord hiccup
                    member = None
            if member is not None:
                return member.display_name
    return user.display_name


_MESSAGE_LINK_RE = re.compile(
    r"https?://(?:ptb\.|canary\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)"
)


def parse_message_link(url: str) -> tuple[int, int, int] | None:
    """(guild_id, channel_id, message_id) from a Discord message jump URL, or None."""
    if not url:
        return None
    m = _MESSAGE_LINK_RE.search(url.strip())
    if m is None:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def first_image_url(message: "discord.Message", include_embeds: bool = False) -> str | None:
    for attachment in message.attachments:
        if (attachment.content_type or "").lower().startswith("image/"):
            return attachment.url
    if include_embeds:
        for embed in message.embeds:
            if embed.image.url:
                return embed.image.url
            if embed.thumbnail.url:
                return embed.thumbnail.url
    return None


CUSTOM_EMOJI_RE = re.compile(r"<(a?):([A-Za-z0-9_]+):(\d+)>")


def message_caption(message: "discord.Message") -> str | None:
    """The text a player wrote under a screenshot, stored as-is and rendered as plain text on the
    site, so a custom emoji keeps only its ``:name:`` instead of the raw Discord snowflake form."""
    text = CUSTOM_EMOJI_RE.sub(r":\2:", message.clean_content or "").strip()
    return text or None


def message_text(message: "discord.Message") -> str:
    """Flatten everything a bot message might carry its text in. A schedule pin is a Components V2
    message (title in a TextDisplay), an announcement is an embed (text in the description), and plain
    posts use ``content`` — so pin-matching and announcement dedup both read from one place."""
    parts = [message.content] if message.content else []
    for embed in message.embeds:
        if embed.title:
            parts.append(embed.title)
        if embed.description:
            parts.append(embed.description)
    parts.append(_component_text(message.components))
    return "\n".join(part for part in parts if part)


def _component_text(components) -> str:
    parts = []
    for component in components:
        content = getattr(component, "content", None)
        if isinstance(content, str):
            parts.append(content)
        children = getattr(component, "children", None)
        if children:
            parts.append(_component_text(children))
    return "\n".join(parts)
