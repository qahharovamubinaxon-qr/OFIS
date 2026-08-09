"""Finishing a cut-out document the way the office's own scanner does.

The office asked for `qrixtools.com/document-scanner`'s behaviour inside
OFIS. That site has no API — it says so itself, and every endpoint on the
host answers 404 bar the short-link one — so what it does is done here, and
these are the two things it does that a plain crop does not: it takes the
room's shadow off the paper, and it sets the picture to the document's real
size.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image
from src.services import doc_enhance as enhance


def _lit(width: int = 900, height: int = 1200, *, shadow: bool = True):
    """A printed page photographed with a shadow across one side of it."""
    from PIL import ImageDraw

    page = Image.new("RGB", (width, height), (248, 247, 243))
    draw = ImageDraw.Draw(page)
    for row in range(14):                       # printing, evenly spread
        y = int(height * 0.08) + row * int(height * 0.06)
        draw.line([(int(width * 0.1), y), (int(width * 0.9), y)],
                  fill=(40, 45, 60), width=4)
    grid = np.asarray(page).astype(np.float32)
    if shadow:
        # a smooth fall-off from left to right — the hand holding the phone
        ramp = np.linspace(0.55, 1.0, width, dtype=np.float32)
        grid *= ramp[None, :, None]
    return np.clip(grid, 0, 255).astype(np.uint8)


def _unevenness(rgb) -> float:
    """How much the paper's brightness wanders across the picture."""
    import cv2

    grey = np.asarray(Image.fromarray(rgb).convert("L")).astype(np.float32)
    spread = max(3, int(min(grey.shape) * 0.12)) | 1
    return float(cv2.GaussianBlur(grey, (spread, spread), 0).std())


# ------------------------------------------------------------ the light
def test_the_shadow_the_phone_cast_is_taken_off_the_paper() -> None:
    lit = _lit()
    before = _unevenness(lit)
    after = _unevenness(enhance.even_lighting(lit))
    assert before > 20, "тест расмида соя йўқ — текширадиган нарса қолмади"
    assert after < before / 2, f"соя қолди: {before:.1f} → {after:.1f}"


def test_an_evenly_lit_page_is_left_as_it_was() -> None:
    flat = _lit(shadow=False)
    assert _unevenness(enhance.even_lighting(flat)) < 6


def test_the_print_survives_the_evening() -> None:
    """Blur wide enough to find the shadow must not swallow the letters."""
    evened = enhance.even_lighting(_lit())
    grey = np.asarray(Image.fromarray(evened).convert("L"))
    assert grey.min() < 110, "босма ювилиб кетди"
    assert grey.max() > 215, "қоғоз оқармади"


def test_a_document_keeps_its_colour() -> None:
    """A passport's pink and blue guilloche is how a real one is told from a
    copy — the evening works on brightness alone and must not grey it."""
    tinted = _lit()
    tinted[:, :, 0] = np.clip(tinted[:, :, 0].astype(int) + 22, 0, 255)
    evened = enhance.even_lighting(tinted)
    red, blue = evened[:, :, 0].astype(int), evened[:, :, 2].astype(int)
    assert (red - blue).mean() > 8, "ранг йўқолди"


# ------------------------------------------------------------- the size
def test_the_standard_sizes_are_the_real_ones_at_300_dpi() -> None:
    assert enhance.pixels("id1") == (1011, 638)         # 85.6×54 mm
    assert enhance.pixels("a4") == (2480, 3508)         # 210×297 mm
    assert enhance.pixels("passport") == (1476, 1039)   # 125×88 mm


def test_a_card_is_recognised_whichever_way_up_it_is() -> None:
    wide, tall = enhance.pixels("id1")
    assert enhance.nearest_size(wide, tall)[0] == "id1"
    assert enhance.nearest_size(tall, wide)[0] == "id1"
    # and the answer comes back the way round it was asked
    assert enhance.nearest_size(tall, wide)[1:] == (tall, wide)


def test_a_shape_belonging_to_nothing_is_left_alone() -> None:
    """Better an odd document at its own proportions than one stretched
    into a card it never was."""
    assert enhance.nearest_size(1000, 300) is None
    assert enhance.nearest_size(0, 0) is None


def test_a_recognised_document_comes_out_its_real_size() -> None:
    card = _lit(1300, 830)                       # roughly ID-1, photographed
    assert enhance.official_size(card).size == enhance.pixels("id1")


def test_an_unrecognised_one_is_still_made_big_enough_to_read() -> None:
    odd = _lit(400, 130)
    assert max(enhance.official_size(odd).size) == enhance.FALLBACK_LONG


def test_the_shape_is_kept_when_a_caller_needs_more_pixels() -> None:
    """АМИНА needs 3500 px: its app will not enlarge anything smaller than
    the frame. The standard sizes are for the SHAPE, and shape scales."""
    spread = _lit(845, 1143)                     # a passport spread as cut
    exact = enhance.official_size(spread)
    bigger = enhance.official_size(spread, min_long=3500)
    assert exact.size == enhance.pixels("passport_spread")
    assert max(bigger.size) == 3500
    assert bigger.width / bigger.height == pytest.approx(
        exact.width / exact.height, abs=0.002)


def test_a_picture_already_big_enough_is_not_blown_up() -> None:
    big = _lit(4000, 1200)
    assert enhance.official_size(big).size == (4000, 1200)


def test_finishing_does_both_at_once() -> None:
    card = _lit(1300, 830)
    done = enhance.finish(card)
    assert done.size == enhance.pixels("id1")
    assert _unevenness(np.asarray(done.convert("RGB"))) < 20
