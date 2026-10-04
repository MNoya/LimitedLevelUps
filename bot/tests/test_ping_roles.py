import asyncio
from datetime import datetime
from types import SimpleNamespace

import discord
import pytest

from bot.commands.roles import Roles
from bot.services.ping_roles import (
    EARLY_POD_ROLE_NAME,
    MANAGED_ROLES,
    REMINDER_COLOR,
    REMINDER_ROLE_NAME,
    MOCK_DRAFT_ROLE_NAME,
    PING_ROLES,
    LATE_POD_ROLE_NAME,
    _ensure_managed_role,
    _first_welcome_for,
    auto_grant_spec_for_event,
    blurb_with_time,
    button_custom_id,
    is_set_champion_title,
    forget_welcome,
    grant_mock_draft_role,
    grant_pod_roles,
)
from bot.services.pod_roles import consume_bot_grant, grant_role, revoke_roles
from bot.services.pod_schedule import POD_DRAFTERS_ROLE_NAME, SCHEDULE_TZ


@pytest.mark.parametrize("event_time, expected", [
    (datetime(2026, 6, 11, 14, 0, tzinfo=SCHEDULE_TZ), EARLY_POD_ROLE_NAME),
    (datetime(2026, 6, 10, 21, 0, tzinfo=SCHEDULE_TZ), LATE_POD_ROLE_NAME),
    (datetime(2026, 6, 13, 14, 0, tzinfo=SCHEDULE_TZ), EARLY_POD_ROLE_NAME),
    (datetime(2026, 6, 13, 21, 0, tzinfo=SCHEDULE_TZ), LATE_POD_ROLE_NAME),
    (datetime(2026, 6, 9, 11, 0, tzinfo=SCHEDULE_TZ), None),
    (datetime(2026, 6, 13, 20, 0, tzinfo=SCHEDULE_TZ), None),
])
def test_auto_grant_maps_a_slot_time_to_its_role(event_time, expected):
    spec = auto_grant_spec_for_event(event_time)

    assert (spec.name if spec else None) == expected


def test_button_custom_id_is_a_stable_slug():
    assert button_custom_id(_spec_named(POD_DRAFTERS_ROLE_NAME)) == "role-toggle-pod-drafters"


def test_blurb_with_time_lists_every_hour_a_slot_runs_at():
    early = blurb_with_time(_spec_named(EARLY_POD_ROLE_NAME))
    late = blurb_with_time(_spec_named(LATE_POD_ROLE_NAME))

    assert early.count("<t:") == 1
    assert late.count("<t:") == 1


def test_first_welcome_fires_once_until_forgotten():
    member_id = 90909

    assert _first_welcome_for(member_id) is True
    assert _first_welcome_for(member_id) is False
    forget_welcome(member_id)
    assert _first_welcome_for(member_id) is True


def test_a_bot_grant_is_marked_once_per_role():
    member = _FakeMember(4242)
    slot_role = SimpleNamespace(name=EARLY_POD_ROLE_NAME)

    asyncio.run(grant_role(member, slot_role))

    assert consume_bot_grant(4242, POD_DRAFTERS_ROLE_NAME) is False
    assert consume_bot_grant(4242, EARLY_POD_ROLE_NAME) is True
    assert consume_bot_grant(4242, EARLY_POD_ROLE_NAME) is False


@pytest.mark.parametrize("member_id, gained, granted_by_bot, expected_roles, expect_welcome", [
    (4545, EARLY_POD_ROLE_NAME, False, [EARLY_POD_ROLE_NAME, POD_DRAFTERS_ROLE_NAME], True),
    (4546, EARLY_POD_ROLE_NAME, True, [EARLY_POD_ROLE_NAME], False),
    (4547, POD_DRAFTERS_ROLE_NAME, False, [POD_DRAFTERS_ROLE_NAME], True),
    (4548, POD_DRAFTERS_ROLE_NAME, True, [POD_DRAFTERS_ROLE_NAME], False),
])
def test_role_listener_welcomes_only_onboarding_gains(
    monkeypatch, stored_choices, member_id, gained, granted_by_bot, expected_roles, expect_welcome,
):
    welcomed = []

    async def record_welcome(bot, member):
        welcomed.append(member.id)

    monkeypatch.setattr("bot.commands.roles.announce_onboarding_welcome", record_welcome)
    before = _FakeMember(member_id)
    after = _FakeMember(member_id)
    role = SimpleNamespace(name=gained)
    if granted_by_bot:
        asyncio.run(grant_role(after, role))
    else:
        after.roles.append(role)

    asyncio.run(Roles(bot=None).on_member_update(before, after))

    assert [held.name for held in after.roles] == expected_roles
    assert bool(welcomed) is expect_welcome


@pytest.mark.parametrize("member_id, held_before, held_after, revoked_by_bot, expected", [
    (4646, [POD_DRAFTERS_ROLE_NAME, LATE_POD_ROLE_NAME], [POD_DRAFTERS_ROLE_NAME], False, [(["late"], True)]),
    (4647, [POD_DRAFTERS_ROLE_NAME, LATE_POD_ROLE_NAME], [POD_DRAFTERS_ROLE_NAME], True, []),
    (4648, [POD_DRAFTERS_ROLE_NAME], [POD_DRAFTERS_ROLE_NAME, LATE_POD_ROLE_NAME], False, [(["late"], False)]),
    (4649, [POD_DRAFTERS_ROLE_NAME, LATE_POD_ROLE_NAME], [LATE_POD_ROLE_NAME], False, [(["late"], True)]),
])
def test_role_listener_stores_a_players_slot_role_choices(
    stored_choices, member_id, held_before, held_after, revoked_by_bot, expected,
):
    before = _FakeMember(member_id)
    before.roles = [SimpleNamespace(name=name) for name in held_before]
    after = _FakeMember(member_id)
    after.roles = [SimpleNamespace(name=name) for name in held_after]
    if revoked_by_bot:
        holder = _FakeMember(member_id)
        holder.roles = list(before.roles)
        asyncio.run(revoke_roles(holder, [holder.roles[-1]], reason="test"))

    asyncio.run(Roles(bot=None).on_member_update(before, after))

    assert stored_choices == expected


