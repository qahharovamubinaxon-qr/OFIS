"""РАСМ-ФОТО: output size/ratio and the no-face fallback path."""

from __future__ import annotations

import io

from PIL import Image
from src.services.photo_service import (
    HEAD_AIR,
    HEAD_HEIGHT,
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


# ----------------------------------------------- head-and-shoulders framing
def _crop_box(face_h: int = 200, aspect: float = OUT_W / OUT_H):
    """Where the window lands for a face box of ``face_h`` in a 1000×1000 photo."""
    import cv2
    import numpy as np

    rgb = np.zeros((1000, 1000, 3), dtype="uint8")
    crop = PhotoService._document_crop(cv2, rgb, 400, 300, face_h, face_h, aspect)
    return crop.shape[0], crop.shape[1]


def test_the_window_is_head_and_a_little_shoulder() -> None:
    """The head must fill ~3/5 of the frame, not a third of it.

    The office crops these by hand this tight because the card windows are
    small; anything looser puts a face on the патент too small to check.
    """
    h, _w = _crop_box(face_h=200)
    assert h == int(round(200 * HEAD_HEIGHT))
    share = 200 / h
    assert 0.62 < share < 0.75, f"face box fills {share:.0%} of the frame"


def test_there_is_air_above_the_hair_but_not_a_field_of_it() -> None:
    """Enough that tall hair survives, little enough that it is not a landscape."""
    air = HEAD_AIR / HEAD_HEIGHT
    assert 0.08 < air < 0.18, f"air above is {air:.0%} of the frame"


def test_the_window_keeps_the_asked_for_shape() -> None:
    """Card windows are not all 3:4 — whatever is asked for is what comes back."""
    for aspect in (OUT_W / OUT_H, 0.75, 0.8):
        h, w = _crop_box(face_h=200, aspect=aspect)
        assert abs(w / h - aspect) < 0.02, f"{w}×{h} is not {aspect}"


def test_every_card_photo_goes_through_the_same_crop() -> None:
    """патент · бейджик · разрешение · сфера must not each invent a framing."""
    import re
    from pathlib import Path

    users = ("src/pdf/razreshenie_renderer.py", "src/services/beydjik_service.py",
             "src/services/patent_service.py", "src/services/svera_service.py")
    for path in users:
        source = Path(path).read_text(encoding="utf-8")
        assert re.search(r"\bprepare_portrait\s*\(", source), path


def test_the_cloud_retouch_stays_off_by_default() -> None:
    """It re-draws the sitter and once held the screen for twenty minutes."""
    from src.services.photo_service import AI_STUDIO

    assert AI_STUDIO is False
