"""Typeset the СФЕРА «Удостоверение» card onto the centre's empty blank.

The bundled blank carries only the red cover and the «Учебный центр СФЕРА»
letterhead, so every line — the licence strip, the labels, the holder's name,
the profession, the commission wording and the signature rules — is set here.
Coordinates were measured off the centre's own filled certificate, so the
output lines up with it 1:1 (Times New Roman, underlines included).

The round stamp is printed last, slightly translucent, so it reads like real
ink pressed over the photo and the text rather than a sticker on top.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz

from src.pdf.engine import _font_file

# ---------------------------------------------------------------- fonts
_REG, _BOLD, _IT, _BI = "OfisSerif", "OfisSerifBold", "OfisSerifItalic", "OfisSerifBoldItalic"
_IDS = {_REG: "sv_r", _BOLD: "sv_b", _IT: "sv_i", _BI: "sv_bi"}

# licence strip, printed on every certificate
LICENCE = ("Лицензия №Л035-01265-18/00460507 выдана Министерством "
           "образования и науки УР")
CHAIRMAN = "Никитина К.С."

# left card
_L_FIO_X = 182.9          # ФИО lines start here
_L_FIO_RIGHT = 283.2      # …and their rules run to here
_L_FIO_BASE = 136.4       # first ФИО baseline
_L_FIO_STEP = 12.4
_FIO_SIZE = 11.5          # holder's name on the left card
_L_CENTRE = 209.4         # centre of the left card's text column
# the profession, in quotes under «…по профессии:». A long one is broken over
# two lines rather than shrunk — the centre asked for it to stay readable.
_L_PROF_SIZE = 11.0
_L_PROF_WIDTH = 150.0     # the card's usable width, between photo and edge
_L_PROF_ONE = 192.9       # baseline when it fits on one line
_L_PROF_TWO = (187.4, 198.9)   # …and the pair of baselines when it does not
# right card
_R_LEFT, _R_RIGHT = 328.5, 551.3
_R_CENTRE = 439.9

# the photo frame on the left card, and its width/height ratio — uploads are
# cropped to exactly this so they fill it edge to edge
PHOTO_BOX = (51.0, 128.3, 121.3, 208.4)
PHOTO_ASPECT = (PHOTO_BOX[2] - PHOTO_BOX[0]) / (PHOTO_BOX[3] - PHOTO_BOX[1])

# the chairman's signature, drawn across the rule after «Председатель комиссии»
SIGNATURE_BOX = (418.0, 220.0, 476.0, 242.0)


@dataclass(frozen=True)
class UdoData:
    number: str            # «3606»
    fio_dative: list[str]  # [«Муминову», «Шерали», «Рузимухаммад Угли»]
    profession: str        # «Электрогазосварщик»
    qualification: str     # «Электрогазосварщик 5 (пятого) разряда»
    issue_date: str        # «04.08.2023 г.»
    basis: str             # «ООО УЦ "СФЕРА" № ПО3355 от 04.08.2023 г.»
    photo_path: Path | None = None
    stamp_path: Path | None = None
    signature_path: Path | None = None


class _Pen:
    """Small helper: text at a baseline, optional underline, in one call."""

    def __init__(self, page: fitz.Page) -> None:
        self._page = page
        self._fonts = {name: fitz.Font(fontfile=str(_font_file(name))) for name in _IDS}
        for name, pdf_id in _IDS.items():
            page.insert_font(fontname=pdf_id, fontfile=str(_font_file(name)))

    def width(self, text: str, font: str, size: float) -> float:
        return self._fonts[font].text_length(text, fontsize=size)

    def text(self, x: float, baseline: float, text: str, *, font: str = _REG,
             size: float = 11.0, centre: float | None = None,
             fit: float | None = None) -> None:
        if not text:
            return
        if fit:  # shrink until it fits the available width
            while size > 5 and self.width(text, font, size) > fit:
                size -= 0.25
        if centre is not None:
            x = centre - self.width(text, font, size) / 2
        self._page.insert_text((x, baseline), text,
                               fontname=_IDS[font], fontsize=size)

    def rule(self, x0: float, x1: float, y: float, width: float = 0.7) -> None:
        self._page.draw_line((x0, y), (x1, y), color=(0, 0, 0), width=width)


def _translucent_stamp(path: Path, alpha: float = 0.82) -> bytes | None:
    """Fade the stamp a touch so the text under it stays legible — the way a
    real rubber stamp looks when pressed over print."""
    try:
        import numpy as np
        from PIL import Image
    except ImportError:  # pragma: no cover - Pillow ships with the app
        return None
    try:
        img = Image.open(path).convert("RGBA")
    except OSError:
        return None
    arr = np.array(img)
    arr[..., 3] = (arr[..., 3].astype(float) * alpha).astype("uint8")
    import io

    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()


def _profession_lines(pen: "_Pen", profession: str) -> None:
    """Set the profession, wrapping onto a second line instead of shrinking.

    A long trade name used to be squeezed down until it fit one line, which
    left it too small to read on the card. It now breaks across two lines at
    the word boundary that makes them most even, and both keep the full size
    whenever the pair fits. Only a name too long even for two lines shrinks,
    and then both lines shrink together so they read as one block.
    """
    if not profession:
        return
    quoted = f"“{profession}”"
    if pen.width(quoted, _BI, _L_PROF_SIZE) <= _L_PROF_WIDTH:
        pen.text(0, _L_PROF_ONE, quoted, font=_BI, size=_L_PROF_SIZE,
                 centre=_L_CENTRE)
        return

    first, second = _balanced_split(pen, quoted)
    size = _L_PROF_SIZE
    widest = max(pen.width(first, _BI, size), pen.width(second, _BI, size))
    while size > 6 and widest > _L_PROF_WIDTH:
        size -= 0.25
        widest = max(pen.width(first, _BI, size), pen.width(second, _BI, size))
    for baseline, line in zip(_L_PROF_TWO, (first, second), strict=True):
        pen.text(0, baseline, line, font=_BI, size=size, centre=_L_CENTRE)


def _balanced_split(pen: "_Pen", text: str) -> tuple[str, str]:
    """Break ``text`` in two at the word boundary that evens the halves out."""
    words = text.split()
    if len(words) < 2:
        return text, ""
    best, best_worst = 1, None
    for cut in range(1, len(words)):
        left = " ".join(words[:cut])
        right = " ".join(words[cut:])
        worst = max(pen.width(left, _BI, _L_PROF_SIZE),
                    pen.width(right, _BI, _L_PROF_SIZE))
        if best_worst is None or worst < best_worst:
            best, best_worst = cut, worst
    return " ".join(words[:best]), " ".join(words[best:])


def render_udostoverenie(page: fitz.Page, data: UdoData) -> None:
    """Draw the whole certificate spread onto ``page`` (the empty blank)."""
    pen = _Pen(page)

    # ---------------- left card ----------------
    pen.text(51.8, 114.1, LICENCE, font=_IT, size=6.5, fit=221.5)
    pen.text(0, 123.7, f"УДОСТОВЕРЕНИЕ № {data.number}",
             font=_BI, size=10, centre=_L_CENTRE)
    pen.text(134.4, 136.6, "Выдано:", font=_BI, size=9)

    # each name line is ruled only as far as the word actually runs
    for i, line in enumerate(data.fio_dative[:3]):
        base = _L_FIO_BASE + i * _L_FIO_STEP
        size = _FIO_SIZE
        while size > 6 and pen.width(line, _BI, size) > _L_FIO_RIGHT - _L_FIO_X:
            size -= 0.25
        pen.text(_L_FIO_X, base, line, font=_BI, size=size)
        pen.rule(_L_FIO_X, _L_FIO_X + pen.width(line, _BI, size), base + 2.1)

    pen.text(0, 170.3, "в том, что он(а) исвоил(а) программу",
             font=_BI, size=7.5, centre=_L_CENTRE)
    pen.text(0, 176.8, "профессионального обучения по профессии:",
             font=_BI, size=7.5, centre=_L_CENTRE)
    _profession_lines(pen, data.profession)

    pen.rule(160.7, 261.0, 205.5)
    pen.text(0, 217.4, "(личная подпись)", font=_BI, size=9, centre=208.5)
    pen.text(140.6, 231.0, f"Дата выдачи: {data.issue_date}", font=_BI, size=10)

    # ---------------- right card ----------------
    pen.text(0, 104.0, "Решением аттестационной комиссии",
             font=_BOLD, size=10, centre=_R_CENTRE)

    fio_line = " ".join(data.fio_dative)
    pen.text(0, 119.2, fio_line, font=_BI, size=12, centre=_R_CENTRE,
             fit=_R_RIGHT - 339.6)
    pen.rule(339.6, 544.3, 121.6)

    pen.text(0, 137.5, "присвоена (подтверждена) квалификация:",
             font=_BOLD, size=10.5, centre=_R_CENTRE)
    pen.text(0, 161.6, data.qualification, font=_BOLD, size=11.5,
             centre=_R_CENTRE, fit=_R_RIGHT - 363.0)
    pen.rule(363.0, 529.9, 165.3)

    # the three body lines share one size — the largest at which the longest
    # of them still fits the card, so they read as one block
    body = ["Допускается к работе согласно должностным обязанностям.",
            "Основание: Протокол аттестационной комиссии",
            data.basis]
    body_size = 11.0
    avail = _R_RIGHT - _R_LEFT
    while body_size > 6 and any(pen.width(t, _REG, body_size) > avail for t in body):
        body_size -= 0.25
    for baseline, line in zip((185.5, 197.5, 214.3), body, strict=True):
        pen.text(_R_LEFT, baseline, line, font=_REG, size=body_size)

    pen.text(_R_LEFT, 234.8, "Председатель комиссии", font=_REG, size=body_size)
    pen.rule(432.0, 468.0, 235.6)
    pen.text(469.1, 234.3, CHAIRMAN, font=_REG, size=body_size)

    # the chairman's signature sits across that rule
    if data.signature_path and Path(data.signature_path).exists():
        try:
            page.insert_image(fitz.Rect(*SIGNATURE_BOX),
                              filename=str(data.signature_path), overlay=True)
        except (RuntimeError, ValueError):
            pass

    # ---------------- photo, then the stamps on top ----------------
    if data.photo_path and Path(data.photo_path).exists():
        box = fitz.Rect(*PHOTO_BOX)
        try:
            # the upload is pre-cropped to PHOTO_ASPECT, so it fills the frame
            page.insert_image(box, filename=str(data.photo_path),
                              keep_proportion=False)
        except (RuntimeError, ValueError):
            pass
        page.draw_rect(box, color=(0, 0, 0), width=0.7)

    if data.stamp_path and Path(data.stamp_path).exists():
        ink = _translucent_stamp(Path(data.stamp_path))
        for box in (fitz.Rect(98.7, 118.0, 215.5, 229.8),     # over the photo
                    fitz.Rect(381.5, 133.6, 490.4, 241.7)):   # over the quals
            try:
                if ink:
                    page.insert_image(box, stream=ink, overlay=True)
                else:
                    page.insert_image(box, filename=str(data.stamp_path), overlay=True)
            except (RuntimeError, ValueError):
                pass
