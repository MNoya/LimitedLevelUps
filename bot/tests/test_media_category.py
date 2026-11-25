from bot.media_sets import EVERGREEN, by_code
from bot.services.media_sync import classify_category

UNMATCHED_TITLE = "How To Beat The Aggro Menace"


def test_unmatched_podcast_with_a_set_falls_back_to_metagame():
    star_trek = by_code("TRK")

    category = classify_category(["Limited Level-Ups"], UNMATCHED_TITLE, "episode", star_trek)

    assert category == "Metagame"


def test_unmatched_podcast_without_a_set_falls_back_to_evergreen():
    category = classify_category(["Limited Level-Ups"], UNMATCHED_TITLE, "episode", EVERGREEN)

    assert category == "Evergreen"


def test_evergreen_playlist_wins_over_the_set_fallback():
    star_trek = by_code("TRK")

    category = classify_category(["Limited Level Ups Evergreen Episodes"], UNMATCHED_TITLE, "episode", star_trek)

    assert category == "Evergreen"
