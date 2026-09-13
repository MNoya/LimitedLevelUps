"""Read-only YouTube Data API client for the channel's uploads and curated playlists.

The channel's playlists are the human-maintained taxonomy: per-set playlists give an
episode its format, "… Set Review" / "Draft …" / "Evergreen" playlists give its category.
``fetch_videos`` returns every upload plus any video Alex featured in a curated playlist
(including the occasional guest/other-channel video), each annotated with the playlists it
belongs to, so the media sync can derive both without guessing from clickbait titles.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import requests

log = logging.getLogger(__name__)

YOUTUBE_API = "https://www.googleapis.com/youtube/v3"
_SKIP_TITLES = {"Private video", "Deleted video"}


@dataclass
class YouTubeVideo:
    id: str
    title: str
    published_at: str
    description: str
    thumbnail: str
    duration_seconds: int
    playlists: list[str] = field(default_factory=list)


class YouTubeClient:
    def __init__(self, api_key: str, channel_handle: str, session: requests.Session | None = None, timeout_s: int = 20):
        self.api_key = api_key
        self.channel_handle = channel_handle
        self.session = session or requests.Session()
        self.timeout_s = timeout_s

    def fetch_videos(self) -> list[YouTubeVideo]:
        channel_id, uploads_playlist = self._resolve_channel()
        upload_ids = self._playlist_video_ids(uploads_playlist)

        membership: dict[str, set[str]] = {}
        for playlist_id, title in self._channel_playlists(channel_id):
            for video_id in self._playlist_video_ids(playlist_id):
                membership.setdefault(video_id, set()).add(title)

        all_ids = list(dict.fromkeys([*upload_ids, *membership]))
        details = self._video_details(all_ids)

        videos: list[YouTubeVideo] = []
        for video_id in all_ids:
            detail = details.get(video_id)
            if detail is None:
                continue
            videos.append(self._to_video(video_id, detail, sorted(membership.get(video_id, set()))))
        return videos

    def fetch_recent_uploads(self, limit: int = 8) -> list[YouTubeVideo]:
        """Newest uploads only, skipping the curated-playlist crawl. Playlists stay empty so categorization
        falls back to the title; the daily full sync reconciles them."""
        _, uploads_playlist = self._resolve_channel()
        recent_ids = self._recent_upload_ids(uploads_playlist, limit)
        details = self._video_details(recent_ids)
        videos: list[YouTubeVideo] = []
        for video_id in recent_ids:
            detail = details.get(video_id)
            if detail is None:
                continue
            videos.append(self._to_video(video_id, detail, []))
        return videos

    @staticmethod
    def _to_video(video_id: str, detail: dict, playlists: list[str]) -> YouTubeVideo:
        return YouTubeVideo(
            id=video_id,
            title=detail["title"],
            published_at=detail["published_at"],
            description=detail["description"],
            thumbnail=detail["thumbnail"],
            duration_seconds=detail["duration_seconds"],
            playlists=playlists,
        )

    def _get(self, path: str, params: dict) -> dict:
        params = {**params, "key": self.api_key}
        resp = self.session.get(f"{YOUTUBE_API}/{path}", params=params, timeout=self.timeout_s)
        try:
            resp.raise_for_status()
        except requests.HTTPError as e:
            raise requests.HTTPError(f"{e} — {_api_error_detail(resp)}", response=resp) from None
        return resp.json()

    def _resolve_channel(self) -> tuple[str, str]:
        body = self._get("channels", {"part": "contentDetails", "forHandle": self.channel_handle})
        items = body.get("items") or []
        if not items:
            raise RuntimeError(f"YouTube channel not found for handle {self.channel_handle}")
        channel = items[0]
        uploads = channel.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
        if not uploads:
            raise RuntimeError("Could not resolve uploads playlist")
        return channel["id"], uploads

    def _channel_playlists(self, channel_id: str) -> list[tuple[str, str]]:
        playlists: list[tuple[str, str]] = []
        seen_pages: set[str] = set()
        page = ""
        while True:
            params = {"part": "snippet", "channelId": channel_id, "maxResults": 50}
            if page:
                params["pageToken"] = page
            body = self._get("playlists", params)
            for item in body.get("items", []):
                playlists.append((item["id"], item.get("snippet", {}).get("title", "")))
            seen_pages.add(page)
            page = body.get("nextPageToken", "")
            if not page or page in seen_pages:
                return playlists

    def _playlist_video_ids(self, playlist_id: str) -> list[str]:
        ids: list[str] = []
        seen_pages: set[str] = set()
        page = ""
        while True:
            params = {"part": "snippet", "playlistId": playlist_id, "maxResults": 50}
            if page:
                params["pageToken"] = page
            body = self._get("playlistItems", params)
            ids.extend(_video_ids_from_items(body))
            seen_pages.add(page)
            page = body.get("nextPageToken", "")
            if not page or page in seen_pages:
                return ids

    def _recent_upload_ids(self, playlist_id: str, limit: int) -> list[str]:
        body = self._get(
            "playlistItems", {"part": "snippet", "playlistId": playlist_id, "maxResults": min(limit, 50)}
        )
        return _video_ids_from_items(body)

    # videos.list carries the authoritative publish date (playlistItems reports the date a video
    # was *added* to a playlist, which is wrong for featured back-catalogue videos), plus the
    # duration, in one call.
    def _video_details(self, video_ids: list[str]) -> dict[str, dict]:
        details: dict[str, dict] = {}
        for start in range(0, len(video_ids), 50):
            chunk = video_ids[start : start + 50]
            body = self._get("videos", {"part": "snippet,contentDetails", "id": ",".join(chunk)})
            for item in body.get("items", []):
                snippet = item.get("snippet", {})
                title = snippet.get("title", "")
                if title in _SKIP_TITLES:
                    continue
                thumbs = snippet.get("thumbnails", {})
                best = thumbs.get("maxres") or thumbs.get("standard") or thumbs.get("high") or thumbs.get("default")
                details[item["id"]] = {
                    "title": title,
                    "published_at": snippet.get("publishedAt", ""),
                    "description": snippet.get("description", ""),
                    "thumbnail": (best or {}).get("url", ""),
                    "duration_seconds": _parse_iso_duration(item.get("contentDetails", {}).get("duration", "")),
                }
        return details


def _api_error_detail(resp: requests.Response) -> str:
    try:
        error = resp.json().get("error", {})
    except ValueError:
        return (resp.text or "")[:200]
    reasons = ", ".join(item.get("reason", "") for item in error.get("errors", []) if item.get("reason"))
    message = error.get("message", "")
    return f"{reasons}: {message}" if reasons else message or "no error detail"


def _video_ids_from_items(body: dict) -> list[str]:
    ids: list[str] = []
    for entry in body.get("items", []):
        video_id = entry.get("snippet", {}).get("resourceId", {}).get("videoId")
        if video_id:
            ids.append(video_id)
    return ids


def _parse_iso_duration(iso: str) -> int:
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not match:
        return 0
    hours, minutes, seconds = match.groups()
    return int(hours or 0) * 3600 + int(minutes or 0) * 60 + int(seconds or 0)
