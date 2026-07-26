from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from bot.commands.pod_queue import _preset_slot_time, _when_options
from bot.services.pod_format_select import WRITE_IN_VALUE
from bot.services.pod_launch import LauncherSlot, _lazy_status
from bot.services.pod_signals import STATUS_EXPIRED, STATUS_FIRED, STATUS_OPEN, named_bucket_key
from bot.sets import active_set_code
from bot.tasks.pod_daily_poll import PodPollView, _committed_card_link, build_reminder_view


BEFORE_EARLY = datetime(2026, 7, 14, 10, 0, tzinfo=timezone.utc)
AFTER_LATE = datetime(2026, 7, 15, 3, 0, tzinfo=timezone.utc)
LATEST = active_set_code()


def _committed(bucket_key, thread_id, thread_message_id):
    return LauncherSlot(
        named_bucket_key(bucket_key, LATEST), committed=True, status=STATUS_FIRED, count=1,
        slot_time=None, set_code=LATEST,
        names=["p"], thread_id=thread_id, signal_id=None, thread_message_id=thread_message_id,
    )


def _lazy(bucket_key, status, set_code=None):
    set_code = set_code or LATEST
    return LauncherSlot(
        named_bucket_key(bucket_key, set_code), committed=False, status=status, count=0, slot_time=None,
        names=[], thread_id=None, signal_id=None, set_code=set_code,
    )


def test_committed_slot_deep_links_to_its_thread_card():
    view = PodPollView([_committed("EARLY", "555", "777")], guild=None)

    assert view.children[0].url.endswith("/555/777")


def test_committed_slot_without_a_card_links_to_the_thread_itself():
    view = PodPollView([_committed("EARLY", "555", None)], guild=None)

    assert view.children[0].url.endswith("/555")


def _committed_named(thread_name, card_channel_id, card_message_id, thread_id="555", thread_message_id="777"):
    return LauncherSlot(
        named_bucket_key("EARLY", LATEST), committed=True, status=STATUS_FIRED, count=1, slot_time=None,
        names=["p"], thread_id=thread_id, signal_id=None, thread_message_id=thread_message_id,
        card_message_id=card_message_id, card_channel_id=card_channel_id, thread_name=thread_name,
        set_code=LATEST,
    )


def test_committed_card_link_targets_the_coordination_card_by_name():
    name = "MSH Jul 21 Early Pod"
    slot = _committed_named(name, "111", "222")

    link = _committed_card_link(None, slot)

    assert link == f"[__**{name}**__](https://discord.com/channels/@me/111/222)"


def test_committed_card_link_falls_back_to_the_thread_without_a_card():
    name = "MSH Jul 21 Early Pod"
    slot = _committed_named(name, None, None)

    link = _committed_card_link(None, slot)

    assert link == f"[__**{name}**__](https://discord.com/channels/@me/555/777)"


def test_committed_card_link_is_none_without_a_thread_name():
    slot = _committed_named(None, "111", "222")

    assert _committed_card_link(None, slot) is None


def test_reminder_view_confirms_yes_or_no_and_opens_format_preference():
    view = build_reminder_view("EVT9")

    custom_ids = [child.custom_id for child in view.children]
    assert custom_ids == ["podreminderrsvp:yes:EVT9", "podreminderrsvp:no:EVT9", "podremindfmt:EVT9"]


def test_format_locked_reminder_view_drops_format_preference():
    view = build_reminder_view("EVT9", format_locked=True)

    custom_ids = [child.custom_id for child in view.children]
    assert custom_ids == ["podreminderrsvp:yes:EVT9", "podreminderrsvp:no:EVT9"]


def test_open_pod_button_is_enabled_a_closed_one_disabled():
    view = PodPollView([_lazy("EARLY", STATUS_EXPIRED), _lazy("LATE", STATUS_OPEN)])

    disabled = {
        child.custom_id: child.item.disabled
        for child in view.children
        if child.custom_id.startswith("pod_poll:")
    }
    assert disabled == {
        f"pod_poll:{named_bucket_key('EARLY', LATEST)}": True,
        f"pod_poll:{named_bucket_key('LATE', LATEST)}": False,
    }


def test_a_slot_offering_two_formats_carries_one_button_per_pod():
    view = PodPollView([_lazy("EARLY", STATUS_OPEN), _lazy("EARLY", STATUS_OPEN, set_code="PEASANT")])

    assert [child.custom_id for child in view.children] == [
        f"pod_poll:{named_bucket_key('EARLY', LATEST)}",
        f"pod_poll:{named_bucket_key('EARLY', 'PEASANT')}",
    ]


