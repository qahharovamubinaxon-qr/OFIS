"""РАСМ-ФОТО: output size/ratio and the no-face fallback path."""

from __future__ import annotations

import io

from PIL import Image

from src.services.photo_service import (
    OUT_H,
    OUT_W,
    STUDIO_HI,
    STUDIO_LO,
    PhotoService,
)


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


# ------------------------------------------------- the «studio» backdrop
def test_the_studio_sweep_is_bright_behind_the_head_and_falls_off() -> None:
    """A sweep, not a flat wall: brightest behind the head, darkest at a corner."""
    import numpy as np

    sweep = PhotoService._studio_backdrop(np, 531, 413)
    head = float(sweep[159, 206, 0])          # 0.30h, 0.50w — the bright spot
    corner = float(sweep[530, 0, 0])
    assert head > corner + 25, "the backdrop has no falloff"
    assert STUDIO_LO - 1 <= corner <= STUDIO_HI
    assert head <= STUDIO_HI


def test_the_studio_sweep_is_neutral_grey() -> None:
    """R, G and B must stay equal — a tinted backdrop pulls the skin with it."""
    import numpy as np

    sweep = PhotoService._studio_backdrop(np, 200, 150)
    assert np.allclose(sweep[..., 0], sweep[..., 1])
    assert np.allclose(sweep[..., 1], sweep[..., 2])


def test_the_shadow_only_ever_darkens() -> None:
    import cv2
    import numpy as np

    sweep = PhotoService._studio_backdrop(np, 120, 90)
    alpha = np.zeros((120, 90, 1), dtype=np.float32)
    alpha[40:, 25:65] = 1.0                   # a block of "person"
    shaded = PhotoService._cast_shadow(cv2, np, sweep, alpha, 120, 90)
    assert (shaded <= sweep + 1e-4).all(), "a shadow that brightens is a bug"
    assert shaded.min() < sweep.min(), "the shadow never landed"


def test_studio_is_offered_and_has_a_flat_fallback_colour() -> None:
    """Every backdrop the screen offers must be a key the service knows."""
    from src.services.photo_service import BG_COLORS

    assert "studio" in BG_COLORS
    r, g, b = BG_COLORS["studio"]
    assert r == g == b, "the fallback colour must be neutral too"


def test_studio_photo_is_still_a_document_3x4() -> None:
    result = PhotoService().process(_photo_bytes(1200, 900), bg="studio")
    img = Image.open(io.BytesIO(result.png))
    assert img.size == (OUT_W, OUT_H)
