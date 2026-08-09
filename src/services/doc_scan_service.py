"""ДОКУМЕНТ — a phone photo of a document turned into a scan.

The office photographs passports, driving licences and patents with a phone,
held at an angle, over a desk or a hand, in whatever light the room has. What
the file has to become is what a flatbed scanner would have produced: the
document alone, square to the page, grey like a photocopy, centred on A4 with
white all round, in a PDF.

How the document is found
-------------------------
The edges of a document against almost any surface are the strongest straight
lines in the frame. So: shrink the photo, find the edges, and look for the
largest four-cornered outline that takes up a real share of the picture. Those
four corners are then mapped onto a rectangle — a perspective warp, not a
rotation — which is what pulls a licence photographed from above-left back into
a true rectangle with parallel sides.

When no clean quadrilateral is there (a document lying on a patterned cloth, a
photo cropped so the edges are already off-frame), the page is *not* mangled
into one: it is straightened by the dominant line angle if that is small, and
otherwise left exactly as it came. A document that arrives slightly crooked is
worth far more than one that has been folded into a trapezoid by a bad guess.

Layout
------
Landscape documents — licences, ID cards, a passport spread — go two to an A4
page; anything portrait goes one to a page. Each is scaled to its slot and
centred, which is how the office lays them out by hand.
"""

from __future__ import annotations

import io

from src.common.errors import OfisError
from src.common.logging import get_logger

log = get_logger(__name__)

#: A4 at 150 dpi — enough to read a passport number, small enough to e-mail.
PAGE_W, PAGE_H = 1240, 1754
PAGE_DPI = 150
#: White left around the documents on every side.
MARGIN = 0.07
#: Gap between two documents sharing a page.
GUTTER = 0.05
#: Wider than this and the document is treated as landscape — two to a page.
LANDSCAPE = 1.15

#: The detected outline must cover at least this share of the photo, or it is
#: not the document — it is a tile, a book, a shadow on the desk.
#:
#: A tenth is low enough for a licence held at arm's length and still far above
#: the things that would otherwise be mistaken for the document: the portrait
#: printed *on* a passport page, a stamp, a signature box. Those are small, and
#: in any case the largest valid outline wins, and the page always encloses
#: what is printed on it.
MIN_AREA = 0.10
#: And no more than this. An outline that is the whole photograph is not the
#: document's border — it is the photograph's own. Warping to it would resample
#: the picture for nothing, so those are left to the straightener instead.
MAX_AREA = 0.97
#: Detection runs on a shrunk copy; the corners are scaled back up and the warp
#: is done at full resolution, so nothing is lost to the shrinking.
DETECT_SIDE = 1200
#: Straightening by angle alone is only ever a small correction — a bigger one
#: means the line found was not the document's edge.
MAX_TILT = 12.0


def _rgb(data: bytes):
    """bytes → RGB array, EXIF rotation honoured."""
    import numpy as np
    from PIL import Image, ImageOps

    try:
        img = Image.open(io.BytesIO(data))
    except OSError as exc:
        raise OfisError("Rasm o'qilmadi — boshqa fayl yuboring.") from exc
    return np.asarray(ImageOps.exif_transpose(img).convert("RGB"))


def _order(np, quad):
    """The four corners as (top-left, top-right, bottom-right, bottom-left).

    By sums and differences of the coordinates, which is orientation-proof: the
    top-left always has the smallest x+y and the top-right the smallest y−x,
    whichever way round ``findContours`` happened to walk the outline.
    """
    pts = quad.reshape(4, 2).astype("float32")
    total, diff = pts.sum(axis=1), np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(total)], pts[np.argmin(diff)],
                     pts[np.argmax(total)], pts[np.argmax(diff)]], dtype="float32")


def _find_quad(cv2, np, rgb):
    """The document's four corners in ``rgb``, or None."""
    height, width = rgb.shape[:2]
    scale = min(1.0, DETECT_SIDE / max(height, width))
    small = cv2.resize(rgb, (int(width * scale), int(height * scale)),
                       interpolation=cv2.INTER_AREA) if scale < 1.0 else rgb

    grey = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    grey = cv2.GaussianBlur(grey, (5, 5), 0)
    # thresholds off the image's own median, so a dark photo and a bright one
    # are read the same way
    median = float(np.median(grey))
    edges = cv2.Canny(grey, int(max(0, 0.66 * median)), int(min(255, 1.33 * median)))
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=2)

    found, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    area_of_photo = small.shape[0] * small.shape[1]
    for contour in sorted(found, key=cv2.contourArea, reverse=True)[:8]:
        if cv2.contourArea(contour) < area_of_photo * MIN_AREA:
            break
        approx = cv2.approxPolyDP(contour, 0.02 * cv2.arcLength(contour, True), True)
        if len(approx) != 4 or not cv2.isContourConvex(approx):
            continue
        # judged on the quadrilateral, not the ragged contour it came from:
        # the quadrilateral is what would actually be warped, and it is always
        # the larger of the two
        share = cv2.contourArea(approx) / area_of_photo
        if share > MAX_AREA:
            continue                     # that is the photo's own edge, not a document
        if share >= MIN_AREA:
            return _order(np, approx) / (scale or 1.0)
    return None


