"""Generate the application icon (resources/icons/ofis.ico).

A document sheet with a folded corner on the app's blue accent — drawn at
512 px and downsampled into a multi-size .ico (16→256). Deterministic: rerun
whenever the design changes; the .ico is committed so builds don't need PIL
tricks at package time.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "resources" / "icons"

ACCENT = (47, 107, 255)       # #2f6bff — app accent
ACCENT_DARK = (23, 62, 168)
PAPER = (255, 255, 255)
FOLD = (214, 224, 245)
LINE = (167, 192, 250)

S = 512


def _rounded(draw: ImageDraw.ImageDraw, box, radius, fill) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def build() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # background: vertical accent gradient in a rounded square
    bg = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bg)
    for y in range(S):
        t = y / S
        color = tuple(int(ACCENT[i] + (ACCENT_DARK[i] - ACCENT[i]) * t) for i in range(3))
        bd.line([(0, y), (S, y)], fill=color + (255,))
    mask = Image.new("L", (S, S), 0)
    _rounded(ImageDraw.Draw(mask), (0, 0, S - 1, S - 1), radius=S // 5, fill=255)
    img.paste(bg, (0, 0), mask)

    # document sheet with folded top-right corner
    left, top, right, bottom = 136, 96, 376, 416
    fold = 64
    d.polygon(
        [(left, top), (right - fold, top), (right, top + fold), (right, bottom),
         (left, bottom)],
        fill=PAPER,
    )
    d.polygon(
        [(right - fold, top), (right - fold, top + fold), (right, top + fold)],
        fill=FOLD,
    )
    # text lines
    for i, y in enumerate(range(top + 96, bottom - 40, 56)):
        width = (right - left - 72) if i % 2 == 0 else (right - left - 120)
        d.rounded_rectangle((left + 36, y, left + 36 + width, y + 18), radius=9, fill=LINE)

    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    art = build()
    art.resize((256, 256), Image.LANCZOS).save(OUT / "ofis_256.png")
    art.resize((256, 256), Image.LANCZOS).save(
        OUT / "ofis.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"Icon written: {OUT / 'ofis.ico'}")


if __name__ == "__main__":
    main()
