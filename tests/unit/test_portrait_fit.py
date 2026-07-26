"""Portrait fitting: any upload is cropped to the target frame's aspect."""

from __future__ import annotations

import io

import pytest

pytest.importorskip("cv2")

from PIL import Image  # noqa: E402

from src.pdf.svera_udo import PHOTO_ASPECT, PHOTO_BOX  # noqa: E402
from src.services.photo_service import prepare_portrait  # noqa: E402


def _jpeg(width: int, height: int) -> bytes:
    """A plain photo-sized image (no face — exercises the centre-crop path)."""
    img = Image.new("RGB", (width, height), (120, 140, 160))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_frame_aspect_matches_the_certificate_box() -> None:
    x0, y0, x1, y1 = PHOTO_BOX
    assert PHOTO_ASPECT == pytest.approx((x1 - x0) / (y1 - y0))
    # the certificate frame is wider than a plain 3:4 portrait
    assert PHOTO_ASPECT > 0.75


@pytest.mark.parametrize(("w", "h"), [(339, 451), (1200, 900), (600, 600), (480, 1040)])
def test_any_upload_is_cropped_to_the_frame(w: int, h: int) -> None:
    png = prepare_portrait(_jpeg(w, h), aspect=PHOTO_ASPECT, height=400)
    assert png, "portrait preparation returned nothing"
    out = Image.open(io.BytesIO(png))
    assert out.width / out.height == pytest.approx(PHOTO_ASPECT, abs=0.01)
    assert out.height == 400


def test_unreadable_upload_is_refused_quietly() -> None:
    assert prepare_portrait(b"not an image", aspect=PHOTO_ASPECT) is None


def test_default_aspect_is_the_3x4_document_ratio() -> None:
    png = prepare_portrait(_jpeg(800, 600), height=400)
    assert png
    out = Image.open(io.BytesIO(png))
    assert out.width / out.height == pytest.approx(0.75, abs=0.01)
