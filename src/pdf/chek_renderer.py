"""Chek renderer — fills templates/chek/premiya_blank.pdf per chek_spec.

Only the 12 measured fields are written; everything else on the template is
never touched. Font is Microsoft Sans Serif from Windows, embedded per draw.
"""
from __future__ import annotations
import os
from dataclasses import dataclass
from datetime import datetime, date, time

import fitz

from src.common.errors import ValidationError
from src.pdf.chek_spec import FIELDS, FONT_PATH, MONTHS_RU

TEMPLATE_DEFAULT = os.path.join("templates", "chek", "premiya_blank.pdf")

# «ишчини компания idcи» — the value is BAKED INTO the template image, so a
# white patch goes over it and the office's own id is written in its place.
IDCI_COVER = (13.0, 960.0, 172.0, 977.0)
IDCI_POS = (14.2, 973.0)
IDCI_SIZE = 10

# ── суммани сўз билан ёзиш (рубль, аёл-жинс минг) ──────────────────────────
_U = ["", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
_UF = ["", "одна", "две", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
_TEEN = ["десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать",
         "пятнадцать", "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать"]
_TENS = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят",
         "семьдесят", "восемьдесят", "девяносто"]
_H = ["", "сто", "двести", "триста", "четыреста", "пятьсот", "шестьсот",
      "семьсот", "восемьсот", "девятьсот"]

def _triple(n: int, fem: bool) -> str:
    u = _UF if fem else _U
    w = []
    if n >= 100: w.append(_H[n // 100]); n %= 100
    if 10 <= n <= 19: w.append(_TEEN[n - 10])
    else:
        if n >= 20: w.append(_TENS[n // 10]); n %= 10
        if n: w.append(u[n])
    return " ".join(w)

def _plural(n: int, forms: tuple[str, str, str]) -> str:
    n = n % 100
    if 11 <= n <= 19: return forms[2]
    n %= 10
    if n == 1: return forms[0]
    if 2 <= n <= 4: return forms[1]
    return forms[2]

def amount_in_words(rub: int, kop: int) -> str:
    if rub == 0: words = "ноль"
    else:
        parts = []
        mln, rest = divmod(rub, 1_000_000)
        th, ones = divmod(rest, 1000)
        if mln: parts.append(_triple(mln, False) + " " + _plural(mln, ("миллион", "миллиона", "миллионов")))
        if th: parts.append(_triple(th, True) + " " + _plural(th, ("тысяча", "тысячи", "тысяч")))
        if ones: parts.append(_triple(ones, False))
        words = " ".join(parts)
    words = (words[:1].upper() + words[1:]) if words else words
    return f"{words} {_plural(rub, ('рубль', 'рубля', 'рублей'))} {kop:02d} копеек"

def format_amount(rub: int, kop: int) -> str:
    return f"{rub:,}".replace(",", " ").replace(" ", " ") + f",{kop:02d} ₽"

@dataclass
class ChekData:
    """Everything printed on the receipt. Nothing here is invented.

    ``avtoriz`` and ``idci`` in particular are what make the receipt a record
    of a payment rather than a picture of one, so they are required: the
    authorisation code is copied off the bank's own confirmation and the
    company id is the office's, recorded once in Sozlamalar. Earlier versions
    generated both at random — see :func:`_check`.
    """

    fam: str; ism: str; otch: str; inn: str
    card4: str
    when: datetime            # entered date + h:m:s
    rub: int; kop: int
    avtoriz: str              # 6 digits, from the bank's confirmation
    idci: str                 # the office's own company id


def _check(data: ChekData) -> tuple[str, str]:
    """The two values the program must never make up."""
    avtoriz = "".join(ch for ch in (data.avtoriz or "") if ch.isdigit())
    if len(avtoriz) != 6:
        raise ValidationError(
            "Код авторизации киритилмаган — уни банк квитанциясидан "
            "(ёки выпискадан) кўчириб ёзинг. 6 та рақам. Программа ўзи "
            "ўйлаб чиқармайди.")
    idci = (data.idci or "").strip()
    if not idci:
        raise ValidationError(
            "Компания коди йўқ — Sozlamalar бўлимида бир марта ёзиб "
            "қўйинг (ЧЕК → компания коди).")
    return avtoriz, idci

def _ensure_font(page, fontfile):
    page.insert_font(fontname="micross", fontfile=fontfile)

#: The baseline sits this far above the bottom of the measured rect.
_BASELINE_LIFT = 2.2


def effective(page, layout: dict | None) -> dict:
    """The fields this blank actually uses.

    :data:`FIELDS` was measured off the owner's own filled receipt and is in
    POINTS. Anything the office has since dragged into place with the mouse is
    kept in FRACTIONS of the page — so it survives a firm re-scanning its blank
    — and is converted back here. A blank nobody has arranged uses the measured
    numbers unchanged.
    """
    fields = {k: dict(v) for k, v in FIELDS.items()}
    moved = (layout or {}).get("fields") or {}
    if not moved:
        return fields
    width, height = page.rect.width, page.rect.height
    for key, value in moved.items():
        if key not in fields or len(value) != 3:
            continue
        x, baseline, size = (float(v) for v in value)
        rect = fields[key]["rect"]
        fields[key]["rect"] = [x * width, rect[1],
                               rect[2], baseline * height + _BASELINE_LIFT]
        fields[key]["size"] = size * height
    return fields


def _put(page, key, text, fontfile, fields=None):
    f = (fields or FIELDS)[key]
    x0, y0, x1, y1 = f["rect"]
    page.insert_text((x0, y1 - _BASELINE_LIFT), text, fontsize=f["size"],
                     fontname="micross", color=(0, 0, 0))

def _put_wrapped(page, key, text, fontfile, line_h=12.3, max_w=200.0, fields=None):
    """propis/sana_baza can overflow the narrow strip — wrap by width."""
    f = (fields or FIELDS)[key]
    x0, y0, x1, y1 = f["rect"]
    font = fitz.Font(fontfile=fontfile)
    words, line, lines = text.split(" "), "", []
    for w in words:
        cand = (line + " " + w).strip()
        if font.text_length(cand, f["size"]) <= max_w or not line: line = cand
        else: lines.append(line); line = w
    lines.append(line)
    for i, ln in enumerate(lines):
        page.insert_text((x0, y1 - _BASELINE_LIFT + i * line_h), ln,
                         fontsize=f["size"],
                         fontname="micross", color=(0, 0, 0))

def render_chek(data: ChekData, template_path: str | None = None,
                layout: dict | None = None) -> tuple[bytes, str]:
    """Returns (pdf_bytes, suggested_filename)."""
    tpl = template_path or TEMPLATE_DEFAULT
    avtoriz, idci = _check(data)
    fontfile = FONT_PATH if os.path.exists(FONT_PATH) else None
    if fontfile is None:
        raise RuntimeError("Microsoft Sans Serif topilmadi: " + FONT_PATH)
    doc = fitz.open(tpl)
    page = doc[0]
    _ensure_font(page, fontfile)
    fields = effective(page, layout)
    w = data.when
    fam, ism, otch = data.fam.upper().strip(), data.ism.upper().strip(), data.otch.upper().strip()
    inn = "".join(ch for ch in data.inn if ch.isdigit())
    amount = format_amount(data.rub, data.kop)

    _put(page, "datetime",
         f"{w.day} {MONTHS_RU[w.month - 1]} {w.year} {w:%H:%M:%S} мск",
         fontfile, fields=fields)
    _put(page, "fio_l1", f"{fam} {ism}", fontfile, fields=fields)
    _put(page, "fio_l2", otch, fontfile, fields=fields)
    _put(page, "card4",
         "".join(ch for ch in data.card4 if ch.isdigit())[-4:],
         fontfile, fields=fields)
    _put(page, "inn", inn, fontfile, fields=fields)
    _put(page, "ism", ism, fontfile, fields=fields)
    _put(page, "otch", otch, fontfile, fields=fields)
    _put(page, "fam", fam, fontfile, fields=fields)
    _put_wrapped(page, "inn12", f"121000000000{inn}", fontfile, fields=fields)
    _put_wrapped(page, "sana_baza", f"1044525225009006{w:%d%m%Y}11071538", fontfile, fields=fields)
    _put(page, "avtoriz", avtoriz, fontfile, fields=fields)
    # company idci: white-out the baked value, write the office's own
    page.draw_rect(fitz.Rect(*IDCI_COVER), color=None, fill=(1, 1, 1))
    page.insert_text(IDCI_POS, idci, fontsize=IDCI_SIZE,
                     fontname="micross", color=(0, 0, 0))
    _put(page, "summa_1", amount, fontfile, fields=fields)
    _put(page, "summa_2", amount, fontfile, fields=fields)
    _put_wrapped(page, "propis", amount_in_words(data.rub, data.kop), fontfile, fields=fields)

    name = f"Документ-{w:%Y-%m-%d-%H-%M-%S}.pdf"
    out = doc.tobytes(deflate=True)
    doc.close()
    return out, name
