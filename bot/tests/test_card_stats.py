from datetime import datetime, timedelta, timezone

import pytest

from bot.services.card_stats import build_card_stats_file, refresh_due


class FakeClient:
    def __init__(self, game_count: int = 1000) -> None:
        self.game_count = game_count
        self.calls: list[str | None] = []

    def fetch_card_ratings(self, expansion: str, colors: str | None = None) -> list[dict]:
        self.calls.append(colors)
        return [{"name": "Grizzly Bears", "game_count": self.game_count, "ever_drawn_game_count": 600,
                 "ever_drawn_win_rate": 0.55}]


@pytest.mark.parametrize(("set_code", "deck_calls"), [("HOB", 10), ("TDM", 20)])
def test_three_color_sets_add_trios(set_code: str, deck_calls: int) -> None:
    client = FakeClient()

    file = build_card_stats_file(client, set_code, None)

    assert client.calls[0] is None
    assert len(client.calls) == 1 + deck_calls
    assert len(file["cards"]["Grizzly Bears"]["pairs"]) == deck_calls


@pytest.mark.parametrize(("previous_games", "expected_calls"), [(1000, 1), (900, 11)])
def test_unchanged_game_counts_reuse_previous_decks(previous_games: int, expected_calls: int) -> None:
    previous = {"set": "HOB", "updatedAt": "x", "cards": {"Grizzly Bears": {"gp": previous_games, "pairs": {}}}}
    client = FakeClient(game_count=1000)

    build_card_stats_file(client, "HOB", previous)

    assert len(client.calls) == expected_calls


@pytest.mark.parametrize(
    ("days_since_start", "hours_since_update", "due"),
    [(10, 1, True), (40, 1, False), (40, 21, True)],
)
def test_refresh_daily_after_first_month(days_since_start: int, hours_since_update: int, due: bool) -> None:
    now = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
    previous = {"updatedAt": (now - timedelta(hours=hours_since_update)).isoformat()}

    result = refresh_due(now.date() - timedelta(days=days_since_start), previous, now)

    assert result is due
