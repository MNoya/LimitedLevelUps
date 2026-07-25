"""Team-draft lifecycle around the board: assignment, reveal, board post, team threads, finalize.

Teams are draft-seat parity, decided the moment `startDraft` locks the table: the manager pushes a
known seating for every seating mode, so the reveal posts immediately — the draft log later only
confirms seat indexes. At `endDraft` all three rounds of cross-team pairings are inserted at once and
the board (pod_team_board) becomes the match surface; the two private team threads open alongside it.
The last reported match finalizes: per-player records feed the existing pod-point path unchanged, the
final standings embed pins in the thread, and the winning team is announced — there is no
single-champion or trophy-hype post for a team draft.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import discord
from sqlalchemy import select, update

from bot.database import SessionLocal
from bot.models import Player as DbPlayer, PodDraftEvent, PodDraftParticipant
from bot.services import pod_swiss, pod_team
from bot.services.pod_active import notify_pod_complete
from bot.services.pod_drafts import (
    FinalStanding,
    apply_seat_indexes,
    finalize_champion,
    load_event_name_sync,
    normalize_player_name,
)
from bot.services.pod_replays import capture_event_replays
from bot.services.pod_team_board import (
    build_team_board_views,
    load_team_board_data,
    team_summary_embed,
)
from bot.discord_helpers import NBSP, ZWSP, player_url
from bot.services.pod_tournament import (
    POD_PAIRING_FAILED_MSG,
    TOTAL_ROUNDS,
    alert_thread_and_owner,
    build_replays_link_button,
    clean_caption,
    colors_only,
    escape_italics,
    format_deck_color_emojis,
    insert_pending_matches,
    load_event_deck_data_sync,
    load_matches,
    load_participant_displays,
    load_seat_indexes,
    load_tournament_players_sync,
    ping_missing_deck_participants,
    roster_in_seat_order,
    send_submit_deck_dms,
)
from bot.services.seventeenlands import SeventeenLandsClient


if TYPE_CHECKING:
    from bot.services.pod_draft_manager import PodDraftManager


log = logging.getLogger(__name__)

TEAM_THREAD_INTRO = (
    "{emoji} **{label}** private room. Talk deckbuilding and strategy here. "
    "Report your matches on the [__**shared thread**__]({board_url}) ➡️"
)


async def assign_teams_at_draft_start(manager: "PodDraftManager") -> None:
    """Assign and persist teams from the locked seating the moment startDraft fires. Every seating
    mode pushes a known order (`manager.desired_seating`) before the start, so the sides are final
    here; the raw lobby order is only a logged fallback."""
    ordered = list(manager.desired_seating or [])
    if not ordered:
        ordered = manager.non_bot_session_names()
        log.warning(f"[TEAM] assign.no_desired_seating event={manager.event_id} fallback=lobby_order")
    if not ordered:
        log.warning(f"[TEAM] assign.empty_roster event={manager.event_id}")
        return
    teams = pod_team.assign_teams(ordered)
    manager.team_map = teams
    await asyncio.to_thread(_persist_start_assignment_sync, manager.event_id, ordered, teams)
    log.info(f"[TEAM] assigned event={manager.event_id} order={ordered}")


def _persist_start_assignment_sync(event_id: str, ordered: list[str], teams: dict[str, str]) -> None:
    with SessionLocal() as session:
        apply_seat_indexes(session, event_id, ordered)
        _apply_teams(session, event_id, teams)
        session.commit()


def _apply_teams(session, event_id: str, teams: dict[str, str]) -> None:
    normalized = {normalize_player_name(name): team for name, team in teams.items()}
    rows = session.execute(
        select(PodDraftParticipant).where(PodDraftParticipant.event_id == event_id)
    ).scalars().all()
    for row in rows:
        key = normalize_player_name(row.draftmancer_name or row.display_name)
        if key in normalized:
            row.team = normalized[key]


async def start_team_tournament(manager: "PodDraftManager") -> None:
    """Phase 3: the draft ended, so pair every round up front and post the board. The fixed rotation
    is results-independent — all report buttons are live from the start, rounds are the cadence."""
    event_id = manager.event_id
    await asyncio.to_thread(manager.persist_seat_indexes_from_log)
    roster = [p.id for p in manager.tournament_players]
    teams, ordered = await asyncio.to_thread(_load_or_assign_teams_sync, event_id, roster)
    manager.team_map = teams
    team_a, team_b = pod_team.team_rosters(ordered, teams)
    try:
        rounds = [(r, pod_team.pair_round(team_a, team_b, r)) for r in range(1, TOTAL_ROUNDS + 1)]
    except ValueError as e:
        log.error(f"[TEAM] pairing_failed event={event_id} err={e!s}")
        await alert_thread_and_owner(
            manager, POD_PAIRING_FAILED_MSG.format(round_num=1),
            f"Pod `{event_id}` team pairing failed: {e}",
            fingerprint=f"pod_pairing_failed:{event_id}:team",
        )
        return
    for round_num, pairings in rounds:
        await asyncio.to_thread(insert_pending_matches, event_id, round_num, pairings)
    manager.current_round = TOTAL_ROUNDS

    thread = await manager._fetch_thread()
    if thread is None:
        return
    data = await asyncio.to_thread(load_team_board_data, event_id)
    try:
        await thread.send(embed=team_summary_embed(data))
        board_messages = [await thread.send(view=view) for view in build_team_board_views(data)]
    except discord.HTTPException:
        log.warning(f"[TEAM] board_post_failed event={event_id}", exc_info=True)
        return
    manager.team_board_messages = board_messages
    try:
        await board_messages[0].pin(reason="pod team-draft board")
    except discord.HTTPException:
        log.warning(f"[TEAM] board_pin_failed event={event_id}", exc_info=True)
    asyncio.create_task(send_submit_deck_dms(manager.bot, event_id))
    await _create_team_threads(manager, board_messages[0])


def _load_or_assign_teams_sync(event_id: str, roster: list[str]) -> tuple[dict[str, str], list[str]]:
    """Teams persisted at startDraft, plus the roster in final seat order. Assigns fresh from seat
    parity only when no assignment survived (e.g. a restart lost the startDraft window)."""
    seats = load_seat_indexes(event_id)
    ordered = roster_in_seat_order(roster, seats)
    teams = load_teams_sync(event_id)
    if not teams:
        log.warning(f"[TEAM] endDraft.no_persisted_teams event={event_id} assigning_from_seats=True")
        teams = pod_team.assign_teams(ordered)
        with SessionLocal() as session:
            _apply_teams(session, event_id, teams)
            session.commit()
    return teams, ordered


def load_teams_sync(event_id: str) -> dict[str, str]:
    """Map draftmancer_name → team for a persisted team draft."""
    with SessionLocal() as session:
        rows = session.execute(
            select(
                PodDraftParticipant.draftmancer_name,
                PodDraftParticipant.display_name,
                PodDraftParticipant.team,
            ).where(
                PodDraftParticipant.event_id == event_id,
                PodDraftParticipant.team.is_not(None),
            )
        ).all()
    out: dict[str, str] = {}
    for draftmancer_name, display_name, team in rows:
        name = draftmancer_name or display_name
        if name and team:
            out[name] = team
    return out


def _load_team_discord_ids_sync(event_id: str) -> dict[str, list[str]]:
    """Map team → linked Discord user ids, for adding each side to its private thread."""
    with SessionLocal() as session:
        rows = session.execute(
            select(PodDraftParticipant.team, DbPlayer.discord_id)
            .join(DbPlayer, DbPlayer.id == PodDraftParticipant.player_id)
            .where(PodDraftParticipant.event_id == event_id)
        ).all()
    out: dict[str, list[str]] = {pod_team.TEAM_A: [], pod_team.TEAM_B: []}
    for team, discord_id in rows:
        if team in out and discord_id:
            out[team].append(discord_id)
    return out


def _persist_team_thread_ids_sync(event_id: str, team_a_id: str | None, team_b_id: str | None) -> None:
    with SessionLocal() as session:
        session.execute(
            update(PodDraftEvent)
            .where(PodDraftEvent.id == event_id)
            .values(team_a_thread_id=team_a_id, team_b_thread_id=team_b_id)
        )
        session.commit()


async def _create_team_threads(manager: "PodDraftManager", board_message: discord.Message) -> None:
    """Open a private thread per team off the pod's parent channel, add each side's linked members,
    and post the one-line intro pointing at the board — then the bot never posts there again.

    Best-effort: a pod without a parent text channel (or lacking the private-thread permission) skips
    the threads rather than failing the tournament. Matches stay reportable on the shared board.
    """
    pod_thread = await manager._fetch_thread()
    if isinstance(pod_thread, discord.Thread):
        parent = pod_thread.parent
    elif isinstance(pod_thread, discord.TextChannel):
        parent = pod_thread
    else:
        parent = None
    if parent is None or not hasattr(parent, "create_thread"):
        log.info(f"[TEAM] threads_skipped event={manager.event_id} reason=no_parent_channel")
        return

    discord_ids = await asyncio.to_thread(_load_team_discord_ids_sync, manager.event_id)
    event_name = await asyncio.to_thread(load_event_name_sync, manager.event_id)
    thread_ids: dict[str, str | None] = {pod_team.TEAM_A: None, pod_team.TEAM_B: None}
    existing_by_name = {t.name: t for t in parent.threads}

    for team in (pod_team.TEAM_A, pod_team.TEAM_B):
        name = f"{pod_team.team_emoji(team)} Team - {event_name}"[:100]
        thread = existing_by_name.get(name)
        if thread is not None:
            log.info(f"[TEAM] thread_reused event={manager.event_id} team={team} thread={thread.id}")
        else:
            try:
                thread = await parent.create_thread(
                    name=name,
                    type=discord.ChannelType.private_thread,
                    invitable=False,
                    reason="pod team-draft private team room",
                )
            except discord.HTTPException:
                log.warning(f"[TEAM] thread_create_failed event={manager.event_id} team={team}", exc_info=True)
                continue
        thread_ids[team] = str(thread.id)
        for discord_id in discord_ids.get(team, []):
            try:
                await thread.add_user(discord.Object(id=int(discord_id)))
            except (discord.HTTPException, ValueError):
                log.warning(f"[TEAM] thread_add_user_failed team={team} user={discord_id}", exc_info=True)
        try:
            await thread.send(TEAM_THREAD_INTRO.format(
                emoji=pod_team.team_emoji(team),
                label=pod_team.team_label(team),
                board_url=board_message.jump_url,
            ).rstrip())
        except discord.HTTPException:
            log.warning(f"[TEAM] thread_intro_failed event={manager.event_id} team={team}", exc_info=True)

    await asyncio.to_thread(
        _persist_team_thread_ids_sync, manager.event_id,
        thread_ids[pod_team.TEAM_A], thread_ids[pod_team.TEAM_B],
    )


async def finalize_team_tournament(manager: "PodDraftManager") -> None:
    """Phase 5, fired by the last reported match: write per-player records (the existing pod-point
    path — the team result is a headline, not a scoring term), pin the final standings, and announce
    the winning team. No single-champion or trophy-hype post."""
    if manager.finalized:
        log.info(f"[TEAM] finalize.already_finalized event={manager.event_id}")
        return
    log.info(f"[TEAM] finalize.start event={manager.event_id}")
    manager.finalized = True
    event_id = manager.event_id
    await asyncio.to_thread(manager.persist_decklists_from_log)
    prior = await asyncio.to_thread(load_matches, event_id)
    standings = pod_swiss.compute_standings(manager.tournament_players, prior)

    final_standings = team_final_standings(standings)

    def _do_write() -> None:
        with SessionLocal() as session:
            finalize_champion(session, event_id, final_standings)
            session.commit()
    await asyncio.to_thread(_do_write)

    notify_pod_complete(manager.bot, event_id)

    teams = manager.team_map or await asyncio.to_thread(load_teams_sync, event_id)
    manager.team_map = teams
    displays = await asyncio.to_thread(load_participant_displays, event_id)
    event_name = await asyncio.to_thread(load_event_name_sync, event_id)
    deck_data = await asyncio.to_thread(load_event_deck_data_sync, event_id)
    embed = build_team_final_embed(
        standings, teams, event_name=event_name, displays=displays, pending_count=0,
        player_colors=colors_only(deck_data),
    )
    thread = await manager._fetch_thread()
    if thread is not None:
        try:
            standings_message = await thread.send(embed=embed, view=team_standings_view(event_name))
            manager.standings_message = standings_message
            await standings_message.pin(reason="pod team-draft final standings")
        except discord.HTTPException:
            log.warning(f"[TEAM] standings_post_failed event={event_id}", exc_info=True)

    from bot.services import pod_team_showcase

    await ping_missing_deck_participants(manager, blocking_keys=team_showcase_keys(standings, teams))
    await manager.share_draft_log()
    asyncio.create_task(capture_event_replays(SeventeenLandsClient(), event_id))
    await pod_team_showcase.maybe_post_team_trophy_hype(manager)
    await pod_team_showcase.maybe_post_team_championship(manager)
    if manager.championship_task is None:
        manager.championship_task = asyncio.create_task(
            pod_team_showcase.team_championship_deadline(manager)
        )
    await manager.disconnect_safely()


def team_final_standings(standings) -> list[FinalStanding]:
    """Per-player records only: a team pod has no individual champion, so no placement is written,
    nobody counts as eliminated, and pod trophies stay record-based."""
    return [
        FinalStanding(
            draftmancer_name=s.player_name,
            placement=None,
            record=f"{s.wins}-{s.losses}",
            eliminated_round=None,
        )
        for s in standings
    ]


def team_showcase_keys(standings, teams: dict[str, str]) -> set[str]:
    """Normalized names whose decks gate the team championship post: the winning side plus any 3-0
    from the losing side. A draw has no winning side, so only the 3-0s gate. The losing team's
    best-performer thumbnail is best-effort — never gated, shown only if that deck is already in."""
    normalized = {normalize_player_name(name): team for name, team in teams.items()}
    a_wins, b_wins = team_scores(standings, teams)
    winner = pod_team.team_winner(a_wins, b_wins)
    keys = set()
    for s in standings:
        key = normalize_player_name(s.player_name)
        is_trophy = f"{s.wins}-{s.losses}" == "3-0"
        if normalized.get(key) == winner or is_trophy:
            keys.add(key)
    return keys


def team_scores(standings, teams: dict[str, str]) -> tuple[int, int]:
    """(team_a_wins, team_b_wins) as the sum of each side's individual match wins."""
    normalized = {normalize_player_name(name): team for name, team in teams.items()}
    a_wins = 0
    b_wins = 0
    for s in standings:
        side = normalized.get(normalize_player_name(s.player_name))
        if side == pod_team.TEAM_A:
            a_wins += s.wins
        elif side == pod_team.TEAM_B:
            b_wins += s.wins
    return a_wins, b_wins


