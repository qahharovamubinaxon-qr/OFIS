"""РАСМ-ФОТО: output size/ratio and the no-face fallback path."""

from __future__ import annotations

import io

from PIL import Image

from src.services.photo_service import OUT_H, OUT_W, PhotoService


def _photo_bytes(w: int, h: int, color=(120, 140, 160)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="JPEG")
    return buf.getvalue()


def test_no_face_fallback_is_3x4() -> None:
    result = PhotoService().process(_photo_bytes(1200, 900))
    assert not result.face_found
    img = Image.open(io.BytesIO(result.png))
    assert img.size == (OUT_W, OUT_H)  # 600×800 = 3:4


def test_portrait_input_also_3x4() -> None:
    result = PhotoService().process(_photo_bytes(700, 1600))
    img = Image.open(io.BytesIO(result.png))
    assert img.size == (OUT_W, OUT_H)