@pytest.fixture
def stored_choices(monkeypatch):
    stored = []

    def record_choice(**choice):
        stored.append((choice["keys"], choice["declined"]))

    monkeypatch.setattr("bot.commands.roles.set_pod_roles_declined_sync", record_choice)
    return stored


def test_the_slot_role_is_skipped_when_the_player_switched_it_off(monkeypatch):
    monkeypatch.setattr("bot.services.ping_roles.declined_pod_roles_sync", lambda user_id: {"early"})
    member = _FakeMember(5151)

    asyncio.run(grant_pod_roles(member, EARLY_POD_ROLE_NAME))

    assert [role.name for role in member.roles] == [POD_DRAFTERS_ROLE_NAME]


def test_a_decline_on_one_slot_leaves_the_others_grantable(monkeypatch):
    monkeypatch.setattr("bot.services.ping_roles.declined_pod_roles_sync", lambda user_id: {"early"})
    member = _FakeMember(5252)

    asyncio.run(grant_pod_roles(member, LATE_POD_ROLE_NAME))

    assert [role.name for role in member.roles] == [POD_DRAFTERS_ROLE_NAME, LATE_POD_ROLE_NAME]


def test_pod_drafters_is_granted_whatever_the_player_declined(monkeypatch):
    monkeypatch.setattr(
        "bot.services.ping_roles.declined_pod_roles_sync",
        lambda user_id: {"drafters", "early", "late"},
    )
    member = _FakeMember(5353)

    asyncio.run(grant_pod_roles(member, None))

    assert [role.name for role in member.roles] == [POD_DRAFTERS_ROLE_NAME]


@pytest.mark.parametrize(
    "declined, held, expected",
    [
        (set(), [], [POD_DRAFTERS_ROLE_NAME, MOCK_DRAFT_ROLE_NAME]),
        ({"mock"}, [], [POD_DRAFTERS_ROLE_NAME]),
        (set(), [MOCK_DRAFT_ROLE_NAME], [MOCK_DRAFT_ROLE_NAME, POD_DRAFTERS_ROLE_NAME]),
    ],
    ids=["grants-on-join", "respects-the-decline", "already-held"],
)
def test_mock_draft_join_carries_the_umbrella(monkeypatch, declined, held, expected):
    monkeypatch.setattr("bot.services.ping_roles.declined_pod_roles_sync", lambda user_id: declined)
    member = _FakeMember(6161)
    member.roles = [role for role in member.guild.roles if role.name in held]

    asyncio.run(grant_mock_draft_role(member))

    assert [role.name for role in member.roles] == expected


def test_every_ping_role_carries_a_distinct_key():
    keys = [spec.key for spec in PING_ROLES]

    assert len(keys) == len(set(keys))
    assert all(key and key == key.lower() for key in keys)


class _FakeGuild:
    def __init__(self):
        self.roles = [SimpleNamespace(name=spec.name) for spec in PING_ROLES]


class _FakeMember:
    def __init__(self, member_id):
        self.id = member_id
        self.name = f"member{member_id}"
        self.display_name = self.name
        self.roles = []
        self.guild = _FakeGuild()

    async def add_roles(self, *roles, reason=None):
        self.roles.extend(roles)

    async def remove_roles(self, *roles, reason=None):
        for role in roles:
            self.roles.remove(role)


def _spec_named(name):
    from bot.services.ping_roles import PING_ROLES

    for spec in PING_ROLES:
        if spec.name == name:
            return spec
    raise AssertionError(f"no spec named {name}")


class FakeManagedGuild:
    def __init__(self, *roles):
        self.name = "guild"
        self.roles = list(roles)
        self.created = []

    async def create_role(self, **kwargs):
        self.created.append(kwargs)
        return SimpleNamespace(**kwargs)


class FakeManagedRole:
    def __init__(self, name, colour):
        self.name = name
        self.colour = colour

    async def edit(self, **kwargs):
        for field, value in kwargs.items():
            if field != "reason":
                setattr(self, field, value)


def test_a_renamed_managed_role_is_adopted_rather_than_orphaned():
    wanted = discord.Colour.from_str(REMINDER_COLOR)
    stale = FakeManagedRole("P0P1 Reminder", discord.Colour.default())
    guild = FakeManagedGuild(stale)

    asyncio.run(_ensure_managed_role(guild, managed_named(REMINDER_ROLE_NAME)))

    assert (stale.name, stale.colour) == (REMINDER_ROLE_NAME, wanted)
    assert guild.created == []


def test_a_managed_role_with_no_alias_present_is_created():
    guild = FakeManagedGuild()

    asyncio.run(_ensure_managed_role(guild, managed_named(REMINDER_ROLE_NAME)))

    assert [role["name"] for role in guild.created] == [REMINDER_ROLE_NAME]


def managed_named(name):
    for spec in MANAGED_ROLES:
        if spec.name == name:
            return spec
    raise AssertionError(f"{name} is not a managed role")


@pytest.mark.parametrize("role_name,expected", [
    ("The Hobbit Set Champion", True),
    ("Marvel Set Champion", True),
    ("Set Champion", False),
    ("Prior Set Champion", False),
    ("Pod Drafters", False),
])
def test_is_set_champion_title(role_name, expected):
    assert is_set_champion_title(role_name) is expected
