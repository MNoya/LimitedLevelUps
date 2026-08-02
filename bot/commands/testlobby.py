"""Owner-only `!test` — sandbox for previewing the pod-draft lobby embed and live tournament path.

This entire module is throwaway scaffolding for design iteration. To remove it:
  1. Delete this file.
  2. Drop the `setup` call from bot/main.py setup_hook.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4

import discord
from discord.ext import commands

from sqlalchemy import any_, delete, select, update

from bot.config import settings
from bot.database import SessionLocal
from bot.models import MagicSet, Player, PodDraftEvent, PodDraftParticipant
from bot.services.lobby_embed import (
    LobbyReadyButtonView,
    ReadyCheckConfirmView,
    build_drafting_view,
    build_not_ready_view,
    ready_check_confirm_text,
    register_force_start_preview,
    register_settings_preview,
    render as render_lobby_embed,
    render_ready_check_progress,
)
from bot.services.pod_active import ACTIVE_POD_MANAGERS
from bot.services.pod_deck_color import SubmitDeckView
from bot.services.pod_draft_manager import PodDraftManager, roster_change_detail, start_manager
from bot.services.pod_drafts import draftmancer_url_for, player_arena_handle, seed_event_participants
from bot.services.pod_join_button import build_join_view
from bot.services.pod_link_dm import build_link_dm, format_thread_ref, send_lobby_link_dms, try_dm
from bot.sets import active_set_code
from bot.services.pod_format import format_display
from bot.services.pod_pairing_select import DEFAULT_PAIRING_MODE, pairing_label
from bot.services.pod_seating_select import seating_mode_label
from bot.services.player_stats import rank_players_for_set
from bot import emojis
from bot.commands.messages import MSG_LOBBY_FULL_PROMPT
from bot.tasks.pod_draft_reminder import build_lobby_open_body
from bot.commands.pod_draft import build_seeding_image_message_from_names, post_manual_seating_table, post_table
from bot.commands.pod_table import build_table_view
from bot.commands.test_group import refused_on_production, register_test_fallback
from bot.services.pod_format_select import FormatSelectView
from bot.services import pod_format_poll
from bot.services import pod_round_robin_vote
from bot.services.pod_settings_view import PodSettingsView
from bot.services.pod_drafts import normalize_player_name
from bot.services import pod_team
from bot.services.pod_swiss import Standing
from bot.services.pod_team_board import (
    TeamBoardData,
    build_board_data,
    build_team_board_views,
    build_team_round_view,
    build_team_summary,
    seating_attachment,
)
from bot.services.pod_team_flow import build_team_final_embed
from bot.services.pod_team_showcase import build_team_championship_view, format_team_trophy_title
from bot.services.pod_team_vote import (
    SIDE_TEAM,
    SIDE_WAIT,
    TEAM_VOTE_TEAM_EMOJI,
    TEAM_VOTE_TEAM_LABEL,
    TEAM_VOTE_WAIT_EMOJI,
    TEAM_VOTE_WAIT_LABEL,
    build_team_vote_locked_embed,
    build_team_vote_offer_embed,
    build_team_vote_waited_embed,
    team_vote_needed,
)
from bot.services.pod_tournament import (
    REVIEW_EMOJI,
    ParticipantDeckData,
    actor_label,
    build_champion_announcement_view,
    build_draft_review_message,
    build_trophy_hype_view,
    mark_trophy_match,
    pod_voice_channel_url,
    render_draft_review_embed,
    round_embed,
    start_tournament,
)
from bot.services.ping_roles import SET_CHAMPION_ROLE_NAME, champion_role_mention
from bot.services.pod_roles import find_role
from bot.slug import disambiguate_slug, slugify


log = logging.getLogger(__name__)

# In testlobby the invoker plays this seat in the fake roster.
_INVOKER_SEAT = "Noya"

# Module-level scratch store for the SubmitDeck POC; cleared on bot restart.
_TEST_DECK_COLORS: dict[int, str] = {}

# Fictional roster for the live-seeded tournament path (`podbracket` / `podswiss` / `round1`);
# most paths use the first 8, `podteam <count>` can seat up to all 10.
_LIVE_TEST_ROSTER = ["Ava", "Bram", "Cara", "Dex", "Eli", "Fern", "Gus", "Hana", "Iris", "Juno"]
_LIVE_TEST_POD_SIZES = ("6", "8", "10")
_LIVE_TEST_STATUS = "test"

# Arena handles for the fictional roster so the live round embeds exercise the real Round 1 arena
# rendering. Bram's handle diverges from the Discord name (shows the 'arena (discord)' form); the rest
# match (collapse to the handle alone).
_LIVE_TEST_ARENA = {
    "Bram": "driftwood#49190",
    "Cara": "Cara#10003",
    "Dex": "Dex#10004",
    "Eli": "Eli#10005",
    "Fern": "Fern#10006",
    "Gus": "Gus#10007",
    "Hana": "Hana#10008",
    "Iris": "Iris#10009",
    "Juno": "Juno#10010",
}


def _looks_like_prod_db() -> bool:
    url = settings.database_url or ""
    return "supabase" in url or "pooler" in url


def _ensure_invoker_player_sync(session, discord_id: int, display_name: str) -> str:
    """Find-or-create a local Player for the testlobby invoker so seat 1 receives the real pairing /
    deck DMs and can report its own matches."""
    player = session.execute(
        select(Player).where(Player.discord_id == str(discord_id))
    ).scalar_one_or_none()
    if player is None:
        taken = set(session.execute(select(Player.slug)).scalars().all())
        player = Player(
            slug=disambiguate_slug(slugify(display_name), taken),
            discord_id=str(discord_id),
            discord_username=display_name,
            display_name=display_name,
            active=True,
            leaderboard_opt_in=False,
        )
        session.add(player)
        session.flush()
    return player.id


def _ensure_fictional_player_sync(session, display_name: str, arena_name: str) -> str:
    """Find-or-create a discord-less Player carrying `arena_name` for a fictional live-test roster
    member, so the round embeds resolve a linked Arena handle. Keyed on the arena alias so repeated
    `!test` runs reuse the same row instead of piling up duplicates."""
    normalized = normalize_player_name(arena_name)
    existing = session.execute(
        select(Player).where(normalized == any_(Player.arena_aliases))
    ).scalar_one_or_none()
    if existing is not None:
        return existing.id
    taken = set(session.execute(select(Player.slug)).scalars().all())
    player = Player(
        slug=disambiguate_slug(slugify(display_name), taken),
        discord_id=f"testlobby-{normalized}",
        discord_username=display_name,
        display_name=display_name,
        arena_name=arena_name,
        arena_aliases=[normalized],
        active=True,
        leaderboard_opt_in=False,
    )
    session.add(player)
    session.flush()
    return player.id


def _seed_live_test_event_sync(
    channel_id: int, mode: str, roster: list[str] | None = None,
    invoker_id: int | None = None,
) -> tuple[str, str]:
    """Create a throwaway PodDraftEvent in the local DB. With `roster`, also seed seated participants
    (seat 0 linked to the invoker so they get the real DMs). With no roster, the event is lobby-only —
    participants arrive from the live Draftmancer session. Returns (event_id, session_id)."""
    now = datetime.now(timezone.utc)
    event_id = str(uuid4())
    session_id = f"TESTLOBBY-{channel_id}"
    with SessionLocal() as session:
        session.add(PodDraftEvent(
            id=event_id,
            event_date=now.date(),
            event_time=now,
            set_code=active_set_code(),
            name="Testlobby Live Pod",
            draftmancer_session=session_id,
            discord_thread_id=str(channel_id),
            socket_status=_LIVE_TEST_STATUS,
            pairing_mode=mode,
        ))
        session.flush()
        if roster:
            seed_event_participants(session, event_id, roster)
            for seat, name in enumerate(roster):
                session.execute(
                    update(PodDraftParticipant)
                    .where(
                        PodDraftParticipant.event_id == event_id,
                        PodDraftParticipant.draftmancer_name == name,
                    )
                    .values(seat_index=seat)
                )
            for name in roster:
                arena = _LIVE_TEST_ARENA.get(name)
                if arena is None:
                    continue
                player_id = _ensure_fictional_player_sync(session, name, arena)
                session.execute(
                    update(PodDraftParticipant)
                    .where(
                        PodDraftParticipant.event_id == event_id,
                        PodDraftParticipant.draftmancer_name == name,
                    )
                    .values(player_id=player_id)
                )
            if invoker_id is not None:
                player_id = _ensure_invoker_player_sync(session, invoker_id, roster[0])
                session.execute(
                    update(PodDraftParticipant)
                    .where(
                        PodDraftParticipant.event_id == event_id,
                        PodDraftParticipant.draftmancer_name == roster[0],
                    )
                    .values(player_id=player_id)
                )
        session.commit()
    return event_id, session_id


# Fictional pre-claims so a single real click by the invoker crosses the table threshold and
# materializes the overflow table. Negative ids mark fixtures so the ping block renders them as
# plain names rather than trying to mention a real user.
_TABLE_PRESEED = [(-1, "Ava"), (-2, "Bram"), (-3, "Cara"), (-4, "Dex"), (-5, "Eli")]


def _table_test_base_name() -> str:
    return f"{active_set_code()} Split Test"


def _seed_table_source_sync(channel_id: int) -> str:
    """Seed a stand-in 'Table 1' source pod so `!test table` has a real event to clone. Returns its id."""
    now = datetime.now(timezone.utc)
    event_id = str(uuid4())
    with SessionLocal() as session:
        session.add(PodDraftEvent(
            id=event_id,
            event_date=now.date(),
            event_time=now,
            set_code=active_set_code(),
            name=_table_test_base_name(),
            draftmancer_session=f"TESTSPLIT-{channel_id}",
            discord_thread_id=str(channel_id),
            socket_status=_LIVE_TEST_STATUS,
            pairing_mode=DEFAULT_PAIRING_MODE,
        ))
        session.commit()
    return event_id


def _purge_table_family_sync(base_name: str) -> list[tuple[str, str]]:
    """Delete the source pod and every table opened off it. Returns (event_id, thread_id) so the caller
    can evict managers and remove the created threads."""
    with SessionLocal() as session:
        rows = session.execute(
            select(PodDraftEvent.id, PodDraftEvent.discord_thread_id)
            .where(PodDraftEvent.name.ilike(f"{base_name}%"))
        ).all()
        ids = [row[0] for row in rows]
        if ids:
            session.execute(delete(PodDraftEvent).where(PodDraftEvent.id.in_(ids)))
            session.commit()
    return [(row[0], row[1]) for row in rows]


def _purge_live_test_pods_sync(channel_id: int) -> list[str]:
    """Delete prior live-test events for this channel (cascades to participants + matches). Returns
    the purged event ids so the caller can evict their managers."""
    with SessionLocal() as session:
        ids = session.execute(
            select(PodDraftEvent.id).where(
                PodDraftEvent.discord_thread_id == str(channel_id),
            )
        ).scalars().all()
        if ids:
            session.execute(delete(PodDraftEvent).where(PodDraftEvent.id.in_(ids)))
            session.commit()
    return list(ids)


def _build_live_test_manager(
    bot, event_id: str, session_id: str, channel_id: int, mode: str, roster: list[str],
) -> PodDraftManager:
    """A socket-less manager wired to drive the real tournament code. Never calls connect()."""
    manager = PodDraftManager(
        bot, event_id, session_id, channel_id, active_set_code(), len(roster),
        event_name="Testlobby Live Pod",
        draftmancer_url=f"{settings.draftmancer_web_url}/?session={session_id}",
    )
    manager.tournament_roster = list(roster)
    manager.pairing_mode = mode
    return manager


async def _refuse_if_prod(ctx) -> bool:
    if _looks_like_prod_db():
        await ctx.send(
            "⚠️ Refusing — `DATABASE_URL` looks like prod. The live testlobby pod only runs against "
            "the local dev DB."
        )
        return True
    return False


async def _evict_test_managers_for_channel(channel_id: int) -> None:
    """Drop any lingering manager for this channel so a fresh `!test` preview isn't intercepted by a
    prior podX run's manager — otherwise its current_round>0 trips the pairing-lock guard on the
    preview's Settings panel."""
    stale = [m for m in ACTIVE_POD_MANAGERS.values() if m.thread_id == channel_id]
    for mgr in stale:
        for task in (mgr.grace_task, mgr.championship_task):
            if task is not None and not task.done():
                task.cancel()
        await mgr.disconnect_safely()


