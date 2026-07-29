"""Owner-only `!test` triggers for the on-demand pod signup surfaces.

`poll` posts a live daily launcher in this channel; `draft` posts a live /draft queue; `rsvp` posts a
live scheduled RSVP card. All reuse the production builders and persistent views and register real
signals, so clicking the buttons drives the real add / remove / fire path (a fire creates the thread
and Draftmancer lobby for real, and `rsvp` creates its thread, event, and timed jobs at post time).
Set POD_SIGNAL_FIRE_THRESHOLD low to reach a fire on your own.

`launcher` drives the whole surface for real: it stages a scheduled pod at the day's last slot so that
slot reflects as a committed jump-link with its Yes roster, leaving the other slots as live lazy
signals, then posts the live launcher. Everything routes through the production paths, so the preview
can't drift from what players see.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands

from bot.commands.pod_queue import (
    QUEUE_CLOSED_MANUAL,
    PodQueueView,
    queue_inactivity_close_reason,
    queue_role_mention,
)
from bot.commands.pod_rsvp import (
    CARD_STATUS_DRAFTING,
    CARD_STATUS_PLAYING,
    DraftedPlayer,
    build_rsvp_embed,
    post_scheduled_card,
    purge_native_events,
    refresh_scheduled_card,
)
from bot.commands.pod_table import offer_second_table
from bot.commands.test_group import HALL_OF_FAME, test_group
from sqlalchemy import delete, select

from bot.database import SessionLocal
from bot.models import PodDraftEvent, PodSignal, PodSignalMember
from bot.services import pod_format
from bot.services import pod_format_interest as fi
from bot.services import pod_format_schedule
from bot.services import pod_gathering
from bot.services import pod_launch
from bot.services.pod_deck_color import format_deck_color_emojis
from bot.services import pod_team
from bot.services.pod_team_board import TeamBoardMember
from bot.services.pod_draft_manager import set_event_pairing_mode
from bot.services.pod_tournament import build_replays_link_button
from bot.services.ping_roles import (
    PING_ROLES,
    QUEUE_GRANT_PING,
    build_grant_view,
    build_welcome_view,
    forget_welcome,
    slot_grant_ping,
    spec_named,
    strip_pod_roles,
)
from bot.services.pod_schedule import POD_QUEUE_ROLE_NAME
from bot.services.pod_signals import (
    KIND_POLL,
    RSVP_YES,
    SCHEDULE_TZ,
    STATUS_FIRED,
    STATUS_OPEN,
    bucket_for_lane,
    named_bucket_key,
    poll_buckets_for,
    slot_event_time,
)
from bot.services.pod_slot import pod_display_name
from bot.services.pod_team_vote import find_team_vote_card, rerender_gathering
from bot.sets import active_set_code
from bot.slug import slugify
from bot.tasks.pod_daily_poll import (
    PodPollView,
    build_play_again_prompt,
    build_poll_embed,
    close_launcher_for_date,
    post_launcher,
)
from bot.tasks.pod_thread_cleanup import delete_threads
from bot.tasks.pod_draft_reminder import fire_roster_reminder


log = logging.getLogger(__name__)


async def _show_welcome_preview(interaction: discord.Interaction, role_name: str) -> None:
    guild = interaction.guild
    spec = spec_named(role_name)
    role = discord.utils.get(guild.roles, name=role_name) if guild is not None else None
    ping = QUEUE_GRANT_PING if role_name == POD_QUEUE_ROLE_NAME else slot_grant_ping(spec)
    preview_role = role or _StubRole(role_name)
    await interaction.response.send_message(
        view=build_welcome_view(guild, interaction.user.mention),
        allowed_mentions=discord.AllowedMentions.none(),
    )
    linked = build_grant_view(preview_role, spec, ping=ping, arena_name="Tester#00000")
    unlinked = build_grant_view(preview_role, spec, ping=ping, arena_name=None)
    await _send_labeled_card(interaction, "**Returning, picks up a new slot (linked):**", linked)
    await _send_labeled_card(interaction, "**Returning, picks up a new slot (not linked):**", unlinked)


async def _send_labeled_card(
    interaction: discord.Interaction, label: str, card: discord.ui.LayoutView,
) -> None:
    """A Components V2 view can't ride with a `content` field, so the preview label posts as its own
    message ahead of the card."""
    await interaction.followup.send(label, allowed_mentions=discord.AllowedMentions.none())
    await interaction.followup.send(view=card, allowed_mentions=discord.AllowedMentions.none())


class _StubRole:
    """Stand-in for a slot role the test guild hasn't created, so the grant-card preview still renders
    with a name mention and the default accent."""

    def __init__(self, role_name: str) -> None:
        self.mention = f"@{role_name}"
        self.color = discord.Color.default()


class _WelcomePreviewButton(discord.ui.Button):
    def __init__(self, role_name: str) -> None:
        super().__init__(label=role_name, style=discord.ButtonStyle.secondary)
        self.role_name = role_name

    async def callback(self, interaction: discord.Interaction) -> None:
        await _show_welcome_preview(interaction, self.role_name)


class WelcomePreviewView(discord.ui.View):
    """Buttons that replay the first-pod welcome and role-grant a new drafter sees, addressed to
    whoever clicks — eyeball the copy without wiping pod history to trip first contact."""

    def __init__(self) -> None:
        super().__init__(timeout=None)
        for spec in PING_ROLES:
            if spec.auto_grant or spec.name == POD_QUEUE_ROLE_NAME:
                self.add_item(_WelcomePreviewButton(spec.name))


async def setup(bot: commands.Bot) -> None:
    @test_group.command(name="poll")
    @commands.is_owner()
    async def test_poll(ctx: commands.Context, *args: str) -> None:
        """Owner-only. Post a live daily launcher whose slots are still ahead — today if one remains,
        otherwise tomorrow — so the buttons are clickable and drive real signals. Prefills each named pod
        with fake signups, a couple of them on both formats of a slot, so the rosters and the flexible
        marker show. Args are order-free: `am` posts tomorrow so every pod is fresh and open like a morning
        post; `split` seeds five dedicated per format plus two on both, so one press has to split them into
        two full pods; a set or cube code is offered beside the latest set, so `poll SAMP` drives that
        format live without waiting for its date."""
        lowered = {arg.lower() for arg in args}
        now = datetime.now(SCHEDULE_TZ)
        if "am" in lowered:
            day = now.date() + timedelta(days=1)
        else:
            last_slot = slot_event_time(now.date(), poll_buckets_for(now.date())[-1].key)
            day = now.date() if last_slot is not None and last_slot > now else now.date() + timedelta(days=1)
        forced = [
            code for code in (
                pod_format.resolve_format_code(arg) if arg.lower() not in ("am", "split") else None
                for arg in args
            ) if code
        ]
        if forced:
            _force_formats(day, tuple(forced))
        message = await post_launcher(ctx.bot, ctx.channel, day)
        if message is None:
            return
        await asyncio.to_thread(_seed_poll_signups_sync, str(message.id), day, "split" in lowered)
        slots = await asyncio.to_thread(pod_launch.launcher_snapshot_sync, str(message.id), day)
        await message.edit(embed=build_poll_embed(slots, ctx.guild), view=PodPollView(slots, ctx.guild))

    @test_group.command(name="named")
    @commands.is_owner()
    async def test_named(ctx: commands.Context, *codes: str) -> None:
        """Owner-only. Post the rolling launcher with a second format named at each slot: every pod carries
        its own roster block under the real set or cube code, and every pod gets its own join button.

        One code applies to both slots (`named NEO`). Two set them per slot, and `-` means that slot offers
        only the latest set (`named PEASANT -`). No code at all is a latest-only day, which carries one pod
        per slot. Fixture slots through the production embed and view builders, so no signal exists behind
        the buttons."""
        day = datetime.now(SCHEDULE_TZ).date() + timedelta(days=1)
        buckets = poll_buckets_for(day)
        wanted = [code.strip().upper() for code in codes] or [""]
        if len(wanted) == 1:
            wanted *= len(buckets)
        slots = [
            slot
            for index, bucket in enumerate(buckets)
            for slot in _named_slots(bucket, slot_event_time(day, bucket.key), _named_arg(wanted, index))
        ]
        await ctx.send(embed=build_poll_embed(slots, ctx.guild), view=PodPollView(slots, ctx.guild))

    @test_group.command(name="lifecycle")
    @commands.is_owner()
    async def test_lifecycle(ctx: commands.Context, flashback: str = "PEASANT") -> None:
        """Owner-only. Post one board per pod lifecycle state so the difference is visible side by side:
        gathering with no thread, fired with a thread and still taking signups, one draft started, both
        started, and played. The points to check are the second one, where a fired pod must keep its full
        roster and put its thread link above the format it plays, and the third, where a pod that is
        drafting must not collapse the format beside it. Fixtures through the production embed builder, no
        signals."""
        other = flashback.strip().upper()
        day = datetime.now(SCHEDULE_TZ).date() + timedelta(days=1)
        buckets = poll_buckets_for(day)
        for label, state in _LIFECYCLE_STATES:
            slots = [
                slot
                for bucket in buckets
                for slot in _lifecycle_slots(
                    bucket, slot_event_time(day, bucket.key), other, state, str(ctx.channel.id))
            ]
            await ctx.send(f"**{label}**", embed=build_poll_embed(slots, ctx.guild))

    @test_group.command(name="rolling")
    @commands.is_owner()
    async def test_rolling(ctx: commands.Context) -> None:
        """Owner-only. Post the rolling launcher render across its situations as static previews from
        fixtures: a fresh morning board, one slot finished (Played over Next), the full 2x2 with both
        finished, a multi-table variant, a team draft, and the handoff (retired On This Day history plus the
        fresh next-day card) — plus the next-day Play Again prompt, whose button is live and joins the
        soonest open slot of that name. The embeds are fixtures: no signals, threads, or jobs. Reuses the
        production embed and view builders so the preview can't drift from what players see."""
        guild = ctx.guild
        channel_id = str(ctx.channel.id)
        set_code = active_set_code()
        today, tomorrow, early, late, early_next, late_next = _rolling_lanes()

        def early_today(**kw):
            return _rolling_slot(early, slot_event_time(today, early.key), **kw)

        def late_today(**kw):
            return _rolling_slot(late, slot_event_time(today, late.key), offset=6, **kw)

        def early_tom(**kw):
            return _rolling_slot(early_next, slot_event_time(tomorrow, early_next.key), offset=3, **kw)

        def late_tom(**kw):
            return _rolling_slot(late_next, slot_event_time(tomorrow, late_next.key), offset=9, **kw)

        playing = dict(fired=True, channel_id=channel_id, set_code=set_code)
        played = dict(finished=True, **playing)

        async def show(label: str, slots, closed: bool = False) -> None:
            await ctx.send(f"**{label}**")
            view = None if closed else PodPollView(slots, guild)
            await ctx.send(embed=build_poll_embed(slots, guild, closed=closed), view=view)

        await show("A. Fresh morning board — both slots gathering today", [
            early_today(count=_ROLL_COUNT_FULL),
            late_today(count=_ROLL_COUNT_SMALL),
        ])

        await show("B. Early finished — Played section links the pod, Next section is the upcoming day", [
            early_today(count=_ROLL_COUNT_FULL, winner="Finkel", **played),
            late_today(count=_ROLL_COUNT_SMALL),
            early_tom(count=_ROLL_COUNT_SMALL),
        ])

        await show("B (playing). Early fired but the draft is still running — Playing section, no winner yet", [
            early_today(count=_ROLL_COUNT_FULL, **playing),
            late_today(count=_ROLL_COUNT_SMALL),
            early_tom(count=_ROLL_COUNT_SMALL),
        ])

        await show("C. Both finished — full 2x2, each column stacks Played over Next", [
            early_today(count=_ROLL_COUNT_FULL, winner="Finkel", **played),
            late_today(count=_ROLL_COUNT_FULL, winner="Shota", **played),
            early_tom(count=_ROLL_COUNT_SMALL),
            late_tom(count=_ROLL_COUNT_SMALL),
        ])

        await show("C (multi-table). Early fired two tables today — the second table joins Played", [
            early_today(count=_ROLL_COUNT_FULL, winner="Finkel", **played),
            _rolling_slot(early, slot_event_time(today, early.key), count=_ROLL_COUNT_SMALL, offset=12,
                          fired=True, channel_id=channel_id, set_code=set_code, winner="LSV", table=2),
            late_today(count=_ROLL_COUNT_FULL, winner="Shota", **played),
            early_tom(count=_ROLL_COUNT_SMALL),
            late_tom(count=_ROLL_COUNT_SMALL),
        ])

        await show("C (team). Late was a team draft — the winning side is credited and links no seat", [
            early_today(count=_ROLL_COUNT_FULL, winner="Finkel", **played),
            late_today(count=_ROLL_COUNT_FULL, winner="Green Team", seat=False, **played),
            early_tom(count=_ROLL_COUNT_SMALL),
            late_tom(count=_ROLL_COUNT_SMALL),
        ])

        await ctx.send("**D. Handoff at 11:00 — the old card retires to a compact On This Day history**")
        await ctx.send(embed=build_poll_embed([
            early_today(count=_ROLL_COUNT_FULL, winner="Finkel", **played),
            late_today(count=_ROLL_COUNT_FULL, winner="Shota", **played),
            early_tom(count=_ROLL_COUNT_FULL, winner="Reid", **played),
        ], guild, closed=True, board_date=today))
        await show("(new card, posted at the bottom)", [
            early_tom(count=_ROLL_COUNT_SMALL),
            late_tom(count=_ROLL_COUNT_SMALL),
        ])

        next_keys = [
            named_bucket_key(early_next.key, code)
            for code in pod_format_schedule.formats_for(tomorrow, early_next.lane)
        ]
        embed, view = build_play_again_prompt(next_keys, guild)
        await ctx.send(
            "**E. Play Again prompt — posted in a finished pod's thread, offering tomorrow's formats**")
        await ctx.send(embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none())

    @test_group.command(name="widths")
    @commands.is_owner()
    async def test_widths(ctx: commands.Context) -> None:
        """Owner-only. Post the Played row at the widths that decide whether it wraps: a short set code with
        short names, the long cube label, a second table, and a winner name past what a column fits. Every
        board pairs a short name against a long one, which is the pair that pushed the two columns out of
        level, so the check is whether both Next headers still sit on the same line. Fixtures through the
        production embed builder, no signals."""
        guild = ctx.guild
        channel_id = str(ctx.channel.id)
        today, tomorrow, early, late, early_next, late_next = _rolling_lanes()

        def played(bucket, code, winner, offset, table=None):
            return _rolling_slot(
                bucket, slot_event_time(today, bucket.key), count=_ROLL_COUNT_FULL, offset=offset,
                fired=True, finished=True, channel_id=channel_id, set_code=code, winner=winner, table=table,
            )

        def gathering(bucket, offset):
            return _rolling_slot(bucket, slot_event_time(tomorrow, bucket.key), count=_ROLL_COUNT_SMALL,
                                 offset=offset)

        for label, code, short_winner, long_winner, tables in _WIDTH_CASES:
            slots = [played(early, code, short_winner, 0), played(late, code, long_winner, 6)]
            if tables:
                slots.append(played(early, code, _handle(1), 12, table=2))
            slots += [gathering(early_next, 3), gathering(late_next, 9)]
            await ctx.send(f"**{label}**")
            await ctx.send(embed=build_poll_embed(slots, guild))

    @test_group.command(name="launcher")
    @commands.is_owner()
    async def test_launcher(ctx: commands.Context, *args: str) -> None:
        """Owner-only. Drive the launcher end to end: stage a real scheduled pod at the day's last slot
        so it reflects as a committed jump-link, seed Yes RSVPs on it so the committed slot shows its
        roster, then post the live launcher for that day. The other slots are real lazy signals whose
        buttons drive the fire path; set POD_SIGNAL_FIRE_THRESHOLD low to graduate one yourself. Uses
        today when a slot is still ahead, otherwise tomorrow, so the staged pod is always in the future.
        Args are order-free: a number sets how many Yes RSVPs to seed (default 5), the word `close`
        immediately retires it into the closed state (grey, no buttons, no role ping, committed slot
        shown as its roster) so that surface can be eyeballed, and a set or cube code is offered beside the
        latest set so any of them can be driven live without waiting for its date."""
        fill = 5
        close = False
        forced_format = None
        for arg in args:
            if arg.isdigit():
                fill = int(arg)
            elif arg.lower() == "close":
                close = True
            else:
                forced_format = pod_format.resolve_format_code(arg) or forced_format
        if not isinstance(ctx.channel, discord.TextChannel):
            await ctx.send("Run `!test launcher` in a server text channel — the pod thread is created there.")
            return
        now = datetime.now(SCHEDULE_TZ)
        today = now.date()
        last_today = slot_event_time(today, poll_buckets_for(today)[-1].key)
        target_day = today if last_today > now else today + timedelta(days=1)
        if forced_format:
            _force_formats(target_day, (forced_format,))
        reflect = poll_buckets_for(target_day)[-1]
        slot_time = slot_event_time(target_day, reflect.key)
        set_code = active_set_code()
        name = await asyncio.to_thread(pod_launch.ondemand_event_name_sync, set_code, slot_time)
        event_id = await post_scheduled_card(
            ctx.bot, ctx.channel, set_code=set_code, event_time=slot_time, name=name, ping_role=False,
        )
        if event_id is None:
            await ctx.send("Could not stage the reflected scheduled pod. Check the logs.")
            return
        if fill > 0:
            await _seed_fake_yes(ctx.channel, event_id, slot_time, name, fill)
        await ctx.send(f"Staged **{name}** at {reflect.name}; posting the live launcher for that day.")
        await post_launcher(ctx.bot, ctx.channel, target_day)
        if close:
            await close_launcher_for_date(ctx.bot, target_day)

    @test_group.command(name="reset")
    @commands.is_owner()
    async def test_reset(ctx: commands.Context) -> None:
        """Owner-only. Clear this guild's on-demand pod signals (poll / queue / scheduled) and every pod
        of the day so the `!test` surfaces start from a clean slate: every slot goes back to lazy, the
        cards and launcher boards are deleted, the pods' threads are deleted, the bot's scheduled events
        come off the Events calendar, and the auto-granted pod ping roles are stripped. Unfinalized pods
        of any day go too; finalized pods from earlier days stay as leaderboard history."""
        if ctx.guild is None:
            await ctx.send("Run `!test reset` in the test server, so the signals it clears are scoped to it.")
            return
        guild_id = str(ctx.guild.id)
        reset = await asyncio.to_thread(pod_launch.reset_ondemand_signals_sync, guild_id)
        purged = await purge_native_events(ctx.guild, ctx.bot.user.id)
        threads_deleted = await delete_threads(ctx.bot, reset.thread_ids)
        cards_deleted = await pod_launch.delete_reset_cards(reset.card_refs)
        roles_removed = 0
        if isinstance(ctx.author, discord.Member):
            roles_removed = await strip_pod_roles(ctx.author)
            forget_welcome(ctx.author.id)
        await ctx.send(
            f"Cleared on-demand pod signals: {reset.signals} signals, {reset.members} members, "
            f"{reset.events} pods. Deleted {cards_deleted} cards and {threads_deleted} pod threads, "
            f"removed {purged} scheduled events from the calendar, and stripped {roles_removed} of "
            f"your pod roles."
        )

    @test_group.command(name="welcome")
    @commands.is_owner()
    async def test_welcome(ctx: commands.Context) -> None:
        """Owner-only. Post slot buttons that replay the first-pod welcome and role-grant a new drafter
        sees, addressed to whoever clicks."""
        if ctx.guild is None:
            await ctx.send("Run `!test welcome` in the server so the role pills resolve.")
            return
        await ctx.send(
            "Click a slot to see the first-pod welcome and role-grant a new drafter gets.",
            view=WelcomePreviewView(),
        )

    @test_group.command(name="rsvp")
    @commands.is_owner()
    async def test_rsvp(
        ctx: commands.Context, minutes: int = 60, fill: int = 0, team: str = "",
    ) -> None:
        """Owner-only. Post a live scheduled RSVP card in this channel via the production creation
        path — thread, event, native Discord event, and timed jobs included. `minutes` sets how far
        out the pod starts; `fill` seeds that many fake Yes signups so the '≥8' multi-pod notice can
        be previewed without eight real people. Pass `team` as the third word to flip the card into a
        Team Draft through the real persist-and-refresh path, so the ` - Team Draft` title marker can
        be eyeballed without a live lobby vote."""
        if not isinstance(ctx.channel, discord.TextChannel):
            await ctx.send("Run `!test rsvp` in a server text channel — the thread is created there.")
            return
        event_time = datetime.now(SCHEDULE_TZ) + timedelta(minutes=minutes)
        set_code = active_set_code()
        name = await asyncio.to_thread(pod_launch.ondemand_event_name_sync, set_code, event_time)
        event_id = await post_scheduled_card(
            ctx.bot, ctx.channel, set_code=set_code, event_time=event_time, name=name,
        )
        if event_id is None:
            await ctx.send("Could not create the scheduled card. Check the logs.")
            return
        if fill > 0:
            await _seed_fake_yes(ctx.channel, event_id, event_time, name, fill)
        if team.lower() == "team":
            await set_event_pairing_mode(event_id, "team")
            await refresh_scheduled_card(ctx.bot, event_id)

    @test_group.command(name="lockroster")
    @commands.is_owner()
    async def test_lockroster(ctx: commands.Context, minutes: int = 60) -> None:
        """Owner-only. Preview the locked-roster card across its three post-gathering states — draft
        started, matches in progress, final standings — as three static embeds from fixture drafters.
        Look-only: no thread, event, or timed jobs. Shows what replaces the RSVP columns once the draft
        starts, and that the Draft Recap button rides only the completed card. `minutes` sets how long
        ago the pod started, since a locked card is always a draft already in flight."""
        event_time = datetime.now(SCHEDULE_TZ) - timedelta(minutes=minutes)
        set_code = active_set_code()
        name = await asyncio.to_thread(pod_launch.ondemand_event_name_sync, set_code, event_time)
        colors = ["WU", "BR", "URg", "WBg", "GW", "UB", "RG", "WUBRG"]
        records = ["3-0", "2-1", "2-1", "2-1", "1-2", "1-2", "1-2", "0-3"]

        started = [DraftedPlayer(display_name=_roster_name(i), seat_index=i) for i in range(8)]
        playing = [
            DraftedPlayer(display_name=_roster_name(i), seat_index=i, deck_colors=colors[i],
                          record="1-0" if i < 4 else "0-1")
            for i in range(8)
        ]
        complete = [
            DraftedPlayer(display_name=_roster_name(i), seat_index=i, deck_colors=colors[i],
                          record=records[i], placement=i + 1)
            for i in range(8)
        ]
        champion_line = f"🏆 **{_roster_name(0)}** wins the draft with {format_deck_color_emojis(colors[0])}"

        for status_line, roster, done in (
            (CARD_STATUS_DRAFTING, started, False),
            (CARD_STATUS_PLAYING, playing, False),
            (champion_line, complete, True),
        ):
            embed = build_rsvp_embed(
                name, event_time, {}, set_code=set_code, status_line=status_line,
                locked_roster=roster, draft_complete=done,
            )
            view = None
            if done:
                view = discord.ui.View(timeout=None)
                view.add_item(build_replays_link_button(name))
            await ctx.send(embed=embed, view=view)

    @test_group.command(name="teamcard")
    @commands.is_owner()
    async def test_teamcard(ctx: commands.Context, minutes: int = 60) -> None:
        """Owner-only. Preview the team-draft card across its three post-gathering states — draft started,
        matches in progress, final result — as three static embeds from fixture teams. Look-only: no
        thread, event, or timed jobs. Shows the Green / Blue roster columns that replace the RSVP columns
        once a team draft starts, each header carrying the team's running match wins, and the final result
        headline once every match is in. `minutes` sets how long ago the pod started."""
        event_time = datetime.now(SCHEDULE_TZ) - timedelta(minutes=minutes)
        set_code = active_set_code()
        name = await asyncio.to_thread(pod_launch.ondemand_event_name_sync, set_code, event_time)
        green = [_roster_name(i) for i in range(0, 8, 2)]
        blue = [_roster_name(i) for i in range(1, 8, 2)]
        green_records, blue_records = ["3-0", "2-1", "2-1", "1-2"], ["2-1", "1-2", "1-2", "0-3"]
        green_colors, blue_colors = ["WU", "BR", "GW", "UB"], ["URg", "WBg", "RG", "WUBRG"]
        gathering = {
            pod_team.TEAM_A: [TeamBoardMember(display=n, arena=None) for n in green],
            pod_team.TEAM_B: [TeamBoardMember(display=n, arena=None) for n in blue],
        }
        final = {
            pod_team.TEAM_A: [TeamBoardMember(green[i], None, green_records[i], green_colors[i]) for i in range(4)],
            pod_team.TEAM_B: [TeamBoardMember(blue[i], None, blue_records[i], blue_colors[i]) for i in range(4)],
        }
        final_line = pod_team.draft_result_line(pod_team.TEAM_A, [f"**{n}**" for n in green], 3, 1)

        for status_line, rosters in (
            (CARD_STATUS_DRAFTING, gathering),
            (CARD_STATUS_PLAYING, gathering),
            (final_line, final),
        ):
            embed = build_rsvp_embed(
                name, event_time, {}, set_code=set_code, status_line=status_line,
                team_draft=True, team_rosters=rosters,
            )
            await ctx.send(embed=embed)

    @test_group.command(name="secondtable")
    @commands.is_owner()
    async def test_secondtable(ctx: commands.Context, total: int = 14, seated: int = 8) -> None:
        """Owner-only. Post a scheduled card, seed `total` fake Yes, then simulate the first pod firing
        with `seated` of them locked in and offer a second table to the rest. No live draft needed —
        this drives the same offer path `_start_draft` fires. Needs `total - seated` at or above the
        table threshold to actually post an offer."""
        if not isinstance(ctx.channel, discord.TextChannel):
            await ctx.send("Run `!test secondtable` in a server text channel.")
            return
        event_time = datetime.now(SCHEDULE_TZ) + timedelta(minutes=60)
        set_code = active_set_code()
        name = await asyncio.to_thread(pod_launch.ondemand_event_name_sync, set_code, event_time)
        event_id = await post_scheduled_card(
            ctx.bot, ctx.channel, set_code=set_code, event_time=event_time, name=name,
        )
        if event_id is None:
            await ctx.send("Could not create the scheduled card. Check the logs.")
            return
        names = [_roster_name(i) for i in range(total)]
        ref = await asyncio.to_thread(pod_launch.scheduled_card_ref_sync, event_id)
        for i, display in enumerate(names):
            await asyncio.to_thread(pod_launch.set_rsvp_sync, ref[2], f"filltest-{i}", display, RSVP_YES)
        await offer_second_table(ctx.bot, event_id, {f"filltest-{i}" for i in range(seated)})

    @test_group.command(name="teamoffer")
    @commands.is_owner()
    async def test_teamoffer(ctx: commands.Context, yes: int = 6, preseed: int = 0) -> None:
        """Owner-only. Stage a scheduled pod 60 minutes out, seed `yes` fake Yes RSVPs, then fire the real
        T-60 roster reminder so the roster embed and the Team-Draft offer card post through the production
        path. The offer only appears when `yes` is exactly six. Pass `preseed` to prefill that many votes on
        the card so a single real click locks the pod to Team Draft solo."""
        if not isinstance(ctx.channel, discord.TextChannel):
            await ctx.send("Run `!test teamoffer` in a server text channel — the thread is created there.")
            return
        event_time = datetime.now(SCHEDULE_TZ) + timedelta(minutes=60)
        set_code = active_set_code()
        name = await asyncio.to_thread(pod_launch.ondemand_event_name_sync, set_code, event_time)
        event_id = await post_scheduled_card(
            ctx.bot, ctx.channel, set_code=set_code, event_time=event_time, name=name,
        )
        if event_id is None:
            await ctx.send("Could not create the scheduled card. Check the logs.")
            return
        if yes > 0:
            await _seed_fake_yes(ctx.channel, event_id, event_time, name, yes)
        await fire_roster_reminder(event_id)
        if preseed > 0:
            await _preseed_team_votes(ctx.bot, event_id, preseed)

    @test_group.command(name="draft")
    @commands.is_owner()
    async def test_draft(ctx: commands.Context) -> None:
        """Owner-only. Post a live /draft queue in this channel; the Join / Leave buttons drive the real signal."""
        today = datetime.now(SCHEDULE_TZ).date()
        view = PodQueueView(role_mention=queue_role_mention(ctx.guild))
        message = await ctx.send(view=view, allowed_mentions=discord.AllowedMentions(roles=True))
        guild_id = str(ctx.guild.id) if ctx.guild else ""
        await asyncio.to_thread(
            pod_launch.create_queue_signal_sync,
            guild_id=guild_id, channel_id=str(ctx.channel.id), message_id=str(message.id),
            signal_date=today, opened_by=str(ctx.author.id),
        )

    @test_group.command(name="gather")
    @commands.is_owner()
    async def test_gather(ctx: commands.Context, scenario: str = "", seats: int = 6) -> None:
        """Owner-only. Stage the gathering-first pod flow in sequence: a scenario blurb, the anchor
        gathering card whose pick buttons are the player surface (a click adds one simulated signup with
        that pick), the card's thread, and a simulator message in the thread whose Ready Check posts the
        seat-claim card there like the real T-10 job would. Table presses seat fixture players with
        exclusives first so a flexible player's press lands last; the thread renames when the first table
        locks. Scenarios: simple, deadlock, swing, split. No signals or lobbies are created."""
        if not isinstance(ctx.channel, discord.TextChannel):
            await ctx.send("Run `!test gather` in a server text channel — the preview creates a thread.")
            return
        key = scenario.lower()
        if key not in _GATHER_SCENARIOS:
            await ctx.send("Scenarios: " + ", ".join(_GATHER_SCENARIOS))
            return
        members = [
            pod_gathering.GatherMember(name, interests, ranking)
            for name, interests, ranking in _GATHER_SCENARIOS[key]
        ]
        slot_time = datetime.now(SCHEDULE_TZ) + timedelta(hours=3)
        state = _GatherState(members, slot_time, seats)
        await ctx.send(f"Scenario **{key}**: {_GATHER_BLURBS[key]}")
        card = await ctx.send(embed=state.gathering_embed(), view=_GatherCardView(state))
        thread = await card.create_thread(
            name=pod_gathering.neutral_pod_title(_GATHER_SLOT_LABEL, slot_time),
        )
        await thread.send(_GATHER_DIRECTOR_NOTE, view=_GatherDirectorView(state, card))

    @test_group.command(name="queueclosed")
    @commands.is_owner()
    async def test_queueclosed(ctx: commands.Context) -> None:
        """Owner-only. Post both closed-queue cards to eyeball the copy: the inactivity timeout keeps its
        roster of idle players, the manual close shows none (only the last player can close it). Inert
        previews through the real builder, no signal."""
        mention = queue_role_mention(ctx.guild)
        set_code = active_set_code()
        opened_at = datetime.now(timezone.utc) - timedelta(hours=1)
        opened_by = str(ctx.author.id)
        await ctx.send(view=PodQueueView(
            names=list(_ROSTER_NAMES[:3]), role_mention=mention,
            close_reason=queue_inactivity_close_reason(), set_code=set_code,
            opened_at=opened_at, opened_by=opened_by,
        ))
        await ctx.send(view=PodQueueView(
            role_mention=mention, close_reason=QUEUE_CLOSED_MANUAL,
            set_code=set_code, opened_at=opened_at, opened_by=opened_by,
        ))


