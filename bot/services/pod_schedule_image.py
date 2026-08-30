"""The pod format calendar grid, rendered to PNG for the `/pod-schedule` embed.

The grid answers one question: what does a day add on top of the set every pod already drafts? That set is
named once in the message, so a cell carries only its own flashback or cube, and a day that adds nothing
falls back to the daily set's own symbol in `FAINT` — enough to read as a drafting day without repeating a
code the message already gives. Two days break the pattern and each gets a filled date band: the day a new
set arrives, and the Set Championship.

Discord fits an embed image inside 400x300, so the layout is sized in logical pixels well under that and
drawn at `SCALE`: a narrower logical grid is shown larger, which is the only lever the image has over how
big its labels land on screen. `_cell_width` holds the grid inside that box's ratio, since an image scaled
down by its height renders short of the full width and narrows the whole embed with it.

`ACCENT` is the embed's green saturated up: the flagged band is a small patch of colour on a grey grid, and
the embed's own green washes out at that size.

Type matches the site — Bebas Neue for dates and format codes, tracked Space Grotesk for the weekday row.
Set symbols are the white-on-transparent PNGs `bot/scripts/generate_set_symbols.py` writes for the site;
a code with no file renders as its label alone. Pillow-only, deterministic, no network and no DB.
"""
from __future__ import annotations

import io
from datetime import date
from functools import lru_cache
from math import ceil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from bot.services.championship_dates import championship_on
from bot.services.pod_format import PEASANT_CODE, is_custom
from bot.services.pod_format_schedule import (
    FLASHBACK,
    calendar_days,
    extras_on,
    is_rotation_day,
    latest_on,
    planned_on,
)

SYMBOLS_DIR = Path(__file__).resolve().parents[2] / "frontend" / "public" / "set-symbols"
CUBE_SYMBOL = "cube"
FONTS_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
FONT_DISPLAY = FONTS_DIR / "BebasNeue-Regular.ttf"
FONT_LABEL = FONTS_DIR / "SpaceGrotesk-Variable.ttf"
LABEL_WEIGHT = "Medium"

SCALE = 3
COLS = 7
CELL_W = 42
CELL_H = 34
PAD = 5
WEEKDAY_H = 12
BAND_H = 12
ROW_H = 11
SYMBOL_PX = 9
SYMBOL_GAP = 1.5
NUM_SIZE = 9
CODE_SIZE = 9
WEEKDAY_SIZE = 6
WEEKDAY_TRACKING = 1
GRID_W = 1
MIN_ASPECT = 4 / 3
WEEKDAY_NAMES = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
CHAMPIONSHIP_LABEL = "CHAMPS"
PLACEHOLDER_LABEL = "TBD"

RGB = tuple[int, int, int]

ACCENT = (25, 225, 108)

BACKGROUND = (43, 45, 49)
CELL = (49, 51, 56)
CELL_PAST = (45, 47, 51)
BAND = (58, 61, 67)
BAND_PAST = (51, 53, 58)
GRID = (78, 82, 90)
TEXT = (219, 222, 225)
MUTED = (160, 167, 176)
DIM = (138, 144, 153)
FAINT = (96, 101, 110)
ARRIVAL = ACCENT
CHAMPIONSHIP = (201, 156, 84)
PLACEHOLDER = (153, 170, 255)
ON_FLAG = (30, 32, 35)
TODAY = ACCENT


