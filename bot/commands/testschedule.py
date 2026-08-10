"""Owner-only `!test` triggers for the pod-draft scheduler, each reusing the production path.

`reminders` posts every pod-chat reminder surface into the pod-draft-chat channel at once: the
recruiting nudge across its states, the launcher slot nudge and fire ping, and each fired-record
variant. `underfill`, `pollnudge`, `firenudge` and `overflow` render those same surfaces one at a time
in the current channel, with arguments for targeted checks. `cardformat` renders the scheduled card
with a mixed sample roster to eyeball the format split, or any set or cube passed to it.
`reminder` renders the roster reminder embed and `tables` renders the roster card at each shape its
columns can take. `rally` renders every `!pod` rally state, which the live command cannot show without a
Draftmancer lobby to stand up.
`rolegrant`
posts the auto-grant announcement embed so its look can be checked. The scheduled RSVP card is
exercised through `!test rsvp`.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import discord
from discord.ext import commands

from bot.commands.pod_rsvp import build_rsvp_embed
from bot.commands.test_group import HALL_OF_FAME, test_group
from bot.config import settings
from bot.services import pod_rally
from bot.services.ping_roles import PING_ROLES, build_grant_embed
from bot.services.pod_confirm import Attendance, card_tables
from bot.services.pod_join_button import build_join_view
from bot.services.pod_launch import ondemand_event_name_sync
from bot.services.pod_reminder_copy import SLOT_FIRE_PING
from bot.services.pod_roles import find_role
from bot.services.pod_schedule import (
    SCHEDULE_TZ,
    build_recruiting_message,
    build_underfill_fired_message,
    slots_for_week,
)
from bot.services import pod_format
from bot.services import pod_format_interest as fi
from bot.services.pod_signals import RSVP_MAYBE, RSVP_YES, slot_role_name_for_event_time
from bot.sets import active_set_code
from bot.tasks.pod_draft_reminder import (
    ROSTER_REMINDER_LEAD_MIN,
    build_lobby_open_body,
    build_roster_embed,
    build_table_plan_embed,
)


async def setup(bot: commands.Bot) -> None:
    @test_group.command(name="underfill")
    @commands.is_owner()
    async def test_underfill(ctx: commands.Context, yes_count: int = 5) -> None:
        """Owner-only. Post a sample underfill nudge in this channel — no DB or sesh lookup."""
        name = ctx.channel.name if isinstance(ctx.channel, discord.Thread) else "Sample Pod Draft - Jun 25"
        body = build_recruiting_message(
            name, yes_count, settings.pod_signal_fire_threshold, settings.pod_draft_target_players,
            _next_slot(), ctx.message.jump_url,
        )
        await ctx.send(body, allowed_mentions=discord.AllowedMentions.none())

    @test_group.command(name="pollnudge")
    @commands.is_owner()
    async def test_pollnudge(ctx: commands.Context) -> None:
        """Owner-only. Post a sample launcher-slot nudge in this channel — no DB or signals lookup."""
        slot = _next_slot()
        name = ondemand_event_name_sync(active_set_code(), slot)
        threshold = settings.pod_signal_fire_threshold
        body = build_recruiting_message(
            name, threshold - 1, threshold, settings.pod_draft_target_players, slot, ctx.message.jump_url,
        )
        await ctx.send(body, allowed_mentions=discord.AllowedMentions.none())

    @test_group.command(name="firenudge")
    @commands.is_owner()
    async def test_firenudge(ctx: commands.Context) -> None:
        """Owner-only. Post the launcher-slot fire ping for the next slot, so its wording can be checked
        without waiting for a slot to graduate near game time. Does not actually ping the role."""
        slot = _next_slot()
        role = find_role(ctx.guild, slot_role_name_for_event_time(slot) or "") if ctx.guild else None
        mention = role.mention if role is not None else "@Early Pod"
        body = SLOT_FIRE_PING.format(unix=int(slot.timestamp()), mention=mention)
        await ctx.send(body, allowed_mentions=discord.AllowedMentions.none())

    @test_group.command(name="overflow")
    @commands.is_owner()
    async def test_overflow(ctx: commands.Context) -> None:
        """Owner-only. Render the live second-table nudge through the production builder, with sample
        counts at the trigger boundary (10 Yes + 6 Maybe = 16) three hours out."""
        event_time = datetime.now(SCHEDULE_TZ) + timedelta(hours=3)
        body = build_recruiting_message(
            "MSH Jul 21 Early Pod", 10, settings.pod_signal_fire_threshold,
            settings.pod_draft_target_players, event_time, ctx.message.jump_url, maybe_count=6,
        )
        await ctx.send(body, allowed_mentions=discord.AllowedMentions.none())

    @test_group.command(name="reminders")
    @commands.is_owner()
    async def test_reminders(ctx: commands.Context, set_code: str = "") -> None:
        """Owner-only. Post the whole pod reminder timeline in this channel, in the order a pod hits it,
        each message through its production builder. Reviews the voice across every reminder surface in
        one place. Each preview carries a small subtext label; none of them ping. `set_code` names the
        pod after another format, so a glyph of any width can be read against the words next to it."""
        code = pod_format.resolve_format_code(set_code)
        if code is None:
            await ctx.send(f"`{set_code}` is not a registered set or cube")
            return
        await ctx.send("-# Pod reminder timeline. Constants live in `bot/services/pod_reminder_copy.py`")
        for label, body, embed in _reminder_timeline(ctx, code):
            await ctx.send(
                content=f"-# {label}\n{body}" if body else f"-# {label}",
                embed=embed, allowed_mentions=discord.AllowedMentions.none(),
            )

    @test_group.command(name="rally")
    @commands.is_owner()
    async def test_rally(ctx: commands.Context) -> None:
        """Owner-only. Post every `!pod` rally state in this channel through the production builder, so
        the copy can be read without a live Draftmancer lobby to stand up. The Join Draft button rides on
        the state that carries one; its session is a fixture, so the link it hands back is dead."""
        await ctx.send("-# `!pod` rally states. Constants live in `bot/services/pod_reminder_copy.py`")
        thread = ctx.message.jump_url
        for label, target in _rally_states(thread):
            await ctx.send(
                f"-# {label}\n{pod_rally.build_rally_line(target)}",
                view=build_join_view(target.session_id) if target.session_id else None,
                suppress_embeds=True, allowed_mentions=discord.AllowedMentions.none(),
            )

    @test_group.command(name="cardformat")
    @commands.is_owner()
    async def test_cardformat(ctx: commands.Context, set_code: str = "") -> None:
        """Owner-only. Post the scheduled RSVP card through the production builder with a mixed sample
        roster, so the live format-split layout can be eyeballed. `set_code` renders another format's
        card: a cube shows the cube-list line and plain roster columns, matching a format-locked pod."""
        code = pod_format.resolve_format_code(set_code)
        if code is None:
            await ctx.send(f"`{set_code}` is not a registered set or cube")
            return
        event_time = datetime.now(SCHEDULE_TZ) + timedelta(hours=1)
        names = iter(HALL_OF_FAME)
        yes_interests = ((fi.LATEST,), (fi.LATEST, fi.FLASHBACK), (fi.FLASHBACK,), (fi.LATEST,), (), (fi.FLASHBACK,))
        maybe_interests = ((fi.LATEST, fi.FLASHBACK), (fi.FLASHBACK,), (fi.LATEST,))
        roster_interests = {
            RSVP_YES: [(next(names), codes) for codes in yes_interests],
            RSVP_MAYBE: [(next(names), codes) for codes in maybe_interests],
        }
        rosters = {state: [name for name, _ in members] for state, members in roster_interests.items()}
        embed = build_rsvp_embed(
            ondemand_event_name_sync(code, event_time), event_time, rosters, set_code=code,
            roster_interests=None if pod_format.is_custom(code) else roster_interests,
        )
        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @test_group.command(name="reminder")
    @commands.is_owner()
    async def test_reminder(ctx: commands.Context) -> None:
        """Owner-only. Post a sample roster reminder embed in this channel — no DB or sesh lookup."""
        name = ctx.channel.name if isinstance(ctx.channel, discord.Thread) else "Sample Pod Draft - Jun 25"
        starts_at = datetime.now(SCHEDULE_TZ) + timedelta(minutes=ROSTER_REMINDER_LEAD_MIN)
        yes_interests = ((fi.LATEST,), (fi.FLASHBACK,), (fi.LATEST, fi.FLASHBACK), (fi.LATEST,), ())
        maybe_interests = ((fi.FLASHBACK,), (fi.LATEST,))
        names = iter(HALL_OF_FAME)
        roster_interests = {
            RSVP_YES: [(next(names), codes) for codes in yes_interests],
            RSVP_MAYBE: [(next(names), codes) for codes in maybe_interests],
        }
        rosters = {state: [name for name, _ in members] for state, members in roster_interests.items()}
        embed = build_roster_embed(name, starts_at, rosters, roster_interests)
        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @test_group.command(name="tables")
    @commands.is_owner()
    async def test_tables(ctx: commands.Context) -> None:
        """Owner-only. Post the roster card at the attendance shapes that change its columns — one table,
        a pod that splits in two, and the eleven that seats ten and leaves a player waiting. Each carries a
        decline, since that column is the one no plan ever seats. Render-only: no DB, event, or buttons."""
        starts_at = datetime.now(SCHEDULE_TZ) + timedelta(minutes=ROSTER_REMINDER_LEAD_MIN)
        for name, attendance in _table_plan_shapes():
            plan, seat_pending = card_tables(attendance)
            embed = build_table_plan_embed(name, starts_at, attendance, plan, seat_pending)
            await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @test_group.command(name="rolegrant")
    @commands.is_owner()
    async def test_rolegrant(ctx: commands.Context) -> None:
        """Owner-only. Post the auto-grant announcement embed for each auto-granted role, to eyeball it."""
        guild = ctx.guild or ctx.bot.get_guild(settings.discord_guild_id)
        if guild is None:
            await ctx.send("No guild available to resolve roles")
            return
        posted = 0
        for spec in PING_ROLES:
            if not spec.auto_grant:
                continue
            role = find_role(guild, spec.name)
            if role is None:
                await ctx.send(f"No `{spec.name}` role on **{guild.name}**, create it first")
                continue
            embed = build_grant_embed(ctx.author.mention, role, spec)
            await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            posted += 1
        if posted == 0:
            await ctx.send("No auto-grant roles to preview")


def _table_plan_shapes() -> tuple[tuple[str, Attendance], ...]:
    """(pod name, attendance) for each layout the roster card can take. Confirmed and Yes fill the table
    columns, Maybe and No sit on a row of their own below them."""
    return (
        ("Quiet Pod", Attendance(
            confirmed=HALL_OF_FAME[0:4], yes=HALL_OF_FAME[4:6],
            maybe=HALL_OF_FAME[6:7], declined=HALL_OF_FAME[7:8],
        )),
        ("Split Pod", Attendance(
            confirmed=HALL_OF_FAME[0:9], yes=HALL_OF_FAME[9:13],
            maybe=HALL_OF_FAME[13:15], declined=HALL_OF_FAME[15:18],
        )),
        ("11th Player Pod", Attendance(
            confirmed=HALL_OF_FAME[0:11], declined=HALL_OF_FAME[11:12],
        )),
    )


def _rally_states(thread_url: str) -> list[tuple[str, pod_rally.RallyTarget]]:
    """Every shape `!pod` can post, in the order a pod passes through them. The lobby states carry a
    session so the Join Draft button renders; the rest have none, which is what the live command sees."""
    name = "MSH Aug 1 Late Pod"
    session = "msh-late-preview"
    slot = _next_slot()
    lobby = [
        ("Lobby open, nobody has arrived", 0),
        ("Lobby open, one arrival", 1),
        ("Lobby open, below the fire threshold", 5),
        ("Lobby open, one seat short", 7),
    ]
    states = [
        (label, pod_rally.RallyTarget(
            pod_rally.KIND_LOBBY, name, thread_url, seated=seated, session_id=session))
        for label, seated in lobby
    ]
    states.append(("Gathering, below the fire threshold", pod_rally.RallyTarget(
        pod_rally.KIND_GATHERING, name, thread_url, yes=5, event_time=slot)))
    states.append(("Gathering, short of a full table", pod_rally.RallyTarget(
        pod_rally.KIND_GATHERING, name, thread_url, yes=6, maybe=2, event_time=slot)))
    states.append(("Open queue, no start time", pod_rally.RallyTarget(
        pod_rally.KIND_QUEUE_SIGNAL, "MSH Aug 1 Pod Draft Queue", thread_url, yes=3)))
    states.append(("Second table collecting claims", pod_rally.RallyTarget(
        pod_rally.KIND_TABLE, f"{name} - Table 2", thread_url, yes=2)))
    states.append(("Draft already running", pod_rally.RallyTarget(
        pod_rally.KIND_STARTED, name, thread_url, seated=8)))
    return states


def _next_slot() -> datetime:
    now = datetime.now(SCHEDULE_TZ)
    monday = now.date() - timedelta(days=now.weekday())
    candidates = slots_for_week(monday) + slots_for_week(monday + timedelta(days=7))
    for slot in candidates:
        if slot > now:
            return slot
    return candidates[-1]


def _reminder_timeline(
    ctx: commands.Context, set_code: str,
) -> list[tuple[str, str | None, discord.Embed | None]]:
    """The pod reminder timeline in lifecycle order, each entry built through its production builder with
    sample numbers, as (label, body, embed). The pod's status message across its states, the launcher
    slot fire ping, the roster reminder embed, the lobby-open post, and the fired record. Each label
    names the constant(s) in pod_reminder_copy.py so the copy can be edited straight from the preview."""
    slot = _next_slot()
    unix = int(slot.timestamp())
    floor = settings.pod_signal_fire_threshold
    target = settings.pod_draft_target_players
    url = ctx.message.jump_url
    pod_name = ondemand_event_name_sync(set_code, slot)

    role = find_role(ctx.guild, slot_role_name_for_event_time(slot) or "") if ctx.guild else None
    mention = role.mention if role is not None else "@Early Pod"
    yes = list(HALL_OF_FAME[:5])
    maybe = list(HALL_OF_FAME[5:7])
    yes_interests = ((fi.LATEST,), (fi.FLASHBACK,), (fi.LATEST, fi.FLASHBACK), (fi.LATEST,), ())
    maybe_interests = ((fi.FLASHBACK,), (fi.LATEST,))
    roster_interests = {
        RSVP_YES: list(zip(yes, yes_interests)),
        RSVP_MAYBE: list(zip(maybe, maybe_interests)),
    }
    rosters = {RSVP_YES: yes, RSVP_MAYBE: maybe}
    roster_embed = build_roster_embed(pod_name, slot, rosters, roster_interests)

    def text(const: str, desc: str, body: str) -> tuple[str, str | None, discord.Embed | None]:
        return (f"`{const}` ({desc})", body, None)

    return [
        text("RECRUITING_BELOW_FLOOR", "short of the floor",
             build_recruiting_message(pod_name, floor - 2, floor, target, slot, url)),
        text("RECRUITING_BELOW_FLOOR", "one short of the floor",
             build_recruiting_message(pod_name, floor - 1, floor, target, slot, url)),
        text("RECRUITING_SHORT", "the draft is on, short of the aim",
             build_recruiting_message(pod_name, floor, floor, target, slot, url)),
        text("RECRUITING_READY", "full pod",
             build_recruiting_message(pod_name, target, floor, target, slot, url, maybe_count=2)),
        text("RECRUITING_READY + RECRUITING_SECOND_TABLE", "second table",
             build_recruiting_message(pod_name, 10, floor, target, slot, url, maybe_count=6)),
        text("SLOT_FIRE_PING", "launcher slot fires", SLOT_FIRE_PING.format(unix=unix, mention=mention)),
        ("`ROSTER_REMINDER_TITLE` + `ROSTER_REMINDER_LINE` (T-60 reminder)", None, roster_embed),
        text("LOBBY_OPEN + LOBBY_OPEN_HEADLINE", "Draftmancer link posted",
             build_lobby_open_body("https://draftmancer.com/?session=Sample", "")),
        text("DRAFT_STARTED", "Team Draft shows through the linked thread",
             build_underfill_fired_message(pod_name, 8, url)),
    ]

