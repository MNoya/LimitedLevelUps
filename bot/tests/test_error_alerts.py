import logging

import discord

from bot.services import error_alerts


def _record_from_raise() -> logging.LogRecord:
    def deepest():
        raise RuntimeError("boom")

    try:
        deepest()
    except Exception as error:
        context = "SomeCard.SomeButton\nuser Finkel (1) in #welcome\ncustom_id some_button"
        return logging.getLogger("bot.interactions").makeRecord(
            "bot.interactions", logging.ERROR, __file__, 1, context, (),
            (type(error), error, error.__traceback__), extra={"alert_context": context},
        )


def test_crash_site_points_at_deepest_app_frame():
    record = _record_from_raise()

    site = error_alerts._crash_site(record)

    assert site.startswith("bot/tests/test_error_alerts.py:")
    assert site.endswith("deepest")


def test_detail_carries_context_and_exception_type():
    record = _record_from_raise()

    detail = error_alerts._compose_detail(record)

    assert "custom_id some_button" in detail
    assert "RuntimeError" in detail


def test_same_site_dedups_and_counts():
    handler = error_alerts.ErrorAlertHandler()

    handler.emit(_record_from_raise())
    handler.emit(_record_from_raise())
    due = handler.drain()

    assert len(due) == 1
    _, _, count = due[0]
    assert count == 2


def test_install_patches_both_view_roots():
    error_alerts._install_interaction_error_logging()

    assert discord.ui.View.on_error.__module__ == "bot.services.error_alerts"
    assert discord.ui.LayoutView.on_error.__module__ == "bot.services.error_alerts"
