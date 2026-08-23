"""Draftmancer socket.io session lifecycle for a single pod-draft event.

One PodDraftManager per active event, kept in the module-level ACTIVE_POD_MANAGERS registry so the
ready check and bracket flows can look up the right session by event_id. Connects with
exponential backoff + jitter, joins the session, applies the agreed settings, and listens for
sessionUsers updates so later commands can act on who is in the lobby
"""
from __future__ import annotations

import asyncio
import gzip
import json
import logging
import random
import re
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone

import discord
import socketio
from discord.ext import commands

from sqlalchemy import func, select

from bot import emojis
from bot.commands.messages import (
    MSG_BOT_RECONNECTED,
    MSG_DRAFTMANCER_LINK_ARENA,
    MSG_DRAFTMANCER_SET_NAME,
    MSG_DRAFTMANCER_USE_DISCORD_NAME,
    MSG_DRAFTMANCER_WELCOME,
    MSG_LOBBY_FULL_PROMPT,
    MSG_LOBBY_WAITING,
    MSG_MOCK_CLOSED_IDLE,
    MSG_MOCK_COMPLETE,
    MSG_MOCK_COMPLETE_CHANNEL,
    MSG_POD_RESTARTED,
    MSG_POD_RESTARTING,
    MSG_RIDER_SEATS_OPEN,
)
from bot.config import settings
from bot.database import SessionLocal
from bot.discord_helpers import NBSP, extract_avatar_hash, run_detached
from bot.models import Player, PodDraftEvent, PodDraftParticipant
from bot.scripts.draftmancer_log import build_compact
from bot.services import bot_log as bot_log_mod
from bot.services import championship
from bot.services.lobby_embed import (
    LobbyReadyButtonView,
    ReadyCheckAnswerView,
    build_live_lobby_view,
    build_started_lobby_view,
    build_not_ready_view,
    ready_check_overdue_text,
    render as render_lobby_embed,
    render_ready_check_progress,
    roster_hold_detail,
    roster_hold_hint,
    stopped_reason,
    waiting_roster,
)
from bot.services.mock_lobby_card import (
    MOCK_CARD_PING,
    MOCK_CARD_QUIET,
    STATE_CANCELED,
    STATE_COMPLETE,
    STATE_DRAFTING,
    STATE_OPEN,
    STATE_OPENING,
    build_mock_card,
    build_mock_complete_view,
)
from bot.services.pod_confirm import plan_tables
from bot.services import pod_disconnect
from bot.services import pod_event_settings
from bot.services import pod_format
from bot.services.pod_format import settings_notice_markers
from bot.services.ping_roles import grant_mock_draft_role
from bot.services.pod_active import (
    ACTIVE_POD_MANAGERS,
    notify_card_phase,
    notify_pod_complete,
    notify_pod_drafting,
)
from bot.services.pod_roles import grant_pod_drafters, role_mention
from bot.services.pod_schedule import MOCK_DRAFT_ROLE_NAME
from bot.services.pod_notices import send_settings_notice
from bot.services.pod_pairing_select import pairing_change_message, pairing_label
from bot.services.pod_registration_embed import update_registered_embed
from bot.services.pod_seating_select import seating_mode_label
from bot.services import pod_format_poll
from bot.services import pod_round_robin_vote
from bot.services.pod_team_vote import (
    SIDE_TEAM,
    TEAM_VOTE_POD_SIZE,
    build_team_vote_locked_embed,
    build_team_vote_offer_embed,
    build_team_vote_view,
    build_team_vote_waited_embed,
    find_team_vote_card,
    needed_from_embed,
    register_team_vote_click_handler,
    rerender_gathering,
    team_voters_from_embed,
    wait_voters_from_embed,
)
from bot.services.pod_drafts import (
    BOT_USER_NAME,
    apply_seat_indexes,
    attach_arena_alias,
    event_member_rankings_sync,
    full_arena_handle,
    normalize_player_name,
    classify_lobby_names,
    delete_event_sync,
    draftmancer_url_for,
    finalize_mock_event,
    is_championship,
    load_event_pairing_mode_sync,
    load_event_seating_mode_sync,
    load_event_thread_id_sync,
    load_event_time_sync,
    mock_repost_sync,
    name_token_match,
    new_drafters_in_roster_sync,
    player_for_name,
    pod_page_url,
    record_mock_repost_sync,
    seed_event_participants,
    update_event_format,
)
from bot.services.pod_signals import inactivity_window_text
from bot.services.pod_team_flow import assign_teams_at_draft_start, load_teams_sync
from bot.services.pod_tournament import (
    persist_pairing_mode,
    persist_seating_mode,
    refresh_round_pairing_messages,
    start_tournament,
)
from bot.services.pod_voice import build_voice_offer_message, free_voice_rooms, pod_voice_channel
from bot.services.player_stats import leaderboard_seat_order
from bot.slug import disambiguate_slug, slugify


log = logging.getLogger(__name__)


_BACKOFF_BASE_S = 1.0
_BACKOFF_MAX_S = 30.0
_BACKOFF_MAX_RETRIES = 8
LOBBY_REHYDRATE_WINDOW = timedelta(hours=12)
_READY_TIMEOUT_S = 180
_READY_DEBOUNCE_S = 2.0
_LOBBY_REFRESH_DEBOUNCE_S = 1.0
_LOBBY_FULL_THRESHOLD = 8
_LOBBY_FULL_PROMPT_DELAY_S = 10
RIDER_WINDOW_S = 120
_RESTART_SETTLE_S = 2.5
_RESTART_READY_MIN_PLAYERS = 2
_DISCONNECT_BLIP_S = 5
_DISCONNECT_GRACE_S = 120
DRAFTMANCER_DEFAULT_NAME = "Player_"
NAME_NUDGE_INTERVAL_S = 5
WORD_JOINER = "⁠"
BUBBLE_BREAK_CHARS = "-/"

_SEEDING_REFRESH_HOOK = None
_SEEDING_REPOST_HOOK = None
_CARD_CLOSE_HOOK = None
_POD_CANCEL_HOOK = None
_CARD_REFRESH_HOOK = None
_UNDERFILL_FIRED_HOOK = None
_RALLY_FIRED_HOOK = None


def set_card_close_hook(callback) -> None:
    """pod_launch registers its RSVP-card close here so the manager can drop the card's buttons at
    draft_done without importing pod_launch (which imports the manager)."""
    global _CARD_CLOSE_HOOK
    _CARD_CLOSE_HOOK = callback


def set_pod_cancel_hook(callback) -> None:
    """pod_launch registers its cancel teardown here so `cancel_pod_event` can retire the pod's card and
    close its launcher slot before the event row is deleted — awaited, not fire-and-forget, so every
    surface resolves while the row still exists."""
    global _POD_CANCEL_HOOK
    _POD_CANCEL_HOOK = callback


def notify_card_close(bot, event_id: str) -> None:
    """Close the pod's RSVP card (no-op if unset). Fired at draft_done — the first state a restart can
    no longer revert to the lobby — so the card stays live through fill, ready check, and any restart."""
    if _CARD_CLOSE_HOOK is not None:
        asyncio.create_task(_CARD_CLOSE_HOOK(bot, event_id))


def set_card_refresh_hook(callback) -> None:
    """pod_draft registers its RSVP-card re-render here so the manager can refresh the card title when
    the pod's pairing mode changes without importing the command module (which imports the manager)."""
    global _CARD_REFRESH_HOOK
    _CARD_REFRESH_HOOK = callback


def notify_card_refresh(bot, event_id: str) -> None:
    """Re-render the pod's RSVP card (no-op if unset). Fired when the pairing mode flips to or from a
    Team Draft so the card title picks up the ` - Team Draft` marker."""
    if _CARD_REFRESH_HOOK is not None:
        asyncio.create_task(_CARD_REFRESH_HOOK(bot, event_id))


def set_underfill_fired_hook(callback) -> None:
    """The underfill task registers its nudge finalizer here so the manager can flip the pod-chat
    recruiting nudge to a fired record at draft start without importing the task module."""
    global _UNDERFILL_FIRED_HOOK
    _UNDERFILL_FIRED_HOOK = callback


def notify_underfill_fired(bot, event_id: str, player_count: int, thread_url: str) -> None:
    """Post the fired record in pod-chat, replacing the recruiting nudge (no-op if unset). Fired once the
    seated roster is locked at draft start, so a reader in pod-chat sees the draft begin at the bottom of the
    channel instead of the nudge going quiet above the conversation."""
    if _UNDERFILL_FIRED_HOOK is not None:
        asyncio.create_task(_UNDERFILL_FIRED_HOOK(bot, event_id, player_count, thread_url))


def set_rally_fired_hook(callback) -> None:
    """`!pod` registers its rally finalizer here so the manager can retire a standing rally at draft start
    without importing the command module."""
    global _RALLY_FIRED_HOOK
    _RALLY_FIRED_HOOK = callback


def notify_rally_fired(bot, event_id: str) -> None:
    """Delete any `!pod` rally still asking for players (no-op if unset). A rally is a static post in
    whichever channel it was called from, so without this it would keep sending people to a pod that is
    already drafting."""
    if _RALLY_FIRED_HOOK is not None:
        asyncio.create_task(_RALLY_FIRED_HOOK(bot, event_id))


def set_seeding_refresh_hook(callback) -> None:
    """The command layer registers its seeding-table refresher here so the manager and the sesh listener
    can update the posted table without importing the command module (which imports the manager)."""
    global _SEEDING_REFRESH_HOOK
    _SEEDING_REFRESH_HOOK = callback


def set_seeding_repost_hook(callback) -> None:
    """Companion to set_seeding_refresh_hook: re-posts a fresh seeding table at the bottom of the thread
    (the in-place refresh only edits the existing ones)."""
    global _SEEDING_REPOST_HOOK
    _SEEDING_REPOST_HOOK = callback


def notify_seeding_change(bot, event_id: str) -> None:
    """Fire the registered seeding-table refresh (no-op if unset). Called on Draftmancer join/leave and
    on sesh RSVP edits; the refresher itself decides whether a table exists and the pod is leaderboard-seated."""
    if _SEEDING_REFRESH_HOOK is not None:
        asyncio.create_task(_SEEDING_REFRESH_HOOK(bot, event_id))


def notify_seeding_repost(bot, event_id: str) -> None:
    """Re-post a fresh seeding table at the bottom of the thread (no-op if unset). Fired when the spectate
    link goes up so the live table sits by the action instead of only at the scrolled-up pinned anchor."""
    if _SEEDING_REPOST_HOOK is not None:
        asyncio.create_task(_SEEDING_REPOST_HOOK(bot, event_id))


def cancel_manager_tasks(manager: "PodDraftManager") -> None:
    """Stop every timer a manager can leave running: the round grace window, the championship deadline,
    and the two deck-chase waits. Every teardown path has to clear all of them."""
    for task in (manager.grace_task, manager.championship_task, manager.deck_nudge_task,
                 manager.deck_ping_task):
        if task is not None and not task.done():
            task.cancel()


async def cancel_pod_event(event_id: str, *, actor: str | None = None, idle: bool = False) -> str | None:
    """Tear down a pod draft entirely: cancel pending tournament tasks, disconnect the manager, and
    delete the event row — the cascade drops participants, matches, replays, and DM trackers, which
    also removes the leaderboard pod page.

    `idle` is the inactivity sweep closing a mock lobby nobody answered: no actor pressed anything, so
    the card names the window instead and the thread stands down with it."""
    log.warning(f"pod-cancel: {actor or 'inactivity'} deleting event {event_id}")
    manager = ACTIVE_POD_MANAGERS.get(event_id)
    if manager is not None:
        cancel_manager_tasks(manager)
        if idle:
            await manager.stand_down_idle_lobby()
        else:
            await manager.mark_canceled(actor)
        await manager.disconnect_safely()
    if _POD_CANCEL_HOOK is not None:
        await _POD_CANCEL_HOOK(event_id)
    await asyncio.to_thread(delete_event_sync, event_id)
    return None


CardPoster = Callable[..., Awaitable[discord.Message]]


