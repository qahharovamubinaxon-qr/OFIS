"""Generate the OFIS logo — the app icon and the full wordmark lockup.

The mark is a sheet of paper with a stamp struck across it, and the stamp's
face is a clock: that is the whole program in one drawing — a document, filled
and stamped, at any hour. It is the same mark the sidebar paints
(:mod:`src.ui.widgets.brand_mark`), so the icon on the taskbar, the icon on the
EXE and the mark inside the window are one thing rather than three.

Colours come from the program's own house palette (:mod:`src.ui.theme`): the
cream it sets ink in, the navy those forms are printed in, and the pale blue
the house sections are written in. Deliberately NOT a blue gradient document —
every program on the machine has one of those.

Everything is drawn at 4× and downsampled, so the curves are clean at 16 px.
Deterministic: rerun whenever the design changes; the results are committed so
building the EXE never needs PIL.

    python scripts/make_icon.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "resources" / "icons"
FONTS = ROOT / "resources" / "fonts"

# -- the house palette, taken from src/ui/theme.py ------------------------
GROUND = (18, 26, 38)          # #121A26 — house ink, the dark ground
GROUND_TOP = (28, 40, 57)      # a touch lighter at the top: paper under light
PAPER = (244, 241, 236)        # the sheet
RULE = (176, 190, 209)         # the typed lines on it
STAMP = (47, 85, 128)          # #2F5580 — the navy these forms are printed in
ACCENT = (168, 190, 220)       # #A8BEDC — what the house sections are written in
MUTED = (142, 139, 150)        # #8E8B96 — the byline

#: Drawn this big, then downsampled. 4× of 512.
S = 2048
SS = S // 512                  # scale factor from the 512-px design grid


def _px(*values: float) -> tuple[float, ...]:
    """Design-grid coordinates (512) to canvas pixels."""
    return tuple(v * SS for v in values)


# ------------------------------------------------------------------- mark


def draw_mark(img: Image.Image, box: tuple[float, float, float, float],
              *, paper: tuple[int, int, int] = PAPER,
              rule: tuple[int, int, int] = RULE,
              stamp: tuple[int, int, int] = STAMP) -> None:
    """The sheet with the clock-stamp, fitted into ``box`` (canvas pixels).

    Drawn on its own so the icon and the wordmark lockup share one mark; if it
    is ever redrawn, both change together.
    """
    d = ImageDraw.Draw(img)
    left, top, right, bottom = box
    w, h = right - left, bottom - top

    # the sheet: upright, a little narrower than tall, softly cornered. It
    # stops short of the bottom so the stamp has somewhere to hang over.
    sheet = (left, top, left + w * 0.70, top + h * 0.90)
    d.rounded_rectangle(sheet, radius=w * 0.055, fill=paper)

    # what is typed on it — three rules, the last one short, as text ends
    sx0, sy0, sx1, sy1 = sheet
    sw, sh = sx1 - sx0, sy1 - sy0
    thick = sh * 0.052
    for y, share in ((0.17, 0.66), (0.32, 0.66), (0.47, 0.40)):
        y0 = sy0 + sh * y
        d.rounded_rectangle((sx0 + sw * 0.17, y0,
                             sx0 + sw * 0.17 + sw * share, y0 + thick),
                            radius=thick / 2, fill=rule)

    # the stamp: struck across the lower corner, half on the sheet and half
    # off it — the way a real one lands, and it keeps the silhouette readable
    # when the icon is 16 px wide.
    # Everything here is deliberately heavy: at 16 px the whole stamp is
    # about five pixels across, and a fine ring turns to grey mush there.
    size = w * 0.58
    cx, cy = left + w * 0.64, bottom - size / 2.0
    ring = (cx - size / 2, cy - size / 2, cx + size / 2, cy + size / 2)
    d.ellipse(ring, fill=paper)                      # struck onto paper
    d.ellipse(ring, outline=stamp, width=int(size * 0.105))
    inner = size * 0.30
    d.ellipse((cx - inner, cy - inner, cx + inner, cy + inner),
              outline=stamp, width=int(size * 0.052))

    # the stamp's face is a clock — the program's «24/7»
    hand = max(2.0, size * 0.052)
    d.line((cx, cy, cx, cy - inner * 0.72), fill=stamp, width=int(hand))
    d.line((cx, cy, cx + inner * 0.55, cy), fill=stamp, width=int(hand))


# ------------------------------------------------------------------- icon


def build_icon() -> Image.Image:
    """The square app icon: the mark on the house ground."""
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    ground = Image.new("RGBA", (S, S))
    gd = ImageDraw.Draw(ground)
    for y in range(S):
        t = y / S
        gd.line([(0, y), (S, y)],
                fill=tuple(int(GROUND_TOP[i] + (GROUND[i] - GROUND_TOP[i]) * t)
                           for i in range(3)) + (255,))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1),
                                           radius=S * 0.22, fill=255)
    img.paste(ground, (0, 0), mask)

    # ~60% of the frame, the share a Windows icon glyph wants, and nudged
    # right because the stamp hangs off the sheet's right-hand side.
    draw_mark(img, _px(112, 103, 418, 409))
    return img


# --------------------------------------------------------------- wordmark


def _spaced(d: ImageDraw.ImageDraw, xy: tuple[float, float], text: str,
            font: ImageFont.FreeTypeFont, fill, tracking: float) -> float:
    """Draw letter-spaced text, returning where the next glyph would start.

    Pillow has no tracking, and the wordmark needs it: «OFIS 24/7» set solid
    reads as a word, spaced out it reads as a mark.
    """
    x, y = xy
    for char in text:
        d.text((x, y), char, font=font, fill=fill)
        x += d.textlength(char, font=font) + tracking
    return x


def build_lockup(*, ink: tuple[int, int, int], muted: tuple[int, int, int],
                 paper: tuple[int, int, int], rule: tuple[int, int, int],
                 stamp: tuple[int, int, int]) -> Image.Image:
    """The full logo: mark, «OFIS 24/7», «by MUSTAFO». Transparent ground."""
    width, height = S * 2, int(S * 0.62)
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    mark = height * 0.78
    mx, my = height * 0.10, (height - mark) / 2
    draw_mark(img, (mx, my, mx + mark, my + mark),
              paper=paper, rule=rule, stamp=stamp)

    d = ImageDraw.Draw(img)
    big = ImageFont.truetype(str(FONTS / "OfisSans-Bold.ttf"), int(height * 0.30))
    small = ImageFont.truetype(str(FONTS / "OfisSans-Regular.ttf"),
                               int(height * 0.115))

    text_x = mx + mark + height * 0.15
    top = height * 0.20
    end = _spaced(d, (text_x, top), "OFIS", big, ink, height * 0.030)
    _spaced(d, (end + height * 0.055, top), "24/7", big, stamp, height * 0.030)

    # the byline sits under the wordmark, quiet: it says who made the program,
    # it is not the program's name.
    _spaced(d, (text_x + height * 0.012, height * 0.615), "by MUSTAFO", small,
            muted, height * 0.038)

    # trimmed to the artwork, then given clear space back: a logo pasted onto
    # a page with its glyphs flush to the edge always looks like a mistake.
    box = img.getbbox()
    pad = int(height * 0.06)
    return img.crop((box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    icon = build_icon()
    icon.resize((256, 256), Image.LANCZOS).save(OUT / "ofis_256.png")
    icon.resize((256, 256), Image.LANCZOS).save(
        OUT / "ofis.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128),
               (256, 256)])

    # on the dark sidebar / dark README
    dark = build_lockup(ink=(232, 230, 227), muted=MUTED, paper=PAPER,
                        rule=RULE, stamp=ACCENT)
    dark.resize((dark.width // 2, dark.height // 2), Image.LANCZOS).save(
        OUT / "ofis_logo_dark.png")

    # on white paper — the printed ink, not the pastel
    light = build_lockup(ink=(27, 26, 24), muted=(110, 106, 98), paper=PAPER,
                         rule=RULE, stamp=STAMP)
    light.resize((light.width // 2, light.height // 2), Image.LANCZOS).save(
        OUT / "ofis_logo.png")

    for name in ("ofis.ico", "ofis_256.png", "ofis_logo.png",
                 "ofis_logo_dark.png"):
        print(f"  {name}")
    print(f"Written to {OUT}")


if __name__ == "__main__":
    main()
