"""2 НДФЛ — each firm's own sheet, and the справка printed onto it.

A firm here is a folder holding ONE thing: the firm's own empty справка,
already carrying its ОКТМО, ИНН, КПП, телефон, налоговый агент, signature
and stamp. The office adds a firm by uploading that sheet; the program
writes only the worker, his months and the four sums.

What the office drags in «📐» is kept per firm — under the FIRM's name,
never under the file's, so one firm's arrangement is never another's.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from src.common.errors import ValidationError
from src.common.logging import get_logger
from src.config import paths
from src.pdf.ndfl2_renderer import Ndfl2Data, output_stem, render

log = get_logger(__name__)

SECTION = "ndfl2"


def bundled_blank() -> Path:
    """The sheet the office handed over, shipped so the section works at once."""
    return paths.templates_dir() / "ndfl2" / "blank.pdf"


def firms_dir() -> Path:
    folder = paths.user_templates_dir() / "ndfl2"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _safe(name: str) -> str:
    cleaned = "".join(c for c in (name or "").strip()
                      if c.isalnum() or c in " _-.«»\"'").strip()
    if not cleaned:
        raise ValidationError("Фирма номи керак")
    return cleaned


def layout_key(firm: Path) -> str:
    """This firm's arrangement is filed under the FIRM, not the file."""
    return Path(firm).name


def load_layout(firm: Path) -> dict:
    from src.services import blank_layout

    return blank_layout.load(SECTION, layout_key(firm))


def save_layout(firm: Path, layout: dict) -> None:
    from src.services import blank_layout

    blank_layout.save(SECTION, layout_key(firm), layout)


@dataclass(frozen=True)
class Ndfl2Result:
    pdf_path: Path
    surname: str
    total: Decimal
    tax: Decimal


class Ndfl2Service:
    def __init__(self, settings=None) -> None:
        self._settings = settings

    # -------------------------------------------------------------- firms
    def firms(self) -> list[Path]:
        self._seed()
        return sorted(p for p in firms_dir().iterdir() if p.is_dir())

    def _seed(self) -> None:
        """The office's own sheet, copied in once so the section is usable."""
        source = bundled_blank()
        if not source.exists():
            return
        first = firms_dir() / "ООО ТРАЙД"
        if first.exists() or any(p.is_dir() for p in firms_dir().iterdir()):
            return
        first.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, first / "blank.pdf")
        log.info("2НДФЛ: биринчи фирма бланкаси қўйилди")

    def add_firm(self, name: str, blank: Path) -> Path:
        blank = Path(blank)
        if blank.suffix.lower() != ".pdf" or not blank.exists():
            raise ValidationError("Бланка PDF бўлиши керак")
        folder = firms_dir() / _safe(name)
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(blank, folder / "blank.pdf")
        log.info("2НДФЛ: «%s» фирмаси қўшилди", folder.name)
        return folder

    def remove_firm(self, firm: Path) -> None:
        shutil.rmtree(Path(firm), ignore_errors=True)

    @staticmethod
    def blank(firm: Path) -> Path | None:
        found = Path(firm) / "blank.pdf"
        return found if found.exists() else None

    # ----------------------------------------------------------- printing
    def generate(self, data: Ndfl2Data, firm: Path | None,
                 output_dir: Path | None = None) -> Ndfl2Result:
        if firm is None:
            raise ValidationError("Фирмани танланг.")
        firm = Path(firm)
        blank = self.blank(firm)
        if blank is None:
            raise ValidationError(
                f"«{firm.name}» да бланка йўқ — PDF ини юкланг.")
        if not (data.surname or "").strip():
            raise ValidationError("Фамилия керак — ҳужжатларни ўқитинг")
        if not data.months:
            raise ValidationError("Камида битта ойнинг ойлигини киритинг")
        data.layout = load_layout(firm)
        pdf = render(data, blank)

        folder = output_dir if output_dir is not None else (
            paths.output_dir() / "ndfl2")
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{output_stem(data)}.pdf"
        counter = 2
        while target.exists():
            target = folder / f"{output_stem(data)}_{counter:03d}.pdf"
            counter += 1
        target.write_bytes(pdf)
        log.info("2НДФЛ: %s — %s, %s ой, жами %s", data.surname, firm.name,
                 len(data.months), data.total())
        return Ndfl2Result(pdf_path=target, surname=data.surname,
                           total=data.total(), tax=data.tax())


def data_of(passport, patent, *, months: dict[int, Decimal], year: int,
            form_date: date | None, inn: str = "") -> Ndfl2Data:
    """The справка's values out of the two documents the operator dropped."""
    return Ndfl2Data(
        surname=(passport.surname if passport else "")
        or (patent.holder_surname if patent else "") or "",
        name=(passport.name if passport else "")
        or (patent.holder_name if patent else "") or "",
        patronymic=(passport.patronymic if passport else "")
        or (patent.holder_patronymic if patent else "") or "",
        inn=inn,
        birth_date=passport.birth_date if passport else None,
        doc_number=_document(passport),
        months=months, year=year, form_date=form_date)


def _document(passport) -> str:
    """«FB 0701509» → «FB0701509»; a Tajik passport has digits only."""
    if passport is None:
        return ""
    series = (passport.series or "").strip()
    number = (passport.number or "").strip()
    return f"{series}{number}".replace(" ", "")
