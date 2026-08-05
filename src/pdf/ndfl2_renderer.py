"""2 НДФЛ — the worker, his months and the four sums, onto the firm's sheet.

The office types the months; everything at the foot of the form is
ARITHMETIC and the program does it: the total of the months is the income,
the income is the tax base (this справка carries no deductions), and the
tax is 13% of that, both «исчисленная» and «удержанная».
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import fitz

from src.common.errors import OfisError
from src.pdf.engine import _font_file, _fontname
from src.pdf.ndfl2_spec import (
    ALL_SLOTS,
    DATE_CLEAR,
    FONT,
    INCOME_CODE,
    INK,
    LEFT_CODE,
    LEFT_MONEY,
    LEFT_MONTH,
    MONTH_SIZE,
    RIGHT_CODE,
    RIGHT_MONEY,
    RIGHT_MONTH,
    ROW_FIRST,
    ROW_PITCH,
    ROWS_PER_TABLE,
    TAX_RATE,
    Slot,
)

#: «1 165 000.00» — a thin no-break space groups the thousands, the way
#: the office's own справка prints them.
_GROUP = " "


def money(value: Decimal | float | int, comma: bool = True) -> str:
    """«1165000» → «1 165 000,00». The office's sheet uses both marks: a
    comma in the tax rows, a dot in the income rows — so callers say."""
    amount = Decimal(str(value)).quantize(Decimal("0.01"), ROUND_HALF_UP)
    whole, cents = f"{amount:.2f}".split(".")
    negative = whole.startswith("-")
    whole = whole.lstrip("-")
    grouped = ""
    while len(whole) > 3:
        grouped = _GROUP + whole[-3:] + grouped
        whole = whole[:-3]
    grouped = whole + grouped
    return f"{'-' if negative else ''}{grouped}{',' if comma else '.'}{cents}"


@dataclass
class Ndfl2Data:
    """One справка: whose, for what year, and what he was paid."""

    surname: str = ""
    name: str = ""
    patronymic: str = ""
    inn: str = ""
    birth_date: date | None = None
    doc_code: str = "10"                 # паспорт иностранного гражданина
    doc_number: str = ""
    #: month number → what he was paid that month
    months: dict[int, Decimal] = field(default_factory=dict)
    year: int = 0
    form_date: date | None = None
    layout: dict = field(default_factory=dict)

    # ---- the arithmetic the office asked the program to do -------------
    def total(self) -> Decimal:
        return sum((Decimal(str(v)) for v in self.months.values()),
                   Decimal("0"))

    def tax_base(self) -> Decimal:
        return self.total()

    def tax(self) -> Decimal:
        return (self.tax_base() * Decimal(str(TAX_RATE))).quantize(
            Decimal("0.01"), ROUND_HALF_UP)


def values(data: Ndfl2Data) -> dict[str, str]:
    """Every named slot's finished text."""
    born = data.birth_date
    made = data.form_date or date.today()
    return {
        "year": str(data.year or made.year),
        "day": f"{made.day:02d}", "month": f"{made.month:02d}",
        "date_year": str(made.year),
        "inn": (data.inn or "").strip(),
        "surname": _title(data.surname), "name": _title(data.name),
        "patronymic": _title(data.patronymic),
        "birth_d": f"{born.day:02d}" if born else "",
        "birth_m": f"{born.month:02d}" if born else "",
        "birth_y": str(born.year) if born else "",
        "doc_code": (data.doc_code or "").strip(),
        "doc_number": (data.doc_number or "").strip(),
        "total_income": money(data.total(), comma=False),
        "tax_base": money(data.tax_base(), comma=False),
        "tax_calculated": money(data.tax()),
        "tax_withheld": money(data.tax()),
    }


def _title(text: str) -> str:
    return " ".join(w.capitalize() for w in (text or "").split())


def placed(layout: dict) -> dict[str, Slot]:
    """The slots, wearing whatever the office dragged and restyled."""
    moved = (layout or {}).get("fields") or {}
    styles = (layout or {}).get("styles") or {}
    out: dict[str, Slot] = {}
    for key, slot in ALL_SLOTS.items():
        x, baseline, size = slot.x, slot.baseline, slot.size
        spot = moved.get(key)
        if spot and len(spot) == 3:
            x, baseline, size = (float(v) for v in spot)
            if slot.align == "right":
                # the editor hands back the LEFT edge; the slot keeps its
                # right edge, so it is put back the way it was measured
                x = x + measured_width(slot, size)
        out[key] = Slot(x, baseline, size, slot.align, slot.sample,
                        slot.label)
    for key, chosen in styles.items():
        if key in out and chosen.get("size"):
            slot = out[key]
            out[key] = Slot(slot.x, slot.baseline, float(chosen["size"]),
                            slot.align, slot.sample, slot.label)
    return out