def _find_paper(cv2, np, rgb):
    """The document found as PAPER rather than as edges — the second try.

    Canny wants clean straight borders. A passport lying on a wooden desk does
    not give them: the grain draws lines of its own, the page curls, and the
    binding throws a shadow along one side. But the page is still the one
    bright, colourless region in the frame, and a desk is neither. So threshold
    on «pale and unsaturated», take the largest blob, and put a rotated
    rectangle round it — which tolerates a corner the edge detector lost.
    """
    height, width = rgb.shape[:2]
    scale = min(1.0, DETECT_SIDE / max(height, width))
    small = cv2.resize(rgb, (int(width * scale), int(height * scale)),
                       interpolation=cv2.INTER_AREA) if scale < 1.0 else rgb

    hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV)
    value, saturation = hsv[..., 2], hsv[..., 1]
    paper = ((value > np.percentile(value, 55)) &
             (saturation < max(60, np.percentile(saturation, 55)))
             ).astype("uint8") * 255
    # close the print up into one solid page, then drop the speckle
    side = max(3, int(min(small.shape[:2]) * 0.02) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (side, side))
    paper = cv2.morphologyEx(paper, cv2.MORPH_CLOSE, kernel)
    paper = cv2.morphologyEx(paper, cv2.MORPH_OPEN, kernel)

    found, _ = cv2.findContours(paper, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not found:
        return None
    biggest = max(found, key=cv2.contourArea)
    share = cv2.contourArea(biggest) / (small.shape[0] * small.shape[1])
    if not (MIN_AREA <= share <= MAX_AREA):
        return None
    box = cv2.boxPoints(cv2.minAreaRect(biggest))
    return _order(np, np.array(box, dtype="float32")) / (scale or 1.0)


def _warp(cv2, np, rgb, quad):
    """Pull the four corners onto a true rectangle."""
    tl, tr, br, bl = quad
    width = int(round(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl))))
    height = int(round(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr))))
    if width < 80 or height < 80:
        return None
    target = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1],
                       [0, height - 1]], dtype="float32")
    matrix = cv2.getPerspectiveTransform(quad, target)
    return cv2.warpPerspective(rgb, matrix, (width, height),
                               flags=cv2.INTER_CUBIC,
                               borderMode=cv2.BORDER_REPLICATE)


def _straighten(cv2, np, rgb):
    """Last resort: rotate by the dominant edge angle, if it is a small one."""
    grey = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(grey, (5, 5), 0), 60, 180)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=120,
                            minLineLength=int(min(rgb.shape[:2]) * 0.35),
                            maxLineGap=20)
    if lines is None:
        return rgb
    import math

    angles = []
    for x1, y1, x2, y2 in lines.reshape(-1, 4):
        angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
        angle = (angle + 90) % 180 - 90          # fold onto (-90, 90]
        if abs(angle) <= MAX_TILT:               # near-horizontal edges only
            angles.append(angle)
    if not angles:
        return rgb
    tilt = float(np.median(angles))
    if abs(tilt) < 0.4:
        return rgb
    height, width = rgb.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), tilt, 1.0)
    return cv2.warpAffine(rgb, matrix, (width, height), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_REPLICATE)


def _photocopy(cv2, np, rgb):
    """Grey, the way a scanner gives it back — flat, legible, not blown out.

    A percentile stretch rather than full equalisation: equalising a document
    with a large pale area drags its paper to mid-grey and makes the scan look
    dirty. Clipping the darkest and lightest 2 % lifts the print off the paper
    and leaves the paper white.
    """
    grey = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    low, high = np.percentile(grey, (2.0, 98.0))
    if high - low < 25:                          # nearly flat — leave it alone
        return cv2.cvtColor(grey, cv2.COLOR_GRAY2RGB)
    stretched = np.clip((grey.astype(np.float32) - low) * (255.0 / (high - low)),
                        0, 255).astype("uint8")
    return cv2.cvtColor(stretched, cv2.COLOR_GRAY2RGB)