TEAM_VICTORY_COLORS = {
    pod_team.TEAM_A: discord.Color.green(),
    pod_team.TEAM_B: discord.Color.blurple(),
}


def build_team_final_embed(standings, teams, *, event_name, displays, pending_count,
                           player_colors: dict[str, str | None] | None = None) -> discord.Embed:
    """Team-draft standings: the winner in the title, an oversized emoji scoreline, and each side's
    roster with records, personal 3-0 trophies, and deck colors. The accent takes the winning team's
    button colour. Per-player records still drive leaderboard pod points, so they stay visible.
    Doubles as the /pod-standings snapshot while matches are open."""
    normalized = {normalize_player_name(name): team for name, team in teams.items()}
    a_wins, b_wins = team_scores(standings, teams)
    winner = pod_team.team_winner(a_wins, b_wins)
    live = pending_count > 0
    if live:
        title = "Team Draft Live Standings ⏳"
    elif winner is None:
        title = "🤝 Team draft ends in a draw!"
    else:
        title = f"🏆 {pod_team.team_label(winner)} wins the draft!"
    a_emoji = pod_team.team_emoji(pod_team.TEAM_A)
    b_emoji = pod_team.team_emoji(pod_team.TEAM_B)
    scoreline = f"## {a_emoji} {a_wins} - {b_wins} {b_emoji}"
    color = TEAM_VICTORY_COLORS.get(None if live else winner, discord.Color.green())
    embed = discord.Embed(title=title, description=scoreline, color=color)
    for team in (pod_team.TEAM_A, pod_team.TEAM_B):
        members = [s for s in standings if normalized.get(normalize_player_name(s.player_name)) == team]
        embed.add_field(
            name=f"{pod_team.team_emoji(team)} {pod_team.team_label(team)}",
            value=team_record_column(members, displays, player_colors or {}) or "—",
            inline=True,
        )
    embed.set_footer(text=event_name)
    return embed


