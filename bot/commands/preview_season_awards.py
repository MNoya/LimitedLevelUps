"""Admin-only `/preview-season-awards` — awards ceremony for a set's preview season.

Scans every channel whose name contains "preview-season" for image posts inside the
set's preview window, tallies emoji reactions, and posts a Components V2 ceremony:
one award per reaction category plus a hype meter of fire vs trash sentiment.

Presentation is fully decoupled from data: `build_awards_view` renders an
`AwardsData`, so `!testawards` can feed fixture data through the same builder.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import discord
from discord import app_commands, ui
from discord.ext import commands

from bot import audit
from bot.commands import descriptions as desc
from bot.commands.messages import MSG_ADMIN_ONLY
from bot.discord_helpers import NBSP, ZWSP, first_image_url
from bot.sets import PREVIEW_WINDOWS, PreviewWindow

log = logging.getLogger(__name__)

COMMUNITY_TZ = ZoneInfo("America/New_York")

FIRE = "🔥"
THUMBS_UP = "👍"
THINKING = "🤔"
WASTEBASKET = "🗑"
WILTED_ROSE = "🥀"
JOY = "😂"
CORE_EMOJIS = (FIRE, THUMBS_UP, THINKING, WASTEBASKET, WILTED_ROSE, JOY)
EMOJI_DISPLAY = {WASTEBASKET: "🗑️"}
SKIN_TONE_MODIFIERS = {chr(codepoint): None for codepoint in range(0x1F3FB, 0x1F400)}

GAP = NBSP * 2
SUBTEXT_START = f"-# {ZWSP}"

HYPE_BAR_SLOTS = 10
CAPTION_MAX_CHARS = 100
CREDIT_NBSP_PER_CHAR = 2.0
CREDIT_PAD_MAX = 120
FOOTER_MAX_EMOJIS = 7
REVEAL_DELAY_SECONDS = 5

SUSPENSE_COUNTING = "Counting the Votes…"
SUSPENSE_UP_NEXT = "Up Next…"
SUSPENSE_FINAL = "Final Verdict…"

MSG_NO_CHANNELS = "No channels with “preview-season” in the name were found in this server."
MSG_NO_POSTS = "No image posts found between {start} and {end} — nothing to award."
MSG_NO_REACTIONS = "Found {count} image posts but no reactions to score."
MSG_POSTED = "🏆 Awards posted — {awards} prizes handed out across {posts} posts."


@dataclass(frozen=True)
class AwardWinner:
    jump_url: str
    image_url: str
    recounts: tuple[tuple[str, int], ...]
    caption: str | None = None
    author: str | None = None


@dataclass(frozen=True)
class AwardsData:
    set_code: str
    window_label: str
    channel_label: str
    hottest: AwardWinner | None
    acceptable: AwardWinner | None
    jury: AwardWinner | None
    trash: AwardWinner | None
    comedy: AwardWinner | None
    flavor: AwardWinner | None
    totals: tuple[tuple[str, int], ...]
    hot_pct: int | None

    @property
    def award_count(self) -> int:
        winners = (self.hottest, self.acceptable, self.jury, self.trash, self.comedy, self.flavor)
        return sum(winner is not None for winner in winners)


@dataclass(frozen=True)
class ScoredPost:
    jump_url: str
    image_url: str
    content: str
    author: str
    created_at: datetime
    reactions: dict[str, int]


def build_awards_view(data: AwardsData, reveal: int | None = None) -> ui.LayoutView:
    """Render the ceremony; `reveal=N` shows only the first N awards with a suspense line and
    holds back the hype meter + footer for the final full render (`reveal=None`)."""
    view = ui.LayoutView()
    container = ui.Container(accent_colour=discord.Color.green())

    container.add_item(ui.TextDisplay(
        f"## 🏆 {data.set_code} Preview Season Awards\n"
        f"{SUBTEXT_START}{data.window_label}{GAP}{data.channel_label}"
    ))
    container.add_item(ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small))

    rows = (
        ("### 🔥 Windmill Slam", "Certified Heater", data.hottest),
        ("### 👍 Voted Most Acceptable", "Playable", data.acceptable),
        ("### 🤔 The Jury is Still Out", "Ask Again in Two Weeks", data.jury),
        ("### 🗑️ Last-Pick Material", "Leave in the Sideboard", data.trash),
        ("### 😂 Comedy Gold", "No Notes", data.comedy),
        ("### ⭐ Flavor Win", "Nailed It", data.flavor),
    )
    awarded_rows = [(heading, tagline, winner) for heading, tagline, winner in rows if winner is not None]
    shown_rows = awarded_rows if reveal is None else awarded_rows[:reveal]
    for i, (heading, tagline, winner) in enumerate(shown_rows):
        award_text = _award_text(heading, tagline, winner, caption_replaces=winner is data.comedy)
        container.add_item(ui.Section(
            ui.TextDisplay(award_text),
            accessory=ui.Thumbnail(media=winner.image_url, spoiler=True),
        ))
        if i < len(shown_rows) - 1:
            container.add_item(ui.Separator(visible=False, spacing=discord.SeparatorSpacing.small))

    if reveal is not None:
        if shown_rows:
            container.add_item(ui.Separator(visible=False, spacing=discord.SeparatorSpacing.small))
        container.add_item(ui.TextDisplay(f"{SUBTEXT_START}🥁{GAP}{_suspense_line(reveal, len(awarded_rows))}"))
    else:
        if data.hot_pct is not None:
            container.add_item(ui.Separator(visible=True, spacing=discord.SeparatorSpacing.large))
            container.add_item(ui.TextDisplay(_hype_meter_text(data.hot_pct)))
        if data.totals:
            container.add_item(ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small))
            container.add_item(ui.TextDisplay(_footer_text(data.totals)))

    view.add_item(container)
    return view


async def reveal_awards(message: discord.Message, data: AwardsData) -> None:
    for shown in range(1, data.award_count + 1):
        await asyncio.sleep(REVEAL_DELAY_SECONDS)
        await message.edit(view=build_awards_view(data, reveal=shown))
    await asyncio.sleep(REVEAL_DELAY_SECONDS)
    await message.edit(view=build_awards_view(data))


def _suspense_line(reveal: int, award_total: int) -> str:
    if reveal == 0:
        return SUSPENSE_COUNTING
    if reveal < award_total:
        return SUSPENSE_UP_NEXT
    return SUSPENSE_FINAL


def _award_text(heading: str, tagline: str, winner: AwardWinner, caption_replaces: bool = False) -> str:
    if winner.caption and caption_replaces:
        line = f"[_{winner.caption}_]({winner.jump_url})"
    elif winner.caption:
        line = f"_{tagline} -_ [{winner.caption}]({winner.jump_url})"
    else:
        line = f"[{tagline}]({winner.jump_url})"
    recount = (GAP * 2).join(_emoji_count(emoji, count) for emoji, count in winner.recounts)
    subtext = f"{SUBTEXT_START}{GAP}{recount}"
    if winner.caption and caption_replaces and winner.author:
        subtext += _credit_suffix(winner.caption, recount, winner.author)
    return f"{heading}\n{GAP}{line}\n{subtext}"


def _credit_suffix(caption: str, recount: str, author: str) -> str:
    """Push the credit toward the end of the quote above, approximately: Discord has no real
    alignment, so pad with NBSPs scaled by how much of the caption's width the recount left over."""
    credit = f"~{author}"
    pad_chars = round((len(caption) - len(recount) - len(credit)) * CREDIT_NBSP_PER_CHAR)
    pad = NBSP * min(max(pad_chars, 0), CREDIT_PAD_MAX)
    return f"{pad}{credit}"


