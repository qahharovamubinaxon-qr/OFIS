"""Fill the ten-page МВД ТРУДАВОЙ packet onto the firm's blank.

The blank already carries everything that belongs to the firm; this writes the
worker. Two writing styles: plain text at its spot, and letter-cells — one
character per printed box, spaces skipping a box the way a typist skips one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import fitz

from src.common.errors import OfisError
from src.pdf.engine import _font_file, _fontname
from src.pdf.mvd_trud_spec import (
    FONT,
    MONTHS_RU,
    P5_LINE_BUDGET,
    PAGE_COUNT,
    SLOTS,
    TEXT_OPACITY,
    Slot,
)


@dataclass
class MvdTrudData:
    """One worker's packet — everything already in the form it gets printed."""

    surname: str = ""
    name: str = ""
    patronymic: str = ""
    citizenship: str = ""
    birth_date: date | None = None
    pass_series: str = ""
    pass_number: str = ""
    pass_issued: date | None = None
    pass_issued_by: str = ""
    pat_series: str = ""
    pat_number: str = ""
    pat_issued: date | None = None
    pat_issued_by: str = ""
    profession: str = ""
    #: the one date the operator picks: приём, заключение, подпись
    deal_date: date | None = None
    #: patent validity — issue date + 1 year unless the back said otherwise
    pat_until: date | None = None
    uved_no: str = ""
    spravka_no: str = ""
    #: per-page overrides the office dragged: {"fields": {key: [x, b, size]}}
    layout: dict = field(default_factory=dict)

    def fio(self) -> str:
        parts = [p.strip() for p in (self.surname, self.name, self.patronymic)
                 if (p or "").strip()]
        return " ".join(parts).upper()

    def initials(self) -> str:
        """«ОЙМАХМАДОВ А.Х.» — the signature line under the договор."""
        who = (self.surname or "").strip().upper()
        letters = "".join(f"{p.strip()[0]}." for p in (self.name, self.patronymic)
                          if (p or "").strip())
        return f"{who} {letters}".strip()


def _dmy(value: date | None) -> tuple[str, str, str]:
    if value is None:
        return "", "", ""
    return f"{value.day:02d}", f"{value.month:02d}", str(value.year)


def _dots(value: date | None) -> str:
    return f"{value:%d.%m.%Y}" if value else ""


def _worded(value: date | None) -> tuple[str, str, str]:
    """«28» ИЮЛЯ 2026 — the day-quotes date the справки use."""
    if value is None:
        return "", "", ""
    return f"{value.day:02d}", MONTHS_RU[value.month - 1], str(value.year)


def plus_one_year(value: date | None) -> date | None:
    if value is None:
        return None
    try:
        return value.replace(year=value.year + 1)
    except ValueError:                       # 29 February
        return value.replace(year=value.year + 1, day=28)


def split_rep_fio(citizenship: str, fio: str,
                  budget: int = P5_LINE_BUDGET) -> tuple[str, str]:
    """The договор's «республики … ФИО» over its two-line designed gap.

    What fits after «республики» stays on the line; the rest opens the next
    line — broken at a word, never inside one.
    """
    whole = " ".join(f"{citizenship} {fio}".split()).upper()
    if len(whole) <= budget:
        return whole, ""
    head = whole[:budget + 1]
    cut = head.rfind(" ")
    if cut <= 0:
        return whole[:budget], whole[budget:]
    return whole[:cut], whole[cut + 1:]