async def _purge_and_reset_test(ctx) -> None:
    """Delete prior test events for this channel, disconnect/evict their managers, and clear the thread."""
    purged = await asyncio.to_thread(_purge_live_test_pods_sync, ctx.channel.id)
    for old_id in purged:
        old = ACTIVE_POD_MANAGERS.get(old_id)
        if old is not None:
            for task in (old.grace_task, old.championship_task):
                if task is not None and not task.done():
                    task.cancel()
            await old.disconnect_safely()
    await _delete_last_test_messages(ctx.channel)


def _top_ranked_names_sync(n: int) -> list[str]:
    with SessionLocal() as session:
        set_id = session.execute(
            select(MagicSet.id).where(MagicSet.code == active_set_code())
        ).scalar_one_or_none()
        if not set_id:
            return []
        return [r.display_name for r in rank_players_for_set(session, set_id)[:n]]


_SEEDING_FILLERS = ["Marina", "Quill", "Ridley", "Sable", "Tovo", "Umbra"]


async def _post_test_seeding(ctx, count: int = 8) -> None:
    """Render the /pod-seeding embed (seat-column table + the round-table PNG) for `count` players from
    the local leaderboard, padding with fictional fillers when the DB has fewer. Bypasses the sesh fetch;
    local DB only."""
    ranked = await asyncio.to_thread(_top_ranked_names_sync, count)
    if not ranked:
        await ctx.send("No ranked players in the local DB — run seed_local_players + refresh_stats first.")
        return
    yes = ranked[:count]
    yes += [f for f in _SEEDING_FILLERS if f not in yes][: max(0, count - len(yes))]
    file, embed = await asyncio.to_thread(build_seeding_image_message_from_names, yes)
    await post_table(ctx.bot, ctx.channel, file, embed)


async def _start_live_test_pod(ctx, mode: str, count: int = 8) -> None:
    """Seed a real event + socket-less manager and hand off to the prod start_tournament, so the
    posted result dropdowns drive the real _handle_result_submission. Seat 1 is the invoker so they
    receive the real pairing / deck DMs. Local DB only."""
    if await _refuse_if_prod(ctx):
        return
    await _purge_and_reset_test(ctx)
    channel_id = ctx.channel.id
    roster = [ctx.author.display_name] + _LIVE_TEST_ROSTER[1:count]
    event_id, session_id = await asyncio.to_thread(
        _seed_live_test_event_sync, channel_id, mode, roster, ctx.author.id,
    )
    manager = _build_live_test_manager(ctx.bot, event_id, session_id, channel_id, mode, roster)
    ACTIVE_POD_MANAGERS[event_id] = manager
    log.info(f"[testlobby] live {mode} pod seeded event={event_id} channel={channel_id}")
    await start_tournament(manager)


async def _preview_link_dms(ctx) -> None:
    """The `dmlink` path: DM the caller both lobby-open DM strings (linked + unlinked) against this
    channel, so every string can be reviewed in one inbox regardless of link state."""
    session_id = f"{active_set_code()}-TestOpen"
    thread_ref = format_thread_ref(ctx.channel)
    handle = await asyncio.to_thread(_arena_handle_for, str(ctx.author.id))
    linked_body, linked_view = build_link_dm(
        session_id=session_id, thread_ref=thread_ref,
        arena_name=handle or "YourArena#12345", rsvp="yes",
    )
    unlinked_body, unlinked_view = build_link_dm(
        session_id=session_id, thread_ref=thread_ref, arena_name=None, rsvp="maybe",
    )
    landed = 0
    for body, view in ((linked_body, linked_view), (unlinked_body, unlinked_view)):
        if await try_dm(ctx.bot, str(ctx.author.id), body, view):
            landed += 1
    if landed:
        note = "" if handle else " (no Arena linked, so the linked DM used a placeholder handle)"
        await ctx.send(f"🧪 Sent {landed}/2 link DMs to your DMs.{note}")
    else:
        await ctx.send("⚠️ Couldn't DM you — open DMs from server members and try again.")


_TEST_LOBBY_THREAD_NAME = "Pod Draft — Test"


async def _preview_full_lobby(ctx) -> None:
    """The `lobby` path: replicate a real lobby open end to end. Clear prior test threads, create a fresh
    thread, post the lobby-open message + Join Draft button inside it, then run the real DM path with the
    caller as the only recipient — so they receive exactly the one DM their own link state earns."""
    session_id = f"{active_set_code()}-TestOpen"
    parent = ctx.channel.parent if isinstance(ctx.channel, discord.Thread) else ctx.channel
    await _clear_test_lobby_threads(parent)
    thread = await parent.create_thread(
        name=f"{active_set_code()} {_TEST_LOBBY_THREAD_NAME}", type=discord.ChannelType.public_thread,
    )
    body = build_lobby_open_body(draftmancer_url_for(session_id), ctx.author.mention)
    await thread.send(
        body, view=build_join_view(session_id),
        allowed_mentions=discord.AllowedMentions(users=True),
    )
    sent = await send_lobby_link_dms(
        ctx.bot, session_id=session_id, thread=thread,
        recipients=[(str(ctx.author.id), ctx.author.display_name, "yes")],
    )
    if sent:
        await ctx.send(f"🧪 Opened {thread.mention} and sent your lobby DM.")
    else:
        await ctx.send(f"🧪 Opened {thread.mention}. No DM sent — Draft DMs off or your DMs are closed.")


