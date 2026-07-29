"""ДОКУМЕНТ — a phone photo of a document turned into a scan."""

from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image
from src.common.errors import OfisError
from src.services.doc_scan_service import (
    LANDSCAPE,
    MARGIN,
    PAGE_H,
    PAGE_W,
    _pages,
    build_pdf,
    scan_one,
)


def _photographed(width=900, height=1200, skew=70, card=(520, 330)) -> bytes:
    """A light document lying at an angle on a dark desk, as a phone would see it.

    The card carries dark bars so the warp has something to be judged on: if the
    perspective is undone the bars come out horizontal and evenly spaced.
    """
    import cv2

    desk = np.full((height, width, 3), 40, dtype="uint8")
    card_w, card_h = card
    page = np.full((card_h, card_w, 3), 235, dtype="uint8")
    for i in range(4):
        y = int(card_h * (0.18 + i * 0.2))
        cv2.rectangle(page, (int(card_w * 0.1), y),
                      (int(card_w * 0.9), y + 12), (30, 30, 30), -1)

    src = np.array([[0, 0], [card_w - 1, 0], [card_w - 1, card_h - 1],
                    [0, card_h - 1]], dtype="float32")
    cx, cy = width / 2, height / 2
    dst = np.array([
        [cx - card_w / 2 + skew, cy - card_h / 2],
        [cx + card_w / 2, cy - card_h / 2 - skew // 2],
        [cx + card_w / 2 - skew, cy + card_h / 2],
        [cx - card_w / 2, cy + card_h / 2 + skew // 2],
    ], dtype="float32")
    warped = cv2.warpPerspective(page, cv2.getPerspectiveTransform(src, dst),
                                 (width, height), borderValue=(40, 40, 40))
    desk = np.where(warped.sum(axis=2, keepdims=True) > 60, warped, desk)
    buf = io.BytesIO()
    Image.fromarray(desk).save(buf, format="JPEG", quality=92)
    return buf.getvalue()


# ------------------------------------------------------------------ finding
def test_the_document_is_cut_out_of_the_desk():
    """What comes back is the card, not the photograph of the card."""
    scan = scan_one(_photographed())
    assert scan.shape[0] * scan.shape[1] < 900 * 1200 * 0.75, "the desk came too"
    assert min(scan.shape[:2]) > 100


def test_the_perspective_is_undone_not_merely_cropped():
    """The card was shot as a trapezoid; it must come back a rectangle.

    Judged on the printed bars: after a true warp the top bar and the bottom
    bar span the same width. Under a plain crop the trapezoid survives and they
    do not.
    """
    scan = scan_one(_photographed())
    dark = scan[..., 0] < 120
    rows = [r for r in range(scan.shape[0]) if dark[r].sum() > scan.shape[1] * 0.4]
    assert len(rows) >= 30, "the printed bars were lost"
    top_bar, bottom_bar = dark[rows[0]].sum(), dark[rows[-1]].sum()
    assert abs(top_bar - bottom_bar) < scan.shape[1] * 0.12, \
        f"still a trapezoid: {top_bar} vs {bottom_bar}"


def test_a_photo_with_no_document_in_it_is_not_mangled():
    """No four corners to find → straighten at most, never invent a shape."""
    noise = np.random.default_rng(7).integers(0, 255, (400, 600, 3), dtype="uint8")
    buf = io.BytesIO()
    Image.fromarray(noise).save(buf, format="PNG")
    scan = scan_one(buf.getvalue())
    assert scan.shape[:2] == (400, 600)


def test_grayscale_is_grey_and_colour_stays_colour():
    colour = scan_one(_photographed(), grayscale=False)
    grey = scan_one(_photographed(), grayscale=True)
    assert np.allclose(grey[..., 0], grey[..., 2])
    assert grey.mean() > 60, "the photocopy came out black"
    assert colour.shape[2] == 3


# ------------------------------------------------------------------ layout
def test_landscape_documents_go_two_to_a_page():
    """A licence front and back belong on one sheet — that is how it is filed."""
    assert _pages([(800, 500), (800, 500)]) == [[0, 1]]
    assert _pages([(800, 500)] * 3) == [[0, 1], [2]]


def test_a_portrait_document_gets_the_page_to_itself():
    assert _pages([(600, 900)]) == [[0]]
    assert _pages([(600, 900), (800, 500), (800, 500)]) == [[0], [1, 2]]


def test_a_square_document_is_not_treated_as_landscape():
    assert LANDSCAPE > 1.0, "a square would otherwise be paired"
    assert _pages([(700, 700), (700, 700)]) == [[0], [1]]


# --------------------------------------------------------------------- pdf
def test_the_pdf_is_a4_with_white_all_round():
    import fitz

    pdf = build_pdf([_photographed()])
    doc = fitz.open("pdf", pdf)
    assert doc.page_count == 1
    page = doc[0]
    assert abs(page.rect.width / page.rect.height - PAGE_W / PAGE_H) < 0.02

    shot = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5))
    img = np.frombuffer(shot.samples, dtype="uint8").reshape(
        shot.height, shot.width, shot.n)
    edge = int(shot.height * MARGIN * 0.5)
    assert img[:edge].min() > 230, "the top margin is not white"
    assert img[-edge:].min() > 230, "the bottom margin is not white"


def test_two_licence_sides_land_on_one_page():
    import fitz

    both = [_photographed(card=(520, 330)), _photographed(card=(520, 330))]
    doc = fitz.open("pdf", build_pdf(both))
    assert doc.page_count == 1


def test_nothing_dropped_is_an_error_not_an_empty_pdf():
    with pytest.raises(OfisError):
        build_pdf([])


def test_an_unreadable_file_says_so():
    with pytest.raises(OfisError):
        build_pdf([b"this is not an image"])
