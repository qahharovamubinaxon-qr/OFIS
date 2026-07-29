"""ТРУД ППУ — the three sheets the office prints from a worker's patent.

One run takes what the office already has in the worker's folder: the
трудовой договор, the уведомление the МВД accepted, both sides of the patent,
and the worker's photograph. Out come three sheets:

* the ППУ front, exactly as the ППУ section prints it;
* the Госуслуги patent page, with the patent's series, number, dates, case
  number, the contract's date and the firm on it;
* the Госуслуги notification page, with the notification's number and the
  worker's Ф.И.О.

Like the ППУ, the finished package is saved to the desktop as PICTURES — that
is how the office files them.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.common.errors import ValidationError
from src.common.logging import get_logger
from src.config import paths
from src.pdf.ppu_renderer import PAGE_FILES as PPU_PAGE_FILES
from src.pdf.ppu_renderer import pages_as_png
from src.pdf.trud_ppu_renderer import (
    TrudPpuData,
    case_number,
    patent_serial,
    plus_one_year,
    render,
)
from src.pdf.trud_ppu_spec import PAGE_FILES
from src.services.ppu_service import desktop_target

log = get_logger(__name__)

#: The ППУ front blank, which sheet 1 is printed on. Sheet 1 must be identical
#: to the ППУ's own front sheet, so it is taken from the ППУ template the
#: operator already selected rather than uploaded a second time.
FRONT_FILE = PPU_PAGE_FILES[0]


@dataclass(frozen=True)
class TrudPpuResult:
    pdf: bytes
    #: the three sheets, as PNG bytes
    pages: list[bytes]
    #: where each sheet was written
    saved: list[Path]
    #: what went on sheet 2, for the operator to check at a glance
    patent: str
    case_number: str
    firm: str
    valid_to: date | None


def _folder() -> Path:
    return paths.user_templates_dir() / "trud_ppu"


def _file_stem(surname: str) -> str:
    stem = "".join(c for c in (surname or "").strip()
                   if c.isalnum() or c in " _-").strip()
    return stem or "ТРУД ППУ"


class TrudPpuService:
    def __init__(self, settings=None) -> None:
        self._settings = settings

    # ---------------------------------------------------------- templates
    def templates(self) -> list[Path]:
        """The sheet-2/sheet-3 blank pairs on offer.

        Empty until the office uploads one — the pages are photographs of the
        Госуслуги site taken in the office, so nothing can be bundled.
        """
        out = []
        bundled = paths.templates_dir() / "trud_ppu" / "standart"
        if all((bundled / name).exists() for name in PAGE_FILES):
            out.append(bundled)
        folder = _folder()
        if folder.exists():
            out += sorted(p for p in folder.iterdir()
                          if p.is_dir()
                          and all((p / name).exists() for name in PAGE_FILES))
        return out

    def add_template(self, name: str, page2: Path, page3: Path) -> Path:
        """Register a blank pair — sheet 2 (patent page), then sheet 3."""
        name = "".join(c for c in name.strip() if c.isalnum() or c in " _-").strip()
        if not name:
            raise ValidationError("Шаблонга ном керак")
        for src in (page2, page3):
            if src.suffix.lower() != ".pdf" or not src.exists():
                raise ValidationError("2- ва 3-саҳифа бланкаси PDF бўлиши керак",
                                      context={"path": str(src)})
        dest = _folder() / name
        dest.mkdir(parents=True, exist_ok=True)
        for src, target in zip((page2, page3), PAGE_FILES, strict=True):
            shutil.copyfile(src, dest / target)
        log.info("ТРУД ППУ шаблони қўшилди: %s", name)
        return dest

    # ----------------------------------------------------------- printing
    def generate(
        self,
        *,
        surname: str,
        name: str,
        patronymic: str = "",
        birth_date: date | None = None,
        gender: str = "",
        citizenship: str = "",
        document: str = "",
        patent_series: str = "",
        patent_number: str = "",
        patent_issue: date | None = None,
        patent_to: date | None = None,
        contract_date: date | None = None,
        firm: str = "",
        uved_number: str = "",
        uved_fio: str = "",
        photo: bytes | None = None,
        ppu_template: Path | None = None,
        template: Path | None = None,
    ) -> TrudPpuResult:
        if not surname.strip() or not name.strip():
            raise ValidationError("Фамилия ва Исм бўш бўлмасин")
        if ppu_template is None:
            raise ValidationError(
                "ППУ бланкаси юкланмаган — 1-саҳифа ППУ нинг олд бланкасига "
                "босилади. ППУ бўлимида «Шаблон қўшиш» орқали юкланг.")
        front = Path(ppu_template) / FRONT_FILE
        if not front.exists():
            raise ValidationError("ППУ шаблонида олд бланка йўқ",
                                  context={"path": str(front)})
        if template is None:
            raise ValidationError(
                "ТРУД ППУ бланкаси юкланмаган — «Шаблон қўшиш» орқали 2- ва "
                "3-саҳифани юкланг.")
        page2, page3 = (Path(template) / part for part in PAGE_FILES)

        data = TrudPpuData(
            surname=surname, name=name, patronymic=patronymic,
            birth_date=birth_date, gender=gender, citizenship=citizenship,
            document=document, photo=photo,
            patent_series=patent_series, patent_number=patent_number,
            patent_issue=patent_issue, patent_to=patent_to,
            contract_date=contract_date, firm=firm,
            uved_number=uved_number, uved_fio=uved_fio)
        pdf = render(data, front=front, page2=page2, page3=page3)
        pages = pages_as_png(pdf)

        stem = _file_stem(surname)
        saved = []
        for index, png in enumerate(pages, 1):
            target = desktop_target(f"{stem} ТРУД ППУ {index}.png")
            target.write_bytes(png)
            saved.append(target)

        log.info("ТРУД ППУ: %s — %d саҳифа сақланди", surname, len(saved))
        return TrudPpuResult(
            pdf=pdf, pages=pages, saved=saved,
            patent=patent_serial(patent_series, patent_number),
            case_number=case_number(patent_series, patent_number),
            firm=(firm or "").strip(),
            valid_to=patent_to or plus_one_year(patent_issue))