async def _clear_test_lobby_threads(parent) -> None:
    """Delete threads left by prior `!test lobby` runs so repeated previews don't pile up. Matched by the
    test thread name, so real pod threads are never touched; sweeps active and recently archived threads."""
    stale = [t for t in parent.threads if _TEST_LOBBY_THREAD_NAME in t.name]
    try:
        async for archived in parent.archived_threads(limit=100):
            if _TEST_LOBBY_THREAD_NAME in archived.name:
                stale.append(archived)
    except discord.HTTPException:
        pass
    for thread in stale:
        try:
            await thread.delete()
        except discord.HTTPException:
            pass


def _arena_handle_for(discord_id: str) -> str | None:
    with SessionLocal() as session:
        return player_arena_handle(session, discord_id)


def _unlink_arena(discord_id: str) -> bool:
    """Clear the caller's Arena handle and aliases so the unlinked Join Draft nudge can be replayed.
    Returns whether anything was cleared."""
    with SessionLocal() as session:
        player = session.execute(
            select(Player).where(Player.discord_id == discord_id)
        ).scalar_one_or_none()
        if player is None or (player.arena_name is None and not player.arena_aliases):
            return False
        player.arena_name = None
        player.arena_aliases = []
        session.commit()
        return True


async def _start_live_test_lobby(ctx) -> None:
    """Seed a lobby-only event and connect a real manager to a live Draftmancer session, so the real
    lobby + ready-check flow runs. Local DB only."""
    if await _refuse_if_prod(ctx):
        return
    await _purge_and_reset_test(ctx)
    channel_id = ctx.channel.id
    event_id, session_id = await asyncio.to_thread(
        _seed_live_test_event_sync, channel_id, DEFAULT_PAIRING_MODE,
    )
    url = f"{settings.draftmancer_web_url}/?session={session_id}"
    log.info(f"[testlobby] live lobby connecting event={event_id} session={session_id}")
    manager = await start_manager(
        ctx.bot, event_id, session_id, channel_id, active_set_code(), 8,
        event_name="Testlobby Live Pod", draftmancer_url=url,
    )
    if manager is None:
        await ctx.send("⚠️ Could not connect to Draftmancer — see logs.")
        return
    await ctx.send(f"🧪 Connected to Draftmancer `{session_id}`.")


async def _arm_pod_team_command(ctx) -> None:
    """Register a socket-less manager holding a fake six-player lobby for this channel, so `/pod-team`
    finds a pod and posts its card through the production path with no Draftmancer session open. Local
    DB only."""
    if await _refuse_if_prod(ctx):
        return
    await _purge_and_reset_test(ctx)
    channel_id = ctx.channel.id
    roster = [ctx.author.display_name] + _LIVE_TEST_ROSTER[1:6]
    event_id, session_id = await asyncio.to_thread(
        _seed_live_test_event_sync, channel_id, DEFAULT_PAIRING_MODE,
    )
    manager = _build_live_test_manager(
        ctx.bot, event_id, session_id, channel_id, DEFAULT_PAIRING_MODE, roster,
    )
    manager.session_users = [{"userID": f"testlobby-{name}", "userName": name} for name in roster]
    ACTIVE_POD_MANAGERS[event_id] = manager
    log.info(f"[testlobby] armed /pod-team event={event_id} channel={channel_id} lobby={len(roster)}")
    await ctx.send(f"🧪 Fake {len(roster)}-player lobby armed. Run `/pod-team` in this channel.")


async def _start_test_table(ctx) -> None:
    """Drive the real `/pod-table` flow: seed a source pod, then post the prod claim card preseeded to
    one below threshold so the invoker's single click materializes the overflow table (real thread +
    Draftmancer lobby + tournament manager). Local DB only."""
    if await _refuse_if_prod(ctx):
        return
    purged = await asyncio.to_thread(_purge_table_family_sync, _table_test_base_name())
    for old_id, old_thread in purged:
        mgr = ACTIVE_POD_MANAGERS.get(old_id)
        if mgr is not None:
            for task in (mgr.grace_task, mgr.championship_task):
                if task is not None and not task.done():
                    task.cancel()
            await mgr.disconnect_safely()
        if old_thread and old_thread != str(ctx.channel.id):
            thread = ctx.bot.get_channel(int(old_thread))
            if thread is not None:
                try:
                    await thread.delete()
                except discord.HTTPException:
                    pass
    source_id = await asyncio.to_thread(_seed_table_source_sync, ctx.channel.id)
    preseed = _TABLE_PRESEED[: max(0, settings.pod_table_open_threshold - 1)]
    log.info(f"[testlobby] table preview seeded source={source_id} preseed={len(preseed)}")
    lobby_channel = ctx.channel.parent if isinstance(ctx.channel, discord.Thread) else ctx.channel
    view = await build_table_view(ctx.bot, source_id, lobby_channel=lobby_channel, preseeded_claims=preseed)
    if view is None:
        await ctx.send("could not seed the table source event")
        return
    view.claim_message = await ctx.send(embed=view.render_embed(), view=view)
    await view.activate()


async def _test_submit_deck_color(interaction: discord.Interaction, color: str) -> None:
    _TEST_DECK_COLORS[interaction.user.id] = color
    log.info(f"testlobby deck color saved: user={interaction.user.id} color={color}")


async def _test_lookup_deck_state(interaction: discord.Interaction) -> str | None:
    return _TEST_DECK_COLORS.get(interaction.user.id)


def _submit_deck_view() -> SubmitDeckView:
    """Build a SubmitDeckView (button form) for the testlobby channel preview."""
    return SubmitDeckView(_test_submit_deck_color, _test_lookup_deck_state)


def _review_preview_roster() -> list[dict]:
    """Fixture roster for the `!test review` preview — fictional seats with varied colors, records, slugs."""
    colors = ["WU", "BRg", "UG", "R", "WUBRG", "BR", "WGu", "UB"]
    records = ["3-0", "2-1", "2-1", "2-1", "1-2", "1-2", "1-2", "0-3"]
    return [
        {
            "seat_index": i, "name": name, "colors": colors[i % len(colors)],
            "result": records[i % len(records)], "slug": slugify(name),
        }
        for i, name in enumerate(_LIVE_TEST_ROSTER[:8])
    ]


# Fictional roster shaped like production: long parentheticals, a u/ handle, an initialism, short handles.
# Arena handles diverge from the Discord display, mirroring how few players match across the two.
_TEAM1 = ["Thistledown (Maramir)", "SilverbackGorilla", "mo"]
_TEAM2 = ["u/Longpost_Enjoyer", "C. Vulgaris", "yo"]
_TEAM_ARENA = {
    "Thistledown (Maramir)": "quickfox#41922",
    "SilverbackGorilla": "sbg#00071",
    "mo": "melodious#88123",
    "u/Longpost_Enjoyer": "postman#55010",
    "C. Vulgaris": "chard#64000",
    "yo": "yolanda#12001",
}


def _team_preview_board_data() -> TeamBoardData:
    """Fixture TeamBoardData for the no-DB board snapshot, rendered through the prod board builder so
    the preview can't drift from the live layout. One pre-reported match shows the recolored button;
    Blue at 0 shows the no-Wins header. Match ids are fake, so the Report buttons are inert."""
    seat_order = [name for pair in zip(_TEAM1, _TEAM2) for name in pair]
    teams = pod_team.assign_teams(seat_order)
    team_rows = [(name, teams[name]) for name in seat_order]
    displays = {
        normalize_player_name(name): {"display_name": name, "arena": _TEAM_ARENA[name]}
        for name in seat_order
    }
    matches = []
    for round_num in (1, 2, 3):
        for a, b in pod_team.pair_round(_TEAM1, _TEAM2, round_num):
            matches.append({
                "match_id": f"team-preview-{len(matches) + 1}", "round": round_num,
                "a_name": a, "b_name": b, "winner_name": None, "score": None,
            })
    matches[0].update(winner_name=matches[0]["a_name"], score="2-0")
    return build_board_data("team-preview", team_rows, matches, displays, finalized=False)