class PodDraftManager:
    def __init__(self, bot: commands.Bot, event_id: str, session_id: str, thread_id: int,
                 set_code: str, expected_attendee_count: int, *,
                 event_name: str = "Pod Draft",
                 draftmancer_url: str = "",
                 kind: str = "tournament",
                 rsvps_yes: list[str] | None = None,
                 rsvps_unconfirmed: list[str] | None = None,
                 rsvps_maybe: list[str] | None = None,
                 reconnect: bool = False,
                 created_by: str | None = None) -> None:
        self.bot = bot
        self.event_id = event_id
        self.session_id = session_id
        self.thread_id = thread_id
        self.set_code = set_code
        self.expected_attendee_count = expected_attendee_count
        self.event_name = event_name
        self.draftmancer_url = draftmancer_url
        self.spectate_url: str | None = None
        self.kind = kind
        self.reconnect = reconnect
        self._lobby_card_adopt_attempted = False
        self._mock_anchor_message: "discord.Message | None" = None
        self._mock_repost_message: "discord.Message | None" = None
        self.created_by = created_by
        self.canceled_by: str | None = None
        self.canceled_idle = False
        self._mock_idle_task: asyncio.Task | None = None
        self._mock_lobby_signature: tuple[str, ...] | None = None
        self._thread_added_ids: set[str] = set()
        self.rsvps_yes: list[str] = list(rsvps_yes or [])
        self.rsvps_unconfirmed: list[str] = list(rsvps_unconfirmed or [])
        self.rsvps_maybe: list[str] = list(rsvps_maybe or [])
        self.claimed_discord_ids: set[str] = set()
        self.table_event_ids: set[str] = set()
        self.new_drafters: frozenset[str] = frozenset()
        self._rsvp_new_drafters: frozenset[str] | None = None
        self.session_users: list[dict] = []
        self.session_spectators: list[dict] = []
        self.spectator_user_ids: set[str] = set()
        self.spectator_names: list[str] = []
        self.spectator_targets: list[tuple[str, str]] = []
        self.desired_seating: list[str] | None = None
        self.bot_user_id: str | None = None
        self._name_nudge_task: asyncio.Task | None = None
        self._welcomed_user_ids: set[str] = set()
        self.owner_claimed = False
        self.is_owner = False
        self._ownership_claim_in_flight = False
        self._ownership_lost_reported = False
        self.ownership_ready = asyncio.Event()
        self._closed = False
        self.abandoned = False
        self.ready_check_active = False
        self.ready_check_generation = 0
        self.ready_check_joined_ids: set[str] = set()
        self.ready_check_left_ids: set[str] = set()
        self.ready_discord_ids: set[str] = set()
        self.ready_socket_ids: set[str] = set()
        self.not_ready_ids: set[str] = set()
        self.expected_user_ids: set[str] = set()
        self.expected_user_names: dict[str, str] = {}
        self._lobby_full_prompt_task: asyncio.Task | None = None
        self._lobby_full_prompt_message: "discord.Message | None" = None
        self._lobby_full_prompted = False
        self._lobby_waiting_message: "discord.Message | None" = None
        self._lobby_waiting_text = ""
        self.rider_seats_held = 0
        self.rider_mentions: list[str] = []
        self._rider_window_task: asyncio.Task | None = None
        self._voice_link_posted = False
        self.team_voice_rooms: list["discord.VoiceChannel"] = []
        self._ready_check_started_at = 0.0
        self.lobby_status_message: object | None = None
        self._repost_lobby_card = False
        self.ready_check_progress_message: object | None = None
        self._lobby_post_lock = asyncio.Lock()
        self._lobby_refresh_pending = False
        self._lobby_refresh_task: asyncio.Task | None = None
        self._ready_timeout_task: asyncio.Task | None = None
        self.drafting = False
        self._draft_start_in_flight = False
        self.draft_paused = False
        self.draft_cancelled = False
        self.draft_complete = False
        self.last_cancel_reason: str | None = None
        self.ready_check_overdue = False
        self.initiated_by: str | None = None
        self.draft_logs: dict[str, dict] = {}
        self.current_round = 0
        self.finalized = False
        self.tournament_roster: list[str] = []  # draftmancer userNames, set on endDraft
        self.tournament_players: list = []       # pod_swiss.Player list, set by pod_tournament.start_tournament
        self.pairing_mode = "swiss"              # resolved in start_tournament; see pod_pairing_select.PAIRING_MODES
        self.seating_mode = "random"             # 'random', 'manual', or 'leaderboard'; hydrated on connect
        self._bots_pushed: int | None = None
        self.pick_timer = settings.pod_draft_pick_timer
        self.picks_per_pack = settings.pod_draft_picks_per_pack
        self.max_players = settings.pod_draft_max_players
        self.packs_per_player: int | None = None
        self.cards_per_pack: int | None = None
        self.disconnected_names: list[str] = []
        self.stall_names: set[str] = set()
        self.bot_filled_names: set[str] = set()
        self._disconnect_message: "discord.Message | None" = None
        self._disconnect_offer_message: "discord.Message | None" = None
        self._flapped_messages: list["discord.Message"] = []
        self._disconnect_watch_task: asyncio.Task | None = None
        self._disconnect_offer_task: asyncio.Task | None = None
        self._disconnect_at: int | None = None
        self.team_map: dict[str, str] | None = None  # draftmancer_name -> 'A'/'B' for team drafts
        self.team_board_messages: list["discord.Message"] = []
        self.team_reveal_messages: dict[int, "discord.Message"] = {}  # round -> per-round reveal block
        self.team_vote_message: "discord.Message | None" = None
        self.team_vote_offered = False
        self.team_vote_size = 0
        self.pairing_set_by_user = False
        self.round_robin_vote_message: "discord.Message | None" = None
        self.round_robin_vote_offered = False
        self.round_robin_vote_size = 0
        self.round_robin_vote_from_signups = False
        self.format_poll_message: "discord.Message | None" = None
        self.format_poll_offered = False
        self.scheduled_start: datetime | None = None
        self._last_seating_signature: tuple[str, ...] | None = None
        self.standings_message = None
        self._standings_post_lock = asyncio.Lock()
        self._advance_lock = asyncio.Lock()
        self.round_messages: dict[int, "discord.Message"] = {}
        self.grace_task = None
        self.grace_round: int | None = None
        self.champion_announced = False
        self.trophy_hype_posted = False
        self.champion_announcement_message = None
        self.card_result_line: str | None = None
        self.card_result_url: str | None = None
        self.champion_discord_ids: set[str] = set()
        self.championship_task: asyncio.Task | None = None
        self.deck_nudge_task: asyncio.Task | None = None
        self.deck_ping_task: asyncio.Task | None = None
        self._end_watchdog_task: asyncio.Task | None = None
        self.sio = socketio.AsyncClient(reconnection=False, logger=False, engineio_logger=False)
        self.sio.on("connect", self._on_connect)
        self.sio.on("disconnect", self._on_disconnect)
        self.sio.on("sessionUsers", self._on_session_users)
        self.sio.on("sessionSpectators", self._on_session_spectators)
        self.sio.on("updateUser", self._on_update_user)
        self.sio.on("setReady", self._on_set_ready)
        self.sio.on("userDisconnected", self._on_user_disconnected)
        self.sio.on("resumeOnReconnection", self._on_resume_on_reconnection)
        self.sio.on("endDraft", self._on_end_draft)
        self.sio.on("draftLog", self._on_draft_log)
        self.sio.on("shareDecklist", self._on_share_decklist)

    @property
    def _connect_user_id(self) -> str:
        return f"{BOT_USER_NAME}-{self.session_id}"

    @property
    def _connect_url(self) -> str:
        return (
            f"{settings.draftmancer_ws_url}/?"
            f"userID={self._connect_user_id}&sessionID={self.session_id}&userName={BOT_USER_NAME}"
        )

    async def connect(self) -> bool:
        delay = _BACKOFF_BASE_S
        for attempt in range(1, _BACKOFF_MAX_RETRIES + 1):
            try:
                await self.sio.connect(self._connect_url, transports=["websocket"], wait_timeout=10)
                return True
            except (socketio.exceptions.ConnectionError, OSError) as e:
                if attempt >= _BACKOFF_MAX_RETRIES:
                    log.error(
                        f"[LIFECYCLE] connect.gave_up event={self.event_id} attempts={attempt} err={e!s}"
                    )
                    await bot_log_mod.get(self.bot).post(
                        f"Draftmancer connect gave up for event `{self.event_id}` after {attempt} attempts.",
                        fingerprint=f"connect_gave_up:{self.event_id}",
                        tag="LIFECYCLE",
                    )
                    return False
                wait = min(delay + random.uniform(0, delay * 0.25), _BACKOFF_MAX_S)
                log.warning(
                    f"[LIFECYCLE] connect.retry event={self.event_id} attempt={attempt} "
                    f"wait_s={wait:.1f} err={e!s}"
                )
                await asyncio.sleep(wait)
                delay = min(delay * 2, _BACKOFF_MAX_S)
        return False

    async def disconnect_safely(self) -> None:
        log.info(
            f"[LIFECYCLE] disconnect_safely event={self.event_id} "
            f"sio_connected={self.sio.connected} drafting={self.drafting} "
            f"complete={self.draft_complete} finalized={self.finalized}"
        )
        self._closed = True
        self._cancel_end_watchdog()
        self._cancel_mock_idle_timer()
        self._cancel_lobby_refresh()
        self._stop_name_nudge()
        try:
            if self.sio.connected:
                await self.sio.disconnect()
        except Exception:
            log.warning(f"[LIFECYCLE] disconnect_safely.error event={self.event_id}", exc_info=True)
        removed = ACTIVE_POD_MANAGERS.pop(self.event_id, None) is not None
        log.info(
            f"[LIFECYCLE] disconnect_safely.done event={self.event_id} "
            f"removed_from_registry={removed} registry_size={len(ACTIVE_POD_MANAGERS)}"
        )

    async def abandon_session(self) -> None:
        """Give up on this session for good, for a pod reopening on a fresh one.

        An ownership claim in flight lands seconds after the socket closes and posts the card on its way
        out, so the flag goes up first and any card already posted comes down."""
        self.abandoned = True
        await self.disconnect_safely()
        card, self.lobby_status_message = self.lobby_status_message, None
        if card is None:
            return
        try:
            await card.delete()
        except discord.HTTPException:
            log.warning(f"could not delete the lobby card of abandoned {self.session_id}", exc_info=True)

    async def _on_connect(self) -> None:
        log.info(f"[LIFECYCLE] socket_connect event={self.event_id} sid={self.session_id}")
        await self._mark_socket_status("connected")

    async def _on_disconnect(self) -> None:
        in_flight = self.drafting or (self.draft_complete and not self.finalized)
        was_closed_intentionally = self._closed
        self._closed = True
        decision = "keep" if in_flight else "drop"
        log.warning(
            f"[LIFECYCLE] socket_disconnect event={self.event_id} sid={self.session_id} "
            f"closed_intentionally={was_closed_intentionally} drafting={self.drafting} "
            f"complete={self.draft_complete} finalized={self.finalized} "
            f"decision={decision} registry_size={len(ACTIVE_POD_MANAGERS)}"
        )
        if in_flight:
            if not was_closed_intentionally:
                await bot_log_mod.get(self.bot).post(
                    f"Socket dropped mid-flight for event `{self.event_id}` "
                    f"(drafting={self.drafting}, complete={self.draft_complete}).",
                    fingerprint=f"socket_drop_in_flight:{self.event_id}",
                    tag="LIFECYCLE",
                )
            return
        removed = ACTIVE_POD_MANAGERS.pop(self.event_id, None) is not None
        log.info(
            f"[LIFECYCLE] socket_disconnect.evict event={self.event_id} "
            f"removed={removed} registry_size={len(ACTIVE_POD_MANAGERS)}"
        )

    async def _on_session_users(self, users) -> None:
        self.session_users = list(users) if isinstance(users, list) else []
        slim = [{k: v for k, v in u.items() if k != "collection"} for u in self.session_users]
        log.info(f"draftmancer sessionUsers for {self.session_id}: {slim}")
        if self.draft_complete:
            return
        if self.bot_user_id is None:
            for u in self.session_users:
                if u.get("userName") == BOT_USER_NAME:
                    self.bot_user_id = u.get("userID")
                    log.info(f"found bot userID={self.bot_user_id} for {self.session_id}")
                    break
        if self.bot_user_id is not None and not self.is_owner and not self.drafting:
            asyncio.create_task(self._claim_ownership_and_apply_settings())

        self._note_mock_lobby_activity()

        self._sync_ready_check_roster()

        if self.ready_check_active and self.ready_check_joined_ids:
            await self._adopt_recognized_arrivals()

        if self.is_owner and not self.drafting:
            await self._apply_bot_fill()

        await self._maybe_lock_planned_table()

        self._schedule_lobby_refresh()

        self._admit_lobby_arrivals()

        self._sync_leaderboard_seeding()

        await self._maybe_complete_ready_check()

    async def _on_session_spectators(self, spectators) -> None:
        self.session_spectators = list(spectators) if isinstance(spectators, list) else []
        self._recompute_spectator_state()
        log.info(f"draftmancer sessionSpectators for {self.session_id}: {self.spectator_names}")
        if self.draft_complete:
            return
        self._schedule_lobby_refresh()

    def _recompute_spectator_state(self) -> None:
        rows = self.session_spectators
        self.spectator_user_ids = {s.get("userID") for s in rows if s.get("userID")}
        self.spectator_names = [s.get("userName") for s in rows if s.get("userName")]
        self.spectator_targets = [
            (s.get("userID"), s.get("userName")) for s in rows
            if s.get("userID") and s.get("userName") != BOT_USER_NAME
        ]

    async def _on_update_user(self, payload) -> None:
        if not isinstance(payload, dict):
            return
        user_id = payload.get("userID")
        updates = payload.get("updatedProperties") or {}
        if not user_id or not updates:
            return
        renamed_roster = self._apply_user_update(self.session_users, user_id, updates)
        renamed_spectator = self._apply_user_update(self.session_spectators, user_id, updates)
        if renamed_spectator:
            self._recompute_spectator_state()
        if "userName" in updates and (renamed_roster or renamed_spectator):
            log.info(f"draftmancer updateUser rename for {self.session_id}: {user_id} → {updates['userName']}")
            if not self.draft_complete:
                self._schedule_lobby_refresh()
                self._admit_lobby_arrivals()
                if renamed_roster:
                    self._sync_leaderboard_seeding()
                    if user_id not in self.spectator_user_ids:
                        run_detached(
                            self.welcome_named_seat(user_id, updates["userName"]), "draftmancer welcome",
                        )

    @staticmethod
    def _apply_user_update(rows: list[dict], user_id: str, updates: dict) -> bool:
        for u in rows:
            if u.get("userID") == user_id:
                u.update(updates)
                return True
        return False

    async def _claim_ownership_and_apply_settings(self) -> None:
        """Claim Draftmancer ownership, then push the owner-only session settings. Re-attempted on every
        pre-draft roster change while the bot is not owner: Draftmancer seats the first arrival in an
        empty session as owner and rotates ownership when that player leaves, so a lobby that opened
        under a human recovers by itself once they go.

        The answer is published the moment the probe returns. The launch path waits on it and reads a wait
        that runs out as ownership lost, so anything slower behind it abandons a session the bot owns."""
        if self.bot_user_id is None or self._ownership_claim_in_flight:
            return
        self._ownership_claim_in_flight = True
        self.owner_claimed = True
        try:
            await self.sio.emit("setSessionOwner", self.bot_user_id)
            await asyncio.sleep(0.3)
            self.is_owner = await self._enable_spectators_and_share_link()
            self.ownership_ready.set()
            if not self.is_owner:
                if self._ownership_lost_reported:
                    return
                self._ownership_lost_reported = True
                log.error(f"[LIFECYCLE] ownership_lost event={self.event_id} bot_user={self.bot_user_id}")
                await bot_log_mod.get(self.bot).post(
                    f"Bot did not hold Draftmancer ownership for event `{self.event_id}`. Owner-only "
                    f"settings were not applied and the lobby may be misconfigured. Check the session.",
                    fingerprint=f"ownership_lost:{self.event_id}",
                    tag="LIFECYCLE",
                )
                return
            self._ownership_lost_reported = False
            await self._emit_session_settings()
            await self.apply_seating_mode()
            log.info(f"[LIFECYCLE] ownership_applied event={self.event_id} bot_user={self.bot_user_id}")
            if not self.reconnect and not self.abandoned:
                await self._refresh_lobby_status()
                notify_seeding_repost(self.bot, self.event_id)
        except Exception:
            if self.abandoned:
                log.info(f"[LIFECYCLE] ownership_dropped_on_abandon event={self.event_id}")
                return
            log.exception(f"[LIFECYCLE] ownership_failed event={self.event_id}")
            await bot_log_mod.get(self.bot).post(
                f"Ownership/settings flow failed for event `{self.event_id}` — draft cannot be started.",
                fingerprint=f"ownership_failed:{self.event_id}",
                tag="LIFECYCLE",
            )
        finally:
            self._ownership_claim_in_flight = False
            self.ownership_ready.set()

    async def await_ownership(self, timeout_s: float = 10.0) -> bool:
        """Block until the ownership claim resolves so a launch path reveals the Draftmancer link only
        after the bot holds the empty session. Returns whether the bot became owner."""
        try:
            await asyncio.wait_for(self.ownership_ready.wait(), timeout=timeout_s)
        except asyncio.TimeoutError:
            log.warning(f"[LIFECYCLE] ownership_wait_timeout event={self.event_id}")
            return False
        return self.is_owner

    async def _emit_session_settings(self) -> None:
        await self._emit_format()
        await self.sio.emit("setOwnerIsPlayer", False)
        await self.sio.emit("setMaxPlayers", self.max_players)
        await self.sio.emit("setPickTimer", self.pick_timer)
        await self.sio.emit("setPickedCardsPerRound", self.picks_per_pack)
        await self._emit_pack_shape()
        await self._apply_bot_fill()
        await self.sio.emit("setPersonalLogs", True)
        await self.sio.emit("setDraftLogRecipients", self._draft_log_recipients)
        team_draft = self.pairing_mode == "team"
        await self.sio.emit("teamDraft", team_draft)
        log.info(
            f"[LIFECYCLE] session_settings_applied event={self.event_id} set={self.set_code} "
            f"max_players={self.max_players} pick_timer={self.pick_timer} "
            f"picks_per_pack={self.picks_per_pack} packs={self.packs_per_player} "
            f"cards_per_pack={self.cards_per_pack} "
            f"bots={self._bots_pushed} log_recipients={self._draft_log_recipients} team_draft={team_draft}"
        )

    async def _emit_pack_shape(self) -> None:
        """Nothing is emitted for a pod that left the pack counts alone, so a plain set keeps its own
        collation and an imported cube keeps the numbers its list carries."""
        if self.packs_per_player is not None:
            await self.sio.emit("boostersPerPlayer", self.packs_per_player)
        if self.cards_per_pack is not None:
            await self.sio.emit("cardsPerBooster", self.cards_per_pack)

    def _desired_bot_count(self) -> int:
        """Draftmancer bots padding the empty seats. A community pod drafts the players who turned up; the
        test bot fills every empty seat, so one browser runs a whole draft."""
        if settings.is_production:
            return 0
        return max(0, self.max_players - len(self.player_session_users()))

    async def _apply_bot_fill(self) -> None:
        """Match the bot count to the seats still empty, pre-draft and only when the number moves."""
        target = self._desired_bot_count()
        if target == self._bots_pushed or self.drafting or self.draft_complete:
            return
        await self.sio.emit("setBots", target)
        self._bots_pushed = target

    async def apply_team_draft_setting(self) -> None:
        """Push the teamDraft flag so Draftmancer splits and colors the sides, then re-push the seating
        mode. The full settings emit only fires once at ownership claim, so a later toggle through the
        Settings panel or the team vote needs this to reach the live table. The seating re-push matters
        under Seats: Random, where the two pairing modes want opposite things — a non-team pod leaves
        Draftmancer's start-time shuffle on, a team pod needs the order known at startDraft and so
        pushes its own. Pre-draft only."""
        if not self.sio.connected or self.drafting or self.draft_complete:
            return
        team_draft = self.pairing_mode == "team"
        await self.sio.emit("teamDraft", team_draft)
        log.info(f"[TEAM] team_draft_flag_pushed event={self.event_id} team_draft={team_draft}")
        await self.apply_seating_mode()

    @property
    def _draft_log_recipients(self) -> str:
        """Mock drafts play no rounds, so picks never need hiding — open every player's draft log the
        moment the draft ends. Tournament pods stay 'delayed' so the table can't be scouted mid-event."""
        return "everyone" if self.kind == "mock" else "delayed"

    async def _enable_spectators_and_share_link(self) -> bool:
        """Enable spectators and store the spectate link. Doubles as the ownership probe: the ack carries
        a spectateKey only when the bot holds the session, so a missing key means ownership was lost.

        Nothing Discord-facing runs here: a card edit inside the probe delays the answer the launch path
        waits on."""
        result = await self._emit_with_ack("setAllowSpectators", True)
        spectate_key = result.get("spectateKey") if isinstance(result, dict) else None
        if not spectate_key:
            error_text = _ack_error_text(result)
            log.warning(f"[LIFECYCLE] spectators.enable_failed event={self.event_id} error={error_text!r}")
            return False
        self.is_owner = True
        self.spectate_url = f"{self.draftmancer_url}&spectate={spectate_key}"
        log.info(f"[LIFECYCLE] spectators.enabled event={self.event_id}")
        return True

    async def _emit_format(self) -> str | None:
        """
        Point the session at the current `set_code`: a registered cube → importCube, else a  plain set → setRestriction.
        Returns an error string on cube-import failure, else None.

        A cube import leaves Draftmancer's `useCustomCardList` flag on, and booster generation reads that
        flag before the set restriction, so a switch from a cube to a set has to turn it off or the pod
        drafts the cube it came from.

        An import overwrites color balance from the imported list, so it is re-asserted on every format emit.
        """
        cube_id = pod_format.cube_id_for(self.set_code)
        if cube_id is not None:
            err = await self._import_cube(cube_id)
            if err is not None:
                thread = await self._fetch_thread()
                if thread is not None:
                    try:
                        await thread.send(f"⚠️ {err}")
                    except Exception:
                        log.warning(f"[LIFECYCLE] import_cube.thread_post_error event={self.event_id}", exc_info=True)
                return err
        else:
            await self.sio.emit("setUseCustomCardList", False)
            await self.sio.emit("setRestriction", [self.set_code.lower()])
        await self.sio.emit("setColorBalance", True)
        return None

    async def _import_cube(self, cube_id: str) -> str | None:
        """Load a CubeCobra cube into the session (owner-only). Ported from Amelas/DraftBot."""
        payload = {"service": "Cube Cobra", "cubeID": cube_id, "matchVersions": True}
        result = await self._emit_with_ack("importCube", payload, timeout_s=30.0)
        error_text = _ack_error_text(result)
        if error_text is not None:
            log.warning(
                f"[LIFECYCLE] import_cube.failed event={self.event_id} cube={cube_id} error={error_text!r}"
            )
            await bot_log_mod.get(self.bot).post(
                f"importCube failed for event `{self.event_id}` (cube `{cube_id}`): {error_text}",
                fingerprint=f"import_cube_failed:{self.event_id}",
                tag="LIFECYCLE",
            )
            return f"Couldn't load cube `{cube_id}` in Draftmancer: {error_text}"
        log.info(f"[LIFECYCLE] import_cube.ok event={self.event_id} cube={cube_id}")
        return None

    async def apply_format(self, code: str) -> str | None:
        """Switch this pod's format to `code` (a set code or a registered cube code). Pre-draft only.
        Persists set_code, renames the thread to lead with the new set, re-emits to a live session,
        and refreshes the lobby card so its title picks up the new keyrune symbol."""
        if self.drafting or self.draft_complete:
            return pod_format.FORMAT_LOCKED_MSG
        new_name = await asyncio.to_thread(_persist_format, self.event_id, code)
        if new_name is None:
            return pod_format.FORMAT_LOCKED_MSG
        self.set_code = code
        if new_name != self.event_name:
            self.event_name = new_name
            await self._rename_thread(new_name)
        if pod_format.cube_id_for(code) is None:
            self.cards_per_pack = None
            await asyncio.to_thread(
                pod_event_settings.clear_sync, self.event_id, pod_event_settings.CARDS_PER_PACK)
        if self.sio.connected and self.owner_claimed:
            err = await self._emit_format()
            if err is not None:
                return err
            await self._emit_pack_shape()
        await self.refresh_lobby_now()
        return None

    async def _rename_thread(self, name: str) -> None:
        thread = await self._fetch_thread()
        if thread is None:
            return
        try:
            await thread.edit(name=name[:100])
        except discord.HTTPException:
            log.warning(f"[LIFECYCLE] rename_thread.failed event={self.event_id} name={name!r}", exc_info=True)

    async def apply_pick_timer(self, seconds: int) -> str | None:
        """Set this pod's Draftmancer pick timer. Pre-draft only — Draftmancer locks the timer once the
        draft starts. Re-emits to the live session. Returns an error string or None."""
        if self.drafting or self.draft_complete:
            return "Pick timer is locked once the draft has started"
        if not self.sio.connected:
            return "Draftmancer session is not connected"
        self.pick_timer = seconds
        try:
            await self.sio.emit("setPickTimer", seconds)
        except Exception:
            log.exception(f"[TIMER] emit_failed event={self.event_id} seconds={seconds}")
            return "Could not update the pick timer"
        log.info(f"[TIMER] pick_timer_set event={self.event_id} seconds={seconds}")
        return None

    async def apply_picks_per_pack(self, n: int) -> str | None:
        """Set how many cards each player takes from a pack before passing it. Pre-draft only, since
        Draftmancer bakes the pick count into the boosters it builds at draft start. Re-emits to the
        live session. Returns an error string or None."""
        if self.drafting or self.draft_complete:
            return "Picks per pack are locked once the draft has started"
        if not self.sio.connected:
            return "Draftmancer session is not connected"
        self.picks_per_pack = n
        try:
            await self.sio.emit("setPickedCardsPerRound", n)
        except Exception:
            log.exception(f"[TIMER] picks_per_pack_emit_failed event={self.event_id} picks={n}")
            return "Could not update the picks per pack"
        log.info(f"[TIMER] picks_per_pack_set event={self.event_id} picks={n}")
        await self._refresh_lobby_status()
        return None

    async def apply_packs_per_player(self, n: int) -> str | None:
        """Set how many packs each player opens. Pre-draft only, since Draftmancer builds the boosters at
        draft start. Re-emits to the live session. Returns an error string or None."""
        if self.drafting or self.draft_complete:
            return "Packs are locked once the draft has started"
        if not self.sio.connected:
            return "Draftmancer session is not connected"
        self.packs_per_player = n
        try:
            await self.sio.emit("boostersPerPlayer", n)
        except Exception:
            log.exception(f"[LOBBY] packs_emit_failed event={self.event_id} packs={n}")
            return "Could not update the packs per player"
        log.info(f"[LOBBY] packs_set event={self.event_id} packs={n}")
        return None

    async def apply_cards_per_pack(self, n: int) -> str | None:
        """Set how many cards a pack holds. Cube pods only: Draftmancer reads this number off the custom
        card list, and a set draft builds its packs from the set's own collation. Pre-draft only.
        Returns an error string or None."""
        if self.drafting or self.draft_complete:
            return "Cards Per Pack is locked once the draft has started"
        if pod_format.cube_id_for(self.set_code) is None:
            return "Cards Per Pack applies to cube drafts. A set draft opens the set's own packs"
        if not self.sio.connected:
            return "Draftmancer session is not connected"
        self.cards_per_pack = n
        try:
            await self.sio.emit("cardsPerBooster", n)
        except Exception:
            log.exception(f"[LOBBY] cards_per_pack_emit_failed event={self.event_id} cards={n}")
            return "Could not update the cards per pack"
        log.info(f"[LOBBY] cards_per_pack_set event={self.event_id} cards={n}")
        return None

    async def apply_max_players(self, n: int) -> str | None:
        """Set this pod's Draftmancer seat cap. Pre-draft only — Draftmancer locks the count once the
        draft starts. Rejects a cap below the players already seated so a live drop can't strand anyone.
        Re-emits to the live session. Returns an error string or None."""
        if self.drafting or self.draft_complete:
            return "Max Players is locked once the draft has started"
        if not self.sio.connected:
            return "Draftmancer session is not connected"
        seated = len(self.player_session_users())
        if n < seated:
            return f"{seated} players are already in the lobby."
        self.max_players = n
        try:
            await self.sio.emit("setMaxPlayers", n)
        except Exception:
            log.exception(f"[LOBBY] max_players_emit_failed event={self.event_id} n={n}")
            return "Could not update max players"
        log.info(f"[LOBBY] max_players_set event={self.event_id} n={n}")
        return None

    async def _mark_socket_status(self, status: str) -> None:
        with SessionLocal() as session:
            event = session.get(PodDraftEvent, self.event_id)
            if event is not None:
                event.socket_status = status
                session.commit()

    @property
    def ready_users(self) -> set[str]:
        """Seats that are ready, from either surface."""
        return self.ready_discord_ids | self.ready_socket_ids

    def ready_check_blocker(self) -> str | None:
        """The hard guards that stop a ready check outright, shared by the lobby button's pre-check and
        initiate_ready_check so they can't drift. None means the check may run. A roster that is short, odd,
        or holding unrecognized seats does not block here: guard_ready_check confirms those with the
        initiator, so a pod that needs an unusual start is never left with Force Start as its only way in.
        A running check is not a blocker either: pressing it again re-arms, which is how a pause clears."""
        if not self.sio.connected:
            return "Draftmancer session is not connected"
        if self.drafting or self.draft_complete:
            return "The draft has already started"
        if not self.player_session_users():
            return "Nobody in the Draftmancer lobby yet"
        return None

    def ready_check_floor(self, min_players: int | None = None) -> int:
        """Roster size below which a ready check warns and asks the initiator to confirm. `/pod-ready` passes
        a lower floor so a deliberately small pod starts without the prompt. A Round Robin pod is meant to
        play four, so four is not short for it."""
        if min_players is not None:
            return min_players
        if self.pairing_mode == "roundrobin":
            return settings.pod_round_robin_size
        return settings.pod_draft_min_ready_players

    def ready_check_needs_confirm(self, unlinked: list[str], *, min_players: int | None = None) -> bool:
        """Whether the roster is unusual enough that the initiator confirms before the check fires. Shared by
        the interactive gate and the draft-restart path, which has nobody to ask and so skips the check."""
        seated = len(self.player_session_users())
        mock = self.kind == "mock"
        odd = seated % 2 != 0 and not mock
        return seated < self.ready_check_floor(min_players) or odd or (bool(unlinked) and not mock)

    async def initiate_ready_check(
        self, thread, initiated_by: str | None = None, initiator: discord.abc.User | None = None,
        post: CardPoster | None = None,
    ) -> str | None:
        """Start a ready check, or re-arm the running one; returns an error string on failure, None on
        success. Only the hard blockers stop it here; a short, odd, or unrecognized roster, and a lobby of
        six that could play a Team Draft, are confirmed by the caller beforehand.

        Arming keeps every answer a seat still in the lobby already gave, so eight players click once.
        `initiator` answers for itself: asking the table is as clear a statement as answering it."""
        blocker = self.ready_check_blocker()
        if blocker:
            return blocker
        non_bot = self.player_session_users()
        rearm = self.ready_check_active
        self.expected_user_ids = {u.get("userID") for u in non_bot}
        self.expected_user_names = {u.get("userID"): u.get("userName") for u in non_bot}
        self.ready_discord_ids &= self.expected_user_ids
        self.ready_socket_ids &= self.expected_user_ids
        self.not_ready_ids &= self.expected_user_ids
        self.ready_check_active = True
        self.ready_check_joined_ids = set()
        self.ready_check_left_ids = set()
        self.ready_check_generation += 1
        generation = self.ready_check_generation
        self._suppress_lobby_full_prompt()
        self._ready_check_started_at = asyncio.get_running_loop().time()
        self.initiated_by = initiated_by
        self.last_cancel_reason = None
        self.ready_check_overdue = False
        if initiator is not None:
            await self._mark_initiator_ready(initiator)
        log.info(
            f"[READY] start event={self.event_id} rearm={rearm} expected={len(self.expected_user_ids)} "
            f"already_ready={len(self.ready_users)} team_draft={self.pairing_mode == 'team'} "
            f"timeout_s={_READY_TIMEOUT_S} expected_ids={self.expected_user_ids}"
        )
        ack = await self._emit_with_ack("readyCheck")
        ack_error = _ack_error_text(ack)
        if ack_error:
            self.ready_check_active = False
            log.warning(f"[READY] rejected event={self.event_id} ack_error={ack_error!r}")
            return f"Draftmancer rejected the ready check: {ack_error}."
        if ack is None:
            log.warning(f"[READY] no_ack event={self.event_id} — starting timer without confirmation")
        self._cancel_ready_timeout()
        self._ready_timeout_task = asyncio.create_task(self._ready_timeout(generation))

        non_bot_names = [u.get("userName") for u in non_bot if u.get("userName")]
        classified = await self._classify_users(non_bot_names) if non_bot_names else []
        if not self._ready_check_is_live(generation):
            await self._abandon_ready_check_setup(generation)
            return None
        await self._show_progress_card(thread, classified, rearm=rearm, post=post)
        await self._refresh_lobby_status()
        await self._maybe_complete_ready_check()
        return None

    async def _mark_initiator_ready(self, initiator: discord.abc.User) -> None:
        """Count the presser as ready when they hold a checked seat. An organizer outside the lobby holds
        none."""
        seat_id = await self.seat_id_for_discord_user(initiator)
        if seat_id is None or seat_id not in self.expected_user_ids:
            return
        self.ready_discord_ids.add(seat_id)
        self.not_ready_ids.discard(seat_id)
        log.info(f"[READY] initiator_ready event={self.event_id} seat={self.seat_name(seat_id)!r}")

    async def _show_progress_card(
        self, thread, classified, *, rearm: bool, post: CardPoster | None = None,
    ) -> None:
        """Put the check's card in front of the pod. A re-arm edits the card players are already looking at,
        a fresh check retires the old one and posts below the conversation. `post` swaps in another way to
        place a fresh card, so /pod-ready can make it the command's own reply."""
        embed = render_ready_check_progress(
            title=self.event_name,
            in_session=classified,
            state="ready",
            ready_arena_names=self.ready_arena_names(),
            initiated_by=self.initiated_by,
            new_drafters=self.new_drafters,
            **self._settings_labels(),
        )
        view = ReadyCheckAnswerView()
        card = self.ready_check_progress_message
        if rearm and card is not None:
            try:
                await card.edit(embed=embed, view=view)
                return
            except Exception:
                log.warning("could not edit ready-check progress card on re-arm", exc_info=True)
        if card is not None:
            try:
                await card.delete()
            except Exception:
                log.info(f"[READY] stale_card_delete_failed event={self.event_id}")
        self.ready_check_progress_message = None
        try:
            self.ready_check_progress_message = await (post or thread.send)(embed=embed, view=view)
        except Exception:
            log.warning("could not post ready-check progress card", exc_info=True)

    def _ready_check_is_live(self, generation: int) -> bool:
        """Whether `generation` is still the running check. Closing a check clears the active flag without
        bumping the generation and a re-arm bumps it without clearing the flag, so both must be checked."""
        return self.ready_check_active and generation == self.ready_check_generation

    async def _abandon_ready_check_setup(self, generation: int) -> None:
        """Bail out of initiate_ready_check when the check it is still building cards for already died.
        Classification and the card edits each take a network round trip, so a decline or a roster change
        lands mid-setup often; without this the setup posts a fresh card advertising a dead check with its
        Ready button disabled, leaving Force Start as the only live control in the thread."""
        log.info(f"[READY] setup_abandoned event={self.event_id} generation={generation}")
        await self._refresh_lobby_status()

    def seat_name(self, user_id: str) -> str | None:
        """A seat's Draftmancer handle, live from the session so a rename mid-check still lines up, falling
        back to the arm-time snapshot for a seat that has left."""
        for user in self.session_users:
            if user.get("userID") == user_id:
                return user.get("userName")
        return self.expected_user_names.get(user_id)

    def is_ready_check_held(self) -> bool:
        return bool(self.ready_check_joined_ids or self.ready_check_left_ids)

    def hold_lines(self) -> tuple[str | None, str | None]:
        """(detail, hint) for a paused check, built fresh each render so a rename mid-pause is picked up."""
        if not self.is_ready_check_held():
            return None, None
        joined = [self.seat_name(uid) or uid for uid in self.ready_check_joined_ids]
        left = [self.seat_name(uid) or uid for uid in self.ready_check_left_ids]
        return roster_hold_detail(joined, left), roster_hold_hint(joined, left)

    def ready_arena_names(self) -> set[str]:
        return self._arena_names(self.ready_users)

    def not_ready_arena_names(self) -> set[str]:
        return self._arena_names(self.not_ready_ids)

    def _arena_names(self, seat_ids) -> set[str]:
        return {name for name in (self.seat_name(uid) for uid in seat_ids) if name}

    async def seat_id_for_discord_user(self, user: discord.abc.User) -> str | None:
        """The lobby seat belonging to a Discord user, by linked Player first and by name match second, so
        someone whose Draftmancer handle merely resembles their Discord name still answers for themselves."""
        seats = [
            (u.get("userID"), u.get("userName")) for u in self.player_session_users() if u.get("userName")
        ]
        if not seats:
            return None
        id_by_name = await asyncio.to_thread(discord_ids_for_names_sync, [name for _, name in seats])
        wanted = str(user.id)
        for user_id, name in seats:
            if id_by_name.get(name) == wanted:
                return user_id
        for matches in (arena_matches_name, arena_matches_token):
            for user_id, name in seats:
                if matches(name, user.display_name) or matches(name, user.name):
                    return user_id
        return None

    async def mark_seat(self, seat_id: str, *, ready: bool, actor: str | None = None) -> str | None:
        """Record one seat's answer, adopting it into the check first when it joined after the check was armed.
        Returns an error string when the click cannot count."""
        if not self.ready_check_active:
            return "No Ready Check is running"
        self._adopt_late_seat(seat_id)
        if ready:
            self.ready_discord_ids.add(seat_id)
            self.not_ready_ids.discard(seat_id)
        else:
            self.ready_discord_ids.discard(seat_id)
            self.ready_socket_ids.discard(seat_id)
            self.not_ready_ids.add(seat_id)
        log.info(
            f"[READY] discord_answer event={self.event_id} seat={self.seat_name(seat_id)!r} ready={ready} "
            f"actor={actor} ready_count={len(self.ready_users)}/{len(self.expected_user_ids)}"
        )
        self._schedule_lobby_refresh()
        if ready:
            await self._maybe_complete_ready_check()
        return None

    def _adopt_late_seat(self, seat_id: str) -> None:
        """Take a seat that joined after the check was armed into it, on that seat's own answer. A pod never
        drafts a table nobody checked, and a player answering for themselves is that seat being checked."""
        if seat_id in self.expected_user_ids:
            return
        self.expected_user_ids.add(seat_id)
        name = self.seat_name(seat_id)
        if name:
            self.expected_user_names[seat_id] = name
        log.info(
            f"[READY] late_seat_adopted event={self.event_id} seat={name!r} "
            f"expected={len(self.expected_user_ids)}"
        )
        self._sync_ready_check_roster()
        self._restart_ready_timeout()

    def _replace_departed_seat(self, name: str) -> None:
        """Retire the seat a reconnecting player left behind, so the check stops waiting on a client that is gone"""
        departed = [
            seat_id for seat_id in self.ready_check_left_ids
            if self.expected_user_names.get(seat_id) == name
        ]
        if not departed:
            return
        for seat_id in departed:
            self.expected_user_ids.discard(seat_id)
            self.expected_user_names.pop(seat_id, None)
            self.ready_discord_ids.discard(seat_id)
            self.ready_socket_ids.discard(seat_id)
            self.not_ready_ids.discard(seat_id)
            log.info(
                f"[READY] reconnect_replaced_seat event={self.event_id} seat={name!r} old={seat_id}"
            )
        self._sync_ready_check_roster()

    def _restart_ready_timeout(self) -> None:
        self._cancel_ready_timeout()
        self._ready_check_started_at = asyncio.get_running_loop().time()
        self._ready_timeout_task = asyncio.create_task(self._ready_timeout(self.ready_check_generation))

    async def stop_ready_check(self, *, actor: str | None = None) -> str | None:
        """Call off a running check. Draftmancer holds no state of its own, so forgetting it here is the
        whole cancellation."""
        if not self.ready_check_active:
            return "No Ready Check is running"
        log.info(f"[READY] stopped event={self.event_id} by={actor}")
        await self._end_ready_check(stopped_reason(actor))
        return None

    async def _classify_users(self, names: list[str]) -> list[tuple[str, str | None]]:
        """Classify Draftmancer usernames against linked players, falling back to guild members
        whose Discord display_name (or username) matches the Draftmancer name's prefix.
        For guild-member matches without a Player row, lazily create one so the participant is
        recorded toward the pod leaderboard at draft completion.

        Leaves `self.new_drafters` holding the seats yet to finish a pod, which the lobby card marks. A
        seat resolved through the guild fallback is one of them: it had no player row a moment ago."""
        classified, self.new_drafters = await asyncio.to_thread(_classify_names_sync, names)
        if not any(dn is None for _, dn in classified):
            return classified
        thread = await self._fetch_thread()
        guild = thread.guild if thread is not None else None
        if guild is None:
            return classified
        unresolved: list[tuple[str, discord.Member]] = []
        out: list[tuple[str, str | None]] = []
        fresh: set[str] = set(self.new_drafters)
        for arena, dn in classified:
            if dn is not None:
                out.append((arena, dn))
                continue
            member = _find_guild_member_for_arena(guild, arena)
            if member is None:
                out.append((arena, None))
                continue
            unresolved.append((arena, member))
            out.append((arena, member.display_name))
            fresh.add(member.display_name)
        if unresolved:
            await asyncio.to_thread(_ensure_players_for_members_sync, unresolved)
        self.new_drafters = frozenset(fresh)
        return out

    def player_session_users(self) -> list[dict]:
        """Session users that count as players: excludes the bot and anyone spectating, and collapses a
        name that opened more than one tab to a single seat so a ghost socket Draftmancer has not yet
        evicted can't inflate the count. Keeps the last socket per name, the live tab after a reconnect."""
        by_name: dict[str, dict] = {}
        for u in self.session_users:
            name = u.get("userName")
            if not name or name == BOT_USER_NAME or u.get("userID") in self.spectator_user_ids:
                continue
            by_name[name] = u
        return list(by_name.values())

    def non_bot_session_names(self) -> list[str]:
        return [u.get("userName") for u in self.player_session_users()]

    def sync_name_nudge(self, classified: list[tuple[str, str | None]]) -> None:
        """Chase the seats the lobby card just failed to resolve, naming them in session chat until every
        one lands. Reads the classification the card already ran, so the repeat costs no queries.
        Pre-draft only, since a rename after the draft starts no longer reaches the roster."""
        unmatched = [arena for arena, display_name in classified if display_name is None]
        if self.drafting or self.draft_complete or self._closed or not unmatched:
            self._stop_name_nudge()
            return
        self._name_nudge_text = name_nudge_text(unmatched)
        self._welcomed_user_ids.difference_update(
            u.get("userID") for u in self.player_session_users() if u.get("userName") in set(unmatched)
        )
        if self._name_nudge_task is None or self._name_nudge_task.done():
            self._name_nudge_task = asyncio.create_task(self._run_name_nudge())

    async def _run_name_nudge(self) -> None:
        while self._name_nudge_text:
            await self.send_chat(self._name_nudge_text)
            await asyncio.sleep(NAME_NUDGE_INTERVAL_S)

    async def welcome_named_seat(self, user_id: str, arena_name: str) -> None:
        """Confirm a rename in session chat the first time it resolves to a player the bot can match. A
        name that matches nobody leaves the seat off the roster, so the chase keeps it instead."""
        if user_id in self._welcomed_user_ids:
            return
        for _, display_name in await self._classify_users([arena_name]):
            if display_name:
                self._welcomed_user_ids.add(user_id)
                await self.send_chat(MSG_DRAFTMANCER_WELCOME.format(name=display_name))

    def _stop_name_nudge(self) -> None:
        self._name_nudge_text = ""
        task, self._name_nudge_task = self._name_nudge_task, None
        if task is not None and not task.done():
            task.cancel()

    async def classified_session_users(self) -> list[tuple[str, str | None]]:
        """Current non-bot session users as (arena_name, linked_display_name_or_None)."""
        names = self.non_bot_session_names()
        return await self._classify_users(names) if names else []

    async def refresh_lobby_now(self) -> None:
        """Re-run classification and edit the lobby card. External hook for /pod-link-arena so the
        lobby reflects the new link immediately. Once the draft completes the roster is frozen:
        _refresh_lobby_status renders the endDraft snapshot, not whoever is in the session now."""
        await self._refresh_lobby_status()

    def _schedule_lobby_refresh(self) -> None:
        """Ask for a re-render, coalescing a burst of answers into one pass. A ready check turns eight seats
        over in a couple of seconds, and one render each outruns what Discord lets the bot edit in a channel:
        the queue that builds up puts the card players are watching seconds behind the state it is meant to
        show, which they read as their answer not registering.

        Every surface a check touches comes through here. State changes a player is waiting on, a draft
        starting or a check closing, render immediately instead."""
        self._lobby_refresh_pending = True
        if self._lobby_refresh_task is not None and not self._lobby_refresh_task.done():
            return
        self._lobby_refresh_task = asyncio.create_task(self._drain_lobby_refreshes())

    async def _drain_lobby_refreshes(self) -> None:
        while self._lobby_refresh_pending:
            await asyncio.sleep(_LOBBY_REFRESH_DEBOUNCE_S)
            if self._lobby_refresh_pending:
                self._lobby_refresh_pending = False
                await self._refresh_lobby_status()

    def _cancel_lobby_refresh(self) -> None:
        self._lobby_refresh_pending = False
        if self._lobby_refresh_task is not None and not self._lobby_refresh_task.done():
            self._lobby_refresh_task.cancel()
        self._lobby_refresh_task = None

    async def bump_lobby_card(self) -> bool:
        """Move the lobby card back to the bottom of its thread, for a lobby that chat has buried, and
        report whether a card is up afterwards. Discord cannot move a message, so the old one is deleted
        and a fresh one posted. Nothing persists the card's id and its buttons carry stable custom_ids, so
        no other surface has to be told; the repost is pinned again, which is how a restart rediscovers it.

        The normal post gate wants the bot to own the session or be reconnecting, which a deliberate bump
        has to bypass: a human owning the lobby would otherwise leave the thread with no card at all.
        """
        old = self.lobby_status_message
        if old is None or self.drafting or self.draft_complete:
            return False
        self.lobby_status_message = None
        self._repost_lobby_card = True
        try:
            try:
                await old.delete()
            except discord.HTTPException:
                log.warning(f"could not delete lobby card to bump it for {self.session_id}", exc_info=True)
                self.lobby_status_message = old
                return False
            await self._refresh_lobby_status()
        finally:
            self._repost_lobby_card = False
        return self.lobby_status_message is not None

    async def _resolve_rsvp_mentions(self, guild: discord.Guild | None) -> dict[int, str]:
        """Resolve `<@id>` mentions in rsvps_yes/rsvps_maybe to guild member display names.
        Used by render_lobby_embed for dedup against in-session display names. Plain-text
        rsvps (when sesh's `Display Usernames as Plain Text` is on) don't need resolution."""
        if guild is None:
            return {}
        ids: set[int] = set()
        for rsvp in (*self.rsvps_yes, *self.rsvps_unconfirmed, *self.rsvps_maybe):
            m = re.match(r"^<@!?(\d+)>$", rsvp.strip())
            if m:
                ids.add(int(m.group(1)))
        out: dict[int, str] = {}
        for mid in ids:
            member = guild.get_member(mid)
            if member is None:
                try:
                    member = await guild.fetch_member(mid)
                except discord.HTTPException:
                    continue
            out[mid] = member.display_name
        return out

    async def _lobby_new_drafters(self, mention_map: dict[int, str]) -> frozenset[str]:
        """The lobby's new-drafter set: the in-session seats plus the rsvp roster entries yet to finish a pod.
        The rsvp half is keyed by the same string the Waiting on / Unconfirmed / Maybe columns render, so a
        plain-text and a mention roster both mark, and it is resolved once since the roster is fixed."""
        if self._rsvp_new_drafters is None:
            resolved: dict[str, str] = {}
            complete = True
            for entry in (*self.rsvps_yes, *self.rsvps_unconfirmed, *self.rsvps_maybe):
                name = _rsvp_display_name(entry, mention_map)
                if name is None:
                    complete = False
                    continue
                resolved[entry] = name
            new_names = await asyncio.to_thread(new_drafters_in_roster_sync, list(resolved.values()))
            computed = frozenset(entry for entry, name in resolved.items() if name in new_names)
            if complete:
                self._rsvp_new_drafters = computed
            return self.new_drafters | computed
        return self.new_drafters | self._rsvp_new_drafters

    def _settings_labels(self) -> dict:
        """Render inputs shared by the lobby + progress cards: the set code that prefixes the title's
        keyrune symbol, the Format / Pairings / Seats footer labels, and the mock flag both cards read to
        drop tournament machinery. A mock draft pairs no matches, so it carries no Pairings label.

        The Seats label leads with the room's own size, so a table holding ten reads as one at a glance and
        a rider window closing to eight shows on the card. Composed here rather than in
        `seating_mode_label`, which the registration embed also renders long before a room exists."""
        mock = self.kind == "mock"
        return {
            "set_code": self.set_code,
            "format_label": pod_format.format_display_with_picks(self.set_code, self.picks_per_pack),
            "pairing_label": None if mock else pairing_label(self.pairing_mode),
            "seating_label": f"({self.max_players}) {seating_mode_label(self.seating_mode)}",
            "mock": mock,
        }

    async def _refresh_lobby_status(self) -> None:
        """Re-render the lobby card from the live session. Roster classification and both card edits run
        together under _lobby_post_lock so concurrent sessionUsers / sessionSpectators broadcasts can't
        clobber each other — without it, a handler that captured a pre-kick roster before its await
        would edit last and resurrect the removed player."""
        if self.abandoned:
            return
        self._lobby_refresh_pending = False
        thread = await self._fetch_thread()
        if thread is None:
            return
        async with self._lobby_post_lock:
            if self.draft_complete and self.tournament_roster:
                names = list(self.tournament_roster)
            else:
                names = self.non_bot_session_names()
            classified = await self._classify_users(names) if names else []
            state = self._compute_state(classified)
            live_check = state in ("ready", "held", "overdue")
            ready_arena_names = self.ready_arena_names()
            hold_detail, hold_hint = self.hold_lines()
            teams = None
            if self.pairing_mode == "team" and state in ("drafting", "complete"):
                teams = self.team_map or await asyncio.to_thread(load_teams_sync, self.event_id)
            mention_map = await self._resolve_rsvp_mentions(thread.guild)
            embed = render_lobby_embed(
                title=self.event_name,
                rsvps_yes=self.rsvps_yes,
                rsvps_unconfirmed=self.rsvps_unconfirmed,
                rsvps_maybe=self.rsvps_maybe,
                in_session=classified,
                state=state,
                draftmancer_url=self.draftmancer_url,
                cancel_reason=self.last_cancel_reason,
                initiated_by=self.initiated_by,
                display_name_by_mention_id=mention_map,
                spectators=self.spectator_names,
                teams=teams,
                new_drafters=await self._lobby_new_drafters(mention_map),
                **self._settings_labels(),
            )
            self._maybe_schedule_lobby_full_prompt(classified)
            self.sync_name_nudge(classified)
            outgrew_vote = len(self.player_session_users()) > max(6, self.team_vote_size)
            if self.team_vote_message is not None and outgrew_vote:
                await self._retire_team_vote_offer()
            round_robin_lobby_moved = len(self.player_session_users()) != self.round_robin_vote_size
            if (self.round_robin_vote_message is not None and round_robin_lobby_moved
                    and not self.round_robin_vote_from_signups):
                await self._retire_round_robin_offer()
                self.round_robin_vote_offered = False
            if state in ("drafting", "complete"):
                view = build_started_lobby_view(self.spectate_url if state == "drafting" else None)
            elif live_check:
                view = build_live_lobby_view(self.draftmancer_url, self.spectate_url)
            else:
                view = LobbyReadyButtonView(
                    draftmancer_url=self.draftmancer_url,
                    show_force_start=(state == "unlinked"),
                    spectate_url=self.spectate_url,
                )
            suppress_empty_reconnect = self.reconnect and not classified
            if (
                self.lobby_status_message is None and self.reconnect and classified
                and not self._lobby_card_adopt_attempted
            ):
                self._lobby_card_adopt_attempted = True
                try:
                    await thread.send(MSG_BOT_RECONNECTED)
                except Exception:
                    log.warning(f"could not post reconnect notice for {self.session_id}", exc_info=True)
                adopted = await _find_pinned_lobby_card(thread, self.bot.user, self.event_name)
                if adopted is not None:
                    self.lobby_status_message = adopted
                    log.info(f"[LIFECYCLE] rehydrate_lobby.adopted_card event={self.event_id} msg={adopted.id}")
            if self.lobby_status_message is None:
                if not suppress_empty_reconnect and (
                    self.is_owner or self.reconnect or self._repost_lobby_card
                ):
                    try:
                        self.lobby_status_message = await thread.send(embed=embed, view=view)
                        try:
                            await self.lobby_status_message.pin()
                        except Exception:
                            log.warning(f"could not pin lobby status for {self.session_id}", exc_info=True)
                    except Exception:
                        log.warning(f"could not post lobby status for {self.session_id}", exc_info=True)
            else:
                try:
                    await self.lobby_status_message.edit(embed=embed, view=view)
                except Exception:
                    log.warning(f"could not edit lobby status for {self.session_id}", exc_info=True)
            if self.kind == "mock":
                await self._update_mock_anchor(classified)

            progress_state = self._progress_card_state(state)
            if self.ready_check_progress_message is not None and progress_state is not None:
                progress_embed = render_ready_check_progress(
                    title=self.event_name,
                    in_session=classified,
                    state=progress_state,
                    ready_arena_names=ready_arena_names,
                    not_ready_arena_names=self.not_ready_arena_names(),
                    cancel_reason=self.last_cancel_reason,
                    hold_detail=hold_detail,
                    hold_hint=hold_hint,
                    draftmancer_url=self.draftmancer_url if self.ready_check_left_ids else None,
                    initiated_by=self.initiated_by,
                    teams=teams,
                    new_drafters=self.new_drafters,
                    **self._settings_labels(),
                )
                if progress_state == "drafting":
                    progress_view = build_started_lobby_view(self.spectate_url)
                elif progress_state == "notready":
                    progress_view = build_not_ready_view()
                elif progress_state == "complete":
                    progress_view = None
                else:
                    progress_view = ReadyCheckAnswerView(paused=progress_state == "held")
                try:
                    await self.ready_check_progress_message.edit(embed=progress_embed, view=progress_view)
                except Exception:
                    log.warning("could not edit ready-check progress card", exc_info=True)

    def _compute_state(self, classified: list[tuple[str, str | None]]) -> str:
        if self.draft_complete:
            return "complete"
        if self.drafting or self._draft_start_in_flight:
            return "drafting"
        if self.ready_check_active:
            if self.is_ready_check_held():
                return "held"
            return "overdue" if self.ready_check_overdue else "ready"
        if self.last_cancel_reason:
            return "notready"
        if not classified:
            return "empty"
        if any(dn is None for _, dn in classified) and self.kind != "mock":
            return "unlinked"
        return "linked"

    def _progress_card_state(self, state: str) -> str | None:
        """The lobby state coerced to one the check card can render, or None to leave the card alone."""
        if self.ready_check_active or state in ("drafting", "complete", "notready"):
            return state
        return None

    async def _on_end_draft(self, *_) -> None:
        if self.draft_cancelled:
            self.draft_cancelled = False
            log.warning(f"[DRAFT] end_ignored_restart event={self.event_id}")
            return
        log.info(f"[DRAFT] end_received event={self.event_id} session_users={len(self.session_users)}")
        self.drafting = False
        self.draft_complete = True
        self._cancel_end_watchdog()
        await self.end_disconnect_stall(delete_watch=True)
        await self._mark_socket_status("draft_done")
        notify_card_close(self.bot, self.event_id)
        self.tournament_roster = self._snapshot_tournament_roster()
        log.info(
            f"[DRAFT] roster_snapshot event={self.event_id} roster_size={len(self.tournament_roster)}"
        )
        await self.refresh_lobby_now()
        if not self.draft_logs:
            log.warning(f"[DRAFT] end_no_payload event={self.event_id}")
        if self.kind == "mock":
            notify_card_phase(self.bot, self.event_id)
            asyncio.create_task(self._finalize_mock())
        else:
            asyncio.create_task(self._launch_matches())

    async def _launch_matches(self) -> None:
        """Offer voice, run the tournament, then flip the scheduled card to Matches In Progress once Round 1
        pairings and their DMs are out. Voice goes first so it reads as an offer for the matches about to
        start. The card edit yields to the pairing messages so a rate limit on the cosmetic status line
        can't delay what players are waiting on."""
        await self.post_voice_offer()
        await start_tournament(self)
        notify_card_phase(self.bot, self.event_id)

    async def _finalize_mock(self) -> None:
        """A mock draft ends at the draft itself — no rounds, no champion. Stamp the event finished so
        the site renders the table + logs, post the breakdown link, then drop the bot from the
        Draftmancer session so it's freed for deckbuilding. Logs are already open to everyone."""
        self.finalized = True
        await asyncio.to_thread(self._mark_mock_finalized)
        notify_pod_complete(self.bot, self.event_id)
        log.info(f"[DRAFT] mock_finalized event={self.event_id}")
        thread = await self._fetch_thread()
        if thread is not None:
            event_url = pod_page_url(self.event_name)
            try:
                await thread.send(MSG_MOCK_COMPLETE.format(
                    event_name=self.event_name, url=event_url, manat=emojis.get("manat"),
                ))
            except Exception:
                log.warning(f"[DRAFT] mock_finalize.thread_post_error event={self.event_id}", exc_info=True)
            await self._announce_mock_complete(thread, event_url)
        await self.disconnect_safely()

    async def _announce_mock_complete(self, thread, event_url: str) -> None:
        """Say the draft finished in the channel the thread hangs off, with the way into both the recap
        and the thread. The anchor card up in that channel also flips to complete, but by then it sits
        above a draft's worth of conversation, so the finish needs its own message at the bottom."""
        channel = thread.parent or self.bot.get_channel(thread.parent_id)
        if channel is None:
            log.info(f"[DRAFT] mock_finalize.no_parent_channel event={self.event_id}")
            return
        try:
            await channel.send(
                MSG_MOCK_COMPLETE_CHANNEL.format(event_name=self.event_name),
                view=build_mock_complete_view(event_url, thread.jump_url),
                allowed_mentions=MOCK_CARD_QUIET,
            )
        except discord.HTTPException:
            log.warning(f"[DRAFT] mock_finalize.channel_post_error event={self.event_id}", exc_info=True)

    def _mark_mock_finalized(self) -> None:
        with SessionLocal() as session:
            finalize_mock_event(session, self.event_id)
            session.commit()

    def _admit_lobby_arrivals(self) -> None:
        """Reaction to a lobby change (join, leave, or rename): add recognized members to the thread, so
        walking into the Draftmancer lobby is enough to land in the pod's conversation. The cards
        themselves re-render from `_refresh_lobby_status`, which every lobby change already runs through."""
        if self.draft_complete:
            return
        asyncio.create_task(self._sync_thread_membership())

    async def _update_mock_anchor(self, roster: list[tuple[str, str | None]]) -> None:
        """Re-render the channel-level mock card in place, and any repost of it with the same content, so
        a bumped card can never drift from the anchor. `roster` is the classification the lobby card was
        just built from, so the two surfaces never disagree about who is at the table.

        Each card is edited under the mentions it was posted with. An edit never notifies anyone, but the
        allowed list still drives the highlight, so re-rendering under the other card's setting would
        either strip the anchor's highlight or light up a repost that deliberately arrived quiet."""
        cards = await self._mock_cards()
        if not cards:
            return
        for card, mentions, thread_url in cards:
            content, embed, view = self._build_mock_card(roster, card.guild, thread_url=thread_url)
            try:
                await card.edit(content=content, embed=embed, view=view, allowed_mentions=mentions)
            except discord.HTTPException:
                log.info(f"[MOCK] card_edit_failed event={self.event_id} msg={card.id}", exc_info=True)

    def _build_mock_card(
        self, roster: list[tuple[str, str | None]], guild: "discord.Guild | None", *,
        thread_url: str | None = None,
    ):
        return build_mock_card(
            event_name=self.event_name, set_code=self.set_code, session_id=self.session_id,
            session_url=self.draftmancer_url, site_url=pod_page_url(self.event_name),
            roster=roster, max_players=self.max_players, state=self._mock_card_state(),
            role_mention=role_mention(guild, MOCK_DRAFT_ROLE_NAME),
            spectate_url=self.spectate_url, canceled_by=self.canceled_by,
            canceled_idle=self.canceled_idle, thread_url=thread_url, created_by=self.created_by,
        )

    async def _mock_cards(self) -> list[tuple["discord.Message", discord.AllowedMentions, str | None]]:
        """Every live copy of the mock card, each paired with the mentions it was posted under and the
        thread link it carries. Only the repost gets that link: it is a plain message, while the anchor
        shows its thread underneath."""
        triples = (
            (await self._mock_anchor(), MOCK_CARD_PING, None),
            (await self._mock_repost(), MOCK_CARD_QUIET, await self._mock_thread_url()),
        )
        return [(card, mentions, thread_url) for card, mentions, thread_url in triples if card is not None]

    async def _mock_thread_url(self) -> str | None:
        thread = await self._fetch_thread()
        return thread.jump_url if thread is not None else None

    async def repost_mock_card(self) -> "discord.Message | None":
        """Post the mock card again at the bottom of its channel, so a lobby still looking for players is
        not lost above the conversation. The anchor and its thread stay where they are — the thread hangs
        off the anchor — and the repost is edited in step with it from then on. Any earlier repost is
        deleted first, so the channel never carries two live copies of one lobby."""
        anchor = await self._mock_anchor()
        if self.kind != "mock" or anchor is None:
            return None
        await self._retire_mock_repost()
        content, embed, view = self._build_mock_card(
            await self.classified_session_users(), anchor.guild, thread_url=await self._mock_thread_url(),
        )
        try:
            repost = await anchor.channel.send(
                content=content, embed=embed, view=view, allowed_mentions=MOCK_CARD_QUIET,
            )
        except discord.HTTPException:
            log.warning(f"[MOCK] repost_send_failed event={self.event_id}", exc_info=True)
            return None
        self._mock_repost_message = repost
        self._arm_mock_idle_timer()
        await asyncio.to_thread(
            record_mock_repost_sync, self.event_id, str(repost.channel.id), str(repost.id),
        )
        log.info(f"[MOCK] card_reposted event={self.event_id} msg={repost.id}")
        return repost

    async def _mock_repost(self) -> "discord.Message | None":
        """The reposted card, resolved from the event row so a restart mid-lobby keeps editing it."""
        if self._mock_repost_message is not None:
            return self._mock_repost_message
        recorded = await asyncio.to_thread(mock_repost_sync, self.event_id)
        if recorded is None:
            return None
        channel_id, message_id = recorded
        channel = self.bot.get_channel(int(channel_id))
        if channel is None:
            return None
        try:
            self._mock_repost_message = await channel.fetch_message(int(message_id))
        except discord.HTTPException:
            log.info(f"[MOCK] repost_fetch_failed event={self.event_id}", exc_info=True)
            return None
        return self._mock_repost_message

    async def _retire_mock_repost(self) -> None:
        repost = await self._mock_repost()
        self._mock_repost_message = None
        await asyncio.to_thread(record_mock_repost_sync, self.event_id, None, None)
        if repost is None:
            return
        try:
            await repost.delete()
        except discord.HTTPException:
            log.info(f"[MOCK] repost_delete_failed event={self.event_id}", exc_info=True)

    def _note_mock_lobby_activity(self) -> None:
        """Restart the inactivity clock when the Draftmancer roster actually changes. Every sessionUsers
        broadcast lands here, so the seat signature is what decides: Draftmancer re-broadcasts the roster
        for collection uploads and ready flags too, and those are not somebody turning up."""
        if self.kind != "mock":
            return
        signature = tuple(sorted(self.non_bot_session_names()))
        if signature == self._mock_lobby_signature:
            return
        self._mock_lobby_signature = signature
        self._arm_mock_idle_timer()

    def _arm_mock_idle_timer(self) -> None:
        """Start the window over. A draft under way, a finished draft, and a closed lobby all have nothing
        left to expire, so they hold no timer.

        The deadline lives in this task rather than a scheduled job because the activity that resets it is
        in memory too. A restart reconnects the lobby and arms a fresh window off the first roster
        broadcast, which is the forgiving side to err on: the lobby outlives the bot going down."""
        if self.kind != "mock":
            return
        self._cancel_mock_idle_timer()
        if self._closed or self.drafting or self.draft_complete or self._mock_lobby_closed():
            return
        self._mock_idle_task = asyncio.create_task(self._close_mock_lobby_when_idle())

    def _cancel_mock_idle_timer(self) -> None:
        if self._mock_idle_task is not None and not self._mock_idle_task.done():
            self._mock_idle_task.cancel()
        self._mock_idle_task = None

    async def _close_mock_lobby_when_idle(self) -> None:
        """Sleeps out the window, then deletes the event. Drops its own handle first: the teardown disarms
        the timer on its way through, and this task is the timer, so a held handle would cancel the close
        half-done."""
        await asyncio.sleep(settings.pod_mock_inactivity_minutes * 60)
        if self._closed or self.drafting or self.draft_complete or self._mock_lobby_closed():
            return
        self._mock_idle_task = None
        log.info(
            f"[MOCK] idle_close event={self.event_id} "
            f"minutes={settings.pod_mock_inactivity_minutes} seated={len(self.non_bot_session_names())}"
        )
        await cancel_pod_event(self.event_id, idle=True)

    def _mock_lobby_closed(self) -> bool:
        return self.canceled_by is not None or self.canceled_idle

    async def stand_down_idle_lobby(self) -> None:
        """Retire a mock lobby that went quiet: the card names the window that closed it, the thread says
        so, then archives so a lobby nobody answered leaves the sidebar. Archiving is reversible, so a
        later reply reopens the thread; the event row is deleted by the caller either way."""
        await self.mark_canceled(idle=True)
        thread = await self._fetch_thread()
        if thread is None:
            return
        window = inactivity_window_text(settings.pod_mock_inactivity_minutes)
        try:
            await thread.send(MSG_MOCK_CLOSED_IDLE.format(window=window))
        except discord.HTTPException:
            log.info(f"[MOCK] idle_notice_failed event={self.event_id}", exc_info=True)
        try:
            await thread.edit(archived=True, reason="Mock draft lobby closed after inactivity")
        except discord.HTTPException:
            log.info(f"[MOCK] idle_archive_failed event={self.event_id}", exc_info=True)

    def _mock_card_state(self) -> str:
        """A lobby the bot does not hold reads as opening, not open: the card's link and Join button are
        what send players into the session, and until ownership lands the first arrival takes it."""
        if self._mock_lobby_closed():
            return STATE_CANCELED
        if self.draft_complete:
            return STATE_COMPLETE
        if self.drafting:
            return STATE_DRAFTING
        if not self.is_owner:
            return STATE_OPENING
        return STATE_OPEN

    async def _mock_anchor(self) -> "discord.Message | None":
        """The card `/mock-draft` posted, resolved from the thread instead of a held reference: the
        thread was created off that message, so they share an id. A restart mid-lobby can keep editing
        the same card that way."""
        if self._mock_anchor_message is not None:
            return self._mock_anchor_message
        thread = await self._fetch_thread()
        parent = getattr(thread, "parent", None)
        if parent is None:
            return None
        try:
            self._mock_anchor_message = await parent.fetch_message(self.thread_id)
        except discord.HTTPException:
            log.info(f"[MOCK] anchor_fetch_failed event={self.event_id}", exc_info=True)
            return None
        return self._mock_anchor_message

    async def mark_canceled(self, actor: str | None = None, *, idle: bool = False) -> None:
        """Flip a mock draft's anchor card to canceled before the event row goes away. Tournament pods
        retire their RSVP card through the cancel hook instead, so this is mock-only."""
        if self.kind != "mock":
            return
        self.canceled_by = actor
        self.canceled_idle = idle
        self._cancel_mock_idle_timer()
        roster = await self.classified_session_users()
        await self._update_mock_anchor(roster)

    async def _sync_thread_membership(self) -> None:
        """Admit Draftmancer joiners we recognize as guild members, so the people drafting see the thread
        without being manually invited."""
        thread = await self._fetch_thread()
        guild = thread.guild if thread is not None else None
        if guild is None:
            return
        names = self.non_bot_session_names()
        if not names:
            return
        discord_id_by_name = await asyncio.to_thread(discord_ids_for_names_sync, names)
        for name in names:
            discord_id = discord_id_by_name.get(name)
            member = guild.get_member(int(discord_id)) if discord_id else _find_guild_member_for_arena(guild, name)
            if member is not None:
                await self.admit_to_thread(member)

    async def admit_to_thread(self, member: discord.Member) -> tuple[bool, bool]:
        """Put a joiner in the pod thread and on the pod roles, at most once per member. Returns the
        (first pod, holds the mock ping) pair the Join Draft reply renders its roles notice from; only a
        mock has a ping of its own to grant, so a tournament pod always reports False for the second.
        Shared by that button and the Draftmancer arrival sweep, so clicking Join and walking into the
        lobby unprompted land in the same place."""
        if str(member.id) in self._thread_added_ids:
            return False, False
        thread = await self._fetch_thread()
        if thread is None:
            return False, False
        self._thread_added_ids.add(str(member.id))
        if self.kind == "mock":
            grants = await grant_mock_draft_role(member)
        else:
            grants = (await grant_pod_drafters(member), False)
        try:
            await thread.add_user(member)
            log.info(f"thread_add event={self.event_id} member={member.display_name}")
        except discord.HTTPException:
            log.info(f"thread_add_failed event={self.event_id} member={member.display_name}", exc_info=True)
        return grants

    def _snapshot_tournament_roster(self) -> list[str]:
        """The locked drafter list, frozen at endDraft. Prefers the draft log's seated users — immune
        to players closing their tab at draft end or spectators joining after — and falls back to
        whoever is in the session right now.

        Draftmancer's own bots stay in the artifact, where the replay needs them to reconstruct the passing,
        but they play no rounds and are dropped here."""
        payload = self._full_draft_log()
        users = payload.get("users") if isinstance(payload, dict) else None
        if isinstance(users, dict):
            seated = [
                u.get("userName") for u in users.values()
                if isinstance(u, dict) and u.get("userName") and not u.get("isBot")
            ]
            if seated:
                return seated
        return self.non_bot_session_names()

    async def _on_draft_log(self, log_payload) -> None:
        if not isinstance(log_payload, dict):
            return
        users = log_payload.get("users") or {}
        if isinstance(users, dict):
            for user in users.values():
                name = user.get("userName") if isinstance(user, dict) else None
                if name:
                    self.draft_logs[name] = log_payload
                    break
        log.info(f"[DRAFT] log_stored event={self.event_id} total={len(self.draft_logs)}")
        await asyncio.to_thread(self._persist_draft_log_gz, log_payload)

    async def _on_share_decklist(self, payload) -> None:
        """Draftmancer streams shareDecklist to the session owner on every deckbuild edit (card moved
        main↔side, lands set) after the draft ends — there is no submit gate. Keep the stored log's per-seat
        decklist current in memory only; persist_decklists_from_log writes the settled result at round 2,
        by which point round 1 has been played. Mocks disconnect at draft end and are never reviewed, so they
        are ignored; as a non-player owner the bot receives the full decklist, not hashes-only. A seat that
        can't be matched means the edit arrived under a reconnected userID the draft log doesn't know, and
        Draftmancer drops it from the log too — logged so a missing corrected deck can be traced."""
        if self.kind == "mock" or not isinstance(payload, dict):
            return
        user_id = payload.get("userID")
        decklist = payload.get("decklist")
        if not user_id or not isinstance(decklist, dict) or decklist.get("main") is None:
            return
        log_payload = self._full_draft_log()
        users = log_payload.get("users") if isinstance(log_payload, dict) else None
        seat = users.get(user_id) if isinstance(users, dict) else None
        if not isinstance(seat, dict):
            known = list(users.keys()) if isinstance(users, dict) else None
            log.info(f"[DECK] share_decklist.unmatched event={self.event_id} user={user_id} known_seats={known}")
            return
        seat["decklist"] = decklist
        main = decklist.get("main") or []
        side = decklist.get("side") or []
        log.info(
            f"[DECK] share_decklist.applied event={self.event_id} name={seat.get('userName')!r} "
            f"main={len(main)} side={len(side)}"
        )

    def persist_decklists_from_log(self) -> bool:
        """Re-persist the artifact with players' post-draft deckbuild edits as round 2 opens, once round 1
        has settled the decks. shareDecklist keeps the in-memory log current live; this is the settling write,
        fired by persist_round_entry_artifacts for both bracket and Swiss pods. Returns False when no draft
        log is in memory (e.g. after a mid-event bot restart), leaving the draft-end decks in place."""
        log_payload = self._full_draft_log()
        if not isinstance(log_payload, dict):
            log.info(f"[DECK] persist_decklists.skip event={self.event_id} reason=no_log_in_memory")
            return False
        self._persist_draft_log_gz(log_payload)
        log.info(f"[DECK] persist_decklists.done event={self.event_id}")
        return True

    def _full_draft_log(self) -> dict | None:
        return next(iter(self.draft_logs.values()), None)

    def _persist_draft_log_gz(self, log_payload: dict) -> None:
        try:
            compact = build_compact(log_payload)
            blob = gzip.compress(json.dumps(compact, separators=(",", ":")).encode("utf-8"))
        except Exception:
            log.warning(f"[DRAFT] persist.compact_error event={self.event_id}", exc_info=True)
            asyncio.run_coroutine_threadsafe(
                bot_log_mod.get(self.bot).post(
                    f"Draft log compact/gzip failed for event `{self.event_id}` — data not persisted.",
                    fingerprint=f"persist_compact_error:{self.event_id}",
                    tag="DRAFT",
                ),
                self.bot.loop,
            )
            return
        try:
            with SessionLocal() as session:
                event = session.execute(
                    select(PodDraftEvent).where(PodDraftEvent.id == self.event_id)
                ).scalar_one_or_none()
                if event is None:
                    log.warning(f"[DRAFT] persist.event_missing event={self.event_id}")
                    return
                event.draft_log_gz = blob
                event.draft_log = compact
                apply_seat_indexes(session, self.event_id, compact.get("seats") or [])
                session.commit()
                log.info(f"[DRAFT] persist.done event={self.event_id} bytes={len(blob)}")
        except Exception:
            log.warning(f"[DRAFT] persist.db_error event={self.event_id}", exc_info=True)
            asyncio.run_coroutine_threadsafe(
                bot_log_mod.get(self.bot).post(
                    f"Draft log DB persist failed for event `{self.event_id}` — data not saved.",
                    fingerprint=f"persist_db_error:{self.event_id}",
                    tag="DRAFT",
                ),
                self.bot.loop,
            )

    async def _fetch_thread(self):
        try:
            cached = self.bot.get_channel(self.thread_id)
            if cached is not None:
                return cached
            return await self.bot.fetch_channel(self.thread_id)
        except Exception:
            log.warning(f"could not fetch thread {self.thread_id}", exc_info=True)
            return None

    def persist_seat_indexes_from_log(self) -> bool:
        """Write seat_index from the in-memory draft log to participants so round-1 pairing and every
        later re-render read the same seating. Idempotent with _persist_draft_log_gz.
        Returns False when no draft log is in memory yet."""
        payload = self._full_draft_log()
        users = payload.get("users") if isinstance(payload, dict) else None
        if not isinstance(users, dict):
            return False
        seats = [u.get("userName") for u in users.values() if isinstance(u, dict)]
        if not any(seats):
            return False
        with SessionLocal() as session:
            apply_seat_indexes(session, self.event_id, seats)
            session.commit()
        return True

    async def _on_set_ready(self, user_id, ready_state) -> None:
        """Draftmancer's answer to the prompt, one input among two. A Not Ready only un-ticks the seat: the
        prompt is a SweetAlert that fires one whenever another popup replaces it, so it reports refusals
        nobody made."""
        ready = _is_ready_state(ready_state)
        log.info(
            f"[READY] set_ready event={self.event_id} user={user_id} state={ready_state!r} "
            f"parsed={ready} active={self.ready_check_active} expected={user_id in self.expected_user_ids}"
        )
        if not self.ready_check_active or user_id not in self.expected_user_ids:
            return
        if ready:
            self.ready_socket_ids.add(user_id)
            self.not_ready_ids.discard(user_id)
        else:
            elapsed = asyncio.get_running_loop().time() - self._ready_check_started_at
            if elapsed < _READY_DEBOUNCE_S:
                log.info(
                    f"[READY] residual_notready_ignored event={self.event_id} user={user_id} "
                    f"elapsed_s={elapsed:.2f}"
                )
                return
            if user_id in self.ready_discord_ids:
                log.info(f"[READY] socket_notready_overridden event={self.event_id} user={user_id}")
                return
            self.ready_socket_ids.discard(user_id)
            self.not_ready_ids.add(user_id)
        self._schedule_lobby_refresh()
        await self._maybe_complete_ready_check()

    def _sync_ready_check_roster(self) -> None:
        """Compare the lobby against the roster the check was armed on. The table that was checked is the
        table that drafts, so any arrival or departure parks the check instead of resizing the pod."""
        if not self.ready_check_active:
            return
        present = {u.get("userID") for u in self.player_session_users()}
        joined = present - self.expected_user_ids
        left = self.expected_user_ids - present
        if not joined and not left:
            if self.is_ready_check_held():
                log.info(f"[READY] hold_released event={self.event_id}")
            self.ready_check_joined_ids = set()
            self.ready_check_left_ids = set()
            return
        if (joined, left) != (self.ready_check_joined_ids, self.ready_check_left_ids):
            log.info(f"[READY] held event={self.event_id} joined={joined} left={left}")
        self.ready_check_joined_ids = joined
        self.ready_check_left_ids = left

    async def _adopt_recognized_arrivals(self) -> None:
        """A player the bot recognizes walking in mid-check joins already ready: turning up is the answer. A
        seat it cannot place parks the check instead, which is the arrival worth a human looking at. A mock
        places nobody by Arena handle, so every arrival counts there."""
        arrivals = [(uid, self.seat_name(uid)) for uid in sorted(self.ready_check_joined_ids)]
        names = [name for _, name in arrivals if name]
        if not names:
            return
        classified = await self._classify_users(names)
        recognized = {arena for arena, display in classified if display is not None}
        still_seated = {u.get("userID") for u in self.player_session_users()}
        for seat_id, name in arrivals:
            if seat_id not in still_seated:
                log.info(f"[READY] arrival_left_before_adoption event={self.event_id} seat={name!r}")
                continue
            if name is None or not (self.kind == "mock" or name in recognized):
                continue
            self._replace_departed_seat(name)
            self._adopt_late_seat(seat_id)
            self.ready_discord_ids.add(seat_id)
            log.info(f"[READY] arrival_auto_ready event={self.event_id} seat={name!r}")

    async def _maybe_complete_ready_check(self) -> None:
        """Start the draft once every seat the check was armed on has answered ready. A paused check never
        starts."""
        if not self.ready_check_active or self.is_ready_check_held():
            return
        if self.expected_user_ids and self.ready_users >= self.expected_user_ids:
            await self._complete_ready_check()

    async def _complete_ready_check(self) -> None:
        if not self.ready_check_active:
            return
        log.info(f"[READY] complete event={self.event_id} ready_count={len(self.ready_users)}")
        self.ready_check_active = False
        self._clear_ready_answers()
        self._cancel_ready_timeout()
        await self._start_draft()

    def _clear_ready_answers(self) -> None:
        self.ready_discord_ids = set()
        self.ready_socket_ids = set()
        self.not_ready_ids = set()
        self.ready_check_joined_ids = set()
        self.ready_check_left_ids = set()
        self.ready_check_overdue = False

    async def force_start(self, *, post: CardPoster | None = None) -> str | None:
        """Bypass the ready-check and emit startDraft directly. Returns an error string on failure, None on success."""
        if not self.sio.connected:
            return "Draftmancer session is not connected"
        if self.draft_complete:
            return "Draft is already complete"
        if self.drafting:
            return "Draft is already in progress"
        self._cancel_ready_timeout()
        self.ready_check_active = False
        self._clear_ready_answers()
        self.last_cancel_reason = None
        log.info(f"[READY] force_start event={self.event_id} ready_check_bypassed=True")
        await self._start_draft(post=post)
        return None

    async def pause_draft(self) -> str | None:
        """Emit pauseDraft to Draftmancer. Pick-phase only. Returns an error string or None."""
        if not self.sio.connected:
            return "Draftmancer session is not connected"
        if not self.drafting or self.draft_complete:
            return "No draft in progress to pause"
        if self.draft_paused:
            return "The draft is already paused"
        try:
            await self.sio.emit("pauseDraft")
        except Exception:
            log.exception(f"[DRAFT] pause_failed event={self.event_id}")
            return "Could not pause the draft, see logs"
        self.draft_paused = True
        log.info(f"[DRAFT] paused event={self.event_id}")
        return None

    async def resume_draft(self) -> str | None:
        """Emit resumeDraft to Draftmancer. Returns an error string or None."""
        if not self.sio.connected:
            return "Draftmancer session is not connected"
        if not self.drafting or self.draft_complete:
            return "No draft in progress to resume"
        if not self.draft_paused:
            return "The draft isn't paused"
        try:
            await self.sio.emit("resumeDraft")
        except Exception:
            log.exception(f"[DRAFT] resume_failed event={self.event_id}")
            return "Could not resume the draft, see logs"
        self.draft_paused = False
        log.info(f"[DRAFT] resumed event={self.event_id}")
        return None

    async def _on_user_disconnected(self, payload) -> None:
        """Draftmancer broadcasts the whole disconnected set on every drop and on every partial return, so
        the payload is the state and not a change. A seat already handed to a bot stays in that set, and
        is dropped here so the thread only ever names the players still being waited on."""
        if not self.drafting or self.draft_complete:
            return
        entries = (payload or {}).get("disconnectedUsers") or {}
        waiting = sorted(
            name for name in (user.get("userName") for user in entries.values())
            if name and name not in self.bot_filled_names
        )
        if waiting == self.disconnected_names:
            return
        if not waiting:
            await self._end_stall_on_return()
            return
        first_drop = not self.disconnected_names
        self.disconnected_names = waiting
        self.stall_names.update(waiting)
        log.warning(f"[DRAFT] players_disconnected event={self.event_id} names={waiting}")
        if first_drop:
            self._disconnect_at = int(datetime.now(timezone.utc).timestamp())
            self._disconnect_watch_task = asyncio.create_task(self._open_disconnect_watch())
        else:
            await self._refresh_disconnect_watch()
        if self._disconnect_offer_task is None or self._disconnect_offer_task.done():
            self._disconnect_offer_task = asyncio.create_task(self._offer_disconnect_choices())

    async def _on_resume_on_reconnection(self, *_payload) -> None:
        """Draftmancer resumes the draft the moment the last missing player returns, and says nothing
        more about who came back. A replacement resumes it too, and settles the cards before it emits."""
        if not self.disconnected_names:
            return
        await self._end_stall_on_return()

    async def _end_stall_on_return(self) -> None:
        """A stall the thread was never told about ends as quietly as it started. One it was told about
        names everyone it waited on, a player who came back early included. A stall that never reached the
        vote leaves its two cards behind as removable, so a flapping connection posts one pair at a time."""
        announced = self._disconnect_message is not None or self._disconnect_offer_message is not None
        card = pod_disconnect.build_back_embed(sorted(self.stall_names)) if announced else None
        watch = self._disconnect_message
        voted = self._disconnect_offer_message is not None
        back = await self.end_disconnect_stall(card=card)
        if voted:
            self._flapped_messages = []
        else:
            self._flapped_messages = [message for message in (watch, back) if message is not None]

    async def _open_disconnect_watch(self) -> None:
        """Nothing is said for the first seconds, so a drop that resolves at once costs no messages."""
        try:
            await asyncio.sleep(_DISCONNECT_BLIP_S)
        except asyncio.CancelledError:
            return
        if not self.drafting or self.draft_complete or not self.disconnected_names:
            return
        thread = await self._fetch_thread()
        if thread is None:
            return
        try:
            self._disconnect_message = await thread.send(embed=self._disconnect_watch_embed())
        except discord.HTTPException:
            log.warning(f"[DRAFT] disconnect_card_failed event={self.event_id}", exc_info=True)
        await self._delete_flapped_cards()

    async def _refresh_disconnect_watch(self) -> None:
        """A second player dropping into a live wait joins the card already up, so one stall is one card."""
        if self._disconnect_message is None:
            return
        try:
            await self._disconnect_message.edit(embed=self._disconnect_watch_embed())
        except discord.HTTPException:
            log.warning(f"[DRAFT] disconnect_card_failed event={self.event_id}", exc_info=True)

    def _disconnect_watch_embed(self) -> "discord.Embed":
        opens_at = (self._disconnect_at or 0) + _DISCONNECT_GRACE_S
        return pod_disconnect.build_waiting_embed(self.disconnected_names, opens_at=opens_at)

    async def _offer_disconnect_choices(self) -> None:
        """Once the wait runs out with nobody back, post the vote as its own message so the table gets a
        fresh ping instead of an edit nobody sees. A return inside the window cancels this, and a player
        who reconnects is never asked about."""
        try:
            await asyncio.sleep(_DISCONNECT_GRACE_S)
        except asyncio.CancelledError:
            return
        if not self.drafting or self.draft_complete or not self.disconnected_names:
            return
        thread = await self._fetch_thread()
        if thread is None:
            return
        needed = pod_disconnect.votes_needed(len(self.player_session_users()))
        try:
            self._disconnect_offer_message = await thread.send(
                embed=pod_disconnect.build_offer_embed(
                    self.disconnected_names, dropped_at=self._disconnect_at or 0, needed=needed),
                view=pod_disconnect.build_offer_view(self.event_id),
            )
        except discord.HTTPException:
            log.warning(f"[DRAFT] disconnect_offer_failed event={self.event_id}", exc_info=True)
            return
        self._disconnect_message = None
        log.info(f"[DRAFT] disconnect_offer_posted event={self.event_id} needed={needed}")

    def clear_disconnect_state(self) -> "discord.Message | None":
        """Forget the stall and hand back its vote card, the one message an ending still has to change."""
        tasks = (self._disconnect_watch_task, self._disconnect_offer_task)
        self._disconnect_watch_task = self._disconnect_offer_task = None
        for task in tasks:
            if task is not None:
                task.cancel()
        self.disconnected_names = []
        self.stall_names = set()
        self._disconnect_at = None
        offer = self._disconnect_offer_message
        self._disconnect_message = self._disconnect_offer_message = None
        return offer

    async def end_disconnect_stall(
        self, *, card: "discord.Embed | None" = None, delete_watch: bool = False,
    ) -> "discord.Message | None":
        """Close out a stall and hand back the card it posted. Nothing is rewritten, so the thread keeps the
        record of who dropped and how the table voted. The vote card loses its buttons, so nobody clicks a
        decision into a draft that moved on, and `card` posts at the bottom of the thread, where a table that
        kept talking through the stall will see it."""
        watch = self._disconnect_message
        offer = self.clear_disconnect_state()
        if delete_watch and watch is not None:
            try:
                await watch.delete()
            except discord.HTTPException:
                log.info(f"[DRAFT] disconnect_watch_cleanup_failed event={self.event_id}", exc_info=True)
        if offer is not None:
            try:
                await offer.edit(view=None)
            except discord.HTTPException:
                log.info(f"[DRAFT] disconnect_end_failed event={self.event_id}", exc_info=True)
        if card is None:
            return None
        thread = await self._fetch_thread()
        if thread is None:
            return None
        try:
            return await thread.send(embed=card)
        except discord.HTTPException:
            log.warning(f"[DRAFT] disconnect_end_card_failed event={self.event_id}", exc_info=True)
            return None

    async def _delete_flapped_cards(self) -> None:
        """Clear the previous stall's pair once a new one is announced, so a connection that drops and
        returns over and over leaves one disconnect card and one return card in the thread."""
        messages = self._flapped_messages
        self._flapped_messages = []
        if not messages:
            return
        if not await pod_disconnect.delete_cards(messages):
            log.info(f"[DRAFT] disconnect_flap_cleanup_failed event={self.event_id}")

    async def replace_disconnected_with_bots(self) -> str | None:
        """Hand every seat still missing to a Draftmancer bot so the draft runs on. Their picks so far
        stay in the draft, and the bot takes it from there. Returns an error string or None."""
        if not self.sio.connected:
            return "Draftmancer session is not connected"
        if not self.drafting or self.draft_complete:
            return "No draft in progress"
        names = self.disconnected_names
        if not names:
            return "Nobody is disconnected right now"
        try:
            await self.sio.emit("replaceDisconnectedPlayers")
        except Exception:
            log.exception(f"[DRAFT] replace_disconnected_failed event={self.event_id}")
            return "Could not replace the disconnected players, see logs"
        self.bot_filled_names.update(names)
        log.warning(f"[DRAFT] disconnected_replaced event={self.event_id} names={names}")
        return None

    async def restart_draft(
        self, thread, *, initiated_by: str | None = None, post: CardPoster | None = None,
    ) -> str | None:
        """Stop the in-flight draft on Draftmancer and reopen the lobby with a fresh ready check on the
        same session. Pick-phase only. `draft_cancelled` swallows the endDraft that stopDraft triggers so
        the tournament phase never fires. A roster too short or odd to check gets the reopened-lobby card
        and its Ready Check button instead, which is every restart a dropped player caused. Returns an
        error string (nothing changed) or None."""
        if not self.sio.connected:
            return "Draftmancer session is not connected"
        if self.draft_complete:
            return "The draft is already complete, nothing to restart"
        if not self.drafting:
            return "No draft in progress to restart"
        log.warning(f"[DRAFT] restart event={self.event_id} by={initiated_by}")
        if initiated_by:
            try:
                await (post or thread.send)(content=MSG_POD_RESTARTED.format(actor=initiated_by))
            except Exception:
                log.warning(f"[DRAFT] restart.actor_notice_failed event={self.event_id}", exc_info=True)
        self.draft_cancelled = True
        self.draft_paused = False
        self.drafting = False
        self._cancel_end_watchdog()
        await self.end_disconnect_stall(delete_watch=True)
        try:
            await self.sio.emit("stopDraft")
        except Exception:
            self.draft_cancelled = False
            self.drafting = True
            log.exception(f"[DRAFT] restart.stop_failed event={self.event_id}")
            return "Could not stop the draft, see logs"
        await asyncio.sleep(_RESTART_SETTLE_S)
        self.draft_logs = {}
        self._arm_mock_idle_timer()
        await self._mark_socket_status("connected")
        notify_card_phase(self.bot, self.event_id)
        await self.refresh_lobby_now()
        if self.ready_check_needs_confirm([], min_players=_RESTART_READY_MIN_PLAYERS):
            skip_reason = "roster is short or odd, and a restart has nobody to confirm with"
        else:
            skip_reason = await self.initiate_ready_check(thread, initiated_by=initiated_by)
        if skip_reason is not None:
            log.info(f"[DRAFT] restart.ready_skipped event={self.event_id} reason={skip_reason!r}")
            try:
                await thread.send(MSG_POD_RESTARTING)
            except Exception:
                log.warning(f"[DRAFT] restart.notice_failed event={self.event_id}", exc_info=True)
            await self.bump_lobby_card()
        return None

    async def _start_draft(self, *, post: CardPoster | None = None) -> None:
        """Send the table into the draft. `_draft_start_in_flight` covers the second the seating re-push and
        the startDraft ack take, where the check is closed and `drafting` is not yet set: a lobby broadcast
        landing there rendered a pod with no check and no draft, which the cards read as a stopped check."""
        if self._odd_roster_blocks_start():
            await self._refuse_odd_roster_start(post=post)
            return
        self._draft_start_in_flight = True
        try:
            await self._start_draft_inner(post=post)
        finally:
            self._draft_start_in_flight = False

    async def _start_draft_inner(self, *, post: CardPoster | None = None) -> None:
        await self._apply_bot_fill()
        await self._reapply_seating_if_set()
        result = await self._emit_with_ack("startDraft")
        log.info(f"[DRAFT] start_ack event={self.event_id} ack={result!r}")
        error_text = _ack_error_text(result)
        if error_text is not None:
            log.warning(f"[DRAFT] start_failed event={self.event_id} error={error_text!r}")
            await bot_log_mod.get(self.bot).post(
                f"startDraft failed for event `{self.event_id}`: {error_text}",
                fingerprint=f"start_draft_failed:{self.event_id}",
                tag="DRAFT",
            )
            thread = await self._fetch_thread()
            if thread is not None:
                try:
                    await (post or thread.send)(
                        content=f"⚠️ Could not start the draft: {error_text}\n"
                                f"Use `/pod-takeover` to take control of the Draftmancer session manually"
                    )
                except Exception:
                    log.warning("[DRAFT] start_failed.thread_post_error", exc_info=True)
            return
        self.drafting = True
        self.draft_cancelled = False
        self.draft_paused = False
        self._stop_name_nudge()
        self._cancel_mock_idle_timer()
        log.info(f"[DRAFT] started event={self.event_id} session_users={len(self.session_users)}")
        self._schedule_end_watchdog()
        await self._retire_lobby_full_prompt()
        await self._retire_lobby_waiting()
        await self._retire_team_vote_offer()
        await self._retire_round_robin_offer()
        await self._retire_format_poll_offer()
        await asyncio.to_thread(self._seed_participants_at_draft_start)
        notify_card_phase(self.bot, self.event_id)
        notify_pod_drafting(self.bot, self.event_id)
        if self.pairing_mode == "team":
            await assign_teams_at_draft_start(self)
        await self.refresh_lobby_now()
        thread = await self._fetch_thread()
        if thread is not None:
            try:
                await (post or thread.send)(content="**🎉 Draft started!**")
            except Exception:
                log.warning("[DRAFT] started.thread_post_error", exc_info=True)
            if self.kind != "mock":
                seated = len(self.player_session_users())
                notify_underfill_fired(
                    self.bot, self.event_id, player_count=seated, thread_url=thread.jump_url,
                )
                notify_rally_fired(self.bot, self.event_id)

    def _odd_roster_blocks_start(self) -> bool:
        """Whether an odd roster must stop this draft. A mock plays no rounds, so it drafts happily at seven,
        and the bench pads its tables with bots."""
        if self.kind == "mock" or not settings.is_production:
            return False
        return len(self.player_session_users()) % 2 != 0

    async def _refuse_odd_roster_start(self, *, post: CardPoster | None = None) -> None:
        """Every pairing mode needs an even table, and a ready check can complete after someone leaves.
        Refusing before the emit keeps the lobby open instead of stranding a fully drafted pod at the endDraft
        pairing error."""
        count = len(self.player_session_users())
        log.warning(f"[DRAFT] start_refused_odd_roster event={self.event_id} players={count}")
        thread = await self._fetch_thread()
        if thread is None:
            return
        try:
            await (post or thread.send)(
                content=f"⚠️ Pairings need an even number of players, but {count} are seated. "
                        "The draft won't start until the roster is evened out"
            )
        except Exception:
            log.warning("[DRAFT] start_refused.thread_post_error", exc_info=True)

    def _seed_participants_at_draft_start(self) -> None:
        """Insert pod_draft_participants for every non-bot Draftmancer userName now that the draft
        has begun (lobby locked). Idempotent — start_tournament will re-call with the same roster
        as a safety net after endDraft."""
        roster = self.non_bot_session_names()
        if not roster:
            log.warning(f"[DRAFT] seed_participants.empty_roster event={self.event_id}")
            return
        try:
            with SessionLocal() as session:
                seed_event_participants(session, self.event_id, roster)
                session.commit()
            log.info(f"[DRAFT] seeded_participants event={self.event_id} count={len(roster)}")
        except Exception:
            log.warning(f"[DRAFT] seed_participants.error event={self.event_id}", exc_info=True)

    async def seating_lobby_order(self) -> list[tuple[str, str]]:
        """Current non-bot lobby users in Draftmancer order, as (userName, display_label)."""
        names = [u.get("userName") for u in self.player_session_users() if u.get("userID")]
        classified = await asyncio.to_thread(_classify_names_sync, names)
        return [(name, display or name) for name, display in classified]

    async def set_seating_order(self, ordered_user_names: list[str]) -> str | None:
        """Force the Draftmancer table order (owner-only, pre-draft). Returns an error string or None."""
        if not self.sio.connected:
            return "Draftmancer session is not connected"
        if self.drafting or self.draft_complete:
            return "Seating can't be changed once the draft has started"
        name_to_id = {
            u.get("userName"): u.get("userID")
            for u in self.player_session_users()
            if u.get("userID")
        }
        if set(ordered_user_names) != set(name_to_id):
            return "Lobby changed since the panel opened. Reopen Settings and set the seating again"
        user_id_order = [name_to_id[name] for name in ordered_user_names]
        try:
            await self.sio.emit("setRandomizeSeatingOrder", False)
            await self.sio.emit("setSeating", user_id_order)
        except Exception:
            log.exception(f"[SEATING] emit_failed event={self.event_id}")
            return "Could not update the seating order"
        self.desired_seating = list(ordered_user_names)
        log.info(f"[SEATING] applied event={self.event_id} order={ordered_user_names}")
        return None

    def kick_targets(self) -> list[tuple[str, str]]:
        """(userID, label) for every removable session user — seated players plus spectators,
        spectators suffixed so the Settings kick select tells them apart."""
        players = [
            (u.get("userID"), u.get("userName")) for u in self.player_session_users()
            if u.get("userID")
        ]
        spectators = [(user_id, f"{name} (spectator)") for user_id, name in self.spectator_targets]
        return players + spectators

    async def kick_player(self, user_id: str) -> str | None:
        """Remove a user from the Draftmancer session (owner-only socket action; Draftmancer parks
        the removed user in a fresh session). Pre-draft only. Returns an error string or None."""
        if not self.sio.connected:
            return "Draftmancer session is not connected"
        if self.drafting or self.draft_complete:
            return "Players can't be removed once the draft has started"
        try:
            await self.sio.emit("removePlayer", user_id)
        except Exception:
            log.exception(f"[KICK] emit_failed event={self.event_id} user_id={user_id}")
            return "Could not remove the player"
        log.info(f"[KICK] removed event={self.event_id} user_id={user_id}")
        return None

    async def unrecognized_lobby_names(self) -> list[str]:
        """Draftmancer seat names in the live lobby with no linked player — the targets the Settings
        'Link Players' action offers an organizer to bind by hand."""
        names = self.non_bot_session_names()
        classified = await self._classify_users(names) if names else []
        return [arena for arena, dn in classified if dn is None]

    async def link_seat(self, member: discord.abc.User, arena_name: str) -> str | None:
        """Bind `member`'s Discord identity to the exact Draftmancer seat `arena_name`, then refresh
        the lobby so the seat resolves. Returns an error string on failure, None on success."""
        def _link() -> None:
            with SessionLocal() as session:
                attach_arena_alias(
                    session,
                    discord_id=str(member.id),
                    discord_username=member.name,
                    display_name=member.display_name,
                    avatar_hash=extract_avatar_hash(member),
                    arena_name=arena_name,
                )
                session.commit()

        await asyncio.to_thread(_link)
        log.info(f"[LINK] seat_linked event={self.event_id} member={member} arena={arena_name!r}")
        await self.refresh_lobby_now()
        await refresh_round_pairing_messages(self)
        return None

    def _sync_leaderboard_seeding(self) -> None:
        """Re-apply leaderboard seating and refresh the posted seeding table after the player pool or a
        name changes. No-op unless the pod is leaderboard-seated. Fires from both the sessionUsers and
        the updateUser-rename paths so a name set after connect can't leave the seating one player behind."""
        if self.seating_mode != "leaderboard":
            return
        if self.owner_claimed:
            asyncio.create_task(self._apply_leaderboard_seating())
        notify_seeding_change(self.bot, self.event_id)

    def _lobby_pod_full(self, classified: list[tuple[str, str | None]]) -> bool:
        """A full, ready-checkable pod: a full pod's worth of players present and every one of them
        linked. Unlinked players can't draft and disable the Ready Check, so they don't count. A mock
        pairs no matches and reports no results, so an unrecognized seat is a seat like any other."""
        if self.kind != "mock" and any(display is None for _, display in classified):
            return False
        return len(classified) >= self._lobby_full_count

    @property
    def _lobby_full_count(self) -> int:
        """How many players make this lobby worth a Ready Check nudge: the table this roster asks for,
        capped by the seats the room holds.

        The size the plan gives, not the count on the roster, so nine players are one short of their table
        of ten rather than full. The widest table the plan holds, not the first, since a roster that has
        not split yet is still one room."""
        planned = plan_tables(self.expected_attendee_count).tables
        widest = max(table.capacity for table in planned) if planned else _LOBBY_FULL_THRESHOLD
        return min(self.max_players, widest)

    def _suppress_lobby_full_prompt(self) -> None:
        """Retire the auto-nudge for this lobby once a Ready Check has been initiated, so it can't fire
        later even if that check is declined and the lobby returns to idle, and delete its posted message
        so the stale Ready Check button can't be clicked."""
        self._lobby_full_prompted = True
        if self._lobby_full_prompt_task is not None:
            self._lobby_full_prompt_task.cancel()
            self._lobby_full_prompt_task = None
        if self._lobby_full_prompt_message is not None:
            asyncio.create_task(self._retire_lobby_full_prompt())
        if self._lobby_waiting_message is not None:
            asyncio.create_task(self._retire_lobby_waiting())

    async def _retire_lobby_full_prompt(self) -> None:
        """Delete the posted lobby-full nudge so its buttons can't outlive the lobby. Best-effort."""
        message = self._lobby_full_prompt_message
        self._lobby_full_prompt_message = None
        if message is None:
            return
        try:
            await message.delete()
        except discord.HTTPException:
            log.info(f"[LOBBY] full_prompt_delete_failed event={self.event_id}", exc_info=True)

    def _maybe_schedule_lobby_full_prompt(self, classified: list[tuple[str, str | None]]) -> None:
        """Arm the delayed pass that posts the Ready Check button once safe, else the waiting announcement"""
        if self.draft_complete or self.drafting or self.ready_check_active or self._lobby_full_prompted:
            return
        if not self._lobby_pod_full(classified):
            return
        if self._lobby_full_prompt_task is not None and not self._lobby_full_prompt_task.done():
            return
        self._lobby_full_prompt_task = asyncio.create_task(self._lobby_full_prompt_after_delay())

    async def _lobby_full_prompt_after_delay(self) -> None:
        try:
            await asyncio.sleep(_LOBBY_FULL_PROMPT_DELAY_S)
        except asyncio.CancelledError:
            return
        if self.draft_complete or self.drafting or self.ready_check_active or self._lobby_full_prompted:
            return
        classified = await self.classified_session_users()
        if not self._lobby_pod_full(classified):
            return
        thread = await self._fetch_thread()
        if thread is None:
            return
        mention_map = await self._resolve_rsvp_mentions(thread.guild)
        waiting = waiting_roster(self.rsvps_yes, classified, mention_map)
        if ready_check_strands_nobody(len(classified), self.max_players, len(waiting)):
            await self._post_lobby_full_prompt(thread, len(classified))
        else:
            await self._post_lobby_waiting(thread, len(classified), waiting)

    async def _post_lobby_full_prompt(self, thread: discord.Thread, present: int) -> None:
        """Post the Ready Check button and retire any waiting announcement it supersedes"""
        self._lobby_full_prompted = True
        await self._retire_lobby_waiting()
        try:
            prompt = MSG_LOBBY_FULL_PROMPT.format(count=emojis.mana_number(present))
            self._lobby_full_prompt_message = await thread.send(prompt, view=LobbyReadyButtonView())
        except discord.HTTPException:
            self._lobby_full_prompted = False
            log.warning(f"[LOBBY] full_prompt_send_failed event={self.event_id}", exc_info=True)

    async def _post_lobby_waiting(self, thread: discord.Thread, present: int, waiting: list[str]) -> None:
        """Name who the lobby is waiting on, no button, edited in place and skipped when the text is unchanged"""
        text = MSG_LOBBY_WAITING.format(count=emojis.mana_number(present), names=", ".join(waiting))
        if text == self._lobby_waiting_text and self._lobby_waiting_message is not None:
            return
        self._lobby_waiting_text = text
        allowed = discord.AllowedMentions(users=True)
        try:
            if self._lobby_waiting_message is not None:
                await self._lobby_waiting_message.edit(content=text, allowed_mentions=allowed)
            else:
                self._lobby_waiting_message = await thread.send(text, allowed_mentions=allowed)
        except discord.HTTPException:
            log.warning(f"[LOBBY] waiting_post_failed event={self.event_id}", exc_info=True)

    async def _retire_lobby_waiting(self) -> None:
        """Delete the waiting announcement once it is superseded or the lobby moves on. Best-effort."""
        message = self._lobby_waiting_message
        self._lobby_waiting_message = None
        self._lobby_waiting_text = ""
        if message is None:
            return
        try:
            await message.delete()
        except discord.HTTPException:
            log.info(f"[LOBBY] waiting_delete_failed event={self.event_id}", exc_info=True)

    def open_rider_window(self, planned: int, rider_mentions: list[str]) -> None:
        """Give a staged table's confirmed roster the first two minutes on its own seats.

        The room already opens wide enough for the riders, so none of them can take a seat the roster
        needs. What is held back is the invitation: a rider is not asked in while the table it was dealt
        onto can still fill itself. The table reaching its planned size closes the window and locks the
        room to that size, which is what puts the Ready Check nudge in front of a table of eight instead
        of leaving it waiting on players nobody is expecting."""
        if planned <= 0 or not rider_mentions:
            return
        self.rider_seats_held = planned
        self.rider_mentions = list(rider_mentions)
        self._rider_window_task = asyncio.create_task(self._ask_the_riders_in_after())

    async def _maybe_lock_planned_table(self) -> None:
        """Close the rider window once the table holds everyone it planned for, and cap it there.

        A room already past the planned size keeps its width: Draftmancer refuses a cap under the players
        seated, and a table that has outgrown its plan wants the seat that makes it even rather than a
        cap that forbids it."""
        if not self.rider_seats_held or self.drafting or self.draft_complete:
            return
        seated = len(self.player_session_users())
        if seated < self.rider_seats_held:
            return
        planned = self.rider_seats_held
        self._close_rider_window()
        if seated > planned:
            log.info(f"[LOBBY] rider_window_outgrown event={self.event_id} seated={seated} planned={planned}")
            return
        error = await self.apply_max_players(planned)
        log.info(f"[LOBBY] rider_window_filled event={self.event_id} locked={planned} error={error}")

    async def _ask_the_riders_in_after(self) -> None:
        """Hand the riders the table two minutes past the start time, when it did not fill on its own."""
        start = self.scheduled_start or datetime.now(timezone.utc)
        wait = (start - datetime.now(timezone.utc)).total_seconds() + RIDER_WINDOW_S
        try:
            await asyncio.sleep(max(0.0, wait))
        except asyncio.CancelledError:
            return
        if not self.rider_seats_held or self.drafting or self.draft_complete:
            return
        mentions = " ".join(self.rider_mentions)
        short = self.rider_seats_held - len(self.player_session_users())
        self.rider_seats_held = 0
        self._rider_window_task = None
        thread = await self._fetch_thread()
        if thread is None:
            return
        try:
            await thread.send(
                MSG_RIDER_SEATS_OPEN.format(
                    count=emojis.mana_number(max(short, 1)), mentions=mentions,
                    url=self.draftmancer_url,
                ),
                allowed_mentions=discord.AllowedMentions(users=True),
            )
        except discord.HTTPException:
            log.warning(f"[LOBBY] rider_window_send_failed event={self.event_id}", exc_info=True)

    def _close_rider_window(self) -> None:
        self.rider_seats_held = 0
        if self._rider_window_task is not None:
            self._rider_window_task.cancel()
            self._rider_window_task = None

    async def post_voice_offer(self) -> None:
        """The one-time offer of the pod voice channel, posted when the draft ends and the pod turns into
        matches people play against each other. An invite link instead of the channel link, since that is
        what makes Discord draw its join card with the members already in there.

        A team draft takes a room per side instead: the two rooms are claimed here, while the pod thread
        still holds every player, and the team flow posts each one in its own team's private thread. A
        guild with fewer than two free rooms falls back to the shared channel offered here."""
        if self._voice_link_posted:
            return
        thread = await self._fetch_thread()
        if thread is None:
            return
        if self.pairing_mode == "team":
            self.team_voice_rooms = free_voice_rooms(thread.guild, 2)
            if len(self.team_voice_rooms) == 2:
                self._voice_link_posted = True
                names = [room.name for room in self.team_voice_rooms]
                log.info(f"[VOICE] team_rooms_claimed event={self.event_id} rooms={names}")
                return
            log.info(f"[VOICE] team_rooms_unavailable event={self.event_id} free={len(self.team_voice_rooms)}")
            self.team_voice_rooms = []
        channel = pod_voice_channel(thread.guild)
        self._voice_link_posted = True
        if channel is None:
            log.info(
                f"[LOBBY] voice_link_skip — no '{settings.pod_draft_voice_channel_name}' voice channel "
                f"event={self.event_id}"
            )
            return
        try:
            await thread.send(await build_voice_offer_message(channel))
        except discord.HTTPException:
            self._voice_link_posted = False
            log.warning(f"[LOBBY] voice_link_send_failed event={self.event_id}", exc_info=True)

    def offers_team_draft(self) -> bool:
        """Whether the ready check asks the initiator to make this pod a Team Draft: six players in the
        Draftmancer lobby and nobody has picked the pairings"""
        if self.kind == "mock" or self.drafting or self.draft_complete or self.pairing_set_by_user:
            return False
        if self.current_round or self.pairing_mode == "team":
            return False
        return len(self.player_session_users()) == TEAM_VOTE_POD_SIZE

    async def take_team_draft(self, actor: str | None = None) -> str | None:
        """Move the pod onto Team Draft as the choice `actor` made, so its size never moves it back.
        Returns an error string when the pod cannot take it, else None"""
        error = await set_event_pairing_mode(self.event_id, "team")
        if error:
            return error
        run_detached(self._post_pairing_notice("team", actor), f"pairing_notice:{self.event_id}")
        log.info(f"[TEAM] took_team_draft event={self.event_id} actor={actor} "
                 f"seated={len(self.player_session_users())}")
        return None

    async def _post_pairing_notice(self, mode: str, actor: str | None) -> None:
        """Say in the thread that the pairings moved, in the same shape a Settings change reads, and bring
        the registration embed along with it."""
        thread = await self._fetch_thread()
        if thread is None:
            return
        await send_settings_notice(
            thread, self.bot.user, pairing_change_message(actor, mode),
            marker=settings_notice_markers("Pairings"),
        )
        await update_registered_embed(
            thread, client_user=self.bot.user, set_code=self.set_code,
            pairing_mode=mode, seating_mode=self.seating_mode,
            championship=is_championship(self.event_name),
        )

    async def offer_round_robin_vote(self, *, pod_size: int | None = None, from_signups: bool = False) -> None:
        """Post the one-time Pick 2 offer card. The organizer decides when a pod is asked; this places the
        card and fixes the votes it needs. `pod_size` sizes the vote off a roster that can only make four,
        where the lobby is not the number to count. No-op once offered or the draft is under way."""
        if self.round_robin_vote_offered or self.drafting or self.draft_complete:
            return
        thread = await self._fetch_thread()
        if thread is None:
            return
        self.round_robin_vote_offered = True
        size = pod_size or len(self.player_session_users()) or settings.pod_round_robin_size
        self.round_robin_vote_size = size
        self.round_robin_vote_from_signups = from_signups
        try:
            self.round_robin_vote_message = await thread.send(
                embed=pod_round_robin_vote.build_offer_embed([], [], size, from_signups=from_signups),
                view=pod_round_robin_vote.build_vote_view(self.event_id),
            )
        except discord.HTTPException:
            self.round_robin_vote_offered = False
            log.warning(f"[RR_VOTE] offer_post_failed event={self.event_id}", exc_info=True)

    async def waiting_on_mentions(self) -> list[str]:
        """Roster mentions with nobody matching them in the Draftmancer lobby, Yes and unconfirmed only.

        A maybe is never a player the room waits on, so a pod short of a table is never told to chase one."""
        thread = await self._fetch_thread()
        guild = thread.guild if thread is not None else None
        classified = await self._classify_users(self.non_bot_session_names())
        mention_map = await self._resolve_rsvp_mentions(guild)
        return waiting_roster(list(self.rsvps_yes) + list(self.rsvps_unconfirmed), classified, mention_map)

    async def bump_offer_card(self) -> None:
        """Move a live Pick 2 or Team Draft card to the bottom of the thread, carrying its tally, for a
        choice that conversation has buried. Called by `!pod` in the thread, right after the lobby card, so
        the question the table is being asked ends up under the lobby it is about."""
        if self.drafting or self.draft_complete:
            return
        thread = await self._fetch_thread()
        if thread is None:
            return
        if self.team_vote_message is not None:
            team, wait = await self._clear_existing_team_vote(thread)
            self.team_vote_offered = False
            self.team_vote_message = None
            await self.offer_team_vote(self.team_vote_size or TEAM_VOTE_POD_SIZE, team=team, wait=wait)
            return
        message = await self._fresh_round_robin_card()
        if message is None or not message.embeds:
            return
        card = message.embeds[0]
        round_robin = pod_round_robin_vote.round_robin_voters_from_embed(card)
        wait = pod_round_robin_vote.wait_voters_from_embed(card)
        from_signups = pod_round_robin_vote.asks_about_signups(card)
        await self._retire_round_robin_offer()
        self.round_robin_vote_offered = False
        await self.offer_round_robin_vote(pod_size=self.round_robin_vote_size, from_signups=from_signups)
        moved = self.round_robin_vote_message
        if moved is not None and (round_robin or wait):
            try:
                await moved.edit(embed=pod_round_robin_vote.rerender_gathering(
                    moved.embeds[0], round_robin, wait))
            except discord.HTTPException:
                log.info(f"[RR_VOTE] bump_tally_failed event={self.event_id}", exc_info=True)

    async def promote_round_robin_offer(self) -> None:
        """Re-title a signups card once its four are all in the Draftmancer lobby, so the card counts the
        room it can now see. The votes already on the message are carried over untouched."""
        if not self.round_robin_vote_from_signups or self.round_robin_vote_message is None:
            return
        if len(self.player_session_users()) < self.round_robin_vote_size:
            return
        message = await self._fresh_round_robin_card()
        if message is None or not message.embeds:
            return
        self.round_robin_vote_from_signups = False
        try:
            await message.edit(embed=pod_round_robin_vote.promoted_from_signups(
                message.embeds[0], self.round_robin_vote_size))
        except discord.HTTPException:
            log.info(f"[RR_VOTE] promote_failed event={self.event_id}", exc_info=True)

    async def _fresh_round_robin_card(self) -> "discord.Message | None":
        """The Pick 2 card re-read off Discord. A click edits the message itself, so the handle held here
        still carries the embed as it was first posted, votes and all missing."""
        message = self.round_robin_vote_message
        if message is None:
            return None
        try:
            return await message.channel.fetch_message(message.id)
        except discord.HTTPException:
            log.info(f"[RR_VOTE] card_refetch_failed event={self.event_id}", exc_info=True)
            return None

    async def _retire_round_robin_offer(self) -> None:
        """Delete the offer card so its buttons can't outlive the offer. A card pulled because the lobby
        changed size leaves `round_robin_vote_offered` cleared by the caller, so a lobby that returns to
        four and stalls again gets asked again. Best-effort."""
        self.round_robin_vote_from_signups = False
        message = self.round_robin_vote_message
        self.round_robin_vote_message = None
        if message is None:
            return
        try:
            await message.delete()
        except discord.HTTPException:
            log.info(f"[RR_VOTE] offer_delete_failed event={self.event_id}", exc_info=True)

    async def apply_round_robin_outcome(self) -> None:
        """Turn the pod into a Pick 2 Round Robin: the pairing mode plus the pick count, which is the
        default way four players draft. Both stay changeable in Settings."""
        self.pairing_mode = "roundrobin"
        self.pairing_set_by_user = True
        await asyncio.to_thread(persist_pairing_mode, self.event_id, "roundrobin")
        await set_event_picks_per_pack(self.event_id, 2)
        await self.refresh_lobby_now()
        notify_card_refresh(self.bot, self.event_id)

    async def offer_team_vote_manual(self, *, post: CardPoster | None = None) -> str | None:
        """Post the Team-Draft vote on demand from /pod-team. A proposal, not a commitment, so it takes
        any pod of at least four and leaves the parity to settle before start — unlike the auto nudge,
        which waits for an even lobby. Re-running with a vote already up deletes that card and re-posts it
        at the bottom of the thread, carrying its votes over. Returns an error string when the pod can't
        take a vote right now, else None."""
        if self.kind == "mock":
            return "A mock draft plays no matches, so it cannot be a Team Draft"
        if self.pairing_mode == "team":
            return "This pod is already a Team Draft"
        if self.drafting or self.draft_complete:
            return "The draft has already started"
        count = len(self.player_session_users())
        if count < 4:
            return "Team Draft needs at least four players in the Draftmancer lobby"
        thread = await self._fetch_thread()
        if thread is None:
            return "Could not reach the pod thread. Try again"
        team, wait = await self._clear_existing_team_vote(thread)
        self.team_vote_offered = False
        self.team_vote_message = None
        await self.offer_team_vote(count, team=team, wait=wait, post=post)
        return None

    async def _clear_existing_team_vote(self, thread: "discord.Thread") -> tuple[list[str], list[str]]:
        """Delete the pod's current Team-Draft card and return its (team, wait) tally, so a re-offer keeps the
        votes already cast. The card message is the source of truth, since clicks edit it directly, not the
        manager's cached handle; an empty pair when no gathering card is up."""
        card = await find_team_vote_card(thread, self.event_id)
        if card is None:
            return [], []
        team: list[str] = []
        wait: list[str] = []
        if card.embeds:
            team = team_voters_from_embed(card.embeds[0])
            wait = wait_voters_from_embed(card.embeds[0])
        try:
            await card.delete()
        except discord.HTTPException:
            log.info(f"[TEAM_VOTE] reoffer_delete_failed event={self.event_id}", exc_info=True)
        return team, wait

    async def offer_team_vote(
        self, pod_size: int, *, team: list[str] | None = None, wait: list[str] | None = None,
        post: CardPoster | None = None,
    ) -> None:
        """Post the one-time Team-Draft vote offer for a settled small pod. The caller decides the pod is
        eligible (even, at most six); `pod_size` fixes the majority the vote needs to lock. `team`/`wait`
        seed the columns when a re-offer carries votes over. `post` swaps in another way to place the card,
        so /pod-team can make it the command's own visible reply. No-op once offered, already a team pod, or
        the draft is under way. Mock drafts never take the offer: they play no matches, so there are no
        sides for a team split to mean anything to."""
        if self.kind == "mock":
            return
        if self.team_vote_offered or self.pairing_mode == "team" or self.drafting or self.draft_complete:
            return
        thread = await self._fetch_thread()
        if thread is None:
            return
        self.team_vote_size = pod_size
        self.team_vote_offered = True
        try:
            self.team_vote_message = await (post or thread.send)(
                embed=build_team_vote_offer_embed(team or [], wait or [], pod_size),
                view=build_team_vote_view(self.event_id),
            )
        except discord.HTTPException:
            self.team_vote_offered = False
            log.warning(f"[TEAM_VOTE] offer_post_failed event={self.event_id}", exc_info=True)

    async def adopt_existing_team_vote(self) -> None:
        """Take over a Team-Draft card already posted before this manager existed — the T-60 offer that ran
        an hour before the lobby opened, or the card left behind by a restart. Adopting marks the offer
        made so the at-start tick doesn't post a duplicate; the card's own button drives the vote either
        way, since the tally lives on the message."""
        if self.pairing_mode == "team" or self.team_vote_offered or self.drafting or self.draft_complete:
            return
        thread = await self._fetch_thread()
        if thread is None:
            return
        card = await find_team_vote_card(thread, self.event_id)
        if card is None:
            return
        self.team_vote_message = card
        self.team_vote_offered = True
        needed = needed_from_embed(card.embeds[0]) if card.embeds else None
        self.team_vote_size = (needed - 1) * 2 if needed is not None else TEAM_VOTE_POD_SIZE
        log.info(f"[TEAM_VOTE] adopted existing card event={self.event_id} size={self.team_vote_size}")

    async def _retire_team_vote_offer(self) -> None:
        """Delete the offer card so its button can't outlive the offer. Best-effort."""
        message = self.team_vote_message
        self.team_vote_message = None
        if message is None:
            return
        try:
            await message.delete()
        except discord.HTTPException:
            log.info(f"[TEAM_VOTE] offer_delete_failed event={self.event_id}", exc_info=True)

    async def offer_format_poll(self, *, post: CardPoster | None = None) -> str | None:
        """Post the one-time format tally in the pod's thread. The present players' standing flashback
        rankings seed the option buttons so the likely sets are one click away, but no vote is pre-cast — the
        split gate counts only live clicks, so the tally reads as a real attendance signal. `post` swaps in
        another way to place the card, so /vote-format can make it the command's own visible reply. Returns
        an error string when this pod already holds a card, else None."""
        if self.format_poll_offered:
            return pod_format_poll.MSG_VOTE_ALREADY_UP
        thread = await self._fetch_thread()
        if thread is None:
            return pod_format_poll.MSG_VOTE_POST_FAILED
        self.format_poll_offered = True
        message = await send_format_poll_card(thread, self.event_id, post=post)
        if message is None:
            self.format_poll_offered = False
            return pod_format_poll.MSG_VOTE_POST_FAILED
        self.format_poll_message = message
        return None

    async def adopt_existing_format_poll(self) -> None:
        """Take over a format poll card already posted before this manager existed, or left by a restart, so
        the at-start tick posts no duplicate. The card's own buttons drive the poll; the tally lives on the
        message."""
        if self.format_poll_offered or self.drafting or self.draft_complete:
            return
        thread = await self._fetch_thread()
        if thread is None:
            return
        card = await pod_format_poll.find_format_poll_card(thread, self.event_id)
        if card is None:
            return
        self.format_poll_message = card
        self.format_poll_offered = True
        log.info(f"[FORMAT_POLL] adopted existing card event={self.event_id}")

    async def _retire_format_poll_offer(self) -> None:
        """Close the poll card when the draft starts: keep the final tally on the thread, disable the buttons
        so no more votes land, and mark it closed. Best-effort."""
        message = self.format_poll_message
        self.format_poll_message = None
        if message is None or not message.embeds:
            return
        options = pod_format_poll.options_from_embed(message.embeds[0])
        try:
            await message.edit(
                embed=pod_format_poll.close_format_poll_embed(message.embeds[0]),
                view=pod_format_poll.build_closed_format_poll_view(options),
            )
        except discord.HTTPException:
            log.info(f"[FORMAT_POLL] offer_close_failed event={self.event_id}", exc_info=True)

    async def apply_seating_mode(self) -> None:
        """Push the current seating_mode to the live table. Leaderboard recomputes the seeded order
        from the present lobby; random asserts the shuffle flag; manual is driven by the Seat Order
        button + the pre-startDraft re-assert, so nothing is pushed here. Pre-draft only.

        Random under team mode is the exception: Draftmancer's own start-time shuffle would hide the
        final order until after startDraft, but team assignment needs it at the start — so the bot
        shuffles and pushes the order itself."""
        if not self.sio.connected or self.drafting or self.draft_complete:
            return
        if self.seating_mode == "leaderboard":
            await self._apply_leaderboard_seating()
        elif self.seating_mode == "random":
            if self.pairing_mode == "team":
                await self._apply_shuffled_seating()
                return
            try:
                await self.sio.emit("setRandomizeSeatingOrder", True)
            except Exception:
                log.exception(f"[SEATING] randomize_emit_failed event={self.event_id}")

    async def _apply_shuffled_seating(self) -> None:
        names = [u.get("userName") for u in self.player_session_users() if u.get("userID")]
        if len(names) < 2:
            return
        random.shuffle(names)
        err = await self.set_seating_order(names)
        if err is not None:
            log.info(f"[SEATING] shuffle_skipped event={self.event_id} reason={err!r}")

    async def _apply_leaderboard_seating(self) -> None:
        """Compute the seeded ring from the present lobby and emit setSeating. Idempotent: skips the
        emit when the computed order matches what was last applied, so the sessionUsers broadcast that
        setSeating itself triggers can't drive a re-seat loop."""
        name_to_id = {
            u.get("userName"): u.get("userID")
            for u in self.player_session_users()
            if u.get("userID")
        }
        if len(name_to_id) < 2:
            return
        ordered_names = await asyncio.to_thread(
            _leaderboard_seat_order_sync, list(name_to_id), self.event_id,
        )
        user_id_order = tuple(name_to_id[name] for name in ordered_names if name in name_to_id)
        if len(user_id_order) != len(name_to_id):
            log.warning(f"[SEATING] leaderboard_order_mismatch event={self.event_id} names={ordered_names}")
            return
        if user_id_order == self._last_seating_signature:
            return
        try:
            await self.sio.emit("setRandomizeSeatingOrder", False)
            await self.sio.emit("setSeating", list(user_id_order))
        except Exception:
            log.exception(f"[SEATING] leaderboard_emit_failed event={self.event_id}")
            return
        self._last_seating_signature = user_id_order
        self.desired_seating = list(ordered_names)
        log.info(f"[SEATING] leaderboard_applied event={self.event_id} order={ordered_names}")

    async def _reapply_seating_if_set(self) -> None:
        """Re-assert seating right before startDraft so late joins/leaves can't leave a stale order in
        place. Leaderboard recomputes from the final roster; random re-asserts the shuffle (or, under
        team mode, reshuffles and pushes the final roster); manual re-emits the organizer's frozen
        order. A team pod whose manual order was never set pushes the lobby order, so the seating is
        always known at startDraft. Best-effort: skipped (logged) on lobby mismatch."""
        if self.seating_mode in ("leaderboard", "random"):
            await self.apply_seating_mode()
            return
        if not self.desired_seating:
            if self.pairing_mode == "team":
                await self._push_lobby_order_seating()
            return
        err = await self.set_seating_order(self.desired_seating)
        if err is not None:
            log.info(f"[SEATING] reapply_skipped event={self.event_id} reason={err!r}")

    async def _push_lobby_order_seating(self) -> None:
        names = [u.get("userName") for u in self.player_session_users() if u.get("userID")]
        if len(names) < 2:
            return
        err = await self.set_seating_order(names)
        if err is not None:
            log.info(f"[SEATING] lobby_order_push_skipped event={self.event_id} reason={err!r}")

    async def _emit_with_ack(self, event: str, *args, timeout_s: float = 5.0):
        """Emit a socket.io event and wait for the server's ack callback."""
        future: asyncio.Future = asyncio.Future()

        def _cb(*cb_args):
            if not future.done():
                future.set_result(cb_args[0] if cb_args else None)

        try:
            await self.sio.emit(event, *args, callback=_cb)
            return await asyncio.wait_for(future, timeout=timeout_s)
        except asyncio.TimeoutError:
            log.warning(f"{event} ack timeout for {self.session_id}")
            return None
        except Exception:
            log.exception(f"{event} emit failed for {self.session_id}")
            return None

    async def send_chat(self, text: str) -> None:
        """Post in the Draftmancer session chat, as the bot. Draftmancer reads `author` as a userID and
        resolves it to a name client-side, so any other value renders as "(Left)"; the server truncates
        the text at 255 characters."""
        if not self.sio.connected or self.bot_user_id is None:
            return
        try:
            await self.sio.emit("chatMessage", {
                "author": self.bot_user_id,
                "text": bubble_text(text),
                "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
            })
        except Exception:
            log.warning(f"[CHAT] send_failed event={self.event_id}", exc_info=True)

    async def share_draft_log(self) -> bool:
        """Owner-only emit that flips the session's delayed/personal logs to fully public.

        Reconnects first when the socket dropped mid-event: this emit is the only way to unlock the
        logs, the session is recoverable by sessionID, and ownership persists for the same userID.
        """
        if not self.sio.connected:
            log.info(f"[DRAFT] share_log.reconnecting event={self.event_id}")
            self._closed = False
            try:
                await self.sio.connect(self._connect_url, transports=["websocket"], wait_timeout=10)
            except (socketio.exceptions.ConnectionError, OSError) as e:
                log.warning(f"[DRAFT] share_log.skipped event={self.event_id} reason=reconnect_failed err={e!s}")
                return False
        if not self.draft_logs:
            log.warning(f"[DRAFT] share_log.skipped event={self.event_id} reason=no_payload")
            return False
        payload = self._full_draft_log()
        try:
            await self.sio.emit("shareDraftLog", payload)
            log.info(f"[DRAFT] share_log.done event={self.event_id}")
            return True
        except Exception:
            log.exception(f"[DRAFT] share_log.error event={self.event_id}")
            return False

    async def takeover(self, target_user_id: str) -> tuple[bool, str]:
        """Hand session ownership to target_user_id and disconnect the bot.

        Sequence (ported from Amelas/DraftBot's /mutiny): setOwnerIsPlayer(True) → setSessionOwner(target).
        Draftmancer's protocol forbids both emits while a draft is in progress for an owner-spectator
        bot, so we refuse mid-draft rather than silently no-op.
        """
        log.info(
            f"[LIFECYCLE] takeover.start event={self.event_id} target={target_user_id} "
            f"sio_connected={self.sio.connected} drafting={self.drafting}"
        )
        if not self.sio.connected:
            return False, "Draftmancer session is not connected."
        if self.drafting:
            return False, (
                "A draft is already in progress — Draftmancer doesn't allow ownership "
                "transfer mid-draft when the bot is owner-spectator. Finish the draft, then retry."
            )
        await self.share_draft_log()
        try:
            await self.sio.emit("setOwnerIsPlayer", True)
            await asyncio.sleep(1.0)
            await self.sio.emit("setSessionOwner", target_user_id)
            await asyncio.sleep(1.0)
            log.info(f"[LIFECYCLE] takeover.done event={self.event_id} target={target_user_id}")
        except Exception:
            log.exception(f"[LIFECYCLE] takeover.error event={self.event_id}")
            await bot_log_mod.get(self.bot).post(
                f"Takeover transfer failed for event `{self.event_id}`.",
                fingerprint=f"takeover_failed:{self.event_id}",
                tag="LIFECYCLE",
            )
            return False, "Ownership transfer failed; check logs."
        await self.disconnect_safely()
        return True, ""

    async def _ready_timeout(self, generation: int) -> None:
        try:
            await asyncio.sleep(_READY_TIMEOUT_S)
        except asyncio.CancelledError:
            return
        if not self._ready_check_is_live(generation):
            log.info(f"[READY] stale_timeout_ignored event={self.event_id} generation={generation}")
            return
        missing_ids = self.expected_user_ids - self.ready_users
        log.warning(
            f"[READY] overdue event={self.event_id} timeout_s={_READY_TIMEOUT_S} "
            f"ready={len(self.ready_users)}/{len(self.expected_user_ids)} missing={missing_ids}"
        )
        self.ready_check_overdue = True
        tally = f"{len(self.ready_users)}/{len(self.expected_user_ids)} ready"
        cause = f"waiting on {self._missing_names(missing_ids)}" if missing_ids else "the lobby roster changed"
        await bot_log_mod.get(self.bot).post(
            f"Ready check overdue for event `{self.event_id}`. {tally}, {cause}.",
            fingerprint=f"ready_check_overdue:{self.event_id}",
            tag="READY",
        )
        await self._announce_overdue_check(missing_ids)
        await self.refresh_lobby_now()

    async def _announce_overdue_check(self, missing_ids: set[str]) -> None:
        thread = await self._fetch_thread()
        if thread is None or not missing_ids:
            return
        try:
            await thread.send(ready_check_overdue_text(await self._missing_mentions(missing_ids)))
        except Exception:
            log.warning(f"[READY] overdue_notice_failed event={self.event_id}", exc_info=True)

    async def _missing_mentions(self, missing_ids: set[str]) -> list[str]:
        """Seats that still owe an answer, as pings where the player is known and as their handle where not"""
        names = [name for name in (self.seat_name(uid) for uid in sorted(missing_ids)) if name]
        if not names:
            return []
        discord_id_by_name = await asyncio.to_thread(discord_ids_for_names_sync, names)
        mentions = []
        for name in names:
            discord_id = discord_id_by_name.get(name)
            mentions.append(f"<@{discord_id}>" if discord_id else name)
        return mentions

    async def _end_ready_check(self, detail: str) -> None:
        """Close a running check, which only a human stopping it does. The answers survive to the next arm"""
        self._cancel_ready_timeout()
        if not self.ready_check_active:
            return
        log.info(
            f"[READY] ended event={self.event_id} detail={detail!r} "
            f"answers_kept={len(self.ready_users)}"
        )
        self.ready_check_active = False
        self.ready_check_joined_ids = set()
        self.ready_check_left_ids = set()
        self.ready_check_overdue = False
        self.last_cancel_reason = detail
        await self._flip_progress_card_to_stopped()
        await self.refresh_lobby_now()

    async def _flip_progress_card_to_stopped(self) -> None:
        """Flip the live card to its closed state in place, so Resume sits on the message players are already
        looking at rather than on a fresh card below it."""
        thread = await self._fetch_thread()
        if thread is None:
            return
        embed = render_ready_check_progress(
            self.event_name, await self.classified_session_users(), state="notready",
            ready_arena_names=self.ready_arena_names(),
            not_ready_arena_names=self.not_ready_arena_names(),
            cancel_reason=self.last_cancel_reason, initiated_by=self.initiated_by,
            new_drafters=self.new_drafters,
            **self._settings_labels(),
        )
        card = self.ready_check_progress_message
        if card is not None:
            try:
                await card.edit(embed=embed, view=build_not_ready_view())
                return
            except Exception:
                log.warning(f"[READY] stopped_card_edit_failed event={self.event_id}", exc_info=True)
        try:
            self.ready_check_progress_message = await thread.send(embed=embed, view=build_not_ready_view())
        except Exception:
            log.warning(f"[READY] stopped_card_repost_failed event={self.event_id}", exc_info=True)

    def _cancel_ready_timeout(self) -> None:
        if self._ready_timeout_task is not None and not self._ready_timeout_task.done():
            self._ready_timeout_task.cancel()
        self._ready_timeout_task = None

    def _missing_names(self, missing_ids: set[str]) -> str:
        """Seats that never answered a ready check, for the admin notice. Falls back to the raw Draftmancer
        userID when a name was not captured, so the notice stays traceable instead of dropping the seat."""
        return ", ".join(self.seat_name(uid) or uid for uid in sorted(missing_ids))

    def _schedule_end_watchdog(self) -> None:
        self._cancel_end_watchdog()
        self._end_watchdog_task = asyncio.create_task(self._end_draft_watchdog())

    def _cancel_end_watchdog(self) -> None:
        if self._end_watchdog_task is not None and not self._end_watchdog_task.done():
            self._end_watchdog_task.cancel()
        self._end_watchdog_task = None

    async def _end_draft_watchdog(self) -> None:
        window_s = max(1, settings.pod_draft_end_watchdog_minutes) * 60
        try:
            await asyncio.sleep(window_s)
        except asyncio.CancelledError:
            return
        if self.draft_complete or self.finalized:
            return
        log.warning(
            f"[DRAFT] end_watchdog_tripped event={self.event_id} window_min={settings.pod_draft_end_watchdog_minutes} "
            f"drafting={self.drafting} complete={self.draft_complete}"
        )
        await bot_log_mod.get(self.bot).post(
            f"endDraft not received for event `{self.event_id}` after "
            f"{settings.pod_draft_end_watchdog_minutes} min — draft may be stuck.",
            fingerprint=f"end_draft_watchdog:{self.event_id}",
            tag="DRAFT",
        )


