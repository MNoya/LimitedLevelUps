
import pytest
import requests
import responses

from bot.services.seventeenlands import (
    DEFAULT_BASE_URL,
    MinIntervalLimiter,
    SeventeenLandsClient,
    classify_token_reply,
    extract_event_row,
    extract_token,
)


VALID_TOKEN = "10c0f8918a2b4fa7b230448caee0b2ca"


# ---------------------------------------------------------------------------
# extract_token
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        VALID_TOKEN,
        f"  {VALID_TOKEN}  ",
        VALID_TOKEN.upper(),
        f"https://www.17lands.com/user_history/{VALID_TOKEN}",
        f"https://www.17lands.com/user/data/{VALID_TOKEN}?start_date=2026-01-20",
        f"http://17lands.com/user_history/{VALID_TOKEN}/",
    ],
)
def test_extract_token_accepts_valid_inputs(raw):
    assert extract_token(raw) == VALID_TOKEN


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not-a-token",
        "https://www.17lands.com/user_history/short",
        "g" * 32,  # right length, wrong charset
    ],
)
def test_extract_token_rejects_invalid_inputs(raw):
    with pytest.raises(ValueError):
        extract_token(raw)


def test_extract_token_handles_none():
    with pytest.raises(ValueError):
        extract_token(None)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("", "empty"),
        ("   ", "empty"),
        (None, "empty"),
        ("x" * 2001, "too_long"),
        (VALID_TOKEN, "hex_present"),
        ("https://17lands.com/history/events", "17lands_url_no_token"),
        ("http://www.17lands.com/user_history/short", "17lands_url_no_token"),
        ("https://example.com/foo", "other_url"),
        ("abc123def", "hex_but_wrong_length"),
        ("just text reply", "text_only"),
    ],
)
def test_classify_token_reply(raw, expected):
    assert classify_token_reply(raw) == expected


# ---------------------------------------------------------------------------
# MinIntervalLimiter
# ---------------------------------------------------------------------------


class FakeClock:
    def __init__(self, start: float = 1000.0):
        self.now = start
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_first_wait_does_not_sleep():
    clk = FakeClock()
    limiter = MinIntervalLimiter(min_interval_s=1.0, sleep=clk.sleep, clock=clk.time)

    limiter.wait()

    assert clk.sleeps == []


def test_second_wait_within_interval_sleeps_remainder():
    clk = FakeClock()
    limiter = MinIntervalLimiter(min_interval_s=1.0, sleep=clk.sleep, clock=clk.time)

    limiter.wait()
    clk.now += 0.3  # only 0.3s passed
    limiter.wait()

    assert clk.sleeps == [pytest.approx(0.7)]


def test_second_wait_after_interval_does_not_sleep():
    clk = FakeClock()
    limiter = MinIntervalLimiter(min_interval_s=1.0, sleep=clk.sleep, clock=clk.time)

    limiter.wait()
    clk.now += 5.0
    limiter.wait()

    assert clk.sleeps == []


def test_zero_interval_never_sleeps():
    clk = FakeClock()
    limiter = MinIntervalLimiter(min_interval_s=0, sleep=clk.sleep, clock=clk.time)

    for _ in range(5):
        limiter.wait()

    assert clk.sleeps == []


# ---------------------------------------------------------------------------
# SeventeenLandsClient
# ---------------------------------------------------------------------------


def _client() -> SeventeenLandsClient:
    return SeventeenLandsClient(limiter=MinIntervalLimiter(min_interval_s=0))


@responses.activate
def test_fetch_drafts_returns_drafts_list():
    drafts = [{"format": "PremierDraft", "wins": 7, "losses": 2}]
    responses.add(
        responses.GET,
        f"{DEFAULT_BASE_URL}/user/data/{VALID_TOKEN}",
        json={"drafts": drafts},
        status=200,
    )

    result = _client().fetch_drafts(VALID_TOKEN)

    assert result == drafts


