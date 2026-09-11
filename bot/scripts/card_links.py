"""Detect Magic card names in transcript text by fuzzy matching a candidate card list"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

RATIO_STRONG = 0.90
RATIO_ANCHORED = 0.80
WORD = re.compile(r"[0-9A-Za-zÀ-ÿ']+")
BASIC_LANDS = {"plains", "island", "swamp", "mountain", "forest", "wastes"}
STOPWORDS = {
    "the", "a", "an", "of", "and", "or", "to", "in", "on", "at", "for", "with", "from", "by",
    "as", "is", "it", "his", "her", "our", "your", "this", "that", "one", "two",
}


def _normalize(text: str) -> str:
    stripped = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    stripped = stripped.replace("'", "")
    return re.sub(r"[^a-z0-9 ]", " ", stripped.lower()).strip()


def tag_text(text: str, card_names: list[str]) -> tuple[str, list[dict]]:
    tokens = [(m.group(0), m.start(), m.end()) for m in WORD.finditer(text)]
    normed_cards = []
    for name in card_names:
        normed = _normalize(name)
        if normed in BASIC_LANDS:
            continue
        normed_cards.append((name, normed, len(normed.split()), _content(normed)))
    matches: list[tuple[int, int, str, float]] = []
    for start_idx in range(len(tokens)):
        for name, normed_name, token_count, content in normed_cards:
            end_idx = start_idx + token_count
            if end_idx > len(tokens):
                continue
            window = _normalize(" ".join(t[0] for t in tokens[start_idx:end_idx]))
            if not (content & _content(window)):
                continue
            score = _score(window, normed_name, token_count)
            if score is None:
                continue
            matches.append((tokens[start_idx][1], tokens[end_idx - 1][2], name, score))
    return _apply(text, _resolve_overlaps(matches))


def _content(normed: str) -> set[str]:
    return {token for token in normed.split() if len(token) >= 4 and token not in STOPWORDS}


def _score(window: str, card: str, token_count: int) -> float | None:
    if token_count == 1:
        if len(card) >= 5 and window == card:
            return 1.0
        return None
    ratio = SequenceMatcher(None, window, card).ratio()
    if ratio >= RATIO_STRONG:
        return ratio
    if ratio >= RATIO_ANCHORED and _mishearing(window, card):
        return ratio
    return None


def _mishearing(window: str, card: str) -> bool:
    anchored = False
    for window_word, card_word in zip(window.split(), card.split()):
        if window_word == card_word:
            if len(window_word) >= 5 and window_word not in STOPWORDS:
                anchored = True
        elif SequenceMatcher(None, window_word, card_word).ratio() < 0.5:
            return False
    return anchored


def _resolve_overlaps(matches: list[tuple[int, int, str, float]]) -> list[tuple[int, int, str, float]]:
    matches.sort(key=lambda m: (m[3], m[1] - m[0]), reverse=True)
    chosen: list[tuple[int, int, str, float]] = []
    for match in matches:
        char_start, char_end, _, _ = match
        if any(char_start < c_end and char_end > c_start for c_start, c_end, _, _ in chosen):
            continue
        chosen.append(match)
    chosen.sort()
    return chosen


def _apply(text: str, spans: list[tuple[int, int, str, float]]) -> tuple[str, list[dict]]:
    corrected = text
    for char_start, char_end, name, score in reversed(spans):
        corrected = corrected[:char_start] + name + corrected[char_end:]
    cards: list[dict] = []
    for char_start, char_end, name, score in spans:
        card = {"name": name}
        if card not in cards:
            cards.append(card)
    return corrected, cards
