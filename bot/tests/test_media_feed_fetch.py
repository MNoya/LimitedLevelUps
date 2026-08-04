import pytest
import requests

from bot.services import media_sync
from bot.services.media_sync import FEED_ATTEMPTS, FeedUnavailable, _fetch_podcast_items

FEED_XML = b"""<?xml version="1.0"?>
<rss xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"><channel>
  <item>
    <guid>pod-1</guid>
    <title>LLU #42: Format Address</title>
    <link>https://example.test/42</link>
    <pubDate>Tue, 16 Jun 2026 12:00:00 +0000</pubDate>
    <itunes:duration>1:02:03</itunes:duration>
    <enclosure url="https://example.test/42.mp3"/>
  </item>
</channel></rss>"""


class _Response:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        return None


@pytest.fixture(autouse=True)
def no_retry_delay(monkeypatch):
    monkeypatch.setattr(media_sync.time, "sleep", lambda _s: None)


def _feed_stub(outcomes):
    calls = []

    def get(url, timeout):
        outcome = outcomes[len(calls)]
        calls.append(url)
        if isinstance(outcome, Exception):
            raise outcome
        return _Response(outcome)

    return get, calls


def test_feed_fetch_retries_past_a_timeout(monkeypatch):
    get, calls = _feed_stub([requests.ReadTimeout("read timed out"), FEED_XML])
    monkeypatch.setattr(media_sync.requests, "get", get)

    items = _fetch_podcast_items("https://feeds.libsyn.test/llu")

    assert len(calls) == 2
    assert [i.number for i in items] == [42]


@pytest.mark.parametrize(
    "failure",
    [requests.ReadTimeout("read timed out"), requests.ConnectionError("reset"), None],
    ids=["timeout", "connection", "unparseable_body"],
)
def test_feed_fetch_raises_feed_unavailable_once_attempts_run_out(monkeypatch, failure):
    outcome = failure or b"<html><body>502 Bad Gateway"
    get, calls = _feed_stub([outcome] * FEED_ATTEMPTS)
    monkeypatch.setattr(media_sync.requests, "get", get)

    with pytest.raises(FeedUnavailable):
        _fetch_podcast_items("https://feeds.libsyn.test/llu")

    assert len(calls) == FEED_ATTEMPTS