def test_a_pod_that_started_drafting_carries_no_button():
    drafting = replace(_committed("EARLY", "555", "777"), locked=True)

    view = PodPollView([drafting])

    assert view.children == []


@pytest.mark.parametrize(
    "status, slot_hour, expected",
    [
        (STATUS_OPEN, 10, STATUS_EXPIRED),
        (STATUS_OPEN, 20, STATUS_OPEN),
        (STATUS_FIRED, 10, STATUS_FIRED),
    ],
)
def test_lazy_status_closes_only_a_passed_open_slot(status, slot_hour, expected):
    slot_time = datetime(2026, 7, 18, slot_hour, 0, tzinfo=timezone.utc)
    now = datetime(2026, 7, 18, 15, 0, tzinfo=timezone.utc)

    assert _lazy_status(status, slot_time, now) == expected


def test_preset_slot_time_uses_today_when_slot_is_ahead():
    early = _preset_slot_time("EARLY", BEFORE_EARLY)

    assert early.astimezone(timezone.utc).date() == BEFORE_EARLY.date()
    assert early > BEFORE_EARLY


def test_preset_slot_time_rolls_to_tomorrow_once_slot_has_passed():
    late = _preset_slot_time("LATE", AFTER_LATE)

    assert late > AFTER_LATE
    assert (late - AFTER_LATE) < timedelta(days=1, hours=18)


def test_when_options_default_right_now_when_unscheduled():
    options = _when_options(None, BEFORE_EARLY)

    defaulted = [o for o in options if o.default]
    assert [o.value for o in defaulted] == ["now"]
    assert options[-1].value == WRITE_IN_VALUE
    assert "Schedule for later" in options[-1].label


def test_when_options_defaults_the_selected_preset():
    late = _preset_slot_time("LATE", BEFORE_EARLY)

    options = _when_options(late, BEFORE_EARLY)

    defaulted = [o for o in options if o.default]
    assert [o.value for o in defaulted] == ["LATE"]
    assert options[-1].value == WRITE_IN_VALUE
    assert "Schedule for later" in options[-1].label


def test_when_options_shows_custom_time_as_its_own_defaulted_option():
    custom = datetime(2026, 7, 18, 21, 0, tzinfo=timezone.utc)

    options = _when_options(custom, BEFORE_EARLY)

    defaulted = [o for o in options if o.default]
    assert len(defaulted) == 1
    assert defaulted[0].value == WRITE_IN_VALUE
    assert "Schedule for later" not in defaulted[0].label


def test_seed_options_from_rankings_adds_each_ranked_set():
    from bot.services.pod_draft_manager import _seed_options_from_rankings

    options = ["MSH", "FLASH", "NEO"]
    rankings = (("1", ("NEO", "IKO")), ("2", ("NEO", "MH3")))

    _seed_options_from_rankings(options, rankings)

    assert options == ["MSH", "FLASH", "NEO", "IKO", "MH3"]


def test_seed_options_from_rankings_respects_the_option_cap():
    from bot.services import pod_format_poll
    from bot.services.pod_draft_manager import _seed_options_from_rankings

    options = [f"S{i}" for i in range(pod_format_poll.MAX_ROWED_OPTIONS)]
    rankings = (("1", ("NEW1", "NEW2")),)

    _seed_options_from_rankings(options, rankings)

    assert len(options) == pod_format_poll.MAX_ROWED_OPTIONS
    assert "NEW1" not in options


def _committed_championship(thread_id="555", card_message_id="900"):
    return LauncherSlot(
        "AFTERNOON", committed=True, status=STATUS_FIRED, count=8, slot_time=None,
        names=["a", "b"], thread_id=thread_id, signal_id=None, thread_message_id="777",
        card_message_id=card_message_id, championship=True,
    )


def test_championship_slot_is_a_link_not_an_rsvp_toggle():
    view = PodPollView([_committed_championship()], guild=None)

    custom_ids = [child.custom_id for child in view.children if getattr(child, "custom_id", None)]
    link_buttons = [child for child in view.children if getattr(child, "url", None)]

    assert not any(cid.startswith("pod_slot_rsvp") for cid in custom_ids)
    assert link_buttons and link_buttons[0].url.endswith("/555/777")
