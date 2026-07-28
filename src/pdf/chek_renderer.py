"""Chek renderer — fills templates/chek/premiya_blank.pdf per chek_spec.

Only the 12 measured fields are written; everything else on the template is
never touched. Font is Microsoft Sans Serif from Windows, embedded per draw.
"""
from __future__ import annotations
import os, random
from dataclasses import dataclass
from datetime import datetime, date, time

import fitz

from src.pdf.chek_spec import FIELDS, FONT_PATH, MONTHS_RU

TEMPLATE_DEFAULT = os.path.join("templates", "chek", "premiya_blank.pdf")

# «ишчини компания idcи» — the value is BAKED INTO the template image, so we
# paint a white patch over it and write a fresh random one (12 digits + 4
# uppercase Latin letters, e.g. 357852345266REGD) on every generated check.
IDCI_COVER = (13.0, 960.0, 172.0, 977.0)
IDCI_POS = (14.2, 973.0)
IDCI_SIZE = 10

def random_idci() -> str:
    import string
    return ("".join(random.choice("0123456789") for _ in range(12))
            + "".join(random.choice(string.ascii_uppercase) for _ in range(4)))

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
    fam: str; ism: str; otch: str; inn: str
    card4: str
    when: datetime            # entered date + h:m:s
    rub: int; kop: int
    avtoriz: str | None = None   # 6-digit; random when None
    idci: str | None = None      # 12 digits + 4 letters; random when None

def _ensure_font(page, fontfile):
    page.insert_font(fontname="micross", fontfile=fontfile)

def _put(page, key, text, fontfile):
    f = FIELDS[key]
    x0, y0, x1, y1 = f["rect"]
    page.insert_text((x0, y1 - 2.2), text, fontsize=f["size"],
                     fontname="micross", color=(0, 0, 0))

def _put_wrapped(page, key, text, fontfile, line_h=12.3, max_w=200.0):
    """propis/sana_baza can overflow the narrow strip — wrap by width."""
    f = FIELDS[key]
    x0, y0, x1, y1 = f["rect"]
    font = fitz.Font(fontfile=fontfile)
    words, line, lines = text.split(" "), "", []
    for w in words:
        cand = (line + " " + w).strip()
        if font.text_length(cand, f["size"]) <= max_w or not line: line = cand
        else: lines.append(line); line = w
    lines.append(line)
    for i, ln in enumerate(lines):
        page.insert_text((x0, y1 - 2.2 + i * line_h), ln, fontsize=f["size"],
                         fontname="micross", color=(0, 0, 0))

def render_chek(data: ChekData, template_path: str | None = None) -> tuple[bytes, str]:
    """Returns (pdf_bytes, suggested_filename)."""
    tpl = template_path or TEMPLATE_DEFAULT
    fontfile = FONT_PATH if os.path.exists(FONT_PATH) else None
    if fontfile is None:
        raise RuntimeError("Microsoft Sans Serif topilmadi: " + FONT_PATH)
    doc = fitz.open(tpl)
    page = doc[0]
    _ensure_font(page, fontfile)
    w = data.when
    fam, ism, otch = data.fam.upper().strip(), data.ism.upper().strip(), data.otch.upper().strip()
    inn = "".join(ch for ch in data.inn if ch.isdigit())
    avtoriz = data.avtoriz or f"{random.randint(0, 999999):06d}"
    amount = format_amount(data.rub, data.kop)

    _put(page, "datetime", f"{w.day} {MONTHS_RU[w.month - 1]} {w.year} {w:%H:%M:%S} мск", fontfile)
    _put(page, "fio_l1", f"{fam} {ism}", fontfile)
    _put(page, "fio_l2", otch, fontfile)
    _put(page, "card4", "".join(ch for ch in data.card4 if ch.isdigit())[-4:], fontfile)
    _put(page, "inn", inn, fontfile)
    _put(page, "ism", ism, fontfile)
    _put(page, "otch", otch, fontfile)
    _put(page, "fam", fam, fontfile)
    _put_wrapped(page, "inn12", f"121000000000{inn}", fontfile)
    _put_wrapped(page, "sana_baza", f"1044525225009006{w:%d%m%Y}11071538", fontfile)
    _put(page, "avtoriz", avtoriz, fontfile)
    # company idci: white-out the baked value, write a fresh random one
    page.draw_rect(fitz.Rect(*IDCI_COVER), color=None, fill=(1, 1, 1))
    page.insert_text(IDCI_POS, data.idci or random_idci(), fontsize=IDCI_SIZE,
                     fontname="micross", color=(0, 0, 0))
    _put(page, "summa_1", amount, fontfile)
    _put(page, "summa_2", amount, fontfile)
    _put_wrapped(page, "propis", amount_in_words(data.rub, data.kop), fontfile)

    name = f"Документ-{w:%Y-%m-%d-%H-%M-%S}.pdf"
    out = doc.tobytes(deflate=True)
    doc.close()
    return out, name