def team_record_line(s, displays: dict[str, dict], player_colors: dict[str, str | None],
                     deck_data=None) -> str:
    """One roster row: the name linking to the player's site profile, record, a 🏆 on a personal
    3-0, the italicized screenshot caption when `deck_data` is passed (championship card only),
    then the player's deck-color glyph once decks are known."""
    key = normalize_player_name(s.player_name)
    info = displays.get(key, {})
    name = info.get("display_name") or s.player_name
    slug = info.get("slug")
    rendered = f"[{name}]({player_url(slug)})" if slug else f"**{name}**"
    record = f"{s.wins}-{s.losses}"
    trophy = "  🏆" if record == "3-0" else ""
    data = deck_data.get(key) if deck_data else None
    caption = clean_caption(data.screenshot_caption) if data and data.screenshot_caption else ""
    caption_suffix = f"  _{escape_italics(caption)}_" if caption else ""
    glyph = format_deck_color_emojis(player_colors.get(key))
    glyph_suffix = f"  {glyph}" if glyph else ""
    return f"{rendered}  {record}{trophy}{caption_suffix}{glyph_suffix}"


def team_record_column(members, displays: dict[str, dict], player_colors: dict[str, str | None],
                       deck_data=None) -> str:
    column_gap = NBSP * 6 + ZWSP
    return "\n".join(
        f"{team_record_line(s, displays, player_colors, deck_data)}{column_gap}" for s in members
    )


