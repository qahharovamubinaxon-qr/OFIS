"""Finishing a cut-out document the way the office's own scanner does.

The office runs a document scanner at ``qrixtools.com/document-scanner``. It
has no API — the page says so itself, and every endpoint on that host answers
404 except the short-link one OFIS already uses — so what it does is done
here instead, on the machine, where a passport never leaves the building.

Two things it does that a plain crop does not:

**The light is evened out.** A document photographed by hand carries the room
with it: a shadow down one side from the person holding the phone, a bright
patch where the window is. The paper is not one colour any more, and the eye
reads that as a bad copy. The cure is to estimate the lighting — blur the
picture until the print disappears and only the illumination is left — and
divide it back out. What remains is the paper as it would look under even
light, with the print untouched.

**The size is the document's own.** A patent card is 85.6×54mm whatever
distance it was photographed from, and a passport page is 125×88mm. Snapping
the finished picture to the real size at 300 dpi means a card printed from it
comes out a card, and two documents of the same kind always come out the same
size — which is what makes a folder of them look like scans rather than
snapshots.

Nothing here finds or straightens the document; that is
:mod:`src.services.doc_scan_service`'s work, and this runs after it.
"""

from __future__ import annotations

from src.common.logging import get_logger

log = get_logger(__name__)

#: Print resolution. The office's scanner uses 300 dpi and so does this: it is
#: what makes a passport number readable on paper.
DPI = 300
_MM = 25.4

#: The documents the office actually handles, in millimetres, each given the
#: way round it is usually photographed. ID-1 is the bank-card size every
#: patent card, driving licence and residence card shares.
SIZES: dict[str, tuple[float, float]] = {
    "id1": (85.6, 54.0),            # патент картаси, айди, ҳайдовчилик
    "passport": (125.0, 88.0),      # паспортнинг битта бети
    "passport_spread": (125.0, 176.0),   # очилган паспорт — икки бет
    "a5": (148.0, 210.0),
    "a4": (210.0, 297.0),
}

#: How far a picture's shape may sit from a standard one and still be called
#: it. Two percent covers the margin a cut leaves; more than that and the
#: guess would start reshaping documents into something they are not.
TOLERANCE = 0.04

#: Anything not close to a standard shape is left at its own shape, sized so
#: the long side is this. Big enough that no viewer has to enlarge it.
FALLBACK_LONG = 3500

#: How wide the blur that estimates the lighting is, as a share of the
#: picture. It has to be far wider than any printing — otherwise the letters
#: themselves are read as shadow and get scrubbed out — and narrower than the
#: shadow it is meant to remove.
_LIGHT_SPREAD = 0.12
#: How far the evening is taken. All the way to 1.0 bleaches a passport's pale
#: guilloche off the page; this keeps the tint and loses the shadow.
_STRENGTH = 0.80


def pixels(name: str, dpi: int = DPI) -> tuple[int, int]:
    """A standard size in pixels — «id1» at 300 dpi is 1011×638."""
    wide, tall = SIZES[name]
    return round(wide / _MM * dpi), round(tall / _MM * dpi)


def even_lighting(rgb, strength: float = _STRENGTH):
    """The shadow off the paper, the print left where it is.

    Works on brightness alone, in LAB, so the document keeps its colour — a
    passport's pink and blue guilloche is part of how a real one is told from
    a copy, and turning it grey would be a loss.
    """
    import cv2
    import numpy as np

    height, width = rgb.shape[:2]
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    light = lab[:, :, 0].astype(np.float32)

    spread = max(3, int(min(height, width) * _LIGHT_SPREAD)) | 1
    illumination = cv2.GaussianBlur(light, (spread, spread), 0)
    illumination = np.maximum(illumination, 1.0)

    # The paper's own brightness, taken high up the range so print and shadow
    # do not drag it down.
    paper = float(np.percentile(illumination, 90))
    evened = light * (paper / illumination)
    lab[:, :, 0] = np.clip(light + (evened - light) * strength,
                           0, 255).astype(np.uint8)
    return cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)


def nearest_size(width: int, height: int) -> tuple[str, int, int] | None:
    """Which standard document this is the shape of, and its size in pixels.

    ``None`` when it is not the shape of any of them — better to leave a
    document at its own proportions than to stretch it into a card.
    """
    shape = width / height if height else 0.0
    if shape <= 0:
        return None
    best: tuple[float, str, int, int] | None = None
    for name in SIZES:
        wide, tall = pixels(name)
        for side_w, side_h in ((wide, tall), (tall, wide)):   # either way up
            off = abs(side_w / side_h - shape) / shape
            if off <= TOLERANCE and (best is None or off < best[0]):
                best = (off, name, side_w, side_h)
    if best is None:
        return None
    return best[1], best[2], best[3]


def official_size(rgb, min_long: int = 0):
    """The document at its real size, or at a good resolution if unrecognised.

    ``min_long`` raises the whole thing, proportionally, until its long side
    reaches that many pixels. The SHAPE is what the standard sizes are for —
    a card comes out card-shaped whatever angle it was photographed at — and
    the shape survives being scaled. Some callers need more pixels than 300
    dpi gives: a passport spread at 300 dpi is 1476 wide, and АМИНА's app
    will not enlarge a picture smaller than its frame.
    """
    from PIL import Image

    height, width = rgb.shape[:2]
    picture = Image.fromarray(rgb)
    match = nearest_size(width, height)
    if match is not None:
        name, wide, tall = match
        log.info("Ҳужжат ўлчами: %s — %d×%d px (%d dpi)", name, wide, tall, DPI)
    else:
        wide, tall = width, height
        scale = FALLBACK_LONG / max(width, height)
        if scale > 1:
            wide, tall = round(width * scale), round(height * scale)

    if min_long:
        lift = min_long / max(wide, tall)
        if lift > 1:
            wide, tall = round(wide * lift), round(tall * lift)

    if (wide, tall) == (width, height):
        return picture
    return picture.resize((max(1, wide), max(1, tall)), Image.LANCZOS)


def finish(rgb, min_long: int = 0):
    """Even the light, then size it — the whole finishing pass, as a PIL image."""
    return official_size(even_lighting(rgb), min_long=min_long)


__all__ = ["DPI", "FALLBACK_LONG", "SIZES", "TOLERANCE", "even_lighting",
           "finish", "nearest_size", "official_size", "pixels"]
