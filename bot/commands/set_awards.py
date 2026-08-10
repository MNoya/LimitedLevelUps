"""Builder for the end-of-set Set Awards ceremony — Components V2, mirrors the preview season awards layout.

One Section per award with the winner's thumbnail, the winner line, and a runner-up subtext.
Presentation is decoupled from data: `build_set_awards_view` renders a `SetAwardsData`, so
`!test setawards` feeds fixture data through the same builder.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date
from zoneinfo import ZoneInfo

import discord
from discord import app_commands, ui
from discord.ext import commands
from sqlalchemy import select

from bot import audit, emojis
from bot.commands import descriptions as desc
from bot.database import SessionLocal
from bot.discord_helpers import NBSP, ZWSP
from bot.models import MagicSet, Player
from bot.services import ping_roles, set_awards as awards_svc
from bot.services.format_schedule import awards_posted_set

log = logging.getLogger(__name__)
COMMUNITY_TZ = ZoneInfo("America/New_York")
MSG_NOT_ON_BOARD = (
    "You're not on the leaderboard yet. "
    "Run `/join` to share your stats, then come back and see how you did {love}"
)
MSG_JOINED_NO_EVENTS = (
    "You're on the leaderboard, but no {set} drafts are showing for you this set. "
    "If this is a mistake, contact an Admin"
)

GAP = NBSP * 2
SUBTEXT_START = f"-# {ZWSP}"
MISS_START = f"{SUBTEXT_START}{GAP}"
MSG_NO_AWARDS_YET = "No Set Awards have been posted yet. They run the morning before a new set releases"
SITE_LEADERBOARD_URL = "https://limitedlevelups.com/leaderboard"
LEADERBOARD_NOTE = f"`/join` to enter · [limitedlevelups.com/leaderboard]({SITE_LEADERBOARD_URL})"


@dataclass(frozen=True)
class AwardEntrant:
    name: str
    detail: str


@dataclass(frozen=True)
class AwardSpec:
    """Shared definition of an award: its copy, glyph, and ceremony order. The test fixture and the
    live computation both attach winner data to these, so names/taglines/emoji live in one place."""
    key: str
    emoji: str
    name: str
    tagline: str
    custom_emoji: str | None = None
    connector: str = "with"
    you_verb: str = ""
    miss: str = ""

    def display_emoji(self) -> str:
        if self.custom_emoji:
            return emojis.get(self.custom_emoji) or self.emoji
        return self.emoji


@dataclass(frozen=True)
class SetAward:
    spec: AwardSpec
    winner: AwardEntrant
    thumbnail_url: str
    runner_ups: tuple[AwardEntrant, ...] = ()


@dataclass(frozen=True)
class SetAwardsData:
    set_code: str
    window_label: str
    awards: tuple[SetAward, ...]


AWARD_SPECS: tuple[AwardSpec, ...] = (
    AwardSpec("first_striker", "⚔️", "First Striker", "First trophy of the set",
              connector="", you_verb="trophied",
              miss="No trophy this set"),
    AwardSpec("seize_the_day", "🔥", "Seize the Day", "Most trophies in 24 hours",
              connector="claimed", you_verb="claimed",
              miss="No multi-trophy day this set"),
    AwardSpec("climber", "🧗", "The Climber", "Fastest ladder grind in a single month",
              connector="-", you_verb="climbed from",
              miss="You didn't grind to Mythic this set"),
    AwardSpec("specialist", "🎯", "The Specialist", "Overperformed on one archetype",
              connector="-", you_verb="posted",
              miss="Not enough games on any one archetype"),
    AwardSpec("revel_in_riches", "📦", "Revel in Riches", "Most Arena Direct boxes won",
              custom_emoji="8000gems", you_verb="won",
              miss="No Arena Direct boxes this set"),
    AwardSpec("mvp", "🚀", "Most Valuable Pod-Drafter", "Most pod drafts played",
              you_verb="played",
              miss="No pod drafts this set"),
)


def build_set_awards_view(data: SetAwardsData) -> ui.LayoutView:
    view = ui.LayoutView(timeout=None)
    container = ui.Container(accent_colour=discord.Color.green())

    container.add_item(ui.TextDisplay(
        f"## 🏆 {data.set_code} Set Awards\n{SUBTEXT_START}{data.window_label} · {LEADERBOARD_NOTE}"
    ))
    container.add_item(ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small))

    for i, award in enumerate(data.awards):
        container.add_item(ui.Section(
            ui.TextDisplay(_award_text(award)),
            accessory=ui.Thumbnail(media=award.thumbnail_url),
        ))
        if i < len(data.awards) - 1:
            container.add_item(ui.Separator(visible=False, spacing=discord.SeparatorSpacing.small))

    view.add_item(container)
    view.add_item(_my_awards_action_row())
    return view


def _award_text(award: SetAward) -> str:
    spec = award.spec
    sep = f" {spec.connector} " if spec.connector else " "
    lines = [
        f"### {spec.display_emoji()} {spec.name}",
        f"{GAP}_{spec.tagline}_",
        f"{GAP}🥇 **{award.winner.name}**{sep}{award.winner.detail}",
    ]
    if award.runner_ups:
        runners = (GAP * 2).join(
            f"🥈 **{entrant.name}**{sep}{entrant.detail.replace('**', '')}"
            for entrant in award.runner_ups
        )
        lines.append(f"{GAP}{runners}")
    return "\n".join(lines)


def build_my_awards_view(
    set_code: str, ranked: dict, discord_id: str, extras: dict | None = None,
) -> ui.LayoutView:
    """Ephemeral per-player view: where the caller stands in each award race, plus personal-only
    fun streaks.

    Every category is shown: earned ones carry a rank badge and the detail line, ones the player
    didn't place in get a muted reason so the board reads as a full scorecard, not a filtered one.
    """
    view = ui.LayoutView()
    container = ui.Container(accent_colour=discord.Color.green())
    container.add_item(ui.TextDisplay(f"## 🏆 Your {set_code} Set Awards"))
    container.add_item(ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small))

    for spec in AWARD_SPECS:
        rank, _total, mine = _standing(ranked.get(spec.key, []), discord_id)
        container.add_item(ui.TextDisplay(_my_award_line(spec, rank, mine)))

    container.add_item(ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small))
    for line in _fun_lines(extras or {}):
        container.add_item(ui.TextDisplay(line))

    view.add_item(container)
    return view


def _my_award_line(spec: AwardSpec, rank: int | None, mine: object) -> str:
    if mine is None:
        return f"### {spec.display_emoji()} {spec.name}\n{MISS_START}{spec.miss}"
    verb = f" {spec.you_verb}" if spec.you_verb else ""
    heading = f"### {spec.display_emoji()} {spec.name} {_rank_badge(rank)}"
    return f"{heading}\n{GAP}You{verb} {mine.detail}"


def _fun_lines(extras: dict) -> list[str]:
    return [
        _trophy_streak_line(extras),
        _merchant_line(extras),
        _heartbreakers_line(extras),
        _cold_run_line(extras),
    ]


def _trophy_streak_line(extras: dict) -> str:
    streak = extras.get("trophy_streak", 0)
    if streak < 2:
        return f"### 🔥 Trophy Streak\n{MISS_START}No back-to-back trophies this set"
    badge = _rank_badge(extras.get("trophy_streak_rank", 1))
    span = _span_phrase(extras.get("trophy_span"))
    return f"### 🔥 Trophy Streak {badge}\n{GAP}You scored **{streak} trophies** in a row{span}"


def _merchant_line(extras: dict) -> str:
    streak = extras.get("merchant_streak", 0)
    tail = _out_of_events(extras.get("merchant_events", 0))
    if streak < 3:
        plural = "" if streak == 1 else "s"
        reason = "No 2-1 streak in Trad" if streak == 0 else f"Only {_spell(streak)} 2-1{plural} in a row in Trad"
        return f"### 🪙 The Merchant\n{MISS_START}**Safe!** {reason}{tail}"
    badge = _rank_badge(extras.get("merchant_streak_rank", 1))
    return f"### 🪙 The Merchant {badge}\n{GAP}You went 2-1 **{_spell(streak)}** times in a row in Trad{tail}"


def _heartbreakers_line(extras: dict) -> str:
    """Ranked on how often a Premier draft ended 6-3, so the floor doubles as the qualifying bar: too few
    Premier drafts and the rate says nothing, which reads as safe rather than as a miss."""
    count = extras.get("heartbreakers", 0)
    events = extras.get("heartbreakers_events", 0)
    if events < awards_svc.HEARTBREAKERS_MIN_EVENTS:
        return f"### 🥀 Heartbreakers\n{MISS_START}**Safe!** {_too_few_premier(events)}"
    tail = _out_of_events(events)
    if count == 0:
        return f"### 🥀 Heartbreakers\n{MISS_START}**Safe!** No Premier 6-3 finishes{tail}"
    badge = _rank_badge(extras.get("heartbreakers_rank", 1))
    rate = extras.get("heartbreakers_rate", 0.0)
    return f"### 🥀 Heartbreakers {badge}\n{GAP}You went 6-3 in Premier **{rate:.0%}** of the time{tail}"


def _too_few_premier(events: int) -> str:
    if events == 0:
        return "No Premier drafts this set"
    plural = "" if events == 1 else "s"
    return f"Only {_spell(events)} Premier draft{plural} this set"


def _out_of_events(n: int) -> str:
    return f", out of {n} event{'' if n == 1 else 's'}"


def _cold_run_line(extras: dict) -> str:
    run = extras.get("cold_run", 0)
    if run < 3:
        if run == 0:
            reason = "No cold Premier streak"
        else:
            reason = f"Only {_spell(run)} Premier drafts in a row without a 4+ win"
        return f"### 🥶 Cold Run\n{MISS_START}**Safe!** {reason}"
    badge = _rank_badge(extras.get("cold_run_rank", 1))
    return f"### 🥶 Cold Run {badge}\n{GAP}You went **{run}** Premier drafts without a 4+ win finish"


def _span_phrase(span: tuple | None) -> str:
    if not span or span[0] is None or span[1] is None:
        return ""
    start = span[0].astimezone(COMMUNITY_TZ)
    end = span[1].astimezone(COMMUNITY_TZ)
    if start.date() == end.date():
        return f" on {start:%b} {start.day}"
    return f" between {start:%b} {start.day} and {end:%b} {end.day}"


def _standing(candidates: list, discord_id: str) -> tuple[int | None, int, object]:
    for index, cand in enumerate(candidates):
        if cand.discord_id == discord_id:
            return index + 1, len(candidates), cand
    return None, len(candidates), None


def _rank_badge(rank: int) -> str:
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    return medals.get(rank, f"- #{rank}")


_ONES = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen",
)
_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")


def _spell(n: int) -> str:
    if 0 <= n < 20:
        return _ONES[n]
    if 20 <= n < 100:
        tens, ones = divmod(n, 10)
        return _TENS[tens] + (f"-{_ONES[ones]}" if ones else "")
    return str(n)


class SetAwards(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="set-awards", description=desc.SET_AWARDS)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def set_awards(self, interaction: discord.Interaction) -> None:
        """Everyone's own scorecard for the last set whose ceremony ran, which is the same view the
        My Awards button gives. Open to every player, so it answers ephemerally and posts nothing."""
        await _respond_posted_set_awards(interaction)


async def run_set_awards_ceremony(
    channel: discord.abc.Messageable, guild: discord.Guild | None, code: str, seed, *, dry: bool,
) -> int | None:
    """Post the whole ceremony into ``channel`` in one message. Only a live post outside a thread pings
    its winners, and those mentions have to ride the initial send, because Discord raises no notification
    for a mention introduced by editing a message. Returns the award count, or None when nothing could be
    computed. Shared by ``/set-awards`` and the scheduled day-before ceremony so both render one way.

    ``dry`` leaves the world untouched: no ping, no role handover, and no pin, the last because the pin is
    the marker next set's warning links back to as that set's ceremony. It also renders plain names in
    place of mentions, because a suppressed mention carries no user data and any viewer without that
    member cached reads ``@unknown-user``. It has no default and is keyword-only on purpose:
    ``/set-awards`` defaults to a dry run while the scheduled ceremony must always be live, so every
    caller states which one it wants.
    """
    in_thread = isinstance(channel, discord.Thread)
    mention = not in_thread and not dry
    with SessionLocal() as session:
        mset = session.execute(select(MagicSet).where(MagicSet.code == code)).scalar_one_or_none()
        if mset is None:
            return None
        ranked = awards_svc.compute_db_awards(session, mset, seed)

    winners, runners = awards_svc.assign(ranked)
    data = build_data(code, seed, winners, runners, guild, mention=mention)
    if not data.awards:
        return None

    recipients = _award_recipients(winners, runners)
    if mention:
        allowed = discord.AllowedMentions(users=[discord.Object(id=uid) for uid in _ping_ids(recipients)])
    else:
        allowed = discord.AllowedMentions.none()
    ceremony = await channel.send(view=build_set_awards_view(data), allowed_mentions=allowed)
    if not dry:
        await _pin_ceremony(ceremony)
        await ping_roles.apply_award_roles(guild, recipients)

    audit.event(
        "set_awards_posted", set_code=code, awards=len(data.awards),
        in_thread=in_thread, dry=dry, channel_id=str(channel.id),
    )
    log.info(f"set awards posted for {code}: {len(data.awards)} awards (thread={in_thread}, dry={dry})")
    return len(data.awards)


async def _pin_ceremony(ceremony: discord.Message) -> None:
    """Pin the ceremony so it's the durable marker the next set's warning links back to. A full pin
    board or missing Manage Messages just leaves it unpinned — the link is a nicety, not load-bearing."""
    try:
        await ceremony.pin()
    except discord.HTTPException:
        log.warning("set awards: could not pin the ceremony", exc_info=True)


def _window_label(seed) -> str:
    today = date.today()
    end = min(seed.end_date, today) if seed.end_date else today
    return f"{seed.start_date:%b} {seed.start_date.day} - {end:%b} {end.day}"


def build_data(
    code: str, seed, winners: dict, runners: dict, guild: discord.Guild | None, mention: bool = True,
) -> SetAwardsData:
    awards = []
    for spec in AWARD_SPECS:
        winner = winners.get(spec.key)
        if winner is None:
            continue
        awards.append(SetAward(
            spec=spec,
            winner=_entrant(winner, mention, guild),
            thumbnail_url=winner.avatar_url or awards_svc.avatar_url(None, None),
            runner_ups=tuple(_runner_entrant(spec, r, winner, mention, guild) for r in runners.get(spec.key, [])),
        ))
    return SetAwardsData(code, _window_label(seed), tuple(awards))


def _entrant(cand: "awards_svc.AwardCandidate", mention: bool, guild: discord.Guild | None) -> AwardEntrant:
    return AwardEntrant(name=_entrant_name(cand, mention, guild), detail=cand.ceremony_detail or cand.detail)


def _entrant_name(cand: "awards_svc.AwardCandidate", mention: bool, guild: discord.Guild | None) -> str:
    """Mention only members of the posting guild; everyone else falls back to their display name so a
    cross-guild winner (or a non-member id) never renders as `@unknown-user`."""
    if mention and guild is not None and cand.discord_id and cand.discord_id.isdigit():
        if guild.get_member(int(cand.discord_id)) is not None:
            return f"<@{cand.discord_id}>"
    return cand.display_name


def _runner_entrant(
    spec: AwardSpec, cand: "awards_svc.AwardCandidate", winner: "awards_svc.AwardCandidate",
    mention: bool, guild: discord.Guild | None,
) -> AwardEntrant:
    name = _entrant_name(cand, mention, guild)
    if spec.key == "specialist" and cand.archetype is not None and cand.archetype == winner.archetype:
        detail = (cand.ceremony_detail or cand.detail).split(awards_svc.SPECIALIST_FIELD_SEP)[0]
    else:
        detail = cand.ceremony_detail or cand.detail
    return AwardEntrant(name=name, detail=detail)


def _award_recipients(winners: dict, runners: dict) -> dict[str, list[str]]:
    """Per award, everyone the card names: the winner, then the runner-ups printed beside them. Keyed off
    ``winners``, which is what makes a category nobody won absent here — `build_data` leaves that award off
    the card, so its role holders must be left alone rather than stripped for an unearned award."""
    recipients: dict[str, list[str]] = {}
    for key, winner in winners.items():
        ids = []
        for cand in (winner, *runners.get(key, ())):
            if cand.discord_id is not None:
                ids.append(cand.discord_id)
        recipients[key] = ids
    return recipients


def _ping_ids(recipients: dict[str, list[str]]) -> list[int]:
    """Every id the card mentions, so the allow list can never fall short of what the text renders."""
    ids: list[int] = []
    for user_ids in recipients.values():
        for user_id in user_ids:
            if user_id.isdigit() and int(user_id) not in ids:
                ids.append(int(user_id))
    return ids


MY_AWARDS_BUTTON_ID = "set_awards:my"


class MyAwardsButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(
            label="My Awards", style=discord.ButtonStyle.success,
            emoji="🏆", custom_id=MY_AWARDS_BUTTON_ID,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await _respond_posted_set_awards(interaction)


async def _respond_posted_set_awards(interaction: discord.Interaction) -> None:
    """The caller's scorecard for the most recently posted ceremony, shared by ``/set-awards`` and the
    My Awards button so the two always name the same set. Reading the posted set rather than the active one
    is what keeps a card from answering for a set whose awards have not happened: the button sits on a
    pinned ceremony that outlives its own set by weeks."""
    seed = awards_posted_set()
    if seed is None:
        await interaction.response.send_message(MSG_NO_AWARDS_YET, ephemeral=True)
        return
    await _respond_my_awards(interaction, seed.code, seed)


def _my_awards_action_row() -> ui.ActionRow:
    row = ui.ActionRow()
    row.add_item(MyAwardsButton())
    return row


def persistent_my_awards_view() -> ui.LayoutView:
    view = ui.LayoutView(timeout=None)
    view.add_item(_my_awards_action_row())
    return view


SET_NOT_IN_DATABASE = object()


async def _respond_my_awards(interaction: discord.Interaction, code: str, seed) -> None:
    await interaction.response.defer(ephemeral=True)
    discord_id = str(interaction.user.id)
    result = await asyncio.to_thread(_my_awards_payload, code, seed, discord_id)
    if result is SET_NOT_IN_DATABASE:
        await interaction.followup.send(f"Set {code} is not in the database", ephemeral=True)
        return
    if result is None:
        await _send_no_standing(interaction, code, discord_id)
        return
    ranked, mine, fun_values = result
    extras = awards_svc.personal_extras(mine)
    extras.update(awards_svc.fun_stat_ranks(mine, fun_values))
    view = build_my_awards_view(code, ranked, discord_id, extras)
    await interaction.followup.send(view=view, ephemeral=True)


def _my_awards_payload(code: str, seed, discord_id: str):
    """`SET_NOT_IN_DATABASE` separates a set the ceremony ran for but nothing seeded from a player who
    simply has no standing in it, which read the same as a bare None."""
    with SessionLocal() as session:
        mset = session.execute(select(MagicSet).where(MagicSet.code == code)).scalar_one_or_none()
        if mset is None:
            return SET_NOT_IN_DATABASE
        return awards_svc.personal_payload(session, mset, seed, discord_id)


async def _send_no_standing(interaction: discord.Interaction, code: str, discord_id: str) -> None:
    """Distinguish a genuinely unjoined clicker (offer `/join`) from a joined player who simply has
    no draft events for this set (the awards payload drops them, but the `/join` CTA would mislead)."""
    joined = await asyncio.to_thread(_has_player_row, discord_id)
    if joined:
        await interaction.followup.send(MSG_JOINED_NO_EVENTS.format(set=code), ephemeral=True)
        return
    love = emojis.get("chordo_love") or "❤️"
    await interaction.followup.send(MSG_NOT_ON_BOARD.format(love=love), ephemeral=True)


def _has_player_row(discord_id: str) -> bool:
    with SessionLocal() as session:
        return session.execute(select(Player.id).where(Player.discord_id == discord_id)).first() is not None


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SetAwards(bot))
    bot.add_view(persistent_my_awards_view())
