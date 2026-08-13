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
import contextlib
import logging
from collections.abc import Iterable
from datetime import date, datetime, timedelta, timezone

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
    post_pod_card,
    post_scheduled_card,
    purge_native_events,
    refresh_card_embed,
)
from bot.config import settings
from bot.commands.test_group import HALL_OF_FAME, test_group
from sqlalchemy import delete, select

from bot.database import SessionLocal
from bot.discord_helpers import channel_matching_name, run_detached
from bot.models import PodDraftEvent, PodSignal, PodSignalMember
from bot.services import pod_confirm
from bot.services import pod_format
from bot.services import pod_format_interest as fi
from bot.services import pod_format_schedule
from bot.services import pod_gathering
from bot.services import pod_launch
from bot.services.pod_active import ACTIVE_TABLE_VIEWS
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
    LANE_EARLY,
    LANE_LATE,
    RSVP_MAYBE,
    RSVP_YES,
    SCHEDULE_TZ,
    STATUS_EXPIRED,
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
    lane_settled_for_day,
    post_launcher,
    repost_board_after_the_late_pods,
    resurface_board_after_the_early_pods,
)
from bot.tasks.pod_draft_reminder import fire_roster_reminder
from bot.tasks.pod_thread_cleanup import delete_bot_threads_in, delete_threads


log = logging.getLogger(__name__)

