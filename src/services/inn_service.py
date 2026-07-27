"""ИНН — the office's own record sheet of a worker's tax number.

ООО «СФЕРА» keeps one of these in every worker's folder: the company letterhead,
the worker's ФИО, sex, date of birth and citizenship, the date, and the twelve
digits of the ИНН the tax office assigned. Nothing here is a state document —
it is the office's internal filing card, so the number is simply the one the
operator types in.

Values are set in Times New Roman, matching the sheet's own labels, at the
coordinates measured off the office's filled copy. The blank is replaceable:
drop a new design into AppData and the module prints on that instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import fitz

from src.common.errors import OfisError
from src.common.logging import get_logger
from src.config import paths
from src.domain.documents import Passport
from src.domain.enums import Gender
from src.pdf.engine import _font_file
from src.pdf.formatters import _date_dmy

log = get_logger(__name__)

INN_DIGITS = 12

_BUNDLED_BLANK = paths.templates_dir() / "inn" / "blank.pdf"

# ---------------------------------------------------------------- geometry
# Times New Roman, as the sheet's own labels use.
_REG, _BOLD = "OfisSerif", "OfisSerifBold"
_SIZE = 11.4

_FIO_CENTRE, _FIO_BASE = 305.2, 265.5      # centred over the long rule
_FIO_MAX_W = 320.0
_SEX_X, _SEX_BASE = 116.6, 296.5
_SEX_MAX_W = 100.0
_DOB_CENTRE, _DOB_BASE = 421.4, 296.5
_CITIZ_X, _CITIZ_BASE = 176.5, 329.9
_CITIZ_MAX_W = 250.0
_DAY_X, _DAY_BASE = 161.5, 425.3

# the twelve ИНН cells
_INN_FIRST_CENTRE, _INN_PITCH, _INN_BASE = 292.8, 17.26, 425.3


@dataclass(frozen=True)
class InnResult:
    pdf_path: Path
    inn: str
    surname: str


def user_blank_path() -> Path:
    """Where the office drops its own design of the sheet.

    In AppData, so `git pull` and rebuilding the EXE never overwrite it.
    """
    return paths.user_templates_dir() / "inn" / "blank.pdf"


def blank_source() -> tuple[Path, bool]:
    """(the file to print on, True when it is the office's own upload)."""
    own = user_blank_path()
    if own.exists():
        return own, True
    return _BUNDLED_BLANK, False


def import_blank(source: Path) -> Path:
    """Adopt ``source`` as the sheet, after a sanity check on the page size."""
    import shutil

    try:
        doc = fitz.open(source)
    except Exception as exc:  # noqa: BLE001 - any unreadable file
        raise OfisError("PDF ochilmadi — boshqa fayl tanlang.") from exc
    try:
        if len(doc) < 1:
            raise OfisError("PDF bo'sh.")
        rect = doc[0].rect
        if not (560 < rect.width < 640 and 800 < rect.height < 880):
            raise OfisError(
                "Bu A4 emas — ИНН varag'ining PDF sini yuklang "
                f"(hozirgi o'lcham {rect.width:.0f}×{rect.height:.0f} pt).")
    finally:
        doc.close()

    target = user_blank_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    log.info("ИНН blank replaced from %s", source)
    return target


def normalise_inn(raw: str) -> str:
    """Keep the digits only and check there are exactly twelve of them."""
    digits = re.sub(r"\D", "", raw or "")
    if not digits:
        raise OfisError("ИНН рақамини киритинг.")
    if len(digits) != INN_DIGITS:
        raise OfisError(
            f"ИНН {INN_DIGITS} та рақамдан иборат бўлади "
            f"(сиз {len(digits)} та ёздингиз).")
    return digits


def _title(text: str) -> str:
    return " ".join(w[:1].upper() + w[1:].lower() for w in (text or "").split())


class InnService:
    def generate(
        self,
        passport: Passport,
        *,
        inn: str,
        form_date: date,
        output_dir: Path | None = None,
    ) -> InnResult:
        digits = normalise_inn(inn)
        blank, _own = blank_source()
        if not blank.exists():
            raise OfisError(
                "ИНН бланкаси топилмади. Sozlamalar → ИНН → «Бланка юклаш» "
                "орқали варақнинг PDF сини юкланг.")

        doc = fitz.open(blank)
        try:
            page = doc[0]
            page.insert_font(fontname="inn_r", fontfile=str(_font_file(_REG)))
            page.insert_font(fontname="inn_b", fontfile=str(_font_file(_BOLD)))
            self._fill(page, passport, digits, form_date)
            out = self._output_path(passport, digits, output_dir)
            doc.save(str(out), garbage=4, deflate=True)
        finally:
            doc.close()

        log.info("ИНН %s for %s → %s", digits, passport.surname, out.name)
        return InnResult(pdf_path=out, inn=digits, surname=passport.surname)

    # ------------------------------------------------------------------
    def _fill(self, page, passport: Passport, digits: str, form_date: date) -> None:
        fio = " ".join(x for x in (passport.surname, passport.name,
                                   passport.patronymic) if x).upper()
        self._text(page, fio, _FIO_CENTRE, _FIO_BASE, centre=True, width=_FIO_MAX_W)

        if passport.gender is not None:
            sex = "мужской" if passport.gender == Gender.MALE else "женский"
            self._text(page, sex, _SEX_X, _SEX_BASE, width=_SEX_MAX_W)

        if passport.birth_date:
            self._text(page, _date_dmy(passport.birth_date), _DOB_CENTRE,
                       _DOB_BASE, centre=True)

        self._text(page, _title(passport.nationality or "").upper(), _CITIZ_X,
                   _CITIZ_BASE, width=_CITIZ_MAX_W)
        self._text(page, _date_dmy(form_date), _DAY_X, _DAY_BASE)

        for i, digit in enumerate(digits):
            self._text(page, digit, _INN_FIRST_CENTRE + i * _INN_PITCH,
                       _INN_BASE, centre=True)

    @staticmethod
    def _text(page, text: str, x: float, baseline: float, *,
              centre: bool = False, width: float | None = None,
              size: float = _SIZE) -> None:
        if not text:
            return
        font = fitz.Font(fontfile=str(_font_file(_BOLD)))
        if width:
            while size > 6 and font.text_length(text, fontsize=size) > width:
                size -= 0.25
        left = x - font.text_length(text, fontsize=size) / 2 if centre else x
        page.insert_text((left, baseline), text, fontname="inn_b", fontsize=size)

    @staticmethod
    def _output_path(passport: Passport, digits: str, base: Path | None) -> Path:
        folder = base if base is not None else paths.output_dir() / "inn"
        folder.mkdir(parents=True, exist_ok=True)
        stem = "".join(c if c.isalnum() or c in " _-" else "_"
                       for c in f"{passport.surname}_{digits}".upper()).strip()
        candidate = folder / f"{stem or 'INN'}.pdf"
        i = 1
        while candidate.exists():
            candidate = folder / f"{stem}_{i:03d}.pdf"
            i += 1
        return candidate