_POLL_SEED_DEDICATED = 3
_POLL_SEED_SHARED = 1
_POLL_SPLIT_DEDICATED = 5
_POLL_SPLIT_SHARED = 2
_POLL_SEED_ID_PREFIX = "polltest-"

_ROLL_COUNT_FULL = 6
_ROLL_COUNT_SMALL = 3

_ROSTER_NAMES = HALL_OF_FAME


def _handle(*indexes: int) -> str:
    """A fixture Discord handle of a chosen length, joined out of hall-of-fame names so a width preview
    never puts an invented community member on the board."""
    return "_".join(HALL_OF_FAME[index].replace(" ", "") for index in indexes)


_WIDTH_CASES = (
    ("A. Short set code, short names: both rows keep their date", None, _handle(0), _handle(4), False),
    ("B. Long cube label: the row drops the date to keep the winner beside the pod",
     pod_format.PEASANT_CODE, _handle(0), _handle(12, 13), False),
    ("C. Second table: the split table reads as an ordinal, so the row keeps its date", None,
     _handle(0), _handle(12, 13), True),
    ("D. Winner name past what a column fits: the name is cut once the date is already gone",
     pod_format.PEASANT_CODE, _handle(1), _handle(12, 13, 14), True),
)


def _rolling_lanes():
    """Today's two lane buckets and the ones they roll into tomorrow, shared by the rolling and width
    previews."""
    today = datetime.now(SCHEDULE_TZ).date()
    tomorrow = today + timedelta(days=1)
    early, late = poll_buckets_for(today)[:2]
    return today, tomorrow, early, late, bucket_for_lane(tomorrow, early.lane), bucket_for_lane(tomorrow, late.lane)


