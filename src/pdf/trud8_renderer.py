"""ТРУДАВОЙ/УВЕДОМЛЕНИЕ — print the worker onto the firm's own blank PDF.

The office uploads an EMPTY ТД and УВ, then places every text itself and
says what each one means (:mod:`src.pdf.trud8_fields`). Printing is then
simply: for each placed field, write the worker's matching value at its
spot, in its size, colour and weight.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import fitz

from src.common.errors import OfisError
from src.pdf.engine import _font_file, _fontname
from src.pdf.trud8_fields import Field

TEXT_OPACITY = 1.0

_FACES = {(False, False): "OfisSansRegular", (False, True): "OfisSans",
          (True, False): "OfisSerif", (True, True): "OfisSerifBold"}

MONTHS_RU = ("января", "февраля", "марта", "апреля", "мая", "июня",
             "июля", "августа", "сентября", "октября", "ноября", "декабря")


@dataclass
class Trud8Data:
    surname: str = ""
    name: str = ""
    patronymic: str = ""
    gender: str = ""                  # "male" | "female"
    citizenship: str = ""
    birth_date: date | None = None
    pass_series: str = ""
    pass_number: str = ""
    pass_issued: date | None = None
    pass_issued_by: str = ""
    pat_series: str = ""
    pat_number: str = ""
    pat_blank_series: str = ""
    pat_blank_number: str = ""
    pat_issued: date | None = None
    pat_valid_to: date | None = None
    profession: str = ""
    deal_date: date | None = None
    work_address: str = ""
    layout: dict = field(default_factory=dict)

    def fio(self) -> str:
        parts = [p.strip() for p in (self.surname, self.name, self.patronymic)
                 if (p or "").strip()]
        return _title(" ".join(parts))


def _title(text: str) -> str:
    return " ".join(w.capitalize() for w in (text or "").split())


def _dots(value: date | None) -> str:
    return f"{value:%d.%m.%Y}" if value else ""


def _join(*parts: str) -> str:
    return " ".join(p.strip() for p in parts if (p or "").strip())


def values(data: Trud8Data) -> dict[str, str]:
    """Every catalogue key's finished text for this worker."""
    birth, deal = data.birth_date, data.deal_date
    return {
        "fio": data.fio(),
        "fio_upper": data.fio().upper(),
        "surname": _title(data.surname),
        "name": _title(data.name),
        "patronymic": _title(data.patronymic),
        "gender": "Женский" if data.gender == "female" else "Мужской",
        "citizenship": _title(data.citizenship),
        "birth_place": _title(data.citizenship),
        "birth_date": _dots(birth),
        "birth_day": f"{birth.day:02d}" if birth else "",
        "birth_month": f"{birth.month:02d}" if birth else "",
        "birth_year": str(birth.year) if birth else "",
        "pass_kind": "Иностранный паспорт",
        "pass_series": (data.pass_series or "").upper(),
        "pass_number": (data.pass_number or "").upper(),
        "pass_full": _join((data.pass_series or "").upper(),
                           (data.pass_number or "").upper()),
        "pass_issued": _dots(data.pass_issued),
        "pass_issued_by": (data.pass_issued_by or "").upper(),
        "pat_kind": "Патент ИГ (ЛБГ)",
        "pat_series": (data.pat_series or "").upper(),
        "pat_number": (data.pat_number or "").upper(),
        "pat_full": _join((data.pat_series or "").upper(),
                          (data.pat_number or "").upper()),
        "pat_blank_series": (data.pat_blank_series or "").upper(),
        "pat_blank_number": (data.pat_blank_number or "").upper(),
        "pat_issued": _dots(data.pat_issued),
        "pat_valid_to": _dots(data.pat_valid_to),
        "profession": (data.profession or "").strip().capitalize(),
        "deal_date": _dots(deal),
        "deal_day": f"{deal.day:02d}" if deal else "",
        "deal_month": f"{deal.month:02d}" if deal else "",
        "deal_month_ru": MONTHS_RU[deal.month - 1] if deal else "",
        "deal_year": str(deal.year) if deal else "",
        "deal_year_short": str(deal.year)[2:] if deal else "",
        "work_address": (data.work_address or "").strip(),
    }


def render(data: Trud8Data, template: Path,
           fields: list[Field]) -> bytes:
    """The firm's blank with the worker's own values written onto it."""
    template = Path(template)
    if not template.exists():
        raise OfisError("Фирманинг бланкаси топилмади — бўлимда юкланг.")
    texts = values(data)
    with fitz.open(str(template)) as raw:
        source = raw if raw.is_pdf else fitz.open("pdf", raw.convert_to_pdf())
        doc = fitz.open("pdf", source.tobytes())
    with doc:
        for item in fields:
            text = texts.get(item.key) or ""
            if not text or item.page > doc.page_count:
                continue
            page = doc[item.page - 1]
            pw, ph = page.rect.width, page.rect.height
            family = _FACES[(bool(item.serif), bool(item.bold))]
            page.insert_text((item.x * pw, item.baseline * ph), text,
                             fontsize=item.size * ph,
                             fontfile=str(_font_file(family)),
                             fontname=_fontname(family),
                             color=item.colour, fill_opacity=TEXT_OPACITY)
        return doc.tobytes()


def output_stem(data: Trud8Data) -> str:
    parts = [p.strip().upper() for p in (data.surname, data.name)
             if (p or "").strip()]
    stem = "_".join(parts) or "TRUD"
    return "".join(c for c in stem if c.isalnum() or c in "_-") or "TRUD"