def ready_check_strands_nobody(present: int, room_size: int, waiting: int) -> bool:
    """Whether a Ready Check now leaves no confirmed player behind: room full, or nobody confirmed absent"""
    return present >= room_size or waiting == 0


def name_nudge_text(names: list[str]) -> str:
    """One line per fix, read off what the name says the player was reaching for: nothing typed yet, an
    Arena handle the bot was never told about, or a Discord identity that matches no member."""
    groups: dict[str, list[str]] = {
        MSG_DRAFTMANCER_SET_NAME: [],
        MSG_DRAFTMANCER_LINK_ARENA: [],
        MSG_DRAFTMANCER_USE_DISCORD_NAME: [],
    }
    for name in names:
        if name.startswith(DRAFTMANCER_DEFAULT_NAME):
            groups[MSG_DRAFTMANCER_SET_NAME].append(name)
        elif full_arena_handle(name):
            groups[MSG_DRAFTMANCER_LINK_ARENA].append(name)
        else:
            groups[MSG_DRAFTMANCER_USE_DISCORD_NAME].append(name)
    return "\n".join(
        message.format(names=", ".join(group)) for message, group in groups.items() if group
    )


def bubble_text(text: str) -> str:
    """Draftmancer sizes the chat bubble to the session owner's chip, so it shrinks to the narrowest
    wrap the text allows and a plain sentence comes out one word per line. Non-breaking spaces read as
    spaces, and a word joiner covers the punctuation a browser also breaks after, so the only break
    left is one this copy asked for."""
    lines = []
    for line in text.splitlines():
        line = line.replace(" ", NBSP)
        for char in BUBBLE_BREAK_CHARS:
            line = line.replace(char, f"{char}{WORD_JOINER}")
        lines.append(line)
    return "\n".join(lines)


