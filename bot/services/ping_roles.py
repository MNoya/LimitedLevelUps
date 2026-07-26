"""Self-assignable ping roles — the single registry every guild reconciles against.

`PING_ROLES` is the source of truth: name, color, the toggle-menu blurb, and an optional slot the
role is tied to (for showing its local time and auto-granting on RSVP). `reconcile_ping_roles`
makes every guild match this list — creating missing roles, recoloring drift, and renaming in place
when a name moves to `aliases`. To rename a role, set the new `name` and list the old name in
`aliases`; the reconcile finds the existing role by the alias and renames it instead of orphaning it.

`MANAGED_ROLES` are bot-kept roles the same reconcile keeps present and correctly colored, but which
are never offered in the self-serve menu nor pushed below the Pod Drafters umbrella — their color is
meant to show on the wearer's name (the Set Champion award).
"""
from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import discord
from sqlalchemy import select

from bot import audit, emojis
from bot.commands.messages import (
    MSG_ARENA_ALREADY_LINKED_NOTE,
    MSG_ARENA_BAD_FORMAT,
    MSG_ARENA_COLLISION,
    MSG_ARENA_HANDLE_LINE,
    MSG_ARENA_LINK_CTA,
    MSG_ARENA_LINKED,
    MSG_FORMAT_PREFERENCE_BUTTON,
    MSG_JOIN_LINE,
    MSG_POD_ROLE_GRANTED,
    MSG_POD_WELCOME,
)
from bot.commands.pod_guide import render_pod_guide_embed_body
from bot.database import SessionLocal
from bot.discord_helpers import extract_avatar_hash, is_pod_coordination_channel, post_welcome, send_welcome
from bot.models import Player
from bot.services import pod_format_interest as fi
from bot.services.pod_active_lobby import active_lobby_link_for
from bot.services.pod_drafts import (
    attach_arena_alias,
    dm_draft_link_enabled,
    draftmancer_url_for,
    player_arena_handle,
)
from bot.services.pod_roles import find_role
from bot.services.pod_schedule import (
    EARLY_POD_ROLE_NAME,
    LATE_POD_ROLE_NAME,
    POD_DRAFTERS_ROLE_NAME,
    POD_QUEUE_ROLE_NAME,
    SATURDAY,
    THURSDAY,
    WEDNESDAY,
    WEEKEND_EARLY_POD_ROLE_NAME,
    WEEKEND_LATE_POD_ROLE_NAME,
    next_slot_datetime,
    slot_by_weekday,
)
from bot.services.pod_signals import slot_event_time, slot_role_name_for_event_time
from bot.services.token_link_flow import start_link_17lands_flow


log = logging.getLogger(__name__)

QUEUE_GRANT_PING = "when it opens or needs more players"


@dataclass(frozen=True)
class PingRole:
    name: str
    emoji: str
    blurb: str
    color: str | None = None
    aliases: tuple[str, ...] = ()
    slot_weekday: int | None = None
    auto_grant: bool = False
    grant_when: str = "at this time of day"
    weekend_bucket_keys: tuple[str, ...] = ()


EARLY_POD_COLOR = "#5CA8E0"
LATE_POD_COLOR = "#9B8AE6"

PING_ROLES: tuple[PingRole, ...] = (
    PingRole(POD_DRAFTERS_ROLE_NAME, "llu", "Server-Wide Pod Announcements", color="#C0C0C0"),
    PingRole(
        EARLY_POD_ROLE_NAME, "💫", "Weekdays", color=EARLY_POD_COLOR,
        aliases=("Early Pods", "Early Pod Drafters", "Euro Pod Drafters"), slot_weekday=THURSDAY, auto_grant=True,
    ),
    PingRole(
        LATE_POD_ROLE_NAME, "☄️", "Weekdays", color=LATE_POD_COLOR,
        aliases=("Late Pods", "Late Pod Drafters"), slot_weekday=WEDNESDAY, auto_grant=True,
    ),
    PingRole(
        WEEKEND_EARLY_POD_ROLE_NAME, "🌅", "", color=EARLY_POD_COLOR,
        aliases=("Weekend Early Pods",), slot_weekday=SATURDAY, auto_grant=True,
        grant_when="on weekends", weekend_bucket_keys=("AFTERNOON",),
    ),
    PingRole(
        WEEKEND_LATE_POD_ROLE_NAME, "🎆", "", color=LATE_POD_COLOR,
        aliases=("Weekend Late Pods",), slot_weekday=SATURDAY, auto_grant=True,
        grant_when="on weekends", weekend_bucket_keys=("EVENING",),
    ),
    PingRole(POD_QUEUE_ROLE_NAME, "⚡", "Daily Draft Sign-Ups", color="#FFAC33"),
    PingRole(fi.LATEST_SET_ROLE_NAME, "🆕", "All Pods drafting the Latest Set", color="#e8e8e8"),
    PingRole(fi.FLASHBACK_ROLE_NAME, "flashback", "All Pods drafting any Past Sets", color="#B0C4DE"),
    PingRole(fi.CUBE_ROLE_NAME, "cube", "All Pods drafting any Cube", color="#B0C4DE"),
)