def _rolling_slot(
    bucket, slot_time, *, count: int, offset: int = 0, fired: bool = False, finished: bool = False,
    winner: str | None = None, seat: bool = True, channel_id: str = "", set_code: str | None = None,
    table: int | None = None, shared: tuple[str, ...] = (),
):
    """Build one fixture LauncherSlot for the rolling preview. A fired slot carries a pod link and counts as
    locked, so it renders as the compact line; `finished` marks it played, so it takes the trophy instead of
    the playing mark. A gathering slot carries its own roster. `offset` shifts the fixture names so pods on
    one board don't repeat. `table` marks a second table so the fixture can show more than one pod under a
    slot. `seat` off is a team draft's winning side, which has no seat on the pod page to link."""
    code = set_code or active_set_code()
    names = [_roster_name(offset + i) for i in range(count)]
    bucket_key = named_bucket_key(bucket.key, code)
    if fired:
        suffix = f" - Table {table}" if table else ""
        title = f"{pod_display_name(code, slot_time)}{suffix}"
        return pod_launch.LauncherSlot(
            bucket_key, committed=True, status=STATUS_FIRED, count=len(names), slot_time=slot_time,
            names=names, thread_id="1", signal_id=None, thread_message_id="1", card_message_id="1",
            card_channel_id=channel_id, thread_name=title, set_code=code,
            finished=finished, winner=winner, locked=True,
            winner_slug=slugify(winner) if winner and seat else None,
        )
    return pod_launch.LauncherSlot(
        bucket_key, committed=False, status=STATUS_OPEN, count=len(names), slot_time=slot_time,
        names=names, thread_id=None, signal_id="1", set_code=code, shared_names=shared,
    )