def _is_ready_state(state) -> bool:
    """Draftmancer sends setReady(userID, state) where state can be 0/1 or 'Ready'/'NotReady'."""
    if isinstance(state, bool):
        return state
    if isinstance(state, int):
        return state == 1
    if isinstance(state, str):
        return state.lower() == "ready"
    return bool(state)


def _ack_error_text(ack) -> str | None:
    """Pull a human error string out of Draftmancer's SocketAck/SocketError shape, or None on success.
    A failure carries code != 0 and a nested error object {title, text}; success is code 0."""
    if not isinstance(ack, dict) or not ack.get("code"):
        return None
    error = ack.get("error")
    if isinstance(error, dict):
        title = error.get("title") or "Error"
        text = error.get("text") or ""
        return f"{title}: {text}".strip(": ")
    if error:
        return str(error)
    title = ack.get("title") or "Error"
    text = ack.get("text") or ""
    return f"{title}: {text}".strip(": ")


async def start_manager(
    bot: commands.Bot, event_id: str, session_id: str, thread_id: int,
    set_code: str, expected_attendee_count: int, *,
    event_name: str = "Pod Draft",
    draftmancer_url: str = "",
    kind: str = "tournament",
    rsvps_yes: list[str] | None = None,
    rsvps_unconfirmed: list[str] | None = None,
    rsvps_maybe: list[str] | None = None,
    reconnect: bool = False,
    created_by: str | None = None,
    pairing_chosen: bool = False,
) -> PodDraftManager | None:
    """`pairing_chosen` marks a launcher that committed a pairing, so the ready check stops offering one"""
    existing = ACTIVE_POD_MANAGERS.get(event_id)
    if existing is not None:
        log.info(f"[LIFECYCLE] start_manager.already_active event={event_id}")
        return existing
    manager = PodDraftManager(
        bot, event_id, session_id, thread_id, set_code, expected_attendee_count,
        event_name=event_name, draftmancer_url=draftmancer_url, kind=kind,
        rsvps_yes=rsvps_yes, rsvps_unconfirmed=rsvps_unconfirmed, rsvps_maybe=rsvps_maybe,
        reconnect=reconnect, created_by=created_by,
    )
    persisted_mode = await asyncio.to_thread(load_event_pairing_mode_sync, event_id)
    if persisted_mode:
        manager.pairing_mode = persisted_mode
    persisted_seating = await asyncio.to_thread(load_event_seating_mode_sync, event_id)
    if persisted_seating:
        manager.seating_mode = persisted_seating
    manager.pairing_set_by_user = pairing_chosen
    stored_setup = await asyncio.to_thread(pod_event_settings.load_sync, event_id)
    pod_event_settings.apply_to_manager(manager, stored_setup)
    manager.scheduled_start = await asyncio.to_thread(load_event_time_sync, event_id)
    ACTIVE_POD_MANAGERS[event_id] = manager
    log.info(
        f"[LIFECYCLE] start_manager.registered event={event_id} sid={session_id} "
        f"thread={thread_id} set={set_code} pairing={manager.pairing_mode} "
        f"registry_size={len(ACTIVE_POD_MANAGERS)}"
    )
    await manager.adopt_existing_team_vote()
    await manager.adopt_existing_format_poll()
    ok = await manager.connect()
    if not ok:
        ACTIVE_POD_MANAGERS.pop(event_id, None)
        log.warning(
            f"[LIFECYCLE] start_manager.connect_failed event={event_id} "
            f"registry_size={len(ACTIVE_POD_MANAGERS)}"
        )
        await manager._mark_socket_status("error")
        return None
    return manager


