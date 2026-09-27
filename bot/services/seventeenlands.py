"""Client and aggregation helpers for 17lands draft data.

Fetches use the data endpoint:
    GET https://www.17lands.com/user/data/{token}?start_date=YYYY-MM-DD
which returns ``{"drafts": [...]}``. The ``/user_history/{token}`` URL
mentioned in the spec is the human-facing page — not used here.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

import requests

from bot.scoring import supported_formats
from bot.sets import normalize_expansion

logger = logging.getLogger(__name__)

# Derived from the scoring buckets so adding a bucket auto-expands what gets fetched
SUPPORTED_FORMATS: tuple[str, ...] = supported_formats()

DEFAULT_BASE_URL = "https://www.17lands.com"

LCQ_DRAFT2_FORMAT = "LimitedChampionshipQualifier_Draft2"
QUALIFIER_DAY2_FORMAT = "Qualifier_D2_Sealed"
QUALIFIER_DAY2_FOUR_WIN_POLICY_START = date(2025, 5, 10)

_TOKEN_RE = re.compile(r"[a-f0-9]{32}")
_HEX_RUN_RE = re.compile(r"[a-f0-9]{6,}")
_URL_RE = re.compile(r"https?://", re.IGNORECASE)
_17LANDS_URL_RE = re.compile(r"17lands\.com", re.IGNORECASE)


def extract_token(value: str) -> str:
    """Accept either a raw 32-hex token or a 17lands URL containing one.

    Returns the lowercase token. Raises ValueError if no token can be parsed.
    """
    if not value or not isinstance(value, str):
        raise ValueError("token is empty")
    candidate = value.strip().lower()
    match = _TOKEN_RE.search(candidate)
    if not match:
        raise ValueError(f"could not extract a 17lands token from: {value!r}")
    return match.group(0)


def classify_token_reply(value: str | None) -> str:
    """Categorise why a reply failed extract_token, without leaking content.

    Returns a short label suitable for logging. Use this only when extract_token
    has already raised — callers shouldn't branch on the label, it's diagnostic.
    """
    if not value or not isinstance(value, str):
        return "empty"
    stripped = value.strip()
    if not stripped:
        return "empty"
    if len(stripped) > 2000:
        return "too_long"
    lower = stripped.lower()
    if _TOKEN_RE.search(lower):
        return "hex_present"
    is_17l = bool(_17LANDS_URL_RE.search(lower))
    is_url = bool(_URL_RE.search(lower))
    has_hex_run = bool(_HEX_RUN_RE.search(lower))
    if is_17l:
        return "17lands_url_no_token"
    if is_url:
        return "other_url"
    if has_hex_run:
        return "hex_but_wrong_length"
    return "text_only"


class MinIntervalLimiter:
    """Block ``wait()`` until at least ``min_interval_s`` has passed since the prior call.

    Time and sleep are injected so tests can drive the limiter deterministically.
    """

    def __init__(
        self,
        min_interval_s: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.min_interval_s = min_interval_s
        self._sleep = sleep
        self._clock = clock
        self._last_at: float | None = None

    def wait(self) -> None:
        now = self._clock()
        if self._last_at is not None and self.min_interval_s > 0:
            remaining = self.min_interval_s - (now - self._last_at)
            if remaining > 0:
                self._sleep(remaining)
                now = self._clock()
        self._last_at = now


class SeventeenLandsClient:
    """Thin client over the 17lands data endpoint.

    Optional file cache: when ``cache_dir`` is set, ``fetch_drafts`` will read
    cached JSON from ``<cache_dir>/<token>__<start_date>.json`` if present, and
    write each fresh response there. Bypasses both rate limiter and HTTP on
    cache hit. Useful for dev iteration where the upstream data hasn't moved.
    """

    def __init__(
        self,
        limiter: MinIntervalLimiter | None = None,
        session: requests.Session | None = None,
        timeout_s: float = 30.0,
        games_timeout_s: float = 60.0,
        games_retry_delay_s: float = 60.0,
        base_url: str = DEFAULT_BASE_URL,
        cache_dir: Path | str | None = None,
    ) -> None:
        self.limiter = limiter or MinIntervalLimiter()
        self.session = session or requests.Session()
        self.timeout_s = timeout_s
        self.games_timeout_s = games_timeout_s
        self.games_retry_delay_s = games_retry_delay_s
        self.base_url = base_url.rstrip("/")
        self.cache_dir = Path(cache_dir) if cache_dir else None

    def _data_url(self, token: str) -> str:
        return f"{self.base_url}/user/data/{token}"

    def _games_url(self, token: str) -> str:
        return f"{self.base_url}/data/user_game_list/{token}"

    def _cache_path(
        self,
        token: str,
        start_date: date | None,
        end_date: date | None,
        expansion: str | None,
    ) -> Path | None:
        if self.cache_dir is None:
            return None
        parts = [
            start_date.isoformat() if start_date else "all",
        ]
        if end_date is not None:
            parts.append(end_date.isoformat())
        if expansion is not None:
            parts.append(f"exp-{expansion}")
        return self.cache_dir / f"{token}__{'__'.join(parts)}.json"

    def fetch_drafts(
        self,
        token: str,
        start_date: date | None = None,
        end_date: date | None = None,
        expansion: str | None = None,
    ) -> list[dict]:
        """Return the list of draft events for a token.

        Args:
            token: 17lands user token.
            start_date: Earliest draft date to include (server-side filter).
            end_date: Latest draft date to include (server-side filter).
            expansion: Single expansion code to scope to (server-side filter). Excludes alchemy
                variants — fall back to the date window when alchemy drafts must come along.

        Raises:
            requests.HTTPError: Upstream returned non-2xx.
            ValueError: Response body was not valid JSON or missing 'drafts'.
        """
        cache_path = self._cache_path(token, start_date, end_date, expansion)
        if cache_path is not None and cache_path.exists():
            with cache_path.open("r", encoding="utf-8") as f:
                cached = json.load(f)
            return cached.get("drafts", []) or []

        params: dict[str, str] = {}
        if start_date is not None:
            params["start_date"] = start_date.isoformat()
        if end_date is not None:
            params["end_date"] = end_date.isoformat()
        if expansion is not None:
            params["expansion"] = expansion

        self.limiter.wait()
        resp = self.session.get(self._data_url(token), params=params, timeout=self.timeout_s)
        resp.raise_for_status()
        try:
            body = resp.json()
        except ValueError as e:
            raise ValueError(f"17lands response was not valid JSON: {e}") from e
        if not isinstance(body, dict) or "drafts" not in body:
            raise ValueError("17lands response missing 'drafts' key")

        if cache_path is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with cache_path.open("w", encoding="utf-8") as f:
                json.dump(body, f)

        return body["drafts"] or []

    def fetch_user_games(self, token: str, *, retries: int = 1) -> list[dict]:
        """Game history for replay capture. Heavy users have a large, uncached history and the endpoint
        is slow on a cold hit, so this uses a longer timeout than the interactive calls and retries
        once on timeout — but only after a delay, since a timed-out request keeps warming 17lands'
        cache server-side, so the retry lands on a ready response instead of timing out again."""
        for attempt in range(retries + 1):
            self.limiter.wait()
            try:
                resp = self.session.get(self._games_url(token), timeout=self.games_timeout_s)
            except requests.Timeout:
                logger.warning(
                    f"17lands user_game_list timeout (attempt {attempt + 1}/{retries + 1}) "
                    f"for token tail …{token[-4:]}"
                )
                if attempt < retries:
                    time.sleep(self.games_retry_delay_s)
                continue
            except requests.RequestException:
                logger.warning(f"17lands user_game_list network error for token tail …{token[-4:]}", exc_info=True)
                return []
            if resp.status_code != 200:
                logger.warning(f"17lands user_game_list non-200 ({resp.status_code}) for token tail …{token[-4:]}")
                return []
            try:
                body = resp.json()
            except ValueError:
                logger.warning(f"17lands user_game_list malformed JSON for token tail …{token[-4:]}")
                return []
            if isinstance(body, list):
                return body
            if isinstance(body, dict):
                games = body.get("games")
                if isinstance(games, list):
                    return games
            return []
        logger.warning(f"17lands user_game_list timed out after {retries + 1} attempts for token tail …{token[-4:]}")
        return []

    def fetch_card_ratings(
        self,
        expansion: str,
        event_type: str = "PremierDraft",
        time_period: str = "ALL_TIME",
        colors: str | None = None,
    ) -> list[dict]:
        """Return card rating records from the public 17lands card ratings endpoint.

        No token required. Raises requests.HTTPError on non-2xx, ValueError on
        malformed response.
        """
        url = f"{self.base_url}/api/card_data"
        params = {"expansion": expansion, "event_type": event_type, "time_period": time_period}
        if colors:
            params["colors"] = colors
        self.limiter.wait()
        resp = self.session.get(url, params=params, timeout=self.timeout_s)
        resp.raise_for_status()
        try:
            body = resp.json()
        except ValueError as e:
            raise ValueError(f"17lands card_ratings response was not valid JSON: {e}") from e
        if not isinstance(body, dict) or not isinstance(body.get("data"), list):
            raise ValueError(f"17lands card_ratings response missing list 'data' field: {type(body)}")
        return body["data"]

    def verify_token(self, token: str) -> bool:
        """Return True if 17lands recognizes the token.

        A new user with no events still returns ``{"drafts": []}`` — that
        counts as recognized. Any non-200, network failure, or malformed
        response means the token is treated as invalid.
        """
        self.limiter.wait()
        try:
            resp = self.session.get(self._data_url(token), timeout=self.timeout_s)
        except requests.RequestException:
            logger.warning("17lands verify failed with network error", exc_info=True)
            return False
        if resp.status_code != 200:
            return False
        try:
            body = resp.json()
        except ValueError:
            return False
        return isinstance(body, dict) and "drafts" in body


def _parse_17lands_ts(value: str | None) -> datetime | None:
    """17lands serves timestamps as ``YYYY-MM-DD HH:MM[:SS]`` UTC strings (no tz).

    Returns a timezone-aware UTC datetime so it lands cleanly in our
    ``DateTime(timezone=True)`` columns and renders correctly via discord.py.
    """
    if not value or not isinstance(value, str):
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def event_is_trophy(draft: dict) -> bool:
    """Whether a 17lands draft is a trophy run.

    Normally a trophy is ``event_wins`` truthy, but 17lands ships ``event_wins=0``
    for two event types so the win count stands in:
      - LCQ Draft 2 always (upstream bug).
      - Qualifier Weekend Day 2 from 2025-05-10 on, when WOTC dropped the bar to
        4 wins to qualify (https://magic.wizards.com/en/news/mtg-arena/qualifier-weekend-event-updates).
        Earlier Day 2 runs keep the old win-6 bar and report ``event_wins`` correctly.
    """
    fmt = draft.get("format")
    wins = int(draft.get("wins") or 0)
    if fmt == LCQ_DRAFT2_FORMAT:
        return wins == 6
    if fmt == QUALIFIER_DAY2_FORMAT:
        started_at = _parse_17lands_ts(draft.get("first_event_server_time"))
        if started_at and started_at.date() >= QUALIFIER_DAY2_FOUR_WIN_POLICY_START:
            return wins >= 4
    return bool(draft.get("event_wins"))


def extract_event_row(draft: dict) -> dict | None:
    """Build a ``DraftEvent``-shaped row dict from one 17lands draft. No filtering.

    Returns ``None`` if the draft lacks an event id (defensive — 17lands has
    always provided one in observed responses). Otherwise returns every field
    the model needs except ``player_id`` and ``set_id``, plus the raw ``account``
    string; the caller resolves those into ids.

    Format/set/expansion are kept raw (other than ``normalize_expansion``) so
    unrecognized values still persist — the leaderboard score layer decides
    what counts, the storage layer keeps everything.
    """
    event_id = draft.get("id")
    if not event_id:
        return None
    fmt = draft.get("format")
    if not fmt:
        return None
    expansion = normalize_expansion(draft.get("expansion") or "")
    wins = int(draft.get("wins") or 0)
    return {
        "seventeenlands_event_id": event_id,
        "format": fmt,
        "expansion": expansion,
        "wins": wins,
        "losses": int(draft.get("losses") or 0),
        "is_trophy": event_is_trophy(draft),
        "colors": draft.get("colors") or None,
        "account": draft.get("account") or None,
        "start_rank": draft.get("start_rank") or None,
        "end_rank": draft.get("end_rank") or None,
        "started_at": _parse_17lands_ts(draft.get("first_event_server_time")),
        "finished_at": _parse_17lands_ts(draft.get("last_event_server_time")),
    }


