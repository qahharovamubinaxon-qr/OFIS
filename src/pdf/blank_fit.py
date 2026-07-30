"""Measure the blank the office actually uploaded, instead of trusting one.

The ППУ front and the ТРУД ППУ pages are PHOTOGRAPHS of a screen. The office
takes a new one whenever it needs a new template, and no two are framed alike:
of the three ППУ fronts in AppData, two sit at one place on the page and the
third is a fifth of an inch lower and 2.5% larger. Coordinates measured off one
of them land above the labels on another — which is exactly what the office saw:
«фамилия исм отчестваси қийшиқ бўпти».

So the numbers in the ``*_spec`` modules are treated as being in ONE reference
frame, and this module works out how the uploaded blank differs from it: a
vertical scale and offset, read off the blank's own label column, plus the x of
its value column and the angle its rows run at. Every slot is then mapped
through that. A blank framed like the reference maps to itself exactly.

Nothing here needs the AI, a network, or the operator: it is pixels on the page
the office already handed over.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.common.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class Fit:
    """How the uploaded blank differs from the frame the spec was measured in."""

    #: vertical scale, 1.0 when the blank is framed like the reference
    scale: float = 1.0
    #: where the reference's ``anchor`` row landed on this blank
    top: float = 0.0
    #: the reference y that ``top`` corresponds to
    anchor: float = 0.0
    #: the value column's left edge on this blank, if it could be read
    value_x: float | None = None
    #: how far off level the blank's rows run, in degrees (clockwise positive)
    tilt: float = 0.0

    def y(self, reference_y: float) -> float:
        return self.top + (reference_y - self.anchor) * self.scale

    def size(self, reference_size: float) -> float:
        return reference_size * self.scale


IDENTITY = Fit()


def _grey(page, zoom: float = 4.0):
    import cv2
    import numpy as np

    shot = page.get_pixmap(matrix=__import__("fitz").Matrix(zoom, zoom))
    arr = np.frombuffer(shot.samples, np.uint8).reshape(shot.height, shot.width, shot.n)
    if shot.n >= 3:
        return cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGB2GRAY)
    return arr[:, :, 0]


def text_bands(grey, x0: float, x1: float, *, threshold: int = 150,
               min_ink: int = 6, min_height: int = 4) -> list[tuple[float, float]]:
    """The rows of ink between ``x0`` and ``x1``, as (top, bottom) page shares."""
    height, width = grey.shape
    strip = grey[:, int(x0 * width):int(x1 * width)]
    dark = (strip < threshold).sum(axis=1)
    rows: list[tuple[float, float]] = []
    run = None
    for y, ink in enumerate(dark):
        if ink >= min_ink and run is None:
            run = y
        elif ink < min_ink and run is not None:
            if y - run >= min_height:
                rows.append((run / height, (y - 1) / height))
            run = None
    if run is not None and height - run >= min_height:
        rows.append((run / height, (height - 1) / height))
    return rows


def left_ink(grey, top: float, bottom: float, x0: float, x1: float,
             *, threshold: int = 150, min_ink: int = 2) -> float | None:
    """Where the leftmost ink of that row sits, as a share of the page width."""
    height, width = grey.shape
    strip = grey[int(top * height):int(bottom * height) + 1, :]
    dark = (strip < threshold).sum(axis=0)
    for x in range(int(x0 * width), int(x1 * width)):
        if dark[x] >= min_ink:
            return x / width
    return None


def row_tilt(grey, top: float, bottom: float, x0: float, x1: float,
             *, threshold: int = 150) -> float | None:
    """How far off level one row of text runs, in degrees.

    Fitted through the TOP of the ink in each column — the cap line. The bottom
    would be pulled about by descenders, and there are only a few of those in a
    row, so they bend the line far more than they should.
    """
    import numpy as np

    height, width = grey.shape
    x_from, x_to = int(x0 * width), int(x1 * width)
    strip = grey[int(top * height):int(bottom * height) + 1, x_from:x_to]
    ys, xs = np.where(strip < threshold)
    if len(xs) < 200:
        return None
    tops: dict[int, int] = {}
    for x, y in zip(xs, ys, strict=True):
        if x not in tops or y < tops[x]:
            tops[x] = y
    if len(tops) < 60:
        return None
    cx = np.array(sorted(tops), dtype=float)
    cy = np.array([tops[int(x)] for x in cx], dtype=float)
    slope, _intercept = np.polyfit(cx, cy, 1)
    return float(np.degrees(np.arctan(slope)))


# ------------------------------------------------------- the ППУ front sheet

#: The reference frame the ППУ front slots were measured in: where the «ФИО»
#: label's cap-top and the «Гражданство» label's cap-top sat on that blank.
FRONT_ANCHOR = 0.1868
FRONT_SPAN = 0.5525 - FRONT_ANCHOR

#: The label column, and the value column, as shares of the page width.
LABEL_COLUMN = (0.17, 0.30)
VALUE_COLUMN = (0.30, 0.55)

#: The «ФИО» label is the second row of ink in the label column — «Физическое
#: лицо» heads it — and «Гражданство» is the seventh.
_ROW_FIO = 1
_ROW_CITIZENSHIP = 6

#: A fit outside these bounds is not a fit, it is a misread blank.
_SCALE_MIN, _SCALE_MAX = 0.80, 1.25
_TOP_MIN, _TOP_MAX = 0.10, 0.35


def fit_front(page) -> Fit:
    """Work out where this ППУ front blank's rows actually are.

    Returns :data:`IDENTITY` — no correction at all — if the blank cannot be
    read. A wrong correction is worse than none, so every step is bounded and
    anything out of range is refused.
    """
    try:
        grey = _grey(page)
    except Exception as exc:                          # noqa: BLE001
        log.warning("бланка ўлчанмади (расм олинмади): %s", exc)
        return IDENTITY

    bands = text_bands(grey, *LABEL_COLUMN)
    if len(bands) <= _ROW_CITIZENSHIP:
        log.warning("бланка ўлчанмади: ёрлиқ устунида %d қатор топилди",
                    len(bands))
        return IDENTITY

    top = bands[_ROW_FIO][0]
    span = bands[_ROW_CITIZENSHIP][0] - top
    if span <= 0:
        return IDENTITY
    scale = span / FRONT_SPAN
    if not (_SCALE_MIN <= scale <= _SCALE_MAX and _TOP_MIN <= top <= _TOP_MAX):
        log.warning("бланка ўлчови ишончсиз (top=%.4f scale=%.3f) — тегилмади",
                    top, scale)
        return IDENTITY

    # The value column's x, read off the sheet's OWN values — «Отсутствует»,
    # «Нет», «За пределами РФ»; the office erases the worker's data and leaves
    # those. The MEDIAN of them, not the first: «За пределами РФ» sits a few
    # points left of the rest on the site itself, and following it would drag
    # the whole column off by that much.
    found = []
    for band_top, band_bottom in text_bands(grey, *VALUE_COLUMN):
        if band_top <= top + 0.35 * scale:
            continue
        edge = left_ink(grey, band_top, band_bottom, VALUE_COLUMN[0], 0.45)
        if edge is not None and 0.28 <= edge <= 0.36:
            found.append(edge)
    value_x = None
    if found:
        found.sort()
        middle = found[len(found) // 2]        # median: the odd row is ignored
        value_x = middle - 0.0009              # back out the letter's side bearing

    fit = Fit(scale=scale, top=top, anchor=FRONT_ANCHOR, value_x=value_x)
    log.info("ППУ олд бланкаси ўлчанди: top=%.4f scale=%.3f value_x=%s",
             top, scale, f"{value_x:.4f}" if value_x else "—")
    return fit


def fit_tilt(page, window: tuple[float, float, float, float]) -> Fit:
    """Only the angle the blank's rows run at, from one row of its own text.

    ``window`` is (top, bottom, left, right) shares of the page, around a row of
    the blank's own text that runs a good way across it.
    """
    try:
        # half the detail of a fit: a slope through a whole row of text needs
        # far fewer pixels than a baseline does, and the notification page is
        # tall enough that 4× costs 70 MB of image
        grey = _grey(page, zoom=2.0)
    except Exception as exc:                          # noqa: BLE001
        log.warning("бланка бурчаги ўлчанмади: %s", exc)
        return IDENTITY
    top, bottom, left, right = window
    angle = row_tilt(grey, top, bottom, left, right)
    if angle is None or abs(angle) > 6.0:
        return IDENTITY
    log.info("бланка бурчаги: %+.2f°", angle)
    return Fit(tilt=angle)