async def set_event_format(bot: commands.Bot, event_id: str, code: str) -> str | None:
    """Change a pod's format by event id; routes to the live manager when one exists, else persists directly
    and renames the thread to lead with the new set. Returns an error string or None."""
    manager = ACTIVE_POD_MANAGERS.get(event_id)
    if manager is not None:
        return await manager.apply_format(code)
    new_name = await asyncio.to_thread(_persist_format, event_id, code)
    if new_name is None:
        return pod_format.FORMAT_LOCKED_MSG
    if pod_format.cube_id_for(code) is None:
        await asyncio.to_thread(
            pod_event_settings.clear_sync, event_id, pod_event_settings.CARDS_PER_PACK)
    await _rename_event_thread(bot, event_id, new_name)
    return None


def _persist_format(event_id: str, code: str) -> str | None:
    """Persist the format change and return the pod's (possibly renamed) event name, or None when the
    event is missing or already finalized."""
    with SessionLocal() as session:
        new_name = update_event_format(session, event_id, code)
        if new_name is not None:
            session.commit()
        return new_name


async def _rename_event_thread(bot: commands.Bot, event_id: str, name: str) -> None:
    thread_id = await asyncio.to_thread(load_event_thread_id_sync, event_id)
    if thread_id is None:
        return
    try:
        thread = await bot.fetch_channel(int(thread_id))
        await thread.edit(name=name[:100])
    except discord.HTTPException:
        log.warning(f"could not rename thread for event {event_id}", exc_info=True)


