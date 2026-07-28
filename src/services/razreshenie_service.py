"""РАЗРЕШЕНИЯ — the work permit card the office issues to its own workers.

One run takes the worker's passport, their photograph, the job they are being
allowed to do and the day the permit starts, and prints the card's two sides.

What the section remembers between workers
------------------------------------------
* **the two numbers.** «Серия 77 № 1354593» on the front and «ВВ 0035453» on
  the back both step by one for every card printed — 1354594, 1354595 … and
  0035454, 0035455 … The operator sees the number the next card will carry
  before printing it, and may correct it: whatever they print, counting goes on
  from there. Nothing is ever invented out of thin air; the office's own block
  is what is being handed out.
* **the firm.** The name and ИНН stay in the boxes for every worker after,
  until somebody types a different firm — and then the one before is kept in
  the list, because the office issues for several of its own companies and goes
  back and forth between them.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.common.errors import ValidationError
from src.common.logging import get_logger
from src.config import paths
from src.pdf.razreshenie_renderer import RazreshenieData, cover_until, render

log = get_logger(__name__)

KEY_SERIA = "razreshenie.seria"
KEY_NUMBER = "razreshenie.number_next"
KEY_BACK = "razreshenie.back_next"
KEY_FIRM_NAME = "razreshenie.firm_name"
KEY_FIRM_INN = "razreshenie.firm_inn"
KEY_FIRMS = "razreshenie.firms"

#: What the office's own card carried, so the very first run starts somewhere
#: sensible instead of at zero. The operator overwrites it if their block
#: begins elsewhere.
DEFAULT_SERIA = "77"
DEFAULT_NUMBER = "1354593"
DEFAULT_BACK = "0035453"

BUNDLED_NAME = "standart"


@dataclass(frozen=True)
class Firm:
    name: str
    inn: str


@dataclass(frozen=True)
class RazreshenieResult:
    pdf: bytes
    filename: str
    seria: str
    number: str
    back_number: str
    valid_from: date
    valid_to: date


def _folder() -> Path:
    return paths.user_templates_dir() / "razreshenie"


def _file_stem(surname: str) -> str:
    """The card is filed under the worker's surname, and nothing else."""
    stem = "".join(c for c in surname.strip()
                   if c.isalnum() or c in " _-").strip()
    return stem or "Разрешение"


def desktop_target(filename: str) -> Path:
    """Where on the desktop this card goes, without treading on another.

    Two workers can share a surname, and a card already printed is not the
    program's to overwrite — the second one becomes «Саидов (2).pdf».
    """
    folder = paths.desktop_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / filename
    stem, suffix = target.stem, target.suffix
    counter = 2
    while target.exists():
        target = folder / f"{stem} ({counter}){suffix}"
        counter += 1
    return target