def team_standings_view(event_name: str) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(build_replays_link_button(event_name))
    return view


async def refresh_team_standings_embed(manager: "PodDraftManager") -> None:
    """Re-render the pinned team standings after a late deck save so the color glyphs stay live.
    Rediscovers the pin after a restart or post-finalize eviction; nothing to refresh before
    finalize posts the message."""
    if manager.standings_message is None:
        manager.standings_message = await _find_pinned_team_standings(manager)
    if manager.standings_message is None:
        return
    embed = await build_team_standings_embed_for_event(manager.event_id)
    if embed is None:
        return
    try:
        await manager.standings_message.edit(embed=embed)
    except discord.HTTPException:
        log.warning(f"[TEAM] standings_refresh_failed event={manager.event_id}", exc_info=True)


async def _find_pinned_team_standings(manager: "PodDraftManager") -> discord.Message | None:
    """The pinned team standings message, recognized by its embed footer carrying the event name —
    the only pinned bot embed with a footer in a team pod thread."""
    thread = await manager._fetch_thread()
    bot_user = getattr(manager.bot, "user", None)
    if thread is None or bot_user is None:
        return None
    event_name = await asyncio.to_thread(load_event_name_sync, manager.event_id)
    try:
        pins = await thread.pins()
    except discord.HTTPException:
        log.warning("could not fetch pins to rediscover team standings", exc_info=True)
        return None
    for message in pins:
        if message.author.id != bot_user.id:
            continue
        if any(embed.footer and embed.footer.text == event_name for embed in message.embeds):
            return message
    return None


async def build_team_standings_embed_for_event(event_id: str) -> discord.Embed | None:
    """The /pod-standings embed for a team pod, live or final, loaded straight from the DB (no
    in-memory manager required). None before teams exist — the pod hasn't started."""
    teams = await asyncio.to_thread(load_teams_sync, event_id)
    if not teams:
        return None
    players = await asyncio.to_thread(load_tournament_players_sync, event_id)
    if not players:
        return None
    prior = await asyncio.to_thread(load_matches, event_id)
    standings = pod_swiss.compute_standings(players, prior)
    board = await asyncio.to_thread(load_team_board_data, event_id)
    displays = await asyncio.to_thread(load_participant_displays, event_id)
    event_name = await asyncio.to_thread(load_event_name_sync, event_id)
    deck_data = await asyncio.to_thread(load_event_deck_data_sync, event_id)
    return build_team_final_embed(
        standings, teams, event_name=event_name, displays=displays, pending_count=board.pending,
        player_colors=colors_only(deck_data),
    )


