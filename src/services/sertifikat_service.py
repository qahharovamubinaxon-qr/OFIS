"""СЕРТИФИКАТ — the Russian-language certificate учебный центр «СФЕРА» issues.

One run takes the student's passport, the city the exam was sat in and the day
it was issued, and prints the certificate: two pages, the reverse of the
security paper and then the printed face.

What the section decides for itself
-----------------------------------
* **the end date.** Three years to the day before — 10.07.2026 runs to
  09.07.2029. The operator types the start; the end follows.
* **the two numbers.** «Регистрационный № 002010264154» and the thirteen
  figures under the barcode both keep their block and re-roll their last three
  figures for every certificate printed, so no two leave the centre carrying the
  same number. The block itself stays in the boxes and can be corrected — it is
  the centre's own, not the program's to invent.
"""

from __future__ import annotations

import secrets
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.common.errors import ValidationError
from src.common.logging import get_logger
from src.config import paths
from src.pdf.sertifikat_renderer import (
    PAGE_FILES,
    SertifikatData,
    render,
    roll_number,
    valid_until,
)
from src.pdf.sertifikat_spec import (
    DEFAULT_BARCODE,
    DEFAULT_REG_NUMBER,
    ROLL_DIGITS,
)

log = get_logger(__name__)

KEY_REG = "sertifikat.reg_number"
KEY_BARCODE = "sertifikat.barcode"
KEY_CITY = "sertifikat.city"

BUNDLED_NAME = "standart"

#: The two the centre works in; anything else can still be typed over them.
CITIES = ("Москва", "Московская область")


@dataclass(frozen=True)
class SertifikatResult:
    pdf: bytes
    filename: str
    reg_number: str
    barcode_number: str
    issued_on: date
    valid_until: date


def _folder() -> Path:
    return paths.user_templates_dir() / "sertifikat"


def _file_stem(surname: str) -> str:
    """The certificate is filed under the student's surname, and nothing else."""
    stem = "".join(c for c in surname.strip()
                   if c.isalnum() or c in " _-").strip()
    return stem or "Сертификат"


def desktop_target(filename: str) -> Path:
    """Where on the desktop this certificate goes, without treading on another."""
    folder = paths.desktop_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / filename
    stem, suffix = target.stem, target.suffix
    counter = 2
    while target.exists():
        target = folder / f"{stem} ({counter}){suffix}"
        counter += 1
    return target


class SertifikatService:
    def __init__(self, settings=None) -> None:
        self._settings = settings

    # ----------------------------------------------------------- settings
    def _get(self, key: str, default: str = "") -> str:
        if self._settings is None:
            return default
        try:
            value = self._settings.get(key)
        except TypeError:                       # a repository that wants a default
            value = self._settings.get(key, default)
        return str(value) if value not in (None, "") else default

    def _set(self, key: str, value: str) -> None:
        if self._settings is not None:
            self._settings.set(key, value)

    # ------------------------------------------------------------ numbers
    def blocks(self) -> tuple[str, str]:
        """(регистрационный №, the figures under the barcode) as they stand."""
        return (self._get(KEY_REG, DEFAULT_REG_NUMBER),
                self._get(KEY_BARCODE, DEFAULT_BARCODE))

    def remember_blocks(self, reg_number: str, barcode: str) -> None:
        """Keep whatever block the operator corrected them to."""
        if reg_number.strip():
            self._set(KEY_REG, reg_number.strip())
        if barcode.strip():
            self._set(KEY_BARCODE, barcode.strip())

    def city(self) -> str:
        return self._get(KEY_CITY, CITIES[0])

    @staticmethod
    def roll(number: str) -> str:
        """Re-roll the last three figures of ``number``.

        ``secrets`` rather than ``random``: two certificates printed a second
        apart must not be able to come out with the same tail, and a seeded
        generator is exactly the way that happens.
        """
        tail = "".join(str(secrets.randbelow(10)) for _ in range(ROLL_DIGITS))
        return roll_number(number, ROLL_DIGITS, tail)

    # ---------------------------------------------------------- templates
    def templates(self) -> list[Path]:
        """The blanks on offer — the bundled one first, then any added."""
        out = []
        bundled = paths.templates_dir() / "sertifikat" / BUNDLED_NAME
        if (bundled / PAGE_FILES[1]).exists():
            out.append(bundled)
        folder = _folder()
        if folder.exists():
            out += sorted(p for p in folder.iterdir()
                          if p.is_dir() and (p / PAGE_FILES[1]).exists())
        return out

    def add_template(self, name: str, page1: Path, page2: Path) -> Path:
        """Register a redesigned blank — the reverse, then the printed face."""
        name = "".join(c for c in name.strip() if c.isalnum() or c in " _-").strip()
        if not name:
            raise ValidationError("Шаблонга ном керак")
        for src in (page1, page2):
            if src.suffix.lower() != ".pdf" or not src.exists():
                raise ValidationError("Иккала саҳифа ҳам PDF бўлиши керак",
                                      context={"path": str(src)})
        dest = _folder() / name
        dest.mkdir(parents=True, exist_ok=True)
        for src, target in zip((page1, page2), PAGE_FILES, strict=True):
            shutil.copyfile(src, dest / target)
        log.info("Сертификат шаблони қўшилди: %s", name)
        return dest

    # ----------------------------------------------------------- printing
    def generate(
        self,
        *,
        surname: str,
        name: str,
        patronymic: str = "",
        city: str = "",
        issued_on: date,
        reg_number: str = "",
        barcode_number: str = "",
        template: Path | None = None,
    ) -> SertifikatResult:
        if not surname.strip() or not name.strip():
            raise ValidationError("Фамилия ва Исм бўш бўлмасин")
        if issued_on is None:
            raise ValidationError("Берилган сана киритилмаган")

        block_reg, block_barcode = self.blocks()
        reg_block = reg_number.strip() or block_reg
        barcode_block = barcode_number.strip() or block_barcode
        city = city.strip() or self.city()

        printed_reg = self.roll(reg_block)
        printed_barcode = self.roll(barcode_block)

        data = SertifikatData(
            surname=surname, name=name, patronymic=patronymic, city=city,
            issued_on=issued_on, reg_number=printed_reg,
            barcode_number=printed_barcode)
        pdf = render(data, template)

        self.remember_blocks(reg_block, barcode_block)
        self._set(KEY_CITY, city)

        log.info("Сертификат: %s %s — %s, рег %s", surname, name, city, printed_reg)
        return SertifikatResult(
            pdf=pdf, filename=f"{_file_stem(surname)}.pdf",
            reg_number=printed_reg, barcode_number=printed_barcode,
            issued_on=issued_on, valid_until=valid_until(issued_on))
