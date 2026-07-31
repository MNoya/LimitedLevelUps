import asyncio
from datetime import datetime
from types import SimpleNamespace

from bot.services.ping_roles import (
    EARLY_POD_ROLE_NAME,
    PING_ROLES,
    LATE_POD_ROLE_NAME,
    WEEKEND_EARLY_POD_ROLE_NAME,
    WEEKEND_LATE_POD_ROLE_NAME,
    _first_welcome_for,
    auto_grant_spec_for_event,
    blurb_with_time,
    button_custom_id,
    forget_welcome,
    grant_pod_roles,
)
from bot.services.pod_roles import consume_bot_umbrella_grant, grant_role
from bot.services.pod_schedule import POD_DRAFTERS_ROLE_NAME, SCHEDULE_TZ


def test_auto_grant_maps_timed_weekday_slots_to_their_roles():
    thursday = datetime(2026, 6, 11, 14, 0, tzinfo=SCHEDULE_TZ)
    wednesday = datetime(2026, 6, 10, 20, 0, tzinfo=SCHEDULE_TZ)
    off_grid = datetime(2026, 6, 9, 11, 0, tzinfo=SCHEDULE_TZ)

    assert auto_grant_spec_for_event(thursday).name == EARLY_POD_ROLE_NAME
    assert auto_grant_spec_for_event(wednesday).name == LATE_POD_ROLE_NAME
    assert auto_grant_spec_for_event(off_grid) is None


def test_auto_grant_splits_weekend_daytime_from_evening():
    saturday_early = datetime(2026, 6, 13, 14, 0, tzinfo=SCHEDULE_TZ)
    saturday_evening = datetime(2026, 6, 13, 20, 0, tzinfo=SCHEDULE_TZ)
    saturday_off_grid = datetime(2026, 6, 13, 10, 0, tzinfo=SCHEDULE_TZ)

    assert auto_grant_spec_for_event(saturday_early).name == WEEKEND_EARLY_POD_ROLE_NAME
    assert auto_grant_spec_for_event(saturday_evening).name == WEEKEND_LATE_POD_ROLE_NAME
    assert auto_grant_spec_for_event(saturday_off_grid) is None


def test_button_custom_id_is_a_stable_slug():
    assert button_custom_id(_spec_named(POD_DRAFTERS_ROLE_NAME)) == "role-toggle-pod-drafters"


def test_blurb_with_time_pairs_a_weekday_slot_with_its_local_time():
    blurb = blurb_with_time(_spec_named(EARLY_POD_ROLE_NAME))

    assert "<t:" in blurb and ":t>" in blurb


def test_blurb_with_time_lists_only_the_role_s_own_weekend_slots():
    early = blurb_with_time(_spec_named(WEEKEND_EARLY_POD_ROLE_NAME))
    late = blurb_with_time(_spec_named(WEEKEND_LATE_POD_ROLE_NAME))

    assert early.count("<t:") == 1
    assert late.count("<t:") == 1


def test_first_welcome_fires_once_until_forgotten():
    member_id = 90909

    assert _first_welcome_for(member_id) is True
    assert _first_welcome_for(member_id) is False
    forget_welcome(member_id)
    assert _first_welcome_for(member_id) is True


def test_consume_bot_umbrella_grant_is_a_one_shot_flag():
    grant_role_marks_umbrella_grant()

    assert consume_bot_umbrella_grant(4242) is True
    assert consume_bot_umbrella_grant(4242) is False


def test_bot_mediated_umbrella_grant_is_marked_so_the_listener_skips_it():
    member = _FakeMember(4343)
    umbrella = SimpleNamespace(name=POD_DRAFTERS_ROLE_NAME)

    asyncio.run(grant_role(member, umbrella))

    assert consume_bot_umbrella_grant(4343) is True


def test_slot_role_grant_leaves_the_umbrella_unmarked():
    member = _FakeMember(4444)
    slot_role = SimpleNamespace(name=EARLY_POD_ROLE_NAME)

    asyncio.run(grant_role(member, slot_role))

    assert consume_bot_umbrella_grant(4444) is False


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
        lambda user_id: {"drafters", "early", "late", "wknd_early", "wknd_late"},
    )
    member = _FakeMember(5353)

    asyncio.run(grant_pod_roles(member, None))

    assert [role.name for role in member.roles] == [POD_DRAFTERS_ROLE_NAME]


def test_every_ping_role_carries_a_distinct_key():
    keys = [spec.key for spec in PING_ROLES]

    assert len(keys) == len(set(keys))
    assert all(key and key == key.lower() for key in keys)


class _FakeGuild:
    def __init__(self):
        self.roles = [SimpleNamespace(name=spec.name) for spec in PING_ROLES]


def grant_role_marks_umbrella_grant():
    member = _FakeMember(4242)
    umbrella = SimpleNamespace(name=POD_DRAFTERS_ROLE_NAME)
    asyncio.run(grant_role(member, umbrella))


class _FakeMember:
    def __init__(self, member_id):
        self.id = member_id
        self.roles = []
        self.guild = _FakeGuild()

    async def add_roles(self, *roles, reason=None):
        self.roles.extend(roles)


def _spec_named(name):
    from bot.services.ping_roles import PING_ROLES

    for spec in PING_ROLES:
        if spec.name == name:
            return spec
    raise AssertionError(f"no spec named {name}")
