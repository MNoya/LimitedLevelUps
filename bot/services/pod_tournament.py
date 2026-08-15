"""Discord-driven Swiss bracket for the pod-draft post-draft phase.

After endDraft, the manager hands control here. We snapshot the roster, run pod_swiss for pairings,
persist pending pod_draft_matches rows, and post ONE message per round: a single embed listing all
pairings + one Select dropdown per match (placeholder "Report A vs B"). Players pick results; the
embed updates in place as each match is reported. When the round is fully reported, the next round
is paired and posted. Round 3 completion triggers champion finalization and the standings post.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Awaitable, Callable, NamedTuple, Sequence

import discord
from discord import ui
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from bot import emojis
from bot.commands.messages import MSG_POD_NO_MATCH_TO_REPORT, MSG_POD_RESULT_ALREADY_RECORDED
from bot.config import settings
from bot.discord_helpers import (
    NBSP,
    channel_matching_name,
    display_width,
    fetch_dm_user,
    first_image_url,
    player_url,
    snowflake_or_none,
)
from bot.slug import slugify
from bot.database import SessionLocal
from bot.models import Player as DbPlayer, PodDraftEvent, PodDraftMatch, PodDraftParticipant
from bot.services import bot_log as bot_log_mod, championship, pod_bracket, pod_round_robin, pod_swiss
from bot.services.pod_active import (
    ACTIVE_POD_MANAGERS,
    notify_card_phase,
    notify_pod_complete,
    notify_podium_posted,
)
from bot.services.pod_deck_color import (
    SAVED_MSG,
    DeckColorSelectView,
    NotInPodError,
    SubmitCallback,
    SubmitDeckButton,
    SubmitDeckView,
    format_deck_color_emojis,
)
from bot.services.player_stats import leaderboard_seat_order
from bot.services.ping_roles import (
    SET_CHAMPION_ROLE_NAME,
    SYNTHETIC_CHAMPION_TAG,
    champion_role_mention,
    grant_set_champion_title,
    swap_set_champion_role,
)
from bot.services.pod_roles import find_role
from bot.services.pod_pairing_select import DEFAULT_PAIRING_MODE
from bot.services.pod_replays import capture_event_replays
from bot.services.seventeenlands import SeventeenLandsClient
from bot.services.pod_drafts import (
    DM_KIND_ROUND,
    DM_KIND_SUBMIT_DECK,
    FinalStanding,
    OwnMatch,
    TOTAL_ROUNDS,
    has_arena_suffix,
    is_championship,
    normalize_player_name,
    strip_arena_suffix,
    _normalized_column,
    active_event_for_discord_user_in_dm,
    add_pairing,
    apply_seat_indexes,
    capture_deck_screenshot,
    caption_has_record_pattern,
    dm_messages_for_match,
    dm_messages_for_round,
    finalize_champion as finalize_db,
    get_participant_deck_state,
    list_event_participants_sync,
    load_event_id_by_thread_sync,
    load_event_name_sync,
    load_event_pairing_mode_sync,
    latest_reported_match,
    pod_page_url,
    load_event_thread_id_sync,
    own_open_matches,
    parse_record,
    participant_dm_info,
    participant_id_for_discord_user,
    participants_with_discord_for_event,
    seed_event_participants,
    set_match_result,
    set_participant_deck_colors,
    set_participant_deck_colors_by_id_sync,
    submit_deck_dm_for_participant,
    upsert_dm_message,
)
from bot.services.pod_swiss import BYE_NAME, BYE_SCORE, MatchOutcome, Player


if TYPE_CHECKING:
    from bot.services.pod_draft_manager import PodDraftManager


log = logging.getLogger(__name__)

SELECT_CUSTOM_PREFIX = "podmatchresult"
MAX_MATCHES_PER_ROUND = 5  # Discord caps ActionRows at 5; supports pods up to 10 players
SKIPPED_SENTINEL = "(skipped)"  # winner_name value for "Not played" matches
CLEAR_SENTINEL = "(clear)"  # transient value from the dropdown; commits NULL winner/score
RESULT_KEEP = "(keep)"  # reorganize-editor value: leave the recorded result untouched

MSG_DM_BYE = "⏭️ You win this round (bye)"
MSG_DM_DROPPED = "🏳️ You dropped from the pod"
MSG_DROPPED_TAG = "dropped"

# Pairing group kinds \u2014 the data model for a round's brackets, independent of how they render
WINNERS = "winners"
LOSERS = "losers"
PAIR_UP = "pair_up"
TROPHY = "trophy"
MIDDLE = "middle"
LAST_CHANCE = "last_chance"
UNDECIDED = "undecided"
GRACE_SECONDS = 60  # window after round completion during which edits regenerate the next round
BRACKET_EDIT_BLOCKED_MSG = "That result can't be changed now. A later round already reported a result"
RESULT_CORRECTED_LEAD = "Result corrected:"
RESULT_CLEARED_LEAD = "Result cleared:"
ORGANIZER_CORRECTED_LEAD = "Result corrected by Organizer:"
POD_RESULT_LOCKED_MSG = "This pod draft is finished. Results can no longer be changed"
MANAGE_ROUND_CUSTOM_PREFIX = "podmanageround"
ORGANIZER_ROLE_NAMES = frozenset({"admin", "moderator", "organizer"})
MSG_FIX_NOT_ORGANIZER = "Only Organizers can reorganize a round's matches"
MSG_FIX_NOT_POD_THREAD = "Open this from inside the pod-draft thread"
MSG_FIX_NO_MATCHES = "This round has no matches to reorganize yet"
MSG_FIX_PROMPT = "Reorganize Round {round_num}: pick a match, then set its players and result"
MSG_PICK_ROUND = "Pick the round to reorganize"
PICK_ROUND_PLACEHOLDER = "Choose Round"
MSG_FIX_SAME_PLAYER = "Pick two different players for the match"
MSG_FIX_MATCH_GONE = "That match no longer exists. Reopen the editor to see the current round"
MSG_DROP_PROMPT = "Pick the player who left. Every match they have left becomes a bye for their opponent"
MSG_DROP_NOBODY_LEFT = "Everyone in this pod has already dropped"
DROP_EMOJI = "🏳️"
POD_PAIRING_FAILED_MSG = (
    "⚠️ Round {round_num} pairings couldn't be generated. Reported results are safe, but the next "
    "round won't post on its own. An Organizer needs to start it."
)
POD_ROSTER_TOO_SMALL_MSG = "⚠️ At least 2 players are needed to start the tournament"
POD_ROSTER_ODD_MSG = (
    "⚠️ Pairings need an even number of players, but {count} are in the pod. Pairings can't be "
    "generated until the roster is evened out"
)
POD_REPAIR_FAILED_MSG = (
    "⚠️ Round {round_num} couldn't be re-paired after the edit, so its previous pairings stand. "
    "An Organizer should check the matchups"
)
ANNOUNCED_MAX_LOSSES = 1  # a 3-0 or 2-1 finish earns an announcement row; the thread keeps full standings
FULL_FIELD_POD_SIZE = 4  # at or below this the announcement carries the whole pod, not only its top records
DECK_GALLERY_CAP = 6  # Discord grids three per row; a seventh deck strands one on a row of its own
TROPHY_HYPE_HISTORY_LIMIT = 100  # messages scanned for a champion's own trophy post before the bot posts
CHAMPIONSHIP_DEADLINE_SECONDS = 600  # hard cap from R3 end: post the announcement with whatever decks landed
DECK_PING_DELAY_SECONDS = 300  # wait from R3 end before pinging whoever still owes a deck
DECK_NUDGE_AFTER_FINISHERS = 4  # players done playing before the gentle screenshot reminder is armed
DECK_NUDGE_DELAY_SECONDS = 120  # wait after arming, so a pod that posts its screenshots promptly gets no reminder
CHAMPIONSHIP_RECONCILE_WINDOW = timedelta(hours=24)  # startup sweep only revisits recently-finalized pods
TOURNAMENT_REHYDRATE_WINDOW = timedelta(hours=24)  # startup sweep only rebuilds managers for recently-scheduled pods


async def is_pod_organizer(bot, user: discord.abc.User) -> bool:
    """Owner, admin, moderator or organizer — the roles allowed to reorganize pod rounds and run backfill.
    Organizer is the role given to someone who runs pods without any wider moderation duty."""
    if await bot.is_owner(user):
        return True
    roles = getattr(user, "roles", None) or []
    return any(role.name.lower() in ORGANIZER_ROLE_NAMES for role in roles)


PODIUM_DECK_HEADER = "🏆 Podium is waiting on a few decks!"

DECK_NUDGE_MSG = "📸 Don't forget to share your deck screenshot here!"

DeckPingAudience = tuple[list[str], list[str]]  # (owes-screenshot ids, owes-colors ids)


def build_deck_ping(blocking: DeckPingAudience, other: DeckPingAudience, pod_url: str) -> str:
    """Compose the R3 deck-chase ping action-forward. Everyone who owes a screenshot or colors is
    pinged on one line each — blocking and non-blocking players merged so the ask isn't repeated.
    The "waiting" header only shows when a top finisher is actually blocking the podium post;
    once it's clear to go up the ping is just the pod-page nudge. Returns "" when nobody owes."""
    block_shots, block_colors = blocking
    other_shots, other_colors = other
    screenshot_ids = block_shots + other_shots
    colors_ids = block_colors + other_colors
    if not screenshot_ids and not colors_ids:
        return ""
    lines = []
    if block_shots or block_colors:
        lines.append(PODIUM_DECK_HEADER)
    if screenshot_ids:
        lines.append(f"Please post your deck screenshot {_mention_run(screenshot_ids)}")
    if colors_ids:
        lines.append(f"Submit your deck colors with the button below {_mention_run(colors_ids)}")
    lines.append("")
    lines.append(_pod_page_deck_line(pod_url))
    return "\n".join(lines)


def _pod_page_deck_line(pod_url: str) -> str:
    label = pod_url.split("://", 1)[-1]
    return f"Draft Recap at [{label}]({pod_url}) 🎨"


def _mention_run(discord_ids: list[str]) -> str:
    return " ".join(f"<@{i}>" for i in discord_ids)


def match_was_played(match: dict) -> bool:
    """True when a match has a real reported result — a "No Match Played" drop doesn't count."""
    winner = match.get("winner_name")
    return bool(winner) and winner != SKIPPED_SENTINEL


def actor_label(interaction: discord.Interaction) -> str:
    return getattr(interaction.user, "display_name", None) or str(interaction.user)


def surface_label(interaction: discord.Interaction) -> str:
    if _is_ephemeral_surface(interaction):
        return "/report-results"
    return "DM" if isinstance(interaction.channel, discord.DMChannel) else "thread"


def format_match_result_log(*, event_label: str, round_num: int, actor: str,
                             match_id: str, winner: str, score: str, surface: str) -> str:
    return (f"[{event_label}] R{round_num} {actor} reported {match_id}: "
            f"{winner} {score} (from {surface})")


def build_thread_link_button(guild_id: int | str, thread_id: int | str) -> ui.Button:
    """`:manat: Thread` link button jumping to the pod-draft thread. Shared by the champion
    announcement view and `/pod-standings` when invoked outside the event's thread."""
    return ui.Button(
        label="Thread",
        style=discord.ButtonStyle.link,
        url=f"https://discord.com/channels/{guild_id}/{thread_id}",
        emoji=emojis.get_emoji("manat"),
    )


def build_podium_link_button(url: str) -> ui.Button:
    """🏆 Podium link button jumping to the pod's podium post. Shared by the scheduled card, the thread's
    registered embed and the Play Again sign-off."""
    return ui.Button(label="Podium", style=discord.ButtonStyle.link, url=url, emoji="🏆")


def build_replays_link_button(event_name: str) -> ui.Button:
    return ui.Button(
        label="Draft Recap",
        style=discord.ButtonStyle.link,
        url=pod_page_url(event_name),
        emoji=emojis.get_emoji("llu") or "🎬",
    )


async def _dm_round_pairings(
    bot_client,
    event_id: str,
    round_num: int,
    pending_rows: list[tuple[str, str, str]],
    pairings_url: str,
    reuse_dms: dict[tuple[int, str], tuple[str, str]] | None = None,
) -> None:
    """DM each linked participant their opponent for this round, with a single-match dropdown
    so they can report from DM. Persists each DM message ref so later edits can sync.

    `reuse_dms` carries the pairing DMs a re-pair is replacing; a recipient found there has their old
    DM rewritten to the new opponent instead of receiving a second one."""
    dm_info = await asyncio.to_thread(load_dm_info_sync, event_id)
    event_name = await asyncio.to_thread(load_event_name_sync, event_id)
    match_states = await asyncio.to_thread(_load_round_states, event_id, round_num)
    dropped = await asyncio.to_thread(load_dropped_names, event_id)
    mark_trophy_match(match_states, round_num)
    by_match_id = {m["match_id"]: m for m in match_states}
    for match_id, a_name, b_name in pending_rows:
        match_state = by_match_id.get(match_id)
        a_key = normalize_player_name(a_name)
        b_key = normalize_player_name(b_name)
        for recipient_key, opponent_key in ((a_key, b_key), (b_key, a_key)):
            if recipient_key in dropped:
                continue
            recipient = dm_info.get(recipient_key)
            reuse = None
            if reuse_dms and recipient is not None:
                reuse = reuse_dms.get((round_num, recipient.participant_id))
            await _send_pairing_dm(bot_client, dm_info, recipient_key, opponent_key, round_num, pairings_url,
                                   event_id=event_id, match_state=match_state, event_name=event_name,
                                   updated=reuse is not None, reuse=reuse)


def load_dm_info_sync(event_id: str):
    with SessionLocal() as session:
        return participant_dm_info(session, event_id)


class ParticipantDeckData(NamedTuple):
    colors: str | None
    screenshot_url: str | None
    screenshot_caption: str | None


def load_event_deck_data_sync(event_id: str) -> dict[str, ParticipantDeckData]:
    """Return normalized_name → deck colors + screenshot URL + caption for every participant."""
    with SessionLocal() as session:
        rows = session.execute(
            select(
                PodDraftParticipant.draftmancer_name,
                PodDraftParticipant.display_name,
                PodDraftParticipant.deck_colors,
                PodDraftParticipant.deck_screenshot_url,
                PodDraftParticipant.deck_screenshot_caption,
            )
            .where(PodDraftParticipant.event_id == event_id)
        ).all()
    out: dict[str, ParticipantDeckData] = {}
    for dm, dn, dc, ds, dcap in rows:
        data = ParticipantDeckData(colors=dc, screenshot_url=ds, screenshot_caption=dcap)
        for src in (dm, dn):
            if src:
                out[normalize_player_name(src)] = data
    return out


def colors_only(deck_data: dict[str, ParticipantDeckData]) -> dict[str, str | None]:
    return {k: v.colors for k, v in deck_data.items()}


def _event_has_draft_log_sync(event_id: str) -> bool:
    """True when the event has a captured draft log, so the in-site reviewer has something to show."""
    with SessionLocal() as session:
        return session.execute(
            select(PodDraftEvent.draft_log_gz).where(PodDraftEvent.id == event_id)
        ).scalar_one_or_none() is not None


def load_event_started_at_sync(event_id: str) -> datetime | None:
    with SessionLocal() as session:
        return session.execute(
            select(PodDraftEvent.event_time).where(PodDraftEvent.id == event_id)
        ).scalar_one_or_none()


def championship_posted_at_sync(event_id: str) -> datetime | None:
    with SessionLocal() as session:
        return session.execute(
            select(PodDraftEvent.championship_posted_at).where(PodDraftEvent.id == event_id)
        ).scalar_one_or_none()


def mark_championship_posted_sync(event_id: str) -> None:
    with SessionLocal() as session:
        session.execute(
            update(PodDraftEvent)
            .where(PodDraftEvent.id == event_id, PodDraftEvent.championship_posted_at.is_(None))
            .values(championship_posted_at=datetime.now(timezone.utc))
        )
        session.commit()


def load_tournament_players_sync(event_id: str) -> list[pod_swiss.Player]:
    """Rebuild pod_swiss.Player list from participants — used when the in-memory manager isn't
    around (e.g. after a bot restart, or for the standalone /pod-standings command)."""
    with SessionLocal() as session:
        rows = session.execute(
            select(PodDraftParticipant.draftmancer_name, PodDraftParticipant.display_name)
            .where(PodDraftParticipant.event_id == event_id)
        ).all()
    return [
        pod_swiss.Player(id=dm or dn, name=dn or dm)
        for dm, dn in rows
        if (dm or dn)
    ]


def _load_participant_standings_sync(event_id: str) -> list[pod_swiss.Standing]:
    """Standings straight from stored placements/records, for events with no match rows
    (record-only backfills). Tiebreaker percentages are zeroed — the placement is the order."""
    with SessionLocal() as session:
        rows = session.execute(
            select(
                PodDraftParticipant.draftmancer_name,
                PodDraftParticipant.display_name,
                PodDraftParticipant.placement,
                PodDraftParticipant.record,
            )
            .where(
                PodDraftParticipant.event_id == event_id,
                PodDraftParticipant.placement.isnot(None),
            )
            .order_by(PodDraftParticipant.placement)
        ).all()
    standings = []
    for dm, dn, placement, record in rows:
        name = dm or dn
        wins, losses = parse_record(record)
        standings.append(pod_swiss.Standing(
            rank=placement, player_id=name, player_name=name,
            wins=wins, losses=losses, omw_pct=0.0, gw_pct=0.0, ogw_pct=0.0,
        ))
    return standings


def short_event_name(event_name: str | None) -> str | None:
    """Drops anything after the first ' - '."""
    if not event_name:
        return None
    return event_name.split(" - ", 1)[0].strip()


_RANK_MEDALS: dict[int, str] = {1: "🥇", 2: "🥈", 3: "🥉"}


def _build_standings_row(
    s: pod_swiss.Standing,
    *,
    displays: dict[str, dict],
    player_colors: dict[str, str | None],
    deck_data: dict[str, ParticipantDeckData],
    leaderboard_url: str | None,
    event_name: str | None = None,
    event_has_log: bool = False,
    inline_caption: bool = False,
    show_medal: bool = True,
) -> str:
    """One standings row used by both the V2 announcement and the thread-side classic embed:
    `{rank}. {medal} {name}  {wins}-{losses}  {colors}  [Draft Log]({url}) 📜`.
    The Draft Log link points at the in-site reviewer keyed on the player's slug, so it needs both
    event_name and a resolved slug to render. Set inline_caption to splice an italicized caption between
    the W-L record and the color glyph."""
    key = normalize_player_name(s.player_name)
    info = displays.get(key, {})
    name = info.get("display_name") or s.player_name
    slug = info.get("slug")
    data = deck_data.get(key)
    medal = _RANK_MEDALS.get(s.rank) if show_medal else None
    prefix = f"{s.rank}. {medal} " if medal else f"{s.rank}. "
    rendered = f"[{name}]({player_url(slug)})" if slug and leaderboard_url else name
    color_glyph = format_deck_color_emojis(player_colors.get(key))
    color_suffix = f"  {color_glyph}" if color_glyph else ""
    log_suffix = ""
    if event_has_log and slug and event_name:
        review_url = f"{pod_page_url(event_name)}/{slug}"
        log_suffix = f"  [Draft Log]({review_url}) 📜"
    caption_cleaned = (
        clean_caption(data.screenshot_caption)
        if inline_caption and data is not None and data.screenshot_caption else ""
    )
    caption_inline = f"  _{escape_italics(caption_cleaned)}_" if caption_cleaned else ""
    dropped_suffix = f"  _{MSG_DROPPED_TAG}_" if info.get("dropped") else ""
    return (
        f"{prefix}{rendered}  {s.wins}-{s.losses}{dropped_suffix}"
        f"{caption_inline}{color_suffix}{log_suffix}"
    )


def build_pairing_dm_embed(
    *,
    round_num: int,
    opponent_label: str,
    opponent_arena: str | None,
    pairings_url: str | None,
    event_name: str | None = None,
    updated: bool = False,
    match_state: dict | None = None,
    viewer_is_a: bool | None = None,
) -> discord.Embed:
    """Single source of truth for round-start + pairings-updated DMs.

    `opponent_label` is the pre-formatted opponent string — see `_opponent_dm_label`. When
    `match_state` carries a winner, a status line ('✅ You won 2-1' / '❌ You lost 2-0' /
    '🚫 Not played' / the bye line) is appended; the line's
    perspective is set by `viewer_is_a` (True if the recipient is player_a in the match).
    An odd field's bye has no opponent to name, so that DM carries the bye line alone.
    """
    short = short_event_name(event_name)
    suffix = "Updated" if updated else "Started"
    title_round = f"Round {round_num} {suffix}"
    title = f"{short} · {title_round}" if short else title_round

    mtga = emojis.get("mtga")
    arena_part = f" {mtga} `{opponent_arena}`" if opponent_arena else ""
    no_opponent = bool(match_state) and BYE_NAME in (match_state.get("a_name"), match_state.get("b_name"))
    body_lines = [] if no_opponent else [f"Opponent: {opponent_label}{arena_part}"]

    if match_state and match_state.get("winner_name"):
        winner = match_state["winner_name"]
        score = match_state.get("score") or ""
        you_won = None
        if viewer_is_a is not None:
            winner_is_a = winner.lower() == (match_state.get("a_name") or "").lower()
            you_won = winner_is_a if viewer_is_a else not winner_is_a
        if winner == SKIPPED_SENTINEL:
            body_lines.append("🚫 Not played")
        elif score == BYE_SCORE:
            body_lines.append(MSG_DM_DROPPED if you_won is False else MSG_DM_BYE)
        elif you_won is not None:
            body_lines.append(f"✅ You won {score}" if you_won else f"▫️ You lost {score}")
        else:
            body_lines.append(f"Result: {winner} {score}")

    if pairings_url:
        link_prefix = emojis.get("manat") or "↳"
        body_lines.append(f"{link_prefix} [**View Pairings**]({pairings_url})")

    color = discord.Color.yellow() if updated else discord.Color.green()
    if match_state and match_state.get("winner_name"):
        color = discord.Color.dark_grey()
    return discord.Embed(
        title=title,
        description="\n".join(body_lines),
        color=color,
    )


def _opponent_dm_label(opponent, fallback_key: str) -> str:
    """Opponent name for a pod DM. DMs have no guild context, so the server nickname is rendered as
    text — a `<@id>` mention would resolve to the opponent's global username instead. `display_name`
    already carries the resolved LLU nickname (see `participant_dm_info`)."""
    name = opponent.display_name if opponent else fallback_key
    return f"**{name}**"


async def _send_pairing_dm(
    bot_client,
    dm_info: dict,
    recipient_key: str,
    opponent_key: str,
    round_num: int,
    pairings_url: str,
    *,
    event_id: str | None = None,
    match_state: dict | None = None,
    event_name: str | None = None,
    updated: bool = False,
    reuse: tuple[str, str] | None = None,
) -> None:
    recipient = dm_info.get(recipient_key)
    if recipient is None or not recipient.discord_id:
        return
    opponent = dm_info.get(opponent_key)
    opp_label = _opponent_dm_label(opponent, opponent_key)
    opp_arena = opponent.arena_name if opponent else None
    viewer_is_a = None
    if match_state:
        viewer_is_a = recipient_key == normalize_player_name(match_state.get("a_name") or "")
    embed = build_pairing_dm_embed(
        round_num=round_num,
        opponent_label=opp_label,
        opponent_arena=opp_arena,
        pairings_url=pairings_url,
        event_name=event_name,
        updated=updated,
        match_state=match_state,
        viewer_is_a=viewer_is_a,
    )
    view = RoundResultsView([match_state]) if match_state else None
    msg = None
    try:
        if reuse is not None:
            msg = await _edit_pairing_dm(bot_client, reuse, embed, view)
        if msg is None:
            user = await fetch_dm_user(bot_client, recipient.discord_id)
            if user is None:
                return
            msg = await user.send(embed=embed, view=view) if view else await user.send(embed=embed)
    except discord.Forbidden:
        log.info(f"pairing DM blocked for user {recipient.discord_id}")
        return
    except discord.HTTPException:
        log.warning("pairing DM failed", exc_info=True)
        return

    if event_id and match_state and msg is not None:
        await asyncio.to_thread(
            _persist_dm_message_sync,
            event_id=event_id,
            participant_id=recipient.participant_id,
            kind=DM_KIND_ROUND,
            round_num=round_num,
            match_id=match_state["match_id"],
            dm_channel_id=str(msg.channel.id),
            dm_message_id=str(msg.id),
        )


async def _edit_pairing_dm(bot_client, ref: tuple[str, str], embed, view) -> discord.Message | None:
    """Rewrite an already-delivered pairing DM in place, so a re-pair reaches the player without a
    second notification. None when the message is gone, which falls back to sending a fresh one."""
    channel_id, message_id = ref
    try:
        channel = bot_client.get_channel(int(channel_id)) or await bot_client.fetch_channel(int(channel_id))
        msg = await channel.fetch_message(int(message_id))
        return await msg.edit(embed=embed, view=view)
    except discord.HTTPException:
        log.info(f"pairing DM {message_id} could not be edited, sending a new one")
        return None


def _persist_dm_message_sync(
    *,
    event_id: str,
    participant_id: str,
    kind: str,
    round_num: int | None,
    match_id: str | None,
    dm_channel_id: str,
    dm_message_id: str,
) -> None:
    with SessionLocal() as session:
        upsert_dm_message(
            session,
            event_id=event_id,
            participant_id=participant_id,
            kind=kind,
            round_num=round_num,
            match_id=match_id,
            dm_channel_id=dm_channel_id,
            dm_message_id=dm_message_id,
        )
        session.commit()


async def _resolve_event_for_interaction(
    interaction: discord.Interaction,
) -> tuple[str | None, str | None]:
    """Map interaction (thread or DM) to (event_id, thread_id). DM interactions look up the user's
    most recent unfinished pod-draft so deck-color/review save works from DM too."""
    discord_id = str(interaction.user.id)
    if isinstance(interaction.channel, discord.DMChannel):
        result = await asyncio.to_thread(_load_active_event_for_user_sync, discord_id)
        return result if result else (None, None)
    thread_id = str(interaction.channel_id)
    event_id = await asyncio.to_thread(load_event_id_by_thread_sync, thread_id)
    return event_id, thread_id


def _load_active_event_for_user_sync(discord_id: str) -> tuple[str, str] | None:
    with SessionLocal() as session:
        return active_event_for_discord_user_in_dm(session, discord_id)


async def live_deck_state_lookup(interaction: discord.Interaction) -> str | None:
    """Resolve the participant; raise NotInPodError if the user isn't in any active pod."""
    event_id, thread_id = await _resolve_event_for_interaction(interaction)
    if thread_id is None:
        raise NotInPodError()
    discord_id = str(interaction.user.id)

    def _do() -> tuple[bool, str | None]:
        with SessionLocal() as session:
            return get_participant_deck_state(session, thread_id, discord_id)

    in_pod, color = await asyncio.to_thread(_do)
    if not in_pod:
        raise NotInPodError()
    return color or None


async def live_deck_color_submit(interaction: discord.Interaction, color: str) -> None:
    event_id, thread_id = await _resolve_event_for_interaction(interaction)
    await save_deck_colors(interaction, event_id, thread_id, color)


def bound_deck_color_submit(event_id: str, thread_id: str) -> SubmitCallback:
    """A deck-color submit pinned to one pod, for surfaces that already resolved it. The interaction-based
    resolver reads the pod out of the channel, which only works from the pod thread or a DM; a
    `/report-results` card can be opened anywhere, so it binds the pod it built itself from."""
    async def _submit(interaction: discord.Interaction, color: str) -> None:
        await save_deck_colors(interaction, event_id, thread_id, color)

    return _submit


