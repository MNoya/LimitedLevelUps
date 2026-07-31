from datetime import datetime, timedelta, timezone

import pytest

from bot.commands.pod_rsvp import (
    CARD_RSVP_PROMPT,
    CARD_STATUS_DRAFTING,
    CARD_STATUS_PLAYING,
    MULTIPOD_NOTICE,
    POD_CAPACITY,
    TIME_LABEL,
    build_rsvp_embed,
    native_body_from_description,
    native_event_description,
    parse_new_time,
    refresh_roster_fields,
)
from bot.services import pod_team
from bot.services.pod_team_board import TeamBoardMember
from bot.models import PodDraftEvent, PodSignal
from bot.services import pod_format_interest as fi
from bot.services import pod_signals
from bot.services.pod_drafts import set_format_interests
from bot.services.pod_launch import _committed_slot, _event_id_for_slot, set_rsvp
from bot.services.pod_registration_embed import (
    build_registered_embed,
    closed_registered_embed,
    embed_event_time,
)
from bot.services.pod_schedule import SCHEDULE_TZ
from bot.services.pod_signals import RSVP_YES


MESSAGE_ID = "9001"


@pytest.fixture
def scheduled_signal(session):
    signal = PodSignal(
        kind=pod_signals.KIND_SCHEDULED,
        bucket=pod_signals.SCHEDULED_BUCKET,
        guild_id="1",
        channel_id="2",
        message_id=MESSAGE_ID,
        signal_date=datetime.now(SCHEDULE_TZ).date(),
        slot_time=datetime.now(timezone.utc) + timedelta(days=2),
        status=pod_signals.STATUS_FIRED,
    )
    session.add(signal)
    session.flush()
    return signal


def test_first_yes_click_joins(session, scheduled_signal):
    result = set_rsvp(session, MESSAGE_ID, "u1", "Nissa Revane", pod_signals.RSVP_YES)

    assert result.joined
    assert result.rsvp == pod_signals.RSVP_YES
    assert result.rosters[pod_signals.RSVP_YES] == ["Nissa Revane"]
    assert result.state.count == 1


def test_clicking_another_state_moves_the_member(session, scheduled_signal):
    set_rsvp(session, MESSAGE_ID, "u1", "Nissa Revane", pod_signals.RSVP_YES)

    result = set_rsvp(session, MESSAGE_ID, "u1", "Nissa Revane", pod_signals.RSVP_MAYBE)

    assert not result.joined
    assert result.rsvp == pod_signals.RSVP_MAYBE
    assert result.rosters[pod_signals.RSVP_YES] == []
    assert result.rosters[pod_signals.RSVP_MAYBE] == ["Nissa Revane"]


def test_clicking_the_held_state_keeps_the_rsvp(session, scheduled_signal):
    set_rsvp(session, MESSAGE_ID, "u1", "Nissa Revane", pod_signals.RSVP_YES)

    result = set_rsvp(session, MESSAGE_ID, "u1", "Nissa Revane", pod_signals.RSVP_YES)

    assert result.rsvp == pod_signals.RSVP_YES
    assert not result.joined
    assert result.rosters[pod_signals.RSVP_YES] == ["Nissa Revane"]


def test_moving_from_maybe_to_yes_counts_as_joining(session, scheduled_signal):
    set_rsvp(session, MESSAGE_ID, "u1", "Nissa Revane", pod_signals.RSVP_MAYBE)

    result = set_rsvp(session, MESSAGE_ID, "u1", "Nissa Revane", pod_signals.RSVP_YES)

    assert result.joined


