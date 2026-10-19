from pathlib import Path

from PIL import Image

GAMES = Path(__file__).resolve().parents[2] / "public" / "games"
CANVAS = 512


def main():
    build_gif("trophy-mage/trophy-emoji.png", frames=24, frame_size=(13, 15), scale=26, durations=[1800] + [83] * 23,
              target="trophy-mage/og-image.gif")
    build_gif("wheel-of-fortune/wheel-emoji.png", frames=32, frame_size=(23, 25), scale=15, durations=[60] * 32,
              target="wheel-of-fortune/og-image.gif")


def build_gif(strip, frames, frame_size, scale, durations, target):
    sheet = Image.open(GAMES / strip).convert("RGBA")
    frame_w, frame_h = frame_size
    images = []
    for i in range(frames):
        frame = sheet.crop((i * frame_w, 0, (i + 1) * frame_w, frame_h))
        big = frame.resize((frame_w * scale, frame_h * scale), Image.NEAREST)
        canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
        canvas.paste(big, ((CANVAS - big.width) // 2, (CANVAS - big.height) // 2), big)
        images.append(canvas)
    images[0].save(GAMES / target, save_all=True, append_images=images[1:], duration=durations, loop=0, disposal=2)


if __name__ == "__main__":
    main()
