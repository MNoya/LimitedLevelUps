import base64
from pathlib import Path

from PIL import Image

WORDMARK = "/home/mnoya/Documents/Discord/LLU Logo - High Res-wordmark.png"
PUBLIC = Path(__file__).resolve().parents[1] / "public"

CANVAS_CX, CANVAS_CY, OUTER_R = 1349, 1395, 908
WORDMARK_X, WORDMARK_Y = 392, 675

RING_STROKE = 19
GAP = 30
PAD = 24

GREEN_TOP = "#00B245"
GREEN_BOTTOM = "#00F30C"
CYAN = "#01FEFE"


EMBED_WIDTH = 1000
EMBED_PATH = Path("/tmp/llu-wordmark-embed.webp")


def data_uri(path):
    with open(path, "rb") as fh:
        return "data:image/webp;base64," + base64.b64encode(fh.read()).decode()


wm = Image.open(WORDMARK).convert("RGBA")
wm_w, wm_h = wm.size
scale = EMBED_WIDTH / wm_w
embed = wm.resize((EMBED_WIDTH, round(wm_h * scale)), Image.LANCZOS)
embed.save(EMBED_PATH, format="WEBP", quality=92, method=6)

ox = min(WORDMARK_X, CANVAS_CX - OUTER_R) - PAD
oy = min(WORDMARK_Y, CANVAS_CY - OUTER_R) - PAD
vb_w = max(WORDMARK_X + wm_w, CANVAS_CX + OUTER_R) + PAD - ox
vb_h = max(WORDMARK_Y + wm_h, CANVAS_CY + OUTER_R) + PAD - oy

cx, cy = CANVAS_CX - ox, CANVAS_CY - oy
ring_center_r = OUTER_R - RING_STROKE / 2
disk_r = OUTER_R - RING_STROKE - GAP
disk_top, disk_bottom = cy - disk_r, cy + disk_r
wm_x, wm_y = WORDMARK_X - ox, WORDMARK_Y - oy

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {vb_w} {vb_h}" width="{vb_w}" height="{vb_h}">
  <defs>
    <linearGradient id="disk" x1="0" y1="{disk_top:.1f}" x2="0" y2="{disk_bottom:.1f}" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="{GREEN_TOP}"/>
      <stop offset="1" stop-color="{GREEN_BOTTOM}"/>
    </linearGradient>
  </defs>
  <circle cx="{cx}" cy="{cy}" r="{disk_r:.1f}" fill="url(#disk)"/>
  <circle cx="{cx}" cy="{cy}" r="{ring_center_r:.1f}" fill="none" stroke="{CYAN}" stroke-width="{RING_STROKE}"/>
  <image href="{data_uri(EMBED_PATH)}" x="{wm_x}" y="{wm_y}" width="{wm_w}" height="{wm_h}"/>
</svg>
'''
out = PUBLIC / "llu-logo.svg"
out.write_text(svg)
print("wrote", out, "viewBox", vb_w, vb_h, "gap", GAP, "stroke", RING_STROKE)