def _team_round_preview_data(clinch: bool = False) -> TeamBoardData:
    """Fixture for the per-round board snapshot at the moment round 2 first goes up: two of round 1's
    three matches are in, so round 2 has one live matchup and two still waiting. That is the exact
    state the ⌛ marker exists for. Winners alternate so both teams carry Wins; match ids are fake, so
    the buttons are inert.

    `clinch` instead reports rounds 1 and 2 with Green taking five, putting the draft out of reach
    with round 3 still open — the state where the score reads as won before the last match lands."""
    seat_order = [name for pair in zip(_TEAM1, _TEAM2) for name in pair]
    teams = pod_team.assign_teams(seat_order)
    team_rows = [(name, teams[name]) for name in seat_order]
    displays = {
        normalize_player_name(name): {"display_name": name, "arena": _TEAM_ARENA[name]}
        for name in seat_order
    }
    matches = []
    for round_num in (1, 2, 3):
        for a, b in pod_team.pair_round(_TEAM1, _TEAM2, round_num):
            matches.append({
                "match_id": f"team-round-preview-{len(matches) + 1}", "round": round_num,
                "a_name": a, "b_name": b, "winner_name": None, "score": None,
            })
    if clinch:
        for index, m in enumerate(matches[:6]):
            winner = m["b_name"] if index == 1 else m["a_name"]
            m.update(winner_name=winner, score="2-1" if index % 2 else "2-0")
    else:
        matches[0].update(winner_name=matches[0]["a_name"], score="2-0")
        matches[1].update(winner_name=matches[1]["b_name"], score="2-1")
    return build_board_data("team-round-preview", team_rows, matches, displays, finalized=False)


async def _send_team_summary(ctx, data: TeamBoardData) -> None:
    embed, seating_png = build_team_summary(data)
    await ctx.send(embed=embed, file=seating_attachment(seating_png))


def _team_reveal_preview_parts() -> tuple[list[str], dict[str, str]]:
    """Seat order and teams for the draft-start reveal: the ready-check card carrying team columns,
    the state a team pod lands in the moment the draft starts."""
    seat_order = [name for pair in zip(_TEAM1, _TEAM2) for name in pair]
    return seat_order, pod_team.assign_teams(seat_order)


_TEAM_PREVIEW_RECORDS = [(3, 0), (2, 1), (1, 2), (3, 0), (0, 3), (0, 3)]
_TEAM_PREVIEW_COLORS = ["WU", "BR", "WBg", "UG", "RG", "WB"]
_TEAM_PREVIEW_CAPTIONS = [
    "fliers win games", "rakdos did rakdos things", None,
    "undefeated on the losing side", None, "never drew the bomb",
]


def _team_standings_preview_embed() -> discord.Embed:
    """Fixture final standings through the prod builder: Green wins 6-3, one personal 3-0 trophy,
    deck colors on every row."""
    names = _TEAM1 + _TEAM2
    teams = {**{n: pod_team.TEAM_A for n in _TEAM1}, **{n: pod_team.TEAM_B for n in _TEAM2}}
    standings = [
        Standing(rank=i + 1, player_id=n, player_name=n, wins=w, losses=losses,
                 omw_pct=0.0, gw_pct=0.0, ogw_pct=0.0)
        for i, (n, (w, losses)) in enumerate(zip(names, _TEAM_PREVIEW_RECORDS))
    ]
    displays = {normalize_player_name(n): {"display_name": n} for n in names}
    player_colors = {
        normalize_player_name(n): colors for n, colors in zip(names, _TEAM_PREVIEW_COLORS)
    }
    return build_team_final_embed(
        standings, teams, event_name="MSH Pod Draft #4 - July 1", displays=displays,
        pending_count=0, player_colors=player_colors,
    )


def _team_preview_showcase_parts():
    names = _TEAM1 + _TEAM2
    teams = {**{n: pod_team.TEAM_A for n in _TEAM1}, **{n: pod_team.TEAM_B for n in _TEAM2}}
    standings = [
        Standing(rank=i + 1, player_id=n, player_name=n, wins=w, losses=losses,
                 omw_pct=0.0, gw_pct=0.0, ogw_pct=0.0)
        for i, (n, (w, losses)) in enumerate(zip(names, _TEAM_PREVIEW_RECORDS))
    ]
    displays = {normalize_player_name(n): {"display_name": n} for n in names}
    player_colors = {
        normalize_player_name(n): colors for n, colors in zip(names, _TEAM_PREVIEW_COLORS)
    }
    deck_data = {
        normalize_player_name(n): ParticipantDeckData(
            colors=colors, screenshot_url=_TEST_DECK_SCREENSHOT_URL, screenshot_caption=caption,
        )
        for n, colors, caption in zip(names, _TEAM_PREVIEW_COLORS, _TEAM_PREVIEW_CAPTIONS)
    }
    return standings, teams, displays, player_colors, deck_data


def _team_championship_preview_view() -> discord.ui.LayoutView:
    """Fixture team championship card through the prod builder: Green wins 6-3, both galleries."""
    standings, teams, displays, player_colors, deck_data = _team_preview_showcase_parts()
    return build_team_championship_view(
        standings, teams, event_name="MSH Pod Draft #4 - July 1", displays=displays,
        player_colors=player_colors, deck_data=deck_data,
    )


def _team_trophy_hype_preview_view() -> discord.ui.LayoutView:
    """Fixture team 3-0 hype card: two 3-0s (one per team) so the divider shows."""
    standings, teams, displays, player_colors, deck_data = _team_preview_showcase_parts()
    hyped = [
        Standing(rank=i + 1, player_id=n, player_name=n, wins=3, losses=0,
                 omw_pct=0.0, gw_pct=0.0, ogw_pct=0.0)
        for i, n in enumerate((_TEAM1[0], _TEAM2[0]))
    ]
    return build_trophy_hype_view(
        hyped, event_name="MSH Pod Draft #4 - July 1", displays=displays,
        player_colors=player_colors, deck_data=deck_data,
        format_title=format_team_trophy_title,
    )


_TEAM_VOTE_POD_SIZE = 6


def _team_vote_seed() -> dict[str, str]:
    """Three prefilled voters so the previewer's own click is the fourth — the majority that locks it."""
    return {f"seed-{i}": name for i, (_, name) in enumerate(_LINKED_EIGHT[1:4])}


