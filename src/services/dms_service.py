"""ДМС — fill the office's РЕСО «ДМС-Трудовой» policy for a worker.

The office is an insurance agent: it completes the insurer's own policy form
for each migrant worker. This module types the worker's data into both blocks
(Страхователь and Застрахованный are the same person), writes the validity
sentence and prints the policy number as red digits plus a Code 128 barcode.

Policy numbers
--------------
The number is NOT invented. РЕСО allocates the agency a block of numbers; the
operator records that block in Settings (``dms.number_from`` … ``dms.number_to``)
and the program hands them out in order, refusing to go past the end. So the
program can only ever print a number the office has declared it was given —
it can never manufacture one, which would leave the worker with a policy that
covers nothing.

Coordinates were measured off the office's own filled policy, so the output
lines up with it 1:1.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import fitz

from src.common.errors import OfisError
from src.common.logging import get_logger
from src.config import paths
from src.domain.documents import Passport
from src.domain.enums import Gender
from src.pdf.barcode import draw_code128
from src.pdf.engine import _font_file
from src.pdf.formatters import _date_dmy, _date_long_g

log = get_logger(__name__)

KEY_FROM, KEY_TO, KEY_NEXT = "dms.number_from", "dms.number_to", "dms.number_next"
KEY_REGION, KEY_PREMIUM = "dms.region", "dms.premium"

DEFAULT_REGION = "Москва"

_TEMPLATE = paths.templates_dir() / "dms" / "blank.pdf"

# ------------------------------------------------------------ geometry
_REG, _BOLD = "OfisArial", "OfisArialBold"
_VALUE_X = 170.0                 # every value column starts here
_RED = (0.85, 0.10, 0.13)

# Страхователь rows (top, bottom) measured on the blank
_S_FIO = (270.2, 294.0)
_S_ADDR = (294.0, 318.0)
_S_PASS = (318.0, 339.6)
_S_PHONE = (339.6, 351.6)
_S_CITIZ = (351.6, 363.6)
# Застрахованный rows
_Z_FIO = (384.0, 420.5)
_Z_ADDR = (420.5, 444.2)
_Z_PASS = (444.2, 465.8)
_Z_PHONE = (465.8, 477.8)
_Z_CITIZ = (477.8, 489.8)
_Z_REGION = (489.8, 501.8)

_SEX_CENTRE = 520.0             # «Пол» value column, centred
_SEX_W = 46.0
_DOB_CENTRE = 508.0             # «Дата Рождения» value column, centred
_DOB_W = 70.0
_ADDR_W = 424.0 - _VALUE_X       # address cells stop before the date column
_WIDE_W = 543.6 - _VALUE_X       # passport row spans the whole table

# header: red number, barcode, digits under it
_NUM_CENTRE = 271.0
_NUM_BASE = 91.0
_NUM_SIZE = 13.0
_BARCODE = (424.6, 54.0, 503.5, 67.7)
_BAR_DIGITS_BASE = 79.0

# the validity sentence added under the premium table
_SROK_X, _SROK_W = 48.0, 512.0
_SROK_BASE, _SROK_LEAD = 636.0, 11.0
_SROK_SIZE = 8.5


@dataclass(frozen=True)
class DmsResult:
    pdf_path: Path
    policy_number: str
    start_date: date
    end_date: date


def policy_end_date(start: date) -> date:
    """One year of cover: 27.07.2026 → 26.07.2027 (a day short of a year)."""
    try:
        return start.replace(year=start.year + 1) - __import__("datetime").timedelta(days=1)
    except ValueError:                      # 29 February
        return date(start.year + 1, 2, 28)


def _title(text: str) -> str:
    return " ".join(w[:1].upper() + w[1:].lower() for w in (text or "").split())


class DmsService:
    def __init__(self, settings) -> None:
        self._settings = settings

    # ------------------------------------------------------- numbering
    def _int(self, key: str, default: int = 0) -> int:
        try:
            return int(str(self._settings.get(key, default) or default))
        except (TypeError, ValueError):
            return default

    def peek_number(self) -> str:
        """The number the next policy would carry ("" when none is available)."""
        low, high = self._int(KEY_FROM), self._int(KEY_TO)
        nxt = self._int(KEY_NEXT, low)
        if not low or not high or nxt < low or nxt > high:
            return ""
        return str(nxt)

    def remaining(self) -> int:
        low, high = self._int(KEY_FROM), self._int(KEY_TO)
        nxt = self._int(KEY_NEXT, low)
        if not low or not high:
            return 0
        return max(0, high - max(nxt, low) + 1)

    def _take_number(self) -> str:
        low, high = self._int(KEY_FROM), self._int(KEY_TO)
        if not low or not high:
            raise OfisError(
                "РЕСО берган полис рақамлари киритилмаган. Sozlamalar → ДМС "
                "бўлимига рақамлар оралиғини (дан … гача) киритинг.")
        nxt = self._int(KEY_NEXT, low)
        if nxt < low:
            nxt = low
        if nxt > high:
            raise OfisError(
                f"Рақамлар тугади ({low}…{high}). РЕСО дан янги рақамлар олиб, "
                "Sozlamalar → ДМС бўлимига киритинг.")
        self._settings.set(KEY_NEXT, nxt + 1)
        return str(nxt)

    # -------------------------------------------------------- generate
    def generate(
        self,
        passport: Passport,
        *,
        start_date: date,
        phone: str,
        address: str,
        region: str | None = None,
        output_dir: Path | None = None,
    ) -> DmsResult:
        if not _TEMPLATE.exists():
            raise OfisError("ДМС бланкаси топилмади (templates/dms/blank.pdf).")
        if not address.strip():
            raise OfisError("Рўйхатдан ўтиш манзилини киритинг.")

        number = self._take_number()
        end_date = policy_end_date(start_date)
        region = (region or str(self._settings.get(KEY_REGION, DEFAULT_REGION)
                                or DEFAULT_REGION)).strip()

        doc = fitz.open(_TEMPLATE)
        try:
            page = doc[0]
            page.insert_font(fontname="dms_r", fontfile=str(_font_file(_REG)))
            page.insert_font(fontname="dms_b", fontfile=str(_font_file(_BOLD)))
            self._fill(page, passport, number=number, phone=phone.strip(),
                       address=address.strip(), region=region,
                       start_date=start_date, end_date=end_date)
            out = self._output_path(passport, output_dir)
            doc.save(str(out), garbage=4, deflate=True)
        finally:
            doc.close()

        log.info("ДМС %s for %s (%s → %s)", number, passport.surname,
                 start_date, end_date)
        return DmsResult(pdf_path=out, policy_number=number,
                         start_date=start_date, end_date=end_date)

    # ------------------------------------------------------------------
    def _fill(self, page, passport: Passport, *, number: str, phone: str,
              address: str, region: str, start_date: date, end_date: date) -> None:
        fio = _title(" ".join(x for x in (passport.surname, passport.name,
                                          passport.patronymic) if x))
        sex = "Мужской" if passport.gender == Gender.MALE else "Женский"
        dob = _date_dmy(passport.birth_date) if passport.birth_date else ""
        citizenship = _title(passport.nationality or "")
        pass_line = ", ".join(x for x in (
            f"{passport.series or ''}{passport.number or ''}".strip(),
            _date_dmy(passport.issue_date) if passport.issue_date else "",
            passport.issued_by or "",
        ) if x)

        # both blocks describe the same person — the worker insures himself
        for fio_row, addr_row, pass_row, phone_row, citiz_row in (
            (_S_FIO, _S_ADDR, _S_PASS, _S_PHONE, _S_CITIZ),
            (_Z_FIO, _Z_ADDR, _Z_PASS, _Z_PHONE, _Z_CITIZ),
        ):
            self._cell(page, fio, _VALUE_X, fio_row, _ADDR_W + 48, size=10.0)
            self._cell(page, sex, _SEX_CENTRE, fio_row, _SEX_W, size=9.0, centre=True)
            self._cell(page, address, _VALUE_X, addr_row, _ADDR_W)
            self._cell(page, dob, _DOB_CENTRE, addr_row, _DOB_W, centre=True)
            self._cell(page, pass_line, _VALUE_X, pass_row, _WIDE_W)
            self._cell(page, phone, _VALUE_X, phone_row, _ADDR_W)
            self._cell(page, citizenship, _VALUE_X, citiz_row, _ADDR_W)
        self._cell(page, region, _VALUE_X, _Z_REGION, _ADDR_W)

        # -- policy number: red digits, barcode, digits under the barcode --
        self._text(page, number, _NUM_CENTRE, _NUM_BASE, size=_NUM_SIZE,
                   bold=True, centre=True, colour=_RED)
        draw_code128(page, number, fitz.Rect(*_BARCODE))
        self._text(page, number, (_BARCODE[0] + _BARCODE[2]) / 2,
                   _BAR_DIGITS_BASE, size=8.5, centre=True)

        # -- validity sentence --------------------------------------------
        sentence = (
            f"Срок действия полиса: Настоящий полис вступает в силу с "
            f"{_date_long_g(start_date)} 00 ч. 00 мин. но не ранее даты уплаты "
            f"страховой премии, и действует по {_date_long_g(end_date)} "
            f"24 ч. 00 мин."
        )
        font = fitz.Font(fontfile=str(_font_file(_REG)))
        y = _SROK_BASE
        for line in _wrap(sentence, font, _SROK_SIZE, _SROK_W):
            page.insert_text((_SROK_X, y), line, fontname="dms_r",
                             fontsize=_SROK_SIZE)
            y += _SROK_LEAD

    def _cell(self, page, text: str, x: float, row: tuple[float, float],
              width: float, *, size: float = 9.5, centre: bool = False) -> None:
        if not text:
            return
        baseline = (row[0] + row[1]) / 2 + size * 0.34   # visually centred
        self._text(page, text, x, baseline, size=size, width=width, centre=centre)

    @staticmethod
    def _text(page, text: str, x: float, baseline: float, *, size: float,
              width: float | None = None, centre: bool = False,
              bold: bool = False, colour=(0, 0, 0)) -> None:
        if not text:
            return
        name = "dms_b" if bold else "dms_r"
        font = fitz.Font(fontfile=str(_font_file(_BOLD if bold else _REG)))
        if width:
            while size > 5.5 and font.text_length(text, fontsize=size) > width:
                size -= 0.25
        left = x - font.text_length(text, fontsize=size) / 2 if centre else x
        page.insert_text((left, baseline), text, fontname=name, fontsize=size,
                         color=colour)

    @staticmethod
    def _output_path(passport: Passport, base: Path | None) -> Path:
        folder = base if base is not None else paths.output_dir() / "dms"
        folder.mkdir(parents=True, exist_ok=True)
        stem = "".join(c if c.isalnum() or c in " _-" else "_"
                       for c in f"{passport.surname}_{passport.name}".upper()).strip()
        candidate = folder / f"{stem or 'DMS'}.pdf"
        i = 1
        while candidate.exists():
            candidate = folder / f"{stem}_{i:03d}.pdf"
            i += 1
        return candidate


def _wrap(text: str, font, size: float, width: float) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        cand = f"{cur} {word}".strip()
        if cur and font.text_length(cand, fontsize=size) > width:
            lines.append(cur)
            cur = word
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return lines
