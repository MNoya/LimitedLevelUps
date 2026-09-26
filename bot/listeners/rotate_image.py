"""React ♻️ on an image post → reply with the same image rotated upright.

Fixes prerelease-deck screenshots posted sideways. Fires when any member reacts ♻️.
The image is normalized to its displayed orientation, then rotated 90° counterclockwise.
The original message stays put. The rotated copy is posted as a reply, seeded with ⤴️
(rotate another 90°), 🔄 (flip 180°), and ❌ (delete it). One manual correction is allowed,
after which the rotate reactions are stripped and only ❌ remains. After a short window the
reply auto-cleans: the bot's control reactions and the hint line are removed, leaving just
the message and image to keep the channel tidy.
"""
from __future__ import annotations

import asyncio
import io
import logging
import random
from collections.abc import Callable

import discord
from discord.ext import commands
from PIL import Image, ImageOps, ImageSequence

log = logging.getLogger(__name__)

VARIATION_SELECTOR = "️"
RECYCLE_EMOJI = "♻️"
ROTATE_EMOJI = "⤴️"
FLIP_EMOJI = "🔄"
DISMISS_EMOJI = "❌"
ROTATED_LINES = (
    "{mention} here is your image, I rotated it to save everyone the neck pain ♻️",
    "{mention} your image was a bit twisted, so I rotated it ♻️",
    "{mention} by order of the ♻️, your image has been rotated",
    "{mention} your image was sideways, so I rotated it to comply with ♻️ standards",
    "{mention} phones have had a rotate button since 2007, but here you go ♻️",
    "{mention} the technology to rotate this exists on your end too, just saying ♻️",
    "{mention} image rotation has been a solved problem for decades, but here we are ♻️",
    "{mention} every device made this century can do this, but I got you ♻️",
    "{mention} the rotate button on your phone is two taps away ♻️",
    "{mention} half the channel tilted their heads for this one ♻️",
    "{mention} you are supposed to turn your creatures sideways, not your deck image ♻️",
)
HINT_CORRECT_OR_DISMISS = "-# react ⤴️ to rotate it 90°, 🔄 to flip it 180°, or ❌ to dismiss this message"
HINT_DISMISS = "-# react ❌ to dismiss this message"
CLEANUP_DELAY_S = 60