async def set_event_pairing_mode(event_id: str, mode: str) -> str | None:
    """Set a pod's pairing mode by event id; updates the live manager when one exists and persists.
    Locked once the tournament has started. Every caller here is a choice somebody made, through the
    Settings panel, the launcher, a vote, or the ready check, so the pod keeps it from then on.
    Returns an error string or None."""
    if mode not in ("swiss", "bracket", "random", "team", "roundrobin"):
        return "Unknown pairing mode"
    manager = ACTIVE_POD_MANAGERS.get(event_id)
    if manager is not None:
        if manager.current_round and manager.current_round > 0:
            return "Pairing mode is locked once the tournament has started"
        manager.pairing_mode = mode
        manager.pairing_set_by_user = True
        await manager.apply_team_draft_setting()
    await asyncio.to_thread(persist_pairing_mode, event_id, mode)
    if manager is not None:
        await manager.refresh_lobby_now()
        notify_card_refresh(manager.bot, event_id)
    return None


_team_vote_click_locks: dict[str, asyncio.Lock] = {}


async def handle_team_vote_click(interaction: "discord.Interaction", event_id: str, side: str) -> None:
    """Move the clicker to their side of the Team-Draft vote against the card message. The first side to a
    majority decides it: Team Draft locks the pairing, Wait for 8 keeps the bracket and closes the vote. The
    card message is the tally, so this works whether or not a live manager backs the pod — the T-60 offer
    runs an hour before the lobby opens. Serialized per pod so rapid clicks can't race.

    Registered as the vote-button handler at import, keeping pod_team_vote free of a manager import."""
    lock = _team_vote_click_locks.setdefault(event_id, asyncio.Lock())
    async with lock:
        if not interaction.message.embeds:
            await interaction.response.defer()
            return
        embed = interaction.message.embeds[0]
        manager = ACTIVE_POD_MANAGERS.get(event_id)
        if manager is not None and (manager.drafting or manager.draft_complete):
            await interaction.response.defer()
            return
        if manager is not None:
            already_team = manager.pairing_mode == "team"
        else:
            already_team = await asyncio.to_thread(load_event_pairing_mode_sync, event_id) == "team"
        team = team_voters_from_embed(embed)
        wait = wait_voters_from_embed(embed)
        if already_team:
            await interaction.response.edit_message(
                embed=build_team_vote_locked_embed(team, wait), view=None)
            return
        needed = needed_from_embed(embed)
        mention = interaction.user.mention
        on_side = mention in (team if side == SIDE_TEAM else wait)
        team = [voter for voter in team if voter != mention]
        wait = [voter for voter in wait if voter != mention]
        if not on_side:
            (team if side == SIDE_TEAM else wait).append(mention)
        if needed is not None and len(team) >= needed:
            if manager is not None:
                manager.team_vote_message = None
            err = await set_event_pairing_mode(event_id, "team")
            if err:
                log.warning(f"[TEAM_VOTE] lock_failed event={event_id} err={err}")
                await interaction.response.defer()
                return
            log.info(f"[TEAM_VOTE] locked team event={event_id} voters={team}")
            await interaction.response.edit_message(
                embed=build_team_vote_locked_embed(team, wait), view=None)
            return
        if needed is not None and len(wait) >= needed:
            if manager is not None:
                manager.team_vote_message = None
            log.info(f"[TEAM_VOTE] waited event={event_id} voters={wait}")
            await interaction.response.edit_message(
                embed=build_team_vote_waited_embed(team, wait), view=None)
            return
        try:
            await interaction.response.edit_message(
                embed=rerender_gathering(embed, team, wait), view=build_team_vote_view(event_id))
        except discord.HTTPException:
            log.warning(f"[TEAM_VOTE] edit_failed event={event_id}", exc_info=True)


