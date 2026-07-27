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
    # the encoder returns 0 for dark and 255 for light
    return (np.asarray(grid) < 128).astype(np.uint8)


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
    """Draw ``text`` as a QR code filling ``rect`` (a fitz.Rect or 4-tuple).

    The white quiet zone is part of the image, so the box may be dropped
    straight onto artwork — nothing else needs clearing.
    """
    import fitz

    box = rect if isinstance(rect, fitz.Rect) else fitz.Rect(*rect)
    # aim for roughly 600 dpi at the printed size, so the modules stay square
    side_modules = modules(text).shape[0] + 2 * quiet
    target_px = max(1, int(box.width / 72 * 600))
    per_module = max(4, target_px // side_modules)
    page.insert_image(box, stream=png_bytes(text, pixels_per_module=per_module,
                                            quiet=quiet), overlay=True)
