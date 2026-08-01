"""Round-table seating PNG — the ASCII octagon rendered as a monospace image.

Discord embed code blocks wrap too narrowly to hold the octagon, so we draw the exact same text art
into a PNG instead and set it as the embed image. Pillow-only, deterministic, no network; the mono font
is bundled so prod never depends on system fonts. Monospace matters — a proportional font would
misalign the art.
"""
from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
FONT_MONO = FONTS_DIR / "DejaVuSansMono.ttf"

SCALE = 1            # keep pixels 1:1 (crisp); enlarge via FONT_SIZE, not fractional scaling
FONT_SIZE = 12
ARROW_FONT_SIZE = 14  # arrows drawn larger than the labels for emphasis; they sit alone in their cells
PAD = 12            # vertical padding around the text block
PAD_X = 20     # horizontal (left/right) padding — a bit roomier than top/bottom
TEXT = (219, 222, 225)
BORDER = (94, 99, 108)  # square box outline, drawn (not ASCII) so it can't misalign
ARROWS = frozenset("→←↑↓↗↘↙↖")


def drop_unrenderable(text: str) -> str:
    """Strip characters the bundled mono font can't draw on the one-column grid — emoji and
    zero-width joiners in Discord names would otherwise render as tofu or skew the alignment."""
    font = _font(FONT_SIZE)
    mono_width = font.getlength("M")
    notdef = _glyph_mask(font, "\ufffe")
    return "".join(
        ch for ch in text
        if font.getlength(ch) == mono_width and _glyph_mask(font, ch) != notdef
    ).strip()


def render_octagon_png(text: str, label_colors: dict[str, tuple[int, int, int]] | None = None) -> bytes:
    """Render the monospace octagon `text` (already laid out, box included) to transparent PNG bytes.
    Labels render at FONT_SIZE; arrows are overlaid larger, centred on their cells, so emphasis doesn't
    disturb the grid (each arrow is surrounded by blanks in the layout). `label_colors` tints named
    labels wherever they appear, which is how a team draft paints each side's seats."""
    font = _font(FONT_SIZE)
    arrow_font = _font(ARROW_FONT_SIZE)
    lines = text.split("\n")
    char_w = font.getlength("M")
    ascent, descent = font.getmetrics()
    line_h = ascent + descent
    pad_x = round(PAD_X * SCALE)
    pad_y = round(PAD * SCALE)
    cols = max((len(line) for line in lines), default=0)
    width = round(char_w * cols) + pad_x * 2
    height = line_h * len(lines) + pad_y * 2
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    inset = round(2 * SCALE)
    draw.rectangle(
        [inset, inset, width - 1 - inset, height - 1 - inset],
        outline=BORDER, width=max(1, round(SCALE)),
    )
    for i, line in enumerate(lines):
        labels_only = "".join(" " if ch in ARROWS else ch for ch in line)
        for start, run, color in _colored_runs(labels_only, label_colors):
            draw.text((pad_x + start * char_w, pad_y + i * line_h), run, font=font, fill=color)
    for i, line in enumerate(lines):
        for j, ch in enumerate(line):
            if ch in ARROWS:
                cx = pad_x + (j + 0.5) * char_w
                cy = pad_y + (i + 0.5) * line_h
                draw.text((cx, cy), ch, font=arrow_font, fill=TEXT, anchor="mm")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def _colored_runs(
    line: str, label_colors: dict[str, tuple[int, int, int]] | None,
) -> list[tuple[int, str, tuple[int, int, int]]]:
    """Split one grid line into (start_column, text, color) runs. Monospace means a run can be drawn
    at its column offset and still land on the grid, so a tinted label costs no alignment."""
    if not label_colors:
        return [(0, line, TEXT)]
    colors: list[tuple[int, int, int]] = [TEXT] * len(line)
    claimed = [False] * len(line)
    # longest first, and never over a claimed span: a short name that is a substring of a longer one
    # ("mo" inside "melodious") must not steal the other seat's color
    for label in sorted(label_colors, key=len, reverse=True):
        start = line.find(label)
        while start != -1:
            span = range(start, start + len(label))
            if not any(claimed[column] for column in span):
                for column in span:
                    colors[column] = label_colors[label]
                    claimed[column] = True
            start = line.find(label, start + 1)
    runs: list[tuple[int, str, tuple[int, int, int]]] = []
    for column, char in enumerate(line):
        if runs and colors[column] == runs[-1][2] and column == runs[-1][0] + len(runs[-1][1]):
            runs[-1] = (runs[-1][0], runs[-1][1] + char, runs[-1][2])
        else:
            runs.append((column, char, colors[column]))
    return runs