class RotateImageListener(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.handled: set[int] = set()
        self.reply_to_original: dict[int, int] = {}
        self.edited_once: set[int] = set()
        self.last_line: str | None = None

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.guild_id is None:
            return
        if self.bot.user is not None and payload.user_id == self.bot.user.id:
            return

        if payload.message_id in self.reply_to_original:
            if _is_dismiss(payload.emoji):
                await self._dismiss(payload.channel_id, payload.message_id)
            elif payload.message_id not in self.edited_once:
                if _is_rotate(payload.emoji):
                    await self._rotate_in_place(payload, 90)
                elif _is_flip(payload.emoji):
                    await self._rotate_in_place(payload, 180)
            return

        if not _is_recycle(payload.emoji) or payload.message_id in self.handled:
            return
        message = await self._fetch_message(payload.channel_id, payload.message_id)
        if message is None or message.author.bot:
            return
        if _bot_marked_recycle(message):
            self.handled.add(payload.message_id)
            return
        attachment = _first_image_attachment(message)
        if attachment is None:
            return
        if payload.message_id in self.handled:
            return

        self.handled.add(payload.message_id)
        await self._reply_rotated(message, attachment)

    async def _fetch_message(self, channel_id: int, message_id: int) -> discord.Message | None:
        channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
        try:
            return await channel.fetch_message(message_id)
        except discord.HTTPException:
            log.info(f"could not fetch message {message_id} for ♻️ rotate", exc_info=True)
            return None

    async def _reply_rotated(self, message: discord.Message, attachment: discord.Attachment) -> None:
        log.info(f"[ROTATE] rotating image msg={message.id} author={message.author.id}")
        rotated = await self._rotate_attachment(attachment)
        if rotated is None:
            self.handled.discard(message.id)
            return
        line = self._pick_line().format(mention=message.author.mention)
        try:
            reply = await message.reply(
                f"{line}\n{HINT_CORRECT_OR_DISMISS}",
                file=discord.File(io.BytesIO(rotated), filename=attachment.filename),
            )
        except discord.HTTPException:
            log.warning(f"could not reply with rotated image for msg={message.id}", exc_info=True)
            self.handled.discard(message.id)
            return
        self.reply_to_original[reply.id] = message.id
        try:
            await message.add_reaction(RECYCLE_EMOJI)
        except discord.HTTPException:
            log.info(f"could not mark original {message.id} as handled", exc_info=True)
        for emoji in (ROTATE_EMOJI, FLIP_EMOJI, DISMISS_EMOJI):
            try:
                await reply.add_reaction(emoji)
            except discord.HTTPException:
                log.info(f"could not seed {emoji} on rotated reply {reply.id}", exc_info=True)
        asyncio.create_task(self._cleanup_after_delay(reply.channel.id, reply.id))

    def _pick_line(self) -> str:
        choices = [line for line in ROTATED_LINES if line != self.last_line] or list(ROTATED_LINES)
        self.last_line = random.choice(choices)
        return self.last_line

    async def _rotate_in_place(self, payload: discord.RawReactionActionEvent, degrees: int) -> None:
        if payload.message_id in self.edited_once:
            return
        self.edited_once.add(payload.message_id)

        message = await self._fetch_message(payload.channel_id, payload.message_id)
        attachment = _first_image_attachment(message) if message else None
        if message is None or attachment is None:
            self.edited_once.discard(payload.message_id)
            return
        rotated = await self._rotate_attachment(attachment, degrees)
        if rotated is None:
            self.edited_once.discard(payload.message_id)
            return

        first_line = message.content.split("\n", 1)[0]
        content = f"{first_line}\n{HINT_DISMISS}"
        try:
            await message.edit(
                content=content,
                attachments=[discord.File(io.BytesIO(rotated), filename=attachment.filename)],
            )
        except discord.HTTPException:
            log.warning(f"could not edit rotated reply {message.id} in place", exc_info=True)
            self.edited_once.discard(payload.message_id)
            return
        await self._strip_rotate_reactions(message, payload)

    async def _strip_rotate_reactions(self, message: discord.Message, payload: discord.RawReactionActionEvent) -> None:
        if self.bot.user is not None:
            for emoji in (ROTATE_EMOJI, FLIP_EMOJI):
                try:
                    await message.remove_reaction(emoji, self.bot.user)
                except discord.HTTPException:
                    pass
        if payload.member is not None:
            try:
                await message.remove_reaction(payload.emoji, payload.member)
            except discord.HTTPException:
                pass

    async def _dismiss(self, channel_id: int, message_id: int) -> None:
        message = await self._fetch_message(channel_id, message_id)
        if message is None:
            return
        try:
            await message.delete()
        except discord.HTTPException:
            log.warning(f"could not dismiss rotated reply {message_id}", exc_info=True)
            return
        original_id = self.reply_to_original.pop(message_id, None)
        self.edited_once.discard(message_id)
        if original_id is not None:
            self.handled.discard(original_id)
            await self._clear_recycle_marker(channel_id, original_id)

    async def _clear_recycle_marker(self, channel_id: int, message_id: int) -> None:
        """Remove the bot's ♻️ from a dismissed post's original, so a fresh ♻️ can re-process it."""
        if self.bot.user is None:
            return
        original = await self._fetch_message(channel_id, message_id)
        if original is None:
            return
        try:
            await original.remove_reaction(RECYCLE_EMOJI, self.bot.user)
        except discord.HTTPException:
            log.info(f"could not clear ♻️ marker on original {message_id}", exc_info=True)

    async def _cleanup_after_delay(self, channel_id: int, message_id: int) -> None:
        await asyncio.sleep(CLEANUP_DELAY_S)
        if message_id not in self.reply_to_original:
            return
        message = await self._fetch_message(channel_id, message_id)
        if message is None:
            return
        first_line = message.content.split("\n", 1)[0]
        try:
            await message.edit(content=first_line)
        except discord.HTTPException:
            log.info(f"could not strip hint from rotated reply {message_id}", exc_info=True)
        if self.bot.user is not None:
            for emoji in (ROTATE_EMOJI, FLIP_EMOJI, DISMISS_EMOJI):
                try:
                    await message.remove_reaction(emoji, self.bot.user)
                except discord.HTTPException:
                    pass

    async def _rotate_attachment(self, attachment: discord.Attachment, degrees: int | None = None) -> bytes | None:
        raw = await attachment.read()
        if degrees is None:
            return await asyncio.to_thread(_rotate_upright, raw)
        return await asyncio.to_thread(_rotate_fixed, raw, degrees)


def _is_recycle(emoji: "discord.PartialEmoji | discord.Emoji | str") -> bool:
    return _emoji_matches(emoji, RECYCLE_EMOJI)


def _is_rotate(emoji: "discord.PartialEmoji | discord.Emoji | str") -> bool:
    return _emoji_matches(emoji, ROTATE_EMOJI)


def _is_flip(emoji: "discord.PartialEmoji | discord.Emoji | str") -> bool:
    return _emoji_matches(emoji, FLIP_EMOJI)


def _is_dismiss(emoji: "discord.PartialEmoji | discord.Emoji | str") -> bool:
    return _emoji_matches(emoji, DISMISS_EMOJI)


def _emoji_matches(emoji: "discord.PartialEmoji | discord.Emoji | str", target: str) -> bool:
    name = emoji if isinstance(emoji, str) else getattr(emoji, "name", "") or ""
    return name.replace(VARIATION_SELECTOR, "") == target.replace(VARIATION_SELECTOR, "")


def _bot_marked_recycle(message: discord.Message) -> bool:
    """The bot reacts ♻️ on an original once it has replied, so a restart can't re-trigger a repost."""
    for reaction in message.reactions:
        if _is_recycle(reaction.emoji) and reaction.me:
            return True
    return False


def _first_image_attachment(message: discord.Message) -> discord.Attachment | None:
    for attachment in message.attachments:
        if (attachment.content_type or "").lower().startswith("image/"):
            return attachment
    return None


def _rotate_upright(raw: bytes) -> bytes | None:
    def upright(image: "Image.Image") -> "Image.Image":
        return ImageOps.exif_transpose(image).rotate(90, expand=True)

    return _rotate_image(raw, upright)


def _rotate_fixed(raw: bytes, degrees: int) -> bytes | None:
    def turn(image: "Image.Image") -> "Image.Image":
        return image.rotate(degrees, expand=True)

    return _rotate_image(raw, turn)


def _rotate_image(raw: bytes, transform: "Callable[[Image.Image], Image.Image]") -> bytes | None:
    image = _open_image(raw)
    if image is None:
        return None
    if getattr(image, "is_animated", False):
        return _encode_animated(image, transform)
    source_format = image.format or "PNG"
    return _encode(transform(image), source_format)


def _open_image(raw: bytes) -> "Image.Image | None":
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
        return image
    except OSError:
        log.info("could not decode image for ♻️ rotate", exc_info=True)
        return None


def _encode(image: "Image.Image", source_format: str) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format=source_format)
    return buffer.getvalue()


def _encode_animated(image: "Image.Image", transform: "Callable[[Image.Image], Image.Image]") -> bytes:
    frames = [transform(frame.copy()) for frame in ImageSequence.Iterator(image)]
    buffer = io.BytesIO()
    frames[0].save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        loop=image.info.get("loop", 0),
        duration=image.info.get("duration", 100),
        disposal=2,
    )
    return buffer.getvalue()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RotateImageListener(bot))