def _roster_name(index: int) -> str:
    return _ROSTER_NAMES[index % len(_ROSTER_NAMES)]


_GATHER_SLOT_LABEL = "Late"
_ANY = (fi.LATEST, fi.FLASHBACK)
_BENCH_RANKINGS = (("DSK",), ("FIN", "DSK"), ("MH3", "DSK"))
MSG_NO_PRESSER = "No eligible player is waiting."

_GATHER_SCENARIOS: dict[str, list[tuple[str, tuple[str, ...], tuple[str, ...]]]] = {
    "simple": [
        ("Noya", (fi.LATEST,), ()),
        ("Finkel", (fi.LATEST,), ()),
        ("LSV", (fi.LATEST,), ()),
        ("Huey", (fi.LATEST,), ()),
        ("Karsten", (), ()),
        ("Owen", _ANY, ()),
    ],
    "deadlock": [
        ("Noya", (fi.LATEST,), ()),
        ("Finkel", (fi.LATEST,), ()),
        ("LSV", (fi.LATEST,), ()),
        ("Huey", (fi.LATEST,), ()),
        ("The Hump", (fi.FLASHBACK,), ("DSK", "FIN")),
        ("Paolo", (fi.FLASHBACK,), ("DSK", "MH3")),
        ("Shota", (fi.FLASHBACK,), ("FIN", "DSK")),
        ("Reid", (fi.FLASHBACK,), ("DSK",)),
    ],
    "swing": [
        ("Noya", (fi.LATEST,), ()),
        ("Finkel", (fi.LATEST,), ()),
        ("LSV", (fi.LATEST,), ()),
        ("Huey", (fi.LATEST,), ()),
        ("Karsten", (fi.LATEST,), ()),
        ("The Hump", (fi.FLASHBACK,), ("DSK", "FIN")),
        ("Paolo", (fi.FLASHBACK,), ("DSK", "MH3")),
        ("Shota", (fi.FLASHBACK,), ("FIN", "DSK")),
        ("Reid", (fi.FLASHBACK,), ("DSK",)),
        ("Nassif", (fi.FLASHBACK,), ("MH3", "DSK")),
        ("Chapin", _ANY, ("DSK",)),
    ],
    "split": [
        ("Noya", (fi.LATEST,), ()),
        ("Finkel", (fi.LATEST,), ()),
        ("LSV", (fi.LATEST,), ()),
        ("Huey", (fi.LATEST,), ()),
        ("Karsten", (fi.LATEST,), ()),
        ("Owen", (fi.LATEST,), ()),
        ("The Hump", (fi.FLASHBACK,), ("DSK", "FIN")),
        ("Paolo", (fi.FLASHBACK,), ("DSK", "MH3")),
        ("Shota", (fi.FLASHBACK,), ("FIN", "DSK")),
        ("Reid", (fi.FLASHBACK,), ("DSK",)),
        ("Nassif", (fi.FLASHBACK,), ("MH3", "DSK")),
        ("Chapin", _ANY, ("DSK",)),
        ("Levy", _ANY, ("FIN",)),
    ],
}


