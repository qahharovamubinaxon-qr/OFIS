"""U²-Net background removal: model plumbing, fallback and (when the model
file is present) real segmentation quality checks.

The model is never in git, so the segmentation tests run only when a model is
reachable — set ``OFIS_BG_MODEL`` or have one in AppData. Everything else
(fallback, colour table, output geometry) runs everywhere.
"""

from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from src.config import paths
from src.services.photo_service import BG_COLORS, OUT_DPI, OUT_H, OUT_W, PhotoService


@pytest.fixture(autouse=True)
def _isolated_appdata(monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", tempfile.mkdtemp())
    paths.data_dir.cache_clear()
    yield
    paths.data_dir.cache_clear()


def _model() -> str | None:
    p = os.environ.get("OFIS_BG_MODEL", "")
    return p if p and Path(p).exists() else None


def test_output_is_document_standard() -> None:
    assert (OUT_W, OUT_H) == (413, 531)  # 3×4 at 300 DPI
    assert OUT_DPI == 300
    assert set(BG_COLORS) == {"white", "gray", "blue"}
    assert BG_COLORS["white"] == (255, 255, 255)


def test_no_model_and_no_network_falls_back_quietly(monkeypatch) -> None:
    """Without a model the pipeline must still produce a photo (flood fill)."""
    from src.services import bg_segment

    monkeypatch.setenv("OFIS_BG_MODEL", "/nonexistent/model.onnx")
    rgb = np.full((200, 150, 3), 128, dtype=np.uint8)
    assert bg_segment.segment(rgb) is None  # env override missing → None

    buf = io.BytesIO()
    Image.new("RGB", (600, 900), (120, 140, 160)).save(buf, format="JPEG")
    result = PhotoService().process(buf.getvalue())
    img = Image.open(io.BytesIO(result.png))
    assert img.size == (OUT_W, OUT_H)


def test_model_catalogue_is_sane() -> None:
    from src.services.bg_segment import _BASE, MODELS

    assert _BASE.startswith("https://github.com/")
    names = [n for n, _ in MODELS]
    assert names[0] == "u2net_human_seg.onnx"  # quality model first
    assert "u2netp.onnx" in names


@pytest.mark.skipif(_model() is None, reason="no local u2net model (OFIS_BG_MODEL)")
def test_segmentation_masks_a_person_shape() -> None:
    from src.services import bg_segment

    # synthetic "portrait": dark torso+head on a light background
    rgb = np.full((400, 300, 3), 230, dtype=np.uint8)
    rgb[120:400, 90:210] = (40, 40, 60)     # torso
    rgb[40:140, 115:185] = (170, 140, 120)  # head
    mask = bg_segment.segment(rgb)
    assert mask is not None and mask.shape == (400, 300)
    assert mask[250, 150] > 128, "torso must be person"
    assert mask[20, 20] < 128, "corner must be background"


@pytest.mark.skipif(_model() is None, reason="no local u2net model (OFIS_BG_MODEL)")
@pytest.mark.parametrize("bg", ["white", "gray", "blue"])
def test_backdrop_is_repainted_to_the_chosen_colour(bg) -> None:
    import cv2

    rgb = np.full((531, 413, 3), 200, dtype=np.uint8)
    rgb[160:531, 120:290] = (40, 40, 60)
    rgb[60:190, 155:255] = (170, 140, 120)
    out, method = PhotoService._apply_background(cv2, rgb, bg)
    assert method == "u2net"
    target = np.array(BG_COLORS[bg])
    for corner in (out[3, 3], out[3, -4], out[45, 3]):
        assert np.abs(corner.astype(int) - target).max() <= 12, (bg, corner)
