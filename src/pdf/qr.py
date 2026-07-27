"""QR codes, drawn straight onto a PDF page — no extra dependency.

OpenCV, which the app already ships for the photo pipeline, carries a QR
encoder in its ``objdetect`` module. It returns the module grid as an image;
this module turns that into a crisp, quiet-zoned bitmap sized to the box it has
to fill, so a printed code scans at badge size.

Kept separate from :mod:`src.pdf.barcode` (Code 128) because the two share
nothing but their purpose.
"""

from __future__ import annotations

import io

from src.common.errors import OfisError
from src.common.logging import get_logger

log = get_logger(__name__)

# how many blank modules surround the code — the QR standard asks for 4, and
# scanners genuinely need them
QUIET_MODULES = 4


def available() -> bool:
    """True when this build of OpenCV can encode (it always should)."""
    try:
        import cv2
    except ImportError:  # pragma: no cover - cv2 ships with the app
        return False
    return hasattr(cv2, "QRCodeEncoder_create")


def modules(text: str):
    """The code as a 2-D array of 0/1 modules (1 = dark), without a quiet zone."""
    if not text:
        raise OfisError("QR-код учун матн бўш.")
    try:
        import cv2
        import numpy as np
    except ImportError as exc:  # pragma: no cover - both ship with the app
        raise OfisError("QR-код яратиб бўлмади (OpenCV топилмади).") from exc
    if not hasattr(cv2, "QRCodeEncoder_create"):
        raise OfisError("Бу OpenCV нусхаси QR-код ярата олмайди.")
    try:
        grid = cv2.QRCodeEncoder_create().encode(text)
    except cv2.error as exc:
        raise OfisError(
            "QR-код яратиб бўлмади — матн жуда узун бўлиши мумкин.") from exc
    # the encoder returns 0 for dark and 255 for light…
    dark = (np.asarray(grid) < 128).astype(np.uint8)
    # …and wraps the symbol in a two-module quiet zone of its own. Strip it, so
    # the caller sizes the code itself and decides on its own margin. Every QR
    # has finder patterns in three corners, so a blank outer row is always
    # padding and never part of the symbol.
    rows = np.where(dark.sum(1) > 0)[0]
    cols = np.where(dark.sum(0) > 0)[0]
    if len(rows) and len(cols):
        dark = dark[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]
    return dark


def _decodes(grid) -> bool:
    """True when the grid we just built reads back as a QR code.

    OpenCV's encoder occasionally emits a symbol its own detector cannot read —
    a rare payload-specific quirk, but a badge with an unreadable code is worse
    than useless, so every code is checked before it is drawn.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:  # pragma: no cover - both ship with the app
        return True
    padded = np.pad(grid, QUIET_MODULES, constant_values=0)
    image = np.where(padded > 0, 0, 255).astype(np.uint8)
    big = cv2.resize(image, (image.shape[1] * 8, image.shape[0] * 8),
                     interpolation=cv2.INTER_NEAREST)
    try:
        return bool(cv2.QRCodeDetector().detectAndDecode(big)[0])
    except cv2.error:  # pragma: no cover - detector gave up
        return False


def verified(text: str) -> tuple[object, str]:
    """(module grid, the text actually encoded) — readable back, if possible.

    When a payload produces a symbol that will not read, a trailing space is
    added and the code rebuilt: harmless to the text, and it moves the encoder
    off the pattern that tripped it.
    """
    candidate = text
    for attempt in range(3):
        grid = modules(candidate)
        if _decodes(grid):
            if attempt:
                log.info("QR rebuilt with %d trailing space(s) to stay readable",
                         attempt)
            return grid, candidate
        candidate += " "
    log.warning("QR for %r did not read back — drawing it anyway", text[:40])
    return modules(text), text


def png_bytes(text: str, *, pixels_per_module: int = 12,
              quiet: int = QUIET_MODULES) -> bytes:
    """The code as a black-on-white PNG, quiet zone included."""
    import numpy as np
    from PIL import Image

    grid = modules(text)
    padded = np.pad(grid, quiet, constant_values=0)
    image = np.where(padded > 0, 0, 255).astype(np.uint8)
    scaled = Image.fromarray(image, mode="L").resize(
        (image.shape[1] * pixels_per_module, image.shape[0] * pixels_per_module),
        resample=Image.NEAREST)
    buf = io.BytesIO()
    scaled.save(buf, format="PNG")
    return buf.getvalue()


def draw_qr(page, text: str, rect, *, quiet: int = QUIET_MODULES) -> None:
    """Draw ``text`` as a QR code whose **dark modules** fill ``rect``.

    The quiet zone is drawn *outside* ``rect``, so the code itself fills the
    frame it was given rather than sitting shrunken inside it. The zone is
    white and part of the image, so the result may be dropped straight onto
    artwork — nothing else needs clearing — at the cost of a thin white margin
    around the frame, which is what the standard's four modules amount to.
    """
    import fitz

    box = rect if isinstance(rect, fitz.Rect) else fitz.Rect(*rect)
    grid, text = verified(text)
    side = grid.shape[0]
    module = min(box.width, box.height) / side
    outer = fitz.Rect(box.x0 - quiet * module, box.y0 - quiet * module,
                      box.x0 + (side + quiet) * module,
                      box.y0 + (side + quiet) * module)
    # aim for roughly 600 dpi at the printed size, so the modules stay square
    per_module = max(4, int(outer.width / 72 * 600) // (side + 2 * quiet))
    page.insert_image(outer, stream=png_bytes(text, pixels_per_module=per_module,
                                              quiet=quiet), overlay=True)