WEEKDAY_ARGS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
POLL_KEYWORDS = ("am", "split", *WEEKDAY_ARGS)
PURGE_WINDOW = timedelta(days=3)


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
        post; a weekday name posts that weekday's board, so `poll sat` shows the slots and formats Saturday
        carries; `split` seeds five dedicated per format plus two on both, so one press has to split them
        into two full pods; a set or cube code is offered beside the latest set, so `poll SAMP` drives that
        format live without waiting for its date."""
        lowered = {arg.lower() for arg in args}
        now = datetime.now(SCHEDULE_TZ)
        day = _poll_day(now, args)
        forced = [
            code for code in (
                pod_format.resolve_format_code(arg) if arg.lower() not in POLL_KEYWORDS else None
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
        fixtures: a fresh morning board, one lane whose draft started and rolled to tomorrow, both lanes
        rolled, a slot whose sibling format closed unfired, and the handoff (retired On This Day history plus
        the fresh next-day card), plus the next-day Play Again prompt, whose button is live and joins the
        soonest open slot of that name. A pod that started leaves the live board, so the point to check is
        that each column reads as the slot still open rather than as the day behind it; the winners only
        surface on the retired card. The embeds are fixtures: no signals, threads, or jobs. Reuses the
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

        await show("A. Fresh morning board, both slots gathering today", [
            early_today(count=_ROLL_COUNT_FULL),
            late_today(count=_ROLL_COUNT_SMALL),
        ])

        await show("B. Early started its draft, so the column drops it and offers tomorrow's Early slot", [
            early_today(count=_ROLL_COUNT_FULL, winner="Finkel", **played),
            late_today(count=_ROLL_COUNT_SMALL),
            early_tom(count=_ROLL_COUNT_SMALL),
        ])

        await show("C. Both lanes started, so the full 2x2 is tomorrow's slots and today is off the board", [
            early_today(count=_ROLL_COUNT_FULL, winner="Finkel", **played),
            late_today(count=_ROLL_COUNT_FULL, winner="Shota", **played),
            early_tom(count=_ROLL_COUNT_SMALL),
            late_tom(count=_ROLL_COUNT_SMALL),
        ])

        await show("C (sibling closed). Early drafted two tables while the format beside them closed unfired", [
            early_today(count=_ROLL_COUNT_FULL, **playing),
            _rolling_slot(early, slot_event_time(today, early.key), count=_ROLL_COUNT_SMALL, offset=12,
                          fired=True, channel_id=channel_id, set_code=set_code, table=2),
            _rolling_slot(early, slot_event_time(today, early.key), count=_ROLL_COUNT_SMALL, offset=15,
                          set_code=pod_format.PEASANT_CODE, closed=True),
            late_today(count=_ROLL_COUNT_SMALL),
        ])

        await ctx.send("**D. Handoff at 11:00, the old card retires to a compact On This Day history**")
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
            "**E. Play Again prompt, posted in a finished pod's thread, offering tomorrow's formats**")
        await ctx.send(embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none())

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
        latest set so any of them can be driven live without waiting for its date. A second code stages a
        third pod at that same slot the way `/draft` creates one, so the slot carries a pod nobody
        scheduled beside the two the day offers.

        The first seeded player is put on every pod at the staged slot, so the shared marker renders with no
        live clicker on either side."""
        fill = 5
        close = False
        formats = []
        for arg in args:
            if arg.isdigit():
                fill = int(arg)
            elif arg.lower() == "close":
                close = True
            else:
                code = pod_format.resolve_format_code(arg)
                if code:
                    formats.append(code)
        if not isinstance(ctx.channel, discord.TextChannel):
            await ctx.send("Run `!test launcher` in a server text channel")
            return
        now = datetime.now(SCHEDULE_TZ)
        today = now.date()
        last_today = slot_event_time(today, poll_buckets_for(today)[-1].key)
        target_day = today if last_today > now else today + timedelta(days=1)
        if formats:
            _force_formats(target_day, (formats[0],))
        reflect = poll_buckets_for(target_day)[-1]
        slot_time = slot_event_time(target_day, reflect.key)
        set_code = active_set_code()
        name = await asyncio.to_thread(pod_launch.ondemand_event_name_sync, set_code, slot_time)
        event_id = await post_scheduled_card(
            ctx.bot, ctx.channel, set_code=set_code, event_time=slot_time, name=name, ping_role=False,
        )
        if event_id is None:
            await ctx.send("Could not stage the reflected scheduled pod. Check the logs")
            return
        if fill > 0:
            await _seed_fake_yes(ctx.channel, event_id, slot_time, name, range(fill))
        staged = [name]
        if len(formats) > 1:
            organized = await _stage_organized_pod(ctx, formats[1], slot_time, fill)
            if organized:
                staged.append(organized)
        await ctx.send(
            f"Staged **{'** and **'.join(staged)}** at {reflect.name}; posting the live launcher for that day"
        )
        message = await post_launcher(ctx.bot, ctx.channel, target_day)
        if message is not None:
            await asyncio.to_thread(_seed_shared_signup_sync, slot_time)
            slots = await asyncio.to_thread(pod_launch.launcher_snapshot_sync, str(message.id), target_day)
            await message.edit(embed=build_poll_embed(slots, ctx.guild), view=PodPollView(slots, ctx.guild))
        if close:
            await close_launcher_for_date(ctx.bot, target_day)

    @test_group.command(name="repost")
    @commands.is_owner()
    async def test_repost(ctx: commands.Context, *args: str) -> None:
        """Owner-only. Drive the two reposts against the live board without waiting for a pod to finish.
        With no argument it runs both real triggers and says which guard stopped each: the early one
        resurfaces the same day below the pods that played, the late one posts the next day's board and
        retires the current one as its On This Day card. `force` skips the guards and posts the late one,
        `force early` the early one, so the cards can be eyeballed side by side."""
        board = await asyncio.to_thread(pod_launch.live_launcher_board_sync)
        if board is None:
            await ctx.send("No launcher board is live. Run `!test poll` first")
            return
        _guild_id, _channel_id, message_id, board_day = board
        lowered = {arg.lower() for arg in args}
        if "force" not in lowered:
            slots = await asyncio.to_thread(pod_launch.launcher_snapshot_sync, message_id, board_day)
            early_done = lane_settled_for_day(slots, LANE_EARLY, board_day)
            late_done = lane_settled_for_day(slots, LANE_LATE, board_day)
            resurfaced = await resurface_board_after_the_early_pods(ctx.bot, board_day)
            reposted = await repost_board_after_the_late_pods(ctx.bot, board_day)
            await ctx.send("\n".join([
                f"Board dated **{board_day}**",
                f"Early pods finished: **{_yes_no(early_done)}** — Late pods finished: **{_yes_no(late_done)}**",
                f"Early resurface: **{_posted_or_skipped(resurfaced)}**. "
                "It runs when the early pods are finished, the late ones are not, and the board went up "
                "before the early slot started.",
                f"Evening repost: **{_posted_or_skipped(reposted)}**. "
                "It runs when the late pods are finished and tomorrow has no board yet.",
                "Add `force early` or `force` to post either one now.",
            ]))
            return
        if "early" in lowered:
            posted = await resurface_board_after_the_early_pods(ctx.bot, board_day, force=True)
            if not posted:
                await ctx.send("Could not resurface the board. Check the logs")
                return
            await ctx.send(f"Forced the early resurface: reposted {board_day} and deleted the old board")
            return
        next_day = board_day + timedelta(days=1)
        message = await post_launcher(ctx.bot, ctx.channel, next_day, ping=False, graduate=False)
        if message is None:
            await ctx.send("Could not post the repost. Check the logs")
            return
        await close_launcher_for_date(ctx.bot, board_day)
        await ctx.send(f"Forced the evening repost: posted {next_day} and retired {board_day}")

    @test_group.command(name="reset")
    @commands.is_owner()
    async def test_reset(ctx: commands.Context) -> None:
        """Owner-only. Clear this guild's on-demand pod signals (poll / queue / scheduled) and every pod
        of the day so the `!test` surfaces start from a clean slate: every slot goes back to lazy, both
        pod channels are emptied of what earlier runs left in them, the pods' threads are deleted, the
        bot's scheduled events come off the Events calendar, and the auto-granted pod ping roles are
        stripped. Unfinalized pods of any day go too; finalized pods from earlier days stay as
        leaderboard history.

        The database side is done before the reply lands, so the next `!test` command can be typed
        straight away. Discord is swept behind it, bounded to what was already there."""
        if ctx.guild is None:
            await ctx.send("Run `!test reset` in the test server")
            return
        guild_id = str(ctx.guild.id)
        reset = await asyncio.to_thread(pod_launch.reset_ondemand_signals_sync, guild_id)
        notice = await ctx.send(
            f"Cleared on-demand pod signals: {reset.signals} signals, {reset.members} members, "
            f"{reset.events} pods. Sweeping Discord"
        )
        run_detached(_sweep_test_surfaces(ctx, reset, notice), "the !test reset sweep")

    @test_group.command(name="welcome")
    @commands.is_owner()
    async def test_welcome(ctx: commands.Context) -> None:
        """Owner-only. Post slot buttons that replay the first-pod welcome and role-grant a new drafter
        sees, addressed to whoever clicks."""
        if ctx.guild is None:
            await ctx.send("Run `!test welcome` in the server so the role pills resolve")
            return
        await ctx.send(
            "Click a slot to see the first-pod welcome and role-grant a new drafter gets",
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
        Team Draft through the real persist-and-refresh path, so the title's Team Draft marker can be
        eyeballed without a live lobby vote."""
        if not isinstance(ctx.channel, discord.TextChannel):
            await ctx.send("Run `!test rsvp` in a server text channel")
            return
        event_time = datetime.now(SCHEDULE_TZ) + timedelta(minutes=minutes)
        set_code = active_set_code()
        name = await asyncio.to_thread(pod_launch.ondemand_event_name_sync, set_code, event_time)
        event_id = await post_scheduled_card(
            ctx.bot, ctx.channel, set_code=set_code, event_time=event_time, name=name,
        )
        if event_id is None:
            await ctx.send("Could not create the scheduled card. Check the logs")
            return
        if fill > 0:
            await _seed_fake_yes(ctx.channel, event_id, event_time, name, range(fill))
        if team.lower() == "team":
            await set_event_pairing_mode(event_id, "team")
            await refresh_card_embed(ctx.bot, event_id)

    @test_group.command(name="hold")
    @commands.is_owner()
    async def test_hold(
        ctx: commands.Context, players: int = 14, maybes: int = 3, unconfirmed: int = 2, minutes: int = 3,
    ) -> None:
        """Owner-only. Drive the attendance hold end to end on a real pod, without waiting an hour for it.

        Posts a live scheduled pod `minutes` out, seeds `players` fake Yes signups, then runs the T-10
        fork by hand. The seeds land inside the confirmation hour so they count as confirmed, which is
        what the release sizes its tables from. The hold posts its ping above the roster card and opens no
        lobby; the release fires at the pod's start time, splits the tables and opens a lobby for each.

        `unconfirmed` seeds that many more who said Yes and never confirmed, and `maybes` that many maybes.
        Both are dealt to the last table the split makes, so its lobby-open post carries all three groups
        and its card carries the Unconfirmed column.

        Thirteen is the smallest count that splits into two tables. Ten or fewer never holds at all, which
        is worth seeing too: pass `players` under eleven and the lobby opens the moment the fork runs."""
        if not isinstance(ctx.channel, discord.TextChannel):
            await ctx.send("Run `!test hold` in a server text channel")
            return
        event_time = datetime.now(SCHEDULE_TZ) + timedelta(minutes=minutes)
        set_code = active_set_code()
        name = await asyncio.to_thread(pod_launch.ondemand_event_name_sync, set_code, event_time)
        event_id = await post_scheduled_card(
            ctx.bot, ctx.channel, set_code=set_code, event_time=event_time, name=name,
        )
        if event_id is None:
            await ctx.send("Could not create the scheduled card. Check the logs")
            return
        _stand_down_armed_open(ctx.bot, event_id)
        await _seed_fake_yes(ctx.channel, event_id, event_time, name, range(players))
        await _seed_fake_maybe(event_id, range(players, players + maybes))
        pending = range(players + maybes, players + maybes + unconfirmed)
        await _seed_fake_unconfirmed(ctx.channel, event_id, event_time, name, pending)
        await pod_launch.open_ondemand_lobby(ctx.bot, event_id)

    @test_group.command(name="lockroster")
    @commands.is_owner()
    async def test_lockroster(ctx: commands.Context, minutes: int = 60) -> None:
        """Owner-only. Preview the pod card across its four states — lobby open, draft started, matches
        in progress, final standings — as static embeds from fixture drafters. Look-only: no thread,
        event, or timed jobs. Lobby open is what a queue pod or a table posts for itself; the three
        locked states are what replaces the RSVP columns on any card once the draft starts, with the
        Draft Recap button riding only the completed one. `minutes` sets how long ago the pod started."""
        event_time = datetime.now(SCHEDULE_TZ) - timedelta(minutes=minutes)
        set_code = active_set_code()
        name = await asyncio.to_thread(pod_launch.ondemand_event_name_sync, set_code, event_time)
        await post_pod_card(
            ctx.channel, name=name, event_time=event_time, set_code=set_code,
            roster=[_roster_name(i) for i in range(8)],
        )
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

    @test_group.command(name="teamoffer")
    @commands.is_owner()
    async def test_teamoffer(ctx: commands.Context, yes: int = 6, preseed: int = 0) -> None:
        """Owner-only. Stage a scheduled pod 60 minutes out, seed `yes` fake Yes RSVPs, then fire the real
        T-60 roster reminder so the roster embed and the Team-Draft offer card post through the production
        path. The offer only appears when `yes` is exactly six. Pass `preseed` to prefill that many votes on
        the card so a single real click locks the pod to Team Draft solo."""
        if not isinstance(ctx.channel, discord.TextChannel):
            await ctx.send("Run `!test teamoffer` in a server text channel")
            return
        event_time = datetime.now(SCHEDULE_TZ) + timedelta(minutes=60)
        set_code = active_set_code()
        name = await asyncio.to_thread(pod_launch.ondemand_event_name_sync, set_code, event_time)
        event_id = await post_scheduled_card(
            ctx.bot, ctx.channel, set_code=set_code, event_time=event_time, name=name,
        )
        if event_id is None:
            await ctx.send("Could not create the scheduled card. Check the logs")
            return
        if yes > 0:
            await _seed_fake_yes(ctx.channel, event_id, event_time, name, range(yes))
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
            await ctx.send("Run `!test gather` in a server text channel")
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
_FILL_SEED_ID_PREFIX = "filltest-"
_SHARED_FILL_SEAT = 0

_ROLL_COUNT_FULL = 6
_ROLL_COUNT_SMALL = 3

_ROSTER_NAMES = HALL_OF_FAME


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _posted_or_skipped(value: bool) -> str:
    return "posted" if value else "skipped"




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
    table: int | None = None, closed: bool = False,
):
    """Build one fixture LauncherSlot for the rolling preview. A fired slot carries a pod link and counts as
    locked, so it renders as the compact line; `finished` marks it played, so it takes the trophy instead of
    the playing mark. A gathering slot carries its own roster, or says Closed when `closed` is its recruiting
    window running out unfired. `offset` shifts the fixture names so pods on one board don't repeat. `table`
    marks a second table so the fixture can show more than one pod under a slot. `seat` off is a team draft's
    winning side, which has no seat on the pod page to link."""
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
        bucket_key, committed=False, status=STATUS_EXPIRED if closed else STATUS_OPEN, count=len(names),
        slot_time=slot_time, names=names, thread_id=None, signal_id="1", set_code=code,
    )


def _roster_name(index: int) -> str:
    return _ROSTER_NAMES[index % len(_ROSTER_NAMES)]


async def _preseed_table_claims(event_id: str, *, first_leftover: int, count: int | None) -> None:
    """Fill the live offer card with fixture claimers, one short of its threshold by default, so the
    owner running the preview can fire the table with their own single click. Fixture claimers take
    negative ids, which `materialize_table` renders as plain names instead of dead mentions."""
    view = ACTIVE_TABLE_VIEWS.get(event_id)
    if view is None:
        return
    wanted = view.threshold - 1 if count is None else count
    for seat in range(max(0, min(wanted, view.threshold - 1))):
        view.claims[-(seat + 1)] = _roster_name(first_leftover + seat)
    await view.refresh_card()


_GATHER_SLOT_LABEL = "Late"
_ANY = (fi.LATEST, fi.FLASHBACK)
_BENCH_RANKINGS = (("DSK",), ("FIN", "DSK"), ("MH3", "DSK"))
MSG_NO_PRESSER = "No eligible player is waiting"

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
    "real T-10 job would. Reset restarts the scenario; earlier ready checks go stale"
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
        await interaction.response.send_message("Scenario reset", ephemeral=True)


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


async def _sweep_test_surfaces(ctx: commands.Context, reset, notice: discord.Message) -> None:
    """Everything a test run leaves on Discord, cleared at once and reported back on the notice.

    Sequentially this ran the better part of a minute with the next command waiting behind it. Bounded to
    what existed when reset was typed, so a pod created during the sweep is never caught in it."""
    channels = _test_surface_channels(ctx)
    purged, by_row, by_owner, events, cards = await asyncio.gather(
        _empty_channels(channels, ctx.message),
        delete_threads(ctx.bot, reset.thread_ids),
        _sweep_leftover_threads(ctx, channels),
        purge_native_events(ctx.guild, ctx.bot.user.id),
        pod_launch.delete_reset_cards(reset.card_refs),
    )
    roles_removed = 0
    if isinstance(ctx.author, discord.Member):
        roles_removed = await strip_pod_roles(ctx.author)
        forget_welcome(ctx.author.id)
    with contextlib.suppress(discord.HTTPException):
        await notice.edit(content=(
            f"{notice.content.removesuffix(' Sweeping Discord.')} Deleted {purged + cards} messages and "
            f"{by_row + by_owner} pod threads, removed {events} scheduled events from the calendar, and "
            f"stripped {roles_removed} of your pod roles"
        ))


def _test_surface_channels(ctx: commands.Context) -> list[discord.TextChannel]:
    """The channels a test run puts things in: pod coordination, pod chat, and wherever reset was typed."""
    candidates = [ctx.channel, ctx.bot.get_channel(settings.pod_draft_channel_id)]
    if ctx.guild is not None:
        candidates.append(channel_matching_name(ctx.guild, settings.pod_draft_chat_channel_name))
    channels: list[discord.TextChannel] = []
    seen: set[int] = set()
    for channel in candidates:
        if isinstance(channel, discord.TextChannel) and channel.id not in seen:
            seen.add(channel.id)
            channels.append(channel)
    return channels


async def _empty_channels(channels: list[discord.TextChannel], before: discord.Message) -> int:
    """Delete what this testing session left in these channels, so the next run reads against a channel
    holding only its own output.

    Clearing cards by row left every stray message a run posted around them. Bulk delete takes a hundred
    at a time. Bounded to PURGE_WINDOW, since unbounded it walked back through weeks of a quiet channel."""
    cutoff = before.created_at - PURGE_WINDOW

    async def empty(channel: discord.TextChannel) -> int:
        try:
            return len(await channel.purge(
                limit=200, before=before, after=cutoff, reason="!test reset cleanup",
            ))
        except discord.HTTPException as e:
            log.warning(f"test reset: purge({channel.id}) failed: {e}")
            return 0

    return sum(await asyncio.gather(*(empty(channel) for channel in channels)))


async def _sweep_leftover_threads(ctx: commands.Context, channels: list[discord.TextChannel]) -> int:
    """Every bot thread still standing in the channels a test run leaves them in.

    Clearing by row misses whatever the rows stopped pointing at, and a pod that splits leaves the thread
    it gathered in behind on purpose. Sweeping by owner catches those, and catches the ones a run that
    errored halfway never recorded either."""
    swept = await asyncio.gather(
        *(delete_bot_threads_in(channel, ctx.bot.user.id) for channel in channels)
    )
    return sum(swept)


async def _seed_fake_maybe(event_id: str, seats: Iterable[int]) -> None:
    """Record one fake Maybe per seat. They are the players the hold pings alongside the Yes roster and
    the plan never seats, so a preview without any cannot show that half of the ask."""
    ref = await asyncio.to_thread(pod_launch.scheduled_card_ref_sync, event_id)
    if ref is None:
        return
    for seat in seats:
        await asyncio.to_thread(
            pod_launch.set_rsvp_sync, ref[2], _fill_seed_id(seat), _roster_name(seat), RSVP_MAYBE,
        )


async def _seed_fake_unconfirmed(
    channel: discord.TextChannel, event_id: str, event_time: datetime, name: str, seats: Iterable[int],
) -> None:
    """Record one fake Yes per seat and take its confirmation back off, for the players a real pod ends the
    hold still waiting on.

    A pod seeded minutes from its start time is already inside the confirmation window, so a Yes recorded
    there arrives confirmed. Unticking them afterwards is the organizer's own path to the same state."""
    seats = list(seats)
    if not seats:
        return
    await _seed_fake_yes(channel, event_id, event_time, name, seats)
    ids = [_fill_seed_id(seat) for seat in seats]
    await asyncio.to_thread(pod_confirm.set_confirmations_sync, event_id, (), ids)


def _stand_down_armed_open(bot: commands.Bot, event_id: str) -> None:
    """Cancel the T-10 open a fresh pod arms for itself.

    A pod created minutes from its start time has that job already behind it, so the scheduler runs it
    seconds later, before the preview has seeded anybody. It would read an empty roster, decide there is
    nothing to hold for, and open a lobby. The preview fires the same path itself once the roster is
    there."""
    scheduler = getattr(bot, "pod_scheduler", None)
    if scheduler is None:
        return
    with contextlib.suppress(Exception):
        scheduler.remove_job(pod_launch.open_job_id(event_id))


async def _seed_fake_yes(
    channel: discord.TextChannel, event_id: str, event_time: datetime, name: str, seats: Iterable[int],
) -> None:
    """Record one fake Yes RSVP per seat against the just-posted card and re-render it, so the multi-pod
    notice can be eyeballed solo. A seat is one fake player, so two pods given the same seat hold the same
    person, which is what the shared marker reads. Fake members never touch Discord; they only fill the
    roster."""
    ref = await asyncio.to_thread(pod_launch.scheduled_card_ref_sync, event_id)
    if ref is None:
        return
    message_id = ref[2]
    rosters = None
    for seat in seats:
        result = await asyncio.to_thread(
            pod_launch.set_rsvp_sync, message_id, _fill_seed_id(seat), _roster_name(seat), RSVP_YES)
        if result is not None:
            rosters = result.rosters
    if rosters is None:
        return
    try:
        card = await channel.fetch_message(int(message_id))
        await card.edit(embed=build_rsvp_embed(name, event_time, rosters))
    except discord.HTTPException:
        log.warning(f"could not re-render the fake-fill card {message_id}", exc_info=True)


def _fill_seed_id(seat: int) -> str:
    return f"{_FILL_SEED_ID_PREFIX}{seat}"


async def _stage_organized_pod(
    ctx: commands.Context, set_code: str, slot_time: datetime, fill: int,
) -> str | None:
    """A pod at the staged slot created the way `/draft` creates one: a format the day's schedule never
    offered, credited to whoever ran the command. Its roster is its own crowd apart from the shared seat, so
    the slot carries three pods and one player on all of them. None when the card could not be posted."""
    name = await asyncio.to_thread(pod_launch.ondemand_event_name_sync, set_code, slot_time)
    event_id = await post_scheduled_card(
        ctx.bot, ctx.channel, set_code=set_code, event_time=slot_time, name=name, ping_role=False,
        opener=ctx.author,
    )
    if event_id is None:
        return None
    seats = [_SHARED_FILL_SEAT, *range(fill, fill + max(0, fill - 1))]
    await _seed_fake_yes(ctx.channel, event_id, slot_time, name, seats)
    return name


def _seed_shared_signup_sync(slot_time: datetime) -> None:
    """Sign the staged pods' shared seat up for every pod still gathering at that slot, so one player sits on
    every pod the slot carries and the board renders the shared marker with nobody clicking."""
    with SessionLocal() as session:
        signals = session.execute(
            select(PodSignal).where(PodSignal.slot_time == slot_time, PodSignal.kind == KIND_POLL)
        ).scalars().all()
        session.execute(delete(PodSignalMember).where(
            PodSignalMember.signal_id.in_([signal.id for signal in signals]),
            PodSignalMember.discord_user_id == _fill_seed_id(_SHARED_FILL_SEAT),
        ))
        for signal in signals:
            session.add(PodSignalMember(
                signal_id=signal.id, discord_user_id=_fill_seed_id(_SHARED_FILL_SEAT),
                display_name=_roster_name(_SHARED_FILL_SEAT),
            ))
        session.commit()


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


def _poll_day(now: datetime, args: tuple[str, ...]) -> date:
    """The day a live `!test poll` posts for: the weekday it names, tomorrow on `am`, otherwise today while
    a slot is still ahead. A named weekday is how a board another day of the week builds is reached, the
    Saturday late pod running an hour later than the rest."""
    for arg in args:
        if arg.lower() in WEEKDAY_ARGS:
            return _next_weekday_still_gathering(now, WEEKDAY_ARGS.index(arg.lower()))
    if "am" in {arg.lower() for arg in args}:
        return now.date() + timedelta(days=1)
    return now.date() if _slots_remain(now, now.date()) else now.date() + timedelta(days=1)


def _next_weekday_still_gathering(now: datetime, weekday: int) -> date:
    """The soonest date on `weekday` that still has a slot ahead of it, so every pod on the board it posts
    is open and clickable."""
    day = now.date() + timedelta(days=(weekday - now.weekday()) % 7)
    return day if _slots_remain(now, day) else day + timedelta(days=7)


def _slots_remain(now: datetime, day: date) -> bool:
    last_slot = slot_event_time(day, poll_buckets_for(day)[-1].key)
    return last_slot is not None and last_slot > now


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
    latest = pod_launch.LauncherSlot(
        named_bucket_key(bucket.key, active_set_code()), committed=False, status=STATUS_OPEN, count=3,
        slot_time=slot_time, names=[_roster_name(i) for i in range(3)], thread_id=None, signal_id="1",
        set_code=active_set_code(),
    )
    if not other_format:
        return [latest]
    names = [_roster_name(index) for index in (1, 2, 4)]
    other = pod_launch.LauncherSlot(
        named_bucket_key(bucket.key, other_format), committed=False, status=STATUS_OPEN, count=len(names),
        slot_time=slot_time, names=names, thread_id=None, signal_id="2", set_code=other_format,
    )
    return [latest, other]