@pytest.mark.parametrize("prior, click, expected", [
    (None, pod_signals.RSVP_YES, True),
    (None, pod_signals.RSVP_MAYBE, False),
    (None, pod_signals.RSVP_NO, False),
    (pod_signals.RSVP_MAYBE, pod_signals.RSVP_YES, True),
    (pod_signals.RSVP_NO, pod_signals.RSVP_YES, True),
    (pod_signals.RSVP_YES, pod_signals.RSVP_MAYBE, True),
    (pod_signals.RSVP_YES, pod_signals.RSVP_NO, True),
    (pod_signals.RSVP_YES, pod_signals.RSVP_YES, False),
    (pod_signals.RSVP_MAYBE, pod_signals.RSVP_NO, False),
    (pod_signals.RSVP_MAYBE, pod_signals.RSVP_MAYBE, False),
    (pod_signals.RSVP_NO, pod_signals.RSVP_NO, False),
])
def test_yes_changed_flags_only_yes_membership_transitions(session, scheduled_signal, prior, click, expected):
    if prior is not None:
        set_rsvp(session, MESSAGE_ID, "u1", "Nissa Revane", prior)

    result = set_rsvp(session, MESSAGE_ID, "u1", "Nissa Revane", click)

    assert result.yes_changed is expected


def test_a_no_click_removes_the_signup_from_every_roster(session, scheduled_signal):
    set_rsvp(session, MESSAGE_ID, "u1", "Nissa Revane", pod_signals.RSVP_YES)

    result = set_rsvp(session, MESSAGE_ID, "u1", "Nissa Revane", pod_signals.RSVP_NO)

    assert not result.joined
    assert result.rsvp is None
    assert all("Nissa Revane" not in names for names in result.rosters.values())
    assert result.state.count == 0


def test_expired_signal_refuses_without_mutating(session, scheduled_signal):
    scheduled_signal.status = pod_signals.STATUS_EXPIRED
    session.flush()

    result = set_rsvp(session, MESSAGE_ID, "u1", "Nissa Revane", pod_signals.RSVP_YES)

    assert result.closed
    assert all(names == [] for names in result.rosters.values())


def test_unknown_message_returns_none(session, scheduled_signal):
    assert set_rsvp(session, "555", "u1", "Nissa Revane", pod_signals.RSVP_YES) is None


def test_mirror_message_resolves_the_same_signal(session, scheduled_signal):
    scheduled_signal.thread_message_id = "9002"
    session.flush()

    set_rsvp(session, MESSAGE_ID, "u1", "Nissa Revane", pod_signals.RSVP_YES)
    result = set_rsvp(session, "9002", "u2", "Chandra Nalaar", pod_signals.RSVP_YES)

    assert result is not None
    assert result.rosters[pod_signals.RSVP_YES] == ["Nissa Revane", "Chandra Nalaar"]


def _pod_event(session, slot_time: datetime) -> str:
    event = PodDraftEvent(
        event_date=slot_time.date(), event_time=slot_time, set_code="TST",
        name="TST Pod Draft #1", draftmancer_session="s1", discord_thread_id="tid-1",
        socket_status="pending",
    )
    session.add(event)
    session.flush()
    return event.id


def _scheduled_pod(session, slot_time: datetime, yes: list[str]) -> str:
    event_id = _pod_event(session, slot_time)
    signal = PodSignal(
        kind=pod_signals.KIND_SCHEDULED, bucket=pod_signals.SCHEDULED_BUCKET, guild_id="1",
        channel_id="2", message_id="card-1", signal_date=slot_time.date(), slot_time=slot_time,
        status=pod_signals.STATUS_FIRED, event_id=event_id,
    )
    session.add(signal)
    session.flush()
    for i, name in enumerate(yes):
        set_rsvp(session, "card-1", f"u{i}", name, pod_signals.RSVP_YES)
    session.flush()
    return event_id


def test_reflection_binds_a_slot_to_the_pod_at_its_instant(session):
    slot_time = datetime.now(timezone.utc) + timedelta(days=1)
    event_id = _scheduled_pod(session, slot_time, [])

    assert _event_id_for_slot(session, slot_time) == event_id


def test_an_off_slot_pod_does_not_occupy_the_slot(session):
    slot_time = datetime.now(timezone.utc) + timedelta(days=1)
    _scheduled_pod(session, slot_time + timedelta(hours=1), [])

    assert _event_id_for_slot(session, slot_time) is None


