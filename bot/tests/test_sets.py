from datetime import date, datetime, timezone

from bot.sets import SetSeed, prerelease_date_for, prereleased_sets


def test_prerelease_date_falls_back_to_the_friday_before_the_arena_release():
    recorded = SetSeed("HOB", "The Hobbit", date(2026, 8, 11), date(2026, 9, 28), prerelease_date=date(2026, 8, 7))
    derived = SetSeed("XXX", "Unrecorded", date(2026, 8, 11), date(2026, 9, 28))

    assert prerelease_date_for(recorded) == date(2026, 8, 7)
    assert prerelease_date_for(derived) == date(2026, 8, 7)


def test_a_set_becomes_selectable_at_midnight_et_on_its_prerelease_date():
    eve = datetime(2026, 8, 7, 3, 0, tzinfo=timezone.utc)
    prerelease_morning = datetime(2026, 8, 7, 5, 0, tzinfo=timezone.utc)

    assert "HOB" not in {seed.code for seed in prereleased_sets(eve)}
    assert prereleased_sets(prerelease_morning)[0].code == "HOB"
