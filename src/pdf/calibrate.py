"""Auto-calibration: detect character-grid rows on a raster template.

The МВД form is a scanned image — its boxes are pixels, not PDF fields. This
module finds each row of equal cells with OpenCV (vertical-line projection),
converting pixel positions to PDF points, so a grid field's ``x0``/``pitch``/
``max_cells`` are measured, not guessed. It is the engineering core of
FIELD_MAPPING.md's "Visual Mapping Editor / automatic coordinate detection".

Usage (dev): ``GridRow`` results are reviewed and assigned a field id, then
written into ``mapping.vN.json``.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import fitz  # PyMuPDF
import numpy as np


@dataclass(frozen=True)
class GridRow:
    """A detected row of equal cells, in PDF points (origin top-left)."""

    page: int
    y_top: float
    y_bottom: float
    x0: float  # center-x of the first cell
    pitch: float  # cell-to-cell spacing
    max_cells: int

    def baseline(self) -> float:
        """A sensible text baseline: ~72% down the cell height."""
        return self.y_top + (self.y_bottom - self.y_top) * 0.72


def _render_gray(page: fitz.Page, dpi: int) -> tuple[np.ndarray, float]:
    pix = page.get_pixmap(dpi=dpi)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if pix.n >= 3 else img[:, :, 0]
    scale = 72.0 / dpi  # px → pt
    return gray, scale


def detect_grid_rows(
    page: fitz.Page,
    page_index: int,
    *,
    dpi: int = 200,
    min_cells: int = 4,
    min_cell_px: int = 14,
) -> list[GridRow]:
    """Find rows of equally-spaced boxes on a page.

    Strategy: binarize → isolate vertical strokes with a tall morphological
    kernel → group them into horizontal bands (rows) → within each band, read
    the x of every vertical divider, keep rows whose dividers are evenly spaced.
    """
    gray, scale = _render_gray(page, dpi)
    inv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(12, min_cell_px)))
    vertical = cv2.morphologyEx(inv, cv2.MORPH_OPEN, v_kernel)

    # Band the page into horizontal strips that contain vertical strokes.
    row_has_ink = vertical.sum(axis=1) > (min_cell_px * 255)
    bands = _contiguous_bands(row_has_ink, min_height=min_cell_px)

    rows: list[GridRow] = []
    for top, bottom in bands:
        strip = vertical[top:bottom, :]
        col_profile = strip.sum(axis=0)
        xs = _peaks(col_profile, min_gap=min_cell_px // 2)
        if len(xs) < min_cells + 1:
            continue
        gaps = np.diff(xs)
        pitch_px = float(np.median(gaps))
        if pitch_px < min_cell_px:
            continue
        # Keep only the evenly-spaced run (tolerate ±25% jitter).
        even = np.abs(gaps - pitch_px) < pitch_px * 0.25
        run = _longest_run(even)
        if run[1] - run[0] < min_cells:
            continue
        first_line = xs[run[0]]
        cells = run[1] - run[0]
        x0_px = first_line + pitch_px / 2  # center of first cell
        rows.append(
            GridRow(
                page=page_index,
                y_top=top * scale,
                y_bottom=bottom * scale,
                x0=round(x0_px * scale, 2),
                pitch=round(pitch_px * scale, 2),
                max_cells=int(cells),
            )
        )
    return rows


def _contiguous_bands(mask: np.ndarray, min_height: int) -> list[tuple[int, int]]:
    bands: list[tuple[int, int]] = []
    start: int | None = None
    for i, on in enumerate(mask):
        if on and start is None:
            start = i
        elif not on and start is not None:
            if i - start >= min_height:
                bands.append((start, i))
            start = None
    if start is not None and len(mask) - start >= min_height:
        bands.append((start, len(mask)))
    return bands


def _peaks(profile: np.ndarray, min_gap: int) -> np.ndarray:
    thresh = profile.max() * 0.4
    idx = np.where(profile > thresh)[0]
    if idx.size == 0:
        return idx
    # collapse clusters of adjacent columns into one line position
    peaks: list[int] = [int(idx[0])]
    for x in idx[1:]:
        if x - peaks[-1] >= min_gap:
            peaks.append(int(x))
    return np.array(peaks)


def _longest_run(flags: np.ndarray) -> tuple[int, int]:
    best = (0, 0)
    start = 0
    for i, ok in enumerate(list(flags) + [False]):
        if not ok:
            if i - start > best[1] - best[0]:
                best = (start, i)
            start = i + 1
    return best