async def save_deck_colors(
    interaction: discord.Interaction, event_id: str | None, thread_id: str | None, color: str,
) -> None:
    if thread_id is None:
        raise NotInPodError()
    discord_id = str(interaction.user.id)

    def _do() -> bool:
        with SessionLocal() as session:
            ok = set_participant_deck_colors(session, thread_id, discord_id, color)
            session.commit()
            return ok

    ok = await asyncio.to_thread(_do)
    if not ok:
        raise NotInPodError()

    actor = actor_label(interaction)
    surface = surface_label(interaction)
    if event_id is None:
        log.info(f"{actor} saved deck colors: {color} (from {surface}, no event)")
        return
    event_name = await asyncio.to_thread(load_event_name_sync, event_id)
    log.info(f"[{event_name}] {actor} saved deck colors: {color} (from {surface})")
    await _refresh_standings_after_deck_change(interaction.client, event_id, thread_id)
    asyncio.create_task(_refresh_submit_deck_dm(interaction.client, event_id, discord_id))


async def _refresh_standings_after_deck_change(
    client: discord.Client, event_id: str, thread_id: str,
) -> None:
    """Re-render the live standings after a deck color changes, on whichever surface owns them: a live
    manager's team or individual standings, else the persisted standings rebuild for the thread."""
    manager = ACTIVE_POD_MANAGERS.get(event_id)
    if manager is not None:
        if manager.pairing_mode == "team":
            from bot.services.pod_team_flow import refresh_team_standings_embed
            from bot.services.pod_team_showcase import maybe_post_team_championship, maybe_post_team_trophy_hype

            await refresh_team_standings_embed(manager)
            await maybe_post_team_trophy_hype(manager)
            await maybe_post_team_championship(manager)
        else:
            await _post_or_update_live_standings(manager)
            await maybe_post_championship(manager)
    else:
        await refresh_standings_for_event(client, event_id, thread_id)


async def open_organizer_color_panel(interaction: discord.Interaction) -> bool:
    """Submit Colors override for organizers: an admin or moderator clicking the button in a pod thread
    gets a per-player color picker for the whole roster instead of the personal one, so any player's
    deck colors can be set from one place. Returns False to fall through to the personal flow — a
    non-organizer, a click outside a guild, or one outside a pod thread."""
    if interaction.guild is None:
        return False
    if not await is_pod_organizer(interaction.client, interaction.user):
        return False
    event_id, thread_id = await _resolve_event_for_interaction(interaction)
    if event_id is None or thread_id is None:
        return False
    roster = await asyncio.to_thread(list_event_participants_sync, event_id)
    if not roster:
        return False
    await interaction.response.send_message(
        view=OrganizerColorPanel(event_id, thread_id, roster), ephemeral=True,
    )
    return True


class OrganizerColorPanel(discord.ui.View):
    """Ephemeral organizer tool: pick any pod player, then set their deck colors. Per-invocation and
    short-lived, so it carries no persistent custom_ids."""

    def __init__(
        self, event_id: str, thread_id: str, roster: list[tuple[str, str, str | None]],
    ) -> None:
        super().__init__(timeout=300)
        self.add_item(_OrganizerPlayerSelect(event_id, thread_id, roster))


