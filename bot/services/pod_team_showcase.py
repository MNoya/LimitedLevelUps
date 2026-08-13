"""Team-draft showcase posts: the championship card and the 3-0 trophy-hype card.

The championship posts once per event to pod-draft-chat after finalize, gated on the showcased decks
(winning team plus any losing-side 3-0) with the same force deadline as regular pods. Both rosters
show records, captions, and deck colors; the winner gets a screenshot gallery, a losing 3-0 gets a
row thumbnail, and the rest of the losing side's decks live behind the Draft Recap link so they never
hold up the post. Trophy-hype fires the
moment the 3-0 set is decided (every undefeated player has finished, nobody can still get there) and
their decks are in: one card for all 3-0s regardless of team, divided per player. Both reuse the
pod-draft posting spine — channel resolution, the posted-at DB guard, the hype channel scan — so a
decision change lands on both systems.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord
from discord import ui

from bot.services import pod_swiss, pod_team
from bot.services.pod_active import notify_card_phase, notify_podium_posted
from bot.services.pod_drafts import normalize_player_name
from bot.services.pod_team_board import load_team_board_data
from bot.services.pod_team_flow import (
    TEAM_VICTORY_COLORS,
    load_teams_sync,
    team_record_column,
    team_record_line,
    team_scores,
    team_showcase_missing,
)
from bot.services.pod_tournament import (
    CHAMPIONSHIP_DEADLINE_SECONDS,
    build_replays_link_button,
    build_thread_link_button,
    championship_posted_at_sync,
    colors_only,
    format_deck_color_emojis,
    incomplete_decks,
    load_dm_info_sync,
    load_event_deck_data_sync,
    load_event_name_sync,
    load_event_started_at_sync,
    load_event_thread_id_sync,
    load_matches,
    load_participant_displays,
    load_tournament_players_sync,
    mark_championship_posted_sync,
    post_trophy_hype,
    resolve_chat_target,
    short_event_name,
)


if TYPE_CHECKING:
    from bot.services.pod_draft_manager import PodDraftManager


log = logging.getLogger(__name__)


async def maybe_post_team_championship(manager: "PodDraftManager", *, force: bool = False) -> None:
    """Post the one-time team championship card to pod-draft-chat. Fires once the pod is finalized
    and every showcased player — the winning team plus any losing-side 3-0 — has colors and a
    screenshot on record, or when forced by the deadline. Posts once, never edits — idempotent via
    the championship_posted_at DB guard."""
    if manager.champion_announced:
        return
    event_id = manager.event_id
    if await asyncio.to_thread(championship_posted_at_sync, event_id) is not None:
        manager.champion_announced = True
        return
    if not manager.finalized:
        log.info(f"[TEAM] champion.skip event={event_id} reason=not_finalized")
        return

    teams = manager.team_map or await asyncio.to_thread(load_teams_sync, event_id)
    if not teams:
        log.info(f"[TEAM] champion.skip event={event_id} reason=no_teams")
        return
    prior = await asyncio.to_thread(load_matches, event_id)
    standings = pod_swiss.compute_standings(manager.tournament_players, prior)
    if not standings:
        log.info(f"[TEAM] champion.skip event={event_id} reason=no_standings")
        return
    deck_data = await asyncio.to_thread(load_event_deck_data_sync, event_id)
    incomplete = team_showcase_missing(standings, teams, deck_data)
    if incomplete and not force:
        log.info(f"[TEAM] champion.skip event={event_id} reason=awaiting_showcase_decks missing={incomplete}")
        return

    target = await resolve_chat_target(manager)
    if target is None:
        log.info(f"[TEAM] champion.skip event={event_id} reason=no_target")
        return
    displays = await asyncio.to_thread(load_participant_displays, event_id)
    event_name = await asyncio.to_thread(load_event_name_sync, event_id)
    started_at = await asyncio.to_thread(load_event_started_at_sync, event_id)
    thread_id = int(manager.thread_id) if isinstance(manager.thread_id, (int, str)) else None
    guild_id = getattr(getattr(target, "guild", None), "id", None)

    view = build_team_championship_view(
        standings, teams,
        event_name=event_name,
        displays=displays,
        player_colors=colors_only(deck_data),
        deck_data=deck_data,
        event_started_at=started_at,
        guild_id=guild_id,
        thread_id=thread_id,
    )
    manager.champion_announced = True
    try:
        posted = await target.send(view=view)
        await asyncio.to_thread(mark_championship_posted_sync, event_id)
        notify_podium_posted(manager.bot, event_id, posted.jump_url)
        log.info(f"[TEAM] champion.posted event={event_id} forced={force} missing={incomplete}")
    except Exception:
        manager.champion_announced = False
        log.warning(f"[TEAM] champion.post_error event={event_id}", exc_info=True)
        return
    manager.card_result_line = _team_result_line(standings, teams)
    manager.card_result_url = posted.jump_url
    notify_card_phase(manager.bot, event_id)
    if not force and manager.championship_task is not None and not manager.championship_task.done():
        manager.championship_task.cancel()


def _team_result_line(standings, teams: dict[str, str]) -> str:
    """The scheduled card's final status for a team pod. The winning team's members are named in bold
    since the card is an embed, where a `<@id>` mention would render as raw text."""
    a_wins, b_wins = team_scores(standings, teams)
    winner = pod_team.team_winner(a_wins, b_wins)
    normalized = {normalize_player_name(name): team for name, team in teams.items()}
    members = [f"**{s.player_name}**" for s in standings
               if normalized.get(normalize_player_name(s.player_name)) == winner]
    return pod_team.draft_result_line(winner, members, a_wins, b_wins)


def build_team_championship_view(
    standings, teams, *,
    event_name: str,
    displays: dict[str, dict],
    player_colors: dict[str, str | None],
    deck_data,
    event_started_at: datetime | None = None,
    guild_id: int | None = None,
    thread_id: int | None = None,
) -> ui.LayoutView:
    """The team counterpart of the champion announcement card: scoreline headline, then one block per
    team divided by a separator — the winning team on top, roster rows with records, captions, and deck
    colors for both sides, a screenshot gallery for the winning team, and a row thumbnail of the losing
    team's best performer's deck. The rest of the losing decks live behind the Draft Recap link. A draw
    keeps the fixed team order and shows only 3-0 thumbnails."""
    normalized = {normalize_player_name(name): team for name, team in teams.items()}
    a_wins, b_wins = team_scores(standings, teams)
    winner = pod_team.team_winner(a_wins, b_wins)
    short = short_event_name(event_name) or event_name
    if winner is None:
        title = f"🤝 {short} ends in a draw, {a_wins}-{b_wins}!"
    else:
        title = f"🏆 {pod_team.team_label(winner)} wins {short} {max(a_wins, b_wins)}-{min(a_wins, b_wins)}!"

    view = ui.LayoutView()
    accent = TEAM_VICTORY_COLORS.get(winner, discord.Color.green())
    container = ui.Container(accent_colour=accent)
    started_at = event_started_at or datetime.now(timezone.utc)
    container.add_item(ui.TextDisplay(f"## {title}\n**Drafted on** <t:{int(started_at.timestamp())}:F>"))

    if winner is None:
        team_order = (pod_team.TEAM_A, pod_team.TEAM_B)
    else:
        team_order = (winner, pod_team.other_team(winner))

    for team in team_order:
        members = [s for s in standings if normalized.get(normalize_player_name(s.player_name)) == team]
        container.add_item(ui.Separator())
        header = f"### {pod_team.team_emoji(team)} {pod_team.team_label(team)}"
        if team == winner:
            roster = team_record_column(members, displays, player_colors, deck_data)
            container.add_item(ui.TextDisplay(f"{header}\n{roster}" if roster else header))
            gallery_items = []
            for s in members:
                data = deck_data.get(normalize_player_name(s.player_name))
                if data is not None and data.screenshot_url:
                    info = displays.get(normalize_player_name(s.player_name), {})
                    name = info.get("display_name") or s.player_name
                    gallery_items.append(
                        discord.MediaGalleryItem(media=data.screenshot_url, description=f"{name}'s deck"),
                    )
            if gallery_items:
                container.add_item(ui.MediaGallery(*gallery_items))
        else:
            lines = [header]
            for s in members:
                lines.append(team_record_line(s, displays, player_colors, deck_data))
            block = "\n".join(lines)
            if winner is not None:
                thumbnail_members = members[:1]
            else:
                thumbnail_members = [s for s in members if s.wins == 3 and s.losses == 0]
            thumbnail = None
            for s in thumbnail_members:
                key = normalize_player_name(s.player_name)
                data = deck_data.get(key)
                if data is not None and data.screenshot_url:
                    info = displays.get(key, {})
                    name = info.get("display_name") or s.player_name
                    thumbnail = ui.Thumbnail(data.screenshot_url, description=f"{name}'s deck")
                    break
            if thumbnail is not None:
                container.add_item(ui.Section(block, accessory=thumbnail))
            else:
                container.add_item(ui.TextDisplay(block))

    view.add_item(container)
    actions = ui.ActionRow()
    if guild_id and thread_id:
        actions.add_item(build_thread_link_button(guild_id, thread_id))
    actions.add_item(build_replays_link_button(event_name))
    view.add_item(actions)
    return view


async def build_team_championship_view_for_event(
    event_id: str, *, guild_id: int | None = None,
) -> ui.LayoutView | None:
    """Manager-free team championship card for /pod-champion re-posts. None when the pod carries no team
    assignment or no standings yet."""
    teams = await asyncio.to_thread(load_teams_sync, event_id)
    if not teams:
        return None
    players = await asyncio.to_thread(load_tournament_players_sync, event_id)
    prior = await asyncio.to_thread(load_matches, event_id)
    standings = pod_swiss.compute_standings(players, prior)
    if not standings:
        return None
    displays = await asyncio.to_thread(load_participant_displays, event_id)
    deck_data = await asyncio.to_thread(load_event_deck_data_sync, event_id)
    event_name = await asyncio.to_thread(load_event_name_sync, event_id)
    started_at = await asyncio.to_thread(load_event_started_at_sync, event_id)
    thread_id_str = await asyncio.to_thread(load_event_thread_id_sync, event_id)
    thread_id = int(thread_id_str) if thread_id_str else None
    return build_team_championship_view(
        standings, teams,
        event_name=event_name,
        displays=displays,
        player_colors=colors_only(deck_data),
        deck_data=deck_data,
        event_started_at=started_at,
        guild_id=guild_id,
        thread_id=thread_id,
    )


async def team_championship_deadline(manager: "PodDraftManager") -> None:
    """Hard cap: CHAMPIONSHIP_DEADLINE_SECONDS after finalize, post the showcase with whatever decks
    landed, forcing trophy-hype for the locked 3-0s the same way."""
    try:
        await asyncio.sleep(CHAMPIONSHIP_DEADLINE_SECONDS)
    except asyncio.CancelledError:
        return
    log.info(f"[TEAM] champion.deadline_reached event={manager.event_id}")
    await maybe_post_team_trophy_hype(manager, force=True)
    await maybe_post_team_championship(manager, force=True)


async def maybe_post_team_trophy_hype(manager: "PodDraftManager", *, force: bool = False) -> None:
    """Post the one-time 3-0 hype card as soon as the trophy set is decided and every 3-0's deck is
    complete — a still-open match elsewhere doesn't hold it back, and a losing-side 3-0 counts the
    same. Fires once per event; the in-memory flag guards the live path and the hype channel scan
    (inside post_trophy_hype) guards a restart re-post."""
    if manager.trophy_hype_posted:
        return
    event_id = manager.event_id
    board = await asyncio.to_thread(load_team_board_data, event_id)
    if not board.rounds:
        return
    prior = await asyncio.to_thread(load_matches, event_id)
    standings = pod_swiss.compute_standings(manager.tournament_players, prior)
    trophies = decided_trophy_standings(standings, board.rounds)
    if trophies is None:
        return
    if not trophies:
        log.info(f"[TEAM] trophy_hype.skip event={event_id} reason=no_3_0s")
        manager.trophy_hype_posted = True
        return
    deck_data = await asyncio.to_thread(load_event_deck_data_sync, event_id)
    incomplete = incomplete_decks(trophies, deck_data)
    if incomplete and not force:
        log.info(f"[TEAM] trophy_hype.skip event={event_id} reason=awaiting_decks missing={incomplete}")
        return

    thread = await manager._fetch_thread()
    guild = getattr(thread, "guild", None)
    thread_id = int(manager.thread_id) if isinstance(manager.thread_id, (int, str)) else None
    displays = await asyncio.to_thread(load_participant_displays, event_id)
    dm_info = await asyncio.to_thread(load_dm_info_sync, event_id)
    event_name = await asyncio.to_thread(load_event_name_sync, event_id)
    manager.trophy_hype_posted = True
    posted = await post_trophy_hype(
        event_id, guild, thread_id, trophies,
        event_name=event_name, displays=displays,
        player_colors=colors_only(deck_data), deck_data=deck_data, dm_info=dm_info,
        format_title=format_team_trophy_title,
    )
    if not posted:
        manager.trophy_hype_posted = False


def format_team_trophy_title(name: str, colors: str | None, short_event: str) -> str:
    emoji_run = format_deck_color_emojis(colors)
    suffix = f" with {emoji_run}" if emoji_run else ""
    return f"🏆 {name} 3-0s {short_event}{suffix}"


def decided_trophy_standings(standings, rounds) -> list | None:
    """The locked 3-0 standings, or None while any undefeated player still has a match open — the
    trophy set isn't final until nobody can join it. An undefeated player short of three wins
    (skipped match) neither blocks nor earns."""
    pending_keys = {
        normalize_player_name(n)
        for _, matches in rounds
        for m in matches if not m["winner_name"]
        for n in (m["a_name"], m["b_name"])
    }
    trophies = []
    for s in standings:
        if s.losses:
            continue
        if normalize_player_name(s.player_name) in pending_keys:
            return None
        if s.wins == 3:
            trophies.append(s)
    return trophies
