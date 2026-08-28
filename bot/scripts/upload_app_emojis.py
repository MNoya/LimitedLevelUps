"""Generate and upload Discord application emojis from the keyrune / mana icon fonts or a local PNG.

Each argument is ``source:glyph[:name]`` — source is ``keyrune``, ``mana`` or ``file``. For a font
source, glyph is the icon's filename in that font's ``svg/`` directory; the glyph is recolored white
and rasterized like the site's set symbols. For ``file``, glyph is a path to a PNG that is trimmed,
fit into a 128px transparent square, and uploaded as is. Name defaults to the glyph basename with
non-alphanumeric characters stripped. Uploads target the application DISCORD_BOT_TOKEN belongs to,
so the same invocation seeds the test and production apps. An emoji whose name already exists is
skipped; pass ``--force`` to replace it.

Example:
    python -m bot.scripts.upload_app_emojis keyrune:8ed mana:dfc-day:dfcday file:art/mema.png:mema
"""
from __future__ import annotations

import base64
import io
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

import requests

from bot.config import settings
from bot.scripts.generate_set_symbols import rasterize, squarify

API_BASE = "https://discord.com/api/v10"
SVG_URLS = {
    "keyrune": "https://cdn.jsdelivr.net/gh/andrewgioia/keyrune@latest/svg/{glyph}.svg",
    "mana": "https://cdn.jsdelivr.net/gh/andrewgioia/mana@latest/svg/{glyph}.svg",
}
EMOJI_PX = 128


def upload(specs: list[tuple[str, str, str]], force: bool) -> int:
    token = settings.discord_bot_token.get_secret_value() if settings.discord_bot_token else None
    if not token:
        print("DISCORD_BOT_TOKEN is not set", file=sys.stderr)
        return 1
    headers = {"Authorization": f"Bot {token}"}
    app_id = requests.get(f"{API_BASE}/applications/@me", headers=headers, timeout=20).json()["id"]
    emoji_url = f"{API_BASE}/applications/{app_id}/emojis"
    existing = {
        e["name"]: e["id"]
        for e in requests.get(emoji_url, headers=headers, timeout=20).json()["items"]
    }

    failures = 0
    for source, glyph, name in specs:
        if name in existing:
            if not force:
                print(f"{name}: already exists, skipped (use --force to replace)")
                continue
            requests.delete(f"{emoji_url}/{existing[name]}", headers=headers, timeout=20)
        png = _render_glyph(source, glyph, name)
        if png is None:
            print(f"{name}: no {source} glyph named {glyph!r}", file=sys.stderr)
            failures += 1
            continue
        image = f"data:image/png;base64,{base64.b64encode(png).decode('ascii')}"
        response = requests.post(emoji_url, headers=headers, json={"name": name, "image": image}, timeout=20)
        if response.ok:
            print(f"{name}: uploaded ({source}:{glyph})")
        else:
            print(f"{name}: upload failed — {response.status_code} {response.text}", file=sys.stderr)
            failures += 1
    return 1 if failures else 0


def _render_glyph(source: str, glyph: str, name: str) -> bytes | None:
    if source == "file":
        return _render_file(glyph)
    url = SVG_URLS[source].format(glyph=glyph)
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    svg = squarify(raw.replace("#444", "#ffffff"))
    workdir = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(dir=workdir) as tmp:
        png_path = Path(tmp) / f"{name}.png"
        rasterize(svg, png_path, EMOJI_PX)
        return png_path.read_bytes()


def _render_file(path: str) -> bytes | None:
    src = Path(path)
    if not src.is_file():
        return None
    return fit_square_png(src.read_bytes(), EMOJI_PX)


def fit_square_png(raw: bytes, size: int) -> bytes:
    """Trim transparent margins and center the image on a transparent square of `size` px."""
    from PIL import Image

    image = Image.open(io.BytesIO(raw)).convert("RGBA")
    bbox = image.getbbox()
    if bbox is not None:
        image = image.crop(bbox)
    scale = size / max(image.width, image.height)
    resized = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(resized, ((size - resized.width) // 2, (size - resized.height) // 2), resized)
    out = io.BytesIO()
    canvas.save(out, format="PNG", optimize=True)
    return out.getvalue()


def parse_spec(arg: str) -> tuple[str, str, str] | None:
    parts = arg.split(":")
    if len(parts) not in (2, 3) or (parts[0] not in SVG_URLS and parts[0] != "file"):
        return None
    source, glyph = parts[0], parts[1]
    default_name = re.sub(r"[^A-Za-z0-9_]", "", Path(glyph).stem if source == "file" else glyph)
    name = parts[2] if len(parts) == 3 else default_name
    return source, glyph, name


def main(argv: list[str]) -> int:
    force = "--force" in argv
    args = [arg for arg in argv if arg != "--force"]
    if not args:
        print("usage: upload_app_emojis [--force] source:glyph[:name] ...", file=sys.stderr)
        return 1
    specs = []
    for arg in args:
        spec = parse_spec(arg)
        if spec is None:
            print(f"bad spec {arg!r}; expected source:glyph[:name] with source keyrune|mana|file", file=sys.stderr)
            return 1
        specs.append(spec)
    if any(source != "file" for source, _glyph, _name in specs) and shutil.which("inkscape") is None:
        print("inkscape not found on PATH", file=sys.stderr)
        return 1
    return upload(specs, force)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
