"""Pod-draft slash commands."""
from __future__ import annotations

import asyncio
import io
import logging
import re
from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands

from bot import audit, emojis
from bot.commands import descriptions as desc
from bot.commands.messages import (
    MSG_ADMIN_ONLY, MSG_ARENA_BAD_FORMAT, MSG_ARENA_LINKED, MSG_RESTART_NOT_ORGANIZER,
)
from bot.config import settings
from bot.database import SessionLocal
from bot.discord_helpers import extract_avatar_hash
from bot.services import championship as championship_service
from bot.services import pod_event_settings
from bot.services import pod_format
from bot.services.lobby_embed import guard_ready_check, open_settings_panel
from bot.services.pod_active import ACTIVE_POD_MANAGERS, set_card_phase_hook, set_pod_card_hook
from bot.services.pod_draft_manager import (
    cancel_pod_event,
    post_format_vote,
    set_event_cards_per_pack,
    set_event_format,
    set_event_max_players,
    set_event_packs_per_player,
    set_event_pairing_mode,
    set_event_pick_timer,
    set_event_picks_per_pack,
    set_event_seating,
    set_event_seating_mode,
    set_card_refresh_hook,
    set_seeding_refresh_hook,
    set_seeding_repost_hook,
)
from bot.services.pod_drafts import (
    is_championship,
    load_event_closed_decklist_sync,
    load_event_description_sync,
    load_event_drafted_sync,
    load_event_id_by_name_sync,
    load_event_id_by_thread_sync,
    load_event_kind_sync,
    load_event_name_sync,
    load_event_pairing_mode_sync,
    load_event_seating_mode_sync,
    load_event_seeding_context_sync,
    load_event_set_code_sync,
    load_event_time_sync,
    load_event_thread_id_sync,
    attach_arena_alias,
    lobby_match_status,
    search_event_names_sync,
    set_event_closed_decklist_sync,
    set_event_description_sync,
)
from bot.commands.pod_rsvp import (
    fetch_channel,
    post_pod_card,
    reflect_format_change,
    refresh_card_embed,
    reschedule_event,
)
from bot.services import pod_launch
from bot.services.player_stats import SeededAttendee, rank_ordered_names, seed_attendees, seated_ring_order
from bot.services.pod_seating_select import SEATING_ORDER_MARKER, seating_change_message
from bot.services.pod_seating_image import octagon_text, render_octagon_png
from bot.services.seeding_table import seeding_block
from bot.sets import active_set_code
from bot.tasks.pod_draft_reminder import event_rsvps
from bot.services.pod_settings_view import PodSettingsView
from bot.services.pod_tournament import (
    REVIEW_EMOJI,
    actor_label,
    build_champion_announcement_view_for_event,
    build_draft_review_embed,
    build_draft_review_message,
    build_live_submit_deck_button,
    build_replays_link_button,
    build_standings_embed_for_event,
    build_thread_link_button,
    is_pod_organizer,
    open_manage_rounds,
    post_trophy_hype_for_event,
    refresh_round_pairing_messages,
    round_picker_options,
)
from bot.services.pod_team_showcase import build_team_championship_view_for_event
from bot.services.pod_voice import pod_voice_channel_url


log = logging.getLogger(__name__)

_ARENA_INPUT_RE = re.compile(r"^.+#\d+$")

MSG_LINK_ARENA_NO_LOBBY_MATCH = (
    "⚠️ No one in an active pod lobby is drafting as `{arena_name}`. Check that it matches "
    "your Draftmancer name exactly"
)
MSG_LINK_ARENA_DID_YOU_MEAN = "Did you mean `{suggestion}`? Re-run `/link-arena` with that exact handle"
MSG_NO_ACTIVE_POD = "No active pod draft session right now"

YES_EMOJI = "✅"
MAYBE_EMOJI = "🤷"
CHAMPIONSHIP_CUT = 8
MANUAL_READY_MIN_PLAYERS = 2
SEEDING_YES_HEADER = f"**{YES_EMOJI} Yes ("
SEEDING_MAYBE_HEADER = f"**{MAYBE_EMOJI} Maybe ("

SEEDING_PHASE_LIVE = "🟢 **Live** - On Draftmancer"
SEEDING_CUT_ALTERNATES = "Alternates"
SEEDING_CUT_OVER_CAP = "Past the cut"


def seeding_phase_projected() -> str:
    """Pre-lobby seeding header — built at call time so the llu emoji resolves from the live registry."""
    active = active_set_code()
    url = f"{settings.leaderboard_url}/{active}"
    return f"{emojis.prefix('llu')}Players ranked by **[{active} Leaderboard]({url})**"

MSG_SEEDING_WAITING = "Waiting for players to confirm attendance"
MSG_SEEDING_NOT_POD_THREAD = "Run this inside a pod-draft thread"
MSG_SEEDING_NO_RSVPS = f"No {YES_EMOJI} or {MAYBE_EMOJI} RSVPs on this pod yet"



