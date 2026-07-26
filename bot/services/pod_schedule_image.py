"""The pod format calendar grid, rendered to PNG for the `/pod-schedule` embed.

The grid answers one question: what does a day add on top of the set every pod already drafts? That set is
named once in the message, so a cell carries only its own flashback or cube and most cells stay empty on
purpose. Two days break the pattern and each gets a filled date band instead of a code: the day a new set
arrives, and the Set Championship.

Discord displays an embed image 400px wide, so the layout is sized in logical pixels well under that and
drawn at `SCALE`: a narrower logical grid is shown larger, which is the only lever the image has over how
big its labels land on screen.

Type matches the site — Bebas Neue for dates and format codes, tracked Space Grotesk for the weekday row.
Set symbols are the white-on-transparent PNGs `bot/scripts/generate_set_symbols.py` writes for the site;
a code with no file renders as its label alone. Pillow-only, deterministic, no network and no DB.
"""
from __future__ import annotations

import io
from datetime import date
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from bot.services.pod_format import is_custom
from bot.services.pod_format_schedule import calendar_days, extras_on, latest_on, rotation_in

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
WEEKDAY_NAMES = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
CHAMPIONSHIP_LABEL = "CHAMPS"

BACKGROUND = (43, 45, 49)
CELL = (49, 51, 56)
CELL_PAST = (45, 47, 51)
BAND = (58, 61, 67)
BAND_PAST = (51, 53, 58)
GRID = (78, 82, 90)
TEXT = (219, 222, 225)
MUTED = (160, 167, 176)
DIM = (138, 144, 153)
ARRIVAL = (108, 178, 132)
CHAMPIONSHIP = (201, 156, 84)
ON_FLAG = (30, 32, 35)
TODAY = (126, 190, 149)