def values(data: MvdTrudData) -> dict[str, str]:
    """Every slot's finished text. An empty value is simply not printed."""
    deal_d, deal_m, deal_y = _worded(data.deal_date)
    birth = _dmy(data.birth_date)
    issue = _dmy(data.pass_issued)
    pat = _dmy(data.pat_issued)
    valid = _dmy(data.pat_issued)
    until = _dmy(data.pat_until)
    deal = _dmy(data.deal_date)
    line1, line2 = split_rep_fio(data.citizenship, data.fio())
    fio = data.fio()
    return {
        "p1_accept_date": _dots(data.deal_date),
        "p1_uved_no": (data.uved_no or "").strip(),
        "p1_uved_date": _dots(data.deal_date) if (data.uved_no or "").strip() else "",
        "p1_republic": (data.citizenship or "").strip().upper(),
        "p1_fio": fio,
        "p1_passport": _pass_line(data),
        "p1_birth": f"{_dots(data.birth_date)} г." if data.birth_date else "",
        "p2_spravka_no": (data.spravka_no or "").strip(),
        "p2_fio": fio,
        "p3_surname": (data.surname or "").upper(),
        "p3_name": (data.name or "").upper(),
        "p3_patronymic": (data.patronymic or "").upper(),
        "p3_citizenship": (data.citizenship or "").upper(),
        "p3_birth_day": birth[0], "p3_birth_month": birth[1],
        "p3_birth_year": birth[2],
        "p3_pass_series": (data.pass_series or "").upper(),
        "p3_pass_number": (data.pass_number or "").upper(),
        "p3_issue_day": issue[0], "p3_issue_month": issue[1],
        "p3_issue_year": issue[2],
        "p3_issued_by": (data.pass_issued_by or "").upper(),
        "p3_pat_series": (data.pat_series or "").upper(),
        "p3_pat_number": (data.pat_number or "").upper(),
        "p3_pat_day": pat[0], "p3_pat_month": pat[1], "p3_pat_year": pat[2],
        "p3_profession": (data.profession or "").upper(),
        "p4_fio": fio,
        "p4_day": deal_d, "p4_month": deal_m, "p4_year": deal_y,
        "p5_date": (f"{deal_d} {deal_m} {deal_y} г." if data.deal_date else ""),
        "p5_rep_fio_1": line1,
        "p5_rep_fio_2": line2,
        "p5_pat_series": (data.pat_series or "").upper(),
        "p5_pat_number": (data.pat_number or "").upper(),
        "p5_pat_date": _dots(data.pat_issued),
        "p5_from": _dots(data.deal_date),
        "p5_to": _dots(data.pat_until),
        "p6_fio": fio,
        "p6_birth": f"{_dots(data.birth_date)} г." if data.birth_date else "",
        "p6_pass_no": _pass_line(data),
        "p6_pass_issued": _dots(data.pass_issued),
        "p6_organ": (data.pass_issued_by or "").upper(),
        "p6_initials": data.initials(),
        "p8_surname": (data.surname or "").upper(),
        "p8_name": (data.name or "").upper(),
        "p8_patronymic": (data.patronymic or "").upper(),
        "p8_citizenship": (data.citizenship or "").upper(),
        "p8_birth_place": (data.citizenship or "").upper(),
        "p8_birth_day": birth[0], "p8_birth_month": birth[1],
        "p8_birth_year": birth[2],
        "p8_pass_series": (data.pass_series or "").upper(),
        "p8_pass_number": (data.pass_number or "").upper(),
        "p8_issue_day": issue[0], "p8_issue_month": issue[1],
        "p8_issue_year": issue[2],
        "p8_issued_by": (data.pass_issued_by or "").upper(),
        "p9_pat_series": (data.pat_series or "").upper(),
        "p9_pat_number": (data.pat_number or "").upper(),
        "p9_pat_day": pat[0], "p9_pat_month": pat[1], "p9_pat_year": pat[2],
        "p9_pat_issuer": (data.pat_issued_by or "").upper(),
        "p9_valid_day": valid[0], "p9_valid_month": valid[1],
        "p9_valid_year": valid[2],
        "p9_until_day": until[0], "p9_until_month": until[1],
        "p9_until_year": until[2],
        "p9_deal_day": deal[0], "p9_deal_month": deal[1],
        "p9_deal_year": deal[2],
        # the form pre-prints the century — «20 __ г.» takes two digits
        "p10_day": deal_d, "p10_month": deal_m, "p10_year": deal_y[2:],
    }


def _pass_line(data: MvdTrudData) -> str:
    """«FA402090755» or bare «402090755» — series only when there is one."""
    series = "".join((data.pass_series or "").split())
    number = "".join((data.pass_number or "").split())
    return f"{series}{number}".strip()