register_team_vote_click_handler(handle_team_vote_click)


_disconnect_vote_click_locks: dict[str, asyncio.Lock] = {}


async def handle_disconnect_vote_click(interaction: "discord.Interaction", event_id: str, side: str) -> None:
    """Move the clicker to their side of the disconnect offer against the card message, which holds the
    tally, and act the moment one side reaches a majority of the players still at the table. Serialized per
    pod so two clicks landing together can't both read the card as one short of the decision."""
    lock = _disconnect_vote_click_locks.setdefault(event_id, asyncio.Lock())
    async with lock:
        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        manager = ACTIVE_POD_MANAGERS.get(event_id)
        needed = pod_disconnect.needed_from_embed(embed) if embed is not None else None
        if embed is None or needed is None or manager is None:
            await interaction.response.defer()
            return
        if not manager.drafting or manager.draft_complete or not manager.disconnected_names:
            await interaction.response.edit_message(view=None)
            return
        mention = interaction.user.mention
        for_bot = [voter for voter in pod_disconnect.bot_voters_from_embed(embed) if voter != mention]
        for_restart = [voter for voter in pod_disconnect.restart_voters_from_embed(embed) if voter != mention]
        (for_bot if side == pod_disconnect.SIDE_BOT else for_restart).append(mention)
        if len(for_bot) >= needed:
            error = await manager.replace_disconnected_with_bots()
            if error:
                await interaction.response.send_message(f"⚠️ {error}", ephemeral=True)
                return
            log.info(f"[DROP_VOTE] replaced event={event_id} voters={for_bot}")
            await _close_disconnect_vote(
                interaction, manager, for_bot, for_restart, notice=pod_disconnect.BOT_NOTICE)
            return
        if len(for_restart) >= needed:
            log.info(f"[DROP_VOTE] restarting event={event_id} voters={for_restart}")
            await _close_disconnect_vote(interaction, manager, for_bot, for_restart)
            thread = await manager._fetch_thread()
            if thread is not None:
                await manager.restart_draft(thread)
            return
        try:
            await interaction.response.edit_message(
                embed=pod_disconnect.rerender_offer(embed, for_bot, for_restart),
                view=pod_disconnect.build_offer_view(event_id))
        except discord.HTTPException:
            log.warning(f"[DROP_VOTE] edit_failed event={event_id}", exc_info=True)


