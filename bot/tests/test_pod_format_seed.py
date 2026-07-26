from datetime import date, datetime, timedelta, timezone

from bot.models import Player, PodDraftEvent, PodSignal
from bot.services import pod_format_interest as fi
from bot.services import pod_signals
from bot.services.pod_drafts import get_flashback_ranking, set_flashback_ranking
from bot.services.pod_launch import _launcher_day_signal_ids, set_rsvp, toggle_member


def _poll_signal(session, message_id="7001", bucket="EARLY"):
    slot_time = datetime.now(timezone.utc) + timedelta(days=1)
    signal = PodSignal(
        kind=pod_signals.KIND_POLL, bucket=bucket, guild_id="g1", channel_id="c1",
        message_id=message_id, signal_date=slot_time.date(), status=pod_signals.STATUS_OPEN,
        slot_time=slot_time, created_at=datetime.now(timezone.utc),
    )
    session.add(signal)
    session.flush()
    return signal


def _scheduled_signal(session, message_id="8001"):
    slot_time = datetime.now(timezone.utc) + timedelta(days=1)
    signal = PodSignal(
        kind=pod_signals.KIND_SCHEDULED, bucket=pod_signals.SCHEDULED_BUCKET, guild_id="g1",
        channel_id="c1", message_id=message_id, signal_date=slot_time.date(),
        status=pod_signals.STATUS_FIRED, slot_time=slot_time, created_at=datetime.now(timezone.utc),
    )
    session.add(signal)
    session.flush()
    return signal


def _seeded_interests(signal):
    """The standing preference each signup carried onto the roster. Dormant data: no signup path reads it
    back, and the launcher names each pod's format on its own button."""
    return [list(member.format_interest) for member in signal.members]


def test_join_seeds_interest_from_the_players_standing_preference(session):
    session.add(Player(
        slug="rowan-1", discord_id="u1", display_name="Rowan", format_interests=[fi.LATEST, fi.FLASHBACK]))
    signal = _poll_signal(session)

    toggle_member(session, signal.message_id, signal.bucket, "u1", "Rowan")

    assert _seeded_interests(signal) == [[fi.LATEST, fi.FLASHBACK]]


def test_join_without_a_player_row_seeds_no_interest(session):
    signal = _poll_signal(session)

    toggle_member(session, signal.message_id, signal.bucket, "u2", "Guest")

    assert _seeded_interests(signal) == [[]]


def test_scheduled_card_rsvp_seeds_interest_from_the_players_standing_preference(session):
    session.add(Player(
        slug="wren-1", discord_id="u3", display_name="Wren", format_interests=[fi.FLASHBACK]))
    signal = _scheduled_signal(session)

    set_rsvp(session, signal.message_id, "u3", "Wren", pod_signals.RSVP_YES)

    assert _seeded_interests(signal) == [[fi.FLASHBACK]]


def test_launcher_day_signals_include_the_reflected_scheduled_pod(session):
    lazy = _poll_signal(session)
    slot_time = pod_signals.slot_event_time(date(2026, 7, 20), "LATE")
    event = PodDraftEvent(
        event_date=slot_time.date(), event_time=slot_time, set_code="TST",
        name="TST Pod Draft #1", draftmancer_session="s1", discord_thread_id="tid-1",
        socket_status="pending",
    )
    session.add(event)
    session.flush()
    scheduled = PodSignal(
        kind=pod_signals.KIND_SCHEDULED, bucket=pod_signals.SCHEDULED_BUCKET, guild_id="g1",
        channel_id="c1", message_id="card-1", signal_date=date(2026, 7, 20), slot_time=slot_time,
        status=pod_signals.STATUS_FIRED, event_id=event.id,
    )
    session.add(scheduled)
    session.flush()

    ids = _launcher_day_signal_ids(session, lazy.message_id, date(2026, 7, 20))

    assert set(ids) == {lazy.id, scheduled.id}


def test_flashback_ranking_is_capped_at_the_max(session):
    session.add(Player(slug="reid-1", discord_id="u9", display_name="Reid"))
    session.flush()
    overflow = ["FIN", "NEO", "DMU", "DSK", "MOM", "BRO", "IKO"]

    set_flashback_ranking(session, discord_id="u9", ranking=overflow)

    stored = get_flashback_ranking(session, "u9")
    assert stored == overflow[: fi.FLASHBACK_RANKING_MAX]
    assert len(stored) == fi.FLASHBACK_RANKING_MAX