def _hype_meter_text(hot_pct: int) -> str:
    filled = round(hot_pct * HYPE_BAR_SLOTS / 100)
    bar = "|".join(["🟩"] * filled + ["⬛"] * (HYPE_BAR_SLOTS - filled))
    return f"### 📊 Hype Meter\n{bar}{GAP}**{hot_pct}%**"


def _footer_text(totals: tuple[tuple[str, int], ...]) -> str:
    core = [(emoji, count) for emoji, count in totals if emoji in CORE_EMOJIS]
    extras = [(emoji, count) for emoji, count in totals if emoji not in CORE_EMOJIS]
    counts = (GAP * 2).join(_emoji_count(emoji, count) for emoji, count in core)
    for emoji, count in extras:
        counts += f"{GAP}{_emoji_count(emoji, count)}"
    return f"{SUBTEXT_START}{counts}"


def _emoji_count(emoji: str, count: int) -> str:
    return f"{EMOJI_DISPLAY.get(emoji, emoji)} {count}"


class PreviewSeasonAwards(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="preview-season-awards", description=desc.PREVIEW_SEASON_AWARDS)
    @app_commands.describe(set="Set Code")
    @app_commands.choices(set=[app_commands.Choice(name=w.set_code, value=w.set_code) for w in PREVIEW_WINDOWS])
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def preview_season_awards(self, interaction: discord.Interaction, set: str) -> None:
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message(MSG_ADMIN_ONLY, ephemeral=True)
            return

        window = next(w for w in PREVIEW_WINDOWS if w.set_code == set)
        channels = [c for c in interaction.guild.text_channels if "preview-season" in c.name]
        if not channels:
            await interaction.response.send_message(MSG_NO_CHANNELS, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        empty_data = AwardsData(
            set_code=set,
            window_label=window_label(window),
            channel_label=channel_label(channels),
            hottest=None, acceptable=None, jury=None, trash=None, comedy=None, flavor=None,
            totals=(), hot_pct=None,
        )
        ceremony = await interaction.channel.send(view=build_awards_view(empty_data, reveal=0))

        posts = await _collect_posts(channels, window)
        if not posts:
            await ceremony.delete()
            await interaction.followup.send(
                MSG_NO_POSTS.format(start=_day_label(window.start_date), end=_day_label(window.end_date)),
                ephemeral=True,
            )
            return

        data = replace(empty_data, **_tally_fields(posts))
        if data.award_count == 0:
            await ceremony.delete()
            await interaction.followup.send(MSG_NO_REACTIONS.format(count=len(posts)), ephemeral=True)
            return

        await reveal_awards(ceremony, data)
        audit.event(
            "preview_season_awards_posted",
            set_code=set,
            posts=len(posts),
            awards=data.award_count,
            channel_id=str(interaction.channel.id),
        )
        log.info(f"preview season awards posted for {set}: {data.award_count} awards from {len(posts)} posts")
        await interaction.followup.send(
            MSG_POSTED.format(awards=data.award_count, posts=len(posts)), ephemeral=True,
        )


def _tally_fields(posts: list[ScoredPost]) -> dict:
    totals: dict[str, int] = {}
    extra_totals: dict[str, int] = {}
    posts_using: dict[str, int] = {}
    for post in posts:
        for emoji in CORE_EMOJIS:
            totals[emoji] = totals.get(emoji, 0) + post.reactions.get(emoji, 0)
        for emoji, count in post.reactions.items():
            if count > 0:
                posts_using[emoji] = posts_using.get(emoji, 0) + 1
            if emoji not in CORE_EMOJIS:
                extra_totals[emoji] = extra_totals.get(emoji, 0) + count

    hot_denominator = totals[FIRE] + totals[WASTEBASKET] + totals[WILTED_ROSE]
    hot_pct = round(totals[FIRE] * 100 / hot_denominator) if hot_denominator else None

    core_counts = [(emoji, count) for emoji, count in totals.items() if count > 0 and posts_using[emoji] > 1]
    reused_extras = [(emoji, count) for emoji, count in extra_totals.items() if posts_using[emoji] > 1]
    extras_room = max(FOOTER_MAX_EMOJIS - len(core_counts), 0)
    top_extras = sorted(reused_extras, key=lambda item: item[1], reverse=True)[:extras_room]

    pool = list(posts)

    def claim_category(emojis: tuple[str, ...]) -> AwardWinner | None:
        post = _category_best(pool, emojis)
        if post is None:
            return None
        pool.remove(post)
        return _winner_from_post(post, _recounts(post, emojis))

    hottest = claim_category((FIRE,))
    acceptable = claim_category((THUMBS_UP,))
    jury = claim_category((THINKING,))
    trash = claim_category((WASTEBASKET, WILTED_ROSE))
    comedy = claim_category((JOY,))

    flavor = None
    flavor_best = _flavor_best(pool)
    if flavor_best is not None:
        post, emoji = flavor_best
        pool.remove(post)
        flavor = _winner_from_post(post, _recounts(post, (emoji,)))

    return dict(
        hottest=hottest,
        acceptable=acceptable,
        jury=jury,
        trash=trash,
        comedy=comedy,
        flavor=flavor,
        totals=tuple(core_counts + top_extras),
        hot_pct=hot_pct,
    )


def _category_best(posts: list[ScoredPost], emojis: tuple[str, ...]) -> ScoredPost | None:
    best: ScoredPost | None = None
    best_key: tuple[int, int, datetime] | None = None
    for post in posts:
        score = sum(post.reactions.get(emoji, 0) for emoji in emojis)
        if score == 0:
            continue
        key = (score, _extra_reactions(post, emojis), post.created_at)
        if best_key is None or key > best_key:
            best = post
            best_key = key
    return best


def _flavor_best(posts: list[ScoredPost]) -> tuple[ScoredPost, str] | None:
    """Score each off-core emoji on its own count, never the sum of a post's off-core reactions, so a
    card that collected a scattering of one-offs cannot beat one the room tagged with a single fitting
    emoji. Returns the winning post and the emoji that won it."""
    best: ScoredPost | None = None
    best_emoji: str | None = None
    best_key: tuple[int, int, datetime] | None = None
    for post in posts:
        for emoji, count in post.reactions.items():
            if emoji in CORE_EMOJIS or count <= 0:
                continue
            key = (count, _extra_reactions(post, (emoji,)), post.created_at)
            if best_key is None or key > best_key:
                best = post
                best_emoji = emoji
                best_key = key
    if best is None:
        return None
    return best, best_emoji


def _recounts(post: ScoredPost, primary: tuple[str, ...]) -> tuple[tuple[str, int], ...]:
    primary_counts = [(emoji, post.reactions[emoji]) for emoji in primary if post.reactions.get(emoji, 0) > 0]
    rest = [(emoji, count) for emoji, count in post.reactions.items() if emoji not in primary and count > 0]
    rest.sort(key=lambda item: item[1], reverse=True)
    return tuple(primary_counts + rest)


def _winner_from_post(post: ScoredPost, recounts: tuple[tuple[str, int], ...]) -> AwardWinner:
    return AwardWinner(
        jump_url=post.jump_url,
        image_url=post.image_url,
        recounts=recounts,
        caption=_trim_caption(post.content),
        author=post.author,
    )


def _extra_reactions(post: ScoredPost, category_emojis: tuple[str, ...]) -> int:
    return sum(count for emoji, count in post.reactions.items() if emoji not in category_emojis)


def _trim_caption(content: str) -> str | None:
    caption = " ".join(content.split())
    if not caption:
        return None
    if len(caption) > CAPTION_MAX_CHARS:
        caption = caption[:CAPTION_MAX_CHARS].rstrip() + "…"
    return caption


async def _collect_posts(channels: list[discord.TextChannel], window: PreviewWindow) -> list[ScoredPost]:
    start = datetime.combine(window.start_date, time.min, tzinfo=COMMUNITY_TZ)
    end = datetime.combine(window.end_date + timedelta(days=1), time.min, tzinfo=COMMUNITY_TZ)
    posts: list[ScoredPost] = []
    for channel in channels:
        async for message in channel.history(after=start, before=end, limit=None):
            image_url = first_image_url(message, include_embeds=True)
            if image_url is None:
                continue
            reactions: dict[str, int] = {}
            for reaction in message.reactions:
                if not _emoji_available(reaction.emoji, channel.guild):
                    continue
                key = _normalize_emoji(reaction.emoji)
                reactions[key] = reactions.get(key, 0) + reaction.count
            posts.append(ScoredPost(
                jump_url=message.jump_url,
                image_url=image_url,
                content=message.content,
                author=message.author.display_name,
                created_at=message.created_at,
                reactions=reactions,
            ))
    log.info(f"collected {len(posts)} preview season image posts across {len(channels)} channels")
    return posts


def _emoji_available(emoji: discord.PartialEmoji | discord.Emoji | str, guild: discord.Guild) -> bool:
    if isinstance(emoji, str):
        return True
    emoji_id = getattr(emoji, "id", None)
    return any(guild_emoji.id == emoji_id for guild_emoji in guild.emojis)


def _normalize_emoji(emoji: discord.PartialEmoji | discord.Emoji | str) -> str:
    """Skin tone variants collapse onto the bare emoji, so a \ud83d\udc4d\ud83c\udffb vote lands on
    the \ud83d\udc4d tally instead of splitting off as its own one-off reaction."""
    return str(emoji).replace("\ufe0f", "").translate(str.maketrans(SKIN_TONE_MODIFIERS))


def window_label(window: PreviewWindow) -> str:
    if window.start_date.month == window.end_date.month:
        return f"{_day_label(window.start_date)} – {window.end_date.day}"
    return f"{_day_label(window.start_date)} – {_day_label(window.end_date)}"


def _day_label(day: date) -> str:
    return f"{day:%B} {day.day}"


def channel_label(channels: list[discord.TextChannel]) -> str:
    return " & ".join(channel.mention for channel in channels)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PreviewSeasonAwards(bot))
