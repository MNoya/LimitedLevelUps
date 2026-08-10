"""/trophy — log a draft result posted in trophy-hype to your profile.

Showcase only, never scored. Trophies and non-trophy decks both log; a trophy flag is guessed
from the record and the player can flip it, and only trophies rank the MTGO flashback board.
Record, colors, and set are read from the post caption; the set defaults to the active one but a
named code or set name (e.g. MH1, "Urza's Saga", MTGO-only flashbacks) overrides it. The player
picks the platform and fills anything that didn't parse. Bare `/trophy` grabs your most recent
image post in the current channel; `/trophy link:<url>` logs one from anywhere. Idempotent per
post via the upsert in services.self_reported_events.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime

import discord
from discord import app_commands, ui
from discord.ext import commands

from bot import audit, emojis
from bot.commands import descriptions as desc
from bot.database import SessionLocal
from bot.discord_helpers import (
    extract_avatar_hash,
    first_image_url,
    message_caption,
    parse_message_link,
    player_deck_url,
    resolve_display_name,
)
from bot.services import bot_log
from bot.services.pod_backfill import COLORS_RE, RECORD_RE, normalize_colors, strip_cdn_dims
from bot.services.pod_deck_color import GUILDS, PAIR_EMOJI_NAME, color_label, format_deck_color_emojis
from bot.services.pod_drafts import parse_caption_record
from bot.services.pod_thread_backfill import parse_caption_colors
from bot.services.pod_tournament import TROPHY_HYPE_HISTORY_LIMIT
from bot.services.self_reported_events import get_or_create_player, is_trophy_record, upsert_event
from bot.sets import active_set_code, parse_caption_set_code, prereleased_sets

logger = logging.getLogger(__name__)

# (label, application-emoji name); names resolve via emojis.get_emoji, None until added + reload
PLATFORM_CHOICES: tuple[tuple[str, str], ...] = (
    ("MTGO", "mtgo"),
    ("MTGA", "mtga"),
    ("xMage", "xmage"),
    ("Paper", "cardboard"),
)
PLATFORM_EMOJI_NAME = dict(PLATFORM_CHOICES)
FORMAT_CHOICES: tuple[str, ...] = ("Premier", "Traditional", "Single Elim")
WRITE_IN_EMOJI = "manax"
WRITE_IN = "__write_in__"
SET_SELECT_LIMIT = 23
SET_CODE_RE = re.compile(r"^[A-Z0-9]{2,5}$")

MSG_NO_CHANNEL = "Run `/trophy` in the channel where you posted your screenshot, or pass `link:` to a post"
MSG_NO_POST = (
    "No trophy screenshot found from you in {channel}. "
    "Post your screenshot here, then run `/trophy` or right-click it → Apps → 🏆 Record Event. "
    "To save one elsewhere, pass `link:`."
)
MSG_BAD_LINK = "That doesn't look like a Discord message link. Right-click a message → Copy Message Link"
MSG_LINK_NOT_FOUND = "Couldn't find that message. Check the link and try again"
MSG_NOT_YOUR_POST = "You can only save your own trophy posts"
MSG_NO_IMAGE = "That post has no image. Save the message that shows your trophy screenshot"


@dataclass
class TrophyDraft:
    discord_id: str
    discord_username: str
    display_name: str
    avatar_hash: str | None
    set_code: str
    source_channel_id: str
    source_message_id: str
    source_url: str
    event_time: datetime
    image_url: str | None
    caption: str | None
    record: str | None
    colors: str | None
    is_trophy: bool
    platform: str | None = None
    format: str | None = None
    already_logged: bool = False
    on_behalf: bool = False

    @property
    def can_confirm(self) -> bool:
        return bool(self.record and self.platform)


class Trophy(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="trophy", description=desc.TROPHY)
    @app_commands.describe(link="Link to a specific trophy post to save instead of your latest")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def trophy(self, interaction: discord.Interaction, link: str | None = None) -> None:
        ephemeral = interaction.guild is not None
        await interaction.response.defer(ephemeral=ephemeral, thinking=True)
        audit.event("trophy_invoked", user_id=str(interaction.user.id), link=link)

        if link is not None:
            message, error = await self._message_from_link(interaction, link)
        else:
            message, error = await self._latest_own_post(interaction)
        if error is not None:
            await interaction.followup.send(error, ephemeral=ephemeral)
            return

        await _present_trophy_draft(self.bot, interaction, message)

    async def _latest_own_post(
        self, interaction: discord.Interaction
    ) -> tuple[discord.Message | None, str | None]:
        channel = interaction.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread, discord.DMChannel)):
            return None, MSG_NO_CHANNEL
        async for message in channel.history(limit=TROPHY_HYPE_HISTORY_LIMIT):
            if message.author.id == interaction.user.id and first_image_url(message) is not None:
                return message, None
        label = channel.mention if isinstance(channel, (discord.TextChannel, discord.Thread)) else "this DM"
        return None, MSG_NO_POST.format(channel=label)

    async def _message_from_link(
        self, interaction: discord.Interaction, link: str
    ) -> tuple[discord.Message | None, str | None]:
        parsed = parse_message_link(link)
        if parsed is None:
            return None, MSG_BAD_LINK
        _, channel_id, message_id = parsed
        target = await self._resolve_channel(interaction.client, channel_id)
        if target is None:
            return None, MSG_LINK_NOT_FOUND
        try:
            message = await target.fetch_message(message_id)
        except discord.HTTPException:
            return None, MSG_LINK_NOT_FOUND
        if message.author.id != interaction.user.id and not await self.bot.is_owner(interaction.user):
            return None, MSG_NOT_YOUR_POST
        if first_image_url(message) is None:
            return None, MSG_NO_IMAGE
        return message, None

    async def _resolve_channel(
        self, client: discord.Client, channel_id: int
    ) -> discord.TextChannel | discord.Thread | None:
        channel = client.get_channel(channel_id)
        if channel is None:
            try:
                channel = await client.fetch_channel(channel_id)
            except discord.HTTPException:
                return None
        return channel if isinstance(channel, (discord.TextChannel, discord.Thread)) else None


def _render_embed(draft: TrophyDraft) -> discord.Embed:
    title = "🏆 Save this Trophy Deck" if draft.is_trophy else "📋 Save this Deck"
    embed = discord.Embed(title=title, color=0xFFC63A if draft.is_trophy else 0x8A8D91)
    embed.add_field(name="Set", value=draft.set_code, inline=True)
    embed.add_field(name="Record", value=draft.record or "*not set*", inline=True)
    embed.add_field(name="Trophy", value="Yes" if draft.is_trophy else "No", inline=True)
    embed.add_field(name="Colors", value=color_label(draft.colors) if draft.colors else "None", inline=True)
    embed.add_field(name="Platform", value=draft.platform or "*not set*", inline=True)
    embed.add_field(name="Format", value=draft.format or "*not set*", inline=True)
    if draft.caption:
        embed.add_field(name="Caption", value=draft.caption, inline=False)
    whose_post = f"{draft.display_name}'s post" if draft.on_behalf else "your post"
    embed.description = f"From [{whose_post}]({draft.source_url})"
    if draft.already_logged:
        embed.description += "\n⚠️ This post was already saved — confirming will update it."
    if draft.image_url:
        embed.set_thumbnail(url=draft.image_url)
    return embed


class TrophyConfirmView(ui.View):
    def __init__(self, draft: TrophyDraft, user_id: str, message: discord.Message) -> None:
        super().__init__(timeout=300)
        self.draft = draft
        self.user_id = user_id
        self.message = message
        self._build()

    def _build(self) -> None:
        self.clear_items()
        self.add_item(_SetSelect(self.draft))
        self.add_item(_ColorSelect(self.draft))
        self.add_item(_PlatformSelect(self.draft))
        self.add_item(_FormatSelect(self.draft))
        self.add_item(_RecordButton(self.draft.record))
        self.add_item(_TrophyToggleButton(self.draft.is_trophy))
        self.add_item(_ConfirmButton(disabled=not self.draft.can_confirm))
        self.add_item(_CancelButton())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return str(interaction.user.id) == self.user_id

    async def rerender(self, interaction: discord.Interaction) -> None:
        self._build()
        await interaction.response.edit_message(embed=_render_embed(self.draft), view=self)


class _SetSelect(ui.Select):
    def __init__(self, draft: TrophyDraft) -> None:
        recent = prereleased_sets()[:SET_SELECT_LIMIT]
        options: list[discord.SelectOption] = [
            discord.SelectOption(label="Other (write-in)", value=WRITE_IN, emoji=emojis.get_emoji(WRITE_IN_EMOJI))
        ]
        if draft.set_code not in {s.code for s in recent}:
            options.append(discord.SelectOption(
                label=draft.set_code, value=draft.set_code, emoji=emojis.set_symbol(draft.set_code), default=True
            ))
        options.extend(
            discord.SelectOption(
                label=s.code, description=s.name[:100], value=s.code,
                emoji=emojis.set_symbol(s.code), default=(draft.set_code == s.code),
            )
            for s in recent
        )
        super().__init__(placeholder="Set", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: TrophyConfirmView = self.view
        if self.values[0] == WRITE_IN:
            await interaction.response.send_modal(_SetWriteInModal(view))
            return
        view.draft.set_code = self.values[0]
        await view.rerender(interaction)


class _ColorSelect(ui.Select):
    def __init__(self, draft: TrophyDraft) -> None:
        guild_codes = {code for code, _ in GUILDS}
        is_write_in = bool(draft.colors) and draft.colors not in guild_codes
        options = [discord.SelectOption(
            label=f"Other ({draft.colors})" if is_write_in else "Other (write-in)",
            value=WRITE_IN,
            description="Mono, 3-color, splash, etc.",
            emoji=emojis.get_emoji(WRITE_IN_EMOJI),
            default=is_write_in,
        )]
        options.extend(
            discord.SelectOption(
                label=f"{name} ({code})", value=code, default=(draft.colors == code),
                emoji=emojis.get_emoji(PAIR_EMOJI_NAME[frozenset(code)]),
            )
            for code, name in GUILDS
        )
        super().__init__(placeholder="Colors", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: TrophyConfirmView = self.view
        if self.values[0] == WRITE_IN:
            await interaction.response.send_modal(_ColorWriteInModal(view))
            return
        view.draft.colors = self.values[0]
        await view.rerender(interaction)


class _PlatformSelect(ui.Select):
    def __init__(self, draft: TrophyDraft) -> None:
        known = {label for label, _ in PLATFORM_CHOICES}
        is_write_in = draft.platform is not None and draft.platform not in known
        options = [
            discord.SelectOption(
                label=label, value=label, emoji=emojis.get_emoji(name), default=(draft.platform == label)
            )
            for label, name in PLATFORM_CHOICES
        ]
        options.append(
            discord.SelectOption(
                label=f"Other ({draft.platform})" if is_write_in else "Other (write-in)",
                value=WRITE_IN,
                emoji=emojis.get_emoji(WRITE_IN_EMOJI),
                default=is_write_in,
            )
        )
        super().__init__(placeholder="Platform", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: TrophyConfirmView = self.view
        if self.values[0] == WRITE_IN:
            await interaction.response.send_modal(_PlatformWriteInModal(view))
            return
        view.draft.platform = self.values[0]
        await view.rerender(interaction)


class _FormatSelect(ui.Select):
    def __init__(self, draft: TrophyDraft) -> None:
        is_write_in = draft.format is not None and draft.format not in FORMAT_CHOICES
        options = [
            discord.SelectOption(label=label, value=label, default=(draft.format == label))
            for label in FORMAT_CHOICES
        ]
        options.append(
            discord.SelectOption(
                label=f"Other ({draft.format})" if is_write_in else "Other (write-in)",
                value=WRITE_IN,
                emoji=emojis.get_emoji(WRITE_IN_EMOJI),
                default=is_write_in,
            )
        )
        super().__init__(placeholder="Format", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: TrophyConfirmView = self.view
        if self.values[0] == WRITE_IN:
            await interaction.response.send_modal(_FormatWriteInModal(view))
            return
        view.draft.format = self.values[0]
        await view.rerender(interaction)


class _RecordButton(ui.Button):
    def __init__(self, record: str | None) -> None:
        super().__init__(
            label="Edit Record" if record else "Set Record",
            style=discord.ButtonStyle.secondary,
            emoji="✏️",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(_RecordModal(self.view))


class _TrophyToggleButton(ui.Button):
    def __init__(self, is_trophy: bool) -> None:
        super().__init__(
            label=f"Trophy: {'Yes' if is_trophy else 'No'}",
            style=discord.ButtonStyle.success if is_trophy else discord.ButtonStyle.secondary,
            emoji="🏆",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: TrophyConfirmView = self.view
        view.draft.is_trophy = not view.draft.is_trophy
        await view.rerender(interaction)


class _ConfirmButton(ui.Button):
    def __init__(self, disabled: bool) -> None:
        super().__init__(label="Confirm", style=discord.ButtonStyle.success, emoji="🏆", disabled=disabled)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: TrophyConfirmView = self.view
        draft = view.draft
        with SessionLocal() as session:
            player = get_or_create_player(
                session,
                discord_id=draft.discord_id,
                discord_username=draft.discord_username,
                display_name=draft.display_name,
                avatar_hash=draft.avatar_hash,
            )
            upsert_event(
                session,
                player_id=player.id,
                set_code=draft.set_code,
                record=draft.record,
                is_trophy=draft.is_trophy,
                colors=draft.colors,
                platform=draft.platform,
                format=draft.format,
                caption=draft.caption,
                screenshot_url=strip_cdn_dims(draft.image_url) if draft.image_url else None,
                source_channel_id=draft.source_channel_id,
                source_message_id=draft.source_message_id,
                source_url=draft.source_url,
                reported_at=draft.event_time,
            )
            deck = player_deck_url(player.slug, draft.set_code, draft.source_message_id)
            session.commit()
        audit.event(
            "trophy_logged", user_id=view.user_id, set_code=draft.set_code,
            record=draft.record, is_trophy=draft.is_trophy, platform=draft.platform,
        )
        logger.info(f"trophy: {view.user_id} logged {draft.record} {draft.colors} on {draft.platform}")
        emoji = "🏆" if draft.is_trophy else "📋"
        colors = color_label(draft.colors) if draft.colors else "no colors"
        oversight = (
            f"{emoji} **{draft.display_name}** (`{draft.discord_username}`) saved "
            f"**{draft.record}** · {colors} · {draft.platform} · {draft.format} · {draft.set_code} — "
            f"[post]({draft.source_url})"
        )
        await bot_log.get(interaction.client).post_plain(oversight)
        await _mark_post_logged(view.message, draft.set_code, draft.platform)
        color_glyph = format_deck_color_emojis(draft.colors)
        platform_glyph = emojis.prefix(PLATFORM_EMOJI_NAME.get(draft.platform, ""))
        headline_parts = [f"**{draft.record}**"]
        if color_glyph:
            headline_parts.append(color_glyph)
        headline_parts.append(f"{platform_glyph}{draft.platform}")
        whose_profile = f"{draft.display_name}'s profile" if draft.on_behalf else "your profile"
        profile_line = f"Added to [{whose_profile}]({deck}) {emojis.get('manat')}".rstrip()
        done = discord.Embed(
            title="🏆 Trophy Recorded" if draft.is_trophy else "📋 Event Recorded",
            description=f"{' '.join(headline_parts)}\n{profile_line}",
            color=0x57F287,
        )
        await interaction.response.edit_message(embed=done, view=None)


class _CancelButton(ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Cancel", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(content="Canceled", embed=None, view=None)


class _PlatformWriteInModal(ui.Modal, title="Platform"):
    platform = ui.TextInput(label="Platform", placeholder="e.g. LGS Friday Night Magic", max_length=60, required=True)

    def __init__(self, view: TrophyConfirmView) -> None:
        super().__init__()
        self._view = view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self._view.draft.platform = self.platform.value.strip()
        await self._view.rerender(interaction)


class _FormatWriteInModal(ui.Modal, title="Format"):
    format = ui.TextInput(label="Format", placeholder="e.g. Chaos Draft, Cube", max_length=40, required=True)

    def __init__(self, view: TrophyConfirmView) -> None:
        super().__init__()
        self._view = view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self._view.draft.format = self.format.value.strip()
        await self._view.rerender(interaction)


class _RecordModal(ui.Modal, title="Record"):
    record = ui.TextInput(label="Record (e.g. 3-0, 7-2)", max_length=10, required=True)
    caption = ui.TextInput(
        label="Caption (shown with your deck)",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=False,
    )

    def __init__(self, view: TrophyConfirmView) -> None:
        super().__init__()
        self._view = view
        self.record.default = view.draft.record or ""
        self.caption.default = view.draft.caption or ""

    async def on_submit(self, interaction: discord.Interaction) -> None:
        record = self.record.value.strip()
        if not RECORD_RE.match(record):
            await interaction.response.send_message(
                f"⚠️ `{record}` isn't a valid record. Use a W-L like `3-0` or `7-2`", ephemeral=True
            )
            return
        self._view.draft.record = record
        self._view.draft.is_trophy = is_trophy_record(record)
        self._view.draft.caption = self.caption.value.strip() or None
        await self._view.rerender(interaction)


class _ColorWriteInModal(ui.Modal, title="Deck colors"):
    colors = ui.TextInput(
        label="Colors (e.g. URg, WUBR, WUBRG)",
        placeholder="Uppercase = main, lowercase = splash",
        max_length=5,
        required=True,
    )

    def __init__(self, view: TrophyConfirmView) -> None:
        super().__init__()
        self._view = view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        colors_raw = self.colors.value.strip()
        if not COLORS_RE.match(colors_raw):
            await interaction.response.send_message(
                f"⚠️ `{colors_raw}` isn't valid. Use only W/U/B/R/G letters, 1–5 chars", ephemeral=True
            )
            return
        self._view.draft.colors = normalize_colors(colors_raw)
        await self._view.rerender(interaction)


class _SetWriteInModal(ui.Modal, title="Set"):
    set_code = ui.TextInput(label="Set (e.g. SOS, or a flashback set)", max_length=5, required=True)

    def __init__(self, view: TrophyConfirmView) -> None:
        super().__init__()
        self._view = view
        self.set_code.default = view.draft.set_code

    async def on_submit(self, interaction: discord.Interaction) -> None:
        set_code = self.set_code.value.strip().upper()
        if not SET_CODE_RE.match(set_code):
            await interaction.response.send_message(
                f"⚠️ `{set_code}` isn't a valid set code. Use 2–5 letters or digits like `SOS`", ephemeral=True
            )
            return
        self._view.draft.set_code = set_code
        await self._view.rerender(interaction)


def _default_format(record: str | None) -> str:
    """A 7-win run reads Premier, anything shorter Traditional; single elim needs an explicit pick."""
    wins = int(record.split("-")[0]) if record and RECORD_RE.match(record) else 0
    return "Premier" if wins >= 7 else "Traditional"


async def _present_trophy_draft(
    bot: commands.Bot, interaction: discord.Interaction, message: discord.Message
) -> None:
    """Parse a resolved post into a TrophyDraft and open the confirm view. Shared by the /trophy
    slash command and the Record Event message context menu."""
    author = message.author
    caption = message_caption(message)
    record = parse_caption_record(caption) or "3-0"
    draft = TrophyDraft(
        discord_id=str(author.id),
        discord_username=str(author),
        display_name=await resolve_display_name(bot, author),
        avatar_hash=extract_avatar_hash(author),
        set_code=parse_caption_set_code(caption) or active_set_code(message.created_at),
        source_channel_id=str(message.channel.id),
        source_message_id=str(message.id),
        source_url=message.jump_url,
        event_time=message.created_at,
        image_url=first_image_url(message),
        caption=caption,
        record=record,
        colors=parse_caption_colors(caption),
        is_trophy=is_trophy_record(record),
        format=_default_format(record),
        already_logged=any(reaction.me for reaction in message.reactions),
        on_behalf=str(author.id) != str(interaction.user.id),
    )
    view = TrophyConfirmView(draft, str(interaction.user.id), message)
    ephemeral = interaction.guild is not None
    await interaction.followup.send(embed=_render_embed(draft), view=view, ephemeral=ephemeral)


@app_commands.context_menu(name="🏆 Record Event")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=False)
@app_commands.allowed_installs(guilds=True, users=False)
async def save_trophy_menu(interaction: discord.Interaction, message: discord.Message) -> None:
    ephemeral = interaction.guild is not None
    await interaction.response.defer(ephemeral=ephemeral, thinking=True)
    audit.event("trophy_invoked", user_id=str(interaction.user.id), via="context_menu")
    is_own = message.author.id == interaction.user.id
    if not is_own and not await interaction.client.is_owner(interaction.user):
        await interaction.followup.send(MSG_NOT_YOUR_POST, ephemeral=ephemeral)
        return
    if first_image_url(message) is None:
        await interaction.followup.send(MSG_NO_IMAGE, ephemeral=ephemeral)
        return
    await _present_trophy_draft(interaction.client, interaction, message)


def _platform_emoji(platform: str | None) -> discord.Emoji | None:
    for label, name in PLATFORM_CHOICES:
        if label == platform:
            return emojis.get_emoji(name)
    return None


async def _mark_post_logged(message: discord.Message, set_code: str, platform: str | None) -> None:
    """React to the trophy-hype post to mark it logged: the set's emoji, else the platform's, else 🏆."""
    emoji = (
        emojis.get_emoji(set_code.lower())
        or emojis.get_emoji(set_code)
        or _platform_emoji(platform)
        or "🏆"
    )
    try:
        await message.add_reaction(emoji)
    except discord.HTTPException:
        logger.warning(f"trophy: could not react to post {message.id}", exc_info=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Trophy(bot))
    bot.tree.add_command(save_trophy_menu)
