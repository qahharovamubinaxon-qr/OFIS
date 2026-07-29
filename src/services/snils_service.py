"""СНИЛС — «Ишчининг СНИЛС номери», one sheet per worker.

The passport gives the name, the birth date, the country of birth and the sex;
the operator types the registration date and, when it differs from the one
already standing in the box, the СНИЛС number.

Blanks can be added and — unlike the other sections — removed again. The office
asked for that: they redesign this sheet often, and a list of dead blanks is a
list of ways to print the wrong one.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.common.errors import ValidationError
from src.common.logging import get_logger
from src.config import paths
from src.pdf.snils_renderer import BLANK_FILE, SnilsData, format_snils, render
from src.pdf.snils_spec import DEFAULT_SNILS

log = get_logger(__name__)

KEY_SNILS = "snils.number"
BUNDLED_NAME = "standart"


@dataclass(frozen=True)
class SnilsResult:
    pdf: bytes
    filename: str
    snils: str
    reg_date: date | None


def _folder() -> Path:
    return paths.user_templates_dir() / "snils"


def _file_stem(surname: str) -> str:
    stem = "".join(c for c in (surname or "").strip()
                   if c.isalnum() or c in " _-").strip()
    return stem or "СНИЛС"


def desktop_target(filename: str) -> Path:
    """Where on the desktop this sheet goes, without treading on another."""
    folder = paths.desktop_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / filename
    stem, suffix = target.stem, target.suffix
    counter = 2
    while target.exists():
        target = folder / f"{stem} ({counter}){suffix}"
        counter += 1
    return target


class SnilsService:
    def __init__(self, settings=None) -> None:
        self._settings = settings

    # ----------------------------------------------------------- settings
    def _get(self, key: str, default: str = "") -> str:
        if self._settings is None:
            return default
        try:
            value = self._settings.get(key)
        except TypeError:
            value = self._settings.get(key, default)
        return str(value) if value not in (None, "") else default

    def _set(self, key: str, value: str) -> None:
        if self._settings is not None:
            self._settings.set(key, value)

    def number(self) -> str:
        """The number standing in the box — the office's own until changed."""
        return self._get(KEY_SNILS, DEFAULT_SNILS)

    # ---------------------------------------------------------- templates
    def templates(self) -> list[Path]:
        """The blanks on offer — the bundled one first, then any added."""
        out = []
        bundled = paths.templates_dir() / "snils" / BUNDLED_NAME
        if (bundled / BLANK_FILE).exists():
            out.append(bundled)
        folder = _folder()
        if folder.exists():
            out += sorted(p for p in folder.iterdir()
                          if p.is_dir() and (p / BLANK_FILE).exists())
        return out

    def add_template(self, name: str, blank: Path) -> Path:
        """Register another blank."""
        name = "".join(c for c in name.strip() if c.isalnum() or c in " _-").strip()
        if not name:
            raise ValidationError("Шаблонга ном керак")
        if blank.suffix.lower() != ".pdf" or not blank.exists():
            raise ValidationError("Бланка PDF бўлиши керак",
                                  context={"path": str(blank)})
        dest = _folder() / name
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(blank, dest / BLANK_FILE)
        log.info("СНИЛС шаблони қўшилди: %s", name)
        return dest

    def remove_template(self, folder: Path) -> None:
        """Delete a blank the office has finished with.

        Only ever one the office added: the bundled sheet ships with the
        program and deleting it would leave the section with nothing to print
        on until somebody uploaded a replacement.
        """
        folder = Path(folder).resolve()
        mine = _folder().resolve()
        if mine not in folder.parents:
            raise ValidationError(
                "Дастур билан келган бланкани ўчириб бўлмайди — "
                "фақат ўзингиз юклаганини ўчириш мумкин.")
        if not folder.exists():
            return
        shutil.rmtree(folder)
        log.info("СНИЛС шаблони ўчирилди: %s", folder.name)

    # ----------------------------------------------------------- printing
    def generate(
        self,
        *,
        surname: str,
        name: str,
        patronymic: str = "",
        birth_date: date | None = None,
        birth_place: str = "",
        gender: str = "",
        reg_date: date,
        snils: str = "",
        template: Path | None = None,
    ) -> SnilsResult:
        if not surname.strip() or not name.strip():
            raise ValidationError("Фамилия ва Исм бўш бўлмасин")

        number = snils.strip() or self.number()
        folders = self.templates()
        chosen = Path(template) if template else (folders[0] if folders else None)
        if chosen is None:
            raise ValidationError(
                "СНИЛС бланкаси йўқ — «Бланка қўшиш» орқали PDF юкланг.")

        data = SnilsData(
            surname=surname, name=name, patronymic=patronymic,
            birth_date=birth_date, birth_place=birth_place, gender=gender,
            reg_date=reg_date, snils=number)
        pdf = render(data, chosen)

        self._set(KEY_SNILS, number)
        printed = format_snils(number)
        log.info("СНИЛС: %s %s — %s", surname, name, printed)
        return SnilsResult(pdf=pdf, filename=f"{_file_stem(surname)} СНИЛС.pdf",
                           snils=printed, reg_date=reg_date)