def measured_width(slot: Slot, size: float) -> float:
    """How wide the sample is, as a share of an A4's width — the editor
    shows a right-aligned value from its left edge, so it has to know."""
    font = fitz.Font(fontfile=str(_font_file(FONT)))
    return font.text_length(slot.sample, fontsize=size * 822.05) / 595.28


def month_rows(months: dict[int, Decimal]) -> list[tuple[int, float, int]]:
    """(month, baseline, column) for every month the office typed, in order.

    The first eight go down the LEFT table, the rest down the right one —
    the way the form itself is laid out.
    """
    rows = []
    for index, month in enumerate(sorted(months)):
        column = index // ROWS_PER_TABLE
        baseline = ROW_FIRST + (index % ROWS_PER_TABLE) * ROW_PITCH
        rows.append((month, baseline, column))
    return rows


def render(data: Ndfl2Data, template: Path) -> bytes:
    """The firm's own sheet with this worker's справка written onto it."""
    template = Path(template)
    if not template.exists():
        raise OfisError("Фирманинг бланкаси топилмади — бўлимда юкланг.")
    text = values(data)
    slots = placed(data.layout)
    with fitz.open(str(template)) as raw:
        source = raw if raw.is_pdf else fitz.open("pdf", raw.convert_to_pdf())
        doc = fitz.open("pdf", source.tobytes())
    with doc:
        page = doc[0]
        width, height = page.rect.width, page.rect.height
        font = fitz.Font(fontfile=str(_font_file(FONT)))
        # the sheet's own printed date is replaced by the operator's
        for x0, y0, x1, y1 in DATE_CLEAR:
            page.draw_rect(fitz.Rect(x0 * width, y0 * height,
                                     x1 * width, y1 * height),
                           color=None, fill=(1, 1, 1))
        styles = (data.layout or {}).get("styles") or {}
        for key, slot in slots.items():
            chosen = styles.get(key) or {}
            _write(page, font, slot, text.get(key, ""),
                   colour=tuple(chosen.get("colour") or INK)[:3],
                   family=str(chosen.get("font") or FONT))
        for month, baseline, column in month_rows(data.months):
            amount = money(data.months[month]) + " ₽"
            if column == 0:
                m_x, c_x, box = LEFT_MONTH, LEFT_CODE, LEFT_MONEY
            else:
                m_x, c_x, box = RIGHT_MONTH, RIGHT_CODE, RIGHT_MONEY
            _write(page, font, Slot(m_x, baseline, MONTH_SIZE, "centre"),
                   str(month))
            _write(page, font, Slot(c_x, baseline, MONTH_SIZE, "centre"),
                   INCOME_CODE)
            _write(page, font,
                   Slot((box[0] + box[1]) / 2, baseline, MONTH_SIZE, "centre"),
                   amount)
        for extra in (data.layout or {}).get("extra") or []:
            _write(page, font, Slot(float(extra.get("x", 0.1)),
                                    float(extra.get("baseline", 0.1)),
                                    float(extra.get("size", 0.0116)), "left"),
                   str(extra.get("text") or ""),
                   colour=tuple(extra.get("colour") or INK)[:3],
                   family=str(extra.get("font") or FONT))
        return doc.tobytes()


def _write(page, font, slot: Slot, text: str, *, colour=INK,
           family: str = FONT) -> None:
    if not text:
        return
    width, height = page.rect.width, page.rect.height
    size = slot.size * height
    if family != FONT:
        font = fitz.Font(fontfile=str(_font_file(family)))
    span = font.text_length(text, fontsize=size)
    x = slot.x * width
    if slot.align == "right":
        x -= span
    elif slot.align == "centre":
        x -= span / 2
    page.insert_text((x, slot.baseline * height), text, fontsize=size,
                     fontfile=str(_font_file(family)),
                     fontname=_fontname(family), color=colour)


def output_stem(data: Ndfl2Data) -> str:
    parts = [p.strip().upper() for p in (data.surname, data.name)
             if (p or "").strip()]
    stem = "_".join(parts) or "NDFL2"
    return "".join(c for c in stem if c.isalnum() or c in "_-") or "NDFL2"