class RazreshenieService:
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
    def next_numbers(self) -> tuple[str, str, str]:
        """(серия, № on the front, ВВ № on the back) the next card would carry."""
        return (self._get(KEY_SERIA, DEFAULT_SERIA),
                self._get(KEY_NUMBER, DEFAULT_NUMBER),
                self._get(KEY_BACK, DEFAULT_BACK))

    @staticmethod
    def _step(value: str, width: int) -> str:
        """«0035453» → «0035454», keeping the leading zeros the card prints."""
        digits = "".join(c for c in value if c.isdigit())
        if not digits:
            return ""
        return str(int(digits) + 1).rjust(len(digits) or width, "0")

    def remember_numbers(self, seria: str, number: str, back_number: str) -> None:
        """Count on from the card just printed, whatever number it carried."""
        self._set(KEY_SERIA, seria.strip() or DEFAULT_SERIA)
        self._set(KEY_NUMBER, self._step(number, 7))
        self._set(KEY_BACK, self._step(back_number, 7))

    # -------------------------------------------------------------- firms
    def firm(self) -> Firm:
        """The firm still standing in the boxes from the last worker."""
        return Firm(self._get(KEY_FIRM_NAME), self._get(KEY_FIRM_INN))

    def firms(self) -> list[Firm]:
        """Every firm the office has issued for, newest first."""
        try:
            rows = json.loads(self._get(KEY_FIRMS, "[]"))
        except (TypeError, ValueError):
            return []
        return [Firm(str(r.get("name", "")), str(r.get("inn", "")))
                for r in rows if isinstance(r, dict) and r.get("name")]

    def remember_firm(self, name: str, inn: str) -> None:
        """Keep this firm in the boxes, and keep the one before it in the list."""
        name, inn = name.strip(), inn.strip()
        if not name:
            return
        self._set(KEY_FIRM_NAME, name)
        self._set(KEY_FIRM_INN, inn)
        kept = [f for f in self.firms() if (f.name, f.inn) != (name, inn)]
        rows = [{"name": name, "inn": inn}] + [
            {"name": f.name, "inn": f.inn} for f in kept]
        self._set(KEY_FIRMS, json.dumps(rows[:30], ensure_ascii=False))

    # ---------------------------------------------------------- templates
    def templates(self) -> list[Path]:
        """The blank pairs on offer — the bundled one first, then the added."""
        out = []
        bundled = paths.templates_dir() / "razreshenie" / BUNDLED_NAME
        if (bundled / "front.pdf").exists():
            out.append(bundled)
        folder = _folder()
        if folder.exists():
            out += sorted(p for p in folder.iterdir()
                          if p.is_dir() and (p / "front.pdf").exists())
        return out

    def add_template(self, name: str, front: Path, back: Path) -> Path:
        """Register another insurer's — or another year's — pair of blanks."""
        name = "".join(c for c in name.strip() if c.isalnum() or c in " _-").strip()
        if not name:
            raise ValidationError("Шаблонга ном керак")
        for src in (front, back):
            if src.suffix.lower() != ".pdf" or not src.exists():
                raise ValidationError("Олд ва орқа бланка PDF бўлиши керак",
                                      context={"path": str(src)})
        dest = _folder() / name
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(front, dest / "front.pdf")
        shutil.copyfile(back, dest / "back.pdf")
        log.info("Разрешение шаблони қўшилди: %s", name)
        return dest

    # ----------------------------------------------------------- printing
    def generate(
        self,
        *,
        surname: str,
        name: str,
        patronymic: str = "",
        birth_date: date | None = None,
        citizenship: str = "",
        document: str = "",
        inn: str = "",
        activity: str,
        valid_from: date,
        firm_name: str,
        firm_inn: str = "",
        seria: str = "",
        number: str = "",
        back_number: str = "",
        photo: bytes | None = None,
        template: Path | None = None,
    ) -> RazreshenieResult:
        if not surname.strip() or not name.strip():
            raise ValidationError("Фамилия ва Исм бўш бўлмасин")
        if not activity.strip():
            raise ValidationError("«Вид деятельности» (должность) киритилмаган")
        if not firm_name.strip():
            raise ValidationError("Фирма номи киритилмаган")

        auto_seria, auto_number, auto_back = self.next_numbers()
        seria = seria.strip() or auto_seria
        number = number.strip() or auto_number
        back_number = back_number.strip() or auto_back

        data = RazreshenieData(
            surname=surname, name=name, patronymic=patronymic,
            birth_date=birth_date, citizenship=citizenship, document=document,
            inn=inn, activity=activity, valid_from=valid_from,
            firm_name=firm_name, firm_inn=firm_inn, seria=seria,
            number=number, back_number=back_number, photo=photo)
        pdf = render(data, template)

        self.remember_numbers(seria, number, back_number)
        self.remember_firm(firm_name, firm_inn)

        log.info("Разрешение: %s %s — %s №%s / ВВ %s",
                 surname, name, seria, number, back_number)
        return RazreshenieResult(
            pdf=pdf, filename=f"{_file_stem(surname)}.pdf",
            seria=seria, number=number, back_number=back_number,
            valid_from=valid_from, valid_to=cover_until(valid_from))