def render_calendar_png(today: date, weeks: int, championship: date | None = None) -> bytes:
    """`weeks` Monday-start weeks from the week holding `today`, each cell carrying what its day adds on top
    of the daily set. Today is outlined; the arrival of a new set and the championship each fill their own
    date band, so a reader finds the two days that matter without reading every cell."""
    days = calendar_days(today, weeks)
    arrival = rotation_in(days)
    width = _px(PAD * 2 + COLS * CELL_W)
    height = _px(PAD * 2 + WEEKDAY_H + weeks * CELL_H)

    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    _draw_weekday_header(draw, today)
    for index, day in enumerate(days):
        _draw_day(draw, day, index, today=today, arrival=arrival, championship=championship)
    _draw_grid(draw, weeks)
    for index, day in enumerate(days):
        if day == today:
            x, y = _cell_origin(index)
            draw.rectangle([x, y, x + _px(CELL_W), y + _px(CELL_H)], outline=TODAY, width=_px(GRID_W))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _draw_weekday_header(draw: ImageDraw.ImageDraw, today: date) -> None:
    """Today's own column header wears the accent, so the eye runs from the weekday down to the outlined
    cell instead of hunting for it."""
    for column, name in enumerate(WEEKDAY_NAMES):
        center = _px(PAD + column * CELL_W + CELL_W // 2)
        color = TODAY if column == today.weekday() else MUTED
        _draw_tracked(draw, name, center, _px(PAD), color)


def _draw_day(draw: ImageDraw.ImageDraw, day: date, index: int, *, today: date, arrival: date | None,
              championship: date | None) -> None:
    x, y = _cell_origin(index)
    past = day < today
    flag = ARRIVAL if day == arrival else (CHAMPIONSHIP if day == championship else None)

    draw.rectangle([x, y, x + _px(CELL_W), y + _px(CELL_H)], fill=CELL_PAST if past else CELL)
    draw.rectangle([x, y, x + _px(CELL_W), y + _px(BAND_H)], fill=flag or (BAND_PAST if past else BAND))

    number = f"{day:%b %-d}".upper() if day.day == 1 else f"{day:%-d}"
    number_color = ON_FLAG if flag else (DIM if past else TEXT)
    draw.text((x + _px(CELL_W // 2), y + _px(BAND_H // 2)), number, font=_font(FONT_DISPLAY, NUM_SIZE),
              fill=number_color, anchor="mm")

    rows = _rows_for(day, past=past, arrival=arrival, championship=championship)
    for offset, (label, color, symbol) in enumerate(rows):
        top = _row_top(y, len(rows)) + _px(offset * ROW_H)
        _draw_row(draw, x, top, label, color, symbol=symbol, crown=symbol is None)


def _rows_for(day: date, *, past: bool, arrival: date | None,
              championship: date | None) -> list[tuple[str, tuple[int, int, int], str | None]]:
    """What a cell lists, as (label, colour, symbol) with no symbol meaning the crown. The championship day
    shows the crown alone: its other pod is still on the schedule and still opens, but the day is read as one
    thing.

    Only the arrival itself names the incoming set. The days after it stay blank like any other day on the
    daily set, which the message names by role rather than by code, so the calendar never has to repeat a
    set that a rotation is about to change."""
    if day == championship:
        return [(CHAMPIONSHIP_LABEL, CHAMPIONSHIP, None)]
    ink = DIM if past else TEXT
    rows = [(latest_on(day), ARRIVAL, latest_on(day))] if day == arrival else []
    rows.extend((code, ink, code) for code in extras_on(day))
    return rows


def _draw_row(draw: ImageDraw.ImageDraw, cell_x: int, top: int, label: str, color: tuple[int, int, int], *,
              symbol: str | None = None, crown: bool = False) -> None:
    """One centred symbol-and-code row. Centring the pair rather than left-aligning it keeps a one-row cell
    reading as a calendar entry instead of a list of one."""
    font = _font(FONT_DISPLAY, CODE_SIZE)
    mark = _crown() if crown else (_symbol(symbol) if symbol else None)
    mark_w = _px(SYMBOL_PX) + _px(SYMBOL_GAP) if mark is not None else 0
    x = cell_x + (_px(CELL_W) - mark_w - font.getlength(label)) / 2
    if mark is not None:
        draw.bitmap((round(x), top), mark, fill=color)
        x += mark_w
    draw.text((round(x), top), label, font=font, fill=color)


def _row_top(cell_y: int, rows: int) -> int:
    """Top of the first content row, so one row sits centred in the space under the band and two stack."""
    free = _px(CELL_H - BAND_H)
    return cell_y + _px(BAND_H) + (free - rows * _px(ROW_H)) // 2


def _draw_grid(draw: ImageDraw.ImageDraw, weeks: int) -> None:
    """One pass of full-length rules over the filled cells, so every line has the same weight. Per-cell
    outlines would double up wherever two cells meet and leave the outer frame half as heavy."""
    left, top = _px(PAD), _px(PAD + WEEKDAY_H)
    right, bottom = left + _px(COLS * CELL_W), top + _px(weeks * CELL_H)
    for column in range(COLS + 1):
        x = left + _px(column * CELL_W)
        draw.line([x, top, x, bottom], fill=GRID, width=_px(GRID_W))
    for row in range(weeks + 1):
        y = top + _px(row * CELL_H)
        draw.line([left, y, right, y], fill=GRID, width=_px(GRID_W))


def _cell_origin(index: int) -> tuple[int, int]:
    row, column = divmod(index, COLS)
    return _px(PAD + column * CELL_W), _px(PAD + WEEKDAY_H + row * CELL_H)


def _draw_tracked(draw: ImageDraw.ImageDraw, text: str, center_x: int, y: int, color: tuple[int, int, int]) -> None:
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
    name = CUBE_SYMBOL if is_custom(code) else code.lower()
    path = SYMBOLS_DIR / f"{name}.png"
    if not path.exists():
        return None
    side = _px(SYMBOL_PX)
    return Image.open(path).convert("RGBA").resize((side, side), Image.LANCZOS).getchannel("A")


@lru_cache(maxsize=1)
def _crown() -> Image.Image:
    """A crown mask drawn as a polygon, since none of the bundled faces carries the glyph and the emoji
    would arrive as a colour bitmap that cannot take the cell's ink."""
    side = _px(SYMBOL_PX)
    mask = Image.new("L", (side, side), 0)
    pen = ImageDraw.Draw(mask)
    points = [(0.04, 0.78), (0.04, 0.24), (0.28, 0.52), (0.5, 0.16), (0.72, 0.52), (0.96, 0.24), (0.96, 0.78)]
    pen.polygon([(x * side, y * side) for x, y in points], fill=255)
    pen.rectangle([0.04 * side, 0.82 * side, 0.96 * side, 0.96 * side], fill=255)
    return mask