def _table_event(session, slot_time: datetime, table_index: int) -> str:
    event = PodDraftEvent(
        event_date=slot_time.date(), event_time=slot_time, set_code="TST",
        name=f"TST Pod Draft #1 - Table {table_index}", draftmancer_session=f"s1-T{table_index}",
        discord_thread_id=f"tid-{table_index}", socket_status="pending", kind="tournament",
    )
    session.add(event)
    session.flush()
    return event.id


def test_a_second_table_keeps_reflecting_the_original_pod(session):
    slot_time = datetime.now(timezone.utc) + timedelta(days=1)
    event_id = _scheduled_pod(session, slot_time, [])
    _table_event(session, slot_time + timedelta(hours=1), 2)

    assert _event_id_for_slot(session, slot_time) == event_id


def test_committed_slot_projects_the_yes_roster_off_the_card(session):
    slot_time = datetime.now(timezone.utc) + timedelta(days=1)
    event_id = _scheduled_pod(session, slot_time, ["Nissa Revane", "Chandra Nalaar"])

    slot = _committed_slot(session, "AFTERNOON", event_id)

    assert slot.committed
    assert slot.count == 2
    assert slot.thread_id == "tid-1"
    assert slot.names == ["Nissa Revane", "Chandra Nalaar"]


def _standing_interest(session, discord_user_id: str, name: str, interests: list[str]) -> None:
    set_format_interests(
        session, discord_id=discord_user_id, discord_username=name, display_name=name,
        avatar_hash=None, interests=interests,
    )


def _flashback_split_pod(session, slot_time: datetime, *, format_locked: bool) -> None:
    event_id = _pod_event(session, slot_time)
    signal = PodSignal(
        kind=pod_signals.KIND_SCHEDULED, bucket=pod_signals.SCHEDULED_BUCKET, guild_id="1",
        channel_id="2", message_id="card-1", signal_date=slot_time.date(), slot_time=slot_time,
        status=pod_signals.STATUS_FIRED, event_id=event_id, format_locked=format_locked,
    )
    session.add(signal)
    session.flush()
    _standing_interest(session, "u0", "Latest Player", [fi.LATEST])
    _standing_interest(session, "u1", "Flashback Player", [fi.FLASHBACK])
    set_rsvp(session, "card-1", "u0", "Latest Player", pod_signals.RSVP_YES)


def test_flex_card_carries_member_interests_for_the_split(session):
    slot_time = datetime.now(timezone.utc) + timedelta(days=1)
    _flashback_split_pod(session, slot_time, format_locked=False)

    result = set_rsvp(session, "card-1", "u1", "Flashback Player", pod_signals.RSVP_YES)

    assert result.state.format_locked is False
    assert result.roster_interests[pod_signals.RSVP_YES] == [
        ("Latest Player", ("latest",)), ("Flashback Player", ("flashback",)),
    ]


def test_format_locked_card_drops_member_interests(session):
    slot_time = datetime.now(timezone.utc) + timedelta(days=1)
    _flashback_split_pod(session, slot_time, format_locked=True)

    result = set_rsvp(session, "card-1", "u1", "Flashback Player", pod_signals.RSVP_YES)

    assert result.state.format_locked is True
    assert result.roster_interests is None
    assert result.rosters[pod_signals.RSVP_YES] == ["Latest Player", "Flashback Player"]


def test_refresh_never_stacks_the_multipod_notice():
    event_time = datetime(2026, 7, 18, 16, 0, tzinfo=timezone.utc)
    embed = build_rsvp_embed("Early Pod", event_time, {RSVP_YES: []})

    for count in range(1, POD_CAPACITY + 4):
        refresh_roster_fields(embed, {RSVP_YES: [f"p{i}" for i in range(count)]})

    assert embed.description.count(MULTIPOD_NOTICE) == 1


def test_description_takes_the_rsvp_prompt_line():
    event_time = datetime(2026, 7, 18, 16, 0, tzinfo=timezone.utc)

    embed = build_rsvp_embed("Early Pod", event_time, {RSVP_YES: []}, description="bring snacks")

    assert "bring snacks" in embed.description
    assert CARD_RSVP_PROMPT not in embed.description