_GATHER_BLURBS = {
    "simple": (
        "all signups lean Latest, so the card stays a flat list and Ready Check offers a single table. "
        "This is today's behavior in the new flow."
    ),
    "deadlock": (
        "4 Latest and 4 Flashback, nobody flexible: eight players but no table of 6. "
        "Ready Check refuses until you add players."
    ),
    "swing": (
        "5 Latest, 5 Flashback and one Any: both formats count 6 but share the flexible player, so only "
        "one table can lock. The last seat-claim press decides which."
    ),
    "split": (
        "6 Latest, 5 Flashback and two Any: thirteen players, both tables can lock."
    ),
}
_GATHER_DIRECTOR_NOTE = (
    "**Simulator controls.** The anchor card's buttons are the player surface: one click there adds one "
    "simulated signup with that pick. Ready Check posts the seat-claim card in this thread, where the "
    "real T-10 job would. Reset restarts the scenario; earlier ready checks go stale."
)


class _GatherState:
    """Fixture state behind the gather preview. Every rendered string comes from the pod_gathering
    builders; this class only tracks who signed, pressed, or no-showed."""

    def __init__(
        self, members: list[pod_gathering.GatherMember], slot_time: datetime, seats: int,
    ) -> None:
        self._initial = list(members)
        self.members = list(members)
        self.slot_time = slot_time
        self.seats = seats
        self.tables: list[pod_gathering.TableCandidate] = []
        self.absent: list[str] = []

    def gathering_embed(self) -> discord.Embed:
        return pod_gathering.build_gathering_embed(_GATHER_SLOT_LABEL, self.slot_time, self.members)

    def ready_embed(self) -> discord.Embed:
        return pod_gathering.build_ready_embed(
            _GATHER_SLOT_LABEL, self.slot_time, self.tables, self.waiting(), self.absent, self.seats,
        )

    def add_member(self, interests: tuple[str, ...]) -> None:
        added = len(self.members) - len(self._initial)
        ranking = _BENCH_RANKINGS[added % len(_BENCH_RANKINGS)] if fi.FLASHBACK in interests else ()
        used = {member.name for member in self.members}
        name = f"Guest {added + 1}"
        for candidate in _ROSTER_NAMES:
            if candidate not in used:
                name = candidate
                break
        self.members.append(pod_gathering.GatherMember(name, interests, ranking))

    def start_ready(self) -> bool:
        comp = fi.composition([member.interests for member in self.members])
        tables: list[pod_gathering.TableCandidate] = []
        if comp.latest_capacity + comp.unstated >= self.seats:
            tables.append(pod_gathering.latest_table_candidate())
        if comp.flashback_capacity >= self.seats:
            tables.append(pod_gathering.flashback_table_candidate())
        if not tables:
            return False
        self.tables = tables
        return True

    def press(self, index: int) -> pod_gathering.TableCandidate | None:
        """Seat the next eligible fixture player at the table; the table just locked comes back so the
        caller can rename the thread."""
        table = self.tables[index]
        if table.locked(self.seats):
            return None
        member = self._next_presser(table)
        if member is None:
            return None
        table.pressed.append(member.name)
        if table.locked(self.seats) and table.format_code == fi.FLASHBACK and table.set_code is None:
            rankings = [m.ranking for m in self.members if m.name in table.pressed]
            table.set_code = pod_gathering.resolve_flashback_set(rankings)
        return table if table.locked(self.seats) else None

    def mark_no_show(self) -> bool:
        waiting = self.waiting()
        if not waiting:
            return False
        self.absent.append(waiting[0])
        return True

    def reset(self) -> None:
        self.members = list(self._initial)
        self.tables = []
        self.absent = []

    def waiting(self) -> list[str]:
        pressed = {name for table in self.tables for name in table.pressed}
        return [
            member.name for member in self.members
            if member.name not in pressed and member.name not in self.absent
        ]

    def _next_presser(self, table: pod_gathering.TableCandidate) -> pod_gathering.GatherMember | None:
        eligible = []
        pressed = {name for candidate in self.tables for name in candidate.pressed}
        for member in self.members:
            if member.name in pressed or member.name in self.absent:
                continue
            codes = fi.normalize(member.interests)
            if table.format_code == fi.LATEST:
                fits = fi.FLASHBACK not in codes or fi.LATEST in codes
            else:
                fits = fi.FLASHBACK in codes
            if fits:
                eligible.append(member)
        for member in eligible:
            if not fi.is_flexible(member.interests):
                return member
        return eligible[0] if eligible else None


