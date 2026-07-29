"""Fill the ТРУД ППУ package — three sheets from four documents.

Sheet 1 is the ППУ front and is filled by :func:`src.pdf.ppu_renderer._fill_front`
itself, so it can never drift from the ППУ section: same slots, same photo
window, same shrink-to-fit. Sheets 2 and 3 are the Госуслуги pages, filled at
the fractions :mod:`src.pdf.trud_ppu_spec` measured off the office's own copies.

The office writes two values that exist nowhere on the documents:

* the patent's **expiry** — exactly one year after it was issued
  (``18.07.2024`` → ``18.07.2025``). This is NOT the «a day short of a year»
  the ППУ and разрешение use: a patent runs to the same date next year, which
  is what the office's own sheet shows.
* the **«Номер дела»** — the patent's number and series the other way round
  with ``ПАТ`` after them (``77 № 2400328451`` → ``2400328451-77ПАТ``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import fitz

from src.common.logging import get_logger
from src.pdf.ppu_renderer import PpuData, _fill_front, _fonts, _write, full_name
from src.pdf.trud_ppu_spec import PAGE2, PAGE3

log = get_logger(__name__)


@dataclass(frozen=True)
class TrudPpuData:
    """Everything one ТРУД ППУ package says."""

    # --- sheet 1, the ППУ front
    surname: str = ""
    name: str = ""
    patronymic: str = ""
    birth_date: date | None = None
    gender: str = ""
    citizenship: str = ""
    #: the foreign passport, as printed at the foot of the ППУ front
    document: str = ""
    photo: bytes | None = None
    # --- sheet 2, the patent page
    patent_series: str = ""
    patent_number: str = ""
    patent_issue: date | None = None
    #: normally left unset — one year after ``patent_issue`` is what the office
    #: prints; set it only to override a patent that says otherwise
    patent_to: date | None = None
    contract_date: date | None = None
    firm: str = ""
    # --- sheet 3, the notification page
    uved_number: str = ""
    #: the Ф.И.О. as the notification prints it; falls back to sheet 1's name
    uved_fio: str = ""


def _dmy(value: date | None) -> str:
    return value.strftime("%d.%m.%Y") if value else ""


def plus_one_year(issued: date | None) -> date | None:
    """The day a patent runs to: the same date, next year.

    A patent issued on 29 February runs to 28 February — there is no 29th to
    run to, and the office would write the last day of the month by hand.
    """
    if issued is None:
        return None
    try:
        return issued.replace(year=issued.year + 1)
    except ValueError:                      # 29 February
        return issued.replace(year=issued.year + 1, day=28)


def patent_serial(series: str, number: str) -> str:
    """«77» + «2400328451» → «77 № 2400328451», as the site prints it."""
    series = "".join((series or "").split())
    number = "".join((number or "").split())
    if not number:
        return series
    return f"{series} № {number}" if series else f"№ {number}"


def case_number(series: str, number: str) -> str:
    """«77» + «2400328451» → «2400328451-77ПАТ» — the office's own «Номер дела».

    The series and the number swap places and ``ПАТ`` closes it. With no series
    there is nothing to swap, so the number is returned with ``ПАТ`` alone
    rather than a dangling dash.
    """
    series = "".join((series or "").split())
    number = "".join((number or "").split())
    if not number:
        return ""
    return f"{number}-{series}ПАТ" if series else f"{number}ПАТ"


def _blanks(front: Path, page2: Path, page3: Path) -> tuple[Path, Path, Path]:
    sheets = (Path(front), Path(page2), Path(page3))
    for sheet in sheets:
        if not sheet.exists():
            raise FileNotFoundError(sheet)
    return sheets


def render(data: TrudPpuData, *, front: Path, page2: Path, page3: Path) -> bytes:
    """The filled package as a three-page PDF."""
    front_blank, page2_blank, page3_blank = _blanks(front, page2, page3)
    out = fitz.open()
    for blank in (front_blank, page2_blank, page3_blank):
        with fitz.open(str(blank)) as source:
            out.insert_pdf(source, from_page=0, to_page=0)

    _fill_front(out[0], PpuData(
        surname=data.surname, name=data.name, patronymic=data.patronymic,
        birth_date=data.birth_date, gender=data.gender,
        citizenship=data.citizenship, document=data.document, photo=data.photo))
    _fill_page2(out[1], data)
    _fill_page3(out[2], data)
    log.info("ТРУД ППУ: %s %s — патент %s, шартнома %s, %s",
             data.surname, data.name,
             patent_serial(data.patent_series, data.patent_number),
             _dmy(data.contract_date), data.firm)
    return out.tobytes()


def _fill_page2(page, data: TrudPpuData) -> None:
    fonts = _fonts(page)
    issued = data.patent_issue
    runs_to = data.patent_to or plus_one_year(issued)
    values = {
        "patent_serial": patent_serial(data.patent_series, data.patent_number),
        "issue_date": _dmy(issued),
        # the site breaks the term over two lines and leaves the dash hanging
        # on the first of them
        "term_from": f"{_dmy(issued)}-" if issued else "",
        "term_to": _dmy(runs_to),
        "case_number": case_number(data.patent_series, data.patent_number),
        "case_date": _dmy(issued),
        "contract_date": _dmy(data.contract_date),
        "firm": (data.firm or "").strip(),
    }
    for key, text in values.items():
        _write(page, PAGE2[key], text, fonts)


def _fill_page3(page, data: TrudPpuData) -> None:
    fonts = _fonts(page)
    number = "".join((data.uved_number or "").split())
    fio = (data.uved_fio or "").strip() or full_name(
        data.surname, data.name, data.patronymic)
    _write(page, PAGE3["uved_number"], f"№ {number}" if number else "", fonts)
    _write(page, PAGE3["fio"], fio, fonts)