def test_status_line_replaces_the_rsvp_intro_and_notice():
    event_time = datetime(2026, 7, 18, 16, 0, tzinfo=timezone.utc)
    full_yes = {RSVP_YES: [f"p{i}" for i in range(POD_CAPACITY)]}

    embed = build_rsvp_embed(
        "Early Pod", event_time, full_yes, description="bring snacks", status_line=CARD_STATUS_DRAFTING,
    )

    assert CARD_STATUS_DRAFTING in embed.description
    assert MULTIPOD_NOTICE not in embed.description
    assert CARD_RSVP_PROMPT not in embed.description
    assert "bring snacks" not in embed.description


def test_refresh_swaps_status_across_phases():
    event_time = datetime(2026, 7, 18, 16, 0, tzinfo=timezone.utc)
    full_yes = {RSVP_YES: [f"p{i}" for i in range(POD_CAPACITY)]}
    embed = build_rsvp_embed("Early Pod", event_time, full_yes, description="bring snacks")
    title_line = embed.description.split("\n")[0]

    refresh_roster_fields(embed, full_yes, CARD_STATUS_DRAFTING)
    refresh_roster_fields(embed, full_yes, CARD_STATUS_PLAYING)

    assert embed.description.split("\n")[0] == title_line
    assert CARD_STATUS_DRAFTING not in embed.description
    assert embed.description.count(CARD_STATUS_PLAYING) == 1
    assert MULTIPOD_NOTICE not in embed.description
    assert "bring snacks" not in embed.description


def test_team_rosters_replace_the_rsvp_columns_in_flight():
    event_time = datetime(2026, 7, 18, 16, 0, tzinfo=timezone.utc)
    team_rosters = {
        pod_team.TEAM_A: [TeamBoardMember("Green One", None), TeamBoardMember("Green Two", None)],
        pod_team.TEAM_B: [TeamBoardMember("Blue One", None), TeamBoardMember("Blue Two", None)],
    }

    embed = build_rsvp_embed(
        "Early Pod", event_time, {RSVP_YES: []}, status_line=CARD_STATUS_PLAYING, team_draft=True,
        team_rosters=team_rosters,
    )

    values = "\n".join(field.value for field in embed.fields)
    assert all(member in values for member in ("Green One", "Blue Two"))
    assert not any(field.name == TIME_LABEL for field in embed.fields)


def test_team_columns_show_record_and_colors_once_finalized():
    event_time = datetime(2026, 7, 18, 16, 0, tzinfo=timezone.utc)
    team_rosters = {
        pod_team.TEAM_A: [TeamBoardMember("Green One", None, record="3-0", deck_colors="WU")],
        pod_team.TEAM_B: [TeamBoardMember("Blue One", None, record="1-2", deck_colors="BR")],
    }

    embed = build_rsvp_embed(
        "Early Pod", event_time, {RSVP_YES: []}, status_line="🏆 Green One wins the draft 3-1",
        team_draft=True, team_rosters=team_rosters,
    )

    values = "\n".join(field.value for field in embed.fields)
    assert "3-0" in values and "1-2" in values


CURRENT = datetime(2026, 7, 15, 20, 0, tzinfo=SCHEDULE_TZ)
NOW = datetime(2026, 7, 14, 12, 0, tzinfo=SCHEDULE_TZ)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("+2h", CURRENT + timedelta(hours=2)),
        ("+30m", CURRENT + timedelta(minutes=30)),
        ("+2h30m", CURRENT + timedelta(hours=2, minutes=30)),
        ("1h", CURRENT + timedelta(hours=1)),
        ("30m", CURRENT + timedelta(minutes=30)),
        ("2h30m", CURRENT + timedelta(hours=2, minutes=30)),
        ("21:00", datetime(2026, 7, 15, 21, 0, tzinfo=SCHEDULE_TZ)),
        ("2026-07-18 21:00", datetime(2026, 7, 18, 21, 0, tzinfo=SCHEDULE_TZ)),
        ("half past nine", None),
        ("+", None),
        ("2020-01-01 12:00", None),
    ],
)
def test_parse_new_time(raw, expected):
    assert parse_new_time(raw, CURRENT, NOW) == expected