@dataclass(frozen=True)
class ManagedRole:
    name: str
    color: str


SET_CHAMPION_ROLE_NAME = "Set Champion"
ORGANIZER_ROLE_NAME = "Organizer"

MANAGED_ROLES: tuple[ManagedRole, ...] = (
    ManagedRole(SET_CHAMPION_ROLE_NAME, "#82CBFF"),
    ManagedRole(ORGANIZER_ROLE_NAME, "#4CD4A9"),
)


def organizer_mention(guild: discord.Guild | None) -> str:
    """Mention pill for the pod organizers, or plain text when the guild has no such role yet."""
    role = find_role(guild, ORGANIZER_ROLE_NAME)
    return role.mention if role is not None else f"@{ORGANIZER_ROLE_NAME}"


def spec_named(name: str) -> PingRole | None:
    for spec in PING_ROLES:
        if spec.name == name:
            return spec
    return None


def button_custom_id(spec: PingRole) -> str:
    return f"role-toggle-{spec.name.lower().replace(' ', '-')}"


def blurb_with_time(spec: PingRole) -> str:
    """A slot role pairs its blurb with its recurring local times: one for a weekday slot, and for a
    weekend role only the buckets it covers (`weekend_bucket_keys`). Roles with no slot show their
    blurb alone."""
    if spec.slot_weekday is None:
        return spec.blurb
    slot = slot_by_weekday(spec.slot_weekday)
    if slot is None:
        return spec.blurb
    slot_date = next_slot_datetime(slot).date()
    if spec.weekend_bucket_keys:
        stamps = [slot_event_time(slot_date, key) for key in spec.weekend_bucket_keys]
    else:
        stamps = [next_slot_datetime(slot)]
    times = ", ".join(f"<t:{int(stamp.timestamp())}:t>" for stamp in stamps)
    return f"{spec.blurb} at {times}" if spec.blurb else f"at {times}"


def display_emoji(spec: PingRole) -> str | None:
    """The Latest Set role wears the active set's symbol, so it rotates with the board."""
    if spec.name == fi.LATEST_SET_ROLE_NAME:
        return str(fi.latest_emoji())
    return emojis.resolve(spec.emoji)


def slot_grant_ping(spec: PingRole) -> str:
    return f"for drafts {spec.grant_when}"


def pod_role_grant_text(
    role_mention: str, ping: str, *, emoji: str = "", member_mention: str | None = None,
) -> str:
    """One role-grant line for every surface: `member_mention` set addresses a member by mention for a
    public thread post, unset addresses the clicker for an ephemeral reply."""
    if member_mention:
        subject = f"{emoji} {member_mention} you're".strip()
    else:
        subject = f"{emoji} You're".strip()
    return MSG_POD_ROLE_GRANTED.format(subject=subject, role=role_mention, ping=ping)


def build_grant_embed(
    user_mention: str, role: discord.Role, spec: PingRole, *, ping: str | None = None,
) -> discord.Embed:
    """The public embed announcing a fresh auto-grant in an event thread, used by the sesh listener.

    A role mention inside an embed never pings (only message content does), so the role tag is safe;
    it renders as the colored role pill from the viewer's role cache.
    """
    message = pod_role_grant_text(
        role.mention, ping or slot_grant_ping(spec),
        emoji=display_emoji(spec) or "", member_mention=user_mention,
    )
    return discord.Embed(
        description=message,
        color=role.color if role.color.value else discord.Color.blurple(),
    )


