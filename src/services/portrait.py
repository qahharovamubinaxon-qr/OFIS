"""Turn a worker's snapshot into a document photo: white ground, 3×4 cut.

The owner photographs a worker against whatever wall the office has; the
card wants a clean portrait. GrabCut lifts the person off the background,
the background goes white, and the cut is centred on the face when one is
found (Haar cascade, offline) — otherwise on the subject itself.
"""

from __future__ import annotations

import cv2
import numpy as np

from src.common.errors import OfisError
from src.common.logging import get_logger

log = get_logger(__name__)

#: Snapshots come off phones at silly sizes — this is plenty for a card.
_MAX_SIDE = 1400


def _decode(data: bytes) -> np.ndarray:
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise OfisError("Ишчи расми ўқилмади — JPG ёки PNG ташланг.")
    side = max(img.shape[:2])
    if side > _MAX_SIDE:
        scale = _MAX_SIDE / side
        img = cv2.resize(img, None, fx=scale, fy=scale,
                         interpolation=cv2.INTER_AREA)
    return img


def _lift_subject(img: np.ndarray) -> np.ndarray:
    """A soft 0–255 mask of the person, GrabCut seeded from the borders."""
    h, w = img.shape[:2]
    mask = np.zeros((h, w), np.uint8)
    margin = max(2, int(0.04 * min(h, w)))
    rect = (margin, margin, w - 2 * margin, h - 2 * margin)
    try:
        cv2.grabCut(img, mask, rect, np.zeros((1, 65), np.float64),
                    np.zeros((1, 65), np.float64), 5, cv2.GC_INIT_WITH_RECT)
    except cv2.error:
        return np.full((h, w), 255, np.uint8)
    fg = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD),
                  255, 0).astype(np.uint8)
    if fg.sum() < 255 * 0.02 * h * w:      # GrabCut lost the person — keep all
        return np.full((h, w), 255, np.uint8)
    # keep the biggest piece, close pinholes, feather the edge
    n, labels, stats, _ = cv2.connectedComponentsWithStats(fg, 8)
    if n > 1:
        biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        fg = np.where(labels == biggest, 255, 0).astype(np.uint8)
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    return cv2.GaussianBlur(fg, (5, 5), 0)


def _face_box(img: np.ndarray) -> tuple[int, int, int, int] | None:
    """Haar face, when this OpenCV still ships it — OpenCV 5 dropped the
    class, and there the subject-led cut below stands in."""
    cascade_cls = getattr(cv2, "CascadeClassifier", None)
    data = getattr(cv2, "data", None)
    if cascade_cls is None or data is None:
        return None
    cascade = cascade_cls(
        data.haarcascades + "haarcascade_frontalface_default.xml")
    if cascade.empty():
        return None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = cascade.detectMultiScale(gray, 1.1, 5,
                                     minSize=(img.shape[1] // 10,) * 2)
    if len(faces) == 0:
        return None
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    return int(x), int(y), int(w), int(h)


def _crop_box(img: np.ndarray, subject: np.ndarray,
              ratio: float) -> tuple[int, int, int, int]:
    """x, y, w, h of the cut — face-led when a face is found."""
    ih, iw = img.shape[:2]
    face = _face_box(img)
    if face is not None:
        # the face takes about a third of a document photo — the rest is
        # air above and the shoulders below
        fx, fy, fw, fh = face
        ch = int(fh * 3.1)
        cw = int(ch * ratio)
        cx = fx + fw // 2
        top = int(fy - 0.55 * fh)
        return cx - cw // 2, top, cw, ch
    ys, xs = np.nonzero(subject > 128)
    if len(xs):
        # the head leads: its width is read off the mask's top band, so the
        # cut keeps head AND shoulders whether GrabCut caught the whole
        # person or only the head
        x0, x1 = int(xs.min()), int(xs.max())
        y0 = int(ys.min())
        band = subject[y0:y0 + max(8, (x1 - x0) // 2)] > 128
        widths = band.sum(axis=1)
        head_w = int(widths.max()) if widths.size else (x1 - x0)
        head_cols = np.nonzero(band.any(axis=0))[0]
        cx = int(head_cols.mean()) if len(head_cols) else (x0 + x1) // 2
        cw = int(max(head_w * 2.3, (x1 - x0) * 1.08))
        ch = int(cw / ratio)
        top = int(y0 - 0.08 * ch)
        return cx - cw // 2, top, cw, ch
    ch = ih
    cw = int(ch * ratio)
    return (iw - cw) // 2, 0, cw, ch


def clean_portrait(data: bytes, ratio: float = 0.73) -> bytes:
    """The finished card photo as PNG: white background, cut to ``ratio``."""
    img = _decode(data)
    subject = _lift_subject(img)
    alpha = subject.astype(np.float32)[:, :, None] / 255.0
    on_white = (img.astype(np.float32) * alpha
                + 255.0 * (1.0 - alpha)).astype(np.uint8)

    x, y, w, h = _crop_box(img, subject, ratio)
    ih, iw = on_white.shape[:2]
    pad_left = max(0, -x)
    pad_top = max(0, -y)
    pad_right = max(0, x + w - iw)
    pad_bottom = max(0, y + h - ih)
    if pad_left or pad_top or pad_right or pad_bottom:
        on_white = cv2.copyMakeBorder(on_white, pad_top, pad_bottom,
                                      pad_left, pad_right,
                                      cv2.BORDER_CONSTANT,
                                      value=(255, 255, 255))
        x += pad_left
        y += pad_top
    cut = on_white[y:y + h, x:x + w]
    ok, out = cv2.imencode(".png", cut)
    if not ok:
        raise OfisError("Расмни тайёрлаб бўлмади.")
    log.info("Портрет тайёрланди: %dx%d", cut.shape[1], cut.shape[0])
    return out.tobytes()