def render_calendar_png(today: date, weeks: int) -> bytes:
    """`weeks` Monday-start weeks from the week holding `today`, each cell carrying what its day adds on top
    of the daily set. Today is outlined; the arrival of a new set and the championship each fill their own
    date band, so a reader finds the two days that matter without reading every cell.

    Both flags are derived per day, so a span long enough to hold two rotations bands them both, and it marks
    the incoming set's championship as readily as the one the set live today holds."""
    days = calendar_days(today, weeks)
    cell_w = _cell_width(weeks)
    width = _px(PAD * 2 + COLS * cell_w)
    height = _px(PAD * 2 + WEEKDAY_H + weeks * CELL_H)

    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    _draw_weekday_header(draw, today, cell_w)
    for index, day in enumerate(days):
        _draw_day(draw, day, index, today=today, cell_w=cell_w)
    _draw_grid(draw, weeks, cell_w)
    for index, day in enumerate(days):
        if day == today:
            x, y = _cell_origin(index, cell_w)
            draw.rectangle([x, y, x + _px(cell_w), y + _px(CELL_H)], outline=TODAY, width=_px(GRID_W))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _cell_width(weeks: int) -> int:
    """How wide a cell is drawn for a span of `weeks`. Discord fits an embed image inside 400x300 keeping its
    ratio, so a grid taller than 4:3 is scaled down by its height, renders short of the full width, and drags
    the whole embed narrow enough to wrap the message lines above it. Past six weeks the cells widen to hold
    that ratio, which also shows them larger rather than smaller."""
    height = PAD * 2 + WEEKDAY_H + weeks * CELL_H
    return max(CELL_W, ceil((MIN_ASPECT * height - PAD * 2) / COLS))


