from pathlib import Path

from PIL import Image

SRC = Path("/home/mnoya/Documents/Discord/LLU Logo - High Res.psd")
PUBLIC = Path(__file__).resolve().parents[1] / "public"
TRANSPARENT_LONGEST = 512


def load_trimmed():
    im = Image.open(SRC).convert("RGBA")
    bbox = im.split()[3].getbbox()
    return im.crop(bbox) if bbox else im


def fit(im, longest):
    scale = longest / max(im.size)
    size = (round(im.width * scale), round(im.height * scale))
    return im.resize(size, Image.LANCZOS)


def on_black(im):
    bg = Image.new("RGBA", im.size, (0, 0, 0, 255))
    bg.alpha_composite(im)
    return bg.convert("RGB")


def square_on_black(im, side):
    logo = fit(im, round(side * 0.86))
    canvas = Image.new("RGB", (side, side), (0, 0, 0))
    canvas.paste(logo, ((side - logo.width) // 2, (side - logo.height) // 2), logo)
    return canvas


def square_transparent(im, side):
    logo = fit(im, side)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.alpha_composite(logo, ((side - logo.width) // 2, (side - logo.height) // 2))
    return canvas


def main():
    logo = load_trimmed()

    transparent = fit(logo, TRANSPARENT_LONGEST)
    transparent.save(PUBLIC / "llu-logo-transparent.png")

    square_on_black(logo, 1200).save(PUBLIC / "llu-logo.png")

    square_on_black(logo, 512).save(PUBLIC / "icon-512.png")
    square_on_black(logo, 192).save(PUBLIC / "icon-192.png")

    square_transparent(logo, 32).save(PUBLIC / "favicon-32.png")
    square_transparent(logo, 16).save(PUBLIC / "favicon-16.png")
    square_transparent(logo, 32).save(PUBLIC / "favicon.ico", sizes=[(16, 16), (32, 32)])

    names = ("llu-logo-transparent.png", "llu-logo.png", "icon-512.png", "icon-192.png",
             "favicon-32.png", "favicon-16.png", "favicon.ico")
    for name in names:
        p = PUBLIC / name
        print(name, Image.open(p).size, Image.open(p).mode)


if __name__ == "__main__":
    main()