class _OrganizerPlayerSelect(discord.ui.Select):
    ORGANIZER_COLOR_PLACEHOLDER = "Choose a Player"
    NO_COLORS = "No colors yet"

    def __init__(
        self, event_id: str, thread_id: str, roster: list[tuple[str, str, str | None]],
    ) -> None:
        self._event_id = event_id
        self._thread_id = thread_id
        self._colors = {pid: colors for pid, _, colors in roster}
        options = [
            discord.SelectOption(
                label=name[:100], value=pid, description=(colors or self.NO_COLORS)[:100],
            )
            for pid, name, colors in roster
        ]
        super().__init__(
            placeholder=self.ORGANIZER_COLOR_PLACEHOLDER, min_values=1, max_values=1, options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        participant_id = self.values[0]
        submit = _organizer_color_submit(self._event_id, self._thread_id, participant_id)
        await interaction.response.send_message(
            view=DeckColorSelectView(submit, current_value=self._colors.get(participant_id)),
            ephemeral=True,
        )


def _organizer_color_submit(event_id: str, thread_id: str, participant_id: str):
    async def _submit(interaction: discord.Interaction, color: str) -> None:
        saved = await asyncio.to_thread(set_participant_deck_colors_by_id_sync, participant_id, color)
        if saved is None:
            raise NotInPodError()
        log.info(f"[{event_id}] {actor_label(interaction)} set deck colors for {participant_id}: {color}")
        await _refresh_standings_after_deck_change(interaction.client, event_id, thread_id)

    return _submit


def build_live_submit_deck_view() -> SubmitDeckView:
    return SubmitDeckView(live_deck_color_submit, live_deck_state_lookup, open_organizer_color_panel)


def build_live_submit_deck_button() -> SubmitDeckButton:
    """A standalone Submit Deck button for composing into other Views (e.g. the in-thread standings).

    Shares the persistent custom_id ('poddecksubmit') with build_live_submit_deck_view, so the
    persistent view registered at startup catches the click regardless of which message it came from.
    """
    return SubmitDeckButton(live_deck_color_submit, live_deck_state_lookup, open_organizer_color_panel)


def build_live_deck_color_select_view(current_value: str | None = None) -> DeckColorSelectView:
    """Direct-dropdown variant for DMs — the select is visible on the message itself."""
    return DeckColorSelectView(live_deck_color_submit, current_value=current_value, persistent=True)


def _build_submit_deck_dm_embed(deck_colors: str | None) -> discord.Embed:
    """Embed body for the Submit Deck DM. Pre-submit shows the prompt; post-submit collapses to
    SAVED_MSG (the dropdown default already conveys the saved value visually)."""
    if deck_colors is not None:
        body = SAVED_MSG
    else:
        body = "🎨 **Submit your deck colors with the dropdown below**"
    return discord.Embed(description=body)


async def send_submit_deck_dms(bot_client, event_id: str) -> None:
    """At Round 1 start: DM each participant a Submit Deck button. Idempotent — skips participants
    whose Submit Deck DM is already tracked. DM permission errors are logged and skipped silently."""
    participants = await asyncio.to_thread(_load_participants_with_discord_sync, event_id)
    for p in participants:
        existing = await asyncio.to_thread(_load_submit_deck_dm_sync, p["participant_id"])
        if existing is not None:
            continue
        embed = _build_submit_deck_dm_embed(p["deck_colors"])
        view = build_live_deck_color_select_view(p["deck_colors"])
        msg = None
        try:
            user = await fetch_dm_user(bot_client, p["discord_id"])
            if user is None:
                continue
            msg = await user.send(embed=embed, view=view)
        except discord.Forbidden:
            log.info(f"submit-deck DM blocked for {p['discord_id']}")
            continue
        except discord.HTTPException:
            log.warning("submit-deck DM failed", exc_info=True)
            continue
        if msg is not None:
            await asyncio.to_thread(
                _persist_dm_message_sync,
                event_id=event_id,
                participant_id=p["participant_id"],
                kind=DM_KIND_SUBMIT_DECK,
                round_num=None,
                match_id=None,
                dm_channel_id=str(msg.channel.id),
                dm_message_id=str(msg.id),
            )


def _load_participants_with_discord_sync(event_id: str) -> list[dict]:
    with SessionLocal() as session:
        return participants_with_discord_for_event(session, event_id)


def _load_submit_deck_dm_sync(participant_id: str):
    with SessionLocal() as session:
        row = submit_deck_dm_for_participant(session, participant_id)
        if row is not None:
            session.expunge(row)
        return row


def _load_participant_deck_state_sync(event_id: str, discord_id: str) -> str | None:
    with SessionLocal() as session:
        row = session.execute(
            select(PodDraftParticipant.deck_colors)
            .join(DbPlayer, DbPlayer.id == PodDraftParticipant.player_id)
            .where(
                PodDraftParticipant.event_id == event_id,
                DbPlayer.discord_id == discord_id,
            )
        ).first()
    return row[0] if row else None


async def _refresh_submit_deck_dm(bot_client, event_id: str, discord_id: str) -> None:
    """Edit the user's Submit Deck DM so the body reflects their current saved state."""
    participant_id = await asyncio.to_thread(_load_participant_id_sync, event_id, discord_id)
    if participant_id is None:
        return
    deck_colors = await asyncio.to_thread(_load_participant_deck_state_sync, event_id, discord_id)
    row = await asyncio.to_thread(_load_submit_deck_dm_sync, participant_id)
    if row is not None:
        await _edit_submit_deck_dm(
            bot_client, row, _build_submit_deck_dm_embed(deck_colors), deck_colors,
        )


async def _edit_submit_deck_dm(
    bot_client, dm_row, embed: discord.Embed, deck_colors: str | None,
) -> None:
    try:
        channel = bot_client.get_channel(int(dm_row.dm_channel_id)) \
            or await bot_client.fetch_channel(int(dm_row.dm_channel_id))
        msg = await channel.fetch_message(int(dm_row.dm_message_id))
        await msg.edit(
            content=None,
            embed=embed,
            view=build_live_deck_color_select_view(deck_colors),
        )
    except discord.HTTPException:
        log.warning(f"refresh_submit_deck_dm: could not edit DM {dm_row.dm_message_id}", exc_info=True)


def _load_participant_id_sync(event_id: str, discord_id: str) -> str | None:
    with SessionLocal() as session:
        return participant_id_for_discord_user(session, event_id, discord_id)


async def alert_thread_and_owner(manager, thread_message: str, ops_summary: str, fingerprint: str) -> None:
    """Surface a pod failure both in the thread (so organizers see it live) and in the bot-log channel
    (so the owner is paged). Best-effort on each leg."""
    try:
        thread = await manager._fetch_thread()
        if thread is not None:
            await thread.send(thread_message)
    except Exception:
        log.warning("could not post pod failure notice to thread", exc_info=True)
    try:
        await bot_log_mod.get(manager.bot).post(ops_summary, fingerprint=fingerprint, tag="POD")
    except Exception:
        log.warning("could not post pod failure notice to bot-log", exc_info=True)


async def start_tournament(manager: "PodDraftManager") -> None:
    """Snapshot the Draftmancer roster, post Round 1 pairings + result dropdowns in the thread."""
    roster = list(manager.tournament_roster)
    if len(roster) < 2:
        log.warning("not enough players in roster for %s: %s", manager.event_id, roster)
        await alert_thread_and_owner(
            manager, POD_ROSTER_TOO_SMALL_MSG,
            f"Pod `{manager.event_id}` can't start: only {len(roster)} player(s) in the roster.",
            fingerprint=f"pod_roster_small:{manager.event_id}",
        )
        return
    if len(roster) % 2 != 0:
        log.warning("odd-numbered roster (%d players) for %s — Swiss not supported", len(roster), manager.event_id)
        await alert_thread_and_owner(
            manager, POD_ROSTER_ODD_MSG.format(count=len(roster)),
            f"Pod `{manager.event_id}` can't start: odd roster of {len(roster)} players (Swiss needs even).",
            fingerprint=f"pod_roster_odd:{manager.event_id}",
        )
        return

    manager.tournament_players = [Player(id=name, name=name) for name in roster]
    effective_mode = manager.pairing_mode or DEFAULT_PAIRING_MODE
    if effective_mode == "bracket" and not pod_bracket.supports(len(roster)):
        effective_mode = "swiss"
    if effective_mode == "roundrobin" and not pod_round_robin.supports(len(roster)):
        effective_mode = "swiss"
    manager.pairing_mode = effective_mode
    await asyncio.to_thread(persist_pairing_mode, manager.event_id, effective_mode)
    # Idempotent re-seed — _start_draft already seeded at draft-start time. Kept as a safety net
    # in case that call didn't fire cleanly (bot restart mid-draft, etc).
    await asyncio.to_thread(_seed_participants_sync, manager.event_id, roster)
    if effective_mode == "team":
        from bot.services.pod_team_flow import start_team_tournament

        await start_team_tournament(manager)
        return
    if effective_mode == "roundrobin":
        await asyncio.to_thread(manager.persist_seat_indexes_from_log)
    await advance_to_round(manager, 1)


def persist_pairing_mode(event_id: str, mode: str) -> None:
    values = {"pairing_mode": mode}
    if mode == "team":
        values["closed_decklist"] = True
    with SessionLocal() as session:
        session.execute(update(PodDraftEvent).where(PodDraftEvent.id == event_id).values(**values))
        session.commit()


def persist_seating_mode(event_id: str, mode: str) -> None:
    with SessionLocal() as session:
        session.execute(update(PodDraftEvent).where(PodDraftEvent.id == event_id).values(seating_mode=mode))
        session.commit()


def _seed_participants_sync(event_id: str, roster: list[str]) -> None:
    with SessionLocal() as session:
        seed_event_participants(session, event_id, roster)
        session.commit()


def roster_in_seat_order(names: list[str], seats: dict[str, int]) -> list[str]:
    """Roster ordered by draft seat; unseated names keep their given order after the seated ones."""
    if not seats:
        return list(names)
    return sorted(names, key=lambda n: seats.get(normalize_player_name(n), len(names)))


def _apply_fallback_seats_sync(event_id: str, seating_mode: str, names: list[str],
                               desired_seating: list[str] | None) -> bool:
    """Round-1 seats normally come from the draft log; when that read is incomplete, recompute the order
    the table was actually seated with — leaderboard ranks or the organizer's manual order — and persist
    it so pairing reflects the seating instead of a random shuffle. Returns True when a full order was
    written. No-op for random seating, which has no intended order to recover."""
    with SessionLocal() as session:
        if seating_mode == "leaderboard":
            order = leaderboard_seat_order(session, names, championship.rank_override(session, event_id))
        elif seating_mode == "manual" and desired_seating:
            roster = set(names)
            order = [name for name in desired_seating if name in roster]
        else:
            return False
        if len(order) != len(names):
            return False
        apply_seat_indexes(session, event_id, order)
        session.commit()
    return True


async def _recover_round1_seats(manager, players, seats: dict[str, int]) -> dict[str, int]:
    """Return seats covering every player. When the log-derived map misses someone, fall back to the
    applied seating order and re-read; otherwise return the map unchanged."""
    if all(normalize_player_name(p.id) in seats for p in players):
        return seats
    names = [p.id for p in players]
    applied = await asyncio.to_thread(
        _apply_fallback_seats_sync, manager.event_id, manager.seating_mode, names, manager.desired_seating,
    )
    if not applied:
        return seats
    log.warning(
        f"[SEATING] round1_seat_fallback event={manager.event_id} mode={manager.seating_mode} "
        f"log_seats={len(seats)} expected={len(players)}"
    )
    return await asyncio.to_thread(load_seat_indexes, manager.event_id)


async def advance_to_round(manager: "PodDraftManager", round_num: int) -> None:
    """Compute pairings for round_num via pod_swiss, persist pending rows, post pairings + views."""
    players = manager.tournament_players
    prior = await asyncio.to_thread(load_matches, manager.event_id)
    await persist_round_entry_artifacts(manager, round_num)
    seats = await asyncio.to_thread(load_seat_indexes, manager.event_id)
    if round_num == 1 and manager.pairing_mode != "random":
        seats = await _recover_round1_seats(manager, players, seats)
    pairing_players = players
    if seats and manager.pairing_mode != "random":
        pairing_players = [replace(p, seat=seats.get(normalize_player_name(p.id))) for p in players]
    try:
        if manager.pairing_mode == "roundrobin":
            pairings = pod_round_robin.pair_round(pairing_players, round_num)
        else:
            pairings = pod_swiss.pair_round(
                pairing_players, prior, round_num, final_round=round_num == TOTAL_ROUNDS,
            )
    except ValueError as e:
        log.error("pairing for round %d failed for %s: %s", round_num, manager.event_id, e)
        await alert_thread_and_owner(
            manager, POD_PAIRING_FAILED_MSG.format(round_num=round_num),
            f"Pod `{manager.event_id}` round {round_num} pairing failed: {e}",
            fingerprint=f"pod_pairing_failed:{manager.event_id}:{round_num}",
        )
        return

    pending_rows = await asyncio.to_thread(insert_pending_matches, manager.event_id, round_num, pairings)
    manager.current_round = round_num

    thread = await manager._fetch_thread()
    if thread is None:
        return

    standings_by_id = {s.player_id: s for s in pod_swiss.compute_standings(players, prior)}
    displays = await asyncio.to_thread(load_participant_displays, manager.event_id)
    match_states = [_state_for_pending(match_id, a, b, standings_by_id, displays) for match_id, a, b in pending_rows]
    await asyncio.to_thread(stamp_reported_byes, manager.event_id, round_num, match_states)
    mark_trophy_match(match_states, round_num)
    if manager.pairing_mode == "bracket":
        for m in match_states:
            m["allow_skip"] = round_num == TOTAL_ROUNDS
    if round_num == 1 and seats and manager.pairing_mode != "random":
        _attach_seats(match_states, seats)
    embed = round_embed(round_num, match_states)
    view = RoundResultsView(match_states, round_num=round_num)
    posted: discord.Message | None = None
    try:
        posted = await thread.send(embed=embed, view=view)
    except Exception:
        log.warning("could not post round %d message", round_num, exc_info=True)

    if posted is not None:
        manager.round_messages[round_num] = posted
        await _pin_round_message(posted, round_num)
        await _dm_round_pairings(manager.bot, manager.event_id, round_num, pending_rows, posted.jump_url)
        if round_num == 1:
            asyncio.create_task(send_submit_deck_dms(manager.bot, manager.event_id))
        await _attach_round_link(manager, round_num - 1)
        await settle_auto_forfeits(manager.bot, manager.event_id, [mid for mid, _, _ in pending_rows])


async def persist_round_entry_artifacts(manager: "PodDraftManager", round_num: int) -> None:
    """Round-entry snapshots that must fire once regardless of pairing mode: freeze seating from the
    draft log as round 1 opens, freeze the post-deckbuild decklists as round 2 opens once round 1 has
    settled the decks. Bracket and Swiss advancement both call this so neither path can skip it."""
    if round_num == 1:
        await asyncio.to_thread(manager.persist_seat_indexes_from_log)
    elif round_num == 2:
        await asyncio.to_thread(manager.persist_decklists_from_log)


def _round_nav_link(manager, round_num: int) -> tuple[str | None, str | None]:
    """(url, label) for the jump link shown under a round's dropdowns: the next round's message once
    it exists, or the standings message after the final round. (None, None) when no target yet."""
    if manager is None:
        return None, None
    if round_num < TOTAL_ROUNDS:
        next_msg = manager.round_messages.get(round_num + 1)
        if next_msg is None:
            return None, None
        return next_msg.jump_url, f"Go to Round {round_num + 1}"
    standings_msg = manager.standings_message
    if standings_msg is None:
        return None, None
    return standings_msg.jump_url, "Go to Standings"


async def _attach_round_link(manager: "PodDraftManager", round_num: int) -> None:
    """Edit round_num's thread message to append its nav link (next round / standings). No-op when
    there's no tracked message, no link target yet, or the view has no ActionRow room (5-match pods)."""
    if round_num < 1:
        return
    msg = manager.round_messages.get(round_num)
    if msg is None:
        return
    url, label = _round_nav_link(manager, round_num)
    if url is None:
        return
    states = await asyncio.to_thread(
        render_round_states, manager.event_id, round_num, bracket=manager.pairing_mode == "bracket",
    )
    try:
        await msg.edit(view=RoundResultsView(states, round_num=round_num, link_url=url, link_label=label))
    except discord.HTTPException:
        log.warning(f"could not attach nav link to round {round_num}", exc_info=True)


async def refresh_round_pairing_messages(manager) -> None:
    """Re-render posted round messages that still show unreported pairings, so a fresh Arena link
    replaces the player's placeholder name mid-round. Fully reported rounds render results only and
    are left untouched."""
    for round_num, msg in sorted(manager.round_messages.items()):
        states = await asyncio.to_thread(
            render_round_states, manager.event_id, round_num, bracket=manager.pairing_mode == "bracket",
        )
        real = [s for s in states if not s.get("placeholder")]
        if not real or all(s.get("winner_name") for s in real):
            continue
        url, label = _round_nav_link(manager, round_num)
        try:
            await msg.edit(
                embed=round_embed(round_num, states),
                view=RoundResultsView(states, round_num=round_num, link_url=url, link_label=label),
            )
        except discord.HTTPException:
            log.warning(f"could not refresh round {round_num} pairings after arena link", exc_info=True)


ResultSubmit = Callable[[discord.Interaction, str], Awaitable[None]]
"""Commits a `match_id|winner|score` pick. Every reporting surface encodes the same value, but a pod's
pairing mode decides which fan-out has to run, so the surface takes the handler as an argument instead
of hard-wiring one. Defaults to the Swiss round fan-out; team pods pass `handle_team_report`."""


class MatchResultSelect(ui.Select):
    """Per-match dropdown; placeholder + labels use Discord display names. Option values still encode
    the draftmancer_name (DB primary key) so result commits resolve correctly."""

    def __init__(self, slot: int, match_id: str = "", a_name: str = "", b_name: str = "",
                 a_display: str = "", b_display: str = "",
                 selected_value: str | None = None, winner_name: str | None = None,
                 is_trophy_match: bool = False, placeholder_text: str = "", allow_skip: bool = True,
                 row: int | None = None, on_submit: ResultSubmit | None = None):
        self.on_submit = on_submit or _handle_result_submission
        disabled = False
        if placeholder_text:
            disabled = True
            placeholder = placeholder_text[:150]
            options = [discord.SelectOption(label="—", value="placeholder")]
        elif match_id and a_name and b_name:
            a_disp = a_display or a_name
            b_disp = b_display or b_name
            base = f"🏆 {a_disp} vs {b_disp} 🏆" if is_trophy_match else f"{a_disp} vs {b_disp}"
            placeholder = base if selected_value else f"⚔️ {base}"
            values = [
                (f"{a_disp} wins: 2-0", f"{a_disp} wins 2-0 vs {b_disp}", f"{match_id}|{a_name}|2-0", True),
                (f"{a_disp} wins: 2-1", f"{a_disp} wins 2-1 vs {b_disp}", f"{match_id}|{a_name}|2-1", True),
                (f"{b_disp} wins: 2-1", f"{b_disp} wins 2-1 vs {a_disp}", f"{match_id}|{b_name}|2-1", True),
                (f"{b_disp} wins: 2-0", f"{b_disp} wins 2-0 vs {a_disp}", f"{match_id}|{b_name}|2-0", True),
            ]
            if allow_skip:
                skip_long = f"{a_disp} vs {b_disp} 🚫 Not Played"
                values.append(("No Match Played", skip_long, f"{match_id}|{SKIPPED_SENTINEL}|0-0", False))
            if selected_value:
                values.insert(0, ("Clear Result", None, f"{match_id}|{CLEAR_SENTINEL}|0-0", False))
            options = []
            for short, long, val, trophy_eligible in values:
                is_selected = val == selected_value
                label = long if (is_selected and long) else short
                if is_trophy_match and trophy_eligible:
                    label = f"🏆 {label}"
                options.append(discord.SelectOption(label=label[:100], value=val, default=is_selected))
        else:
            placeholder = "Result"
            options = [discord.SelectOption(label="—", value="placeholder")]
        super().__init__(
            custom_id=f"{SELECT_CUSTOM_PREFIX}:{slot}",
            placeholder=placeholder,
            options=options,
            min_values=1,
            max_values=1,
            row=slot if row is None else row,
            disabled=disabled,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.on_submit(interaction, self.values[0])


class RoundResultsView(ui.View):
    """One View per round; holds up to MAX_MATCHES_PER_ROUND Selects, one per match. Locked matches
    render no dropdown — their result already shows in the round embed.

    When `link_url` is provided AND there's an ActionRow free, a link button labelled `link_label`
    is appended so players can jump to the next round's message or the standings.

    `round_num` orders the dropdowns through the same `round_groups` the embed groups by, so a
    dropdown's position always matches its line in the embed body. Omitted for single-match DM views
    and the persistent template, where order is moot.

    `on_submit` overrides where a pick is committed; see `ResultSubmit`.
    """

    def __init__(self, match_states: list[dict] | None = None, *, round_num: int | None = None,
                 link_url: str | None = None, link_label: str | None = None,
                 on_submit: ResultSubmit | None = None):
        super().__init__(timeout=None)
        if match_states:
            if round_num is not None:
                match_states = [m for _, group in round_groups(round_num, match_states) for m in group]
            next_row = 0
            for slot, m in enumerate(match_states):
                if m.get("locked") or m.get("score") == BYE_SCORE:
                    continue
                if m.get("placeholder"):
                    trophy = "🏆 " if m.get("is_trophy_match") else ""
                    text = m.get("dropdown_label") or m.get("label") or ""
                    self.add_item(MatchResultSelect(
                        slot=slot,
                        placeholder_text=f"⏳ {trophy}{text}",
                        row=next_row,
                        on_submit=on_submit,
                    ))
                    next_row += 1
                    continue
                selected = None
                if m.get("winner_name") and m.get("score"):
                    selected = f"{m['match_id']}|{m['winner_name']}|{m['score']}"
                self.add_item(MatchResultSelect(
                    slot=slot,
                    match_id=m["match_id"],
                    a_name=m["a_name"],
                    b_name=m["b_name"],
                    a_display=m.get("a_display") or m["a_name"],
                    b_display=m.get("b_display") or m["b_name"],
                    selected_value=selected,
                    is_trophy_match=bool(m.get("is_trophy_match")),
                    allow_skip=m.get("allow_skip", True),
                    row=next_row,
                    on_submit=on_submit,
                ))
                next_row += 1
            if next_row < MAX_MATCHES_PER_ROUND:
                if round_num is not None:
                    self.add_item(ManageRoundButton(round_num, row=next_row))
                if link_url and link_label:
                    self.add_item(discord.ui.Button(
                        style=discord.ButtonStyle.link,
                        url=link_url,
                        label=link_label,
                        emoji=emojis.get_emoji("manat"),
                        row=next_row,
                    ))
        else:
            # Persistent template covering all possible slots; real messages will only render the slots they need
            for slot in range(MAX_MATCHES_PER_ROUND):
                self.add_item(MatchResultSelect(slot=slot))


class ManageRoundButton(ui.DynamicItem[ui.Button], template=rf"{MANAGE_ROUND_CUSTOM_PREFIX}:(?P<round>\d+)"):
    """Organizer-only button on each round message that opens an ephemeral pairing editor. The event
    is resolved from the thread at click time, so only the round number rides in the custom_id and the
    button dispatches after a restart without any per-message state."""

    def __init__(self, round_num: int, *, row: int | None = None):
        self.round_num = round_num
        super().__init__(ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji="🔧",
            custom_id=f"{MANAGE_ROUND_CUSTOM_PREFIX}:{round_num}",
            row=row,
        ))

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["round"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await is_pod_organizer(interaction.client, interaction.user):
            await interaction.response.send_message(MSG_FIX_NOT_ORGANIZER, ephemeral=True)
            return
        thread_id = str(interaction.channel_id) if interaction.channel_id else None
        event_id = await asyncio.to_thread(load_event_id_by_thread_sync, thread_id) if thread_id else None
        if event_id is None:
            await interaction.response.send_message(MSG_FIX_NOT_POD_THREAD, ephemeral=True)
            return
        view = await build_round_editor(event_id, self.round_num, interaction.message)
        if view is None:
            await interaction.response.send_message(MSG_FIX_NO_MATCHES, ephemeral=True)
            return
        await interaction.response.send_message(
            MSG_FIX_PROMPT.format(round_num=self.round_num), view=view, ephemeral=True,
        )


class FixPairingView(ui.View):
    """Ephemeral organizer editor: choose a round match, reassign its two players, set or correct its
    result, save. Changes are written straight to the match row and the round message is re-rendered.
    The result editor is the only way to fix a match once its round has locked and the public report
    dropdowns are gone — e.g. a match reported early that the players then actually played."""

    def __init__(self, event_id: str, round_num: int, round_message: discord.Message | None,
                 matches: list[dict], roster: list[tuple[str, str]]):
        super().__init__(timeout=300)
        self.event_id = event_id
        self.round_num = round_num
        self.round_message = round_message
        self.matches = matches
        self.roster = roster
        self.selected_match: dict | None = None
        self.selected_a: str | None = None
        self.selected_b: str | None = None
        self.selected_result: str | None = None
        self._build_items()

    def _build_items(self) -> None:
        self.clear_items()
        chosen_id = self.selected_match["match_id"] if self.selected_match else None
        match_select = ui.Select(placeholder="Match to fix…", row=0, options=[
            discord.SelectOption(
                label=f"{m['a_display']} vs {m['b_display']}"[:100],
                value=m["match_id"],
                default=m["match_id"] == chosen_id,
            )
            for m in self.matches
        ])
        match_select.callback = self._on_match
        self.add_item(match_select)
        if self.selected_match is None:
            drop = ui.Button(label="Drop Player", emoji=DROP_EMOJI, style=discord.ButtonStyle.danger, row=1)
            drop.callback = self._on_drop
            self.add_item(drop)
        if self.selected_match is not None:
            self.add_item(self._player_select("a", self.selected_a, row=1))
            self.add_item(self._player_select("b", self.selected_b, row=2))
            self.add_item(self._result_select(row=3))
            save = ui.Button(label="Save", style=discord.ButtonStyle.success, row=4)
            save.callback = self._on_save
            self.add_item(save)
            cancel = ui.Button(label="Cancel", style=discord.ButtonStyle.secondary, row=4)
            cancel.callback = self._on_cancel
            self.add_item(cancel)

    def _player_select(self, slot: str, selected: str | None, row: int) -> ui.Select:
        options = []
        names = set()
        for name, display in self.roster:
            options.append(discord.SelectOption(label=display[:100], value=name[:100], default=name == selected))
            names.add(name)
        if selected and selected not in names:
            options.insert(0, discord.SelectOption(label=selected[:100], value=selected[:100], default=True))
        select = ui.Select(placeholder=f"Player {slot.upper()}…", row=row, options=options[:25])
        select.callback = self._on_player_a if slot == "a" else self._on_player_b
        return select

    def _result_select(self, row: int) -> ui.Select:
        a_disp = _roster_display(self.roster, self.selected_a)
        b_disp = _roster_display(self.roster, self.selected_b)
        chosen = self.selected_result or self._current_result_token()
        values = [
            ("Leave result as-is", RESULT_KEEP),
            (f"{a_disp} wins 2-0", "a|2-0"),
            (f"{a_disp} wins 2-1", "a|2-1"),
            (f"{b_disp} wins 2-1", "b|2-1"),
            (f"{b_disp} wins 2-0", "b|2-0"),
            ("No Match Played", "skip"),
        ]
        if self.selected_match and self.selected_match.get("winner_name"):
            values.append(("Clear result", "clear"))
        options = [
            discord.SelectOption(label=label[:100], value=value, default=value == chosen)
            for label, value in values
        ]
        select = ui.Select(placeholder="Result…", row=row, options=options)
        select.callback = self._on_result
        return select

    def _current_result_token(self) -> str:
        """The result token matching the match's recorded outcome, keyed to the current player slots so
        the dropdown shows the standing result until the organizer picks a different one."""
        match = self.selected_match
        if match is None or not match.get("winner_name"):
            return RESULT_KEEP
        winner = match["winner_name"]
        if winner == SKIPPED_SENTINEL:
            return "skip"
        score = match.get("score") or ""
        if winner == self.selected_a:
            return f"a|{score}"
        if winner == self.selected_b:
            return f"b|{score}"
        return RESULT_KEEP

    async def _on_match(self, interaction: discord.Interaction) -> None:
        match_id = interaction.data["values"][0]
        self.selected_match = next((m for m in self.matches if m["match_id"] == match_id), None)
        if self.selected_match is not None:
            self.selected_a = self.selected_match["a_name"]
            self.selected_b = self.selected_match["b_name"]
        self._build_items()
        await interaction.response.edit_message(view=self)

    async def _on_player_a(self, interaction: discord.Interaction) -> None:
        self.selected_a = interaction.data["values"][0]
        self._build_items()
        await interaction.response.edit_message(view=self)

    async def _on_player_b(self, interaction: discord.Interaction) -> None:
        self.selected_b = interaction.data["values"][0]
        self._build_items()
        await interaction.response.edit_message(view=self)

    async def _on_result(self, interaction: discord.Interaction) -> None:
        self.selected_result = interaction.data["values"][0]
        self._build_items()
        await interaction.response.edit_message(view=self)

    async def _on_cancel(self, interaction: discord.Interaction) -> None:
        self.stop()
        await interaction.response.edit_message(content="No changes made", view=None)

    async def _on_drop(self, interaction: discord.Interaction) -> None:
        dropped = await asyncio.to_thread(load_dropped_names, self.event_id)
        remaining = [
            (name, display) for name, display in self.roster
            if normalize_player_name(name) not in dropped and name != BYE_NAME
        ]
        if not remaining:
            await interaction.response.send_message(MSG_DROP_NOBODY_LEFT, ephemeral=True)
            return
        await interaction.response.send_message(
            MSG_DROP_PROMPT,
            view=DropPlayerView(self.event_id, self.round_num, remaining, self.round_message),
            ephemeral=True,
        )

    async def _on_save(self, interaction: discord.Interaction) -> None:
        if self.selected_match is None:
            self.stop()
            await interaction.response.edit_message(content=MSG_FIX_MATCH_GONE, view=None)
            return
        if self.selected_a == self.selected_b:
            await interaction.response.send_message(MSG_FIX_SAME_PLAYER, ephemeral=True)
            return
        match_id = self.selected_match["match_id"]
        if await asyncio.to_thread(bracket_edit_blocked, match_id):
            await interaction.response.send_message(BRACKET_EDIT_BLOCKED_MSG, ephemeral=True)
            return
        result = await asyncio.to_thread(apply_pairing_swap, match_id, self.selected_a, self.selected_b)
        if result is None:
            self.stop()
            await interaction.response.edit_message(content=MSG_FIX_MATCH_GONE, view=None)
            return
        choice = self._resolve_result_choice()
        result_meta = None
        if choice is not None:
            winner_name, score = choice
            result_meta = await asyncio.to_thread(commit_result, match_id, winner_name, score)
            if result_meta == "not_found":
                result_meta = None
        self.stop()
        await interaction.response.defer()
        try:
            await interaction.delete_original_response()
        except discord.HTTPException:
            log.warning("could not dismiss pairing editor", exc_info=True)
        log.info(
            f"[{self.event_id}] R{self.round_num} match edited {match_id} -> "
            f"{self.selected_a} vs {self.selected_b} result={self.selected_result or RESULT_KEEP} "
            f"by {actor_label(interaction)}"
        )
        await _refresh_round_message_after_edit(
            interaction.client, self.round_message, self.event_id, self.round_num, match_id,
        )
        a_disp = _roster_display(self.roster, self.selected_a)
        b_disp = _roster_display(self.roster, self.selected_b)
        url = self.round_message.jump_url if self.round_message is not None else None
        label = round_link_label(self.round_num, url)

        if await self._regenerate_bracket_after_result(choice, result_meta, a_disp, b_disp, url):
            return
        if result_meta is not None:
            await announce_round_result(interaction.client, self.event_id, format_round_change(
                self.round_num, self._result_phrase(choice, a_disp, b_disp), url, ORGANIZER_CORRECTED_LEAD,
            ))
            return
        a_ref = await _resolve_discord_mention(self.event_id, self.selected_a) or a_disp
        b_ref = await _resolve_discord_mention(self.event_id, self.selected_b) or b_disp
        note = " — report the result again" if result["cleared"] else ""
        phrase = f"{label} Match updated by Organizer: {a_ref} vs {b_ref}{note}"
        await announce_round_result(interaction.client, self.event_id, phrase, mention_users=True)

    def _resolve_result_choice(self) -> tuple[str, str] | None:
        token = self.selected_result or RESULT_KEEP
        if token == RESULT_KEEP:
            return None
        if token == "clear":
            return CLEAR_SENTINEL, "0-0"
        if token == "skip":
            return SKIPPED_SENTINEL, "0-0"
        slot, score = token.split("|", 1)
        winner = self.selected_a if slot == "a" else self.selected_b
        return winner, score

    def _result_phrase(self, choice: tuple[str, str], a_disp: str, b_disp: str) -> str:
        winner_name, score = choice
        if winner_name == SKIPPED_SENTINEL:
            return f"{a_disp} vs {b_disp} marked not played"
        if winner_name == CLEAR_SENTINEL:
            return format_result_change(self.selected_a, self.selected_b, None, None, a_disp, b_disp)
        return format_result_change(self.selected_a, self.selected_b, winner_name, score, a_disp, b_disp)

    async def _regenerate_bracket_after_result(self, choice: tuple[str, str] | None,
                                               result_meta: dict | None,
                                               a_disp: str, b_disp: str,
                                               pairings_url: str | None) -> bool:
        """Rebuild downstream bracket rounds when a corrected result changed the winner. Posts the
        correction and the new pairings as one thread note, so the caller skips the plain announcement.
        Returns whether it ran."""
        if result_meta is None or not result_meta.get("winner_changed"):
            return False
        manager = ACTIVE_POD_MANAGERS.get(self.event_id)
        if manager is None or manager.pairing_mode != "bracket" or self.round_num >= TOTAL_ROUNDS:
            return False
        winner_name, score = choice
        settled = winner_name not in (CLEAR_SENTINEL, SKIPPED_SENTINEL)
        phrase = format_result_change(
            self.selected_a, self.selected_b,
            winner_name if settled else None, score if settled else None,
            a_disp, b_disp,
        )
        head = format_round_change(self.round_num, phrase, pairings_url, ORGANIZER_CORRECTED_LEAD)
        await bracket_regenerate_downstream(manager, self.round_num, head)
        return True


class DropPlayerView(ui.View):
    """Ephemeral organizer confirm: pick who left, then commit. A drop can't be undone, so the button
    only arms once a name is chosen."""

    def __init__(self, event_id: str, round_num: int, roster: list[tuple[str, str]],
                 round_message: discord.Message | None):
        super().__init__(timeout=300)
        self.event_id = event_id
        self.round_num = round_num
        self.roster = roster
        self.round_message = round_message
        self.selected: str | None = None
        self._build_items()

    def _build_items(self) -> None:
        self.clear_items()
        select = ui.Select(placeholder="Player who dropped…", row=0, options=[
            discord.SelectOption(label=display[:100], value=name[:100], default=name == self.selected)
            for name, display in self.roster[:25]
        ])
        select.callback = self._on_select
        self.add_item(select)
        confirm = ui.Button(label="Confirm Drop", emoji=DROP_EMOJI, style=discord.ButtonStyle.danger,
                            row=1, disabled=self.selected is None)
        confirm.callback = self._on_confirm
        self.add_item(confirm)

    async def _on_select(self, interaction: discord.Interaction) -> None:
        self.selected = interaction.data["values"][0]
        self._build_items()
        await interaction.response.edit_message(view=self)

    async def _on_confirm(self, interaction: discord.Interaction) -> None:
        if self.selected is None:
            return
        await interaction.response.defer()
        forfeited = await asyncio.to_thread(apply_drop, self.event_id, self.selected, self.round_num)
        self.stop()
        display = _roster_display(self.roster, self.selected)
        try:
            await interaction.delete_original_response()
        except discord.HTTPException:
            log.warning("could not dismiss drop editor", exc_info=True)
        log.info(
            f"[{self.event_id}] R{self.round_num} dropped {self.selected} "
            f"forfeited={len(forfeited)} by {actor_label(interaction)}"
        )
        await announce_round_result(
            interaction.client, self.event_id, format_drop_announcement(self.round_num, display),
        )
        await _refresh_round_message_after_edit(
            interaction.client, self.round_message, self.event_id, self.round_num,
            forfeited[0] if forfeited else "",
        )
        await settle_auto_forfeits(interaction.client, self.event_id, forfeited)


def format_drop_announcement(round_num: int, display: str) -> str:
    return f"{DROP_EMOJI} **{round_link_target(round_num)} Drop:** {display}"


def apply_drop(event_id: str, draftmancer_name: str, round_num: int) -> list[str]:
    """Mark a player out of the pod and forfeit every match of theirs still open, in this round and any
    later one already paired. Returns the forfeited match ids. Their played results stand; from here
    each pairing they land in is reported for them, so the pod finishes without them."""
    with SessionLocal() as session:
        key = normalize_player_name(draftmancer_name)
        participants = session.execute(
            select(PodDraftParticipant).where(PodDraftParticipant.event_id == event_id)
        ).scalars().all()
        for participant in participants:
            if normalize_player_name(participant.draftmancer_name or "") == key:
                participant.dropped_round = round_num
        dropped = dropped_names_sync(session, event_id) | {key}
        open_matches = session.execute(
            select(PodDraftMatch).where(
                PodDraftMatch.event_id == event_id,
                PodDraftMatch.winner_name.is_(None),
            )
        ).scalars().all()
        forfeited = []
        for match in open_matches:
            if forfeit_unplayable_match(session, match, dropped) is not None:
                forfeited.append(match.id)
        session.commit()
    return forfeited


async def build_round_editor(
    event_id: str, round_num: int, round_message: discord.Message | None,
) -> "FixPairingView | None":
    """The pairing editor for one round, or None when the round has no matches yet. `round_message` is
    what the editor re-renders after a save; it is None when the editor was opened away from that
    message and the pod's manager is gone, which only costs the in-place refresh."""
    matches = await asyncio.to_thread(_load_round_states, event_id, round_num)
    if not matches:
        return None
    roster = await asyncio.to_thread(_load_round_roster, event_id)
    return FixPairingView(event_id, round_num, round_message, matches, roster)


async def open_manage_rounds(interaction: discord.Interaction, event_id: str) -> None:
    """The Settings panel's route into the pairing editor, picking the round first.

    A ten-player round fills every dropdown row, so its message has no space for the 🔧 button and this
    is the only way in. Organizer-gated on its own, since opening Settings is not organizer-only.
    """
    if not await is_pod_organizer(interaction.client, interaction.user):
        await interaction.response.send_message(MSG_FIX_NOT_ORGANIZER, ephemeral=True)
        return
    rounds = await asyncio.to_thread(round_picker_options, event_id)
    if not rounds:
        await interaction.response.send_message(MSG_FIX_NO_MATCHES, ephemeral=True)
        return
    await interaction.response.send_message(
        MSG_PICK_ROUND, view=ManageRoundsPickerView(event_id, rounds), ephemeral=True,
    )


def round_picker_options(event_id: str) -> list[tuple[int, str]]:
    """(round, how far along it is) for every round that has matches, ordered. Empty until a pod has
    pairings, which is what keeps Manage Rounds off a lobby that has not drafted yet."""
    with SessionLocal() as session:
        rows = session.execute(
            select(
                PodDraftMatch.round,
                func.count(PodDraftMatch.id),
                func.count(PodDraftMatch.winner_name),
            )
            .where(PodDraftMatch.event_id == event_id)
            .group_by(PodDraftMatch.round)
            .order_by(PodDraftMatch.round)
        ).all()
    options = []
    for round_num, total, reported in rows:
        state = "All Reported" if reported == total else f"{reported} of {total} Reported"
        options.append((round_num, state))
    return options


class ManageRoundsPickerView(ui.View):
    """Ephemeral round picker behind the Settings panel's Manage Rounds button. Picking a round swaps
    this message for the same editor the round message's 🔧 opens."""

    def __init__(self, event_id: str, rounds: list[tuple[int, str]]) -> None:
        super().__init__(timeout=300)
        self.add_item(_RoundPickerSelect(event_id, rounds))


class _RoundPickerSelect(ui.Select):
    def __init__(self, event_id: str, rounds: list[tuple[int, str]]) -> None:
        self.event_id = event_id
        super().__init__(
            placeholder=PICK_ROUND_PLACEHOLDER,
            options=[
                discord.SelectOption(label=f"Round {num}", value=str(num), description=state)
                for num, state in rounds
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        round_num = int(self.values[0])
        manager = ACTIVE_POD_MANAGERS.get(self.event_id)
        round_message = manager.round_messages.get(round_num) if manager is not None else None
        view = await build_round_editor(self.event_id, round_num, round_message)
        if view is None:
            await interaction.response.edit_message(content=MSG_FIX_NO_MATCHES, view=None)
            return
        await interaction.response.edit_message(
            content=MSG_FIX_PROMPT.format(round_num=round_num), view=view,
        )


def apply_pairing_swap(match_id: str, new_a: str, new_b: str) -> dict | None:
    """Reassign a match's two players. Clears a reported result whose winner is no longer in the
    match so standings can't reference a phantom win. Returns None when the row is gone."""
    with SessionLocal() as session:
        match = session.get(PodDraftMatch, match_id)
        if match is None:
            return None
        match.player_a_name = new_a
        match.player_b_name = new_b
        cleared = False
        if match.winner_name is not None and match.winner_name not in (new_a, new_b, SKIPPED_SENTINEL):
            match.winner_name = None
            match.score = None
            match.reported_at = None
            cleared = True
        result = {"round": match.round, "event_id": match.event_id, "cleared": cleared}
        session.commit()
    return result


def _load_round_roster(event_id: str) -> list[tuple[str, str]]:
    """(draftmancer_name, Discord display) for every participant, feeding the pairing-editor selects.
    Prefers the linked player's Discord display over the participant row's stored handle, which can
    carry a stale Arena-style name that reads as a different person to the organizer."""
    with SessionLocal() as session:
        rows = session.execute(
            select(
                PodDraftParticipant.draftmancer_name,
                PodDraftParticipant.display_name,
                DbPlayer.display_name,
            )
            .outerjoin(DbPlayer, DbPlayer.id == PodDraftParticipant.player_id)
            .where(
                PodDraftParticipant.event_id == event_id,
                PodDraftParticipant.draftmancer_name.is_not(None),
            )
            .order_by(PodDraftParticipant.seat_index.nulls_last(), PodDraftParticipant.draftmancer_name)
        ).all()
    roster = []
    for draftmancer_name, participant_display, player_display in rows:
        raw = player_display or participant_display or draftmancer_name
        roster.append((draftmancer_name, strip_arena_suffix(raw)))
    return roster


def _roster_display(roster: list[tuple[str, str]], name: str | None) -> str:
    for candidate, display in roster:
        if candidate == name:
            return display
    return name or "?"


async def _refresh_round_message_after_edit(
    bot_client, round_message: discord.Message | None, event_id: str, round_num: int, match_id: str,
) -> None:
    """Re-render the edited round message from DB state and fan the change out to any DM surfaces."""
    bracket = (await asyncio.to_thread(load_event_pairing_mode_sync, event_id)) == "bracket"
    states = await asyncio.to_thread(render_round_states, event_id, round_num, bracket=bracket)
    manager = ACTIVE_POD_MANAGERS.get(event_id)
    url, label = _round_nav_link(manager, round_num)
    if round_message is not None:
        try:
            await round_message.edit(
                content=None,
                embed=round_embed(round_num, states),
                view=RoundResultsView(states, round_num=round_num, link_url=url, link_label=label),
            )
        except discord.HTTPException:
            log.warning(f"could not refresh round {round_num} message after pairing edit", exc_info=True)
    exclude = str(round_message.channel.id) if round_message is not None and round_message.channel else None
    asyncio.create_task(_propagate_match_to_other_surfaces(
        bot_client, event_id, match_id, round_num, exclude_channel_id=exclude,
    ))


async def _handle_result_submission(interaction: discord.Interaction, value: str) -> None:
    if value == "placeholder":
        await interaction.response.send_message("This dropdown isn't bound to a match yet", ephemeral=True)
        return
    try:
        match_id, winner_name, score = value.split("|", 2)
    except ValueError:
        await interaction.response.send_message("Malformed result option", ephemeral=True)
        return

    try:
        await interaction.response.defer()
    except discord.HTTPException:
        log.warning("could not defer result-submission interaction", exc_info=True)

    if await asyncio.to_thread(event_result_locked, match_id):
        await interaction.followup.send(
            POD_RESULT_LOCKED_MSG,
            ephemeral=(interaction.guild is not None),
        )
        return

    if await asyncio.to_thread(bracket_edit_blocked, match_id):
        await interaction.followup.send(
            BRACKET_EDIT_BLOCKED_MSG,
            ephemeral=(interaction.guild is not None),
        )
        return

    result = await asyncio.to_thread(commit_result, match_id, winner_name, score)
    if result == "not_found":
        return

    round_num = result["round"]
    event_id = result["event_id"]
    manager = ACTIVE_POD_MANAGERS.get(event_id)
    bracket = manager is not None and manager.pairing_mode == "bracket"
    match_states = await asyncio.to_thread(render_round_states, event_id, round_num, bracket=bracket)
    match_state = next((m for m in match_states if m.get("match_id") == match_id), None)
    event_name = await asyncio.to_thread(load_event_name_sync, event_id)
    ephemeral_surface = _is_ephemeral_surface(interaction)
    is_dm = isinstance(interaction.channel, discord.DMChannel)
    channel_id = str(interaction.channel.id) if interaction.channel else None
    exclude_channel_id = None if ephemeral_surface else channel_id

    if result.get("cleared"):
        if manager is not None and manager.grace_round == round_num and manager.grace_task is not None:
            manager.grace_task.cancel()
            manager.grace_round = None
            manager.grace_task = None
        log.info(
            f"[{event_name}] R{round_num} cleared {match_id} by {actor_label(interaction)} "
            f"({surface_label(interaction)})"
        )
        if not ephemeral_surface:
            try:
                if is_dm and match_state is not None:
                    dm_info = await asyncio.to_thread(load_dm_info_sync, event_id)
                    pairings_url = _resolve_pairings_url(event_id, round_num)
                    dm_embed, dm_view = _build_dm_match_view(
                        dm_info, str(interaction.user.id), match_state, round_num, pairings_url, event_name,
                    )
                    if dm_embed is not None:
                        await interaction.edit_original_response(embed=dm_embed, view=dm_view)
                else:
                    url, label = _round_nav_link(manager, round_num)
                    await interaction.edit_original_response(
                        content=None,
                        embed=round_embed(round_num, match_states),
                        view=RoundResultsView(match_states, round_num=round_num, link_url=url, link_label=label),
                    )
            except Exception:
                log.warning("could not edit interaction message after clear", exc_info=True)
        asyncio.create_task(_propagate_match_to_other_surfaces(
            interaction.client, event_id, match_id, round_num, exclude_channel_id=exclude_channel_id,
        ))
        head = None
        if result.get("was_reported") and match_state is not None:
            head = format_round_clear_announcement(
                round_num, match_state, _resolve_pairings_url(event_id, round_num),
            )
        regenerating = bracket and round_num < TOTAL_ROUNDS and manager is not None \
            and bool(result.get("winner_changed"))
        if head and not regenerating:
            await announce_round_result(interaction.client, event_id, head)
        if regenerating:
            await bracket_regenerate_downstream(manager, round_num, head)
        return

    log.info(format_match_result_log(
        event_label=event_name, round_num=round_num, actor=actor_label(interaction),
        match_id=match_id, winner=winner_name, score=score, surface=surface_label(interaction),
    ))
    if not ephemeral_surface:
        try:
            if is_dm and match_state is not None:
                dm_info = await asyncio.to_thread(load_dm_info_sync, event_id)
                pairings_url = _resolve_pairings_url(event_id, round_num)
                dm_embed, dm_view = _build_dm_match_view(
                    dm_info, str(interaction.user.id), match_state, round_num, pairings_url, event_name,
                )
                if dm_embed is not None:
                    await interaction.edit_original_response(embed=dm_embed, view=dm_view)
            else:
                url, label = _round_nav_link(manager, round_num)
                await interaction.edit_original_response(
                    content=None,
                    embed=round_embed(round_num, match_states),
                    view=RoundResultsView(match_states, round_num=round_num, link_url=url, link_label=label),
                )
        except Exception:
            log.warning("could not edit interaction message", exc_info=True)

    asyncio.create_task(_propagate_match_to_other_surfaces(
        interaction.client, event_id, match_id, round_num, exclude_channel_id=exclude_channel_id,
    ))

    corrected = result_was_corrected(result)
    regenerating = bracket and corrected and round_num < TOTAL_ROUNDS and manager is not None
    head = None
    if match_state is not None and match_was_played(match_state) and result_needs_announcement(result):
        pairings_url = _resolve_pairings_url(event_id, round_num)
        head = format_round_announcement(round_num, match_state, pairings_url, corrected=corrected)
        if not regenerating:
            await announce_round_result(interaction.client, event_id, head)

    await _maybe_advance(
        interaction.client, event_id, round_num,
        is_edit=corrected,
        head=head if regenerating else None,
    )
    if round_num >= TOTAL_ROUNDS:
        asyncio.create_task(deck_recovery_scan(
            interaction.client, event_id, [result["a_name"], result["b_name"]],
        ))


def _is_ephemeral_surface(interaction: discord.Interaction) -> bool:
    """True when the clicked component sits on an ephemeral message, i.e. a `/report-results` card.

    Such a card is disposable: it is left untouched after a pick (the public result line is the
    confirmation, as on the team board) and nothing tracks it, so every persisted surface still needs
    the result fanned out to it.
    """
    message = interaction.message
    return message is not None and message.flags.ephemeral


def _resolve_pairings_url(event_id: str, round_num: int) -> str | None:
    """Best-effort pairings URL — pulls from the in-memory manager when available, else None."""
    manager = ACTIVE_POD_MANAGERS.get(event_id)
    if manager is None:
        return None
    msg = manager.round_messages.get(round_num)
    return msg.jump_url if msg is not None else None


def _build_dm_match_view(
    dm_info: dict,
    viewer_discord_id: str,
    match_state: dict,
    round_num: int,
    pairings_url: str | None,
    event_name: str | None,
) -> tuple[discord.Embed | None, "RoundResultsView | None"]:
    """Render the per-recipient DM body + Select view for one match. Returns (None, None) when the
    viewer isn't a participant we can resolve from dm_info."""
    recipient_key = _viewer_key(dm_info, viewer_discord_id)
    if recipient_key is None:
        return None, None
    viewer_is_a = recipient_key == normalize_player_name(match_state.get("a_name") or "")
    opp_key = normalize_player_name(
        match_state["b_name"] if viewer_is_a else match_state["a_name"]
    )
    opponent = dm_info.get(opp_key)
    opp_label = _opponent_dm_label(opponent, opp_key)
    embed = build_pairing_dm_embed(
        round_num=round_num,
        opponent_label=opp_label,
        opponent_arena=opponent.arena_name if opponent else None,
        pairings_url=pairings_url,
        event_name=event_name,
        match_state=match_state,
        viewer_is_a=viewer_is_a,
    )
    return embed, RoundResultsView([match_state])


class OwnMatchReport(NamedTuple):
    """A card to act on (embed + view) or a `notice` explaining why there is none. The view is the match
    dropdowns while matches are open, and the deck-color dropdown once the only thing left to hand in is
    colors."""
    embed: discord.Embed | None
    view: discord.ui.View | None
    notice: str | None


class OpenMatch(NamedTuple):
    round_num: int
    state: dict


async def build_own_match_report(discord_id: str, *, team_submit: ResultSubmit) -> OwnMatchReport:
    """The `/report-results` card: every match the caller still owes, each carrying the same dropdown
    its round message does, rebuilt on demand so a lost or missed DM never blocks reporting. A team pod
    puts all three of its rounds on one card, since all three are playable from the moment the draft ends.

    `team_submit` is the commit path for team pods, passed in because it lives downstream of this module.

    Only unreported matches are served. A recorded result stays with the round message or the board while
    its grace window is open, and with an Organizer after that, so a stale correction can't void a later
    round the pod already played.
    """
    own = await asyncio.to_thread(_own_open_matches_sync, discord_id)
    if not own:
        return await _nothing_open_card(discord_id)
    event_id = own[0].event_id
    if await asyncio.to_thread(event_result_locked, own[0].match_id):
        return OwnMatchReport(None, None, POD_RESULT_LOCKED_MSG)

    mode = await asyncio.to_thread(load_event_pairing_mode_sync, event_id)
    open_matches = await _open_match_states(event_id, own, bracket=mode == "bracket")
    dm_info = await asyncio.to_thread(load_dm_info_sync, event_id)
    viewer_key = _viewer_key(dm_info, discord_id)
    if not open_matches or viewer_key is None:
        return OwnMatchReport(None, None, MSG_POD_NO_MATCH_TO_REPORT)

    event_name = await asyncio.to_thread(load_event_name_sync, event_id)
    embed = build_report_card_embed(event_name, dm_info, viewer_key, open_matches)
    view = RoundResultsView(
        [m.state for m in open_matches], on_submit=team_submit if mode == "team" else None,
    )
    return OwnMatchReport(embed, view, None)


async def _open_match_states(event_id: str, own: list[OwnMatch], *, bracket: bool) -> list[OpenMatch]:
    """Live render state for each of the caller's open matches, reading each round only once."""
    by_round: dict[int, list[dict]] = {}
    open_matches: list[OpenMatch] = []
    for entry in own:
        if entry.round_num not in by_round:
            by_round[entry.round_num] = await asyncio.to_thread(
                render_round_states, event_id, entry.round_num, bracket=bracket,
            )
        state = next((m for m in by_round[entry.round_num] if m.get("match_id") == entry.match_id), None)
        if state is not None:
            open_matches.append(OpenMatch(entry.round_num, state))
    return open_matches


def build_report_card_embed(
    event_name: str | None, dm_info: dict, viewer_key: str, open_matches: list[OpenMatch],
) -> discord.Embed:
    """One line per match the caller still owes, naming the opponent and their Arena handle."""
    short = short_event_name(event_name)
    mtga = emojis.get("mtga")
    lines = [f"**{short}**"] if short else []
    for round_num, state in open_matches:
        viewer_is_a = viewer_key == normalize_player_name(state.get("a_name") or "")
        opponent_key = normalize_player_name(state["b_name"] if viewer_is_a else state["a_name"])
        opponent = dm_info.get(opponent_key)
        arena = opponent.arena_name if opponent else None
        arena_part = f" {mtga} `{arena}`" if arena else ""
        lines.append(f"Round {round_num}: {_opponent_dm_label(opponent, opponent_key)}{arena_part}")
    return discord.Embed(
        title="Report Your Match" if len(open_matches) == 1 else "Report Your Matches",
        description="\n".join(lines),
        color=discord.Color.green(),
    )


async def _nothing_open_card(discord_id: str) -> OwnMatchReport:
    """With no match open, deck colors are the one thing still worth collecting, so serve that dropdown
    when the caller hasn't picked any. Otherwise report which round already stands."""
    deck = await asyncio.to_thread(_owed_deck_colors_sync, discord_id)
    if deck is not None:
        event_id, thread_id = deck
        return OwnMatchReport(
            _build_submit_deck_dm_embed(None),
            DeckColorSelectView(bound_deck_color_submit(event_id, thread_id)),
            None,
        )
    reported = await asyncio.to_thread(_latest_reported_sync, discord_id)
    if reported is None:
        return OwnMatchReport(None, None, MSG_POD_NO_MATCH_TO_REPORT)
    return OwnMatchReport(None, None, MSG_POD_RESULT_ALREADY_RECORDED.format(round_num=reported.round_num))


def _owed_deck_colors_sync(discord_id: str) -> tuple[str, str] | None:
    """(event_id, thread_id) of the caller's newest pod when they are in it and still owe deck colors."""
    with SessionLocal() as session:
        active = active_event_for_discord_user_in_dm(session, discord_id)
        if active is None:
            return None
        event_id, thread_id = active
        is_participant, colors = get_participant_deck_state(session, thread_id, discord_id)
        if not is_participant or colors is not None:
            return None
        return event_id, thread_id


def _viewer_key(dm_info: dict, discord_id: str) -> str | None:
    """The dm_info key for a Discord user, or None when they aren't a resolvable participant."""
    for key, info in dm_info.items():
        if info.discord_id == discord_id:
            return key
    return None


def _own_open_matches_sync(discord_id: str) -> list[OwnMatch]:
    with SessionLocal() as session:
        return own_open_matches(session, discord_id)


def _latest_reported_sync(discord_id: str) -> OwnMatch | None:
    with SessionLocal() as session:
        return latest_reported_match(session, discord_id)


async def _propagate_match_to_other_surfaces(
    bot_client,
    event_id: str,
    match_id: str,
    round_num: int,
    exclude_channel_id: str | None,
) -> None:
    """Edit every other surface tracking this match (thread + the other player's DM) so they all
    reflect the latest result. The interaction's own message is already edited inline."""
    manager = ACTIVE_POD_MANAGERS.get(event_id)
    bracket = manager is not None and manager.pairing_mode == "bracket"
    match_states = await asyncio.to_thread(render_round_states, event_id, round_num, bracket=bracket)
    match_state = next((m for m in match_states if m.get("match_id") == match_id), None)
    if match_state is None:
        return
    event_name = await asyncio.to_thread(load_event_name_sync, event_id)
    dm_info = await asyncio.to_thread(load_dm_info_sync, event_id)
    pairings_url = _resolve_pairings_url(event_id, round_num)

    dm_rows = await asyncio.to_thread(_dm_rows_for_match_sync, match_id)
    for row in dm_rows:
        if exclude_channel_id and row.dm_channel_id == exclude_channel_id:
            continue
        viewer_discord_id = next(
            (v.discord_id for v in dm_info.values() if v.participant_id == row.participant_id),
            None,
        )
        if viewer_discord_id is None:
            continue
        dm_embed, dm_view = _build_dm_match_view(
            dm_info, viewer_discord_id, match_state, round_num, pairings_url, event_name,
        )
        if dm_embed is None:
            continue
        try:
            channel = bot_client.get_channel(int(row.dm_channel_id)) \
                or await bot_client.fetch_channel(int(row.dm_channel_id))
            msg = await channel.fetch_message(int(row.dm_message_id))
            await msg.edit(embed=dm_embed, view=dm_view)
        except discord.HTTPException:
            log.warning(f"propagate: could not edit DM {row.dm_message_id}", exc_info=True)

    if manager is None:
        return
    thread_msg = manager.round_messages.get(round_num)
    if thread_msg is None or str(thread_msg.channel.id) == exclude_channel_id:
        return
    url, label = _round_nav_link(manager, round_num)
    try:
        await thread_msg.edit(
            content=None,
            embed=round_embed(round_num, match_states),
            view=RoundResultsView(match_states, round_num=round_num, link_url=url, link_label=label),
        )
    except discord.HTTPException:
        log.warning(f"propagate: could not edit thread message {thread_msg.id}", exc_info=True)


def _dm_rows_for_match_sync(match_id: str):
    with SessionLocal() as session:
        rows = dm_messages_for_match(session, match_id)
        session.expunge_all()
        return rows


def _load_round_states(event_id: str, round_num: int) -> list[dict]:
    """Re-read all matches for a round + each player's standings-to-date so the embed reflects live state."""
    with SessionLocal() as session:
        rows = session.execute(
            select(PodDraftMatch)
            .where(PodDraftMatch.event_id == event_id, PodDraftMatch.round == round_num)
            .order_by(PodDraftMatch.pairing_index)
        ).scalars().all()
    prior = load_matches(event_id)
    # Build standings as of the start of this round (use only earlier-round results). Use the full
    # pod roster, not just this round's rows — a partial bracket round holds a subset of players, and
    # restricting the standings input would drop their games against everyone else.
    pre_round = [m for m in prior if m.round_num < round_num]
    roster = _load_pod_player_names(event_id) or sorted(
        {n for r in rows for n in (r.player_a_name, r.player_b_name)}
    )
    players = [Player(id=n, name=n) for n in roster]
    standings_by_id = {s.player_id: s for s in pod_swiss.compute_standings(players, pre_round)}
    displays = load_participant_displays(event_id)
    states = []
    for r in rows:
        a_s = standings_by_id.get(r.player_a_name)
        b_s = standings_by_id.get(r.player_b_name)
        a_info = displays.get(normalize_player_name(r.player_a_name), {})
        b_info = displays.get(normalize_player_name(r.player_b_name), {})
        states.append({
            "match_id": r.id,
            "a_name": r.player_a_name,
            "b_name": r.player_b_name,
            "a_display": a_info.get("display_name") or r.player_a_name,
            "b_display": b_info.get("display_name") or r.player_b_name,
            "a_arena": a_info.get("arena"),
            "b_arena": b_info.get("arena"),
            "a_record": f"{a_s.wins}-{a_s.losses}" if a_s else "0-0",
            "b_record": f"{b_s.wins}-{b_s.losses}" if b_s else "0-0",
            "winner_name": r.winner_name,
            "score": r.score,
        })
    mode = load_event_pairing_mode_sync(event_id)
    if round_num == 1 and mode != "random":
        _attach_seats(states, load_seat_indexes(event_id))
    return states


def commit_result(match_id: str, winner_name: str, score: str):
    with SessionLocal() as session:
        match = session.get(PodDraftMatch, match_id)
        if match is None:
            return "not_found"
        was_reported = match.reported_at is not None
        prev_winner = match.winner_name
        prev_score = match.score
        if winner_name == CLEAR_SENTINEL:
            match.winner_name = None
            match.score = None
            match.reported_at = None
            session.commit()
            return {
                "cleared": True,
                "was_reported": was_reported,
                "winner_changed": prev_winner is not None,
                "loser_name": None,
                "a_name": match.player_a_name,
                "b_name": match.player_b_name,
                "round": match.round,
                "event_id": match.event_id,
            }
        # Allow editing — overwrite winner/score on each submission
        set_match_result(session, match_id, winner_name, score)
        session.commit()
        loser = match.player_b_name if winner_name.lower() == match.player_a_name.lower() else match.player_a_name
        return {
            "was_reported": was_reported,
            "winner_changed": (prev_winner or "").lower() != (winner_name or "").lower(),
            "score_changed": (prev_score or "") != (score or ""),
            "loser_name": loser,
            "a_name": match.player_a_name,
            "b_name": match.player_b_name,
            "round": match.round,
            "event_id": match.event_id,
        }


def result_was_corrected(result: dict) -> bool:
    """Whether a re-report changed the recorded outcome. A score-only fix counts: game win percentage
    is a Swiss tiebreaker, so 2-0 against 2-1 moves the standings even with the same winner."""
    changed = result.get("winner_changed") or result.get("score_changed")
    return bool(result.get("was_reported") and changed)


def result_needs_announcement(result: dict) -> bool:
    """Whether the thread should get a result line: a first report, or a correction to a reported one."""
    return not result.get("was_reported") or result_was_corrected(result)


async def announce_round_result(bot_client, event_id: str, phrase: str,
                                 mention_users: bool = False) -> None:
    """Post a single reported result to the pod thread for immediate feedback, e.g. '[Round 2] Marlo
    wins 2-1 vs Bob'. Best-effort — a missing thread or send failure is logged, not raised.

    `mention_users` lets a re-pairing notice actually ping the two players so they know to go play;
    result announcements leave it off."""
    thread_id = await asyncio.to_thread(_load_event_thread_id_sync, event_id)
    if thread_id is None:
        return
    try:
        thread = bot_client.get_channel(int(thread_id)) or await bot_client.fetch_channel(int(thread_id))
    except discord.HTTPException:
        log.info(f"[ROUND-RESULT] could not fetch thread event={event_id}", exc_info=True)
        return
    allowed = discord.AllowedMentions(users=True) if mention_users else discord.AllowedMentions.none()
    try:
        await thread.send(phrase, allowed_mentions=allowed)
    except discord.HTTPException:
        log.warning(f"[ROUND-RESULT] announce failed event={event_id}", exc_info=True)


def _load_event_thread_id_sync(event_id: str) -> str | None:
    with SessionLocal() as session:
        return session.execute(
            select(PodDraftEvent.discord_thread_id).where(PodDraftEvent.id == event_id)
        ).scalar_one_or_none()


async def deck_recovery_scan(bot_client, event_id: str, names: list[str]) -> None:
    """Once a player's last match reports, walk thread history for them and capture the most
    recent record-pattern image they posted but the live listener missed. Skips players
    who already have a record-pattern caption stored."""
    targets = await asyncio.to_thread(_recovery_targets_sync, event_id, names)
    if not targets:
        return
    thread_id, target_discord_ids = targets
    try:
        thread = bot_client.get_channel(int(thread_id)) or await bot_client.fetch_channel(int(thread_id))
    except discord.HTTPException:
        log.info("[R3-RECOVERY] could not fetch thread", exc_info=True)
        return
    if not isinstance(thread, discord.Thread):
        return

    latest_by_user: dict[str, tuple[str, str]] = {}
    try:
        async for msg in thread.history(limit=200):
            if msg.author.bot:
                continue
            author_id = str(msg.author.id)
            if author_id not in target_discord_ids or author_id in latest_by_user:
                continue
            caption = (msg.content or "").strip() or None
            if not caption_has_record_pattern(caption):
                continue
            image_url = first_image_url(msg)
            if image_url is None:
                continue
            latest_by_user[author_id] = (image_url, caption)
            if len(latest_by_user) == len(target_discord_ids):
                break
    except discord.HTTPException:
        log.info("[R3-RECOVERY] thread.history failed", exc_info=True)
        return

    for discord_id, (image_url, caption) in latest_by_user.items():
        await asyncio.to_thread(_capture_recovery_sync, str(thread.id), discord_id, image_url, caption)


def _recovery_targets_sync(event_id: str, names: list[str]) -> tuple[str, set[str]] | None:
    with SessionLocal() as session:
        thread_id = session.execute(
            select(PodDraftEvent.discord_thread_id).where(PodDraftEvent.id == event_id)
        ).scalar_one_or_none()
        if thread_id is None:
            return None
        rows = session.execute(
            select(DbPlayer.discord_id, PodDraftParticipant.deck_screenshot_caption)
            .join(DbPlayer, DbPlayer.id == PodDraftParticipant.player_id)
            .where(
                PodDraftParticipant.event_id == event_id,
                PodDraftParticipant.draftmancer_name.in_(names),
                DbPlayer.discord_id.is_not(None),
            )
        ).all()
        targets = {did for did, cap in rows if not caption_has_record_pattern(cap)}
        return (thread_id, targets) if targets else None


def _capture_recovery_sync(thread_id: str, discord_id: str, image_url: str, caption: str | None) -> None:
    with SessionLocal() as session:
        capture_deck_screenshot(session, thread_id, discord_id, image_url, caption)
        session.commit()


async def _maybe_advance(bot_client, event_id: str, round_num: int, is_edit: bool = False,
                         head: str | None = None) -> None:
    """Advance, finalize, or regenerate-on-edit, depending on round state.

    First time a round completes → advance to N+1 (or for R3 start the finalize grace).
    Edit during the grace window → regenerate N+1 (or refresh standings for R3) and reset the timer.
    Once the grace timer expires → lock the round-N view and (for R3) finalize.

    Held under the manager's advance lock so two results landing at once can't both read the next
    round as unposted and each send it — the source of the duplicated pairings message.
    """
    manager = ACTIVE_POD_MANAGERS.get(event_id)
    if manager is None:
        pending_remaining = await asyncio.to_thread(_count_pending_in_round, event_id, round_num)
        if pending_remaining > 0:
            log.info(
                f"[FINALIZE] maybe_advance.pending event={event_id} round={round_num} "
                f"pending_remaining={pending_remaining} decision=wait"
            )
            return
        log.warning(
            f"[FINALIZE] maybe_advance.no_manager event={event_id} round={round_num} decision=bail"
        )
        return

    async with manager._advance_lock:
        await _advance_locked(manager, event_id, round_num, is_edit, head)


async def _advance_locked(manager, event_id: str, round_num: int, is_edit: bool,
                          head: str | None) -> None:
    if manager.pairing_mode == "bracket":
        await _bracket_maybe_advance(manager, round_num, is_edit, head)
        return

    if round_num == TOTAL_ROUNDS:
        await _post_or_update_live_standings(manager)

    pending_remaining = await asyncio.to_thread(_count_pending_in_round, event_id, round_num)
    if pending_remaining > 0:
        await maybe_arm_deck_nudge(manager)
        log.info(
            f"[FINALIZE] maybe_advance.pending event={event_id} round={round_num} "
            f"pending_remaining={pending_remaining} decision=wait"
        )
        return

    is_edit_during_grace = (manager.grace_round == round_num and manager.grace_task is not None)
    grace_active = manager.grace_task is not None and not manager.grace_task.done()

    if is_edit_during_grace:
        log.info(
            f"[FINALIZE] maybe_advance.edit_during_grace event={event_id} round={round_num} "
            f"grace_round={manager.grace_round} decision=regenerate_or_refresh"
        )
        if round_num < TOTAL_ROUNDS:
            await _regenerate_next_round(manager, round_num + 1)
        _schedule_grace(manager, round_num)
        return

    if round_num >= TOTAL_ROUNDS:
        log.info(
            f"[FINALIZE] maybe_advance.final_round event={event_id} round={round_num} "
            f"grace_active={grace_active} decision=share_log_and_schedule_grace"
        )
        await manager.share_draft_log()
        _schedule_grace(manager, round_num)
        return

    next_exists = await asyncio.to_thread(_round_has_rows, event_id, round_num + 1)
    log.info(
        f"[FINALIZE] maybe_advance.advance event={event_id} round={round_num} "
        f"next_exists={next_exists} decision={'schedule_grace' if next_exists else 'advance_and_grace'}"
    )
    if not next_exists:
        await advance_to_round(manager, round_num + 1)
    _schedule_grace(manager, round_num)


def _count_pending_in_round(event_id: str, round_num: int) -> int:
    with SessionLocal() as session:
        return session.execute(
            select(func.count(PodDraftMatch.id))
            .where(
                PodDraftMatch.event_id == event_id,
                PodDraftMatch.round == round_num,
                PodDraftMatch.winner_name.is_(None),
            )
        ).scalar_one() or 0


def _round_has_rows(event_id: str, round_num: int) -> bool:
    with SessionLocal() as session:
        count = session.execute(
            select(func.count(PodDraftMatch.id))
            .where(PodDraftMatch.event_id == event_id, PodDraftMatch.round == round_num)
        ).scalar_one() or 0
        return count > 0


async def finalize_tournament(manager: "PodDraftManager") -> None:
    if manager.finalized:
        log.info(f"[FINALIZE] tournament.already_finalized event={manager.event_id}")
        return
    log.info(f"[FINALIZE] tournament.start event={manager.event_id}")
    manager.finalized = True
    prior = await asyncio.to_thread(load_matches, manager.event_id)
    players = manager.tournament_players
    standings = pod_swiss.compute_standings(players, prior)

    final_standings = []
    for s in standings:
        wins, losses = pod_swiss.played_record(s.player_id, prior)
        final_standings.append(FinalStanding(
            draftmancer_name=s.player_name,
            placement=s.rank,
            record=f"{wins}-{losses}",
            eliminated_round=None if s.rank == 1 else TOTAL_ROUNDS,
        ))

    def _do_write() -> None:
        with SessionLocal() as session:
            finalize_db(session, manager.event_id, final_standings)
            session.commit()
    await asyncio.to_thread(_do_write)

    await _post_or_update_live_standings(manager)
    notify_pod_complete(manager.bot, manager.event_id)

    if hasattr(manager, "share_draft_log"):
        await manager.share_draft_log()

    asyncio.create_task(capture_event_replays(SeventeenLandsClient(), manager.event_id))


def _load_participant_slugs(event_id: str) -> dict[str, str]:
    """Map normalized draftmancer_name → Player.slug for participants linked to a Player."""
    with SessionLocal() as session:
        rows = session.execute(
            select(PodDraftParticipant.draftmancer_name, DbPlayer.slug)
            .join(DbPlayer, DbPlayer.id == PodDraftParticipant.player_id)
            .where(PodDraftParticipant.event_id == event_id)
        ).all()
    return {normalize_player_name(name): slug for name, slug in rows if name}


def load_participant_displays(event_id: str) -> dict[str, dict]:
    """Map normalized name → {'display_name', 'slug', 'arena', 'discord_id', 'dropped'}.

    Indexed by both draftmancer_name and the participant's display_name so pre-draft and post-draft
    participants both resolve. The display_name we *expose* prefers Player.display_name (the Discord
    display) over the participant row's display_name, which can carry stale Arena-style handles when
    the participant was created from a test/debug roster. `arena` is the linked Arena handle when known,
    surfaced in the Round 1 pairings so players can find each other in-client.
    """
    with SessionLocal() as session:
        rows = session.execute(
            select(
                PodDraftParticipant.draftmancer_name,
                PodDraftParticipant.display_name,
                DbPlayer.display_name,
                DbPlayer.slug,
                DbPlayer.arena_name,
                DbPlayer.discord_id,
                PodDraftParticipant.dropped_round,
            )
            .outerjoin(DbPlayer, DbPlayer.id == PodDraftParticipant.player_id)
            .where(PodDraftParticipant.event_id == event_id)
        ).all()
    out: dict[str, dict] = {}
    for dm, participant_dn, player_dn, slug, arena, discord_id, dropped_round in rows:
        raw = player_dn or participant_dn
        display = strip_arena_suffix(raw) if raw else raw
        arena_ref = arena or _first_arena_handle(dm, participant_dn)
        info = {"display_name": display, "slug": slug, "arena": arena_ref, "discord_id": discord_id,
                "dropped": dropped_round is not None}
        if dm:
            out[normalize_player_name(dm)] = info
        if participant_dn:
            out.setdefault(normalize_player_name(participant_dn), info)
    return out


def _first_arena_handle(*names: str | None) -> str | None:
    """First name carrying an Arena '#1234' suffix. The Draftmancer session handle stands in when a
    linked Player has no recorded arena_name, so the pairing still leads with a findable handle instead
    of dropping to the bare Discord name."""
    for name in names:
        if name and has_arena_suffix(name):
            return name
    return None


async def _resolve_discord_mention(event_id: str, draftmancer_name: str) -> str | None:
    def _query() -> str | None:
        with SessionLocal() as session:
            participant = session.execute(
                select(PodDraftParticipant).where(
                    PodDraftParticipant.event_id == event_id,
                    _normalized_column(PodDraftParticipant.draftmancer_name) == normalize_player_name(draftmancer_name),
                )
            ).scalar_one_or_none()
            if participant is None or participant.player_id is None:
                return None
            player = session.get(DbPlayer, participant.player_id)
            if player is None or not player.discord_id:
                return None
            return f"<@{player.discord_id}>"
    return await asyncio.to_thread(_query)


def _discord_display(displays: dict[str, dict], name: str) -> str:
    """Discord display for a raw Draftmancer/Arena name, falling back to the arena-stripped name when
    the participant has no linked player."""
    info = displays.get(normalize_player_name(name))
    if info and info.get("display_name"):
        return info["display_name"]
    return strip_arena_suffix(name)


def _discord_mention(displays: dict[str, dict], name: str) -> str:
    """Pingable `<@id>` for a raw Draftmancer/Arena name, falling back to the plain display when the
    participant has no linked Discord account. Fixture rosters carry non-numeric ids, so those render
    as names instead of a mention that resolves to nobody."""
    info = displays.get(normalize_player_name(name))
    discord_id = info.get("discord_id") if info else None
    if discord_id and discord_id.isdigit():
        return f"<@{discord_id}>"
    return _discord_display(displays, name)


def register_persistent_views(bot) -> None:
    """Register persistent views so component clicks dispatch after restart."""
    bot.add_view(RoundResultsView())
    bot.add_dynamic_items(ManageRoundButton)
    bot.add_view(build_live_submit_deck_view())
    bot.add_view(build_live_deck_color_select_view())


async def reset_event_matches(event_id: str) -> int:
    """Delete all pod_draft_matches rows for an event. Returns number deleted."""
    def _do() -> int:
        with SessionLocal() as session:
            result = session.execute(
                delete(PodDraftMatch).where(PodDraftMatch.event_id == event_id)
            )
            session.commit()
            return result.rowcount or 0
    return await asyncio.to_thread(_do)


def _standings_header_text(pending_count: int) -> str:
    """`'Final Standings'` when no matches pending, `'Live Standings - N match(es) pending ⏳'` otherwise."""
    if pending_count == 0:
        return "Final Standings"
    word = "match" if pending_count == 1 else "matches"
    return f"Live Standings - {pending_count} {word} pending ⏳"


REVIEW_EMOJI = "🙋"
REVIEW_REACT_PROMPT = f"React {REVIEW_EMOJI} if you would like to review your draft"


async def build_draft_review_embed(event_id: str) -> discord.Embed | None:
    """Draft-review roster table, one row per seat in Draftmancer order with the player's colors and a
    masked link to the in-site draft log. Table only — the react/join prompt lives in the message content
    (see build_draft_review_message). None when the pod has no participants yet."""
    roster = await asyncio.to_thread(_load_review_roster_sync, event_id)
    if not roster:
        return None
    event_name = await asyncio.to_thread(load_event_name_sync, event_id)
    return render_draft_review_embed(roster, event_name)


def render_draft_review_embed(roster: list[dict], event_name: str | None) -> discord.Embed:
    """Monospace roster table (same inline-code trick as /leaderboard): header `🪑 Player Result` + Colors,
    each row wrapped as a masked link to the player's in-site draft log. Mana emoji render after the code
    span — they don't render inside it."""
    event_slug = slugify(event_name) if event_name else None
    site = settings.public_site_url.rstrip("/")
    seat_w = max([display_width("🪑"), *(display_width(_review_seat_label(r)) for r in roster)])
    name_w = max([len("Player"), *(display_width(r["name"]) for r in roster)])
    result_w = max([len("Result"), *(display_width(r["result"]) for r in roster)])

    def cell(value: str, width: int) -> str:
        return value + " " * max(0, width - display_width(value))

    def center(value: str, width: int) -> str:
        pad = max(0, width - display_width(value))
        left = pad // 2
        return " " * left + value + " " * (pad - left)

    header = f"`{cell('🪑', seat_w)} {cell('Player', name_w)}  {cell('Result', result_w)}`  Colors"
    lines = [header]
    for r in roster:
        inner = f"{cell(_review_seat_label(r), seat_w)} {cell(r['name'], name_w)}  {center(r['result'], result_w)}"
        colors = format_deck_color_emojis(r["colors"])
        suffix = f"  {colors}" if colors else ""
        if r["slug"] and event_slug:
            lines.append(f"[`{inner}`](<{site}/pods/{event_slug}/{r['slug']}>){suffix}")
        else:
            lines.append(f"`{inner}`{suffix}")

    return discord.Embed(description="\n".join(lines), color=discord.Color.green())


def _review_seat_label(seat: dict) -> str:
    return str(seat["seat_index"] + 1) if seat["seat_index"] is not None else "—"


def build_draft_review_message(voice_url: str | None) -> str:
    """Message content above the table embed: the react/join prompt. Who started the review comes from
    Discord's own '/pod-review' command attribution."""
    if voice_url is None:
        return f"{REVIEW_REACT_PROMPT}."
    return f"{REVIEW_REACT_PROMPT} and join {voice_url}"


def _load_review_roster_sync(event_id: str) -> list[dict]:
    with SessionLocal() as session:
        rows = session.execute(
            select(
                PodDraftParticipant.seat_index,
                PodDraftParticipant.draftmancer_name,
                PodDraftParticipant.display_name,
                PodDraftParticipant.deck_colors,
                PodDraftParticipant.record,
                DbPlayer.display_name,
                DbPlayer.slug,
            )
            .outerjoin(DbPlayer, DbPlayer.id == PodDraftParticipant.player_id)
            .where(PodDraftParticipant.event_id == event_id)
        ).all()
        live_records = _live_records_from_matches(session, event_id)
    roster: list[dict] = []
    for seat_index, dm_name, part_display, colors, record, player_display, slug in rows:
        key = normalize_player_name(dm_name or part_display or "")
        roster.append({
            "seat_index": seat_index,
            "name": player_display or part_display or dm_name or "?",
            "colors": colors,
            "result": live_records.get(key) or record or "—",
            "slug": slug,
        })
    roster.sort(key=lambda r: (r["seat_index"] is None, r["seat_index"] or 0))
    return roster


def _live_records_from_matches(session: Session, event_id: str) -> dict[str, str]:
    """Per-player W-L over the reported matches, keyed by normalized name. Lets the review table show
    partial standings before finalize writes each participant's `record` — one outstanding match no
    longer blanks the whole column."""
    rows = session.execute(
        select(PodDraftMatch.player_a_name, PodDraftMatch.player_b_name, PodDraftMatch.winner_name)
        .where(PodDraftMatch.event_id == event_id)
    ).all()
    return tally_match_records(rows)


def tally_match_records(rows: Sequence[tuple[str, str, str | None]]) -> dict[str, str]:
    """Normalized-name → "W-L" over (player_a, player_b, winner) rows. Unplayed and skipped matches
    count toward neither side."""
    wins: dict[str, int] = {}
    losses: dict[str, int] = {}
    for a_name, b_name, winner_name in rows:
        if not winner_name or winner_name == SKIPPED_SENTINEL:
            continue
        a, b, w = (normalize_player_name(a_name), normalize_player_name(b_name),
                   normalize_player_name(winner_name))
        winner, loser = (a, b) if w == a else (b, a) if w == b else (None, None)
        if winner is None:
            continue
        wins[winner] = wins.get(winner, 0) + 1
        losses[loser] = losses.get(loser, 0) + 1
    return {key: f"{wins.get(key, 0)}-{losses.get(key, 0)}" for key in set(wins) | set(losses)}


CHAMPION_TITLE_GLYPH = "🏆"
SET_CHAMPION_TITLE_GLYPH = "👑"


def _format_champion_title(
    names_with_colors: list[tuple[str, str | None]], short_event: str, champion_mention: str | None = None,
) -> str:
    """Headline-style title — single: `Name takes {event} with {colors}`; multi: `A {colors} and
    B {colors} share {event}`. A Set Championship wears the crown instead of the trophy and drops the
    one its pod name already carries, so the headline never shows two glyphs. It names the winner as the
    set's new champion instead of taking the event, and carries no deck colors: the crown and the role
    are the headline, and the colors read on the standings row below."""
    championship = is_championship(short_event)
    glyph = SET_CHAMPION_TITLE_GLYPH if championship else CHAMPION_TITLE_GLYPH
    event = _stripped_event_title(short_event) if championship else short_event
    article = "the " if championship else ""
    if not names_with_colors:
        return f"{glyph} {event}"

    if len(names_with_colors) == 1:
        name, color = names_with_colors[0]
        if championship:
            mention = champion_mention or SYNTHETIC_CHAMPION_TAG
            return f"{glyph} {name} is the new {_event_set_code(event)} {mention}"
        emoji_run = format_deck_color_emojis(color)
        suffix = f" with {emoji_run}" if emoji_run else ""
        return f"{glyph} {name} takes {article}{event}{suffix}"

    names = _join_champion_names(names_with_colors, colors=not championship)
    return f"{glyph} {names} share {article}{event}"


def _event_set_code(event: str) -> str:
    """The set code leading a championship's name, so the headline reads `the new MSH @Set Champion`."""
    return event.split(" ", 1)[0]


def _stripped_event_title(event_name: str) -> str:
    """The event name without the leading glyph its pod name carries, so the headline supplies its own."""
    return event_name.lstrip(f"{SET_CHAMPION_TITLE_GLYPH}{CHAMPION_TITLE_GLYPH} ").strip()


def _format_champion_result_line(names_with_colors: list[tuple[str, str | None]]) -> str:
    """Card-side phrasing of the champion headline: no event name, since the card it replaces the status
    line of is the pod's own, and the glyph is supplied by the caller."""
    if len(names_with_colors) == 1:
        name, color = names_with_colors[0]
        emoji_run = format_deck_color_emojis(color)
        suffix = f" with {emoji_run}" if emoji_run else ""
        return f"{name} wins the draft{suffix}"

    return f"{_join_champion_names(names_with_colors)} share the draft"


def _join_champion_names(names_with_colors: list[tuple[str, str | None]], *, colors: bool = True) -> str:
    chunks = []
    for name, color in names_with_colors:
        emoji_run = format_deck_color_emojis(color) if colors else ""
        chunks.append(f"{name} {emoji_run}" if emoji_run else name)
    if len(chunks) == 2:
        return f"{chunks[0]} and {chunks[1]}"
    return ", ".join(chunks[:-1]) + f", and {chunks[-1]}"


def _load_champions_sync(event_id: str) -> list[tuple[str, str | None]]:
    """(bold display name, deck colors) for the pod's placement-1 finishers, for rebuilding the card's
    champion line without a live manager. Prefers the linked player's Discord display name so the winner
    reads the same as the card roster, and falls back to the Draftmancer seat name for an unlinked seat.
    The card is an embed, where a `<@id>` mention renders as raw text, so the winner is named in bold."""
    with SessionLocal() as session:
        rows = session.execute(
            select(PodDraftParticipant.display_name, PodDraftParticipant.deck_colors, DbPlayer.display_name)
            .outerjoin(DbPlayer, DbPlayer.id == PodDraftParticipant.player_id)
            .where(PodDraftParticipant.event_id == event_id, PodDraftParticipant.placement == 1)
        ).all()
    champions: list[tuple[str, str | None]] = []
    for seat_name, deck_colors, player_display in rows:
        champions.append((f"**{player_display or seat_name}**", deck_colors))
    return champions


async def champion_card_line(event_id: str) -> str | None:
    """The 🏆 winner line for a finished pod, rebuilt from persisted placements so the scheduled card
    can show it after the live manager is gone. None when the event has no recorded champion."""
    champions = await asyncio.to_thread(_load_champions_sync, event_id)
    if not champions:
        return None
    return f"🏆 {_format_champion_result_line(champions)}"


class CardDrafter(NamedTuple):
    display_name: str
    seat_index: int | None
    record: str | None
    placement: int | None
    deck_colors: str | None


def load_solo_card_drafters(event_id: str) -> tuple[list[CardDrafter], bool]:
    """The seated drafters of a non-team pod for the scheduled card's locked-roster body, plus whether
    the pod is finalized. Prefers each seat's linked Discord display name so the card reads the same as
    the champion line, and falls back to the Draftmancer seat name for an unlinked seat. Empty until the
    draft seeds participants, which drops the card back to its RSVP columns."""
    with SessionLocal() as session:
        rows = session.execute(
            select(
                PodDraftParticipant.display_name, DbPlayer.display_name,
                PodDraftParticipant.seat_index, PodDraftParticipant.record,
                PodDraftParticipant.placement, PodDraftParticipant.deck_colors,
            )
            .outerjoin(DbPlayer, DbPlayer.id == PodDraftParticipant.player_id)
            .where(PodDraftParticipant.event_id == event_id, PodDraftParticipant.team.is_(None))
            .order_by(PodDraftParticipant.seat_index)
        ).all()
        finalized_at = session.execute(
            select(PodDraftEvent.finalized_at).where(PodDraftEvent.id == event_id)
        ).scalar_one_or_none()
    drafters = [
        CardDrafter(player_display or seat_name, seat_index, record, placement, deck_colors)
        for seat_name, player_display, seat_index, record, placement, deck_colors in rows
    ]
    return drafters, finalized_at is not None


def build_champion_announcement_view(
    standings: list[pod_swiss.Standing],
    *,
    event_name: str,
    displays: dict[str, dict] | None = None,
    player_colors: dict[str, str | None] | None = None,
    leaderboard_url: str | None = None,
    pending_count: int = 0,
    deck_data: dict[str, "ParticipantDeckData"] | None = None,
    guild_id: int | None = None,
    thread_id: int | None = None,
    event_started_at: datetime | None = None,
    subtitle_override: str | None = None,
    champion_mention: str | None = None,
) -> ui.LayoutView:
    """One-shot 'champion crowned' Components V2 layout for the pod-draft channel (not the thread).

    Layout: Container (green accent) holds the headline + localized timestamp, then the blocks
    _announcement_blocks splits the announced finishers into (see announced_finishers), each one a compact
    text run of its rows with an optional italicized caption line, followed by its deck screenshots batched
    into one MediaGallery, capped at DECK_GALLERY_CAP so the grid ends on a full row and the last
    finisher's deck is the one dropped. Full standings stay in the thread embed. Thread-link button sits
    OUTSIDE the container at LayoutView top level.
    """
    displays = displays or {}
    player_colors = player_colors or {}
    deck_data = deck_data or {}

    champs_named: list[tuple[str, str | None]] = []
    for s in standings:
        if s.losses != 0:
            continue
        key = normalize_player_name(s.player_name)
        info = displays.get(key, {})
        display = info.get("display_name") or s.player_name
        champs_named.append((display, player_colors.get(key)))

    # Fall back to crowning rank 1 when nobody finished undefeated
    if not champs_named and standings:
        top = standings[0]
        key = normalize_player_name(top.player_name)
        info = displays.get(key, {})
        display = info.get("display_name") or top.player_name
        champs_named.append((display, player_colors.get(key)))

    short = short_event_name(event_name) or event_name
    title = _format_champion_title(champs_named, short, champion_mention)

    view = ui.LayoutView()
    container = ui.Container(accent_colour=discord.Color.green())

    started_at = event_started_at or datetime.now(timezone.utc)
    ts = int(started_at.timestamp())
    subtitle = subtitle_override or f"**Drafted on** <t:{ts}:F>"
    container.add_item(ui.TextDisplay(f"## {title}\n{subtitle}"))
    container.add_item(ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small))

    # Hide rows whose record isn't yet final; the announcement re-edits when later R3 results land
    top_standings = [
        s for s in announced_finishers(standings, event_name)
        if s.wins + s.losses >= TOTAL_ROUNDS
    ]

    for block in _announcement_blocks(top_standings, deck_data, event_name):
        rows: list[str] = []
        decks: list[discord.MediaGalleryItem] = []
        for s in block:
            rows.append(_build_standings_row(
                s, displays=displays, player_colors=player_colors,
                deck_data=deck_data, leaderboard_url=leaderboard_url,
                event_name=event_name, inline_caption=True,
            ))
            key = normalize_player_name(s.player_name)
            data = deck_data.get(key)
            if data is None or not data.screenshot_url:
                continue
            info = displays.get(key, {})
            name = info.get("display_name") or s.player_name
            decks.append(
                discord.MediaGalleryItem(media=data.screenshot_url, description=f"{name}'s deck"),
            )
        container.add_item(ui.TextDisplay("\n".join(rows)))
        if decks:
            container.add_item(ui.MediaGallery(*decks[:DECK_GALLERY_CAP]))

    view.add_item(container)

    actions = ui.ActionRow()
    if guild_id and thread_id:
        actions.add_item(build_thread_link_button(guild_id, thread_id))
    actions.add_item(build_replays_link_button(event_name))
    view.add_item(actions)

    return view


def _announcement_blocks(finishers, deck_data, event_name: str | None) -> list[list[pod_swiss.Standing]]:
    """The announced rows split into the blocks the card draws, each block one text run plus its own deck
    gallery. A pod groups by record, so its 3-0s and its 2-1s each get a gallery of their own. A Set
    Championship keeps the champion alone above their full-size deck, once they have posted one, with the
    rest of the field in a single block below."""
    if is_championship(event_name):
        champion = finishers[0] if finishers else None
        data = deck_data.get(normalize_player_name(champion.player_name)) if champion else None
        if data is not None and data.screenshot_url:
            return [block for block in ([champion], finishers[1:]) if block]
        return [finishers] if finishers else []
    blocks: list[list[pod_swiss.Standing]] = []
    for s in finishers:
        if blocks and blocks[-1][0].losses == s.losses:
            blocks[-1].append(s)
        else:
            blocks.append([s])
    return blocks


def round_header(round_num: int, complete: bool, *, seated: bool = True) -> str:
    if complete:
        return f"✅ Round {round_num} complete!"
    if round_num == 1:
        return f"⚔️ Round {round_num} Pairings {'by Seats' if seated else '(Random)'} ⚔️"
    return f"⚔️ Round {round_num} Pairings ⚔️"


_ROUND_TITLE_RE = re.compile(r"Round (\d+)")  # restart recovery reads the round number back out of round_header titles


def escape_italics(text: str) -> str:
    return text.replace("_", "\\_").replace("*", "\\*")


_LEADING_RECORD_RE = re.compile(r"^\s*\d{1,2}\s*[-:\s]\s*\d{1,2}(?:\s*[-:\s]\s*\d{1,2})?\s*[,;:.\-]?\s*")


def clean_caption(raw: str) -> str:
    """Strip a leading W-L like '2-1' / '3:0' / '3 0' — the standings row already shows the record."""
    return _LEADING_RECORD_RE.sub("", raw).strip()


def build_champion_embed(
    standings: list[pod_swiss.Standing],
    *,
    event_name: str = "Pod Draft",
    displays: dict[str, dict] | None = None,
    player_colors: dict[str, str | None] | None = None,
    leaderboard_url: str | None = None,
    champion_locked: bool = True,
    pending_count: int = 0,
    deck_data: dict[str, "ParticipantDeckData"] | None = None,
    event_has_log: bool = False,
    match_states: list[dict] | None = None,
) -> discord.Embed:
    """Thread-side standings embed. `player_colors` adds a mana-emoji glyph after each player's record.
    `event_has_log` appends an inline Draft Log link per row pointing at the in-site reviewer when the
    event has a captured draft log. `match_states` (final, trophy-marked) drives the tiebreaker table,
    shown only once the pod is complete and a placement was actually decided on tiebreakers."""
    displays = displays or {}
    player_colors = player_colors or {}
    deck_data = deck_data or {}
    medals_locked = pending_count == 0
    lines = [
        _build_standings_row(
            s, displays=displays, player_colors=player_colors,
            deck_data=deck_data, leaderboard_url=leaderboard_url, event_name=event_name,
            event_has_log=event_has_log,
            show_medal=medals_locked or (champion_locked and s.rank == 1),
        )
        for s in standings
    ]

    heading = f"### 🏆 {event_name}" if champion_locked else f"### 🟢 {event_name}"

    header = f"**{_standings_header_text(pending_count)}**"

    description = f"{heading}\n{header}\n" + "\n".join(lines)
    if pending_count == 0 and match_states:
        tiebreakers = _build_tiebreaker_block(standings, match_states, displays)
        if tiebreakers:
            description += f"\n{tiebreakers}"

    return discord.Embed(
        description=description,
        color=discord.Color.green(),
    )


def _trophy_match_loser_rank(standings, match_states) -> int | None:
    """Final rank of the player who lost a trophy match, or None when no trophy match has a winner yet."""
    if not match_states:
        return None
    rank_by_key = {normalize_player_name(s.player_name): s.rank for s in standings}
    for m in match_states:
        if not m.get("is_trophy_match"):
            continue
        winner = m.get("winner_name")
        if not winner or winner == SKIPPED_SENTINEL:
            continue
        if normalize_player_name(winner) == normalize_player_name(m.get("a_name") or ""):
            loser = m.get("b_name")
        else:
            loser = m.get("a_name")
        rank = rank_by_key.get(normalize_player_name(loser or ""))
        if rank is not None:
            return rank
    return None


def _contested_win_counts(standings, match_states) -> set[int]:
    """Win-count groups whose internal order the standings settled on tiebreakers: the top group when
    the champion took a loss, and the trophy-match loser's group when they placed below second."""
    contested: set[int] = set()
    champion = standings[0] if standings else None
    if champion is not None and champion.losses > 0:
        contested.add(champion.wins)
    loser_rank = _trophy_match_loser_rank(standings, match_states)
    if loser_rank is not None and loser_rank != 2:
        for s in standings:
            if s.rank == loser_rank:
                contested.add(s.wins)
                break
    return contested


def _build_tiebreaker_block(standings, match_states, displays) -> str | None:
    """Monospace OMW%/GW%/OGW% table for the tie groups that decided a contested placement, or None
    when every placement fell straight out of match record."""
    contested = _contested_win_counts(standings, match_states)
    if not contested:
        return None
    displays = displays or {}

    def _name(s) -> str:
        return displays.get(normalize_player_name(s.player_name), {}).get("display_name") or s.player_name

    rows = [s for s in standings if s.wins in contested]
    if len(rows) < 2:
        return None
    name_col = max(len(_name(s)) for s in rows)
    lines = ["```", f"{'#':<2} {'Player':<{name_col}}  OMW   GW  OGW"]
    for s in rows:
        lines.append(
            f"{s.rank:<2} {_name(s):<{name_col}}  "
            f"{s.omw_pct * 100:>3.0f}  {s.gw_pct * 100:>3.0f}  {s.ogw_pct * 100:>3.0f}"
        )
    lines.append("```")
    return "**Tiebreakers**\n" + "\n".join(lines)


async def build_standings_embed_for_event(event_id: str) -> discord.Embed | None:
    """Snapshot variant of the live standings: same shape as `_post_or_update_live_standings`'s
    embed but loads tournament_players from the DB (no in-memory manager required) and omits the
    Submit-Deck CTA. Events with no match rows (record-only backfills) fall back to the stored
    placements; returns None when there are neither pairings nor placements. Team pods render
    their own embed — the swiss shape assumes a single champion."""
    if await asyncio.to_thread(load_event_pairing_mode_sync, event_id) == "team":
        from bot.services.pod_team_flow import build_team_standings_embed_for_event

        return await build_team_standings_embed_for_event(event_id)
    players = await asyncio.to_thread(load_tournament_players_sync, event_id)
    if not players:
        return None
    match_states = await asyncio.to_thread(_load_round_states, event_id, TOTAL_ROUNDS)
    if match_states:
        mark_trophy_match(match_states, TOTAL_ROUNDS)
        trophy = [m for m in match_states if m.get("is_trophy_match")]
        champion_locked = bool(trophy) and all(m.get("winner_name") for m in trophy)
        pending_count = sum(1 for m in match_states if not m.get("winner_name"))
        prior = await asyncio.to_thread(load_matches, event_id)
        standings = pod_swiss.compute_standings(players, prior)
    else:
        standings = await asyncio.to_thread(_load_participant_standings_sync, event_id)
        if not standings:
            return None
        champion_locked = any(s.rank == 1 for s in standings)
        pending_count = 0
    displays = await asyncio.to_thread(load_participant_displays, event_id)
    event_name = await asyncio.to_thread(load_event_name_sync, event_id)
    deck_data = await asyncio.to_thread(load_event_deck_data_sync, event_id)
    event_has_log = await asyncio.to_thread(_event_has_draft_log_sync, event_id)
    player_colors = colors_only(deck_data)
    return build_champion_embed(
        standings,
        event_name=event_name,
        displays=displays,
        player_colors=player_colors,
        leaderboard_url=settings.leaderboard_url,
        champion_locked=champion_locked,
        pending_count=pending_count,
        deck_data=deck_data,
        event_has_log=event_has_log,
        match_states=match_states,
    )


async def _resolve_announcement_standings(event_id: str):
    """Standings for the post-finalize champion announcement, or None when the trophy match has no
    winner yet. Prefers live pairings; falls back to stored placements for record-only backfills.
    Returns (standings, match_states), with match_states empty on the stored-placements path."""
    players = await asyncio.to_thread(load_tournament_players_sync, event_id)
    if not players:
        return None
    match_states = await asyncio.to_thread(_load_round_states, event_id, TOTAL_ROUNDS)
    if match_states:
        mark_trophy_match(match_states, TOTAL_ROUNDS)
        trophy = [m for m in match_states if m.get("is_trophy_match")]
        if not trophy or not all(m.get("winner_name") for m in trophy):
            return None
        prior = await asyncio.to_thread(load_matches, event_id)
        standings = pod_swiss.compute_standings(players, prior)
        if not standings:
            return None
        nobody_undefeated = not any(s.losses == 0 for s in standings)
        round_three_open = not all(m.get("winner_name") for m in match_states)
        if nobody_undefeated and round_three_open:
            return None
        return standings, match_states
    standings = await asyncio.to_thread(_load_participant_standings_sync, event_id)
    if not standings or not any(s.rank == 1 for s in standings):
        return None
    return standings, []


async def build_champion_announcement_view_for_event(
    event_id: str,
    *,
    guild_id: int | None = None,
    guild=None,
) -> ui.LayoutView | None:
    """Manager-free builder for the channel-level champion announcement view. Returns None when the
    trophy match has no winner yet, nobody is undefeated, or the event has neither pairings nor
    stored placements. Used by /pod-champion to re-post the announcement after the fact (e.g. when
    finalization was missed, or for a record-only backfill)."""
    resolved = await _resolve_announcement_standings(event_id)
    if resolved is None:
        return None
    standings, match_states = resolved
    displays = await asyncio.to_thread(load_participant_displays, event_id)
    deck_data = await asyncio.to_thread(load_event_deck_data_sync, event_id)
    player_colors = colors_only(deck_data)
    event_name = await asyncio.to_thread(load_event_name_sync, event_id)
    event_started_at = await asyncio.to_thread(load_event_started_at_sync, event_id)
    thread_id_str = await asyncio.to_thread(load_event_thread_id_sync, event_id)
    thread_id = int(thread_id_str) if thread_id_str else None
    pending_count = sum(1 for m in match_states if not m.get("winner_name"))

    return build_champion_announcement_view(
        standings,
        event_name=event_name,
        displays=displays,
        player_colors=player_colors,
        leaderboard_url=settings.leaderboard_url,
        pending_count=pending_count,
        deck_data=deck_data,
        event_started_at=event_started_at,
        guild_id=guild_id,
        thread_id=thread_id,
        champion_mention=champion_role_mention(find_role(guild, SET_CHAMPION_ROLE_NAME)),
    )


def _schedule_grace(manager, round_num: int) -> None:
    """(Re)start the grace timer for round_num. Cancels any pending grace on the same manager."""
    if manager.grace_task is not None and not manager.grace_task.done():
        manager.grace_task.cancel()
        log.info(
            f"[FINALIZE] grace.reset event={manager.event_id} round={round_num} window_s={GRACE_SECONDS}"
        )
    else:
        log.info(
            f"[FINALIZE] grace.scheduled event={manager.event_id} round={round_num} window_s={GRACE_SECONDS}"
        )
    manager.grace_round = round_num
    manager.grace_task = asyncio.create_task(_grace_expire(manager, round_num))


async def _locked_round_view(manager, round_num: int):
    """View for a round once its grace window passes: reported dropdowns are hidden (results stay
    visible in the round embed) and only the nav link survives."""
    states = await asyncio.to_thread(
        render_round_states, manager.event_id, round_num, bracket=manager.pairing_mode == "bracket",
    )
    for m in states:
        if m.get("winner_name"):
            m["locked"] = True
    url, label = _round_nav_link(manager, round_num)
    return RoundResultsView(states, round_num=round_num, link_url=url, link_label=label)


async def _grace_expire(manager, round_num: int) -> None:
    try:
        await asyncio.sleep(GRACE_SECONDS)
    except asyncio.CancelledError:
        return

    log.info(f"[FINALIZE] grace.expired event={manager.event_id} round={round_num}")

    msg = manager.round_messages.get(round_num)
    if msg is not None:
        try:
            await msg.edit(view=await _locked_round_view(manager, round_num))
        except Exception:
            log.warning(f"[FINALIZE] grace.lock_view_error round={round_num}", exc_info=True)

    await _lock_round_dms(manager.bot, manager.event_id, round_num)

    if round_num >= TOTAL_ROUNDS and not manager.finalized:
        await finalize_tournament(manager)
        schedule_deck_ping(manager, delay=DECK_PING_DELAY_SECONDS - GRACE_SECONDS)
        if manager.championship_task is None:
            manager.championship_task = asyncio.create_task(_championship_deadline(manager))
        await maybe_post_championship(manager)

    manager.grace_round = None
    manager.grace_task = None


async def _lock_round_dms(bot_client, event_id: str, round_num: int) -> None:
    """Strip the result-dropdown view from every tracked pairing DM for this round."""
    rows = await asyncio.to_thread(_dm_rows_for_round_sync, event_id, round_num)
    for row in rows:
        try:
            channel = bot_client.get_channel(int(row.dm_channel_id)) \
                or await bot_client.fetch_channel(int(row.dm_channel_id))
            dm_msg = await channel.fetch_message(int(row.dm_message_id))
            await dm_msg.edit(view=None)
        except discord.HTTPException:
            log.warning(f"could not lock DM {row.dm_message_id} for round {round_num}", exc_info=True)


def _dm_rows_for_round_sync(event_id: str, round_num: int):
    with SessionLocal() as session:
        rows = dm_messages_for_round(session, event_id, round_num)
        session.expunge_all()
        return rows


async def _regenerate_next_round(manager, next_round: int) -> None:
    """A previous-round edit landed during grace — re-pair `next_round` and edit its message in place.

    Re-pairs via Swiss using updated prior results before touching the existing rows, then swaps them
    and DMs any participant whose opponent changed. A pairing failure leaves the prior rows intact.
    """
    event_id = manager.event_id
    prev_pairings = await asyncio.to_thread(_load_pairings_for_round, event_id, next_round)

    prior = await asyncio.to_thread(load_matches, event_id)
    try:
        pairings = pod_swiss.pair_round(manager.tournament_players, prior, next_round)
    except ValueError as e:
        log.error("regenerate pairings for round %d failed for %s: %s", next_round, event_id, e)
        await alert_thread_and_owner(
            manager, POD_REPAIR_FAILED_MSG.format(round_num=next_round),
            f"Pod `{event_id}` round {next_round} re-pair after edit failed, keeping prior pairings: {e}",
            fingerprint=f"pod_pairing_failed:{event_id}:{next_round}:regen",
        )
        return

    await asyncio.to_thread(_delete_round_rows, event_id, next_round)

    pending_rows = await asyncio.to_thread(insert_pending_matches, event_id, next_round, pairings)
    standings_by_id = {s.player_id: s for s in pod_swiss.compute_standings(manager.tournament_players, prior)}
    displays = await asyncio.to_thread(load_participant_displays, event_id)
    match_states = [_state_for_pending(match_id, a, b, standings_by_id, displays) for match_id, a, b in pending_rows]
    mark_trophy_match(match_states, next_round)
    embed = round_embed(next_round, match_states)
    url, label = _round_nav_link(manager, next_round)
    view = RoundResultsView(match_states, round_num=next_round, link_url=url, link_label=label)

    posted = manager.round_messages.get(next_round)
    if posted is not None:
        try:
            await posted.edit(embed=embed, view=view)
        except Exception:
            log.warning("could not edit round %d message during regenerate", next_round, exc_info=True)

    new_opponent_pairs = _changed_opponent_pairs(prev_pairings, pairings)
    if new_opponent_pairs and posted is not None:
        await _dm_changed_opponents(manager.bot, event_id, next_round, new_opponent_pairs, posted.jump_url)


def _load_pairings_for_round(event_id: str, round_num: int) -> list[tuple[str, str]]:
    with SessionLocal() as session:
        rows = session.execute(
            select(PodDraftMatch.player_a_name, PodDraftMatch.player_b_name)
            .where(PodDraftMatch.event_id == event_id, PodDraftMatch.round == round_num)
            .order_by(PodDraftMatch.pairing_index)
        ).all()
    return [(a, b) for a, b in rows]


def _dm_refs_for_rounds_sync(event_id: str, rounds) -> dict[tuple[int, str], tuple[str, str]]:
    """(round, participant_id) → (dm_channel_id, dm_message_id) for the pairing DMs already delivered.

    Read before a regenerate deletes the match rows: the DM refs hang off match_id with ON DELETE
    CASCADE, so they go with them, and the rebuilt round would DM everyone a second time.
    """
    refs: dict[tuple[int, str], tuple[str, str]] = {}
    with SessionLocal() as session:
        for round_num in rounds:
            for row in dm_messages_for_round(session, event_id, round_num):
                refs[(round_num, row.participant_id)] = (row.dm_channel_id, row.dm_message_id)
    return refs


def _delete_round_rows(event_id: str, round_num: int) -> None:
    with SessionLocal() as session:
        session.execute(
            delete(PodDraftMatch).where(PodDraftMatch.event_id == event_id, PodDraftMatch.round == round_num)
        )
        session.commit()


def _prune_stale_pairings(event_id: str, round_num: int, keep: list[tuple[str, str]]) -> None:
    """Delete this round's pairings except `keep`, then compact pairing_index over the survivors so the
    pairer can append from len(survivors) without landing on an index still in use."""
    kept_keys = _pairing_keys(keep)
    with SessionLocal() as session:
        rows = session.execute(
            select(PodDraftMatch)
            .where(PodDraftMatch.event_id == event_id, PodDraftMatch.round == round_num)
            .order_by(PodDraftMatch.pairing_index)
        ).scalars().all()
        index = 0
        for row in rows:
            key = frozenset((
                normalize_player_name(row.player_a_name), normalize_player_name(row.player_b_name),
            ))
            if key in kept_keys:
                row.pairing_index = index
                index += 1
            else:
                session.delete(row)
        session.commit()


def _changed_opponent_pairs(
    prev: list[tuple[str, str]],
    new: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Return (player, new_opponent) tuples for every player whose opponent changed between prev and new."""
    def _by_player(pairs):
        out: dict[str, str] = {}
        for a, b in pairs:
            out[normalize_player_name(a)] = b
            out[normalize_player_name(b)] = a
        return out
    prev_map = _by_player(prev)
    new_map = _by_player(new)
    changed: list[tuple[str, str]] = []
    for player_key, new_opp in new_map.items():
        prev_opp = prev_map.get(player_key)
        if prev_opp is None or normalize_player_name(prev_opp) != normalize_player_name(new_opp):
            for a, b in new:
                if normalize_player_name(a) == player_key:
                    changed.append((a, b))
                    break
                if normalize_player_name(b) == player_key:
                    changed.append((b, a))
                    break
    return changed


async def _dm_changed_opponents(
    bot_client,
    event_id: str,
    round_num: int,
    changed: list[tuple[str, str]],
    pairings_url: str,
) -> None:
    dm_info = await asyncio.to_thread(load_dm_info_sync, event_id)
    event_name = await asyncio.to_thread(load_event_name_sync, event_id)
    seen: set[str] = set()
    for player_name, new_opp in changed:
        key = normalize_player_name(player_name)
        if key in seen:
            continue
        seen.add(key)
        info = dm_info.get(key)
        if info is None or not info.discord_id:
            continue
        opp_info = dm_info.get(normalize_player_name(new_opp))
        opp_label = _opponent_dm_label(opp_info, new_opp)
        opp_arena = opp_info.arena_name if opp_info else None
        embed = build_pairing_dm_embed(
            round_num=round_num,
            opponent_label=opp_label,
            opponent_arena=opp_arena,
            pairings_url=pairings_url,
            event_name=event_name,
            updated=True,
        )
        try:
            user = await fetch_dm_user(bot_client, info.discord_id)
            if user is None:
                continue
            await user.send(embed=embed)
        except discord.Forbidden:
            log.info(f"re-pair DM blocked for {info.discord_id}")
        except discord.HTTPException:
            log.warning("re-pair DM failed", exc_info=True)


async def _resolve_announcement_target(manager):
    """Return the parent channel for the pod-draft thread; falls back to fetching by parent_id when
    the cache doesn't have it, then to the thread itself if no parent exists at all.
    """
    thread = await manager._fetch_thread()
    if thread is None:
        return None
    parent = getattr(thread, "parent", None)
    if parent is None:
        parent_id = getattr(thread, "parent_id", None)
        if parent_id:
            try:
                parent = await manager.bot.fetch_channel(parent_id)
            except Exception:
                log.warning("could not fetch parent for thread %s", thread.id, exc_info=True)
    return parent or thread


async def resolve_chat_target(manager):
    """Channel for the pod championship announcement: the dedicated pod-draft-chat channel when it
    exists, else the thread's parent (coordination) channel as before."""
    parent = await _resolve_announcement_target(manager)
    guild = getattr(parent, "guild", None)
    if guild is not None:
        chat = channel_matching_name(guild, settings.pod_draft_chat_channel_name)
        if chat is not None:
            return chat
    return parent


def deck_complete(data: "ParticipantDeckData | None") -> bool:
    """A participant's deck is share-complete once both colors and a screenshot are on record."""
    return bool(data and data.colors and data.screenshot_url)


def deck_missing_parts(data: "ParticipantDeckData | None") -> list[str]:
    """Which share-complete pieces a participant still owes, in "screenshot", "colors" order."""
    missing = []
    if not (data and data.screenshot_url):
        missing.append("screenshot")
    if not (data and data.colors):
        missing.append("colors")
    return missing


def announced_finishers(standings, event_name: str | None) -> list[pod_swiss.Standing]:
    """How far the channel announcement reaches: every record within ANNOUNCED_MAX_LOSSES for a normal pod,
    so a ten-player pod posts all of its 2-1s instead of cutting at a fixed four, and the whole field for a
    Set Championship, whose full result is the record worth keeping. A pod of four goes out whole too: one
    loss cuts it to two rows, which reads as half a result. The same set gates the post, so every row it
    shows has had its deck waited for."""
    if is_championship(event_name) or len(standings) <= FULL_FIELD_POD_SIZE:
        return list(standings)
    return [s for s in standings if s.losses <= ANNOUNCED_MAX_LOSSES]


def incomplete_decks(finishers, deck_data) -> list[str]:
    """Names among `finishers` still missing colors or a screenshot. Empty list means the post they gate
    is clear to go up."""
    return [
        s.player_name for s in finishers
        if not deck_complete(deck_data.get(normalize_player_name(s.player_name)))
    ]


async def maybe_arm_deck_nudge(manager) -> None:
    """Arm the one gentle screenshot reminder once a few players are done playing, so the pod hears the
    ask while the last tables are still in their match instead of a minute after they report.

    Armed at most once per pod, and only in the final round — earlier than that the deck slot is closed
    and a screenshot posted in answer would be dropped."""
    if manager.deck_nudge_task is not None or manager.current_round < TOTAL_ROUNDS:
        return
    finished = await asyncio.to_thread(finished_players_sync, manager.event_id)
    if len(finished) < DECK_NUDGE_AFTER_FINISHERS:
        return
    log.info(f"[FINALIZE] deck_nudge.armed event={manager.event_id} finished={len(finished)}")
    manager.deck_nudge_task = asyncio.create_task(_delayed_deck_nudge(manager))


async def _delayed_deck_nudge(manager) -> None:
    """Post the reminder DECK_NUDGE_DELAY_SECONDS after arming, and only if a player who is done playing
    still owes a screenshot — a pod that posts its decks on its own gets no reminder at all. Colors are
    left out of the ask on purpose: the screenshot is what needs the lead time, and the deck-chase ping
    carries the color button later."""
    try:
        await asyncio.sleep(DECK_NUDGE_DELAY_SECONDS)
    except asyncio.CancelledError:
        return
    owing = await finished_players_owing_screenshots(manager.event_id)
    if not owing:
        log.info(f"[FINALIZE] deck_nudge.skip event={manager.event_id} reason=nobody_owes")
        return
    thread = await manager._fetch_thread()
    if thread is None:
        log.info(f"[FINALIZE] deck_nudge.skip event={manager.event_id} reason=no_thread")
        return
    try:
        await thread.send(DECK_NUDGE_MSG, allowed_mentions=discord.AllowedMentions.none())
        log.info(f"[FINALIZE] deck_nudge.sent event={manager.event_id} owing={len(owing)}")
    except Exception:
        log.warning(f"[FINALIZE] deck_nudge.error event={manager.event_id}", exc_info=True)


async def finished_players_owing_screenshots(event_id: str) -> list[str]:
    """Keys of the players with no match left to play whose deck screenshot is still missing."""
    finished = await asyncio.to_thread(finished_players_sync, event_id)
    deck_data = await asyncio.to_thread(load_event_deck_data_sync, event_id)
    return [key for key in finished if not (deck_data.get(key) and deck_data[key].screenshot_url)]


def finished_players_sync(event_id: str) -> set[str]:
    with SessionLocal() as session:
        open_pairs = session.execute(
            select(PodDraftMatch.player_a_name, PodDraftMatch.player_b_name)
            .where(PodDraftMatch.event_id == event_id, PodDraftMatch.winner_name.is_(None))
        ).all()
        participants = session.execute(
            select(PodDraftParticipant.draftmancer_name, PodDraftParticipant.display_name)
            .where(PodDraftParticipant.event_id == event_id)
        ).all()
    return finished_player_keys(participants, open_pairs)


def finished_player_keys(participants, open_pairs) -> set[str]:
    """Keys of the players with no unreported match left, so every mode reads the same "done playing"
    set: a Swiss seat once its R3 result lands, a bracket seat once it is eliminated or wins the final,
    a team seat once all three of its ungated rounds are in. A seat is matched on either of its names,
    since pairings carry the Draftmancer handle while a roster-only seat has just its display name."""
    still_playing = {normalize_player_name(name) for pair in open_pairs for name in pair if name}
    finished: set[str] = set()
    for draftmancer_name, display_name in participants:
        keys = {normalize_player_name(name) for name in (draftmancer_name, display_name) if name}
        primary = normalize_player_name(draftmancer_name or display_name or "")
        if primary and not keys & still_playing:
            finished.add(primary)
    return finished


def schedule_deck_ping(manager, *, blocking_keys: set[str] | None = None, delay: float) -> None:
    """Hold the deck-chase ping until `delay` seconds from now. The last table to report shouldn't be
    pinged for a screenshot while they are still typing their post."""
    if manager.deck_ping_task is not None and not manager.deck_ping_task.done():
        return
    log.info(f"[FINALIZE] deck_ping.scheduled event={manager.event_id} delay_s={delay:.0f}")
    manager.deck_ping_task = asyncio.create_task(_delayed_deck_ping(manager, blocking_keys, delay))


async def _delayed_deck_ping(manager, blocking_keys: set[str] | None, delay: float) -> None:
    try:
        await asyncio.sleep(max(0.0, delay))
    except asyncio.CancelledError:
        return
    await ping_missing_deck_participants(manager, blocking_keys)


async def ping_missing_deck_participants(manager, blocking_keys: set[str] | None = None) -> None:
    """At tournament end, post a single deck-chase ping split by audience: the players gating the
    championship post get the urgent block, everyone else the pod-page nudge. The gating set defaults
    to the announced finishers; team pods pass their own (winning side plus losing 3-0s). Skips silently
    once every participant has both colors and a screenshot on record."""
    event_id = manager.event_id
    deck_data = await asyncio.to_thread(load_event_deck_data_sync, event_id)
    dm_info = await asyncio.to_thread(load_dm_info_sync, event_id)
    prior = await asyncio.to_thread(load_matches, event_id)
    event_name = await asyncio.to_thread(load_event_name_sync, event_id)
    standings = pod_swiss.compute_standings(manager.tournament_players, prior)
    blocking, other = _missing_deck_mentions(
        standings, dm_info, deck_data, blocking_keys, event_name=event_name)
    content = build_deck_ping(blocking, other, pod_page_url(event_name))
    if not content:
        log.info(f"[FINALIZE] deck_ping.skip event={event_id} reason=all_complete")
        return
    thread = await manager._fetch_thread()
    if thread is None:
        log.info(f"[FINALIZE] deck_ping.skip event={event_id} reason=no_thread")
        return
    view = ui.View(timeout=None)
    view.add_item(build_live_submit_deck_button())
    try:
        await thread.send(
            content=content,
            allowed_mentions=discord.AllowedMentions(users=True),
            view=view,
        )
        blocking_count = len(set(blocking[0]) | set(blocking[1]))
        other_count = len(set(other[0]) | set(other[1]))
        log.info(
            f"[FINALIZE] deck_ping.sent event={event_id} blocking={blocking_count} other={other_count}"
        )
    except Exception:
        log.warning(f"[FINALIZE] deck_ping.error event={event_id}", exc_info=True)


def _missing_deck_mentions(standings, dm_info, deck_data, blocking_keys: set[str] | None = None,
                           *, event_name: str | None = None) -> tuple[DeckPingAudience, DeckPingAudience]:
    """Split incomplete participants into the championship blockers (the gating set still owing a
    deck) and everyone else, each as (owes-screenshot, owes-colors) id lists. Standings order first
    so top finishers lead; participants absent from standings fall to the non-blocking audience."""
    if blocking_keys is None:
        finishers = announced_finishers(standings, event_name)
        blocking_keys = {
            normalize_player_name(n) for n in incomplete_decks(finishers, deck_data)
        }
    blocking: DeckPingAudience = ([], [])
    other: DeckPingAudience = ([], [])
    seen: set[str] = set()

    def collect(key: str) -> None:
        info = dm_info.get(key)
        data = deck_data.get(key)
        if info is None or not info.discord_id or deck_complete(data):
            return
        seen.add(key)
        missing = deck_missing_parts(data)
        screenshot_ids, colors_ids = blocking if key in blocking_keys else other
        if "screenshot" in missing:
            screenshot_ids.append(info.discord_id)
        if "colors" in missing:
            colors_ids.append(info.discord_id)

    for standing in standings:
        key = normalize_player_name(standing.player_name)
        if key not in seen:
            collect(key)
    for key in dm_info:
        if key not in seen:
            collect(key)
    return blocking, other


async def _championship_deadline(manager) -> None:
    """Hard cap: CHAMPIONSHIP_DEADLINE_SECONDS after R3 ends, post the announcement with whatever
    decks have landed. R3 end already cost one grace window, so only wait the remainder here."""
    try:
        await asyncio.sleep(max(0, CHAMPIONSHIP_DEADLINE_SECONDS - GRACE_SECONDS))
    except asyncio.CancelledError:
        return
    log.info(f"[FINALIZE] championship.deadline_reached event={manager.event_id}")
    await maybe_post_championship(manager, force=True)
    await manager.disconnect_safely()


async def maybe_post_championship(manager, *, force: bool = False) -> None:
    """Post the one-time podium post (ComponentsV2 screenshot gallery) to pod-draft-chat, then release the
    pod's Play Again sign-off with a link to it. Fires once every announced finisher (3-0 and 2-1, or the
    whole pod for a Set Championship) has colors and a screenshot, or when forced by the deadline. Posts
    once, never edits.

    The champion-only #trophy-hype card posts separately, once the champions' decks are complete —
    see maybe_post_trophy_hype. Team pods never post either — a team draft has no single champion;
    the team flow announces its own result.
    """
    if manager.pairing_mode == "team":
        return
    await maybe_post_trophy_hype(manager, force=force)
    if manager.champion_announced:
        return
    event_id = manager.event_id
    if await asyncio.to_thread(championship_posted_at_sync, event_id) is not None:
        manager.champion_announced = True
        return
    if not manager.finalized:
        log.info(f"[FINALIZE] champion.skip event={event_id} reason=not_finalized")
        return

    match_states = await asyncio.to_thread(_load_round_states, event_id, TOTAL_ROUNDS)
    if not match_states:
        log.info(f"[FINALIZE] champion.skip event={event_id} reason=no_match_states")
        return
    if any(not m.get("winner_name") for m in match_states):
        log.info(f"[FINALIZE] champion.skip event={event_id} reason=r3_incomplete")
        return

    prior = await asyncio.to_thread(load_matches, event_id)
    standings = pod_swiss.compute_standings(manager.tournament_players, prior)
    if not standings:
        log.info(f"[FINALIZE] champion.skip event={event_id} reason=no_standings")
        return

    event_name = await asyncio.to_thread(load_event_name_sync, event_id)
    deck_data = await asyncio.to_thread(load_event_deck_data_sync, event_id)
    finishers = announced_finishers(standings, event_name)
    incomplete = incomplete_decks(finishers, deck_data)
    if incomplete and not force:
        log.info(
            f"[FINALIZE] champion.skip event={event_id} reason=awaiting_finisher_decks "
            f"announced={len(finishers)} missing={incomplete}"
        )
        return

    if manager.champion_announced:
        return
    target = await resolve_chat_target(manager)
    if target is None:
        log.info(f"[FINALIZE] champion.skip event={event_id} reason=no_target")
        return

    displays = await asyncio.to_thread(load_participant_displays, event_id)
    champions = [s for s in standings if s.losses == 0] or [standings[0]]
    champion_keys = {normalize_player_name(c.player_name) for c in champions}
    dm_info = await asyncio.to_thread(load_dm_info_sync, event_id)
    manager.champion_discord_ids = {
        info.discord_id for key, info in dm_info.items()
        if key in champion_keys and info.discord_id
    }
    thread_id = int(manager.thread_id) if isinstance(manager.thread_id, (int, str)) else None
    guild = getattr(target, "guild", None)
    player_colors = colors_only(deck_data)

    view = build_champion_announcement_view(
        standings,
        event_name=event_name,
        displays=displays,
        player_colors=player_colors,
        leaderboard_url=settings.leaderboard_url,
        pending_count=0,
        deck_data=deck_data,
        event_started_at=await asyncio.to_thread(load_event_started_at_sync, event_id),
        guild_id=getattr(guild, "id", None),
        thread_id=thread_id,
        champion_mention=champion_role_mention(find_role(guild, SET_CHAMPION_ROLE_NAME)),
    )
    manager.champion_announced = True  # claim before the await so concurrent triggers don't double-post
    try:
        manager.champion_announcement_message = await target.send(
            view=view, allowed_mentions=discord.AllowedMentions.none())
        await asyncio.to_thread(mark_championship_posted_sync, event_id)
        notify_podium_posted(manager.bot, event_id, manager.champion_announcement_message.jump_url)
        log.info(
            f"[FINALIZE] champion.posted event={event_id} rank1={champions[0].player_name!r} "
            f"forced={force} missing={incomplete}"
        )
    except Exception:
        manager.champion_announced = False
        log.warning(f"[FINALIZE] champion.post_error event={event_id}", exc_info=True)
        return
    if is_championship(event_name):
        guild = getattr(target, "guild", None)
        await swap_set_champion_role(guild, manager.champion_discord_ids)
        await grant_set_champion_title(guild, manager.set_code, manager.champion_discord_ids)
    await _set_champion_card_result(manager, champions, player_colors)
    await _react_trophy_on_champion_screenshots(manager, deck_data, dm_info)
    if not force and manager.championship_task is not None and not manager.championship_task.done():
        manager.championship_task.cancel()
    await manager.disconnect_safely()


async def maybe_post_trophy_hype(manager, *, force: bool = False) -> None:
    """Post the champion-only #trophy-hype card as soon as the champion is decided and their deck is
    complete — the trophy match settling is enough, so a still-open 1-1 or last-chance match no longer
    holds the card back until the whole round finalizes. `_resolve_announcement_standings` returns None
    until the trophy match has a winner, so this never fires on a mid-tournament leader. Fires once per
    event; the in-memory flag guards the live path and a channel scan for the card's own recap link
    guards a restart re-post. Force (deadline, backfill) sends with whatever champion decks have landed."""
    if manager.trophy_hype_posted:
        return
    event_id = manager.event_id
    resolved = await _resolve_announcement_standings(event_id)
    if resolved is None:
        return
    standings, _ = resolved
    champions = [s for s in standings if s.losses == 0] or [standings[0]]
    deck_data = await asyncio.to_thread(load_event_deck_data_sync, event_id)
    incomplete = incomplete_decks(champions, deck_data)
    if incomplete and not force:
        log.info(
            f"[FINALIZE] trophy_hype.skip event={event_id} reason=awaiting_champion_decks "
            f"missing={incomplete}"
        )
        return
    target = await _resolve_announcement_target(manager)
    guild = getattr(target, "guild", None)
    thread_id = int(manager.thread_id) if isinstance(manager.thread_id, (int, str)) else None
    displays = await asyncio.to_thread(load_participant_displays, event_id)
    dm_info = await asyncio.to_thread(load_dm_info_sync, event_id)
    event_name = await asyncio.to_thread(load_event_name_sync, event_id)
    manager.trophy_hype_posted = True
    posted = await post_trophy_hype(
        event_id, guild, thread_id, champions,
        event_name=event_name, displays=displays,
        player_colors=colors_only(deck_data), deck_data=deck_data, dm_info=dm_info,
    )
    if not posted:
        manager.trophy_hype_posted = False


SCREENSHOT_BACKFILL_HISTORY_LIMIT = 200


async def _react_trophy_on_champion_screenshots(manager, deck_data, dm_info) -> None:
    """Back-fill the 🏆 react on each champion's stored deck screenshot. It usually lands before the
    champion is known, so the live listener can't have reacted to it. Attachment URLs are compared
    without their query string — the CDN signature params rotate between fetches."""
    if not manager.champion_discord_ids:
        return
    thread = await manager._fetch_thread()
    if thread is None:
        return
    wanted_by_author: dict[str, str] = {}
    for key, info in dm_info.items():
        if info.discord_id not in manager.champion_discord_ids:
            continue
        data = deck_data.get(key)
        if data and data.screenshot_url:
            wanted_by_author[str(info.discord_id)] = data.screenshot_url.split("?")[0]
    if not wanted_by_author:
        return
    try:
        async for msg in thread.history(limit=SCREENSHOT_BACKFILL_HISTORY_LIMIT):
            wanted = wanted_by_author.get(str(msg.author.id))
            if wanted is None or wanted not in {att.url.split("?")[0] for att in msg.attachments}:
                continue
            try:
                await msg.add_reaction("🏆")
                log.info(f"[DECK] champion_screenshot_backfill event={manager.event_id} message={msg.id}")
            except discord.HTTPException:
                log.info("could not back-fill 🏆 reaction", exc_info=True)
            wanted_by_author.pop(str(msg.author.id))
            if not wanted_by_author:
                break
    except discord.HTTPException:
        log.warning(f"[FINALIZE] screenshot_backfill.scan_error event={manager.event_id}", exc_info=True)


async def _set_champion_card_result(manager, champions, player_colors) -> None:
    """The champion headline and the jump link both card surfaces show once the podium post is up. The thread
    gets no callout of its own: its Play Again sign-off links the same post, and the thread's own embed
    carries the jump button."""
    announcement = manager.champion_announcement_message
    if announcement is None:
        return
    carded = [
        (f"**{s.player_name}**", player_colors.get(normalize_player_name(s.player_name)))
        for s in champions
    ]
    if not carded:
        return
    manager.card_result_line = f"🏆 {_format_champion_result_line(carded)}"
    manager.card_result_url = announcement.jump_url
    notify_card_phase(manager.bot, manager.event_id)


def build_trophy_hype_view(
    champions, *,
    event_name: str,
    displays: dict[str, dict],
    player_colors: dict[str, str | None],
    deck_data: dict[str, "ParticipantDeckData"],
    guild_id: int | None = None,
    thread_id: int | None = None,
    format_title=None,
    champion_mention: str | None = None,
) -> ui.LayoutView:
    """Champion-only announcement for #trophy-hype: headline, italic deck caption, and the deck
    shot, with Thread + Draft Recap link buttons. A simplified take on the championship post,
    sized to the channel's trophy-screenshot pattern. `format_title(name, colors, short_event)`
    overrides the headline — team pods use it since their 3-0s don't take the pod."""
    short = short_event_name(event_name) or event_name
    if format_title is None:
        def format_title(name, colors, short_event):
            return _format_champion_title([(name, colors)], short_event, champion_mention)
    view = ui.LayoutView()
    container = ui.Container(accent_colour=discord.Color.gold())
    for index, s in enumerate(champions):
        if index:
            container.add_item(ui.Separator())
        key = normalize_player_name(s.player_name)
        data = deck_data.get(key)
        name = (displays.get(key) or {}).get("display_name") or s.player_name
        lines = [f"### {format_title(name, player_colors.get(key), short)}"]
        if data and data.screenshot_caption:
            lines.append(f"*{data.screenshot_caption}*")
        container.add_item(ui.TextDisplay("\n".join(lines)))
        if data and data.screenshot_url:
            container.add_item(ui.MediaGallery(
                discord.MediaGalleryItem(media=data.screenshot_url, description=f"{name}'s deck"),
            ))
    view.add_item(container)
    actions = ui.ActionRow()
    if guild_id and thread_id:
        actions.add_item(build_thread_link_button(guild_id, thread_id))
    actions.add_item(build_replays_link_button(event_name))
    view.add_item(actions)
    return view


async def post_trophy_hype_for_event(bot, event_id: str, guild) -> None:
    """Manager-free #trophy-hype post so /pod-champion fires the same hype card the automatic finalize
    would. Team pods route to the team 3-0 card; regular pods resolve champions from the announcement
    standings."""
    if await asyncio.to_thread(load_event_pairing_mode_sync, event_id) == "team":
        from bot.services.pod_team_showcase import maybe_post_team_trophy_hype

        players = await asyncio.to_thread(load_tournament_players_sync, event_id)
        thread_id_str = await asyncio.to_thread(load_event_thread_id_sync, event_id)
        shim = _RecoveryManager(bot, event_id, int(thread_id_str) if thread_id_str else 0, players, "team")
        await maybe_post_team_trophy_hype(shim)
        return
    resolved = await _resolve_announcement_standings(event_id)
    if resolved is None:
        return
    standings, _ = resolved
    champions = [s for s in standings if s.losses == 0] or [standings[0]]
    deck_data = await asyncio.to_thread(load_event_deck_data_sync, event_id)
    displays = await asyncio.to_thread(load_participant_displays, event_id)
    dm_info = await asyncio.to_thread(load_dm_info_sync, event_id)
    event_name = await asyncio.to_thread(load_event_name_sync, event_id)
    thread_id_str = await asyncio.to_thread(load_event_thread_id_sync, event_id)
    thread_id = int(thread_id_str) if thread_id_str else None
    await post_trophy_hype(
        event_id, guild, thread_id, champions,
        event_name=event_name, displays=displays,
        player_colors=colors_only(deck_data), deck_data=deck_data, dm_info=dm_info,
    )


async def post_trophy_hype(
    event_id: str, guild, thread_id: int | None, champions, *,
    event_name: str,
    displays: dict[str, dict],
    player_colors: dict[str, str | None],
    deck_data: dict[str, "ParticipantDeckData"],
    dm_info: dict,
    format_title=None,
) -> bool:
    """Send the champion hype card. Returns True when handled (sent, or skipped because the card is
    already in the channel / every champion self-posted); False on a recoverable miss (no channel,
    send error) so a later trigger retries."""
    channel = _find_trophy_hype_channel(guild)
    if channel is None:
        log.info(f"[FINALIZE] trophy_hype.skip event={event_id} reason=no_channel")
        return False
    started_at = await asyncio.to_thread(load_event_started_at_sync, event_id)
    recap_url = pod_page_url(event_name)
    self_post_authors, already_posted = await _scan_trophy_hype_channel(channel, started_at, recap_url)
    if already_posted:
        log.info(f"[FINALIZE] trophy_hype.skip event={event_id} reason=already_in_channel")
        return True
    remaining = []
    for standing in champions:
        info = dm_info.get(normalize_player_name(standing.player_name))
        discord_id = info.discord_id if info else None
        if discord_id and discord_id in self_post_authors:
            log.info(
                f"[FINALIZE] trophy_hype.skip_champion event={event_id} "
                f"champion={standing.player_name!r} reason=already_posted"
            )
            continue
        remaining.append(standing)
    if not remaining:
        log.info(f"[FINALIZE] trophy_hype.skip event={event_id} reason=champions_already_posted")
        return True
    hype_view = build_trophy_hype_view(
        remaining, event_name=event_name, displays=displays,
        player_colors=player_colors, deck_data=deck_data,
        guild_id=getattr(guild, "id", None), thread_id=thread_id,
        format_title=format_title,
        champion_mention=champion_role_mention(find_role(guild, SET_CHAMPION_ROLE_NAME)),
    )
    try:
        await channel.send(view=hype_view, allowed_mentions=discord.AllowedMentions.none())
        log.info(f"[FINALIZE] trophy_hype.posted event={event_id} channel={channel.id}")
        return True
    except Exception:
        log.warning(f"[FINALIZE] trophy_hype.post_error event={event_id}", exc_info=True)
        return False


def _find_trophy_hype_channel(guild: discord.Guild | None) -> discord.TextChannel | None:
    if guild is None:
        return None
    return channel_matching_name(guild, settings.pod_draft_trophy_hype_channel_name)


async def _scan_trophy_hype_channel(channel: discord.TextChannel, after, recap_url: str):
    """One pass over the hype channel since the event started, returning (image-poster discord ids,
    card-already-posted). The image posters let a champion who shared their own shot skip a duplicate
    bot post; the flag — any message carrying this event's Draft Recap link — makes the bot's own
    post idempotent across a restart, since only this card links to that pod page."""
    authors: set[str] = set()
    already_posted = False
    try:
        async for message in channel.history(limit=TROPHY_HYPE_HISTORY_LIMIT, after=after):
            if message.attachments or message.embeds:
                authors.add(str(message.author.id))
            if not already_posted and recap_url in _component_link_urls(message.components):
                already_posted = True
    except Exception:
        log.warning("could not scan trophy hype channel history", exc_info=True)
    return authors, already_posted


def _component_link_urls(components) -> list[str]:
    """Every link URL reachable in a message's component tree, walking nested containers/rows."""
    urls = []
    for component in components:
        url = getattr(component, "url", None)
        if url:
            urls.append(url)
        children = getattr(component, "children", None)
        if children:
            urls.extend(_component_link_urls(children))
    return urls


class _RecoveryManager:
    """Manager-less stand-in so maybe_post_championship and _post_or_update_live_standings can run after
    a restart or post-finalize eviction, when the live PodDraftManager is gone. Exposes only what those
    read; backed by the DB row."""

    def __init__(self, bot, event_id: str, thread_id: int, tournament_players: list,
                 pairing_mode: str) -> None:
        self.bot = bot
        self.event_id = event_id
        self.thread_id = thread_id
        self.tournament_players = tournament_players
        self.pairing_mode = pairing_mode
        self.team_map: dict[str, str] | None = None
        self.finalized = True
        self.champion_announced = False
        self.trophy_hype_posted = False
        self.champion_discord_ids: set[str] = set()
        self.champion_announcement_message = None
        self.championship_task = None
        self.deck_nudge_task = None
        self.deck_ping_task = None
        self.current_round = TOTAL_ROUNDS
        self.standings_message = None
        self._standings_post_lock = asyncio.Lock()
        self.round_messages: dict = {}

    async def _fetch_thread(self):
        try:
            return await self.bot.fetch_channel(self.thread_id)
        except Exception:
            log.warning(f"could not fetch thread {self.thread_id}", exc_info=True)
            return None

    async def disconnect_safely(self) -> None:
        return None


def _load_unannounced_finalized_sync() -> list[tuple[str, str, datetime]]:
    """Rows a restart sweep can still announce in, so a pod filed against a placeholder thread id is left out"""
    cutoff = datetime.now(timezone.utc) - CHAMPIONSHIP_RECONCILE_WINDOW
    with SessionLocal() as session:
        rows = session.execute(
            select(
                PodDraftEvent.id,
                PodDraftEvent.discord_thread_id,
                PodDraftEvent.finalized_at,
            ).where(
                PodDraftEvent.finalized_at.is_not(None),
                PodDraftEvent.championship_posted_at.is_(None),
                PodDraftEvent.finalized_at >= cutoff,
            )
        ).all()
        return [(row[0], row[1], row[2]) for row in rows if snowflake_or_none(row[1]) is not None]


def _load_in_progress_tournaments_sync() -> list[dict]:
    """Pod events whose tournament had started (current_round set) but never finalized, within the
    rehydrate window — the rows a restart sweep rebuilds an in-memory manager for."""
    cutoff = datetime.now(timezone.utc) - TOURNAMENT_REHYDRATE_WINDOW
    with SessionLocal() as session:
        rows = session.execute(
            select(
                PodDraftEvent.id,
                PodDraftEvent.draftmancer_session,
                PodDraftEvent.discord_thread_id,
                PodDraftEvent.set_code,
                PodDraftEvent.name,
                PodDraftEvent.pairing_mode,
                PodDraftEvent.seating_mode,
                PodDraftEvent.current_round,
            ).where(
                PodDraftEvent.kind == "tournament",
                PodDraftEvent.finalized_at.is_(None),
                PodDraftEvent.current_round.is_not(None),
                PodDraftEvent.event_time >= cutoff,
            )
        ).all()
    return [dict(row._mapping) for row in rows]


async def rehydrate_active_tournaments(bot) -> None:
    """Startup sweep: rebuild an in-memory manager for any pod whose tournament had started but not
    finalized when the bot last stopped, so round advancement, grace-window locking, and finalize keep
    working after a restart. Result dropdowns survive on their own (persistent views) — this restores
    the manager those handlers look up. The Draftmancer socket is left unconnected: the draft is already
    over by the tournament phase, and reconnecting would re-arm lobby/ready-check side effects."""
    from bot.services.pod_draft_manager import PodDraftManager

    rows = await asyncio.to_thread(_load_in_progress_tournaments_sync)
    restored = 0
    for row in rows:
        event_id = row["id"]
        if event_id in ACTIVE_POD_MANAGERS:
            continue
        players = await asyncio.to_thread(load_tournament_players_sync, event_id)
        if len(players) < 2:
            continue
        manager = PodDraftManager(
            bot, event_id, row["draftmancer_session"], int(row["discord_thread_id"]),
            row["set_code"], len(players), event_name=row["name"],
        )
        manager.tournament_players = players
        manager.pairing_mode = row["pairing_mode"] or "swiss"
        manager.seating_mode = row["seating_mode"] or "random"
        manager.current_round = row["current_round"] or 0
        manager.drafting = False
        manager.draft_complete = True
        thread = await manager._fetch_thread()
        if thread is not None and bot.user is not None:
            manager.round_messages = await _find_pinned_round_messages(thread, bot.user)
            manager.standings_message = await _find_pinned_standings(thread, bot.user, row["name"])
            if manager.pairing_mode == "team":
                from bot.services.pod_team_board import find_reveal_messages

                manager.team_reveal_messages = await find_reveal_messages(thread, bot.user)
        ACTIVE_POD_MANAGERS[event_id] = manager
        restored += 1
        log.info(
            f"[LIFECYCLE] rehydrate.restored event={event_id} round={manager.current_round} "
            f"rounds_found={sorted(manager.round_messages)} pairing={manager.pairing_mode}"
        )
    if restored:
        log.info(f"startup sweep rehydrated {restored} in-progress tournament(s)")


async def post_championship_for_event(
    bot, event_id: str, thread_id: str | int, *, force: bool = True,
) -> bool:
    """Post the championship announcement for a finalized event with no live manager (restart sweep,
    /pod-backfill). Idempotent via the championship_posted_at DB guard. `force` posts with whatever decks
    have landed; pass False to post only once the showcased decks are in, so a restart mid-deck-wait
    doesn't jump the gate."""
    players = await asyncio.to_thread(load_tournament_players_sync, event_id)
    pairing_mode = await asyncio.to_thread(load_event_pairing_mode_sync, event_id)
    shim = _RecoveryManager(bot, event_id, int(thread_id), players, pairing_mode)
    if pairing_mode == "team":
        from bot.services.pod_team_showcase import maybe_post_team_championship

        await maybe_post_team_championship(shim, force=force)
    else:
        await maybe_post_championship(shim, force=force)
    return shim.champion_announced


async def refresh_standings_for_event(bot, event_id: str, thread_id: str | int) -> None:
    """Re-render the pinned Final Standings embed for a finalized event with no live manager, so a late
    deck-color submission still surfaces on the posted standings. Finalize evicts the manager, yet its
    deck-ping invites exactly these late submits. Adopts the pinned message via _post_or_update_live_standings;
    no-op if the roster can't be loaded. Team pods refresh their own embed and run the showcase
    triggers, so a post-eviction deck completing the winning set still posts their championship."""
    players = await asyncio.to_thread(load_tournament_players_sync, event_id)
    if len(players) < 2:
        return
    pairing_mode = await asyncio.to_thread(load_event_pairing_mode_sync, event_id) or "swiss"
    shim = _RecoveryManager(bot, event_id, int(thread_id), players, pairing_mode)
    if pairing_mode == "team":
        from bot.services import pod_team_flow, pod_team_showcase
        from bot.services.pod_team_board import load_team_board_data

        board = await asyncio.to_thread(load_team_board_data, event_id)
        shim.finalized = board.finalized
        await pod_team_flow.refresh_team_standings_embed(shim)
        await pod_team_showcase.maybe_post_team_trophy_hype(shim)
        await pod_team_showcase.maybe_post_team_championship(shim)
        return
    await _post_or_update_live_standings(shim)


async def reconcile_unannounced_championships(bot) -> None:
    """Startup sweep: finish the one-time championship for any recently-finalized pod whose announcement
    never went out (e.g. the bot restarted between finalize and post). A restart still inside the deck-wait
    window re-arms the remaining wait rather than forcing, so the post keeps holding for the showcased
    decks; once the wait has elapsed it posts with whatever landed. Idempotent via the DB guard."""
    rows = await asyncio.to_thread(_load_unannounced_finalized_sync)
    now = datetime.now(timezone.utc)
    posted = 0
    for event_id, thread_id, finalized_at in rows:
        elapsed = (now - finalized_at).total_seconds()
        remaining = CHAMPIONSHIP_DEADLINE_SECONDS - elapsed
        if remaining <= 0:
            if await post_championship_for_event(bot, event_id, thread_id):
                posted += 1
            continue
        await post_championship_for_event(bot, event_id, thread_id, force=False)
        asyncio.create_task(_delayed_championship_post(bot, event_id, thread_id, remaining))
        if elapsed < DECK_PING_DELAY_SECONDS:
            await _rearm_deck_ping(bot, event_id, thread_id, DECK_PING_DELAY_SECONDS - elapsed)
    if posted:
        log.info(f"startup sweep reconciled {posted} unannounced championship(s)")


async def _rearm_deck_ping(bot, event_id: str, thread_id: str | int, delay: float) -> None:
    """A restart inside the deck wait takes the finalize-time ping timer with it, so rebuild a shim and
    hold the rest of the wait. Team pods are left alone: their ping needs the winning side as its
    blocking set, which only the live team flow holds."""
    pairing_mode = await asyncio.to_thread(load_event_pairing_mode_sync, event_id)
    if pairing_mode == "team":
        return
    players = await asyncio.to_thread(load_tournament_players_sync, event_id)
    shim = _RecoveryManager(bot, event_id, int(thread_id), players, pairing_mode)
    schedule_deck_ping(shim, delay=delay)


async def _delayed_championship_post(bot, event_id: str, thread_id: str | int, delay: float) -> None:
    """Re-armed deck-wait deadline after a restart: once the remaining wait elapses, post with whatever
    decks landed. Idempotent via the championship_posted_at guard, so an earlier deck-driven post wins."""
    try:
        await asyncio.sleep(delay)
    except asyncio.CancelledError:
        return
    await post_championship_for_event(bot, event_id, thread_id, force=True)


async def _post_or_update_live_standings(manager) -> None:
    """Post the Final Standings embed once every R3 match is reported, then edit it on later
    corrections or deck-color submissions. It never posts mid-round — the website is the live view.
    No-op for team pods: their rounds are ungated (R3 can close first) and the team flow owns their
    final standings embed."""
    if manager.pairing_mode == "team":
        return
    event_id = manager.event_id
    match_states = await asyncio.to_thread(_load_round_states, event_id, TOTAL_ROUNDS)
    if not match_states:
        return
    mark_trophy_match(match_states, TOTAL_ROUNDS)

    trophy = [m for m in match_states if m.get("is_trophy_match")]
    champion_locked = bool(trophy) and all(m.get("winner_name") for m in trophy)
    if manager.pairing_mode == "bracket":
        pending_count = await asyncio.to_thread(
            bracket_pending_in_round, event_id, TOTAL_ROUNDS, len(manager.tournament_players),
        )
    else:
        pending_count = sum(1 for m in match_states if not m.get("winner_name"))

    if pending_count > 0 and manager.standings_message is None:
        return

    prior = await asyncio.to_thread(load_matches, event_id)
    standings = pod_swiss.compute_standings(manager.tournament_players, prior)
    displays = await asyncio.to_thread(load_participant_displays, event_id)
    event_name = await asyncio.to_thread(load_event_name_sync, event_id)
    deck_data = await asyncio.to_thread(load_event_deck_data_sync, event_id)
    event_has_log = await asyncio.to_thread(_event_has_draft_log_sync, event_id)
    player_colors = colors_only(deck_data)
    embed = build_champion_embed(
        standings,
        event_name=event_name,
        displays=displays,
        player_colors=player_colors,
        leaderboard_url=settings.leaderboard_url,
        champion_locked=champion_locked,
        pending_count=pending_count,
        deck_data=deck_data,
        event_has_log=event_has_log,
        match_states=match_states,
    )

    async with manager._standings_post_lock:
        if manager.standings_message is None:
            thread = await manager._fetch_thread()
            if thread is None:
                return
            adopted = await _find_pinned_standings(thread, manager.bot.user, event_name)
            if adopted is not None:
                manager.standings_message = adopted
            else:
                view = ui.View(timeout=None)
                view.add_item(build_replays_link_button(event_name))
                try:
                    manager.standings_message = await thread.send(embed=embed, view=view)
                except Exception:
                    log.warning("could not post live standings", exc_info=True)
                    return
                try:
                    await manager.standings_message.pin(reason="pod-draft live standings")
                except discord.HTTPException:
                    log.warning(f"could not pin standings message {manager.standings_message.id}", exc_info=True)
            await _attach_round_link(manager, TOTAL_ROUNDS)
            if adopted is None:
                return
    try:
        await manager.standings_message.edit(embed=embed)
    except Exception:
        log.warning("could not edit live standings", exc_info=True)


async def _find_pinned_standings(thread, bot_user, event_name: str) -> discord.Message | None:
    """Rediscover a standings message pinned by an earlier manager (pre-restart) so the embed is
    edited in place instead of posting — and pinning — a duplicate."""
    try:
        pins = await thread.pins()
    except discord.HTTPException:
        log.warning("could not fetch pins to rediscover standings", exc_info=True)
        return None
    for msg in pins:
        if bot_user is not None and msg.author.id != bot_user.id:
            continue
        for pinned_embed in msg.embeds:
            body = pinned_embed.description or ""
            if event_name in body and "Standings" in body:
                return msg
    return None


async def _find_pinned_round_messages(thread, bot_user) -> dict[int, discord.Message]:
    """Rediscover round-pairings messages pinned by an earlier manager (pre-restart), keyed by round
    number parsed from the embed title, so a rehydrated tournament can edit and lock prior rounds in
    place instead of losing the references on restart."""
    try:
        pins = await thread.pins()
    except discord.HTTPException:
        log.warning("could not fetch pins to rediscover round messages", exc_info=True)
        return {}
    found: dict[int, discord.Message] = {}
    for msg in pins:
        if bot_user is not None and msg.author.id != bot_user.id:
            continue
        for embed in msg.embeds:
            match = _ROUND_TITLE_RE.search(embed.title or "")
            if match is None:
                continue
            round_num = int(match.group(1))
            found.setdefault(round_num, msg)
            break
    return found


async def _pin_round_message(message: discord.Message, round_num: int) -> None:
    """Pin a round-pairings message to the thread; silent on Forbidden / HTTPException."""
    try:
        await message.pin(reason=f"pod-draft round {round_num} pairings")
    except discord.HTTPException:
        log.warning(f"could not pin round {round_num} message {message.id}", exc_info=True)


async def pin_only_this_bot_message(message: discord.Message) -> None:
    """Pin `message`, first unpinning any prior pins authored by the same bot in this channel.
    Keeps only one bot pin live so subsequent standings posts (or testlobby reruns) replace the
    prior one cleanly. Silent on Forbidden / HTTPException."""
    bot_user_id = message.author.id
    try:
        pins = await message.channel.pins()
    except discord.HTTPException:
        log.warning("could not fetch pins for %s", message.channel.id, exc_info=True)
        return
    for pin in pins:
        if pin.author.id == bot_user_id and pin.id != message.id:
            try:
                await pin.unpin(reason="rotating pod-draft standings pin")
            except discord.HTTPException:
                log.info("could not unpin %s", pin.id, exc_info=True)
    try:
        await message.pin(reason="latest pod-draft standings")
    except discord.HTTPException:
        log.warning("could not pin standings message %s", message.id, exc_info=True)


def mark_trophy_match(match_states: list[dict], round_num: int) -> None:
    """Stamp is_trophy_match on every final-round pairing where at least one player is genuinely
    undefeated: every prior round played AND every one of them won.

    Skipped matches (winner = SKIPPED_SENTINEL) leave the player with fewer games played, so a
    1-0 entering R3 (one win, one skip) is NOT a trophy contender even though losses == 0.
    """
    if round_num != TOTAL_ROUNDS:
        return

    def _wl(record: str | None) -> tuple[int, int] | None:
        if not record or "-" not in record:
            return None
        try:
            wins, losses = record.split("-", 1)
            return int(wins), int(losses)
        except ValueError:
            return None

    expected_wins = round_num - 1
    for m in match_states:
        a = _wl(m.get("a_record"))
        b = _wl(m.get("b_record"))
        if (a and a == (expected_wins, 0)) or (b and b == (expected_wins, 0)):
            m["is_trophy_match"] = True


def _state_for_pending(match_id: str, a_name: str, b_name: str, standings_by_id,
                       displays: dict[str, dict] | None = None) -> dict:
    a_s = standings_by_id.get(a_name)
    b_s = standings_by_id.get(b_name)
    displays = displays or {}
    a_info = displays.get(normalize_player_name(a_name), {})
    b_info = displays.get(normalize_player_name(b_name), {})
    return {
        "match_id": match_id,
        "a_name": a_name,
        "b_name": b_name,
        "a_display": a_info.get("display_name") or a_name,
        "b_display": b_info.get("display_name") or b_name,
        "a_arena": a_info.get("arena"),
        "b_arena": b_info.get("arena"),
        "a_record": f"{a_s.wins}-{a_s.losses}" if a_s else "0-0",
        "b_record": f"{b_s.wins}-{b_s.losses}" if b_s else "0-0",
        "winner_name": None,
        "score": None,
    }


def _parse_wl(record: str | None) -> tuple[int, int]:
    if record and "-" in record:
        try:
            wins, losses = record.split("-", 1)
            return int(wins), int(losses)
        except ValueError:
            pass
    return (0, 0)


def _arena_matches_display(arena: str, display: str | None) -> bool:
    """Whether the Arena handle and Discord display name are the same identity — equal base, or one a
    prefix of the other (e.g. 'Marlo' ~ 'Marlo#08011', 'driftwood' ~ 'driftwood60'). Drives whether
    a pairing needs to show both names or can lead with the Arena handle alone."""
    base = arena.split("#", 1)[0].strip().lower()
    name = (display or "").strip().lower()
    if not name or not base:
        return True
    return base == name or base.startswith(name) or name.startswith(base)


def name_with_arena(display: str, arena: str | None) -> str:
    """Pairing label: lead with the Draftmancer Arena handle so opponents can find each other in-client,
    appending the Discord name only when it diverges from the handle (e.g. '`driftwood#49190` (Marlo)')."""
    if not arena:
        return display
    if _arena_matches_display(arena, display):
        return f"`{arena}`"
    return f"`{arena}` ({display})"


def match_displays(m: dict) -> tuple[str, str]:
    """Both players of a match state as they should be shown, Discord display preferred over handle."""
    return m.get("a_display") or m["a_name"], m.get("b_display") or m["b_name"]


def format_reported_result(m: dict) -> str:
    """A reported match as plain text, display names preferred: 'Marlo wins 2-1 vs Bob'. A match won
    without playing it reads 'Marlo wins vs Bob (bye)', or 'Marlo wins (bye)' where an odd field left
    no opponent at all. Shared by the round-results list and the live per-result announcement so their
    wording can't drift."""
    a_disp, b_disp = match_displays(m)
    if m["winner_name"].lower() == m["a_name"].lower():
        winner_disp, loser_disp = a_disp, b_disp
    else:
        winner_disp, loser_disp = b_disp, a_disp
    if m["score"] == BYE_SCORE:
        if m["a_name"] == BYE_NAME or m["b_name"] == BYE_NAME:
            return f"{winner_disp} wins (bye)"
        return f"{winner_disp} wins vs {loser_disp} (bye)"
    return f"{winner_disp} wins {m['score']} vs {loser_disp}"


def round_link_target(round_num: int, pairings_url: str | None = None) -> str:
    """Unbolded round label, linked to that round's pairings message and underlined to signal the link
    when the URL is known ('[__Round 2__](url)'). Callers that lead with more than the round bold the
    whole lead around it."""
    if pairings_url:
        return f"[__Round {round_num}__]({pairings_url})"
    return f"Round {round_num}"


def round_link_label(round_num: int, pairings_url: str | None = None) -> str:
    """Bold round label ('**[__Round 2__](url)**'). Shared by the per-result announcement and the
    waiting-slot footer so their round labels can't drift."""
    return f"**{round_link_target(round_num, pairings_url)}**"


def win_completes_trophy(m: dict, round_num: int) -> bool:
    """Whether this result takes the winner to 3-0, records on a match state being as of round start"""
    winner = m.get("winner_name")
    if round_num != TOTAL_ROUNDS or not winner or winner == SKIPPED_SENTINEL:
        return False
    if normalize_player_name(winner) == normalize_player_name(m.get("a_name") or ""):
        record = m.get("a_record")
    else:
        record = m.get("b_record")
    return _parse_wl(record) == (round_num - 1, 0)


def format_round_announcement(round_num: int, m: dict, pairings_url: str | None = None,
                              *, corrected: bool = False) -> str:
    """The per-result thread announcement, round-labelled: '**[__Round 2__]** Marlo wins 2-1 vs Bob',
    with a 🏆 in front of a win that completes a 3-0.

    A `corrected` result is marked as one, so overwriting a reported match reads as a fix to the round
    rather than as a second match played in it.
    """
    phrase = format_reported_result(m)
    if win_completes_trophy(m, round_num):
        phrase = f"🏆 {phrase}"
    if corrected:
        return format_round_change(round_num, phrase, pairings_url)
    return f"{round_link_label(round_num, pairings_url)} {phrase}"


def format_round_change(round_num: int, phrase: str, pairings_url: str | None = None,
                        lead: str = RESULT_CORRECTED_LEAD) -> str:
    """A change to an already-reported round as one line: '♻️ **[__Round 2__] Result corrected:** Marlo
    wins 2-1 vs Bob'. Also the head a bracket re-pair note continues from, so a correction that moves
    later pairings stays one message."""
    return f"♻️ **{round_link_target(round_num, pairings_url)} {lead}** {phrase}"


def format_round_clear_announcement(round_num: int, m: dict, pairings_url: str | None = None) -> str:
    """The thread note when a reported result is cleared, so a round never loses a result silently."""
    a_disp, b_disp = match_displays(m)
    return format_round_change(round_num, f"{a_disp} vs {b_disp}", pairings_url, RESULT_CLEARED_LEAD)


def _match_line(m: dict, *, seat_label: str | None = None, show_arena: bool = False) -> str:
    """One pairing line: result once reported, otherwise the matchup. Pending cross-record matches
    show inline records with the higher record first; same-record matches lean on the group header.
    `show_arena` leads each unreported matchup with the players' Arena handles."""
    a_disp, b_disp = match_displays(m)
    winner = m["winner_name"]
    if winner == SKIPPED_SENTINEL:
        return f"🚫{NBSP}{NBSP}Not played: {a_disp} vs {b_disp}"
    if winner:
        return f"▫️{NBSP}{NBSP}{format_reported_result(m)}"
    if show_arena:
        a_disp = name_with_arena(a_disp, m.get("a_arena"))
        b_disp = name_with_arena(b_disp, m.get("b_arena"))
    if seat_label:
        return f"⚔️{NBSP}{NBSP}{a_disp} vs {b_disp} {seat_label}"
    a_wl, b_wl = _parse_wl(m["a_record"]), _parse_wl(m["b_record"])
    if a_wl != b_wl:
        if (b_wl[0], -b_wl[1]) > (a_wl[0], -a_wl[1]):
            a_disp, b_disp, a_wl, b_wl = b_disp, a_disp, b_wl, a_wl
        return f"⚔️{NBSP}{NBSP}{a_disp} ({a_wl[0]}-{a_wl[1]}) vs {b_disp} ({b_wl[0]}-{b_wl[1]})"
    return f"⚔️{NBSP}{NBSP}{a_disp} vs {b_disp}"


def _round1_lines(match_states: list[dict], seated: bool) -> list[str]:
    lines: list[str] = []
    for m in match_states:
        label = None
        if seated:
            lo, hi = sorted((m["a_seat"], m["b_seat"]))
            label = f"({lo}v{hi})"
        lines.append(_match_line(m, seat_label=label, show_arena=True))
    return lines


REPORT_NOTICE = f"🎯{NBSP}{NBSP}Opponent DM'd. Use `/report-results` or the menu below after your match"
DECK_IMAGE_NOTICE = f"🚨{NBSP}{NBSP}Change your MTGA deck image before you play, or it leaks your P1P1"


def _round_notice_lines(round_num: int, match_states: list[dict]) -> list[str]:
    """Report prompt + P1P1 deck-image warning, round 1 only, while a real match is still unreported."""
    if round_num != 1:
        return []
    reportable = any(not m.get("placeholder") and not m.get("winner_name") for m in match_states)
    if not reportable:
        return []
    return ["", REPORT_NOTICE, DECK_IMAGE_NOTICE]


def round_groups(round_num: int, match_states: list[dict]) -> list[tuple[str, list[dict]]]:
    """Ordered (group_kind, matches) for a round — the presentation-free data model. Intermediate
    rounds split into WINNERS → PAIR_UP → LOSERS; the final round into TROPHY → MIDDLE → LAST_CHANCE."""
    return _final_round_groups(match_states) if round_num >= TOTAL_ROUNDS else _swiss_round_groups(match_states)


def _swiss_round_groups(match_states: list[dict]) -> list[tuple[str, list[dict]]]:
    same: dict[tuple[int, int], list[dict]] = {}
    pairups: list[dict] = []
    undecided: list[dict] = []
    for m in match_states:
        if m["a_record"] is None or m["b_record"] is None:
            undecided.append(m)
        elif _parse_wl(m["a_record"]) == _parse_wl(m["b_record"]):
            same.setdefault(_parse_wl(m["a_record"]), []).append(m)
        else:
            pairups.append(m)
    ranked = sorted(same, key=lambda r: (-r[0], r[1]))
    groups: list[tuple[str, list[dict]]] = [
        (WINNERS if idx == 0 else LOSERS, same[rec]) for idx, rec in enumerate(ranked)
    ]
    if pairups:
        groups.insert(1 if groups else 0, (PAIR_UP, pairups))
    if undecided:
        groups.append((UNDECIDED, undecided))
    return groups


def _final_round_groups(match_states: list[dict]) -> list[tuple[str, list[dict]]]:
    """Trophy first, then the even 1-1 matches, then anyone playing across records, then the pair with
    no win between them. A match across records is its own group: filing a 1-1 against a 0-2 under the
    1-1 header reads as an even match and misnames the 0-2 player's round."""
    trophy: list[dict] = []
    middle: list[dict] = []
    pairups: list[dict] = []
    last_chance: list[dict] = []
    undecided: list[dict] = []
    for m in match_states:
        if m.get("is_trophy_match"):
            trophy.append(m)
        elif m["a_record"] is None or m["b_record"] is None:
            undecided.append(m)
        elif _parse_wl(m["a_record"]) != _parse_wl(m["b_record"]):
            pairups.append(m)
        elif _parse_wl(m["a_record"])[0] == 0:
            last_chance.append(m)
        else:
            middle.append(m)
    named = ((TROPHY, trophy), (MIDDLE, middle), (PAIR_UP, pairups),
             (LAST_CHANCE, last_chance), (UNDECIDED, undecided))
    return [(kind, matches) for kind, matches in named if matches]


_GROUP_EMOJI = {
    WINNERS: "⬆️", LOSERS: "⬇️", PAIR_UP: "🌉",
    TROPHY: "🏆", MIDDLE: "⚖️", LAST_CHANCE: "🎯", UNDECIDED: "⏳",
}
_GROUP_LABEL = {PAIR_UP: "Pair Up", TROPHY: "Trophy", MIDDLE: "1-1", LAST_CHANCE: "Last Chance",
                UNDECIDED: "Waiting"}


def _grouped_lines(round_num: int, match_states: list[dict]) -> list[str]:
    lines: list[str] = []
    for i, (kind, matches) in enumerate(round_groups(round_num, match_states)):
        if i:
            lines.append("")
        label = _GROUP_LABEL.get(kind) or "{}-{}".format(*_parse_wl(matches[0]["a_record"]))
        word = "Match" if len(matches) == 1 else "Matches"
        lines.append(f"{_GROUP_EMOJI[kind]}{NBSP}{NBSP}**{label} {word}**")
        for m in matches:
            if m.get("placeholder"):
                label = m.get("label") or ""
                lines.append(f"⏳{NBSP}{NBSP}{label}" if label else "⏳")
            else:
                lines.append(_match_line(m, show_arena=True))
    return lines


def _waiting_footer_line(match_states: list[dict]) -> str | None:
    """Subtext hint under a partial bracket round naming how many of the previous round's matches are
    still unreported before the waiting slots pair up, linking to that round when its URL is known."""
    for m in match_states:
        pending = m.get("waiting_pending") if m.get("placeholder") else None
        if not pending:
            continue
        noun = "Match" if pending == 1 else "Matches"
        link = round_link_label(m["waiting_prev_round"], m.get("waiting_prev_url"))
        return f"⏱️ **{pending}** {noun} Remaining in {link}"
    return None


def round_embed(round_num: int, match_states: list[dict]) -> discord.Embed:
    all_done = all(m["winner_name"] for m in match_states)
    if round_num == 1:
        seated = bool(match_states) and all(m.get("a_seat") and m.get("b_seat") for m in match_states)
        title = round_header(round_num, all_done, seated=seated)
        lines = _round1_lines(match_states, seated)
    else:
        # Rounds 2+ group by record (1-0/0-1, then Trophy/1-1/Last Chance), waiting slots included
        title = round_header(round_num, all_done)
        lines = _grouped_lines(round_num, match_states)
    lines = lines + _round_notice_lines(round_num, match_states)
    footer = _waiting_footer_line(match_states)
    if footer is not None:
        lines = lines + ["", footer]
    return discord.Embed(
        title=title,
        description="\n".join(lines),
        color=discord.Color.green(),
    )


def load_seat_indexes(event_id: str) -> dict[str, int]:
    """Map normalized draftmancer_name → seat_index for participants whose seat is known."""
    with SessionLocal() as session:
        rows = session.execute(
            select(PodDraftParticipant.draftmancer_name, PodDraftParticipant.seat_index)
            .where(
                PodDraftParticipant.event_id == event_id,
                PodDraftParticipant.seat_index.is_not(None),
            )
        ).all()
    return {normalize_player_name(name): idx for name, idx in rows if name}


def _attach_seats(match_states: list[dict], seats: dict[str, int]) -> None:
    """Stamp 1-based seat numbers onto round-1 states so the embed can label '(1v5)' and title 'by
    Seats'. Missing seats stay None, which renders the round as '(Random)'."""
    for m in match_states:
        a = seats.get(normalize_player_name(m["a_name"]))
        b = seats.get(normalize_player_name(m["b_name"]))
        m["a_seat"] = a + 1 if a is not None else None
        m["b_seat"] = b + 1 if b is not None else None


def load_matches(event_id: str) -> list[MatchOutcome]:
    """Loads played matches only — skipped/no-match-played rows are excluded from standings."""
    with SessionLocal() as session:
        rows = session.execute(
            select(PodDraftMatch)
            .where(
                PodDraftMatch.event_id == event_id,
                PodDraftMatch.winner_name.is_not(None),
                PodDraftMatch.winner_name != SKIPPED_SENTINEL,
            )
            .order_by(PodDraftMatch.round, PodDraftMatch.reported_at)
        ).scalars().all()
        return [
            MatchOutcome(
                round_num=r.round,
                player_a_id=r.player_a_name,
                player_b_id=r.player_b_name,
                winner_id=r.winner_name,
                score=r.score or "2-0",
            )
            for r in rows
        ]


def insert_pending_matches(
    event_id: str, round_num: int, pairings: list[tuple[str, str]], start_index: int = 0,
) -> list[tuple[str, str, str]]:
    """Insert pending match rows for a round and bump the event's current_round. `start_index` lets
    the bracket pairer append to a round already partly posted without colliding pairing_index;
    current_round only ever advances so several open bracket rounds don't make it thrash backwards.

    A pairing that reaches a dropped player is reported here as it is created, so no round ever opens
    holding a match nobody can play."""
    out: list[tuple[str, str, str]] = []
    with SessionLocal() as session:
        dropped = dropped_names_sync(session, event_id)
        for idx, (a_name, b_name) in enumerate(pairings):
            row = add_pairing(session, event_id, round_num, a_name, b_name, pairing_index=start_index + idx)
            forfeit_unplayable_match(session, row, dropped)
            out.append((row.id, a_name, b_name))
        session.execute(
            update(PodDraftEvent)
            .where(PodDraftEvent.id == event_id)
            .values(current_round=func.greatest(func.coalesce(PodDraftEvent.current_round, 0), round_num))
        )
        session.commit()
    return out


def load_dropped_names(event_id: str) -> set[str]:
    with SessionLocal() as session:
        return dropped_names_sync(session, event_id)


def dropped_names_sync(session: Session, event_id: str) -> set[str]:
    """Normalized draftmancer names of everyone an organizer has dropped from this pod"""
    rows = session.execute(
        select(PodDraftParticipant.draftmancer_name).where(
            PodDraftParticipant.event_id == event_id,
            PodDraftParticipant.dropped_round.is_not(None),
        )
    ).scalars().all()
    return {normalize_player_name(name) for name in rows if name}


def forfeit_unplayable_match(session: Session, match: PodDraftMatch, dropped: set[str]) -> str | None:
    """Report a match that can't be played: a bye for whoever is still in, or no match at all when both
    sides are gone. Returns the winner written, or None when the match is playable."""
    a_gone = normalize_player_name(match.player_a_name) in dropped or match.player_a_name == BYE_NAME
    b_gone = normalize_player_name(match.player_b_name) in dropped or match.player_b_name == BYE_NAME
    if not a_gone and not b_gone:
        return None
    if a_gone and b_gone:
        winner, score = SKIPPED_SENTINEL, "0-0"
    else:
        winner, score = (match.player_b_name, BYE_SCORE) if a_gone else (match.player_a_name, BYE_SCORE)
    set_match_result(session, match.id, winner, score)
    return winner


def stamp_reported_byes(event_id: str, round_num: int, match_states: list[dict]) -> None:
    """Fill winner/score on the states whose row was forfeited as it was inserted, so a round posts
    showing the bye already reported instead of offering a dropdown for it."""
    reported = auto_reported_results_sync(event_id, [m["match_id"] for m in match_states if m.get("match_id")])
    for m in match_states:
        result = reported.get(m.get("match_id"))
        if result is not None:
            m["winner_name"], m["score"] = result


def auto_reported_results_sync(event_id: str, match_ids: list[str]) -> dict[str, tuple[str, str]]:
    """{match_id: (winner_name, score)} for rows that were forfeited as they were created, so they
    carry a result before anyone has had the chance to report one."""
    if not match_ids:
        return {}
    with SessionLocal() as session:
        rows = session.execute(
            select(PodDraftMatch.id, PodDraftMatch.winner_name, PodDraftMatch.score).where(
                PodDraftMatch.event_id == event_id,
                PodDraftMatch.id.in_(match_ids),
                PodDraftMatch.winner_name.is_not(None),
            )
        ).all()
    return {match_id: (winner, score) for match_id, winner, score in rows}


def forfeited_rounds_sync(event_id: str, match_ids: list[str]) -> dict[int, list[str]]:
    """Match ids grouped by the round they sit in, so a drop that reaches several open rounds settles
    each of them."""
    if not match_ids:
        return {}
    with SessionLocal() as session:
        rows = session.execute(
            select(PodDraftMatch.round, PodDraftMatch.id).where(
                PodDraftMatch.event_id == event_id,
                PodDraftMatch.id.in_(match_ids),
            )
        ).all()
    by_round: dict[int, list[str]] = {}
    for round_num, match_id in rows:
        by_round.setdefault(round_num, []).append(match_id)
    return by_round


async def settle_auto_forfeits(bot_client, event_id: str, match_ids: list[str]) -> None:
    """Announce each pairing forfeited to a bye as it was created, then re-check its round for
    advancement — a bye can be the result that completes a round, and nobody clicks to report one."""
    forfeited = await asyncio.to_thread(auto_reported_results_sync, event_id, match_ids)
    if not forfeited:
        return
    for round_num, round_ids in (await asyncio.to_thread(
        forfeited_rounds_sync, event_id, list(forfeited),
    )).items():
        states = await asyncio.to_thread(_load_round_states, event_id, round_num)
        pairings_url = await asyncio.to_thread(_resolve_pairings_url, event_id, round_num)
        for state in states:
            if state["match_id"] in round_ids and match_was_played(state):
                await announce_round_result(
                    bot_client, event_id, format_round_announcement(round_num, state, pairings_url),
                )
        asyncio.create_task(_maybe_advance(bot_client, event_id, round_num))


def _load_pod_player_names(event_id: str) -> list[str]:
    """Full roster names, read from round-1 matches where everyone is paired. A bye placeholder is not
    a player and never joins the roster."""
    with SessionLocal() as session:
        rows = session.execute(
            select(PodDraftMatch.player_a_name, PodDraftMatch.player_b_name)
            .where(PodDraftMatch.event_id == event_id, PodDraftMatch.round == 1)
        ).all()
    return sorted({n for a, b in rows for n in (a, b) if n != BYE_NAME})


def bracket_placeholder_states(event_id: str, round_num: int, real: list[dict] | None = None) -> list[dict]:
    """Waiting-match states padding a bracket round to its full slate, so the round always renders one
    dropdown per match it will hold. A known waiting player is named ('Alice vs 1-0'); a slot with no
    known side reads 'waiting on Round N' in the embed (the record comes from the group header) and
    '1-1 Match waiting on Round N' in the dropdown (no header there). A slot whose records the
    projection can't yet fix carries none and reads as waiting on both. Each state carries the
    previous round's still-unreported count so the embed can footer 'how many matches remain before
    these pairings are set'. `real` is this round's reportable matches."""
    if round_num < 2:
        return []
    if real is None:
        real = _load_round_states(event_id, round_num)
    real_pairs = [(_parse_wl(m["a_record"]), _parse_wl(m["b_record"])) for m in real]
    paired = [n for m in real for n in (m["a_name"], m["b_name"])]
    players = [Player(id=n, name=n) for n in _load_pod_player_names(event_id)]
    completed = load_matches(event_id)
    displays = load_participant_displays(event_id)
    prev_round = round_num - 1
    prev_pending = bracket_pending_in_round(event_id, prev_round, len(players))
    prev_url = _resolve_pairings_url(event_id, prev_round)

    def disp(name: str) -> str:
        return displays.get(normalize_player_name(name), {}).get("display_name") or name

    out: list[dict] = []
    for record_a, record_b, a, b in pod_bracket.padding_slots(
        players, completed, real_pairs, paired, round_num,
    ):
        rec_a = _format_wl(record_a)
        rec_b = _format_wl(record_b)
        if a and b:
            label = dropdown_label = f"{disp(a)} vs {disp(b)}"
        elif a:
            label = dropdown_label = f"{disp(a)} vs {rec_b}"
        elif b:
            label = dropdown_label = f"{rec_a} vs {disp(b)}"
        else:
            label = f"waiting on Round {prev_round}"
            dropdown_label = f"{_slot_record_label(rec_a, rec_b)} waiting on Round {prev_round}"
        out.append({
            "placeholder": True,
            "label": label,
            "dropdown_label": dropdown_label,
            "waiting_prev_round": prev_round,
            "waiting_pending": prev_pending,
            "waiting_prev_url": prev_url,
            "a_record": rec_a,
            "b_record": rec_b,
            "winner_name": None,
            "score": None,
        })
    return out


def _format_wl(record: tuple[int, int] | None) -> str | None:
    return None if record is None else "{}-{}".format(*record)


def _slot_record_label(rec_a: str | None, rec_b: str | None) -> str:
    """How a waiting slot names itself where no group header carries its record: '1-1 Match', or
    '1-1 vs 0-2 Match' when the two sides come from different records. Empty while the projection
    can't yet say which records the slot holds."""
    if rec_a is None or rec_b is None:
        return "Match"
    if rec_a == rec_b:
        return f"{rec_a} Match"
    return f"{rec_a} vs {rec_b} Match"


def load_bracket_round_states(event_id: str, round_num: int) -> list[dict]:
    """Full ordered slate for a bracket round: reportable matches first, then waiting-on placeholders.
    Round 1 (and any not-yet-projectable round) is just the real matches."""
    real = _load_round_states(event_id, round_num)
    locked = round_num < TOTAL_ROUNDS and _later_round_reported(event_id, round_num)
    for m in real:
        m["allow_skip"] = round_num == TOTAL_ROUNDS
        m["locked"] = locked and bool(m.get("winner_name"))
    if round_num < 2:
        return real
    display = real + bracket_placeholder_states(event_id, round_num, real)
    mark_trophy_match(display, round_num)
    return display


def _later_round_reported(event_id: str, round_num: int) -> bool:
    """True if any round after round_num has a reported result — the point at which edits to this
    round are blocked, so its reported dropdowns should render locked."""
    with SessionLocal() as session:
        return session.execute(
            select(func.count(PodDraftMatch.id)).where(
                PodDraftMatch.event_id == event_id,
                PodDraftMatch.round > round_num,
                PodDraftMatch.winner_name.is_not(None),
            )
        ).scalar_one() > 0


def render_round_states(event_id: str, round_num: int, *, bracket: bool) -> list[dict]:
    """Trophy-marked match states for rendering a round message. Bracket mode appends the
    waiting-on placeholders; Swiss returns just the real matches. The one place mode decides which
    slate a thread/DM edit shows."""
    if bracket:
        return load_bracket_round_states(event_id, round_num)
    states = _load_round_states(event_id, round_num)
    mark_trophy_match(states, round_num)
    return states


def bracket_pending_in_round(event_id: str, round_num: int, roster_size: int) -> int:
    """Outstanding matches in an incrementally-built bracket round: roster/2 minus those reported,
    rather than the count of rows that happen to exist right now."""
    with SessionLocal() as session:
        reported = session.execute(
            select(func.count(PodDraftMatch.id)).where(
                PodDraftMatch.event_id == event_id,
                PodDraftMatch.round == round_num,
                PodDraftMatch.winner_name.is_not(None),
            )
        ).scalar_one()
    return max(roster_size // 2 - reported, 0)


def event_result_locked(match_id: str) -> bool:
    """True once the match's event is finalized. Results freeze at finalization so a stale DM dropdown
    can't rewrite a recorded result. Survives a restart (derived from the persisted finalized_at)."""
    with SessionLocal() as session:
        finalized_at = session.execute(
            select(PodDraftEvent.finalized_at)
            .join(PodDraftMatch, PodDraftMatch.event_id == PodDraftEvent.id)
            .where(PodDraftMatch.id == match_id)
        ).scalar_one_or_none()
    return finalized_at is not None


def bracket_edit_blocked(match_id: str) -> bool:
    """Block editing an already-reported bracket result in a non-final round once a later round has
    reported a result — regenerating downstream then would void a match someone already played.
    Swiss matches are never blocked here. Survives a restart (derived from persisted rows)."""
    with SessionLocal() as session:
        row = session.execute(
            select(PodDraftMatch.round, PodDraftMatch.reported_at,
                   PodDraftMatch.event_id, PodDraftEvent.pairing_mode)
            .join(PodDraftEvent, PodDraftEvent.id == PodDraftMatch.event_id)
            .where(PodDraftMatch.id == match_id)
        ).first()
        if row is None:
            return False
        rnd, reported_at, event_id, mode = row
        if mode != "bracket" or reported_at is None or rnd >= TOTAL_ROUNDS:
            return False
        downstream = session.execute(
            select(func.count(PodDraftMatch.id)).where(
                PodDraftMatch.event_id == event_id,
                PodDraftMatch.round > rnd,
                PodDraftMatch.winner_name.is_not(None),
            )
        ).scalar_one()
    return downstream > 0


async def bracket_advance(manager, source_round: int, *, announce_fill: bool = True,
                          reuse_dms: dict[tuple[int, str], tuple[str, str]] | None = None) -> None:
    """Fast-advance: after a result in source_round, append whatever target-round pairings the new
    records now allow and grow the target round's message in place. Posts the target round the first
    time it has a real pairing — never an all-placeholder slate. The 2-0 trophy match opens the
    moment both 2-0 players exist. Re-pair-on-edit (the Swiss grace regenerate) isn't supported.

    When later matches lock into an already-posted round, a thread note names them so the other-half
    fill reads as an event rather than the message silently changing. `announce_fill` is False during
    the edit-driven regenerate, which posts its own corrected-pairings note, and `reuse_dms` lets it
    rewrite the pairing DMs it already sent instead of sending a second set."""
    if source_round >= TOTAL_ROUNDS:
        return
    event_id = manager.event_id
    target = source_round + 1
    players = manager.tournament_players

    outcomes = await asyncio.to_thread(load_matches, event_id)
    existing = await asyncio.to_thread(_load_pairings_for_round, event_id, target)
    new = pod_bracket.incremental_pairings(
        players, outcomes, existing, target,
        source_round_complete=await _round_fully_reported(manager, source_round),
    )
    new_rows: list[tuple[str, str, str]] = []
    if new:
        new_rows = await asyncio.to_thread(insert_pending_matches, event_id, target, new, len(existing))
        manager.current_round = max(manager.current_round, target)

    target_msg = manager.round_messages.get(target)
    was_posted = target_msg is not None
    if target_msg is None and not new_rows and not existing:
        return

    display = await asyncio.to_thread(load_bracket_round_states, event_id, target)
    if not display:
        return
    embed = round_embed(target, display)
    url, label = _round_nav_link(manager, target)
    view = RoundResultsView(display, round_num=target, link_url=url, link_label=label)

    if target_msg is None:
        thread = await manager._fetch_thread()
        if thread is None:
            return
        try:
            target_msg = await thread.send(embed=embed, view=view)
        except Exception:
            log.warning(f"could not post bracket round {target}", exc_info=True)
            return
        manager.round_messages[target] = target_msg
        await _pin_round_message(target_msg, target)
        await _attach_round_link(manager, source_round)
        await persist_round_entry_artifacts(manager, target)
    else:
        try:
            await target_msg.edit(content=None, embed=embed, view=view)
        except Exception:
            log.warning(f"could not edit bracket round {target}", exc_info=True)

    if new_rows:
        await _dm_round_pairings(manager.bot, event_id, target, new_rows, target_msg.jump_url, reuse_dms)
        if was_posted and announce_fill:
            await _announce_bracket_fill(manager, target, new_rows, target_msg.jump_url)
        await settle_auto_forfeits(manager.bot, event_id, [mid for mid, _, _ in new_rows])


async def _round_fully_reported(manager, round_num: int) -> bool:
    """Whether every match of the round is paired and reported. The pairer only forces a rematch out of
    a group it can't pair cleanly once the source round is settled, so this gates that fallback."""
    states = await asyncio.to_thread(_load_round_states, manager.event_id, round_num)
    return (
        len(states) == (len(manager.tournament_players) + 1) // 2
        and all(m["winner_name"] for m in states)
    )


def bracket_fill_notice(round_num: int, matchups: list[tuple[str, str]], url: str | None) -> str:
    """Thread note when the fast bracket fills previously-pending slots in an already-posted round, so
    the other-half matches read as newly set rather than the message changing silently."""
    pairings = ", ".join(f"{a} vs {b}" for a, b in matchups)
    link = f"[__Round {round_num} Pairings__]({url})" if url else f"Round {round_num} Pairings"
    return f"**{link}** {pairings}"


async def _announce_bracket_fill(manager, round_num: int, new_rows: list[tuple[str, str, str]], url: str) -> None:
    thread = await manager._fetch_thread()
    if thread is None:
        return
    displays = await asyncio.to_thread(load_participant_displays, manager.event_id)

    def disp(name: str) -> str:
        return displays.get(normalize_player_name(name), {}).get("display_name") or strip_arena_suffix(name)

    matchups = [(disp(a), disp(b)) for _, a, b in new_rows]
    try:
        await thread.send(
            bracket_fill_notice(round_num, matchups, url),
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except discord.HTTPException:
        log.warning(f"could not post bracket fill note event={manager.event_id} round={round_num}", exc_info=True)


async def _bracket_maybe_advance(manager, round_num: int, is_edit: bool = False,
                                  head: str | None = None) -> None:
    """Bracket counterpart to the Swiss advance branch in _maybe_advance: append the next round after
    a fresh result, regenerate downstream after an edit, and on the final round refresh standings +
    schedule the finalize grace once the full slate (roster/2 matches) has reported.

    `head` is the corrected-result line the caller held back for the regenerate to post as one message
    with the pairing change; see `bracket_regenerate_downstream`."""
    event_id = manager.event_id
    roster_size = len(manager.tournament_players)
    if round_num >= TOTAL_ROUNDS:
        await _post_or_update_live_standings(manager)
        pending = await asyncio.to_thread(bracket_pending_in_round, event_id, TOTAL_ROUNDS, roster_size)
        if pending > 0:
            await maybe_arm_deck_nudge(manager)
        elif not manager.finalized:
            await manager.share_draft_log()
            _schedule_grace(manager, round_num)
    elif is_edit:
        await bracket_regenerate_downstream(manager, round_num, head)
    else:
        await bracket_advance(manager, round_num)
    await _relock_prior_rounds(manager, round_num)


async def _relock_prior_rounds(manager, current_round: int) -> None:
    """Re-render the messages of rounds before current_round so their reported dropdowns disappear now
    that a later round has reported (edits to them are blocked). Keeps each round's nav link."""
    for r in range(1, current_round):
        msg = manager.round_messages.get(r)
        if msg is None:
            continue
        display = await asyncio.to_thread(load_bracket_round_states, manager.event_id, r)
        url, label = _round_nav_link(manager, r)
        try:
            await msg.edit(view=RoundResultsView(display, round_num=r, link_url=url, link_label=label))
        except discord.HTTPException:
            log.warning(f"could not relock round {r}", exc_info=True)


def format_result_change(a_name: str, b_name: str, winner_name: str | None, score: str | None,
                         a_disp: str | None = None, b_disp: str | None = None) -> str:
    """The corrected result as plain text for the regenerate notice: 'Bob wins 2-1 vs Alice', or a
    cleared/no-result fallback. Shared by prod and testlobby so both word it identically. Winner side
    is decided from the raw names; a_disp/b_disp override how each player is shown so callers can lead
    with the Discord display instead of the Arena/Draftmancer handle."""
    a_disp = a_disp if a_disp is not None else strip_arena_suffix(a_name)
    b_disp = b_disp if b_disp is not None else strip_arena_suffix(b_name)
    if winner_name and winner_name not in (SKIPPED_SENTINEL, CLEAR_SENTINEL):
        winner_is_a = winner_name.lower() == a_name.lower()
        winner_disp, loser_disp = (a_disp, b_disp) if winner_is_a else (b_disp, a_disp)
        return f"{winner_disp} wins {score} vs {loser_disp}" if score else f"{winner_disp} wins vs {loser_disp}"
    return f"{a_disp} vs {b_disp} result cleared"


PAIRING_GAP = NBSP * 5


def bracket_regen_notice(head: str | None, round_num: int, pairings_url: str | None,
                         new_matchups: list[tuple[str, str]] | None = None) -> str:
    """The single source of truth for the thread note posted when an edit re-pairs a bracket round.

    `head` is the corrected-result line the re-pair follows from, so the correction and the pairing
    change read as one message. `new_matchups` carries the pairings the regenerate created, each side a
    mention where the player has a linked Discord account, so the re-paired players are pinged.
    """
    updated = f"[**Pairings Updated**]({pairings_url})" if pairings_url else "**Pairings Updated**"
    lead = f"{head} - " if head else "♻️ "
    notice = f"{lead}Round {round_num} {updated} {emojis.get('manat')}".rstrip()
    if new_matchups:
        pairings = PAIRING_GAP.join(f"{a} vs {b}" for a, b in new_matchups)
        notice += f"\n⚠️ **New Pairings:** {pairings}"
    return notice


async def bracket_regenerate_downstream(manager, edited_round: int, head: str | None = None) -> None:
    """An upstream result changed (edit/clear) while no later round had reported yet: discard the
    downstream rounds and rebuild them from the corrected results, editing the round messages in
    place.

    Pairings the correction did not invalidate are kept, so only the players whose record moved get a
    new opponent. Posts `head` (the corrected-result line the caller held back) with the changed round
    and its new pairings appended, so a correction is one thread message instead of two. Each re-paired
    player's existing round DM is rewritten in place, which reaches them without a second notification.
    """
    event_id = manager.event_id
    downstream = range(edited_round + 1, TOTAL_ROUNDS + 1)
    old = {r: await asyncio.to_thread(_load_pairings_for_round, event_id, r) for r in downstream}
    sent_dms = await asyncio.to_thread(_dm_refs_for_rounds_sync, event_id, downstream)
    keep = await _pairings_to_keep(manager, downstream, old)
    for r in downstream:
        await asyncio.to_thread(_prune_stale_pairings, event_id, r, keep[r])
    for src in range(edited_round, TOTAL_ROUNDS):
        await bracket_advance(manager, src, announce_fill=False, reuse_dms=sent_dms)

    changed_rounds = []
    current: dict[int, list[tuple[str, str]]] = {}
    for r in downstream:
        current[r] = await asyncio.to_thread(_load_pairings_for_round, event_id, r)
        if _pairing_keys(current[r]) != _pairing_keys(old.get(r, [])):
            changed_rounds.append(r)
    thread = await manager._fetch_thread()
    if thread is None:
        return
    if not changed_rounds:
        if head:
            await _send_regen_notice(thread, head)
        return
    log.info(f"[BRACKET] event={event_id} regenerate after R{edited_round} edit changed rounds {changed_rounds}")
    target = changed_rounds[0]
    target_msg = manager.round_messages.get(target)
    url = target_msg.jump_url if target_msg is not None else None
    displays = await asyncio.to_thread(load_participant_displays, event_id)
    new_matchups = [
        (_discord_mention(displays, a), _discord_mention(displays, b))
        for a, b in _added_pairings(old.get(target, []), current[target])
    ]
    await _send_regen_notice(thread, bracket_regen_notice(head, target, url, new_matchups))


async def _pairings_to_keep(manager, downstream, old: dict[int, list[tuple[str, str]]],
                            ) -> dict[int, list[tuple[str, str]]]:
    """Which downstream pairings survive a corrected result, per round.

    A pairing whose two players still share a record is still a legal pairing and re-pairing it would
    move players for nothing. So is one a from-scratch re-pair would make anyway, which is how a pod
    that plays someone across records keeps that match instead of churning it on every correction.
    Keeping some pairings does shrink the pool the rest re-pair from, which can force a rematch a full
    re-pair would have avoided; when that happens the round is re-paired from scratch instead.
    """
    players = manager.tournament_players
    outcomes = await asyncio.to_thread(load_matches, manager.event_id)
    records = pod_bracket.player_records(players, outcomes)
    keep: dict[int, list[tuple[str, str]]] = {}
    for r in downstream:
        source_complete = await _round_fully_reported(manager, r - 1)
        from_scratch = _pairing_keys(pod_bracket.incremental_pairings(
            players, outcomes, [], r, source_round_complete=source_complete,
        ))
        survivors = [
            (a, b) for a, b in old.get(r, [])
            if a in records and b in records
            and (records[a] == records[b] or _pairing_keys([(a, b)]) <= from_scratch)
        ]
        candidate = pod_bracket.incremental_pairings(
            players, outcomes, survivors, r, source_round_complete=source_complete,
        )
        if pod_bracket.contains_rematch(candidate, outcomes):
            log.info(f"[BRACKET] event={manager.event_id} keeping R{r} pairings would force a rematch, full re-pair")
            survivors = []
        keep[r] = survivors
    return keep


async def _send_regen_notice(thread, notice: str) -> None:
    try:
        await thread.send(notice, allowed_mentions=discord.AllowedMentions(users=True))
    except discord.HTTPException:
        log.warning("could not post bracket regenerate announcement", exc_info=True)


def _pairing_keys(pairs: list[tuple[str, str]]) -> set[frozenset[str]]:
    return {frozenset((normalize_player_name(a), normalize_player_name(b))) for a, b in pairs}


def _added_pairings(old: list[tuple[str, str]], now: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """The pairings in `now` that `old` did not have, so a regenerate names only the matchups it
    actually changed instead of the whole round."""
    previous = _pairing_keys(old)
    added = []
    for a, b in now:
        if frozenset((normalize_player_name(a), normalize_player_name(b))) not in previous:
            added.append((a, b))
    return added
