"""Generate white-on-transparent set-symbol PNGs for the leaderboard from keyrune.

Keyrune ships each set glyph as a monochrome ``#444`` SVG; the leaderboard renders
white symbols on dark surfaces (Discord unfurls, the site), so each glyph is
recolored to white and rasterized to PNG. Run with no args to (re)generate every
set in ``bot.sets.ALL_SETS`` plus the ``MTGO_FLASHBACK_SETS``, or pass specific
codes (e.g. ``MSH SOS`` or ``MH1 IPA``).

A code with no keyrune glyph of its own borrows another set's via ``KEYRUNE_ALIAS``
(e.g. ``IPA`` -> Invasion); keep that map in sync with ``KEYRUNE_OVERRIDES`` in
``frontend/src/components/Brand.tsx``.

Downstream: upload the same PNG to the bot's Discord application as an emoji named by
the lowercase code (``mh1``, ``war`` …). ``/event-scribe`` and set embeds look the
symbol up by that name, so a set with no uploaded emoji renders without its glyph.

Requires ``inkscape`` (rasterizer) and ``pngquant`` (optional optimization) on PATH.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from bot.sets import ALL_SETS, MTGO_FLASHBACK_SETS

KEYRUNE_SVG_URL = "https://cdn.jsdelivr.net/gh/andrewgioia/keyrune@latest/svg/{code}.svg"
OUTPUT_DIR = Path(__file__).resolve().parents[2] / "frontend" / "public" / "set-symbols"
SYMBOL_PX = 256

# Sets keyrune has no glyph of their own borrow a source set's symbol. Mirror any block/flashback
# override here and in KEYRUNE_OVERRIDES (frontend/src/components/Brand.tsx).
KEYRUNE_ALIAS = {"SIR": "soi", "IPA": "inv", "CHAOS": "mb2"}


def generate(codes: list[str]) -> tuple[list[str], list[str]]:
    """Generate a PNG for each code; return ``(generated, missing)`` where missing codes have no keyrune glyph."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    generated: list[str] = []
    missing: list[str] = []
    for code in codes:
        svg = _fetch_white_svg(code)
        if svg is None:
            missing.append(code)
            continue
        _rasterize(code, svg)
        generated.append(code)
    if generated:
        _optimize([OUTPUT_DIR / f"{code.lower()}.png" for code in generated])
    return generated, missing


def _fetch_white_svg(code: str) -> str | None:
    glyph = KEYRUNE_ALIAS.get(code.upper(), code.lower())
    url = KEYRUNE_SVG_URL.format(code=glyph)
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    return squarify(raw.replace("#444", "#ffffff"))


def squarify(svg: str) -> str:
    """Keyrune glyphs share a height but vary in width; without this the 256x256 export stretches
    a non-square glyph to fill the square. Centering it in a square viewBox keeps its proportions."""
    m = re.search(r'viewBox="(-?[\d.]+) (-?[\d.]+) ([\d.]+) ([\d.]+)"', svg)
    if not m:
        return svg
    width, height = float(m.group(3)), float(m.group(4))
    side = max(width, height)
    min_x = float(m.group(1)) - (side - width) / 2
    min_y = float(m.group(2)) - (side - height) / 2

    def fmt(value: float) -> str:
        return f"{value:g}"

    svg = re.sub(r'(<svg[^>]*?)\swidth="[\d.]+"', rf'\1 width="{fmt(side)}"', svg, count=1)
    svg = re.sub(r'(<svg[^>]*?)\sheight="[\d.]+"', rf'\1 height="{fmt(side)}"', svg, count=1)
    return re.sub(
        r'viewBox="[^"]*"',
        f'viewBox="{fmt(min_x)} {fmt(min_y)} {fmt(side)} {fmt(side)}"',
        svg,
        count=1,
    )


def _rasterize(code: str, svg: str) -> None:
    rasterize(svg, OUTPUT_DIR / f"{code.lower()}.png", SYMBOL_PX)


def rasterize(svg: str, png: Path, px: int) -> None:
    """Snap-confined inkscape only resolves absolute paths, so png must be fully resolved."""
    src = png.with_name(f"_src_{png.stem}.svg")
    src.write_text(svg, encoding="utf-8")
    try:
        subprocess.run(
            ["inkscape", str(src), "--export-type=png", f"--export-filename={png}",
             "-w", str(px), "-h", str(px)],
            check=True, capture_output=True,
        )
    finally:
        src.unlink(missing_ok=True)


def _optimize(paths: list[Path]) -> None:
    if shutil.which("pngquant") is None:
        return
    subprocess.run(
        ["pngquant", "--quality=80-100", "--force", "--ext", ".png", "--strip", *map(str, paths)],
        check=False, capture_output=True,
    )


def main(argv: list[str]) -> int:
    if shutil.which("inkscape") is None:
        print("inkscape not found on PATH; install it to rasterize set symbols", file=sys.stderr)
        return 1
    codes = [arg.upper() for arg in argv] or [s.code for s in ALL_SETS] + list(MTGO_FLASHBACK_SETS)
    generated, missing = generate(codes)
    print(f"generated {len(generated)}: {', '.join(generated) or '(none)'}")
    if missing:
        print(f"no keyrune glyph, skipped: {', '.join(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