def octagon_text(names: list[str]) -> str:
    """Round-table ring for an even pod (6, 8, or 10 seats), arrows tracing the seat order clockwise
    from seat 1. Box-less text art; `render_octagon_png` rasterizes it and draws the border, so it
    ships as an image. Two seats on top and bottom; the rest split into `s = (n-4)/2` side-row pairs
    (6 → 1, 8 → 2, 10 → 3). Width-driven: the right column is anchored `GAP` past the widest left
    label; top/bottom seats inset by `TAPER` for the polygon shape; horizontal arrows sit in the
    centre gap, clear of long names.
    """
    GAP = 4  # spacing between the left and right name columns
    TAPER = 2  # how far the top/bottom seats pull in from the vertical seats
    n = len(names)
    s = (n - 4) // 2  # side-row pairs
    right_side = list(range(2, 2 + s))           # seats 3..  down the right, top -> bottom
    left_side = list(range(n - 1, 3 + s, -1))    # seats ..N up the left, rendered top -> bottom
    bottom_left, bottom_right = 3 + s, 2 + s

    labels = [seat_label(name) for name in names]
    # the right column must clear GAP on both the side rows (flush to the edges) and the inset top/bottom
    # rows (which lose 2*TAPER of usable width)
    vertical = max(len(labels[i]) for i in left_side) + GAP + max(len(labels[i]) for i in right_side)
    horizontal = (max(len(labels[0]), len(labels[bottom_left])) + GAP
                  + max(len(labels[1]), len(labels[bottom_right])) + 2 * TAPER)
    right = max(vertical, horizontal)
    rows = [""] * (2 * s + 3)

    def place(r: int, c: int, text: str) -> None:
        line = rows[r].ljust(c)
        rows[r] = line[:c] + text + line[c + len(text):]

    def place_right(r: int, end: int, text: str) -> None:
        place(r, max(0, end - len(text)), text)

    r = 0
    place(r, TAPER, labels[0])
    place_right(r, right - TAPER, labels[1])
    top_row = r
    r += 1
    place(r, TAPER - 1, "↗")
    place_right(r, right - TAPER + 1, "↘")
    r += 1
    for k in range(s):
        place(r, 0, labels[left_side[k]])
        place_right(r, right, labels[right_side[k]])
        r += 1
        if k < s - 1:
            place(r, 0, "↑")
            place_right(r, right, "↓")
            r += 1
    place(r, TAPER - 1, "↖")
    place_right(r, right - TAPER + 1, "↙")
    r += 1
    place(r, TAPER, labels[bottom_left])
    place_right(r, right - TAPER, labels[bottom_right])
    bottom_row = r

    # horizontal arrows aim for the table's centre column so → and ← line up vertically, but slide
    # toward the row's free gap when a long label covers the centre; skipped only when the gap can't
    # fit an arrow with a space on each side (the diagonals still trace the ring)
    centre = right // 2

    def place_centre(r: int, left_label: str, right_label: str, arrow: str) -> None:
        lo = TAPER + len(left_label) + 1
        hi = (right - TAPER) - len(right_label) - 2
        if lo <= hi:
            place(r, min(max(centre, lo), hi), arrow)

    place_centre(top_row, labels[0], labels[1], "→")
    place_centre(bottom_row, labels[bottom_left], labels[bottom_right], "←")

    return "\n".join(line.rstrip() for line in rows)


SEAT_LABEL_WIDTH = 12


def seat_label(name: str) -> str:
    """A name as it lands on the ring: unrenderable characters dropped, truncated to one seat's width.
    Public so a caller tinting labels can key its color map on the same string the art carries."""
    rendered = drop_unrenderable(name) or "?"
    if len(rendered) <= SEAT_LABEL_WIDTH:
        return rendered
    return rendered[:SEAT_LABEL_WIDTH - 1] + "…"


@lru_cache(maxsize=4)
def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_MONO), round(size * SCALE))


def _glyph_mask(font: ImageFont.FreeTypeFont, ch: str) -> tuple:
    mask = font.getmask(ch)
    return (mask.size, bytes(mask))
