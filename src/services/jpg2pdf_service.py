"""JPG→PDF — stack images into one PDF, in the order given.

Extracted from the desktop view so the Telegram bot can use the same code
(business logic never lives in ``src.ui``; see ARCHITECTURE.md §2).
"""

from __future__ import annotations

import io
from pathlib import Path

from src.common.errors import OfisError


def build_pdf(images: list[bytes]) -> bytes:
    """Return a PDF whose pages are ``images``, one image per page."""
    from PIL import Image, ImageOps

    pages = []
    for data in images:
        try:
            img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
        except OSError as exc:
            raise OfisError("Rasm o'qilmadi — boshqa fayl yuboring.") from exc
        pages.append(img)
    if not pages:
        raise OfisError("Kamida bitta rasm yuklang.")
    buf = io.BytesIO()
    pages[0].save(buf, format="PDF", save_all=True, append_images=pages[1:],
                  resolution=150)
    return buf.getvalue()


def build_pdf_from_paths(paths: list[str] | list[Path]) -> bytes:
    return build_pdf([Path(p).read_bytes() for p in paths])
