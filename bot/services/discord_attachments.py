from __future__ import annotations

import json
import urllib.request

REFRESH_ENDPOINT = "https://discord.com/api/v10/attachments/refresh-urls"
USER_AGENT = "DiscordBot (https://limitedlevelups.com, 1.0)"


def refresh_attachment_urls(urls: list[str], token: str) -> dict[str, str]:
    refreshed: dict[str, str] = {}
    for start in range(0, len(urls), 50):
        chunk = urls[start : start + 50]
        req = urllib.request.Request(
            REFRESH_ENDPOINT,
            data=json.dumps({"attachment_urls": chunk}).encode(),
            headers={"Authorization": f"Bot {token}", "Content-Type": "application/json", "User-Agent": USER_AGENT},
            method="POST",
        )
        body = json.loads(urllib.request.urlopen(req).read())
        for row in body["refreshed_urls"]:
            refreshed[row["original"]] = row["refreshed"]
    return refreshed
