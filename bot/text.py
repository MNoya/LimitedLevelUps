from __future__ import annotations

import re


_EMOJI_BASE = (
    r"[\U0001F1E6-\U0001F1FF\U0001F300-\U0001F5FF\U0001F600-\U0001F64F"
    r"\U0001F680-\U0001F6FF\U0001F700-\U0001F77F\U0001F780-\U0001F7FF"
    r"\U0001F800-\U0001F8FF\U0001F900-\U0001F9FF\U0001FA00-\U0001FAFF"
    r"\U00002300-\U000023FF\U00002600-\U000026FF\U00002700-\U000027BF"
    r"\U00002B00-\U00002BFF\U00002190-\U000021FF"
    r"\U0001F004\U0001F0CF\U00002122\U000000A9\U000000AE"
    r"\U00003030\U0000303D\U00003297\U00003299]"
)
_EMOJI_TRAILER = r"[\U0001F3FB-\U0001F3FF️⃣]"
_EMOJI_CLUSTER = rf"(?:<a?:\w+:\d+>|{_EMOJI_BASE}{_EMOJI_TRAILER}*(?:‍{_EMOJI_BASE}{_EMOJI_TRAILER}*)*)"

_LEADING_EMOJI = re.compile(rf"^\s*{_EMOJI_CLUSTER}")
_TRAILING_EMOJI = re.compile(rf"{_EMOJI_CLUSTER}\s*$")
_ANY_EMOJI = re.compile(_EMOJI_CLUSTER)
_COLLAPSE_WS = re.compile(r"\s{2,}")


def link_with_emoji(text: str, url: str) -> str:
    """Markdown link with emoji moved out of the label: leading emoji before it, trailing after, interior dropped.

    Discord mis-renders a link whose `[label]` carries an emoji anywhere, so the label must be emoji-free.
    """
    leading, core, trailing = partition_emoji(text)
    link = f"[{core}]({url})"
    if leading:
        link = f"{leading} {link}"
    if trailing:
        link = f"{link} {trailing}"
    return link


def partition_emoji(text: str) -> tuple[str, str, str]:
    """Split `text` into (leading emoji, emoji-free core, trailing emoji); interior emoji are dropped from core."""
    rest = text.strip()
    leading_parts: list[str] = []
    while True:
        match = _LEADING_EMOJI.match(rest)
        if match is None:
            break
        leading_parts.append(match.group(0).strip())
        rest = rest[match.end():].lstrip()

    trailing_parts: list[str] = []
    while True:
        match = _TRAILING_EMOJI.search(rest)
        if match is None:
            break
        trailing_parts.insert(0, match.group(0).strip())
        rest = rest[: match.start()].rstrip()

    core = _COLLAPSE_WS.sub(" ", _ANY_EMOJI.sub("", rest)).strip()
    return " ".join(leading_parts), core, " ".join(trailing_parts)