def test_parse_new_time_refuses_a_past_result():
    late_now = CURRENT + timedelta(hours=3)

    assert parse_new_time("+2h", CURRENT, late_now) is None


REF = datetime(2026, 7, 14, 12, 0, tzinfo=SCHEDULE_TZ)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Today 10pm ET", datetime(2026, 7, 14, 22, 0, tzinfo=SCHEDULE_TZ)),
        ("tonight 8pm", datetime(2026, 7, 14, 20, 0, tzinfo=SCHEDULE_TZ)),
        ("tomorrow 8:30pm", datetime(2026, 7, 15, 20, 30, tzinfo=SCHEDULE_TZ)),
        ("fri 9pm", datetime(2026, 7, 17, 21, 0, tzinfo=SCHEDULE_TZ)),
        ("friday at 20:00", datetime(2026, 7, 17, 20, 0, tzinfo=SCHEDULE_TZ)),
        ("next tuesday 8pm", datetime(2026, 7, 21, 20, 0, tzinfo=SCHEDULE_TZ)),
        ("10pm", datetime(2026, 7, 14, 22, 0, tzinfo=SCHEDULE_TZ)),
        ("8am", datetime(2026, 7, 15, 8, 0, tzinfo=SCHEDULE_TZ)),
        ("12pm", datetime(2026, 7, 14, 12, 0, tzinfo=SCHEDULE_TZ) + timedelta(days=1)),
        ("today 8am", None),
        ("half past nine", None),
    ],
)
def test_parse_new_time_natural_language(raw, expected):
    assert parse_new_time(raw, REF, REF) == expected


def test_parse_new_time_accepts_a_pasted_discord_timestamp():
    future = datetime(2026, 7, 18, 21, 0, tzinfo=SCHEDULE_TZ)

    parsed = parse_new_time(f"<t:{int(future.timestamp())}:F>", REF, REF)

    assert parsed == future


def test_parse_new_time_rejects_a_past_discord_timestamp():
    past = datetime(2020, 1, 1, 12, 0, tzinfo=SCHEDULE_TZ)

    assert parse_new_time(f"<t:{int(past.timestamp())}:F>", REF, REF) is None


JUMP_URL = "https://discord.com/channels/1/2/3"


@pytest.mark.parametrize(
    "body",
    [None, "one paragraph", "two\n\nparagraphs", "a line\nand another\n\nafter a break"],
)
def test_a_tally_re_render_keeps_the_announcement(body):
    posted = native_event_description({RSVP_YES: ["a"]}, JUMP_URL, body)

    carried = native_body_from_description(posted)
    resynced = native_event_description({RSVP_YES: ["a", "b"]}, JUMP_URL, carried)

    assert carried == body
    assert native_body_from_description(resynced) == body


@pytest.mark.parametrize("hours", [-3, 3])
def test_closing_the_registered_embed_keeps_the_columns_and_the_time(hours):
    event_time = datetime.now(timezone.utc) + timedelta(hours=hours)
    open_embed = build_registered_embed(
        "LTR", "bracket", "random", rsvp_hint=True, channel_post_url=JUMP_URL, event_time=event_time)

    closed = closed_registered_embed(open_embed)

    assert len(open_embed.fields) == len(closed.fields) + 1
    assert [field.name for field in closed.fields] == [field.name for field in open_embed.fields[:-1]]
    assert embed_event_time(closed) == event_time.replace(microsecond=0)


def test_closing_a_registered_embed_without_a_time_drops_the_body():
    open_embed = build_registered_embed("LTR", "bracket", "random")

    closed = closed_registered_embed(open_embed)

    assert closed.description is None
    assert len(closed.fields) == len(open_embed.fields)