async def _close_disconnect_vote(interaction: "discord.Interaction", manager, bot_votes: list[str],
                                 restart_votes: list[str], *, notice: str | None = None) -> None:
    """Land the deciding click: the card keeps the tally that decided it and loses only its buttons, and
    the outcome goes out as its own plain message. A restart passes no notice, since reopening the lobby
    posts its own card for every path that reaches it."""
    manager.clear_disconnect_state()
    await interaction.response.edit_message(
        embed=pod_disconnect.rerender_offer(interaction.message.embeds[0], bot_votes, restart_votes),
        view=None)
    if notice is not None:
        await interaction.followup.send(notice)


pod_disconnect.register_vote_click_handler(handle_disconnect_vote_click)


_round_robin_vote_click_locks: dict[str, asyncio.Lock] = {}


async def handle_round_robin_vote_click(interaction: "discord.Interaction", event_id: str, side: str) -> None:
    """Move the clicker to their side of the Pick 2 offer against the card message, which holds the tally.
    Every player has to agree, so the card has one outcome and no deadline: Wait keeps it open, and a player
    who wanted to wait can move to Pick 2 once nobody else arrives. Serialized per pod so rapid clicks can't
    race."""
    lock = _round_robin_vote_click_locks.setdefault(event_id, asyncio.Lock())
    async with lock:
        manager = ACTIVE_POD_MANAGERS.get(event_id)
        card = interaction.message.embeds[0] if interaction.message.embeds else None
        if card is None or manager is None or manager.drafting or manager.draft_complete:
            await interaction.response.defer()
            return
        mention = interaction.user.mention
        for_rr = [voter for voter in pod_round_robin_vote.round_robin_voters_from_embed(card) if voter != mention]
        for_wait = [voter for voter in pod_round_robin_vote.wait_voters_from_embed(card) if voter != mention]
        (for_rr if side == pod_round_robin_vote.SIDE_ROUND_ROBIN else for_wait).append(mention)
        if len(for_rr) >= pod_round_robin_vote.votes_needed(manager.round_robin_vote_size):
            manager.round_robin_vote_message = None
            await manager.apply_round_robin_outcome()
            log.info(f"[RR_VOTE] locked round_robin event={event_id} voters={for_rr}")
            await interaction.response.edit_message(
                embed=pod_round_robin_vote.build_locked_embed(for_rr, for_wait), view=None)
            return
        try:
            await interaction.response.edit_message(
                embed=pod_round_robin_vote.rerender_gathering(card, for_rr, for_wait),
                view=pod_round_robin_vote.build_vote_view(event_id),
            )
        except discord.HTTPException:
            log.warning(f"[RR_VOTE] edit_failed event={event_id}", exc_info=True)


pod_round_robin_vote.register_vote_click_handler(handle_round_robin_vote_click)


_format_poll_click_locks: dict[str, asyncio.Lock] = {}


def _apply_format_poll_vote(
    event_id: str, embed: "discord.Embed", mention: str, code: str,
) -> tuple["discord.Embed", "discord.ui.View"]:
    """Toggle one voter's vote for one option against the card embed. The tally stays open — it decides
    nothing."""
    votes = pod_format_poll.votes_from_embed(embed)
    options = pod_format_poll.options_from_embed(embed)
    adders = pod_format_poll.adders_from_embed(embed)
    pod_format_poll.toggle_vote(votes, options, mention, code)
    options = pod_format_poll.order_options(options, votes)
    return (
        pod_format_poll.rerender_gathering(embed, options, votes, adders),
        pod_format_poll.build_format_poll_view(event_id, options),
    )


def _seed_options_from_rankings(
    options: list[str], rankings: "tuple[tuple[str, tuple[str, ...]], ...]",
) -> None:
    """Add each present player's standing flashback ranking to the poll as an option, best first, up to the
    cap — so the likely sets show as one-click buttons. No vote is pre-cast: the split gate counts only live
    clicks, so the card's tally stays an accurate live signal that a restart recovers straight off the
    message. Mutates ``options`` in place with any new codes."""
    for _discord_id, ranking in rankings:
        for code in ranking:
            if code in options:
                continue
            if len(options) >= pod_format_poll.MAX_ROWED_OPTIONS:
                continue
            options.append(code)


async def post_format_vote(
    channel: "discord.abc.Messageable", event_id: str | None, *, post: CardPoster | None = None,
) -> str | None:
    """Post a Format Vote card wherever it is asked for. It goes through the pod's live manager while that
    pod can still act on the result, so the card closes at draft start and feeds the second-table gate;
    everywhere else it stands alone, keyed to the channel. The card message is the tally, so its buttons work
    with no pod behind them. `post` swaps in another way to place the card. Returns an error string, or None
    once the card is up."""
    manager = ACTIVE_POD_MANAGERS.get(event_id) if event_id else None
    if manager is not None and not manager.drafting and not manager.draft_complete:
        return await manager.offer_format_poll(post=post)
    if event_id and manager is None:
        poll_id = event_id
    else:
        poll_id = f"{pod_format_poll.CHANNEL_POLL_ID_PREFIX}{channel.id}"
    existing = await pod_format_poll.find_format_poll_card(channel, poll_id)
    if existing is not None:
        return pod_format_poll.MSG_VOTE_ALREADY_UP
    if await send_format_poll_card(channel, poll_id, post=post) is None:
        return pod_format_poll.MSG_VOTE_POST_FAILED
    return None


async def send_format_poll_card(
    channel: "discord.abc.Messageable", poll_id: str, *, post: CardPoster | None = None,
) -> "discord.Message | None":
    """Post one format tally card, its options seeded from the standing flashback rankings of whoever signed
    up for ``poll_id`` when that is a pod event. None when Discord refused the post."""
    options = pod_format_poll.build_options()
    rankings = await asyncio.to_thread(event_member_rankings_sync, poll_id)
    _seed_options_from_rankings(options, rankings)
    options = pod_format_poll.order_options(options, {})
    try:
        return await (post or channel.send)(
            embed=pod_format_poll.build_format_poll_embed(options, {}),
            view=pod_format_poll.build_format_poll_view(poll_id, options),
        )
    except discord.HTTPException:
        log.warning(f"[FORMAT_POLL] post_failed poll={poll_id}", exc_info=True)
        return None


async def handle_format_poll_click(interaction: "discord.Interaction", event_id: str, code: str) -> None:
    """Toggle the clicker's vote for one format option against the card message. Multiple choice, so a
    player can back several formats. The card message is the tally, so this works whether or not a live
    manager backs the pod. Serialized per pod so rapid clicks can't race.

    Registered as the poll-button handler at import, keeping pod_format_poll free of a manager import."""
    lock = _format_poll_click_locks.setdefault(event_id, asyncio.Lock())
    async with lock:
        if not interaction.message.embeds:
            await interaction.response.defer()
            return
        manager = ACTIVE_POD_MANAGERS.get(event_id)
        if manager is not None and (manager.drafting or manager.draft_complete):
            await interaction.response.defer()
            return
        new_embed, new_view = _apply_format_poll_vote(
            event_id, interaction.message.embeds[0], interaction.user.mention, code,
        )
        try:
            await interaction.response.edit_message(embed=new_embed, view=new_view)
        except discord.HTTPException:
            log.warning(f"[FORMAT_POLL] edit_failed event={event_id}", exc_info=True)
            return


def _apply_format_poll_write_ins(
    event_id: str, embed: "discord.Embed", mention: str, codes: list[str], adder_name: str,
) -> tuple["discord.Embed", "discord.ui.View", list[str]]:
    """Vote the player for each code: an existing option gains their vote, a new one is added with an "added
    by" credit and their first vote, up to the option cap. Never retracts, so re-submitting a code the player
    already backs is a no-op. Returns the re-render and the codes actually applied."""
    votes = pod_format_poll.votes_from_embed(embed)
    options = pod_format_poll.options_from_embed(embed)
    adders = pod_format_poll.adders_from_embed(embed)
    applied: list[str] = []
    for code in codes:
        if code not in options:
            if len(options) >= pod_format_poll.MAX_ROWED_OPTIONS:
                continue
            options.append(code)
            adders[code] = adder_name
        voters = votes.setdefault(code, [])
        if mention not in voters:
            voters.append(mention)
        applied.append(code)
    options = pod_format_poll.order_options(options, votes)
    return (
        pod_format_poll.rerender_gathering(embed, options, votes, adders),
        pod_format_poll.build_format_poll_view(event_id, options),
        applied,
    )


async def handle_format_poll_add(
    interaction: "discord.Interaction", event_id: str, raw_code: str, message: "discord.Message",
) -> None:
    """Add one or more player-typed set codes to the poll and vote the player for each, then re-render the
    card. Codes can be comma or space separated. Unparseable input is refused ephemerally."""
    codes = pod_format_poll.normalize_write_ins(raw_code)
    if not codes:
        await interaction.response.send_message("Enter set codes like DSK FIN MH3", ephemeral=True)
        return
    lock = _format_poll_click_locks.setdefault(event_id, asyncio.Lock())
    async with lock:
        if not message.embeds:
            await interaction.response.send_message("This poll is no longer active", ephemeral=True)
            return
        new_embed, new_view, applied = _apply_format_poll_write_ins(
            event_id, message.embeds[0], interaction.user.mention, codes, interaction.user.display_name,
        )
        if not applied:
            full = "This poll already has the most formats it can hold."
            await interaction.response.send_message(full, ephemeral=True)
            return
        try:
            await message.edit(embed=new_embed, view=new_view)
        except discord.HTTPException:
            log.warning(f"[FORMAT_POLL] add_edit_failed event={event_id}", exc_info=True)
            await interaction.response.send_message("Could not update the poll", ephemeral=True)
            return
        await interaction.response.send_message(f"Voted for {', '.join(applied)}", ephemeral=True)


pod_format_poll.register_format_poll_click_handler(handle_format_poll_click)
pod_format_poll.register_format_poll_add_handler(handle_format_poll_add)


async def set_event_seating_mode(event_id: str, mode: str) -> str | None:
    """Set a pod's seating mode by event id; updates the live manager when one exists and persists.
    Locked once the draft is underway. Returns an error string or None."""
    if mode not in ("random", "manual", "leaderboard"):
        return "Unknown seating mode"
    manager = ACTIVE_POD_MANAGERS.get(event_id)
    if manager is not None:
        if manager.drafting or manager.draft_complete:
            return "Seating mode is locked once the draft has started"
        manager.seating_mode = mode
    await asyncio.to_thread(persist_seating_mode, event_id, mode)
    if manager is not None:
        await manager.apply_seating_mode()
        await manager.refresh_lobby_now()
    return None


async def set_event_seating(event_id: str, ordered_user_names: list[str]) -> str | None:
    """Apply a manual Draftmancer seating order by event id. Live-only — needs the socket session.
    Returns an error string or None."""
    manager = ACTIVE_POD_MANAGERS.get(event_id)
    if manager is None:
        return "No active Draftmancer session for this pod"
    return await manager.set_seating_order(ordered_user_names)


async def set_event_pick_timer(event_id: str, seconds: int) -> str | None:
    return await store_setup_value(
        event_id, pod_event_settings.PICK_TIMER, seconds,
        lambda manager, value: manager.apply_pick_timer(value))


async def set_event_picks_per_pack(event_id: str, n: int) -> str | None:
    return await store_setup_value(
        event_id, pod_event_settings.PICKS_PER_PACK, n,
        lambda manager, value: manager.apply_picks_per_pack(value))


async def set_event_packs_per_player(event_id: str, n: int) -> str | None:
    return await store_setup_value(
        event_id, pod_event_settings.PACKS_PER_PLAYER, n,
        lambda manager, value: manager.apply_packs_per_player(value))


async def set_event_cards_per_pack(event_id: str, n: int) -> str | None:
    return await store_setup_value(
        event_id, pod_event_settings.CARDS_PER_PACK, n,
        lambda manager, value: manager.apply_cards_per_pack(value))


async def set_event_max_players(event_id: str, n: int) -> str | None:
    return await store_setup_value(
        event_id, pod_event_settings.MAX_PLAYERS, n,
        lambda manager, value: manager.apply_max_players(value))


SetupPush = Callable[["PodDraftManager", int], Awaitable[str | None]]


async def store_setup_value(event_id: str, key: str, value: int, push: SetupPush) -> str | None:
    """Store one Draftmancer setup value on the event, after pushing it to the table when a session is
    live. A pod configured before its lobby opens carries the value into the session; a value the live
    table refuses is not stored. Returns an error string or None."""
    manager = ACTIVE_POD_MANAGERS.get(event_id)
    if manager is not None:
        error = await push(manager, value)
        if error:
            return error
    await asyncio.to_thread(pod_event_settings.store_sync, event_id, **{key: value})
    return None


async def rehydrate_active_lobbies(bot) -> None:
    """Startup sweep: reconnect a manager to any pod whose Draftmancer socket was live (lobby or
    drafting, tournament not yet started) when the bot last stopped, reclaiming ownership so ready
    checks, kicks, seating, and draft start keep working after a restart. The bot's userID is
    derived from the sessionID, so reconnecting to the same session re-lands as the same user and
    setSessionOwner reclaims the chair without forcing players to rejoin a new session."""
    rows = await asyncio.to_thread(_load_live_lobby_pods_sync)
    restored = 0
    for row in rows:
        event_id = row["id"]
        if event_id in ACTIVE_POD_MANAGERS:
            continue
        session_id = row["draftmancer_session"]
        expected = await asyncio.to_thread(_count_participants_sync, event_id)
        manager = await start_manager(
            bot, event_id, session_id, int(row["discord_thread_id"]), row["set_code"], expected,
            event_name=row["name"], draftmancer_url=draftmancer_url_for(session_id),
            kind=row["kind"], reconnect=True,
        )
        if manager is None:
            log.warning(f"[LIFECYCLE] rehydrate_lobby.connect_failed event={event_id} sid={session_id}")
            continue
        restored += 1
        log.info(f"[LIFECYCLE] rehydrate_lobby.restored event={event_id} sid={session_id}")
    if restored:
        log.info(f"startup sweep reconnected {restored} live lobby/draft session(s)")


def _load_live_lobby_pods_sync() -> list[dict]:
    """Pod events whose Draftmancer socket was live but whose tournament hadn't started when the bot
    last stopped — the rows the restart sweep reconnects a manager for."""
    cutoff = datetime.now(timezone.utc) - LOBBY_REHYDRATE_WINDOW
    with SessionLocal() as session:
        rows = session.execute(
            select(
                PodDraftEvent.id,
                PodDraftEvent.draftmancer_session,
                PodDraftEvent.discord_thread_id,
                PodDraftEvent.set_code,
                PodDraftEvent.name,
                PodDraftEvent.kind,
            ).where(
                PodDraftEvent.socket_status == "connected",
                PodDraftEvent.finalized_at.is_(None),
                PodDraftEvent.current_round.is_(None),
                PodDraftEvent.event_time >= cutoff,
            )
        ).all()
    return [dict(row._mapping) for row in rows]


def _count_participants_sync(event_id: str) -> int:
    with SessionLocal() as session:
        return session.execute(
            select(func.count()).select_from(PodDraftParticipant)
            .where(PodDraftParticipant.event_id == event_id)
        ).scalar_one()


async def _find_pinned_lobby_card(thread, bot_user, event_name: str) -> "discord.Message | None":
    """Rediscover the lobby status card pinned by an earlier manager (pre-restart) so a reconnect
    edits it in place instead of posting and pinning a duplicate. The 🤖 Commands field is unique to
    the lobby card, distinguishing it from a pinned standings or round-pairings embed."""
    try:
        pins = await thread.pins()
    except discord.HTTPException:
        log.warning(f"could not fetch pins to rediscover lobby card for {event_name}", exc_info=True)
        return None
    for msg in pins:
        if bot_user is not None and msg.author.id != bot_user.id:
            continue
        for pinned_embed in msg.embeds:
            if any("Commands" in (field.name or "") for field in pinned_embed.fields):
                return msg
    return None


def _rsvp_display_name(rsvp: str, mention_map: dict[int, str]) -> str | None:
    """The display name behind an rsvp entry, resolving a `<@id>` mention through the guild map.
    None for a mention the map has not resolved yet, so a caller can leave it unmarked until it does."""
    text = rsvp.strip()
    m = re.match(r"^<@!?(\d+)>$", text)
    if m:
        return mention_map.get(int(m.group(1)))
    return text


def _classify_names_sync(names: list[str]) -> list[tuple[str, str | None]]:
    with SessionLocal() as session:
        return classify_lobby_names(session, names)


def discord_ids_for_names_sync(names: list[str]) -> dict[str, str | None]:
    """Map each Draftmancer userName to its linked player's discord_id (or None when unrecognized)."""
    with SessionLocal() as session:
        result: dict[str, str | None] = {}
        for name in names:
            player = player_for_name(session, name)
            result[name] = player.discord_id if player else None
        return result


def _leaderboard_seat_order_sync(names: list[str], event_id: str) -> list[str]:
    with SessionLocal() as session:
        return leaderboard_seat_order(session, names, championship.rank_override(session, event_id))


def arena_matches_name(arena_name: str, candidate: str) -> bool:
    """Whether a Draftmancer handle is this Discord name, ignoring the trailing Arena suffix, so `MNG#61656`
    matches `MNG`."""
    norm = normalize_player_name(arena_name)
    return bool(norm) and norm == candidate.lower()


def arena_matches_token(arena_name: str, candidate: str) -> bool:
    """The looser pass: `wonderland#12345` matches a member displayed as `Alice (Wonderland)`."""
    norm = normalize_player_name(arena_name)
    return bool(norm) and name_token_match(norm, candidate)


def _find_guild_member_for_arena(guild: discord.Guild, arena_name: str) -> discord.Member | None:
    """The guild member behind a Draftmancer handle. Exact matches win over token matches across the whole
    guild, so a nickname that merely contains someone else's handle cannot outrank the real owner."""
    for matches in (arena_matches_name, arena_matches_token):
        for member in guild.members:
            if matches(arena_name, member.display_name) or matches(arena_name, member.name):
                return member
    return None


def _ensure_players_for_members_sync(pairs: list[tuple[str, discord.Member]]) -> None:
    """For each (arena_name, member) pair, find or lazily create a Player row keyed by discord_id.
    Only a full ArenaID#12345 handle is stored as `arena_name` — a bare Draftmancer nickname goes to
    aliases only — and a stored full handle is never overwritten here."""
    if not pairs:
        return
    with SessionLocal() as session:
        taken_slugs = set(session.execute(select(Player.slug)).scalars().all())
        for arena_name, member in pairs:
            discord_id = str(member.id)
            normalized = normalize_player_name(arena_name)
            existing = session.execute(
                select(Player).where(Player.discord_id == discord_id)
            ).scalar_one_or_none()
            if existing is not None:
                if full_arena_handle(arena_name) and not full_arena_handle(existing.arena_name):
                    existing.arena_name = arena_name
                    log.info(f"backfilled arena_name for {member.display_name} → {arena_name}")
                if normalized and normalized not in existing.arena_aliases:
                    existing.arena_aliases = [*existing.arena_aliases, normalized]
                continue
            slug = disambiguate_slug(slugify(member.display_name), taken_slugs)
            taken_slugs.add(slug)
            session.add(Player(
                slug=slug,
                discord_id=discord_id,
                discord_username=member.name,
                display_name=member.display_name,
                avatar_hash=extract_avatar_hash(member),
                arena_name=arena_name if full_arena_handle(arena_name) else None,
                arena_aliases=[normalized] if normalized else [],
                active=True,
                leaderboard_opt_in=False,
            ))
            log.info(f"auto-created Player row for guild member {member.display_name} (arena={arena_name})")
        session.commit()