def build_welcome_view(
    guild: discord.Guild, user_mention: str, *, show_link_17lands: bool = False,
) -> discord.ui.LayoutView:
    """First-pod welcome as a Components V2 container: a green accent card whose text block behaves as
    message content, so the newcomer mention pings where an embed mention would stay silent. This one is
    public, so it welcomes and points at the buttons and nothing else — which slot role the click granted
    is between the bot and the clicker, and rides on their ephemeral confirmation instead."""
    umbrella = discord.utils.get(guild.roles, name=POD_DRAFTERS_ROLE_NAME)
    pod_drafters = umbrella.mention if umbrella is not None else POD_DRAFTERS_ROLE_NAME
    message = MSG_POD_WELCOME.format(user=user_mention, pod_drafters=pod_drafters).rstrip()
    return _PodButtonCard(message, show_link_17lands_button=show_link_17lands)


def build_grant_view(
    role: discord.Role, spec: PingRole, *, ping: str | None = None, arena_name: str | None = None,
    card_lead: str | None = None, show_link_17lands: bool = False,
) -> discord.ui.LayoutView:
    """The ephemeral card a returning drafter gets on a fresh slot grant: the grant line plus the same
    Pod Guide and Notifications buttons as the welcome. No self-mention — the card is ephemeral, so the
    reader is the subject. When linked, it shows their Arena handle and drops the Link Arena button; when
    unlinked it offers Link Arena so they can link before joining the lobby. `card_lead` folds the caller's
    join confirmation into the card, so a grant and an RSVP acknowledgement arrive as one message. Accented
    with the granted role's color."""
    grant_line = pod_role_grant_text(
        role.mention, ping or slot_grant_ping(spec), emoji=display_emoji(spec) or "",
    )
    if card_lead:
        grant_line = f"{card_lead}\n{grant_line}"
    text = _card_body(grant_line, arena_name=arena_name)
    accent = role.color if role.color.value else discord.Color.blurple()
    return _PodButtonCard(
        text, accent=accent, show_link_button=arena_name is None,
        show_link_17lands_button=show_link_17lands,
    )


def _card_body(lead: str, *, arena_name: str | None) -> str:
    """The card text below its lead, shared by the grant card and the RSVP confirmation card: the linked
    reader sees their Arena handle, the unlinked reader the link prompt. No format preference line — the
    saved preference decides nothing about a signup, so quoting it back on a join reads as a promise."""
    if arena_name is None:
        return f"{lead}\n{MSG_ARENA_LINK_CTA}"
    handle_line = MSG_ARENA_HANDLE_LINE.format(emoji=emojis.get("mtga"), arena_name=arena_name)
    return f"{lead}\n{handle_line}"


def persistent_pod_card_view() -> discord.ui.LayoutView:
    """A component-only instance for `bot.add_view` so the welcome and grant-card buttons keep
    dispatching after a restart; the placeholder text is never shown — registration routes on the
    button custom_ids, which both cards share."""
    return _PodButtonCard("welcome", show_format_button=True, show_link_17lands_button=True)


class _PodButtonCard(discord.ui.LayoutView):
    """The shared Components V2 card behind both the welcome and the returning grant notice: a text
    block over the Link Arena / Pod Guide / Notifications / Format Preference button row. The accent
    defaults to green; the grant card overrides it with the granted role's color."""

    def __init__(
        self, text: str, *, accent: discord.Color | None = None, show_link_button: bool = True,
        show_format_button: bool = False, show_link_17lands_button: bool = False,
    ) -> None:
        super().__init__(timeout=None)
        container = discord.ui.Container(accent_colour=accent or discord.Color.green())
        container.add_item(discord.ui.TextDisplay(text))
        row = discord.ui.ActionRow()
        if show_link_button:
            row.add_item(_LinkArenaButton())
        if show_link_17lands_button:
            row.add_item(_Link17LandsButton())
        row.add_item(_PodGuideButton())
        row.add_item(_ManageRolesButton())
        if show_format_button:
            row.add_item(_FormatPreferenceButton())
        container.add_item(row)
        self.add_item(container)


LINK_ARENA_BUTTON_ID = "pod_welcome_link_arena"
LINK_17LANDS_BUTTON_ID = "pod_welcome_link_17lands"
POD_GUIDE_BUTTON_ID = "pod_welcome_guide"
MANAGE_ROLES_BUTTON_ID = "pod_welcome_roles"
FORMAT_PREFERENCE_BUTTON_ID = "pod_welcome_format"
MSG_PICKER_UNAVAILABLE = "The preference picker is not available right now."
_ARENA_HANDLE_RE = re.compile(r"^.+#\d+$")

