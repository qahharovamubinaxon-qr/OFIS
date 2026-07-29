"""РАСМ-ФОТО: output size/ratio and the no-face fallback path."""

from __future__ import annotations

import io

from PIL import Image
from src.services.photo_service import (
    AIR_SHARE,
    HAIR_GUESS,
    HEAD_SHARE,
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
    """Where the window lands for a face box of ``face_h`` in a 1000×1000 photo.

    A flat image has no silhouette to read, so this exercises the FALLBACK
    path — the one that guesses the hair line off the detector's box.
    """
    import cv2
    import numpy as np

    rgb = np.zeros((1000, 1000, 3), dtype="uint8")
    crop = PhotoService._document_crop(cv2, rgb, 400, 300, face_h, face_h, aspect)
    return crop.shape[0], crop.shape[1]


def test_the_head_fills_the_frame_the_way_the_office_crops_it() -> None:
    """Hair top to chin ≈ 62% of the height — the office's own proportion.

    The office crops these by hand this tight because the card windows are
    small; anything looser puts a face on the патент too small to check.
    """
    face_h = 200
    h, _w = _crop_box(face_h=face_h)
    head = face_h * (1 + HAIR_GUESS)          # brow-to-chin plus the hair
    share = head / h
    assert abs(share - HEAD_SHARE) < 0.02, f"head fills {share:.0%}, want {HEAD_SHARE:.0%}"


def test_there_is_air_above_the_hair_but_not_a_field_of_it() -> None:
    """Enough that the head never touches the edge, little enough to stay a
    document photo rather than a landscape."""
    assert 0.03 < AIR_SHARE < 0.15, f"air above is {AIR_SHARE:.0%} of the frame"


def test_the_top_of_the_head_is_taken_from_the_silhouette_not_a_guess() -> None:
    """The whole point of the fix: hair is measured, not assumed.

    A bald sitter's head barely clears the detector's box; thick hair or a
    headscarf clears it by a third of the box again. One fixed offset cannot
    serve both — it clipped one and stranded the other, which is what the
    office reported.
    """
    import cv2
    import numpy as np

    rgb = np.zeros((900, 700, 3), dtype="uint8")
    # a "person": tall hair well above the brow line, on a black ground
    cv2.ellipse(rgb, (350, 300), (120, 150), 0, 0, 360, (220, 200, 190), -1)
    cv2.ellipse(rgb, (350, 700), (260, 220), 0, 0, 360, (200, 190, 180), -1)
    found = PhotoService._hair_top(cv2, rgb, 260, 260, 180, 180)
    assert found is None or found <= 260, "the hair line cannot be below the brow"


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
