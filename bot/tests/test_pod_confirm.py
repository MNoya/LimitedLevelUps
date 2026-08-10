from datetime import datetime, timedelta, timezone

import discord
import pytest

from bot.models import PodDraftEvent, PodSignal, PodSignalMember
from bot.services import pod_confirm, pod_signals
from bot.services.pod_confirm import (
    Attendance,
    confirm_present_players_sync,
    opens_confirmation,
    plan_tables,
    seating_plan,
)
from bot.services.pod_staging import Signup, deal_into_plan
from bot.services.pod_roster_fields import FIELD_VALUE_LIMIT, add_table_plan_fields
from bot.services.pod_launch import set_rsvp
from bot.tasks import pod_draft_reminder as reminder
from bot.tasks.pod_daily_poll import build_reminder_view
from bot.services.pod_schedule import SCHEDULE_TZ


MESSAGE_ID = "9101"


def _session_factory(session):
    class _Ctx:
        def __enter__(self):
            return session

        def __exit__(self, *exc):
            return False

    return lambda: _Ctx()

HALL_OF_FAME = ("Finkel", "LSV", "Reid", "Nassif", "Chapin", "Budde")


@pytest.fixture
def scheduled_signal(session):
    signal = PodSignal(
        kind=pod_signals.KIND_SCHEDULED,
        bucket=pod_signals.SCHEDULED_BUCKET,
        guild_id="1",
        channel_id="2",
        message_id=MESSAGE_ID,
        signal_date=datetime.now(SCHEDULE_TZ).date(),
        slot_time=datetime.now(timezone.utc) + timedelta(hours=1),
        status=pod_signals.STATUS_FIRED,
    )
    session.add(signal)
    session.flush()
    return signal


@pytest.mark.parametrize("players, seating, waiting", [
    (6, ((6, 6),), 0),
    (7, ((7, 8),), 0),
    (8, ((8, 8),), 0),
    (9, ((9, 10),), 0),
    (10, ((10, 10),), 0),
    (11, ((10, 10),), 1),
    (12, ((6, 6), (6, 6)), 0),
    (13, ((6, 6), (7, 8)), 0),
    (14, ((8, 8), (6, 6)), 0),
    (15, ((8, 8), (7, 8)), 0),
    (16, ((8, 8), (8, 8)), 0),
    (18, ((8, 8), (10, 10)), 0),
    (19, ((10, 10), (9, 10)), 0),
    (20, ((8, 8), (6, 6), (6, 6)), 0),
    (30, ((8, 8), (8, 8), (8, 8), (6, 6)), 0),
])
def test_plan_seats_players_in_real_pods(players, seating, waiting):
    plan = plan_tables(players)

    assert tuple((t.seated, t.capacity) for t in plan.tables) == seating
    assert plan.waiting == waiting


def test_every_player_is_seated_or_waiting_at_a_real_pod():
    for players in range(6, 41):
        plan = plan_tables(players)

        assert plan.seated + plan.waiting == players
        assert all(t.seated >= 6 for t in plan.tables)
        assert all(t.capacity in (6, 8, 10) for t in plan.tables)


def test_only_eleven_leaves_anyone_without_a_table():
    waiting = [players for players in range(6, 41) if plan_tables(players).waiting]

    assert waiting == [11]


def test_expected_counts_an_unanswered_yes_but_not_an_unanswered_maybe():
    attendance = Attendance(confirmed=("Finkel",), yes=("LSV", "Reid"), maybe=("Nassif",))

    assert attendance.expected == 3
    assert attendance.signed_up == 4


@pytest.mark.parametrize("yes_count, opens", [(7, False), (8, True), (9, True)])
def test_confirmation_opens_at_a_full_table_of_yes(yes_count, opens):
    attendance = Attendance(yes=tuple(HALL_OF_FAME[:1] * yes_count))

    assert opens_confirmation(attendance) is opens


def test_confirming_stamps_a_member_who_was_already_yes(session, scheduled_signal):
    set_rsvp(session, MESSAGE_ID, "u1", "Finkel", pod_signals.RSVP_YES)

    set_rsvp(session, MESSAGE_ID, "u1", "Finkel", pod_signals.RSVP_YES, confirming=True)

    member = session.query(PodSignalMember).filter_by(discord_user_id="u1").one()
    assert member.confirmed_at is not None
    assert member.rsvp == pod_signals.RSVP_YES


def test_confirming_from_maybe_lands_in_confirmed_not_yes(session, scheduled_signal):
    set_rsvp(session, MESSAGE_ID, "u2", "LSV", pod_signals.RSVP_MAYBE)

    set_rsvp(session, MESSAGE_ID, "u2", "LSV", pod_signals.RSVP_YES, confirming=True)

    member = session.query(PodSignalMember).filter_by(discord_user_id="u2").one()
    assert member.confirmed_at is not None
    assert member.rsvp == pod_signals.RSVP_YES


@pytest.mark.parametrize("confirming, state", [(False, pod_signals.RSVP_YES), (True, "confirm")])
def test_reminder_yes_seat_carries_the_confirm_state_when_asked(confirming, state):
    view = build_reminder_view("evt-1", confirming)

    ids = [item.item.custom_id for item in view.children if hasattr(item, "item")]
    seats = [custom_id for custom_id in ids if custom_id.startswith("podreminderrsvp:")]
    assert seats == [f"podreminderrsvp:{state}:evt-1", "podreminderrsvp:no:evt-1"]


@pytest.mark.parametrize("messages, buried", [(0, False), (9, False), (10, True), (25, True)])
def test_card_counts_as_buried_only_after_enough_was_said(messages, buried):
    reminder._messages_since_card[4242] = 0
    for _ in range(messages):
        reminder.note_thread_message(4242)

    assert reminder.card_is_buried(4242) is buried