FormatPreferenceOpener = Callable[[discord.Interaction], Awaitable[None]]

_format_preference_opener: FormatPreferenceOpener | None = None


def register_format_preference_opener(handler: FormatPreferenceOpener) -> None:
    """Wire the preference-picker launch. The daily-poll task registers it at import so this module
    stays free of a task import and the button works on any card."""
    global _format_preference_opener
    _format_preference_opener = handler


class _FormatPreferenceButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(
            label=MSG_FORMAT_PREFERENCE_BUTTON, style=discord.ButtonStyle.primary,
            emoji=fi.FLEXIBLE_EMOJI, custom_id=FORMAT_PREFERENCE_BUTTON_ID,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if _format_preference_opener is None:
            await interaction.response.send_message(MSG_PICKER_UNAVAILABLE, ephemeral=True)
            return
        await _format_preference_opener(interaction)


class _LinkArenaButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(
            label="Link Arena",
            style=discord.ButtonStyle.primary,
            emoji=emojis.get("mtga"),
            custom_id=LINK_ARENA_BUTTON_ID,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        existing = await _linked_arena_handle(str(interaction.user.id))
        await interaction.response.send_modal(_LinkArenaModal(existing=existing))


class _Link17LandsButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(
            label="Link 17Lands",
            style=discord.ButtonStyle.primary,
            emoji=emojis.get_emoji("17lands"),
            custom_id=LINK_17LANDS_BUTTON_ID,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        audit.event("rsvp_link_17lands_clicked", user_id=str(interaction.user.id))
        await start_link_17lands_flow(interaction.client, interaction)


class _PodGuideButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(
            label="Pod Guide", style=discord.ButtonStyle.success, emoji="📖", custom_id=POD_GUIDE_BUTTON_ID,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        role = discord.utils.get(interaction.guild.roles, name=POD_DRAFTERS_ROLE_NAME) if interaction.guild else None
        mention = role.mention if role is not None else f"@{POD_DRAFTERS_ROLE_NAME}"
        await interaction.response.send_message(
            embed=discord.Embed(description=render_pod_guide_embed_body(mention), color=discord.Color.green()),
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )


class _ManageRolesButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(
            label="Notifications", style=discord.ButtonStyle.secondary, emoji="🔔", custom_id=MANAGE_ROLES_BUTTON_ID,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        from bot.commands.roles import RolesView

        held = {role.name for role in getattr(interaction.user, "roles", [])}
        dm_opt_in = await asyncio.to_thread(_dm_opt_in_for, str(interaction.user.id))
        await interaction.response.send_message(
            view=RolesView(held, interaction.guild, in_guild=interaction.guild is not None, dm_opt_in=dm_opt_in),
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )


def _dm_opt_in_for(discord_id: str) -> bool:
    with SessionLocal() as session:
        return dm_draft_link_enabled(session, discord_id)


def _has_seventeenlands_token(discord_id: str) -> bool:
    with SessionLocal() as session:
        token = session.execute(
            select(Player.seventeenlands_token).where(Player.discord_id == discord_id)
        ).scalar_one_or_none()
    return bool(token)


async def submit_arena_link(interaction: discord.Interaction, arena_name: str) -> str | None:
    """Validate and store an Arena handle from a modal, replying only on rejection (bad format or
    collision). Returns the linked handle on success without a response, so the caller owns the success
    reply — the in-channel announcement, or a DM's in-place re-render. Shared so validation can't drift."""
    if not _ARENA_HANDLE_RE.match(arena_name):
        await interaction.response.send_message(MSG_ARENA_BAD_FORMAT, ephemeral=True)
        return None
    with SessionLocal() as session:
        player_id, collision_id = attach_arena_alias(
            session,
            discord_id=str(interaction.user.id),
            discord_username=interaction.user.name,
            display_name=interaction.user.display_name,
            avatar_hash=extract_avatar_hash(interaction.user),
            arena_name=arena_name,
            overwrite=True,
        )
        if collision_id is not None:
            await interaction.response.send_message(
                MSG_ARENA_COLLISION.format(arena_name=arena_name), ephemeral=True,
            )
            return None
        session.commit()
    log.info(f"pod-welcome-link: {interaction.user} linked {arena_name} (player_id={player_id})")
    return arena_name


class _LinkArenaModal(discord.ui.Modal, title="Link Arena Handle"):
    handle = discord.ui.TextInput(
        label="MTG Arena Handle",
        placeholder="ArenaID#12345",
        min_length=3,
        max_length=40,
        required=True,
    )

    def __init__(self, after_link=None, existing: str | None = None) -> None:
        super().__init__()
        self.after_link = after_link
        if existing:
            self.remove_item(self.handle)
            note = MSG_ARENA_ALREADY_LINKED_NOTE.format(emoji=emojis.get("mtga"), arena_name=existing)
            self.add_item(discord.ui.TextDisplay(note))
            self.add_item(self.handle)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        arena_name = await submit_arena_link(interaction, str(self.handle.value).strip())
        if arena_name is None:
            return
        if self.after_link is not None:
            await self.after_link(interaction, arena_name)
            return
        linked = MSG_ARENA_LINKED.format(
            emoji=emojis.get("mtga"), mention=interaction.user.mention, arena_name=arena_name,
        )
        no_pings = discord.AllowedMentions(users=False, everyone=False, roles=False)
        if is_pod_coordination_channel(interaction.channel):
            await interaction.response.send_message(linked, ephemeral=True, allowed_mentions=no_pings)
        else:
            await interaction.response.defer()
            await interaction.channel.send(linked, allowed_mentions=no_pings)
        await _handoff_active_lobby_link(interaction)


def format_join_line(session_id: str, name: str, *, arena: bool = True) -> str:
    """The one-line join call to action shared by the lobby DM, the in-thread Join Draft reply, and the
    post-link handoff: the personalized Draftmancer link plus the identity, mtga emoji first when the app
    emoji resolves. `arena` is False for a mock draft, where the name is a Discord one."""
    emoji = emojis.get("mtga") if arena else ""
    identity = f"{emoji} **{name}**" if emoji else f"**{name}**"
    return MSG_JOIN_LINE.format(url=draftmancer_url_for(session_id, name), identity=identity)


async def _handoff_active_lobby_link(interaction: discord.Interaction) -> None:
    """Right after a link, hand back the personalized session link for a live lobby the player is in, so
    linking from the Join Draft nudge (or anywhere during a lobby) needs no second Join Draft click."""
    lobby = active_lobby_link_for(str(interaction.user.id))
    if lobby is None:
        return
    session_id, arena_name = lobby
    await interaction.followup.send(format_join_line(session_id, arena_name), ephemeral=True)


def build_link_arena_button() -> discord.ui.Button:
    """The registered Link Arena button, for embedding in the Join Draft nudge and the unlinked lobby
    DM. Shares the registered custom_id so clicks dispatch after a restart."""
    return _LinkArenaButton()


def build_link_arena_view() -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(build_link_arena_button())
    return view


def build_link_arena_modal(after_link=None) -> discord.ui.Modal:
    """The Link Arena modal with an optional `after_link(interaction, arena_name)` step run on a
    successful link in place of the default in-channel announcement — the lobby DM uses it to re-render
    itself with the personalized link."""
    return _LinkArenaModal(after_link=after_link)


async def _linked_arena_handle(discord_id: str) -> str | None:
    with SessionLocal() as session:
        return player_arena_handle(session, discord_id)


_welcomed_member_ids: set[int] = set()


def _first_welcome_for(member_id: int) -> bool:
    """True the first time a member would be welcomed, False after — so re-gaining Pod Drafters (a
    Customize re-toggle, or a drop-and-return) never re-posts the public welcome. In-memory, so it
    re-arms on restart; a member only picks the role once in normal use, so the reset is harmless."""
    if member_id in _welcomed_member_ids:
        return False
    _welcomed_member_ids.add(member_id)
    return True


def forget_welcome(member_id: int) -> None:
    """Drop a member's welcomed mark so `!test reset` can replay the first-pod welcome for the tester."""
    _welcomed_member_ids.discard(member_id)


NOTICE_WELCOME = "welcome"
NOTICE_GRANT = "grant"


async def announce_pod_grant(
    interaction: discord.Interaction, *, first_pod: bool, granted_role: discord.Role | None,
    spec: PingRole | None, ping: str | None, card_lead: str | None = None,
) -> str | None:
    """The post-join notice every signal surface shares: a first-ever drafter with no linked Arena handle
    gets the public welcome in pod-draft-chat; anyone already linked is treated as a returning drafter,
    since reaching `/link-arena` means they already found pods — they get only the ephemeral grant card if
    they freshly picked up a slot role, else nothing. `granted_role` gates the returning case on an actual
    fresh grant, so a re-click never re-announces. The public welcome names no slot role: the caller's own
    ephemeral confirmation is where a clicker learns which role the click granted them.
    `card_lead` is folded into the grant card so the caller's join confirmation and the grant arrive as
    one message. Returns `NOTICE_WELCOME` or `NOTICE_GRANT` for the notice posted, None for none, so the
    caller can decide whether its own confirmation still needs to be sent."""
    user = interaction.user
    arena_name = await _linked_arena_handle(str(user.id))
    has_token = await asyncio.to_thread(_has_seventeenlands_token, str(user.id))
    wants_welcome = first_pod and arena_name is None
    if wants_welcome and _first_welcome_for(user.id):
        welcome = build_welcome_view(interaction.guild, user.mention, show_link_17lands=not has_token)
        await post_welcome(interaction, welcome)
        log.info(f"posted first-pod welcome for {user}")
        return NOTICE_WELCOME
    if granted_role is not None:
        grant = build_grant_view(
            granted_role, spec, ping=ping, arena_name=arena_name,
            card_lead=card_lead, show_link_17lands=not has_token,
        )
        await interaction.followup.send(
            view=grant, ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
        )
        log.info(f"posted returning grant card for {user} (linked={arena_name is not None})")
        return NOTICE_GRANT
    log.info(
        f"no pod-grant notice for {user}: first_pod={first_pod} linked={arena_name is not None} "
        f"granted_role={granted_role.name if granted_role else None}"
    )
    return None


async def send_join_confirmation_card(
    interaction: discord.Interaction, *, lead: str, accent: discord.Color,
) -> None:
    """A join acknowledgement (RSVP Yes/Maybe, launcher slot add, picker Confirm) as a full pod card:
    the confirmation lead over the same Link Arena / Pod Guide / Notifications / Format Preference row
    the grant card carries, so every join click offers the self-service controls, not only the click
    that granted a role."""
    user_id = str(interaction.user.id)
    arena_name = await _linked_arena_handle(user_id)
    has_token = await asyncio.to_thread(_has_seventeenlands_token, user_id)
    card = _PodButtonCard(
        _card_body(lead, arena_name=arena_name),
        accent=accent, show_link_button=arena_name is None,
        show_link_17lands_button=not has_token,
    )
    await interaction.followup.send(view=card, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())


async def announce_onboarding_welcome(client: discord.Client, member: discord.Member) -> None:
    """The welcome for a drafter who picked up Pod Drafters through Discord's onboarding question,
    which bypasses every interaction path. Posted publicly in pod-draft-chat with no slot role to fold
    in, since onboarding grants only the umbrella. Anyone already linked is skipped — they found pods
    on their own, and with no interaction there's no ephemeral to fall back to."""
    if await _linked_arena_handle(str(member.id)) is not None:
        log.info(f"onboarding welcome skipped for {member}: already linked")
        return
    if not _first_welcome_for(member.id):
        log.info(f"onboarding welcome skipped for {member}: already welcomed")
        return
    has_token = await asyncio.to_thread(_has_seventeenlands_token, str(member.id))
    welcome = build_welcome_view(member.guild, member.mention, show_link_17lands=not has_token)
    posted = await send_welcome(client, member, welcome)
    log.info(f"onboarding welcome {'posted' if posted else 'failed to post'} for {member}")


def auto_grant_spec_for_event(event_time) -> PingRole | None:
    """The ping role auto-granted to RSVPs of the pod at this time, or None. Resolves off the poll
    buckets (weekend + time-of-day), so a launcher pod and a weekly-schedule pod at the same slot map
    to the same role regardless of weekday."""
    role_name = slot_role_name_for_event_time(event_time)
    if role_name is None:
        return None
    spec = spec_named(role_name)
    return spec if spec is not None and spec.auto_grant else None


async def reconcile_ping_roles(bot: discord.Client) -> None:
    """Make every guild's roles match PING_ROLES — create, rename-via-alias, and recolor as needed."""
    for guild in bot.guilds:
        me = guild.me
        if me is None or not me.guild_permissions.manage_roles:
            log.info(f"ping-role reconcile skipped in {guild.name}: missing Manage Roles")
            continue
        for spec in PING_ROLES:
            await _ensure_role(guild, spec)
        await _keep_umbrella_on_top(guild)
        for managed in MANAGED_ROLES:
            await _ensure_managed_role(guild, managed)


async def strip_pod_roles(member: discord.Member) -> int:
    """Remove the auto-granted pod ping roles — the slot roles plus the Pod Drafters umbrella — from
    one member. Backs `!test reset` so the tester's own re-test starts with no leftover grants; the
    opt-in-only Pod Queue role is left alone. Returns the number of roles removed."""
    target_names = {POD_DRAFTERS_ROLE_NAME} | {spec.name for spec in PING_ROLES if spec.auto_grant}
    roles = [role for role in member.roles if role.name in target_names]
    if not roles:
        return 0
    try:
        await member.remove_roles(*roles, reason="test reset")
    except discord.HTTPException:
        log.warning(f"could not strip pod roles from {member.id} in {member.guild.name}", exc_info=True)
        return 0
    return len(roles)


async def _keep_umbrella_on_top(guild: discord.Guild) -> None:
    """Members wear the gray Pod Drafters umbrella for their name color; every other ping role must
    sit below it in the hierarchy so its color stays a cosmetic mention-pill color."""
    umbrella = discord.utils.get(guild.roles, name=POD_DRAFTERS_ROLE_NAME)
    if umbrella is None:
        return
    for spec in PING_ROLES:
        if spec.name == POD_DRAFTERS_ROLE_NAME:
            continue
        role = discord.utils.get(guild.roles, name=spec.name)
        if role is None or role.position < umbrella.position:
            continue
        try:
            await role.edit(position=umbrella.position, reason="ping-role reorder below umbrella")
            log.info(f"moved {spec.name!r} below {POD_DRAFTERS_ROLE_NAME!r} in {guild.name}")
        except discord.HTTPException:
            log.warning(f"could not reorder {spec.name!r} in {guild.name}", exc_info=True)


async def _ensure_role(guild: discord.Guild, spec: PingRole) -> None:
    role = discord.utils.get(guild.roles, name=spec.name) or await _adopt_alias(guild, spec)
    if role is None:
        await _create_role(guild, spec)
        return
    for alias in spec.aliases:
        if discord.utils.get(guild.roles, name=alias) is not None:
            log.warning(f"both {spec.name!r} and stale alias {alias!r} exist in {guild.name}; delete the alias role")
    if spec.color is not None:
        wanted = discord.Colour.from_str(spec.color)
        if role.colour != wanted:
            try:
                await role.edit(colour=wanted, reason="ping-role recolor")
                log.info(f"recolored {spec.name!r} in {guild.name}")
            except discord.HTTPException:
                log.warning(f"could not recolor {spec.name!r} in {guild.name}", exc_info=True)


async def _ensure_managed_role(guild: discord.Guild, spec: ManagedRole) -> None:
    wanted = discord.Colour.from_str(spec.color)
    role = discord.utils.get(guild.roles, name=spec.name)
    if role is None:
        try:
            await guild.create_role(name=spec.name, colour=wanted, reason="managed-role create")
            log.info(f"created {spec.name!r} in {guild.name}")
        except discord.HTTPException:
            log.warning(f"could not create {spec.name!r} in {guild.name}", exc_info=True)
        return
    if role.colour != wanted:
        try:
            await role.edit(colour=wanted, reason="managed-role recolor")
            log.info(f"recolored {spec.name!r} in {guild.name}")
        except discord.HTTPException:
            log.warning(f"could not recolor {spec.name!r} in {guild.name}", exc_info=True)


async def _adopt_alias(guild: discord.Guild, spec: PingRole) -> discord.Role | None:
    for alias in spec.aliases:
        existing = discord.utils.get(guild.roles, name=alias)
        if existing is None:
            continue
        try:
            await existing.edit(name=spec.name, reason="ping-role rename")
            log.info(f"renamed {alias!r} -> {spec.name!r} in {guild.name}")
        except discord.HTTPException:
            log.warning(f"could not rename {alias!r} in {guild.name}", exc_info=True)
        return existing
    return None


async def _create_role(guild: discord.Guild, spec: PingRole) -> None:
    kwargs = {"name": spec.name, "reason": "ping-role create"}
    if spec.color is not None:
        kwargs["colour"] = discord.Colour.from_str(spec.color)
    try:
        await guild.create_role(**kwargs)
        log.info(f"created {spec.name!r} in {guild.name}")
    except discord.HTTPException:
        log.warning(f"could not create {spec.name!r} in {guild.name}", exc_info=True)