@responses.activate
def test_fetch_drafts_raises_on_http_error():
    responses.add(
        responses.GET,
        f"{DEFAULT_BASE_URL}/user/data/{VALID_TOKEN}",
        status=500,
    )

    with pytest.raises(requests.HTTPError):
        _client().fetch_drafts(VALID_TOKEN)


@responses.activate
def test_fetch_drafts_raises_on_missing_drafts_key():
    responses.add(
        responses.GET,
        f"{DEFAULT_BASE_URL}/user/data/{VALID_TOKEN}",
        json={"oops": "bad shape"},
        status=200,
    )

    with pytest.raises(ValueError):
        _client().fetch_drafts(VALID_TOKEN)


@responses.activate
def test_fetch_drafts_handles_null_drafts():
    responses.add(
        responses.GET,
        f"{DEFAULT_BASE_URL}/user/data/{VALID_TOKEN}",
        json={"drafts": None},
        status=200,
    )

    assert _client().fetch_drafts(VALID_TOKEN) == []


@responses.activate
def test_fetch_card_ratings_defaults_to_all_time():
    responses.add(
        responses.GET,
        f"{DEFAULT_BASE_URL}/api/card_data",
        json={"copyright": "(c) 17Lands", "notes": "", "data": [{"name": "Bolt", "ever_drawn_win_rate": 0.55}]},
        status=200,
    )

    cards = _client().fetch_card_ratings("MSH")

    request = responses.calls[0].request
    assert "event_type=PremierDraft" in request.url
    assert "time_period=ALL_TIME" in request.url
    assert cards == [{"name": "Bolt", "ever_drawn_win_rate": 0.55}]


@responses.activate
def test_fetch_card_ratings_forwards_time_period():
    responses.add(
        responses.GET,
        f"{DEFAULT_BASE_URL}/api/card_data",
        json={"copyright": "(c) 17Lands", "notes": "", "data": [{"name": "Bolt", "ever_drawn_win_rate": 0.55}]},
        status=200,
    )

    _client().fetch_card_ratings("MSH", time_period="LAST_TWO_WEEKS")

    request = responses.calls[0].request
    assert "time_period=LAST_TWO_WEEKS" in request.url


@responses.activate
def test_fetch_card_ratings_rejects_response_without_data_field():
    responses.add(
        responses.GET,
        f"{DEFAULT_BASE_URL}/api/card_data",
        json=[{"name": "Bolt"}],
        status=200,
    )

    with pytest.raises(ValueError, match="missing list 'data' field"):
        _client().fetch_card_ratings("MSH")


@responses.activate
def test_verify_token_true_for_200_with_drafts_key():
    responses.add(
        responses.GET,
        f"{DEFAULT_BASE_URL}/user/data/{VALID_TOKEN}",
        json={"drafts": []},
        status=200,
    )

    assert _client().verify_token(VALID_TOKEN) is True


@responses.activate
def test_verify_token_false_for_404():
    responses.add(
        responses.GET,
        f"{DEFAULT_BASE_URL}/user/data/{VALID_TOKEN}",
        status=404,
    )

    assert _client().verify_token(VALID_TOKEN) is False


@responses.activate
def test_verify_token_false_for_malformed_json():
    responses.add(
        responses.GET,
        f"{DEFAULT_BASE_URL}/user/data/{VALID_TOKEN}",
        body="not json",
        status=200,
        content_type="text/html",
    )

    assert _client().verify_token(VALID_TOKEN) is False


@responses.activate
def test_verify_token_false_on_network_error():
    responses.add(
        responses.GET,
        f"{DEFAULT_BASE_URL}/user/data/{VALID_TOKEN}",
        body=requests.ConnectionError("boom"),
    )

    assert _client().verify_token(VALID_TOKEN) is False