class PodDraft(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="pod-ready", description=desc.POD_READY)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def pod_ready(self, interaction: discord.Interaction) -> None:
        manager = _find_manager_for_thread(interaction)
        if manager is None:
            await interaction.response.send_message(MSG_NO_ACTIVE_POD, ephemeral=True)
            return
        thread = interaction.channel
        log.info(f"ready-check: {interaction.user} in thread {interaction.channel_id}")
        actor = actor_label(interaction)
        if await guard_ready_check(
            interaction, manager, thread, initiated_by=actor, min_players=MANUAL_READY_MIN_PLAYERS,
        ):
            return
        await interaction.response.defer(thinking=False)
        poster = ReplyPoster(interaction)
        err = await manager.initiate_ready_check(
            thread, initiated_by=actor, initiator=interaction.user, post=poster,
        )
        if err is not None:
            log.warning(f"ready-check: failed — {err}")
            await interaction.followup.send(f"⚠️ {err}")
            return
        await poster.clear_if_unused()

    @app_commands.command(name="pod-start", description=desc.POD_START)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def pod_start(self, interaction: discord.Interaction) -> None:
        manager = _find_manager_for_thread(interaction)
        if manager is None:
            await interaction.response.send_message(MSG_NO_ACTIVE_POD, ephemeral=True)
            return
        log.info(f"pod-start: {interaction.user} force-starting in thread {interaction.channel_id}")
        await interaction.response.defer(thinking=False)
        poster = ReplyPoster(interaction)
        err = await manager.force_start(post=poster)
        if err is not None:
            log.warning(f"pod-start: failed — {err}")
            await interaction.followup.send(f"⚠️ {err}")
            return
        await poster.clear_if_unused()

    @app_commands.command(name="pod-team", description=desc.POD_TEAM)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def pod_team(self, interaction: discord.Interaction) -> None:
        manager = _find_manager_for_thread(interaction)
        if manager is None:
            await interaction.response.send_message(MSG_NO_ACTIVE_POD, ephemeral=True)
            return
        log.info(f"pod-team: {interaction.user} offering team vote in thread {interaction.channel_id}")
        await interaction.response.defer(thinking=False)
        poster = ReplyPoster(interaction)
        err = await manager.offer_team_vote_manual(post=poster)
        if err is not None:
            await interaction.followup.send(f"⚠️ {err}")
            return
        await poster.clear_if_unused()

    @app_commands.command(name="vote-format", description=desc.VOTE_FORMAT)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def vote_format(self, interaction: discord.Interaction) -> None:
        log.info(f"vote-format: {interaction.user} posting format vote in channel {interaction.channel_id}")
        await interaction.response.defer(thinking=False)
        thread_id = str(interaction.channel_id) if interaction.channel_id else None
        event_id = await asyncio.to_thread(load_event_id_by_thread_sync, thread_id) if thread_id else None
        poster = ReplyPoster(interaction)
        err = await post_format_vote(interaction.channel, event_id, post=poster)
        if err is not None:
            await interaction.followup.send(f"⚠️ {err}")
            return
        await poster.clear_if_unused()

    @app_commands.command(name="pod-pause", description=desc.POD_PAUSE)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def pod_pause(self, interaction: discord.Interaction) -> None:
        manager = _find_manager_for_thread(interaction)
        if manager is None:
            await interaction.response.send_message(MSG_NO_ACTIVE_POD, ephemeral=True)
            return
        err = await manager.pause_draft()
        if err is not None:
            await interaction.response.send_message(f"⚠️ {err}", ephemeral=True)
            return
        log.info(f"pod-pause: {interaction.user} paused draft in thread {interaction.channel_id}")
        await interaction.response.send_message(
            f"⏸️ {interaction.user.mention} paused the draft. Resume with `/pod-unpause`",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name="pod-unpause", description=desc.POD_UNPAUSE)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def pod_unpause(self, interaction: discord.Interaction) -> None:
        manager = _find_manager_for_thread(interaction)
        if manager is None:
            await interaction.response.send_message(MSG_NO_ACTIVE_POD, ephemeral=True)
            return
        err = await manager.resume_draft()
        if err is not None:
            await interaction.response.send_message(f"⚠️ {err}", ephemeral=True)
            return
        log.info(f"pod-unpause: {interaction.user} resumed draft in thread {interaction.channel_id}")
        await interaction.response.send_message(
            f"▶️ {interaction.user.mention} resumed the draft",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name="pod-restart", description=desc.POD_RESTART)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def pod_restart(self, interaction: discord.Interaction) -> None:
        if not await is_pod_organizer(self.bot, interaction.user):
            await interaction.response.send_message(MSG_RESTART_NOT_ORGANIZER, ephemeral=True)
            return
        manager = _find_manager_for_thread(interaction)
        if manager is None:
            await interaction.response.send_message(MSG_NO_ACTIVE_POD, ephemeral=True)
            return
        log.warning(f"pod-restart: {interaction.user} restarting draft in thread {interaction.channel_id}")
        await interaction.response.defer(thinking=False)
        poster = ReplyPoster(interaction)
        err = await manager.restart_draft(
            interaction.channel, initiated_by=actor_label(interaction), post=poster,
        )
        if err is not None:
            log.warning(f"pod-restart: failed — {err}")
            await interaction.followup.send(f"⚠️ {err}")
            return
        await poster.clear_if_unused()

    @app_commands.command(name="pod-review", description=desc.POD_REVIEW)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def pod_review(self, interaction: discord.Interaction) -> None:
        thread_id = str(interaction.channel_id) if interaction.channel_id else None
        event_id = await asyncio.to_thread(load_event_id_by_thread_sync, thread_id) if thread_id else None
        if event_id is None:
            await interaction.response.send_message("Run this inside a pod-draft thread", ephemeral=True)
            return
        embed = await build_draft_review_embed(event_id)
        if embed is None:
            await interaction.response.send_message("No players are on record for this pod yet", ephemeral=True)
            return
        log.info(f"pod-review: {interaction.user} started review for event_id={event_id}")
        voice_url = pod_voice_channel_url(interaction.guild)
        await interaction.response.send_message(
            content=build_draft_review_message(voice_url),
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        message = await interaction.original_response()
        try:
            await message.add_reaction(REVIEW_EMOJI)
        except discord.HTTPException:
            log.warning("pod-review: could not add the review reaction", exc_info=True)

    @commands.command(name="start")
    @commands.is_owner()
    async def start_lobby(self, ctx: commands.Context) -> None:
        """Owner-only. Bypass the T-10 wait and open the Draftmancer lobby for this thread now."""
        thread_id = str(ctx.channel.id) if ctx.channel else None
        event_id = await asyncio.to_thread(load_event_id_by_thread_sync, thread_id) if thread_id else None
        if event_id is None:
            await ctx.reply("Run this inside a pod-draft thread", mention_author=False)
            return
        log.info(f"!start: {ctx.author} opening lobby early for event_id={event_id}")
        scheduler = getattr(self.bot, "pod_scheduler", None)
        if scheduler is not None:
            try:
                scheduler.remove_job(f"pod-ondemand-open-{event_id}")
            except Exception:
                log.info(f"no pending open job to cancel for {event_id}", exc_info=True)
        await pod_launch.open_ondemand_lobby(self.bot, event_id)

    @app_commands.command(name="pod-settings", description=desc.POD_SETTINGS)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def pod_settings(self, interaction: discord.Interaction) -> None:
        await open_settings_panel(interaction)

    @app_commands.command(
        name="link-arena",
        description=desc.LINK_ARENA,
    )
    @app_commands.describe(name="Your full MTG Arena handle: ArenaID#12345")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def pod_link_arena(self, interaction: discord.Interaction, name: str) -> None:
        user_id = str(interaction.user.id)
        arena_name = name.strip()
        mention = interaction.user.mention
        audit.event("pod_link_arena_invoked", user_id=user_id, arena_name=arena_name)
        no_pings = discord.AllowedMentions(users=False, everyone=False, roles=False)

        if not _ARENA_INPUT_RE.match(arena_name):
            audit.event("pod_link_arena_bad_format", user_id=user_id, arena_name=arena_name)
            await interaction.response.send_message(MSG_ARENA_BAD_FORMAT, ephemeral=True)
            return

        with SessionLocal() as session:
            player_id = attach_arena_alias(
                session,
                discord_id=user_id,
                discord_username=interaction.user.name,
                display_name=interaction.user.display_name,
                avatar_hash=extract_avatar_hash(interaction.user),
                arena_name=arena_name,
                overwrite=True,
            )
            session.commit()

        audit.event("pod_link_arena_success", user_id=user_id, player_id=player_id)
        log.info(f"pod-link-arena: {interaction.user} linked {arena_name} (player_id={player_id})")
        await interaction.response.send_message(
            MSG_ARENA_LINKED.format(emoji=emojis.get("mtga"), mention=mention, arena_name=arena_name),
            allowed_mentions=no_pings,
        )

        await self._warn_if_no_lobby_match(interaction, arena_name, player_id)

        for manager in list(ACTIVE_POD_MANAGERS.values()):
            asyncio.create_task(manager.refresh_lobby_now())
            asyncio.create_task(refresh_round_pairing_messages(manager))

    async def _warn_if_no_lobby_match(
        self, interaction: discord.Interaction, arena_name: str, player_id: str
    ) -> None:
        """Ephemeral nudge when the just-linked handle resolves to no seat in any live lobby — the
        typo case where the link silently takes no effect. Skipped when no lobby is running."""
        live_names = _live_lobby_names()
        if not live_names:
            return
        matched, suggestion = await asyncio.to_thread(
            lobby_match_status, arena_name, player_id, live_names,
        )
        if matched:
            return
        warning = MSG_LINK_ARENA_NO_LOBBY_MATCH.format(arena_name=arena_name)
        if suggestion is not None:
            warning = f"{warning}\n{MSG_LINK_ARENA_DID_YOU_MEAN.format(suggestion=suggestion)}"
        audit.event("pod_link_arena_no_lobby_match", user_id=str(interaction.user.id),
                    arena_name=arena_name, suggestion=suggestion)
        await interaction.followup.send(warning, ephemeral=(interaction.guild is not None))

    @app_commands.command(name="pod-seeding", description=desc.POD_SEEDING)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def pod_seeding(self, interaction: discord.Interaction) -> None:
        thread_id = str(interaction.channel_id) if interaction.channel_id else None
        event_id = await asyncio.to_thread(load_event_id_by_thread_sync, thread_id) if thread_id else None
        if event_id is None:
            await interaction.response.send_message(MSG_SEEDING_NOT_POD_THREAD, ephemeral=True)
            return

        await interaction.response.defer(thinking=False)
        seating_mode = await asyncio.to_thread(load_event_seating_mode_sync, event_id)
        if seating_mode == "leaderboard":
            file, embed = await seating_message_for_event(self.bot, event_id)
            if embed is None:
                await interaction.followup.send(MSG_SEEDING_NO_RSVPS)
                return
        else:
            yes, maybe = await event_rsvps(event_id)
            seen = {n.casefold() for n in yes}
            maybe = [n for n in maybe if n.casefold() not in seen]
            if not yes and not maybe:
                await interaction.followup.send(MSG_SEEDING_NO_RSVPS)
                return

            live = ACTIVE_POD_MANAGERS.get(event_id)
            seat_cap = live.max_players if live is not None else settings.pod_draft_max_players
            file, embed = await asyncio.to_thread(
                build_seeding_image_message_from_names, yes, maybe, seat_cap=seat_cap,
            )
        log.info(f"pod-seeding: {interaction.user} for event_id={event_id} (mode={seating_mode})")
        if file is not None:
            posted = await interaction.followup.send(embed=embed, file=file, wait=True)
        else:
            posted = await interaction.followup.send(embed=embed, wait=True)
        await finalize_seeding_post(interaction.channel, self.bot.user, posted)

    @app_commands.command(
        name="pod-standings",
        description=desc.POD_STANDINGS,
    )
    @app_commands.describe(event="Pick an event to publish standings for; defaults to the current thread")
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def pod_standings(self, interaction: discord.Interaction, event: str | None = None) -> None:
        await interaction.response.defer(thinking=False)

        if event:
            event_id = await asyncio.to_thread(load_event_id_by_name_sync, event)
            if event_id is None:
                await interaction.followup.send(f"No pod-draft event named `{event}`")
                return
        else:
            channel = interaction.channel
            thread_id = str(channel.id) if channel is not None else None
            event_id = await asyncio.to_thread(load_event_id_by_thread_sync, thread_id) if thread_id else None
            if event_id is None:
                await interaction.followup.send(
                    "Run this inside a pod-draft thread, or pass an `event` to publish standings for a specific pod",
                )
                return

        embed = await build_standings_embed_for_event(event_id)
        if embed is None:
            await interaction.followup.send("No standings yet")
            return

        log.info(f"pod-standings: {interaction.user} posted standings for event_id={event_id}")
        thread_id = await asyncio.to_thread(load_event_thread_id_sync, event_id)
        invoked_outside_thread = thread_id is not None and str(interaction.channel_id) != thread_id
        event_name = await asyncio.to_thread(load_event_name_sync, event_id)

        view = discord.ui.View()
        if invoked_outside_thread and interaction.guild_id is not None:
            view.add_item(build_thread_link_button(interaction.guild_id, thread_id))
        view.add_item(build_replays_link_button(event_name))
        if not invoked_outside_thread:
            view.add_item(build_live_submit_deck_button())

        await interaction.followup.send(embed=embed, view=view)

    @pod_standings.autocomplete("event")
    async def _pod_standings_event_autocomplete(
        self, interaction: discord.Interaction, current: str,
    ) -> list[app_commands.Choice[str]]:
        names = await asyncio.to_thread(search_event_names_sync, current)
        return [app_commands.Choice(name=n, value=n) for n in names]

    @app_commands.command(
        name="pod-champion",
        description=desc.POD_CHAMPION,
    )
    @app_commands.describe(event="Pod-draft event to announce; defaults to the current thread")
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def pod_champion(self, interaction: discord.Interaction, event: str | None = None) -> None:
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message(MSG_ADMIN_ONLY, ephemeral=True)
            return
        await interaction.response.defer(thinking=False)

        if event:
            event_id = await asyncio.to_thread(load_event_id_by_name_sync, event)
            if event_id is None:
                await interaction.followup.send(f"No pod-draft event named `{event}`")
                return
        else:
            channel = interaction.channel
            thread_id = str(channel.id) if channel is not None else None
            event_id = await asyncio.to_thread(load_event_id_by_thread_sync, thread_id) if thread_id else None
            if event_id is None:
                await interaction.followup.send(
                    "Run this inside a pod-draft thread, or pass an `event` to announce a specific pod",
                )
                return

        pairing_mode = await asyncio.to_thread(load_event_pairing_mode_sync, event_id)
        if pairing_mode == "team":
            view = await build_team_championship_view_for_event(event_id, guild_id=interaction.guild_id)
        else:
            view = await build_champion_announcement_view_for_event(
                event_id, guild_id=interaction.guild_id, guild=interaction.guild)
        if view is None:
            await interaction.followup.send(
                "Champion announcement isn't ready. The trophy match has no winner on record yet",
            )
            return

        log.info(f"pod-champion: {interaction.user} re-posted champion announcement for event_id={event_id}")
        await interaction.followup.send(view=view, allowed_mentions=discord.AllowedMentions.none())
        await post_trophy_hype_for_event(interaction.client, event_id, interaction.guild)

    @pod_champion.autocomplete("event")
    async def _pod_champion_event_autocomplete(
        self, interaction: discord.Interaction, current: str,
    ) -> list[app_commands.Choice[str]]:
        names = await asyncio.to_thread(search_event_names_sync, current)
        return [app_commands.Choice(name=n, value=n) for n in names]

    @app_commands.command(name="pod-takeover", description=desc.POD_TAKEOVER)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def pod_takeover(self, interaction: discord.Interaction) -> None:
        manager = _find_manager_for_thread(interaction)
        if manager is None:
            await interaction.response.send_message(MSG_NO_ACTIVE_POD, ephemeral=True)
            return

        target = _pick_takeover_target(manager, interaction.user.display_name)
        if target is None:
            await interaction.response.send_message(
                "No suitable Draftmancer user found to transfer ownership to. "
                "Make sure you're in the Draftmancer session before running this",
                ephemeral=True,
            )
            return
        target_user_id, target_user_name = target

        log.info(f"pod-takeover: {interaction.user} → {target_user_name}")
        await interaction.response.defer(thinking=False)
        ok, err = await manager.takeover(target_user_id)
        if not ok:
            log.warning(f"pod-takeover: failed — {err}")
            await interaction.followup.send(f"⚠️ Takeover failed: {err}")
            return
        await interaction.followup.send(
            f"👑 {interaction.user.mention} is now in control of the Draftmancer session. Bot disconnected"
        )


class ReplyPoster:
    """The command's own reply as the place a card lands, so Discord heads it with who ran the command"""

    def __init__(self, interaction: discord.Interaction) -> None:
        self.interaction = interaction
        self.used = False

    async def __call__(self, **kwargs) -> discord.Message:
        sent = await self.interaction.followup.send(**kwargs, wait=True)
        self.used = True
        return await self.interaction.channel.fetch_message(sent.id)

    async def clear_if_unused(self) -> None:
        """Drop the pending reply when nothing took it, so no empty placeholder is left behind"""
        if self.used:
            return
        try:
            await self.interaction.delete_original_response()
        except discord.HTTPException:
            log.info("could not clear an unused command reply", exc_info=True)


def _seed_rsvps(
    yes: list[str], maybe: list[str],
) -> tuple[list[SeededAttendee], list[SeededAttendee]]:
    with SessionLocal() as session:
        return seed_attendees(session, yes), seed_attendees(session, maybe)


def _rank_ordered_names_sync(names: list[str], rank_override: dict[str, int] | None = None) -> list[str]:
    with SessionLocal() as session:
        return rank_ordered_names(session, names, rank_override)


def build_seeding_image_message_from_names(
    yes: list[str], maybe: list[str] | None = None, *, seat_cap: int = CHAMPIONSHIP_CUT,
    header: str | None = None, cut_label: str | None = None,
) -> tuple[discord.File | None, discord.Embed]:
    """Seed RSVP-style name lists and render the seeding message: the table embed with the round-table
    octagon as a PNG inside it. Shared by /pod-seeding, the Leaderboard-seats trigger, and the testlobby
    preview. `seat_cap` bounds how many seeds fill the seats: top-8 when Leaderboard seats decide the
    pod, the pod maximum otherwise. File is None for non-8 pods (the embed still stands alone)."""
    yes_seeded, maybe_seeded = _seed_rsvps(yes, list(maybe or []))
    embed = _build_seeding_embed(yes_seeded, maybe_seeded, seat_cap=seat_cap, header=header, cut_label=cut_label)
    file = _build_seeding_image(yes_seeded, embed, seat_cap=seat_cap)
    return file, embed


def build_seeding_image_message_for_pool(
    pool: list[str], overflow: list[str], maybe: list[str],
    *, header: str | None = None, cut_label: str | None = None, rank_override: dict[str, int] | None = None,
) -> tuple[discord.File | None, discord.Embed]:
    """Seeding message where `pool` holds the table regardless of rank: pool and overflow are seeded
    separately so a high seed who only RSVP'd can't displace a locked Draftmancer player."""
    with SessionLocal() as session:
        pool_seeded = seed_attendees(session, pool, rank_override)
        overflow_seeded = seed_attendees(session, overflow, rank_override)
        maybe_seeded = seed_attendees(session, maybe, rank_override)
    yes_seeded = pool_seeded + overflow_seeded
    embed = _build_seeding_embed(
        yes_seeded, maybe_seeded, seat_cap=CHAMPIONSHIP_CUT, header=header, cut_label=cut_label)
    file = _build_seeding_image(yes_seeded, embed, seat_cap=CHAMPIONSHIP_CUT)
    return file, embed


CHAMPIONSHIP_STANDINGS_MAX = 60
CHAMPIONSHIP_STANDINGS_BUDGET = 3800


def build_leaderboard_standings_embed(attendees: list[SeededAttendee], *, timestamp: datetime) -> discord.Embed:
    """The full leaderboard as the shared ranked table (Rnk / Player / Pts / 🏆), as deep as one embed
    holds, under the seeding header — no seats, no Yes grouping, no ring. Backs the locked standings
    snapshot a Set Championship posts in its thread. `timestamp` dates the footer."""
    header = seeding_phase_projected()
    shown = attendees[:CHAMPIONSHIP_STANDINGS_MAX]
    description = header
    while shown:
        candidate = f"{header}\n\n{seeding_block(shown)}"
        if len(candidate) <= CHAMPIONSHIP_STANDINGS_BUDGET:
            description = candidate
            break
        shown = shown[:-1]
    embed = discord.Embed(description=description, color=discord.Color.green())
    embed.set_footer(text=f"Timestamped {timestamp:%B} {timestamp.day}, {timestamp.year}")
    return embed


_OPEN_SEAT = SeededAttendee(slug=None, display_name="(open)", rank=None, score=None, trophies=None)


def _pod_ring(yes: list[SeededAttendee], seat_cap: int) -> list[SeededAttendee] | None:
    """Seat the pod (capped at seat_cap) into the ring for the image, padding an odd count to even
    with an open seat. Returns the seated ring for 6-10 players, else None (no ring drawn)."""
    pool = list(yes[:seat_cap])
    if len(pool) % 2:
        pool.append(_OPEN_SEAT)
    if not 6 <= len(pool) <= 10:
        return None
    return seated_ring_order(pool)


def _build_seeding_image(
    yes: list[SeededAttendee], embed: discord.Embed, *, seat_cap: int,
) -> discord.File | None:
    """Render the seated ring as a monospace PNG (6-10 players) and attach it to the embed; None otherwise."""
    seated = _pod_ring(yes, seat_cap)
    if seated is None:
        return None
    png = render_octagon_png(octagon_text([a.display_name for a in seated]))
    embed.set_image(url="attachment://seating.png")
    return discord.File(io.BytesIO(png), "seating.png")


def _build_seeding_embed(
    yes: list[SeededAttendee], maybe: list[SeededAttendee], *, seat_cap: int,
    header: str | None = None, cut_label: str | None = None,
) -> discord.Embed:
    """Seeding embed shared by /pod-seeding and the Leaderboard-seats trigger. The Yes list is seated by
    rank (the top seat_cap fill the ring); Maybe is listed without seats. The round-table octagon is
    attached as a PNG image (see _build_seeding_image) — embed code blocks wrap too narrowly for the
    text version. `header` prepends a phase line; `cut_label` titles the below-cut group."""
    parts: list[str] = []
    if header:
        parts.append(header)
    if yes:
        cut = seat_cap if len(yes) > seat_cap else None
        ring = seated_ring_order(yes[:seat_cap])
        seat_of = {id(a): i + 1 for i, a in enumerate(ring)}
        yes_seats = [seat_of.get(id(a)) for a in yes]
        parts.append(
            f"{SEEDING_YES_HEADER}{len(yes)})**\n"
            + seeding_block(yes, seats=yes_seats, cut_after=cut, cut_label=cut_label)
        )
    if maybe:
        parts.append(f"{SEEDING_MAYBE_HEADER}{len(maybe)})**\n" + seeding_block(maybe))
    return discord.Embed(description="\n\n".join(parts), color=discord.Color.green())


def has_seeding_headers(message: discord.Message) -> bool:
    """True for a leaderboard seeding table — identified by its Yes/Maybe embed headers."""
    return any(
        SEEDING_YES_HEADER in (e.description or "") or SEEDING_MAYBE_HEADER in (e.description or "")
        for e in message.embeds
    )


async def delete_stale_seeding_messages(
    channel: discord.Thread | discord.TextChannel, bot_user: discord.ClientUser, *,
    keep_message_id: int | None = None, include_pinned: bool = False,
) -> None:
    def stale(message: discord.Message) -> bool:
        if message.id == keep_message_id or message.author.id != bot_user.id:
            return False
        if message.pinned and not include_pinned:
            return False
        if SEATING_ORDER_MARKER in message.content:
            return True
        return has_seeding_headers(message)

    try:
        await channel.purge(limit=None, check=stale, reason="Stale pod-seeding table")
    except discord.HTTPException as exc:
        log.warning(f"pod-seeding: could not purge stale seeding messages: {exc}")


async def build_pod_settings_view(bot, event_id: str, *, is_organizer: bool) -> PodSettingsView:
    """Settings panel wired for `event_id`. Shared by /pod-settings and the lobby Settings button.
    Link Players and Kick Player need a live Draftmancer session, and Link Players stays through the
    draft so an unlinked seat can be fixed mid-draft. The format/pairing/seats/pick-options controls are
    pre-draft only: they read the live table when there is one and the pod's stored setup otherwise, so a
    scheduled pod can be configured before its lobby opens.

    Cancel Draft is Organizer-only on a tournament pod, whose signups and matches belong to the people who
    organized it. A mock draft opens it to everyone until the picks are done: anyone can open a lobby, so
    anyone can close one, but a finished draft has decks and logs on the site that nobody else's click
    should take down.

    A mock draft plays no matches and opens its draft logs to everyone the moment the draft ends, so
    Pairings and Closed Decklist are left off its panel."""
    current_code = await asyncio.to_thread(load_event_set_code_sync, event_id)
    current_mode = await asyncio.to_thread(load_event_pairing_mode_sync, event_id)
    current_seating = await asyncio.to_thread(load_event_seating_mode_sync, event_id)
    event_name = await asyncio.to_thread(load_event_name_sync, event_id)
    mock = await asyncio.to_thread(load_event_kind_sync, event_id) == "mock"
    drafted = await asyncio.to_thread(load_event_drafted_sync, event_id)
    manager = ACTIVE_POD_MANAGERS.get(event_id)
    drafting = manager is not None and (manager.drafting or manager.draft_complete)
    setup_open = not drafting and not drafted
    scheduled = await asyncio.to_thread(pod_launch.scheduled_card_ref_sync, event_id) is not None
    thread_id = await asyncio.to_thread(load_event_thread_id_sync, event_id)
    notice_channel = await fetch_channel(bot, thread_id) if thread_id else None

    async def on_format(inter: discord.Interaction, code: str) -> str | None:
        err = await set_event_format(bot, event_id, code)
        if err is None:
            await reflect_format_change(bot, event_id)
        return err

    async def on_pairing(inter: discord.Interaction, mode: str) -> str | None:
        return await set_event_pairing_mode(event_id, mode)

    async def on_seating_mode(inter: discord.Interaction, mode: str) -> str | None:
        return await set_event_seating_mode(event_id, mode)

    async def on_seating_table(inter: discord.Interaction) -> None:
        await post_seeding_table(bot, event_id, inter.channel)

    async def on_seated(inter: discord.Interaction, labels: list[str]) -> None:
        await post_manual_seating_table(bot, inter.channel, labels, actor_label(inter))

    async def on_timer(inter: discord.Interaction, value: str) -> str | None:
        return await set_event_pick_timer(event_id, int(value))

    async def on_picks_per_pack(inter: discord.Interaction, value: str) -> str | None:
        return await set_event_picks_per_pack(event_id, int(value))

    async def on_packs(inter: discord.Interaction, value: str) -> str | None:
        return await set_event_packs_per_player(event_id, int(value))

    async def on_cards_per_pack(inter: discord.Interaction, value: str) -> str | None:
        return await set_event_cards_per_pack(event_id, int(value))

    async def on_max_players(inter: discord.Interaction, value: str) -> str | None:
        return await set_event_max_players(event_id, int(value))

    current_closed_decklist = await asyncio.to_thread(load_event_closed_decklist_sync, event_id)

    async def on_closed_decklist(inter: discord.Interaction, value: str) -> str | None:
        await asyncio.to_thread(set_event_closed_decklist_sync, event_id, value == "1")
        return None

    on_seating = None
    seat_order_provider = None
    kick_targets_provider = None
    on_kick = None
    current_timer = None
    current_picks_per_pack = None
    current_max_players = None
    current_packs = None
    current_cards_per_pack = None
    link_targets_provider = None
    on_link = None
    if setup_open:
        setup = pod_event_settings.from_manager(manager) if manager is not None else (
            await asyncio.to_thread(pod_event_settings.load_sync, event_id))
        current_timer = setup[pod_event_settings.PICK_TIMER]
        current_picks_per_pack = setup[pod_event_settings.PICKS_PER_PACK]
        current_max_players = setup[pod_event_settings.MAX_PLAYERS]
        current_packs = setup[pod_event_settings.PACKS_PER_PLAYER]
        current_cards_per_pack = setup[pod_event_settings.CARDS_PER_PACK]
    if manager is not None:
        link_targets_provider = manager.unrecognized_lobby_names

        async def on_link(inter: discord.Interaction, arena_name: str, member: discord.abc.User) -> str | None:
            return await manager.link_seat(member, arena_name)

        if not drafting:
            seat_order_provider = manager.seating_lobby_order
            kick_targets_provider = manager.kick_targets

            async def on_seating(inter: discord.Interaction, ordered_user_names: list[str]) -> str | None:
                return await set_event_seating(event_id, ordered_user_names)

            async def on_kick(inter: discord.Interaction, user_id: str) -> str | None:
                return await manager.kick_player(user_id)

    on_manage_rounds = None
    if await asyncio.to_thread(round_picker_options, event_id):
        async def on_manage_rounds(inter: discord.Interaction) -> None:
            await open_manage_rounds(inter, event_id)

    on_restart = None
    if manager is not None and manager.drafting and not manager.draft_complete:
        async def on_restart(inter: discord.Interaction) -> str | None:
            thread = notice_channel or inter.channel
            return await manager.restart_draft(thread, initiated_by=actor_label(inter))

    on_cancel = None
    if is_organizer or (mock and not drafted):
        async def on_cancel(inter: discord.Interaction) -> str | None:
            return await cancel_pod_event(event_id, actor=actor_label(inter))

    on_reschedule = None
    on_description = None
    current_description = None
    current_start = None
    if scheduled and not drafting:
        current_start = await asyncio.to_thread(load_event_time_sync, event_id)

        async def on_reschedule(inter: discord.Interaction, raw: str) -> str | None:
            return await reschedule_event(
                inter.client, event_id, raw, guild=inter.guild, actor_id=str(inter.user.id))

        current_description = await asyncio.to_thread(load_event_description_sync, event_id)

        async def on_description(inter: discord.Interaction, text: str | None) -> None:
            await asyncio.to_thread(set_event_description_sync, event_id, text)
            await refresh_card_embed(bot, event_id)

    return PodSettingsView(
        on_format=None if drafting else on_format,
        on_pairing=None if drafting or mock else on_pairing,
        current_code=current_code, current_mode=current_mode,
        on_seating_mode=None if drafting else on_seating_mode, current_seating=current_seating,
        on_seating=on_seating, seat_order_provider=seat_order_provider,
        on_seating_table=None if drafting else on_seating_table, on_seated=on_seated,
        on_timer=on_timer if setup_open else None, current_timer=current_timer,
        on_packs=on_packs if setup_open else None, current_packs=current_packs,
        on_cards_per_pack=on_cards_per_pack if setup_open else None,
        current_cards_per_pack=current_cards_per_pack,
        cube_format=pod_format.cube_id_for(current_code) is not None if current_code else False,
        on_picks_per_pack=on_picks_per_pack if setup_open else None,
        current_picks_per_pack=current_picks_per_pack,
        on_max_players=on_max_players if setup_open else None,
        current_max_players=current_max_players,
        kick_targets_provider=kick_targets_provider, on_kick=on_kick,
        link_targets_provider=link_targets_provider, on_link=on_link,
        on_manage_rounds=on_manage_rounds, on_restart=on_restart,
        on_cancel=on_cancel, on_reschedule=on_reschedule, current_start=current_start,
        on_description=on_description, current_description=current_description,
        on_closed_decklist=None if mock else on_closed_decklist,
        current_closed_decklist=current_closed_decklist,
        event_name=event_name, mock=mock,
        notice_channel=notice_channel,
    )


async def seating_message_for_event(bot, event_id: str) -> tuple[discord.File | None, discord.Embed | None]:
    """The Leaderboard-seats message — the seeding table embed with the round-table octagon as a PNG
    inside it. Draftmancer session members are locked at the table; Yes RSVPs only fill the seats
    left under the cut and later ones list below it. Returns (file, embed); (None, None) on no data."""
    yes, maybe = await event_rsvps(event_id)
    locked, locked_keys = await _locked_table_names(event_id)
    rank_override = await asyncio.to_thread(championship_service.rank_override_sync, event_id)
    yes = await asyncio.to_thread(_rank_ordered_names_sync, yes, rank_override)
    pool, overflow = _seating_pool(locked, locked_keys, yes)
    if not pool and not maybe:
        return None, None
    pooled = {n.casefold() for n in pool} | {n.casefold() for n in overflow} | locked_keys
    maybe = [n for n in maybe if n.casefold() not in pooled]
    header = SEEDING_PHASE_LIVE if locked else seeding_phase_projected()
    cut_label = SEEDING_CUT_OVER_CAP if locked else SEEDING_CUT_ALTERNATES
    return await asyncio.to_thread(
        build_seeding_image_message_for_pool, pool, overflow, maybe,
        header=header, cut_label=cut_label, rank_override=rank_override)


async def _locked_table_names(event_id: str) -> tuple[list[str], set[str]]:
    """Display names of everyone in the live Draftmancer session, plus the casefolded keys (display
    and arena names) used to dedup RSVPs against them. Empty when no manager is connected."""
    manager = ACTIVE_POD_MANAGERS.get(event_id)
    if manager is None:
        return [], set()
    classified = await manager.classified_session_users()
    if not classified:
        return [], set()
    locked = [display or arena for arena, display in classified]
    keys = {arena.casefold() for arena, _ in classified} | {n.casefold() for n in locked}
    return locked, keys


def _seating_pool(locked: list[str], locked_keys: set[str], yes: list[str]) -> tuple[list[str], list[str]]:
    """Locked session players take the table first; Yes RSVPs fill the seats left up to
    CHAMPIONSHIP_CUT; everyone after that overflows below the cut."""
    pool = list(locked)
    overflow: list[str] = []
    taken = set(locked_keys)
    for name in yes:
        key = name.casefold()
        if key in taken:
            continue
        taken.add(key)
        if len(pool) < CHAMPIONSHIP_CUT:
            pool.append(name)
        else:
            overflow.append(name)
    return pool, overflow


async def post_seeding_table(bot, event_id: str, channel) -> None:
    file, embed = await seating_message_for_event(bot, event_id)
    if embed is None or channel is None:
        return
    await post_table(bot, channel, file, embed)


_SEEDING_LOCKS: dict[str, asyncio.Lock] = {}


def _seeding_lock(event_id: str) -> asyncio.Lock:
    """Per-event lock serializing all seeding-table mutations, so a re-post's clear+post can't race a
    concurrent refresh into double-posting."""
    lock = _SEEDING_LOCKS.get(event_id)
    if lock is None:
        lock = asyncio.Lock()
        _SEEDING_LOCKS[event_id] = lock
    return lock


async def _resolve_seeding_render(bot, event_id: str):
    """(channel, file, embed, championship) for a leaderboard pod — the live/projected table, or the
    championship waiting placeholder when there's nothing to show. None when the pod isn't
    leaderboard-seated, the thread is gone, or a non-championship pod has nothing to show."""
    seating_mode, thread_id, name = await asyncio.to_thread(load_event_seeding_context_sync, event_id)
    if seating_mode != "leaderboard" or thread_id is None:
        return None
    channel = bot.get_channel(int(thread_id))
    if channel is None:
        try:
            channel = await bot.fetch_channel(int(thread_id))
        except discord.HTTPException:
            return None
    championship = is_championship(name)
    file, embed = await seating_message_for_event(bot, event_id)
    if embed is None:
        if not championship:
            return None
        file, embed = None, _championship_waiting_embed()
    return channel, file, embed, championship


CHAMPIONSHIP_REPOST_INTERVAL = timedelta(hours=1)


async def refresh_seeding_table(bot, event_id: str) -> None:
    """Keep the leaderboard seeding table current as the pool changes. Fires on Draftmancer joins/leaves
    and on RSVP edits; non-leaderboard pods are left alone. Refreshing edits the posted table(s) in place;
    a championship also moves its table to the bottom once the current one has aged past the repost
    interval, so the latest standings resurface without jumping on every single RSVP."""
    async with _seeding_lock(event_id):
        resolved = await _resolve_seeding_render(bot, event_id)
        if resolved is None:
            return
        channel, file, embed, championship = resolved
        if championship and championship_service.invites_pending(event_id):
            return
        existing = await _find_seeding_messages(channel, bot.user)
        if championship and not _within_repost_interval(existing):
            await _repost_seeding_at_bottom(bot, channel, file, embed, pin=False)
            log.info(f"pod-seeding: reposted championship seeding table for event {event_id}")
            return
        if not existing:
            return
        await _edit_seeding_in_place(existing, file, embed)
        log.info(f"pod-seeding: refreshed {len(existing)} seeding table(s) for event {event_id}")


async def repost_seeding_table(bot, event_id: str) -> None:
    """Replace the seeding table when the lobby goes live: clear the scrolled-up pinned anchor (and any
    on-demand copies) and post a fresh table at the bottom, by the spectate link, then pin that one. Fired
    right after the spectate link. Leaderboard-seated pods only; championship falls back to the placeholder."""
    async with _seeding_lock(event_id):
        resolved = await _resolve_seeding_render(bot, event_id)
        if resolved is None:
            return
        channel, file, embed, _ = resolved
        await _repost_seeding_at_bottom(bot, channel, file, embed, pin=True)


async def _repost_seeding_at_bottom(bot, channel, file, embed, *, pin: bool) -> None:
    """Clear every existing table (the pinned anchor included) and post a fresh one at the bottom.
    Lock-free — the caller holds the seeding lock. `pin` anchors the live-lobby table; the gathering-phase
    repost stays unpinned to keep the thread quiet."""
    if isinstance(channel, (discord.Thread, discord.TextChannel)) and bot.user:
        await delete_stale_seeding_messages(channel, bot.user, include_pinned=True)
    if pin:
        await post_table(bot, channel, file, embed)
    elif file is not None:
        await channel.send(embed=embed, file=file)
    else:
        await channel.send(embed=embed)


def _within_repost_interval(existing: list[discord.Message]) -> bool:
    """True while the newest posted table is younger than the championship repost interval, so a refresh
    edits it in place instead of moving it to the bottom. Reads only the already-fetched messages."""
    newest = None
    for message in existing:
        if newest is None or message.created_at > newest:
            newest = message.created_at
    if newest is None:
        return False
    return discord.utils.utcnow() - newest < CHAMPIONSHIP_REPOST_INTERVAL


async def _edit_seeding_in_place(existing: list[discord.Message], file, embed) -> None:
    png = file.fp.read() if file is not None else None
    for message in existing:
        attachments = [discord.File(io.BytesIO(png), "seating.png")] if png is not None else []
        try:
            await message.edit(embed=embed, attachments=attachments)
        except discord.HTTPException:
            log.warning("could not refresh the seeding table in place", exc_info=True)


def _championship_waiting_embed() -> discord.Embed:
    """Placeholder seeding table for a championship with no RSVPs yet. Carries the Yes header so the
    in-place refresher finds and replaces it once players confirm."""
    description = (
        f"{seeding_phase_projected()}\n\n"
        f"{SEEDING_YES_HEADER}0)**\n"
        f"_{MSG_SEEDING_WAITING}_"
    )
    return discord.Embed(description=description, color=discord.Color.green())


async def _find_seeding_messages(channel, bot_user) -> list[discord.Message]:
    """Every bot-posted seeding table in the channel — the pinned anchor plus any on-demand re-post —
    so the refresher keeps each one current rather than letting the pinned anchor drift stale.

    Scans recent history for re-posts and the pins for the durable anchor: the anchor is posted at
    registration and scrolls out of the history window long before the event, so a history-only scan
    would leave it frozen."""
    if bot_user is None or not isinstance(channel, (discord.Thread, discord.TextChannel)):
        return []
    found: dict[int, discord.Message] = {}
    try:
        async for message in channel.history(limit=50):
            if message.author.id == bot_user.id and has_seeding_headers(message):
                found[message.id] = message
    except discord.HTTPException:
        log.warning("could not scan history for existing seeding tables", exc_info=True)
    try:
        for message in await channel.pins():
            if message.author.id == bot_user.id and has_seeding_headers(message):
                found[message.id] = message
    except discord.HTTPException:
        log.warning("could not scan pins for existing seeding tables", exc_info=True)
    return list(found.values())


def build_manual_seating_image(labels: list[str]) -> discord.File | None:
    """The manual seat order rendered verbatim around the octagon (no leaderboard seeding), as a bare
    attachment — the notice's arrow chain carries the order in text. None outside 6-10 seats."""
    seated = [SeededAttendee(slug=None, display_name=lbl, rank=None, score=None, trophies=None) for lbl in labels]
    if len(seated) % 2:
        seated.append(_OPEN_SEAT)
    if not 6 <= len(seated) <= 10:
        return None
    png = render_octagon_png(octagon_text([a.display_name for a in seated]))
    return discord.File(io.BytesIO(png), "seating.png")


async def post_manual_seating_table(bot, channel, labels: list[str], actor: str) -> None:
    if channel is None:
        return
    file = await asyncio.to_thread(build_manual_seating_image, labels)
    await post_table(bot, channel, file, None, content=seating_change_message(actor, labels))


async def post_table(bot, channel, file: discord.File | None, embed: discord.Embed | None,
                     content: str | None = None) -> None:
    if file is not None:
        posted = await channel.send(content=content, embed=embed, file=file)
    else:
        posted = await channel.send(content=content, embed=embed)
    await finalize_seeding_post(channel, bot.user, posted)


async def finalize_seeding_post(channel, bot_user, posted: discord.Message) -> None:
    """Pin the durable seeding table (the first one posted) and purge stale non-pinned re-posts. Shared
    by /pod-seeding, the Seating Table button, and the championship auto-post so all behave the same:
    one pinned anchor, on-demand re-posts overriding each other below it."""
    if bot_user is None or not isinstance(channel, (discord.Thread, discord.TextChannel)):
        return
    await _pin_first_seeding_table(channel, bot_user, posted)
    await delete_stale_seeding_messages(channel, bot_user, keep_message_id=posted.id)


async def _pin_first_seeding_table(channel, bot_user, posted: discord.Message) -> None:
    """Pin `posted` only when it's a seeding table and none is pinned yet — so a later on-demand re-post
    stays unpinned and just overrides the previous one below the anchor."""
    if not has_seeding_headers(posted):
        return
    try:
        pins = await channel.pins()
    except discord.HTTPException:
        return
    for message in pins:
        if message.id != posted.id and message.author.id == bot_user.id and has_seeding_headers(message):
            return
    try:
        await posted.pin()
    except discord.HTTPException:
        log.warning("could not pin the seeding table", exc_info=True)


def _pick_takeover_target(manager, invoker_display_name: str):
    """Prefer the invoker by display_name match; else any non-bot user. Returns (userID, userName) or None."""
    for user in manager.session_users:
        if user.get("userName") == "DisChordBot":
            continue
        if user.get("userName") == invoker_display_name:
            return user.get("userID"), user.get("userName")
    for user in manager.session_users:
        if user.get("userName") != "DisChordBot":
            return user.get("userID"), user.get("userName")
    return None


def _find_manager_for_thread(interaction: discord.Interaction):
    """Pick the manager whose thread matches the invocation, else fall back to any active one."""
    channel_id = str(interaction.channel.id) if interaction.channel else None
    for manager in ACTIVE_POD_MANAGERS.values():
        if str(manager.thread_id) == channel_id:
            return manager
    return next(iter(ACTIVE_POD_MANAGERS.values()), None)


def _live_lobby_names() -> list[str]:
    """Draftmancer usernames currently seated across all active, not-yet-complete real pod lobbies."""
    names: list[str] = []
    for manager in ACTIVE_POD_MANAGERS.values():
        if manager.draft_complete or manager.kind == "mock":
            continue
        names.extend(n for n in manager.non_bot_session_names() if n)
    return names


async def setup(bot: commands.Bot) -> None:
    set_seeding_refresh_hook(refresh_seeding_table)
    set_seeding_repost_hook(repost_seeding_table)
    set_card_refresh_hook(refresh_card_embed)
    set_card_phase_hook(refresh_card_embed)
    set_pod_card_hook(post_pod_card)
    await bot.add_cog(PodDraft(bot))
