"""Finding a printed box on a page, and rendering a page for the operator.

The МВД blank draws its «Отметка о подтверждении» box as ink, not as vector
rectangles, so the box is found the way the eye finds it: by looking for the
long dark lines that bound the point of interest. Used to show the operator
exactly which box they are placing a value inside.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.common.errors import ValidationError

_DPI = 150
_INK = 170               # a border is much darker than a scan's paper
_MIN_H_PT = 120.0        # a box side worth calling a side
_MIN_V_PT = 40.0
_MAX_GAP_PT = 2.0        # a scanned line breaks up; close small holes


@dataclass(frozen=True)
class PageImage:
    """A rendered page, plus what one image pixel is worth in points."""

    png: bytes
    width_pt: float
    height_pt: float
    width_px: int
    height_px: int

    def to_points(self, px: float, py: float) -> tuple[float, float]:
        return (px * self.width_pt / self.width_px,
                py * self.height_pt / self.height_px)

    def to_pixels(self, x: float, y: float) -> tuple[float, float]:
        return (x * self.width_px / self.width_pt,
                y * self.height_px / self.height_pt)


def render(pdf: Path, page: int, *, dpi: int = _DPI) -> PageImage:
    """Render one 1-based page as PNG bytes."""
    import fitz

    try:
        doc = fitz.open(str(pdf))
    except Exception as exc:  # noqa: BLE001 - not a PDF / unreadable
        raise ValidationError("PDF ўқилмади", context={"path": str(pdf)}) from exc
    try:
        if not 1 <= page <= len(doc):
            raise ValidationError("Бундай бет йўқ",
                                  context={"page": page, "pages": len(doc)})
        p = doc[page - 1]
        pix = p.get_pixmap(dpi=dpi)
        return PageImage(png=pix.tobytes("png"),
                         width_pt=p.rect.width, height_pt=p.rect.height,
                         width_px=pix.width, height_px=pix.height)
    finally:
        doc.close()


def _runs(mask, min_len: int, max_gap: int) -> list[tuple[int, int]]:
    """Stretches of True, forgiving gaps of up to ``max_gap`` pixels."""
    import numpy as np

    idx = np.flatnonzero(mask)
    if not len(idx):
        return []
    out: list[tuple[int, int]] = []
    start = prev = int(idx[0])
    for raw in idx[1:]:
        i = int(raw)
        if i - prev > max_gap + 1:
            if prev - start + 1 >= min_len:
                out.append((start, prev))
            start = i
        prev = i
    if prev - start + 1 >= min_len:
        out.append((start, prev))
    return out


def enclosing_box(pdf: Path, page: int, point: tuple[float, float],
                  *, dpi: int = _DPI) -> tuple[float, float, float, float] | None:
    """The printed box around ``point`` (x0, y0, x1, y1 in points), or None.

    None when the page has no such box — the operator then places the value by
    eye on the page itself, which is the picture in front of them anyway.
    """
    import fitz
    import numpy as np

    scale = 72.0 / dpi
    try:
        doc = fitz.open(str(pdf))
    except Exception:  # noqa: BLE001
        return None
    try:
        if not 1 <= page <= len(doc):
            return None
        pix = doc[page - 1].get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
        ink = (np.frombuffer(pix.samples, np.uint8)
               .reshape(pix.height, pix.width)) < _INK
    finally:
        doc.close()

    px, py = point[0] / scale, point[1] / scale
    gap = max(1, int(_MAX_GAP_PT / scale))
    min_h, min_v = int(_MIN_H_PT / scale), int(_MIN_V_PT / scale)

    above = below = left = right = None
    for y in range(ink.shape[0]):
        for a0, a1 in _runs(ink[y], min_h, gap):
            if a0 <= px <= a1:
                if y <= py and (above is None or y > above[0]):
                    above = (y, a0, a1)
                if y >= py and below is None:
                    below = (y, a0, a1)
    if above is None or below is None or above[0] == below[0]:
        return None

    for x in range(ink.shape[1]):
        for b0, b1 in _runs(ink[:, x], min_v, gap):
            if b0 <= py <= b1:
                if x <= px and (left is None or x > left):
                    left = x
                if x >= px and right is None:
                    right = x
    if left is None or right is None or left == right:
        return None

    return (left * scale, above[0] * scale, right * scale, below[0] * scale)