@responses.activate
def test_fetch_user_games_returns_list():
    games = [{"game_id": "g1", "event_name": "DirectGameLimited"}]
    responses.add(
        responses.GET,
        f"{DEFAULT_BASE_URL}/data/user_game_list/{VALID_TOKEN}",
        json=games,
        status=200,
    )

    assert _client().fetch_user_games(VALID_TOKEN) == games


def _games_client() -> SeventeenLandsClient:
    return SeventeenLandsClient(limiter=MinIntervalLimiter(min_interval_s=0), games_retry_delay_s=0)


@responses.activate
def test_fetch_user_games_retries_after_timeout():
    url = f"{DEFAULT_BASE_URL}/data/user_game_list/{VALID_TOKEN}"
    games = [{"game_id": "g1"}]
    responses.add(responses.GET, url, body=requests.Timeout("slow first hit"))
    responses.add(responses.GET, url, json=games, status=200)

    assert _games_client().fetch_user_games(VALID_TOKEN) == games


@responses.activate
def test_fetch_user_games_empty_when_timeout_exhausts_retries():
    responses.add(
        responses.GET,
        f"{DEFAULT_BASE_URL}/data/user_game_list/{VALID_TOKEN}",
        body=requests.Timeout("always slow"),
    )

    assert _games_client().fetch_user_games(VALID_TOKEN, retries=1) == []


def test_client_invokes_limiter_once_per_call():
    calls = {"n": 0}

    class CountingLimiter:
        def wait(self):
            calls["n"] += 1

    client = SeventeenLandsClient(limiter=CountingLimiter())  # type: ignore[arg-type]
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            f"{DEFAULT_BASE_URL}/user/data/{VALID_TOKEN}",
            json={"drafts": []},
            status=200,
        )
        rsps.add(
            responses.GET,
            f"{DEFAULT_BASE_URL}/user/data/{VALID_TOKEN}",
            json={"drafts": []},
            status=200,
        )
        client.fetch_drafts(VALID_TOKEN)
        client.verify_token(VALID_TOKEN)

    assert calls["n"] == 2


# ---------------------------------------------------------------------------
# extract_event_row
# ---------------------------------------------------------------------------


def _draft(**overrides):
    base = {
        "id": "abc123",
        "format": "PremierDraft",
        "expansion": "SOS",
        "wins": 5,
        "losses": 3,
        "event_wins": 0,
        "colors": "WB",
        "start_rank": "Gold-3",
        "end_rank": "Platinum-4",
        "first_event_server_time": "2026-04-28 23:16:43",
        "last_event_server_time": "2026-04-28 23:39:04",
    }
    base.update(overrides)
    return base


def test_extract_event_row_basic_fields():
    row = extract_event_row(_draft(id="abc"))
    assert row["seventeenlands_event_id"] == "abc"
    assert row["format"] == "PremierDraft"
    assert row["expansion"] == "SOS"
    assert row["wins"] == 5
    assert row["losses"] == 3


def test_extract_event_row_preserves_color_case_for_splash():
    """Lowercase letters in colors are splash markers — case must survive."""
    for colors in ("WB", "WBg", "WUBRG", "RGwub", "W"):
        assert extract_event_row(_draft(colors=colors))["colors"] == colors


def test_extract_event_row_handles_null_colors_and_ranks():
    row = extract_event_row(_draft(colors=None, start_rank=None, end_rank=None))
    assert row["colors"] is None
    assert row["start_rank"] is None
    assert row["end_rank"] is None


def test_extract_event_row_trophy_flag_from_event_wins():
    assert extract_event_row(_draft(event_wins=7))["is_trophy"] is True
    assert extract_event_row(_draft(event_wins=0))["is_trophy"] is False
    assert extract_event_row(_draft(event_wins=4))["is_trophy"] is True