class _TeamVotePreviewView(discord.ui.View):
    """Interactible preview of the two-sided Team-Draft vote. Three votes are prefilled on the Team side, so
    the previewer's Team click is the fourth — the majority that locks the pod to Team Draft and proposes a
    Ready Check. A Wait majority resolves the card to the waiting state. No live pod behind it."""

    def __init__(self) -> None:
        super().__init__(timeout=900)
        self.team = list(_team_vote_seed().values())
        self.wait: list[str] = []

    @discord.ui.button(
        emoji=TEAM_VOTE_TEAM_EMOJI, label=TEAM_VOTE_TEAM_LABEL, style=discord.ButtonStyle.primary)
    async def team_vote(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._vote(interaction, SIDE_TEAM)

    @discord.ui.button(
        emoji=TEAM_VOTE_WAIT_EMOJI, label=TEAM_VOTE_WAIT_LABEL, style=discord.ButtonStyle.secondary)
    async def wait_vote(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._vote(interaction, SIDE_WAIT)

    async def _vote(self, interaction: discord.Interaction, side: str) -> None:
        needed = team_vote_needed(_TEAM_VOTE_POD_SIZE)
        name = interaction.user.display_name
        on_side = name in (self.team if side == SIDE_TEAM else self.wait)
        self.team = [voter for voter in self.team if voter != name]
        self.wait = [voter for voter in self.wait if voter != name]
        if not on_side:
            (self.team if side == SIDE_TEAM else self.wait).append(name)
        if len(self.team) >= needed:
            await interaction.response.edit_message(
                embed=build_team_vote_locked_embed(self.team, self.wait), view=None,
            )
            await interaction.followup.send(
                MSG_LOBBY_FULL_PROMPT.format(count=emojis.mana_number(_TEAM_VOTE_POD_SIZE)),
                view=LobbyReadyButtonView(draftmancer_url=_DRAFTMANCER_URL),
            )
            return
        if len(self.wait) >= needed:
            await interaction.response.edit_message(
                embed=build_team_vote_waited_embed(self.team, self.wait), view=None)
            return
        await interaction.response.edit_message(
            embed=build_team_vote_offer_embed(self.team, self.wait, _TEAM_VOTE_POD_SIZE), view=self)


_ROUND_ROBIN_POD_SIZE = 4


def _round_robin_vote_seed() -> list[str]:
    """Three prefilled voters so the previewer's own click is the fourth — the unanimous vote that locks it."""
    return [name for _, name in _LINKED_EIGHT[1:4]]


class _RoundRobinVotePreviewView(discord.ui.View):
    """Interactible preview of the Pick 2 offer a lobby stalled at four gets. Three votes are prefilled on the
    Pick 2 side, so the previewer's click is the fourth — the unanimous vote that locks Pick 2 Round Robin.
    Clicking Wait instead leaves the card open, since waiting is not a verdict. No live pod behind it."""

    def __init__(self) -> None:
        super().__init__(timeout=900)
        self.round_robin = _round_robin_vote_seed()
        self.wait: list[str] = []

    @discord.ui.button(
        emoji=pod_round_robin_vote.ROUND_ROBIN_EMOJI, label=pod_round_robin_vote.ROUND_ROBIN_LABEL,
        style=discord.ButtonStyle.success)
    async def round_robin_vote(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._vote(interaction, pod_round_robin_vote.SIDE_ROUND_ROBIN)

    @discord.ui.button(
        emoji=pod_round_robin_vote.WAIT_EMOJI, label=pod_round_robin_vote.WAIT_LABEL,
        style=discord.ButtonStyle.secondary)
    async def wait_vote(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._vote(interaction, pod_round_robin_vote.SIDE_WAIT)

    async def _vote(self, interaction: discord.Interaction, side: str) -> None:
        name = interaction.user.display_name
        self.round_robin = [voter for voter in self.round_robin if voter != name]
        self.wait = [voter for voter in self.wait if voter != name]
        if side == pod_round_robin_vote.SIDE_ROUND_ROBIN:
            self.round_robin.append(name)
        else:
            self.wait.append(name)
        if len(self.round_robin) >= pod_round_robin_vote.votes_needed(_ROUND_ROBIN_POD_SIZE):
            await interaction.response.edit_message(
                embed=pod_round_robin_vote.build_locked_embed(self.round_robin, self.wait), view=None)
            return
        await interaction.response.edit_message(
            embed=pod_round_robin_vote.build_offer_embed(
                self.round_robin, self.wait, _ROUND_ROBIN_POD_SIZE),
            view=self,
        )


class _FormatPollPreviewView(discord.ui.View):
    """Interactible preview of the multiple-choice flashback format tally: the Add Format button first, then
    one working button per option. Votes are prefilled so the bars read as a mid-evening tally. No live pod
    behind it."""

    def __init__(self) -> None:
        super().__init__(timeout=900)
        self.options = pod_format_poll.build_options()
        self.votes: dict[str, list[str]] = {code: [] for code in self.options}
        self.adders: dict[str, str] = {}
        self.poll_message: discord.Message | None = None
        self._seed_demo_tally()
        self._rebuild()

    def _seed_demo_tally(self) -> None:
        """Prefill a mid-evening tally that shows every grouping case: a clear leader, a two-set tie sharing
        one bar, and a run of unvoted sets sharing the closing bar. One set carries an "added by" credit so
        the write-in attribution stays visible."""
        names = [name for _, name in _LINKED_EIGHT]
        self.votes[pod_format_poll.ANY_FLASHBACK_CODE] = [names[1], names[2], names[4]]
        seeds = {
            "FIN": [names[0], names[1], names[2], names[3]],
            "ECL": [names[6], names[7]],
            "TLA": [names[5]],
            "SOS": [names[6]],
            "MH3": [],
            "WOE": [],
        }
        for code, voters in seeds.items():
            self.options.append(code)
            self.votes[code] = voters
        self.adders["SOS"] = names[5]

    def _rebuild(self) -> None:
        self.options = pod_format_poll.order_options(self.options, self.votes)
        self.clear_items()
        self.add_item(self._add_button())
        for code, label_override, row in pod_format_poll.format_poll_button_layout(self.options):
            self.add_item(self._option_button(code, label_override, row))

    def _option_button(self, code: str, label_override: str | None = None, row: int | None = None) -> discord.ui.Button:
        label, emoji = pod_format_poll.option_button_face(code)
        if label_override is not None:
            label = label_override
        button = discord.ui.Button(
            label=label, emoji=emoji, style=discord.ButtonStyle.secondary, row=row,
        )

        async def callback(interaction: discord.Interaction) -> None:
            await self._vote(interaction, code)

        button.callback = callback
        return button

    def _add_button(self) -> discord.ui.Button:
        button = discord.ui.Button(
            emoji=pod_format_poll.add_button_emoji(), label=pod_format_poll.ADD_BUTTON_LABEL,
            style=discord.ButtonStyle.secondary, row=0)

        async def callback(interaction: discord.Interaction) -> None:
            await interaction.response.send_modal(_AddFormatPreviewModal(self))

        button.callback = callback
        return button

    def add_write_in(self, code: str, adder: str) -> None:
        if code not in self.options:
            self.options.append(code)
            self.adders[code] = adder
            self._rebuild()

    def ensure_vote(self, name: str, code: str) -> None:
        voters = self.votes.setdefault(code, [])
        if name not in voters:
            voters.append(name)

    async def refresh(self, interaction: discord.Interaction) -> None:
        if interaction.message is not None:
            self.poll_message = interaction.message
        await interaction.response.edit_message(
            embed=pod_format_poll.build_format_poll_embed(self.options, self.votes, self.adders),
            view=self,
        )

    async def _vote(self, interaction: discord.Interaction, code: str) -> None:
        pod_format_poll.toggle_vote(self.votes, self.options, interaction.user.display_name, code)
        self._rebuild()
        await self.refresh(interaction)


class _AddFormatPreviewModal(discord.ui.Modal, title=pod_format_poll.ADD_MODAL_TITLE):
    code = discord.ui.TextInput(
        label=pod_format_poll.ADD_MODAL_FIELD, placeholder=pod_format_poll.ADD_MODAL_PLACEHOLDER,
        min_length=2, max_length=100,
    )

    def __init__(self, view: "_FormatPollPreviewView") -> None:
        super().__init__()
        self.preview = view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        codes = pod_format_poll.normalize_write_ins(str(self.code.value))
        if not codes:
            await interaction.response.send_message("Enter set codes like DSK FIN MH3.", ephemeral=True)
            return
        name = interaction.user.display_name
        for code in codes:
            self.preview.add_write_in(code, name)
            self.preview.ensure_vote(name, code)
        await self.preview.refresh(interaction)


class _ReadyCheckPreviewView(discord.ui.View):
    """Preview-only Ready Check button for `!test readyunlinked`: drives the real warn-but-allow confirm
    ephemerally, exactly as the initiator sees it, with no live pod behind it. The seated count is one short
    of the floor and odd, so the preview carries every warning line at once."""

    def __init__(self) -> None:
        super().__init__(timeout=900)

    @discord.ui.button(label="Start Ready Check", style=discord.ButtonStyle.success)
    async def ready_check(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        floor = settings.pod_draft_min_ready_players
        await interaction.response.send_message(
            ready_check_confirm_text(floor - 1, floor, [_UNLINKED_SEAT]),
            view=ReadyCheckConfirmView(None, None, None),
            ephemeral=True,
        )


_TEST_DECK_SCREENSHOT_URL = "https://placehold.co/1280x720/2b2d31/ffffff/png?text=Deck+Screenshot"


def _trophy_hype_preview() -> discord.ui.LayoutView:
    """The #trophy-hype champion card rendered from fixture data via the prod builder."""
    champion = Standing(
        rank=1, player_id="Ava", player_name="Ava", wins=3, losses=0,
        omw_pct=0.0, gw_pct=0.0, ogw_pct=0.0,
    )
    key = normalize_player_name(champion.player_name)
    return build_trophy_hype_view(
        [champion],
        event_name="SOS Pod Draft #6 - Jun 3",
        displays={key: {"display_name": "Ava"}},
        player_colors={key: "URg"},
        deck_data={key: ParticipantDeckData(
            colors="URg",
            screenshot_url=_TEST_DECK_SCREENSHOT_URL,
            screenshot_caption="Izzet spells with a green splash for the bombs",
        )},
        guild_id=1,
        thread_id=1,
    )


_CHAMPION_PREVIEW_NAMES = (
    "Thistledown (Maramir)", "u/Longpost_Enjoyer", "SilverbackGorilla⭐-_-💧", "C. Vulgaris",
    "driftwood", "quickfox", "mo", "yo",
)
_CHAMPION_PREVIEW_RECORDS = ((3, 0), (2, 1), (2, 1), (2, 1), (1, 2), (1, 2), (1, 2), (0, 3))
_CHAMPION_PREVIEW_COLORS = ("URg", "WB", "RG", "UB", "WU", "BRw", "GW", "WUBRG")
_CHAMPION_PREVIEW_CAPTIONS = (
    "three bombs and a prayer", "fliers win games", None, "rakdos did rakdos things",
    None, "never drew the bomb", None, "five colors, zero wins",
)


def _preview_deck_url(rank: int) -> str:
    """A placeholder deck shot labeled with its finishing place, so the gallery grid reads as eight
    distinct decks instead of one image repeated."""
    return f"https://placehold.co/1280x720/2b2d31/ffffff/png?text=Deck+%23{rank}"


def _championship_preview_name() -> str:
    return f"👑 {active_set_code()} Set Championship"


def _champion_preview_parts():
    """Fixture parts for both championship surfaces. The winner carries a parenthetical alias, so the
    previews show how an aliased display name reads in each headline."""
    standings = [
        Standing(rank=i + 1, player_id=n, player_name=n, wins=wins, losses=losses,
                 omw_pct=0.0, gw_pct=0.0, ogw_pct=0.0)
        for i, (n, (wins, losses)) in enumerate(zip(_CHAMPION_PREVIEW_NAMES, _CHAMPION_PREVIEW_RECORDS))
    ]
    displays = {normalize_player_name(n): {"display_name": n} for n in _CHAMPION_PREVIEW_NAMES}
    player_colors = {
        normalize_player_name(n): colors
        for n, colors in zip(_CHAMPION_PREVIEW_NAMES, _CHAMPION_PREVIEW_COLORS)
    }
    deck_data = {
        normalize_player_name(n): ParticipantDeckData(
            colors=colors, screenshot_url=_preview_deck_url(rank), screenshot_caption=caption,
        )
        for rank, (n, colors, caption) in enumerate(zip(
            _CHAMPION_PREVIEW_NAMES, _CHAMPION_PREVIEW_COLORS, _CHAMPION_PREVIEW_CAPTIONS), start=1)
    }
    return standings, displays, player_colors, deck_data


def _champion_announcement_preview(guild) -> discord.ui.LayoutView:
    standings, displays, player_colors, deck_data = _champion_preview_parts()
    return build_champion_announcement_view(
        standings,
        event_name=_championship_preview_name(),
        displays=displays,
        player_colors=player_colors,
        deck_data=deck_data,
        leaderboard_url=settings.leaderboard_url,
        guild_id=1,
        thread_id=1,
        champion_mention=champion_role_mention(find_role(guild, SET_CHAMPION_ROLE_NAME)),
    )


def _champion_hype_preview(guild) -> discord.ui.LayoutView:
    """The #trophy-hype card for the same fixture championship, so its headline can be read beside the
    announcement's."""
    standings, displays, player_colors, deck_data = _champion_preview_parts()
    return build_trophy_hype_view(
        standings[:1],
        event_name=_championship_preview_name(),
        displays=displays,
        player_colors=player_colors,
        deck_data=deck_data,
        guild_id=1,
        thread_id=1,
        champion_mention=champion_role_mention(find_role(guild, SET_CHAMPION_ROLE_NAME)),
    )


def _round1_preview_states(seated: bool) -> list[dict]:
    """In-memory Round-1 match states for the no-DB `round1` snapshot, fed through the prod `round_embed`
    builder so the rendering stays in sync — only the match data is fixtured. Arena handles come from
    `_LIVE_TEST_ARENA` (Bram diverges → 'arena (discord)'; the rest collapse to the handle). Seated
    cross-pairs 1v5/2v6/...; `seated=False` previews the random header. Use `podswiss` to drive rounds."""
    roster = _LIVE_TEST_ROSTER
    states: list[dict] = []
    for offset in range(4):
        a, b = roster[offset], roster[offset + 4]
        a_arena = _LIVE_TEST_ARENA.get(a) or f"{a}#10001"
        b_arena = _LIVE_TEST_ARENA.get(b) or f"{b}#10005"
        states.append({
            "a_name": a, "a_display": a, "a_arena": a_arena,
            "a_record": "0-0", "a_seat": offset + 1 if seated else None,
            "b_name": b, "b_display": b, "b_arena": b_arena,
            "b_record": "0-0", "b_seat": offset + 5 if seated else None,
            "winner_name": None, "score": None,
        })
    return states


# Fixture records for the no-DB `round2` / `round3` snapshots: round 2 splits into Winners (1-0) and
# Losers (0-1); round 3 into Trophy (2-0), 1-1, and Last Chance (0-2).
_LATER_ROUND_PREVIEW = {
    2: [("Ava", "Bram", "1-0", "1-0"), ("Cara", "Dex", "1-0", "1-0"),
        ("Eli", "Fern", "0-1", "0-1"), ("Gus", "Hana", "0-1", "0-1")],
    3: [("Ava", "Bram", "2-0", "2-0"), ("Cara", "Dex", "1-1", "1-1"),
        ("Eli", "Fern", "1-1", "1-1"), ("Gus", "Hana", "0-2", "0-2")],
}


def _later_round_preview_states(round_num: int) -> list[dict]:
    """In-memory match states for the no-DB `round2` / `round3` snapshots, fed through the prod
    `round_embed` builder so the grouped rendering (Winners/Losers, Trophy/1-1/Last Chance) and arena
    handles stay in sync. Only the match data is fixtured."""
    states: list[dict] = []
    for a, b, a_record, b_record in _LATER_ROUND_PREVIEW[round_num]:
        states.append({
            "match_id": f"{a}-{b}", "a_name": a, "b_name": b,
            "a_display": a, "b_display": b,
            "a_arena": _LIVE_TEST_ARENA.get(a) or f"{a}#10001",
            "b_arena": _LIVE_TEST_ARENA.get(b) or f"{b}#10005",
            "a_record": a_record, "b_record": b_record,
            "winner_name": None, "score": None,
        })
    mark_trophy_match(states, round_num)
    return states


_THREAD_NAME = "SOS Pod Draft #3 - May 15"
_DRAFTMANCER_URL = f"{settings.draftmancer_web_url}/?session=LLUT-SOS-May-15-D"
_UNLINKED_SEAT = "Stranger#12345"
_RSVPS_YES = [
    "Noya", "Finkel", "LSV", "The Hump", "Paolo", "Shota",
    "Reid", "Chapin", "Nassif", "Huey",
]
_RSVPS_MAYBE = ["Kibler", "Juza", "Levy"]
_SPECTATORS = ["Nakamura", "Karsten"]
# Arena handle, then the Discord display name shown in the announcement
_LINKED_EIGHT: list[tuple[str, str]] = [
    ("Noya#08011", "Noya"),
    ("Finkel#00196", "Finkel"),
    ("LSV#00420", "LSV"),
    ("TheHump#31337", "The Hump"),
    ("PVDDR#00777", "Paolo"),
    ("Shota#08150", "Shota"),
    ("Reid#02200", "Reid"),
    ("Chapin#13000", "Chapin"),
]
_VALID_STATES = (
    "empty", "partial", "linked", "unlinked", "ready", "notready", "cancelled", "left", "superseded",
    "readyunlinked", "readycancel",
    "drafting", "complete", "submit", "lobby", "lobbyopen", "dmlink", "unlink", "podbracket", "podswiss", "podrandom",
    "podteam", "podlobby", "podteamvote",
    "format", "seeding", "trophyhype", "champ", "round1", "round2", "round3", "voicelink", "review",
    "table",
    "teams", "teamreveal", "teamround", "teamstandings", "teamchamp", "teamhype", "teamvote", "p2vote",
    "formatpoll", "linkpicker", "settings",
)

_LIVE_POD_MODES = {
    "podbracket": "bracket", "podswiss": "swiss", "podrandom": "random", "podteam": "team",
}

_PRODUCTION_BLOCKED_STATES = frozenset(_LIVE_POD_MODES) | {"podlobby", "podteamvote", "unlink"}

_LAST_MESSAGE: dict[int, discord.Message] = {}
_LAST_PROGRESS_MESSAGES: dict[int, list[discord.Message]] = {}


async def _delete_last_test_messages(channel) -> None:
    """Clear the previous testlobby preview before a fresh run by deleting only the tracked last
    message(s) for this channel — never sweep the channel history, which would also take out unrelated
    bot messages."""
    last = _LAST_MESSAGE.pop(channel.id, None)
    progress = _LAST_PROGRESS_MESSAGES.pop(channel.id, None) or []
    for msg in [last, *progress]:
        if msg is None:
            continue
        try:
            await msg.delete()
        except discord.HTTPException:
            pass


_PROGRESS_STATES = ("ready", "notready", "cancelled", "left", "superseded", "drafting", "complete")

def _preview_settings_labels() -> dict:
    return dict(
        set_code=active_set_code(),
        format_label=format_display(active_set_code()),
        pairing_label=pairing_label(DEFAULT_PAIRING_MODE),
        seating_label=seating_mode_label("random"),
    )


def _preview_cancel_reason(state: str) -> str | None:
    """Representative cancel reasons matching the runtime paths: a mid-check join and a mid-check leave."""
    if state == "cancelled":
        return roster_change_detail([_UNLINKED_SEAT], "joined")
    if state == "left":
        return roster_change_detail([_LINKED_EIGHT[4][0]], "left")
    return None


def _build(state: str) -> tuple[discord.Embed, discord.ui.View | None]:
    """Returns (embed, view) for a lobby-state preview."""
    if state == "empty":
        in_session: list[tuple[str, str | None]] = []
    elif state == "partial":
        in_session = list(_LINKED_EIGHT[:2])
    elif state == "unlinked":
        in_session = list(_LINKED_EIGHT[:7]) + [(_UNLINKED_SEAT, None)]
    else:
        in_session = list(_LINKED_EIGHT)

    if state in ("cancelled", "left"):
        render_state = "notready"
    elif state == "superseded":
        render_state = "ready"
    else:
        render_state = state
    decliner_name = _LINKED_EIGHT[3][0] if state == "notready" else None
    cancel_reason = _preview_cancel_reason(state)
    initiated_by = _LINKED_EIGHT[0][1] if render_state in ("ready", "notready") else None
    embed = render_lobby_embed(
        _THREAD_NAME, _RSVPS_YES, _RSVPS_MAYBE, in_session,
        state=render_state, draftmancer_url=_DRAFTMANCER_URL,
        decliner_name=decliner_name, cancel_reason=cancel_reason, initiated_by=initiated_by,
        spectators=_SPECTATORS,
        **_preview_settings_labels(),
    )
    spectate_url = f"{_DRAFTMANCER_URL}&spectate=preview"
    if state == "drafting":
        view: discord.ui.View | None = build_drafting_view(spectate_url)
    elif state == "complete":
        view = None
    else:
        view = LobbyReadyButtonView(
            draftmancer_url=_DRAFTMANCER_URL,
            ready_disabled=(render_state == "ready"),
            show_force_start=(render_state == "unlinked"),
            spectate_url=spectate_url,
        )
    return embed, view


def _build_ready_progress(state: str) -> list[tuple[discord.Embed, discord.ui.View | None]]:
    """Preview the ready-check progress card(s) for the states where one is posted in prod. Returns a
    list: `superseded` mirrors a real retry — the collapsed old receipt plus the fresh active check
    below it — every other state is a single card. An active check carries the ready-check buttons,
    a declined card the resume + Settings pair; a superseded receipt carries none."""
    if state not in _PROGRESS_STATES:
        return []
    in_session = list(_LINKED_EIGHT)
    initiator = _LINKED_EIGHT[0][1]
    active_view = LobbyReadyButtonView(
        draftmancer_url=_DRAFTMANCER_URL, ready_disabled=True, show_force_start=True,
    )
    if state == "ready":
        embed = render_ready_check_progress(
            _THREAD_NAME, in_session, state="ready",
            ready_arena_names={arena for arena, _ in _LINKED_EIGHT[:3]},
            initiated_by=initiator, **_preview_settings_labels(),
        )
        return [(embed, active_view)]
    if state in ("notready", "cancelled", "left"):
        decliner = _LINKED_EIGHT[3][0] if state == "notready" else None
        embed = render_ready_check_progress(
            _THREAD_NAME, in_session, state="notready",
            decliner_name=decliner, cancel_reason=_preview_cancel_reason(state),
            initiated_by=initiator, ready_count=3, total_count=8, **_preview_settings_labels(),
        )
        return [(embed, build_not_ready_view())]
    if state == "superseded":
        collapsed = render_ready_check_progress(
            _THREAD_NAME, in_session, state="notready",
            decliner_name=_LINKED_EIGHT[3][0], superseded=True, ready_count=3, total_count=8,
            **_preview_settings_labels(),
        )
        active = render_ready_check_progress(
            _THREAD_NAME, in_session, state="ready", ready_arena_names=set(),
            initiated_by=initiator, **_preview_settings_labels(),
        )
        return [(collapsed, None), (active, active_view)]
    embed = render_ready_check_progress(
        _THREAD_NAME, in_session, state=state,
        **_preview_settings_labels(),
    )
    return [(embed, None)]


async def _settings_preview_noop(interaction: discord.Interaction, value: str) -> str | None:
    return None


async def _settings_preview_description_noop(
    interaction: discord.Interaction, text: str | None,
) -> None:
    return None


async def _settings_preview_seating_noop(
    interaction: discord.Interaction, ordered_user_names: list[str],
) -> str | None:
    return None


async def _settings_preview_seat_order() -> list[tuple[str, str]]:
    return [(arena, display or arena) for arena, display in _LINKED_EIGHT]


async def _settings_preview_on_seated(interaction: discord.Interaction, labels: list[str]) -> None:
    await post_manual_seating_table(interaction.client, interaction.channel, labels, actor_label(interaction))


async def _settings_preview_link_targets() -> list[str]:
    return [_UNLINKED_SEAT]


async def _settings_preview_on_link(
    interaction: discord.Interaction, arena_name: str, member: discord.abc.User,
) -> str | None:
    return None


async def _post_link_picker_preview(ctx) -> None:
    """Throwaway: post the Link Players seat→member picker on its own, so the single-panel seat +
    member + Confirm flow is eyeballable without a live pod or a stale-event-free channel."""
    from bot.services.pod_settings_view import LINK_SEAT_PROMPT, LinkSeatSelectView

    await ctx.send(LINK_SEAT_PROMPT, view=LinkSeatSelectView([_UNLINKED_SEAT], _settings_preview_on_link))


def _settings_preview_view() -> PodSettingsView:
    """No-op Settings panel so `!test` can preview the format + pairing + seats dropdowns plus the Link
    Players flow with no pod. Defaults to Seats: Random (like a fresh pod); pick Manual in the dropdown
    to reveal the Seat Order button."""
    return PodSettingsView(
        on_format=_settings_preview_noop, on_pairing=_settings_preview_noop,
        current_code=None, current_mode=DEFAULT_PAIRING_MODE,
        on_seating_mode=_settings_preview_noop, current_seating="random",
        on_seating=_settings_preview_seating_noop, seat_order_provider=_settings_preview_seat_order,
        on_seated=_settings_preview_on_seated,
        on_timer=_settings_preview_noop, current_timer=60,
        on_picks_per_pack=_settings_preview_noop, current_picks_per_pack=1,
        on_max_players=_settings_preview_noop, current_max_players=8,
        on_closed_decklist=_settings_preview_noop, current_closed_decklist=False,
        on_description=_settings_preview_description_noop,
        link_targets_provider=_settings_preview_link_targets, on_link=_settings_preview_on_link,
    )


async def setup(bot: commands.Bot) -> None:
    """Wire the lobby states as the `!test` fallback and register the settings preview."""
    register_settings_preview(_settings_preview_view)
    register_force_start_preview(lambda: (5, 8, ["Bram", "Cara", "Dex"]))

    async def test_lobby(ctx: commands.Context, state: str = "", extra: str = "") -> None:
        """Owner-only. The `!test` fallback, so each state below is a top-level word: `!test champ`.
        Renders the pod-draft lobby embed in this channel.

        `state` ∈ empty | partial | linked | unlinked | ready | notready | cancelled | left | superseded |
        readyunlinked | drafting | complete | submit | lobbyopen | podbracket | podswiss | podrandom | podteam |
        podlobby | format | seeding | trophyhype | champ | round1 | round2 | round3 | voicelink | linkpicker |
        settings.
        `lobbyopen` posts the real lobby-open message and its Join Draft button — click it to get the
        ephemeral link with your Arena name pre-filled, or the Link Arena nudge when unlinked.
        `dmlink` DMs you both lobby-open link DMs (linked + unlinked) and the opt-in test DM, so every
        DM string can be reviewed in a real inbox without a live lobby. `unlink` clears your own Arena
        handle so the unlinked Join Draft nudge can be replayed; re-link with the Link Arena button.
        `linkpicker` posts the Link Players picker on its own — pick a seat, the member dropdown and
        Confirm button appear below it, and the link commits only on Confirm.
        `settings` posts the no-op Settings panel directly, so it works in a channel already bound to a
        pod event, where the lobby card's Settings button would open that pod's real panel instead.
        `podteam [6|8|10]` seeds a real team draft at that player count (default 6; seat 1 = you,
        Green Team) — posts the team summary embed + live board with working report buttons and
        opens the two private team threads off this channel.
        `teamstandings` shows the pinned final standings embed for a finished team draft.
        `teamchamp` shows the two-gallery team championship card; `teamhype` the combined 3-0 hype card.
        `teams` is the no-DB snapshot of the Components V2 team board (team headers + all three rounds,
        one row per match); its Report buttons are inert — use `podteam` to drive reports.
        `teamround` is the no-DB snapshot of the live model: the big all-rounds block, then the Round
        2 and Round 3 reveal blocks that post as each round becomes playable, with cumulative footers.
        Buttons are inert here — use `podteam` to drive real reports and reveals.
        `teamvote` shows the Team-Draft offer card with a working 🤝 vote button and three votes
        prefilled — your click is the fourth, locking it to Team Draft and proposing a Ready Check.
        `p2vote` shows the Pick 2 offer card a lobby stalled at four gets, with working buttons and three
        votes prefilled — your click is the fourth, the unanimous vote that locks Pick 2 Round Robin. Click
        Wait instead and the card stays open, since waiting is not a verdict.
        `podteamvote` arms a fake six-player lobby on this channel so `/pod-team` posts the real card
        as its own reply, with no Draftmancer session needed; re-run `/pod-team` for the re-offer path.
        `formatpoll` shows the flashback format tally with a working button per option and prefilled
        votes — clicks toggle votes on the card, nothing locks.
        `ready` shows the active ready-check card; clicking its Force Start button previews the ephemeral
        confirm dialog (no live pod needed). `readycancel` posts each way a check ends — a decline, a
        roster-change join, and a timeout — as the progress card plus (for the non-decline cases) the
        thread notice, so the resume surfaces can be compared.
        `round1`/`round2`/`round3` are no-DB snapshots of each round
        embed (`round1 random` for the random-pairing header).
        No arg → posts the beginning lobby state. Every invocation posts fresh messages.
        `podbracket` / `podswiss` / `podrandom` seed a real 8-player pod (seat 1 = you) and hand off to
        the prod tournament code, so the round embeds + result dropdowns drive the real round-to-round
        flow (these write to the local DB). `round1` (`round1 random` for random pairing) is a no-DB
        snapshot of the Round 1 embed only — to drive rounds, use `podswiss`. `podlobby` connects to a
        live Draftmancer session for ready-check testing. `seeding [count]` posts the /pod-seeding embed
        (table + round-table PNG) for `count` players (default 8; ranked padded with fillers), no sesh."""
        if state and state not in _VALID_STATES:
            await ctx.send(f"unknown state `{state}`; pick one of: {', '.join(_VALID_STATES)}")
            return

        if state in _PRODUCTION_BLOCKED_STATES and await refused_on_production(ctx, state):
            return

        if state in _LIVE_POD_MODES:
            if extra and extra not in _LIVE_TEST_POD_SIZES:
                await ctx.send(f"player count must be one of: {', '.join(_LIVE_TEST_POD_SIZES)}")
                return
            mode = _LIVE_POD_MODES[state]
            default_count = 6 if mode == "team" else 8
            await _start_live_test_pod(ctx, mode, int(extra) if extra else default_count)
            return

        if state == "lobby":
            await _preview_full_lobby(ctx)
            return

        if state == "lobbyopen":
            session_id = f"{active_set_code()}-TestOpen"
            body = build_lobby_open_body(draftmancer_url_for(session_id), ctx.author.mention)
            await ctx.send(
                body, view=build_join_view(session_id),
                allowed_mentions=discord.AllowedMentions(users=True),
            )
            return

        if state == "dmlink":
            await _preview_link_dms(ctx)
            return

        if state == "unlink":
            cleared = await asyncio.to_thread(_unlink_arena, str(ctx.author.id))
            await ctx.send(
                "🧪 Arena unlinked — Join Draft now shows the unlinked nudge."
                if cleared else "No linked Arena to clear.",
            )
            return

        if state == "podlobby":
            await _start_live_test_lobby(ctx)
            return

        if state == "podteamvote":
            await _arm_pod_team_command(ctx)
            return

        if state == "readyunlinked":
            embed, _ = _build("unlinked")
            await ctx.send(embed=embed, view=_ReadyCheckPreviewView())
            return

        if state == "readycancel":
            initiator = _LINKED_EIGHT[0][1]
            scenarios = [
                ("Decline — player pressed Not Ready", {"decliner_name": _LINKED_EIGHT[3][0]}),
                ("Roster change — someone joined", {"cancel_reason": _preview_cancel_reason("cancelled")}),
                ("Roster change — someone left", {"cancel_reason": _preview_cancel_reason("left")}),
                ("Timeout", {"timed_out": True}),
            ]
            for label, banner in scenarios:
                await ctx.send(f"__**{label}**__")
                card = render_ready_check_progress(
                    _THREAD_NAME, [], state="notready", initiated_by=initiator,
                    ready_count=6, total_count=8, **banner, **_preview_settings_labels(),
                )
                await ctx.send(embed=card, view=build_not_ready_view())
            return

        if state == "table":
            await _start_test_table(ctx)
            return

        if state == "seeding":
            await _post_test_seeding(ctx, int(extra) if extra.isdigit() else 8)
            return

        if state == "linkpicker":
            await _post_link_picker_preview(ctx)
            return

        if state == "settings":
            await ctx.send(view=_settings_preview_view())
            return

        if state == "submit":
            await ctx.send(view=_submit_deck_view())
            return

        if state == "trophyhype":
            await ctx.send(view=_trophy_hype_preview())
            return

        if state == "champ":
            await ctx.send(
                view=_champion_announcement_preview(ctx.guild),
                allowed_mentions=discord.AllowedMentions.none(),
            )
            await ctx.send(
                view=_champion_hype_preview(ctx.guild),
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

        if state == "teamstandings":
            await ctx.send(embed=_team_standings_preview_embed())
            return

        if state == "teamchamp":
            await ctx.send(view=_team_championship_preview_view())
            return

        if state == "teamhype":
            await ctx.send(view=_team_trophy_hype_preview_view())
            return

        if state == "teamvote":
            seeded = list(_team_vote_seed().values())
            embed = build_team_vote_offer_embed(seeded, [], _TEAM_VOTE_POD_SIZE)
            await ctx.send(embed=embed, view=_TeamVotePreviewView())
            return

        if state == "p2vote":
            preview = _RoundRobinVotePreviewView()
            await ctx.send(
                embed=pod_round_robin_vote.build_offer_embed(
                    preview.round_robin, preview.wait, _ROUND_ROBIN_POD_SIZE),
                view=preview,
            )
            return

        if state == "formatpoll":
            preview = _FormatPollPreviewView()
            embed = pod_format_poll.build_format_poll_embed(preview.options, preview.votes)
            await ctx.send(embed=embed, view=preview)
            return

        if state == "teams":
            preview_data = _team_preview_board_data()
            await _send_team_summary(ctx, preview_data)
            for view in build_team_board_views(preview_data):
                await ctx.send(view=view)
            return

        if state == "teamreveal":
            seat_order, teams = _team_reveal_preview_parts()
            labels = {**_preview_settings_labels(), "pairing_label": pairing_label("team")}
            await ctx.send(embed=render_ready_check_progress(
                _THREAD_NAME, [(_TEAM_ARENA[name], name) for name in seat_order],
                state="drafting", teams={_TEAM_ARENA[n]: t for n, t in teams.items()},
                initiated_by=_INVOKER_SEAT, **labels,
            ))
            return

        if state == "teamround":
            preview_data = _team_round_preview_data(clinch=extra == "clinch")
            await _send_team_summary(ctx, preview_data)
            for view in build_team_board_views(preview_data):
                await ctx.send(view=view)
            for round_num in (2, 3):
                await ctx.send(view=build_team_round_view(preview_data, round_num))
            return

        if state == "round1":
            await ctx.send(embed=round_embed(1, _round1_preview_states(seated=extra != "random")))
            return

        if state in ("round2", "round3"):
            round_num = int(state[-1])
            await ctx.send(embed=round_embed(round_num, _later_round_preview_states(round_num)))
            return

        if state == "voicelink":
            channel = discord.utils.get(
                ctx.guild.voice_channels, name=settings.pod_draft_voice_channel_name,
            ) if ctx.guild else None
            if channel is None:
                await ctx.send(f"(no '{settings.pod_draft_voice_channel_name}' voice channel in this server)")
                return
            await ctx.send(channel.jump_url)
            return

        if state == "review":
            voice_url = pod_voice_channel_url(ctx.guild)
            embed = render_draft_review_embed(_review_preview_roster(), event_name="Pod Draft Preview")
            msg = await ctx.send(
                content=build_draft_review_message(voice_url),
                embed=embed, allowed_mentions=discord.AllowedMentions.none(),
            )
            try:
                await msg.add_reaction(REVIEW_EMOJI)
            except discord.HTTPException:
                pass
            return

        if state == "format":
            async def _test_apply(inter: discord.Interaction, code: str) -> str | None:
                labels = {**_preview_settings_labels(), "set_code": code, "format_label": format_display(code)}
                embed = render_lobby_embed(
                    _THREAD_NAME, _RSVPS_YES, _RSVPS_MAYBE, list(_LINKED_EIGHT),
                    state="linked", draftmancer_url=_DRAFTMANCER_URL, **labels,
                )
                await inter.channel.send(embed=embed)
                return None
            await ctx.send(view=FormatSelectView(_test_apply))
            return

        if state == "":
            state = "empty"

        await _evict_test_managers_for_channel(ctx.channel.id)
        embed, view = _build(state)
        _LAST_MESSAGE[ctx.channel.id] = await ctx.send(embed=embed, view=view)
        posted = [await ctx.send(embed=e, view=v) for e, v in _build_ready_progress(state)]
        _LAST_PROGRESS_MESSAGES[ctx.channel.id] = posted

    register_test_fallback(test_lobby)
