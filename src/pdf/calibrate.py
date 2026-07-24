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


def detect_all_runs(
    page: fitz.Page,
    page_index: int,
    *,
    dpi: int = 200,
    min_cells: int = 2,
    min_cell_px: int = 14,
    pitch_lo: float = 15.0,
    pitch_hi: float = 16.5,
    threshold: int | None = None,
    kernel_px: int | None = None,
) -> list[GridRow]:
    """Every evenly-spaced cell run on a page (a band may hold several: a date
    band yields три runs — число/месяц/год). Filtered to the form's true box
    pitch so label lettering is ignored. Used to calibrate multi-group rows.

    ``threshold``: when set, binarize with a fixed cutoff (``gray < threshold``)
    instead of OTSU — needed for very light forms (the registration blank prints
    its boxes in faint gray that OTSU discards). ``kernel_px`` overrides the
    vertical-stroke morphology height.
    """
    gray, scale = _render_gray(page, dpi)
    if threshold is not None:
        inv = ((gray < threshold).astype(np.uint8)) * 255
    else:
        inv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    kh = kernel_px if kernel_px is not None else max(12, min_cell_px)
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, kh))
    vertical = cv2.morphologyEx(inv, cv2.MORPH_OPEN, v_kernel)
    bands = _contiguous_bands(vertical.sum(axis=1) > (min_cell_px * 255), min_height=min_cell_px)

    out: list[GridRow] = []
    for top, bottom in bands:
        xs = _peaks(vertical[top:bottom, :].sum(axis=0), min_gap=min_cell_px // 2)
        if len(xs) < min_cells + 1:
            continue
        gaps = np.diff(xs)
        i = 0
        while i < len(gaps):
            j = i
            while j + 1 < len(gaps) and abs(gaps[j + 1] - gaps[i]) < gaps[i] * 0.3:
                j += 1
            ncells = j - i + 1
            if ncells >= min_cells and gaps[i] >= min_cell_px:
                pitch_px = float(np.median(gaps[i : j + 1]))
                pitch_pt = round(pitch_px * scale, 2)
                if pitch_lo <= pitch_pt <= pitch_hi:
                    out.append(
                        GridRow(
                            page=page_index,
                            y_top=round(top * scale, 2),
                            y_bottom=round(bottom * scale, 2),
                            x0=round((xs[i] + pitch_px / 2) * scale, 2),
                            pitch=pitch_pt,
                            max_cells=int(ncells),
                        )
                    )
            i = j + 1
    return out


def detect_cell_runs(
    page: fitz.Page,
    page_index: int,
    *,
    dpi: int = 200,
    threshold: int = 200,
    box_lo_px: int = 22,
    box_hi_px: int = 48,
    row_tol_px: int = 12,
    min_cells: int = 2,
) -> list[GridRow]:
    """Detect character-box runs by finding each box outline (contours), not by
    projecting strokes. Robust on faint forms (registration blank) where the box
    lines are too light for OTSU. A row is split into runs wherever the x-gap
    jumps well above the local pitch, so a date band yields separate
    число/месяц/год runs.
    """
    gray, scale = _render_gray(page, dpi)
    binv = ((gray < threshold).astype(np.uint8)) * 255
    cnts, _ = cv2.findContours(binv, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        if box_lo_px <= w <= box_hi_px and box_lo_px <= h <= box_hi_px:
            boxes.append((x + w / 2.0, y + h / 2.0, w, h))
    if not boxes:
        return []

    # Cluster into rows by y-center.
    boxes.sort(key=lambda b: b[1])
    rows_px: list[list[tuple[float, float, float, float]]] = []
    for b in boxes:
        placed = False
        for row in rows_px:
            if abs(row[0][1] - b[1]) <= row_tol_px:
                row.append(b)
                placed = True
                break
        if not placed:
            rows_px.append([b])

    out: list[GridRow] = []
    box_w = float(np.median([b[2] for b in boxes]))
    box_h = float(np.median([b[3] for b in boxes]))
    dedup_gap = box_w * 0.5  # a box border yields inner+outer contours → merge
    for row in rows_px:
        row.sort(key=lambda b: b[0])
        # Merge near-duplicate x-centers (double contour per box outline).
        xs: list[float] = []
        for b in row:
            if xs and b[0] - xs[-1] < dedup_gap:
                xs[-1] = (xs[-1] + b[0]) / 2.0
            else:
                xs.append(b[0])
        yc = float(np.median([b[1] for b in row]))
        # Split into contiguous evenly-spaced runs (a big x-gap ends a run).
        i = 0
        while i < len(xs):
            j = i
            while j + 1 < len(xs):
                gap = xs[j + 1] - xs[j]
                base = xs[i + 1] - xs[i]  # this run's pitch (first gap)
                if gap > base * 1.6:
                    break
                j += 1
            ncells = j - i + 1
            if ncells >= min_cells:
                run_xs = xs[i : j + 1]
                pitch_px = float(np.median(np.diff(run_xs)))
                out.append(
                    GridRow(
                        page=page_index,
                        y_top=round((yc - box_h / 2) * scale, 2),
                        y_bottom=round((yc + box_h / 2) * scale, 2),
                        x0=round(run_xs[0] * scale, 2),
                        pitch=round(pitch_px * scale, 2),
                        max_cells=int(ncells),
                    )
                )
            i = j + 1
    out.sort(key=lambda r: (r.y_top, r.x0))
    return out


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