def test_extract_event_row_lcq_draft_2_trophy_from_six_wins():
    lcq = dict(format="LimitedChampionshipQualifier_Draft2", event_wins=0)

    six_wins = extract_event_row(_draft(wins=6, losses=1, **lcq))
    five_wins = extract_event_row(_draft(wins=5, losses=2, **lcq))
    seven_wins = extract_event_row(_draft(wins=7, losses=0, **lcq))

    assert six_wins["is_trophy"] is True
    assert five_wins["is_trophy"] is False
    assert seven_wins["is_trophy"] is False


def test_extract_event_row_qualifier_day2_four_win_policy():
    qd2 = dict(format="Qualifier_D2_Sealed", event_wins=0)

    four_oh = extract_event_row(_draft(wins=4, losses=0, first_event_server_time="2026-05-17 14:04:36", **qd2))
    five_two = extract_event_row(_draft(wins=5, losses=2, first_event_server_time="2025-10-19 10:00:00", **qd2))
    three_two = extract_event_row(_draft(wins=3, losses=2, first_event_server_time="2026-05-17 14:04:36", **qd2))

    assert four_oh["is_trophy"] is True
    assert five_two["is_trophy"] is True
    assert three_two["is_trophy"] is False


def test_extract_event_row_qualifier_day2_keeps_old_win_six_bar_before_policy():
    qd2 = dict(format="Qualifier_D2_Sealed")

    old_four_win = extract_event_row(
        _draft(wins=4, losses=2, event_wins=0, first_event_server_time="2025-04-06 10:00:00", **qd2)
    )
    old_trophy = extract_event_row(
        _draft(wins=6, losses=1, event_wins=6, first_event_server_time="2024-05-12 10:00:00", **qd2)
    )

    assert old_four_win["is_trophy"] is False
    assert old_trophy["is_trophy"] is True


def test_extract_event_row_keeps_unknown_format():
    """Format is never filtered at extract; storage layer keeps everything."""
    row = extract_event_row(_draft(format="MidWeekSealed"))
    assert row["format"] == "MidWeekSealed"


@pytest.mark.parametrize("expansion, stored", [
    ("MAT", "MOM"),
    ("OM1", "SPM"),
    ("Cube - Powered", "Cube - Powered"),
    ("Cube - Planar", "Cube - Planar"),
    ("Cube", "Cube"),
])
def test_extract_event_row_normalizes_only_aliased_expansions(expansion, stored):
    """An aliased set's expansion becomes its code; a cube variant stays verbatim so its board
    stays separable from the other cubes sharing the CUBE set."""
    row = extract_event_row(_draft(expansion=expansion))
    assert row["expansion"] == stored


def test_extract_event_row_returns_none_without_id():
    assert extract_event_row(_draft(id=None)) is None
    assert extract_event_row(_draft(id="")) is None


def test_extract_event_row_returns_none_without_format():
    assert extract_event_row(_draft(format=None)) is None


def test_extract_event_row_parses_timestamps():
    row = extract_event_row(_draft(
        first_event_server_time="2026-04-28 23:16:43",
        last_event_server_time="2026-04-28 23:39:04",
    ))
    # 17lands serves UTC-naive strings; we tag them as UTC-aware on parse
    assert row["started_at"].isoformat() == "2026-04-28T23:16:43+00:00"
    assert row["finished_at"].isoformat() == "2026-04-28T23:39:04+00:00"


def test_extract_event_row_handles_minute_precision_timestamps():
    """Some 17lands timestamps come at minute precision (no seconds)."""
    row = extract_event_row(_draft(
        first_event_server_time="2026-04-28 23:16",
        last_event_server_time="2026-04-28 23:39",
    ))
    assert row["started_at"].isoformat() == "2026-04-28T23:16:00+00:00"
    assert row["finished_at"].isoformat() == "2026-04-28T23:39:00+00:00"


def test_extract_event_row_handles_missing_timestamps():
    row = extract_event_row(_draft(first_event_server_time=None, last_event_server_time=None))
    assert row["started_at"] is None
    assert row["finished_at"] is None