def placed(layout: dict | None = None) -> dict[str, Slot]:
    """The measured slots, with anything the office dragged put on top.

    EVERYTHING but the three dragged numbers is carried over from the measured
    slot. Rebuilding without the wrap geometry once dropped it to defaults —
    and merely SAVING the layout dialog rebuilds every slot, so after one save
    «Кем выдан»'s continuation forgot the margin row and printed «БЛАСТИ»
    under the boxes instead of in them.
    """
    out = dict(SLOTS)
    for key, moved in ((layout or {}).get("fields") or {}).items():
        if key not in out or len(moved) != 3:
            continue
        slot = out[key]
        x, baseline, size = (float(v) for v in moved)
        # the pitch scales with the size, so grown cells stay cells
        scale = size / slot.size if slot.size else 1.0
        out[key] = Slot(slot.page, x, baseline, size,
                        pitch=slot.pitch * scale,
                        per_row=slot.per_row, rows=slot.rows,
                        wrap_x=slot.wrap_x,
                        wrap_per_row=slot.wrap_per_row,
                        wrap_pitch=(slot.wrap_pitch * scale
                                    if slot.wrap_pitch > 0 else slot.wrap_pitch),
                        row_step=slot.row_step)
    return out


def _write_cells(page: fitz.Page, slot: Slot, text: str, *,
                 width: float, height: float, fontfile: str,
                 fontname: str) -> None:
    """One character per box; a space skips its box.

    Overflow wraps while the form has a continuation row — and on this form
    those rows very often start back at the page margin, full width, so a
    wrapped row takes the slot's own continuation x and cell count. What no
    row can hold is dropped: the grid is fixed, and a glyph past the last box
    would land on the next label.
    """
    per_row = slot.per_row or len(text)
    x, baseline, pitch = slot.x, slot.baseline, slot.pitch
    for _row in range(max(1, slot.rows)):
        chunk, text = text[:per_row], text[per_row:].lstrip()
        if not chunk:
            break
        for i, char in enumerate(chunk):
            if char == " ":
                continue
            page.insert_text((x * width + i * pitch * width,
                              baseline * height),
                             char, fontsize=slot.size * height,
                             fontfile=fontfile, fontname=fontname,
                             color=(0, 0, 0), fill_opacity=TEXT_OPACITY)
        baseline += slot.row_step
        if slot.wrap_x >= 0:
            x = slot.wrap_x
            per_row = slot.wrap_per_row or per_row
            if slot.wrap_pitch > 0:
                pitch = slot.wrap_pitch


def render(data: MvdTrudData, template: Path | str) -> bytes:
    """The finished ten-page packet as PDF bytes."""
    blank = Path(template)
    if not blank.exists():
        raise OfisError("МВД ТРУДАВОЙ бланкаси топилмади — бўлимда юкланг.")

    with fitz.open(str(blank)) as raw:
        source = raw if raw.is_pdf else fitz.open("pdf", raw.convert_to_pdf())
        doc = fitz.open("pdf", source.tobytes())
    with doc:
        if doc.page_count < PAGE_COUNT:
            raise OfisError(
                f"Бланкада {doc.page_count} та саҳифа бор — тўплам "
                f"{PAGE_COUNT} саҳифали бўлиши керак.")
        fontfile = str(_font_file(FONT))
        fontname = _fontname(FONT)
        slots = placed(data.layout)

        for key, text in values(data).items():
            slot = slots.get(key)
            if slot is None or not text:
                continue
            page = doc[slot.page - 1]
            width, height = page.rect.width, page.rect.height
            if slot.pitch > 0:
                _write_cells(page, slot, text, width=width, height=height,
                             fontfile=fontfile, fontname=fontname)
            else:
                page.insert_text((slot.x * width, slot.baseline * height),
                                 text, fontsize=slot.size * height,
                                 fontfile=fontfile, fontname=fontname,
                                 color=(0, 0, 0), fill_opacity=TEXT_OPACITY)
        return doc.tobytes()


def output_name(data: MvdTrudData) -> str:
    """SURNAME_NAME.pdf — the office's filing rule."""
    parts = [p.strip().upper() for p in (data.surname, data.name)
             if (p or "").strip()]
    stem = "_".join(parts) or "MVD_TRUD"
    keep = "".join(c for c in stem if c.isalnum() or c in "_-")
    return f"{keep or 'MVD_TRUD'}.pdf"
