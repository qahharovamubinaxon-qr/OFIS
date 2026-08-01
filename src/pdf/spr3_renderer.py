"""Print the 3-СПРАВКА packet onto the firm's six-page blank."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import fitz

from src.common.errors import OfisError
from src.pdf.engine import _font_file, _fontname
from src.pdf.spr3_spec import (
    FONT,
    MONTHS_RU,
    PAGE_COUNT,
    SLOTS,
    TEXT_OPACITY,
    Slot,
)

#: Cyrillic → Latin, the way a Kyrgyz/Uzbek passport writes its own MRZ names.
_LATIN = {
    "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Е": "E", "Ё": "E",
    "Ж": "ZH", "З": "Z", "И": "I", "Й": "Y", "К": "K", "Л": "L", "М": "M",
    "Н": "N", "О": "O", "П": "P", "Р": "R", "С": "S", "Т": "T", "У": "U",
    "Ф": "F", "Х": "KH", "Ц": "TS", "Ч": "CH", "Ш": "SH", "Щ": "SHCH",
    "Ъ": "", "Ы": "Y", "Ь": "", "Э": "E", "Ю": "YU", "Я": "YA",
    "Ў": "U", "Қ": "Q", "Ғ": "G", "Ҳ": "H",
}


def to_latin(text: str) -> str:
    return "".join(_LATIN.get(c, c) for c in (text or "").upper())


@dataclass
class Spr3Data:
    """One worker's certificate packet — texts as they get printed."""

    surname: str = ""
    name: str = ""
    patronymic: str = ""
    citizenship: str = ""
    birth_date: date | None = None
    gender: str = ""                   # "male" | "female"
    pass_series: str = ""
    pass_number: str = ""
    pass_issued: date | None = None
    pass_issued_by: str = ""
    valid_from: date | None = None
    #: the blanks' own serial numbers, typed by the operator
    num3: str = ""                     # «450215 6510668»
    ser3: str = ""                     # «235035»
    num5: str = ""                     # «45Г 8889529»
    #: the address, in page 5's own pieces
    oblast: str = ""
    gorod: str = ""
    ulitsa: str = ""
    dom: str = ""
    korpus: str = ""
    kvartira: str = ""
    layout: dict = field(default_factory=dict)

    def fio(self) -> str:
        parts = [p.strip() for p in (self.surname, self.name, self.patronymic)
                 if (p or "").strip()]
        return " ".join(parts).upper()


def year_minus_day(start: date | None) -> date | None:
    """10.07.2026 → 09.07.2027 — the certificate runs a year less a day."""
    if start is None:
        return None
    try:
        anniversary = start.replace(year=start.year + 1)
    except ValueError:                       # 29 February
        anniversary = start.replace(year=start.year + 1, day=28)
    return anniversary - timedelta(days=1)


def _dots(value: date | None) -> str:
    return f"{value:%d.%m.%Y}" if value else ""


def _worded(value: date | None) -> str:
    """«16» июня 2026 г — the quoted manner page 1 uses."""
    if value is None:
        return ""
    return f"«{value.day:02d}» {MONTHS_RU[value.month - 1]} {value.year} г"


def _passport_joined(data: Spr3Data) -> str:
    series = "".join((data.pass_series or "").split())
    number = "".join((data.pass_number or "").split())
    return f"{series}{number}".strip()


def _split_two(text: str) -> tuple[str, str]:
    """«450215 6510668» → the two numbers, for the guide's two spots."""
    parts = (text or "").split(None, 1)
    if not parts:
        return "", ""
    return parts[0], (parts[1].strip() if len(parts) > 1 else "")