def scan_one(data: bytes, grayscale: bool = True):
    """One photo → the document alone, square, as an RGB array."""
    import cv2
    import numpy as np

    rgb = _rgb(data)
    page = None
    for find in (_find_quad, _find_paper):
        quad = find(cv2, np, rgb)
        if quad is None:
            continue
        page = _warp(cv2, np, rgb, quad)
        if page is not None:
            break
    if page is None:
        log.info("Ҳужжат чегараси топилмади — фақат тўғриланади")
        page = _straighten(cv2, np, rgb)
    if grayscale:
        page = _photocopy(cv2, np, page)
    return page


def _place(canvas, image, box) -> None:
    """Scale ``image`` into ``box`` keeping its shape, and centre it there."""
    from PIL import Image

    left, top, right, bottom = box
    slot_w, slot_h = right - left, bottom - top
    scale = min(slot_w / image.width, slot_h / image.height)
    size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
    fitted = image.resize(size, Image.LANCZOS)
    canvas.paste(fitted, (left + (slot_w - size[0]) // 2,
                          top + (slot_h - size[1]) // 2))


def _pages(shapes: list[tuple[int, int]]) -> list[list[int]]:
    """Which documents share a page: two landscape ones, or one of anything else."""
    out: list[list[int]] = []
    index = 0
    while index < len(shapes):
        w, h = shapes[index]
        wide = h and w / h >= LANDSCAPE
        if wide and index + 1 < len(shapes):
            nw, nh = shapes[index + 1]
            if nh and nw / nh >= LANDSCAPE:
                out.append([index, index + 1])
                index += 2
                continue
        out.append([index])
        index += 1
    return out


def build_pdf(images: list[bytes], grayscale: bool = True) -> bytes:
    """Photos of documents → one PDF, each straightened and centred on A4."""
    from PIL import Image

    if not images:
        raise OfisError("Kamida bitta hujjat rasmini yuklang.")

    # In colour, the room comes with the document: a shadow down one side
    # from the hand holding the phone, a bright patch by the window. The
    # grey mode already flattens that in `_photocopy`; in colour it used to
    # be left in. This is the same evening the office's own scanner does.
    from src.services.doc_enhance import even_lighting

    scans = [Image.fromarray(scan_one(data, grayscale) if grayscale
                             else even_lighting(scan_one(data, False)))
             for data in images]
    margin_x, margin_y = int(PAGE_W * MARGIN), int(PAGE_H * MARGIN)
    gutter = int(PAGE_H * GUTTER)

    pages = []
    for group in _pages([(s.width, s.height) for s in scans]):
        canvas = Image.new("RGB", (PAGE_W, PAGE_H), "white")
        usable_h = PAGE_H - 2 * margin_y
        if len(group) == 2:
            slot_h = (usable_h - gutter) // 2
            for row, which in enumerate(group):
                top = margin_y + row * (slot_h + gutter)
                _place(canvas, scans[which],
                       (margin_x, top, PAGE_W - margin_x, top + slot_h))
        else:
            _place(canvas, scans[group[0]],
                   (margin_x, margin_y, PAGE_W - margin_x, PAGE_H - margin_y))
        pages.append(canvas)

    buf = io.BytesIO()
    pages[0].save(buf, format="PDF", save_all=True, append_images=pages[1:],
                  resolution=PAGE_DPI)
    log.info("Ҳужжат сканери: %d расм → %d саҳифа", len(images), len(pages))
    return buf.getvalue()


def first_page_png(pdf: bytes) -> bytes:
    """Page one of a finished PDF, for the screen to show.

    The PAGE, not the cut-out document: what the operator needs to judge is
    whether the thing came out straight and centred on white A4, and a preview
    of the crop alone cannot answer that. Rendered from the PDF that will
    actually be saved, so what they approve is what they get.
    """
    import fitz
    from PIL import Image

    doc = fitz.open("pdf", pdf)
    shot = doc[0].get_pixmap(matrix=fitz.Matrix(0.7, 0.7))
    page = Image.frombytes("RGB", (shot.width, shot.height), shot.samples)
    buf = io.BytesIO()
    page.save(buf, format="PNG")
    return buf.getvalue()


def preview_png(images: list[bytes] | bytes, grayscale: bool = True) -> bytes:
    """Convenience: scan ``images`` and hand back page one as a PNG."""
    if isinstance(images, bytes):
        images = [images]
    return first_page_png(build_pdf(images, grayscale))