class _GatherCardView(discord.ui.View):
    """The anchor card's player surface. In the preview a click adds one simulated signup with that
    pick, standing in for a real player pressing it."""

    def __init__(self, state: _GatherState) -> None:
        super().__init__(timeout=3600)
        self.state = state
        self.add_item(_GatherPickButton("Latest", fi.latest_emoji(), (fi.LATEST,)))
        self.add_item(_GatherPickButton("Flashback", fi.flashback_emoji(), (fi.FLASHBACK,)))
        self.add_item(_GatherPickButton("Any", fi.FLEXIBLE_EMOJI, _ANY))


class _GatherPickButton(discord.ui.Button):
    def __init__(self, label: str, emoji: object, interests: tuple[str, ...]) -> None:
        super().__init__(label=label, style=discord.ButtonStyle.secondary, emoji=emoji)
        self.interests = interests

    async def callback(self, interaction: discord.Interaction) -> None:
        view: _GatherCardView = self.view
        view.state.add_member(self.interests)
        await interaction.response.edit_message(embed=view.state.gathering_embed(), view=view)


class _GatherDirectorView(discord.ui.View):
    def __init__(self, state: _GatherState, card: discord.Message) -> None:
        super().__init__(timeout=3600)
        self.state = state
        self.card = card

    @discord.ui.button(label="Start Ready Check", style=discord.ButtonStyle.primary)
    async def ready_check(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not self.state.start_ready():
            await interaction.response.send_message(
                pod_gathering.MSG_NO_TABLE_YET.format(seats=self.state.seats), ephemeral=True,
            )
            return
        view = _GatherReadyView(self.state)
        await interaction.response.send_message(embed=self.state.ready_embed(), view=view)

    @discord.ui.button(label="Reset", style=discord.ButtonStyle.secondary)
    async def reset(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.state.reset()
        await self.card.edit(embed=self.state.gathering_embed())
        await interaction.response.send_message("Scenario reset.", ephemeral=True)


class _GatherReadyView(discord.ui.View):
    def __init__(self, state: _GatherState) -> None:
        super().__init__(timeout=3600)
        self.state = state
        self.renamed = False
        self._rebuild()

    def _rebuild(self) -> None:
        self.clear_items()
        for index, table in enumerate(self.state.tables):
            self.add_item(_GatherPressButton(index, table, self.state.seats))
        self.add_item(_GatherNoShowButton())

    async def render(self, interaction: discord.Interaction) -> None:
        self._rebuild()
        await interaction.response.edit_message(embed=self.state.ready_embed(), view=self)

    async def rename_thread(self, interaction: discord.Interaction, locked: pod_gathering.TableCandidate) -> None:
        if self.renamed or not isinstance(interaction.channel, discord.Thread):
            return
        self.renamed = True
        title = pod_gathering.neutral_pod_title(_GATHER_SLOT_LABEL, self.state.slot_time)
        try:
            await interaction.channel.edit(name=f"{locked.set_code} {title}")
        except discord.HTTPException:
            log.warning("gather preview: could not rename the thread", exc_info=True)


class _GatherPressButton(discord.ui.Button):
    def __init__(self, index: int, table: pod_gathering.TableCandidate, seats: int) -> None:
        emoji = fi.latest_emoji() if table.format_code == fi.LATEST else fi.flashback_emoji()
        super().__init__(
            label=pod_gathering.table_button_label(table, seats),
            style=discord.ButtonStyle.success, emoji=emoji, disabled=table.locked(seats),
        )
        self.index = index

    async def callback(self, interaction: discord.Interaction) -> None:
        view: _GatherReadyView = self.view
        before = len(view.state.tables[self.index].pressed)
        locked = view.state.press(self.index)
        if len(view.state.tables[self.index].pressed) == before:
            await interaction.response.send_message(MSG_NO_PRESSER, ephemeral=True)
            return
        await view.render(interaction)
        if locked is not None:
            await view.rename_thread(interaction, locked)


class _GatherNoShowButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="No Show", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: _GatherReadyView = self.view
        if not view.state.mark_no_show():
            await interaction.response.send_message(MSG_NO_PRESSER, ephemeral=True)
            return
        await view.render(interaction)


def _seed_poll_signups_sync(message_id: str, day, split: bool = False) -> None:
    """Insert fake signups on every pod the launcher just opened, so `!test poll` shows filled rosters without
    needing live clickers. Each pod gets its own dedicated crowd plus a couple of players signed up for both
    formats at that slot, one id and one name each so they read as the same person in both rosters, which is
    what the flexible marker renders. Slots already past stay empty.

    `split` seeds the allocation case instead: five dedicated per format plus two on both, so both pods read
    seven and one press has to split them into two full pods.

    Seeded members are cleared before each run: a second `!test poll` for the same day adopts the signal rows
    the first one opened, so re-inserting the same fake ids would collide. Real signups survive."""
    now = datetime.now(SCHEDULE_TZ)
    dedicated = _POLL_SPLIT_DEDICATED if split else _POLL_SEED_DEDICATED
    shared = _POLL_SPLIT_SHARED if split else _POLL_SEED_SHARED
    next_name = 0
    with SessionLocal() as session:
        for bucket in poll_buckets_for(day):
            slot_time = slot_event_time(day, bucket.key)
            if slot_time is not None and slot_time <= now:
                continue
            signals = session.execute(
                select(PodSignal).where(
                    PodSignal.message_id == message_id,
                    PodSignal.slot_time == slot_time,
                    PodSignal.kind == KIND_POLL,
                )
            ).scalars().all()
            if signals:
                session.execute(delete(PodSignalMember).where(
                    PodSignalMember.signal_id.in_([signal.id for signal in signals]),
                    PodSignalMember.discord_user_id.startswith(_POLL_SEED_ID_PREFIX),
                ))
            both = [
                (f"{_POLL_SEED_ID_PREFIX}{bucket.key}-both-{seat}", _roster_name(next_name + seat))
                for seat in range(shared)
            ]
            next_name += shared
            for signal in signals:
                for seat in range(dedicated):
                    session.add(PodSignalMember(
                        signal_id=signal.id,
                        discord_user_id=f"{_POLL_SEED_ID_PREFIX}{signal.bucket}-{seat}",
                        display_name=_roster_name(next_name + seat),
                    ))
                next_name += dedicated
                for discord_user_id, display_name in both:
                    session.add(PodSignalMember(
                        signal_id=signal.id, discord_user_id=discord_user_id, display_name=display_name,
                    ))
        session.commit()


async def _seed_fake_yes(
    channel: discord.TextChannel, event_id: str, event_time: datetime, name: str, count: int,
) -> None:
    """Record `count` fake Yes RSVPs against the just-posted card and re-render it, so the multi-pod
    notice can be eyeballed solo. Fake members never touch Discord; they only fill the roster."""
    ref = await asyncio.to_thread(pod_launch.scheduled_card_ref_sync, event_id)
    if ref is None:
        return
    message_id = ref[2]
    rosters = None
    for i in range(count):
        result = await asyncio.to_thread(
            pod_launch.set_rsvp_sync, message_id, f"filltest-{i}", _roster_name(i), RSVP_YES)
        if result is not None:
            rosters = result.rosters
    if rosters is None:
        return
    try:
        card = await channel.fetch_message(int(message_id))
        await card.edit(embed=build_rsvp_embed(name, event_time, rosters))
    except discord.HTTPException:
        log.warning(f"could not re-render the fake-fill card {message_id}", exc_info=True)


async def _preseed_team_votes(bot: commands.Bot, event_id: str, count: int) -> None:
    """Prefill `count` fake votes on the just-posted Team-Draft card so the previewer's own click reaches
    the majority and locks the pod solo. Fake voters render as broken mentions; they only fill the tally."""
    thread_id = await asyncio.to_thread(_event_thread_id_sync, event_id)
    if thread_id is None:
        return
    try:
        thread = await bot.fetch_channel(thread_id)
    except discord.HTTPException:
        return
    card = await find_team_vote_card(thread, event_id)
    if card is None or not card.embeds:
        return
    fake = [f"<@{900000000000000000 + i}>" for i in range(count)]
    try:
        await card.edit(embed=rerender_gathering(card.embeds[0], fake, []))
    except discord.HTTPException:
        log.warning(f"could not preseed the team-vote card for {event_id}", exc_info=True)


def _event_thread_id_sync(event_id: str) -> int | None:
    with SessionLocal() as session:
        event = session.get(PodDraftEvent, event_id)
        return int(event.discord_thread_id) if event is not None else None


_LIFECYCLE_STATES = (
    ("1. Gathering, no thread yet", "open"),
    ("2. Both pods fired, threads created, STILL taking signups", "threaded"),
    ("3. Second format is drafting, latest set still joinable", "locked_other"),
    ("4. Both drafts started", "locked_all"),
    ("5. Played", "played"),
)


def _lifecycle_slots(bucket, slot_time, other_format: str, state: str, channel_id: str):
    """The two fixture pods of one slot in a given lifecycle state, so the states render side by side.
    `locked_other` is the case to check: the second format's draft started while the latest set at the same
    time stays joinable."""
    latest = _lifecycle_pod(bucket, slot_time, active_set_code(), channel_id, offset=0, state=(
        "open" if state == "locked_other" else state
    ))
    other = _lifecycle_pod(bucket, slot_time, other_format, channel_id, offset=4, state=state)
    return [latest, other]


def _lifecycle_pod(bucket, slot_time, code: str, channel_id: str, *, offset: int, state: str):
    names = [_roster_name(offset + i) for i in range(4)]
    bucket_key = named_bucket_key(bucket.key, code)
    if state == "open":
        return pod_launch.LauncherSlot(
            bucket_key, committed=False, status=STATUS_OPEN, count=len(names), slot_time=slot_time,
            names=names, thread_id=None, signal_id="1", set_code=code,
        )
    title = f"{code} {slot_time.astimezone(SCHEDULE_TZ):%b %-d} {bucket.name}"
    return pod_launch.LauncherSlot(
        bucket_key, committed=True, status=STATUS_FIRED, count=len(names), slot_time=slot_time,
        names=names, thread_id="1", signal_id=None, thread_message_id="1", card_message_id="1",
        card_channel_id=channel_id, thread_name=title, set_code=code,
        finished=state == "played", winner=_roster_name(offset) if state == "played" else None,
        locked=state in ("locked_other", "locked_all", "played"),
    )


def _force_formats(day, codes: tuple[str, ...]) -> None:
    """Point the schedule at `codes` beside the latest set for one day so a live `!test poll` / `!test
    launcher` can drive any format without waiting for its date. Mutates the in-memory table only, so a
    restart drops it."""
    pod_format_schedule.FORMATS_BY_DAY[day] = (pod_format_schedule.LATEST, *codes)
    log.info(f"[testpolls] forced formats {codes} for {day}")


def _named_arg(codes: list[str], index: int) -> str | None:
    """One slot's code from the command args, where a missing entry or a bare dash means no second format."""
    code = codes[index] if index < len(codes) else ""
    return code if code and code != "-" else None


def _named_slots(bucket, slot_time, other_format):
    """One slot's fixture pods, each with its own roster, so the per-format blocks and their buttons render.
    `other_format` None is the latest-only slot, which carries a single pod. Two of the latest-set signups
    also joined the other format, so the flexible marker shows."""
    shared = tuple(_roster_name(index) for index in (1, 2)) if other_format else ()
    latest = pod_launch.LauncherSlot(
        named_bucket_key(bucket.key, active_set_code()), committed=False, status=STATUS_OPEN, count=3,
        slot_time=slot_time, names=[_roster_name(i) for i in range(3)], thread_id=None, signal_id="1",
        set_code=active_set_code(), shared_names=shared,
    )
    if not other_format:
        return [latest]
    names = [_roster_name(index) for index in (1, 2, 4)]
    other = pod_launch.LauncherSlot(
        named_bucket_key(bucket.key, other_format), committed=False, status=STATUS_OPEN, count=len(names),
        slot_time=slot_time, names=names, thread_id=None, signal_id="2", set_code=other_format,
        shared_names=shared,
    )
    return [latest, other]