def values(data: Spr3Data) -> dict[str, str]:
    """Every slot's finished text, exactly the way the owner's guide has it."""
    start = data.valid_from
    until = year_minus_day(start)
    day = f"{start.day:02d}" if start else ""
    month = MONTHS_RU[start.month - 1] if start else ""
    yy = str(start.year)[2:] if start else ""
    gender_ru = "женский" if data.gender == "female" else "мужской"
    num3_1, num3_2 = _split_two(data.num3)
    num5_1, num5_2 = _split_two(data.num5)
    passport = _passport_joined(data)
    out: dict[str, str] = {
        "p1_fio": data.fio(),
        "p1_birth": _worded(data.birth_date),
        "p1_gender": gender_ru,
        "p1_passport": (
            f"серия и номер: {passport}, выдан {_dots(data.pass_issued)} г. "
            f"{(data.pass_issued_by or '').strip()}").strip().rstrip("."),
        "p1_date_osvid": _worded(start),
        "p1_date_chim": _worded(start),
        "p1_date_low": _worded(start),
        "p3_num1": num3_1, "p3_num2": num3_2,
        "p3_fio": data.fio(),
        "p3_fio_lat": to_latin(data.fio()),
        "p3_pass_grajd": f"{passport} {(data.citizenship or '').upper()}".strip(),
        "p3_birth": _dots(data.birth_date),
        "p3_date_ser": (f"{_dots(start)} сер. {data.ser3.strip()}"
                        if (data.ser3 or "").strip() else _dots(start)),
        "p3_from_day": day, "p3_from_month": (f"{start.month:02d}" if start else ""),
        "p3_from_year": (str(start.year) if start else ""),
        "p3_to_day": (f"{until.day:02d}" if until else ""),
        "p3_to_month": (f"{until.month:02d}" if until else ""),
        "p3_to_year": (str(until.year) if until else ""),
        "p5_num1": num5_1, "p5_num2": num5_2,
        "p5_date_day": day, "p5_date_month": month, "p5_date_yy": yy,
        "p5_fio": data.fio(),
        "p5_birth_day": (f"{data.birth_date.day:02d}" if data.birth_date else ""),
        "p5_birth_month": (f"{data.birth_date.month:02d}"
                           if data.birth_date else ""),
        "p5_birth_year": (str(data.birth_date.year) if data.birth_date else ""),
        "p5_citizenship": (data.citizenship or "").upper(),
        "p5_gender": gender_ru,
        "p5_passport": (f"{passport} выдан {_dots(data.pass_issued)}").strip(),
        "p5_issuer": (data.pass_issued_by or "").strip(),
        "p5_rf": "Российская Федерация",
        "p5_oblast": (data.oblast or "").strip(),
        "p5_gorod": (data.gorod or "").strip(),
        "p5_ulitsa": (data.ulitsa or "").strip(),
        "p5_dom": (data.dom or "").strip(),
        "p5_korpus": (data.korpus or "").strip(),
        "p5_kvartira": (data.kvartira or "").strip(),
        "p5_citizen2": (data.citizenship or "").upper(),
        "p5_citizen3": (data.citizenship or "").upper(),
        "p5_range": (f"с {_dots(start)} до {_dots(until)}" if start else ""),
    }
    # page 6: the same start date scattered over its seven spots
    for spot in ("d1", "d2", "d3", "d4", "d5", "d6", "low"):
        out[f"p6_{spot}_day"] = day
        out[f"p6_{spot}_month"] = month
        out[f"p6_{spot}_yy"] = yy
    return out


def placed(layout: dict | None = None) -> dict[str, Slot]:
    """The measured slots, with anything the office dragged put on top."""
    out = dict(SLOTS)
    for key, moved in ((layout or {}).get("fields") or {}).items():
        if key in out and len(moved) == 3:
            slot = out[key]
            x, baseline, size = (float(v) for v in moved)
            out[key] = Slot(slot.page, x, baseline, size)
    return out


def render(data: Spr3Data, template: Path | str) -> bytes:
    """The finished six-page certificate as PDF bytes."""
    blank = Path(template)
    if not blank.exists():
        raise OfisError("3-СПРАВКА бланкаси топилмади — бўлимда юкланг.")

    with fitz.open(str(blank)) as raw:
        source = raw if raw.is_pdf else fitz.open("pdf", raw.convert_to_pdf())
        doc = fitz.open("pdf", source.tobytes())
    with doc:
        if doc.page_count < PAGE_COUNT:
            raise OfisError(
                f"Бланкада {doc.page_count} та саҳифа бор — 3-СПРАВКА "
                f"{PAGE_COUNT} саҳифали бўлиши керак.")
        fontfile = str(_font_file(FONT))
        fontname = _fontname(FONT)
        slots = placed(data.layout)
        for key, text in values(data).items():
            slot = slots.get(key)
            if slot is None or not text:
                continue
            page = doc[slot.page - 1]
            page.insert_text(
                (slot.x * page.rect.width, slot.baseline * page.rect.height),
                text, fontsize=slot.size * page.rect.height,
                fontfile=fontfile, fontname=fontname,
                color=(0, 0, 0), fill_opacity=TEXT_OPACITY)
        return doc.tobytes()


def output_name(data: Spr3Data) -> str:
    parts = [p.strip().upper() for p in (data.surname, data.name)
             if (p or "").strip()]
    stem = "_".join(parts) or "SPRAVKA3"
    keep = "".join(c for c in stem if c.isalnum() or c in "_-")
    return f"{keep or 'SPRAVKA3'}.pdf"