def _draw_weekday_header(draw: ImageDraw.ImageDraw, today: date, cell_w: int) -> None:
    """Today's own column header wears the accent, so the eye runs from the weekday down to the outlined
    cell instead of hunting for it."""
    for column, name in enumerate(WEEKDAY_NAMES):
        center = _px(PAD + column * cell_w + cell_w // 2)
        color = TODAY if column == today.weekday() else MUTED
        _draw_tracked(draw, name, center, _px(PAD), color)


def _draw_day(draw: ImageDraw.ImageDraw, day: date, index: int, *, today: date, cell_w: int) -> None:
    x, y = _cell_origin(index, cell_w)
    past = day < today
    flag = _flag_fill(day)

    draw.rectangle([x, y, x + _px(cell_w), y + _px(CELL_H)], fill=CELL_PAST if past else CELL)
    draw.rectangle([x, y, x + _px(cell_w), y + _px(BAND_H)], fill=flag or (BAND_PAST if past else BAND))

    number = f"{day:%b %-d}".upper() if day.day == 1 else f"{day:%-d}"
    number_color = ON_FLAG if flag else (DIM if past else TEXT)
    draw.text((x + _px(cell_w // 2), y + _px(BAND_H // 2)), number, font=_font(FONT_DISPLAY, NUM_SIZE),
              fill=number_color, anchor="mm")

    rows = _rows_for(day, past=past)
    for offset, (label, color, symbol) in enumerate(rows):
        top = _row_top(y, len(rows)) + _px(offset * ROW_H)
        _draw_row(draw, x, top, label, color, symbol, cell_w)


def _flag_fill(day: date) -> RGB | None:
    if is_rotation_day(day):
        return ARRIVAL
    if championship_on(day) is not None:
        return CHAMPIONSHIP
    return None


def _rows_for(day: date, *, past: bool) -> list[tuple[str, RGB, str]]:
    """What a cell lists, as (label, colour, symbol). The championship day shows its set in the championship
    ink alone, its other pod still opening but the day read as one thing. A day running only the latest set
    falls back to its symbol; a day naming two formats lists both, so the latest set shows by code on a
    shared day."""
    if championship_on(day) is not None:
        return [(CHAMPIONSHIP_LABEL, CHAMPIONSHIP, latest_on(day))]
    ink = DIM if past else TEXT
    if is_rotation_day(day):
        rows = [(latest_on(day), ARRIVAL, latest_on(day))]
        rows.extend((_cell_label(code), ink, code) for code in extras_on(day))
        return rows
    latest = latest_on(day)
    formats = planned_on(day)
    if not formats or formats == (latest,):
        return [("", FAINT if past else ink, latest)]
    return [(_cell_label(code), PLACEHOLDER if code == FLASHBACK else ink, code) for code in formats]


def _cell_label(code: str) -> str:
    """A flashback day with no set chosen has no code to show, so its cell names what is still missing."""
    return PLACEHOLDER_LABEL if code == FLASHBACK else code


def _draw_row(draw: ImageDraw.ImageDraw, cell_x: int, top: int, label: str, color: RGB, symbol: str,
              cell_w: int) -> None:
    """One centred symbol-and-code row. Centring the pair rather than left-aligning it keeps a one-row cell
    reading as a calendar entry instead of a list of one."""
    long_label = label == PEASANT_CODE
    font = _font(FONT_DISPLAY, CODE_SIZE - 1 if long_label else CODE_SIZE)
    mark = _symbol(symbol)
    mark_w = _px(SYMBOL_PX) + (_px(SYMBOL_GAP) if label else 0) if mark is not None else 0
    x = cell_x + (_px(cell_w) - mark_w - font.getlength(label)) / 2
    if mark is not None:
        draw.bitmap((round(x), top), mark, fill=color)
        x += mark_w
    draw.text((round(x), top), label, font=font, fill=color)


def _row_top(cell_y: int, rows: int) -> int:
    """Top of the first content row, so one row sits centred in the space under the band and two stack."""
    free = _px(CELL_H - BAND_H)
    return cell_y + _px(BAND_H) + (free - rows * _px(ROW_H)) // 2


def _draw_grid(draw: ImageDraw.ImageDraw, weeks: int, cell_w: int) -> None:
    """One pass of full-length rules over the filled cells, so every line has the same weight. Per-cell
    outlines would double up wherever two cells meet and leave the outer frame half as heavy."""
    left, top = _px(PAD), _px(PAD + WEEKDAY_H)
    right, bottom = left + _px(COLS * cell_w), top + _px(weeks * CELL_H)
    for column in range(COLS + 1):
        x = left + _px(column * cell_w)
        draw.line([x, top, x, bottom], fill=GRID, width=_px(GRID_W))
    for row in range(weeks + 1):
        y = top + _px(row * CELL_H)
        draw.line([left, y, right, y], fill=GRID, width=_px(GRID_W))


def _cell_origin(index: int, cell_w: int) -> tuple[int, int]:
    row, column = divmod(index, COLS)
    return _px(PAD + column * cell_w), _px(PAD + WEEKDAY_H + row * CELL_H)


def _draw_tracked(draw: ImageDraw.ImageDraw, text: str, center_x: int, y: int, color: RGB) -> None:
    """Letter-spaced small caps, drawn glyph by glyph because Pillow has no tracking. Mirrors the site's
    `tracking-[0.2em]` header treatment, which is most of why those labels read as headers at all."""
    font = _label_font(WEEKDAY_SIZE)
    tracking = _px(WEEKDAY_TRACKING)
    widths = [font.getlength(character) for character in text]
    x = center_x - (sum(widths) + tracking * (len(text) - 1)) / 2
    for character, width in zip(text, widths):
        draw.text((x, y), character, font=font, fill=color)
        x += width + tracking


def _px(logical: float) -> int:
    return round(logical * SCALE)


@lru_cache(maxsize=8)
def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), _px(size))


@lru_cache(maxsize=4)
def _label_font(size: int) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(str(FONT_LABEL), _px(size))
    font.set_variation_by_name(LABEL_WEIGHT)
    return font


@lru_cache(maxsize=64)
def _symbol(code: str) -> Image.Image | None:
    """The format's symbol as an alpha mask, so `bitmap` can paint it in whatever ink the cell uses."""
    path = _symbol_path(code)
    if path is None:
        return None
    side = _px(SYMBOL_PX)
    return Image.open(path).convert("RGBA").resize((side, side), Image.LANCZOS).getchannel("A")


def _symbol_path(code: str) -> Path | None:
    """The format's own set-symbol PNG first, so a cube with an uploaded symbol like MEMA uses it, then the
    generic cube symbol for a custom format that has none."""
    own = SYMBOLS_DIR / f"{code.lower()}.png"
    if own.exists():
        return own
    if is_custom(code):
        cube = SYMBOLS_DIR / f"{CUBE_SYMBOL}.png"
        if cube.exists():
            return cube
    return None