def test_an_unseen_thread_is_never_treated_as_buried():
    reminder._messages_since_card.pop(777, None)
    reminder.note_thread_message(777)

    assert reminder.card_is_buried(777) is False


def test_a_long_column_stays_inside_the_discord_field_limit():
    names = tuple("W" * 32 + str(i) for i in range(40))
    attendance = Attendance(confirmed=names[:8], maybe=names[8:])

    embed = discord.Embed()
    add_table_plan_fields(embed, attendance, plan_tables(attendance.expected))

    assert all(len(field.value) <= FIELD_VALUE_LIMIT for field in embed.fields)
    assert embed.fields[-1].value.endswith("+5 more")


def test_confirmed_players_fill_the_first_table_before_anyone_unconfirmed():
    confirmed = tuple(HALL_OF_FAME[:4])
    attendance = Attendance(confirmed=confirmed, yes=tuple(f"Unconfirmed{i}" for i in range(9)))

    embed = discord.Embed()
    add_table_plan_fields(embed, attendance, plan_tables(attendance.expected))

    first_table = embed.fields[0].value
    assert all(name in first_table for name in confirmed)
    assert "Unconfirmed" not in embed.fields[0].value.split(confirmed[-1])[0]


def test_the_eleventh_player_is_shown_waiting_instead_of_dropped():
    names = tuple(f"Player{i}" for i in range(11))
    attendance = Attendance(confirmed=names)

    embed = discord.Embed()
    add_table_plan_fields(embed, attendance, plan_tables(attendance.expected))

    rendered = " ".join(field.value for field in embed.fields)
    assert all(name in rendered for name in names)
    assert names[10] in embed.fields[-1].value


@pytest.mark.parametrize("minutes_out, expect_job", [(120, True), (50, True), (8, False)])
def test_a_late_born_pod_still_gets_its_roster_card(minutes_out, expect_job):
    scheduler = _RecordingScheduler()
    event_time = datetime.now(timezone.utc) + timedelta(minutes=minutes_out)

    reminder.schedule_roster_reminder(scheduler, "EVT", event_time)

    assert bool(scheduler.added) is expect_job


class _RecordingScheduler:
    def __init__(self) -> None:
        self.added: list[datetime] = []

    def add_job(self, _func, _trigger, run_date, **_kwargs) -> None:
        self.added.append(run_date)

    def remove_job(self, _job_id) -> None:
        pass


@pytest.mark.parametrize("minutes, confirms", [(30, True), (300, False)])
def test_saying_yes_confirms_only_once_the_draft_is_within_the_hour(
    session, scheduled_signal, minutes, confirms,
):
    scheduled_signal.event_id = _pod_starting_in(session, minutes=minutes).id
    set_rsvp(session, MESSAGE_ID, "u9", "Finkel", pod_signals.RSVP_YES)

    member = session.query(PodSignalMember).filter_by(discord_user_id="u9").one()
    assert (member.confirmed_at is not None) is confirms


def test_dropping_to_maybe_gives_the_confirmation_back(session, scheduled_signal):
    scheduled_signal.event_id = _pod_starting_in(session, minutes=30).id
    set_rsvp(session, MESSAGE_ID, "u11", "Reid", pod_signals.RSVP_YES, confirming=True)

    set_rsvp(session, MESSAGE_ID, "u11", "Reid", pod_signals.RSVP_MAYBE)

    member = session.query(PodSignalMember).filter_by(discord_user_id="u11").one()
    assert member.confirmed_at is None


def test_turning_up_in_the_lobby_confirms_a_seat(session, scheduled_signal, monkeypatch):
    monkeypatch.setattr(pod_confirm, "SessionLocal", _session_factory(session))
    scheduled_signal.event_id = _pod_starting_in(session, minutes=300).id
    set_rsvp(session, MESSAGE_ID, "u12", "Chapin", pod_signals.RSVP_YES)
    session.flush()

    stamped = confirm_present_players_sync(scheduled_signal.event_id, ["u12", "u-not-signed-up"])

    member = session.query(PodSignalMember).filter_by(discord_user_id="u12").one()
    assert (stamped, member.confirmed_at is not None) == (1, True)


def _pod_starting_in(session, *, minutes: int) -> PodDraftEvent:
    event = PodDraftEvent(
        name=f"Pod in {minutes}", set_code="CUBE", discord_thread_id="77",
        draftmancer_session=f"llu-{minutes}", socket_status="pending",
        event_date=datetime.now(SCHEDULE_TZ).date(),
        event_time=datetime.now(timezone.utc) + timedelta(minutes=minutes),
    )
    session.add(event)
    session.flush()
    return event


@pytest.mark.parametrize("signed, confirmed", [
    (13, 13), (13, 8), (20, 12), (20, 20), (12, 6), (11, 11), (6, 4), (8, 0),
])
def test_the_card_draws_what_the_release_deals(signed, confirmed):
    """One planner, two surfaces. They read the same TablePlan, so a player counting seats on the card is
    counting the seats that open."""
    attendance = Attendance(
        confirmed=tuple(f"c{i}" for i in range(confirmed)),
        yes=tuple(f"u{i}" for i in range(signed - confirmed)),
    )
    roster = (
        [Signup(f"c{i}", f"c{i}", True) for i in range(confirmed)]
        + [Signup(f"u{i}", f"u{i}", False) for i in range(signed - confirmed)]
    )

    plan = seating_plan(attendance)
    groups = deal_into_plan([signup for signup in roster if signup.confirmed], plan)

    assert [table.seated for table in plan.tables] == [len(group) for group in groups]
    assert sum(len(group) for group in groups) + plan.waiting == confirmed
