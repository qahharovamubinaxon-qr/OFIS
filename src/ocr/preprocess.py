"""Shrink a photo before sending it to the AI.

Phone passport/patent photos are 3–10 MB; uploading three of them per worker is
the main cause of slow OCR. Downscaling to ~1600 px on the long side and
re-encoding as JPEG q85 cuts each image to a few hundred KB with no loss of
readability, so a request that took minutes takes seconds. Returns the original
bytes unchanged if anything goes wrong (never blocks a generation).
"""

from __future__ import annotations

from io import BytesIO

from src.common.logging import get_logger

log = get_logger(__name__)

_MAX_SIDE = 1600
_QUALITY = 85


def prepare_image(data: bytes, max_side: int = _MAX_SIDE, quality: int = _QUALITY) -> bytes:
    try:
        from PIL import Image, ImageOps

        img = Image.open(BytesIO(data))
        img = ImageOps.exif_transpose(img)  # honour phone orientation
        img = img.convert("RGB")
        w, h = img.size
        longest = max(w, h)
        if longest > max_side:
            scale = max_side / longest
            img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
        out = BytesIO()
        img.save(out, format="JPEG", quality=quality, optimize=True)
        result = out.getvalue()
        log.info("Image %d KB → %d KB", len(data) // 1024, len(result) // 1024)
        return result
    except Exception as exc:  # noqa: BLE001 - preprocessing must never block OCR
        log.warning("Image preprocess skipped: %s", str(exc)[:100])
        return data
