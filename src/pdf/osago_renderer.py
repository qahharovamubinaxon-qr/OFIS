"""Print the ОСАГО policy onto the insurer's own blank."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import fitz

from src.common.errors import OfisError
from src.domain.vehicle import DriverLicence, Sts
from src.pdf.engine import _font_file, _fontname
from src.pdf.osago_spec import (
    BASES,
    FONT_BOLD,
    FONT_REGULAR,
    MARKS,
    MAX_DRIVERS,
    MONTHS_RU,
    STARS_FIO,
    STARS_KBM,
    STARS_VU,
    TEXT_OPACITY,
    Slot,
)


@dataclass
class OsagoData:
    """One policy — everything as it gets printed."""

    sts: Sts
    drivers: list[DriverLicence] = field(default_factory=list)
    unlimited: bool = True
    start: date | None = None
    until: date | None = None
    policy_holder: str = ""          # blank → the СТС owner
    policy_no: str = ""              # blank → the бланк's own pre-print stays
    premium: str = ""
    layout: dict = field(default_factory=dict)

    def holder(self) -> str:
        return (self.policy_holder or "").strip() or self.sts.owner_fio

    def holder_short(self) -> str:
        """«НАЙДЕНОВ А.В.» — the way РЕСО signs the страхователь."""
        parts = [p for p in self.holder().upper().split() if p]
        if not parts:
            return ""
        initials = "".join(f"{p[0]}." for p in parts[1:3])
        return f"{parts[0]} {initials}".strip()


def _dmy(value: date | None) -> str:
    return f"{value:%d.%m.%Y}" if value else ""


def _quoted(value: date | None) -> str:
    """««15» июля 2026 г.» — the manner Ингосстрах dates its lines."""
    if value is None:
        return ""
    return f"«{value.day:02d}» {MONTHS_RU[value.month - 1]} {value.year} г."


def values(data: OsagoData, base: str) -> dict[str, str]:
    """Every slot's finished text for this insurer style."""
    sts = data.sts
    mark = MARKS.get(base, "X")
    start, until = data.start, data.until
    out: dict[str, str] = {
        "strah_fio": data.holder().upper(),
        "owner_fio": (sts.owner_fio or data.holder()).upper(),
        "brand": sts.vehicle.upper(),
        "plate": (sts.plate or "").upper(),
        "doc_series": (sts.series or "").upper(),
        "tick_unlimited": mark if data.unlimited else "",
        "tick_named": "" if data.unlimited else mark,
        "tick_personal": mark,
        "tick_no_trailer": mark,
        "policy_no": (data.policy_no or "").strip(),
        "premium": (data.premium or "").strip(),
        "doc_kind": "Свидетельство о регистрации ТС",
        "strah_short": data.holder_short(),
        "deal_date": f"{_dmy(start)} г." if start else "",
        "issue_date": f"{_dmy(start)} г." if start else "",
        "deal_q": _quoted(start),
        "deal_dots": _dmy(start),
        "issue_q": _quoted(start),
        "srok_from": (f"{_dmy(start)} г." if base == "ingosstrah"
                      else f"00 ч. 00 мин. {_dmy(start)} г.") if start else "",
        "srok_to": (f"{_dmy(until)} г." if base == "ingosstrah"
                    else f"24 ч. 00 мин. {_dmy(until)} г.") if until else "",
        "use_period": (f"с {_dmy(start)} г. по {_dmy(until)} г.,"
                       if start and until else ""),
        "use_from": f"с {_dmy(start)} г." if start else "",
        "use_to": f"по {_dmy(until)} г." if until else "",
    }
    vin = "".join((sts.vin or "").split()).upper()
    if base == "ingosstrah":
        out["vin"] = vin
        out["doc_number"] = (sts.number or "").upper()
    else:
        out["vin"] = vin or "ОТСУТСТВУЕТ"
        # РЕСО prints the СТС as one joined серия+номер
        out["doc_number"] = "".join(sts.document.split()).upper()

    named = [d for d in data.drivers if not d.is_empty()][:MAX_DRIVERS]
    for i in range(1, MAX_DRIVERS + 1):
        if not data.unlimited and i <= len(named):
            driver = named[i - 1]
            out[f"dr{i}_num"] = str(i)
            out[f"dr{i}_fio"] = driver.fio.upper()
            out[f"dr{i}_vu"] = driver.licence.upper()
            out[f"dr{i}_kbm"] = "1"
        elif data.unlimited and base == "ingosstrah":
            # the sample fills every row with stars when anyone may drive
            out[f"dr{i}_num"] = str(i)
            out[f"dr{i}_fio"] = STARS_FIO
            out[f"dr{i}_vu"] = STARS_VU
            out[f"dr{i}_kbm"] = STARS_KBM
        else:
            out[f"dr{i}_num"] = out[f"dr{i}_fio"] = ""
            out[f"dr{i}_vu"] = out[f"dr{i}_kbm"] = ""
    out["dr5_num"] = "-" if data.unlimited and base == "ingosstrah" else ""
    return out


def placed(layout: dict | None, base: dict[str, Slot]) -> dict[str, Slot]:
    """The measured slots, with anything the office dragged put on top."""
    out = dict(base)
    for key, moved in ((layout or {}).get("fields") or {}).items():
        if key in out and len(moved) == 3:
            slot = out[key]
            x, baseline, size = (float(v) for v in moved)
            scale = size / slot.size if slot.size else 1.0
            # dragging a cells slot slides the whole measured grid with it
            shifted = tuple(c + (x - slot.x) for c in slot.cells)
            out[key] = Slot(x, baseline, size, bold=slot.bold,
                            pitch=slot.pitch * scale, per_row=slot.per_row,
                            clear_to=slot.clear_to, cells=shifted)
    return out


def render(data: OsagoData, template: Path | str, base: str) -> bytes:
    """The finished policy as PDF bytes — values go on page 1 only."""
    blank = Path(template)
    if not blank.exists():
        raise OfisError("СТРАХОВКА бланкаси топилмади — бўлимда юкланг.")
    if base not in BASES:
        base = "ingosstrah"

    with fitz.open(str(blank)) as raw:
        source = raw if raw.is_pdf else fitz.open("pdf", raw.convert_to_pdf())
        doc = fitz.open("pdf", source.tobytes())
    with doc:
        page = doc[0]
        width, height = page.rect.width, page.rect.height
        slots = placed(data.layout, BASES[base])
        fonts = {True: (str(_font_file(FONT_BOLD)), _fontname(FONT_BOLD)),
                 False: (str(_font_file(FONT_REGULAR)),
                         _fontname(FONT_REGULAR))}
        for key, text in values(data, base).items():
            slot = slots.get(key)
            if slot is None or not text:
                continue
            fontfile, fontname = fonts[slot.bold]
            size = slot.size * height
            if slot.clear_to > slot.x:
                page.draw_rect(
                    fitz.Rect((slot.x - 0.004) * width,
                              (slot.baseline - slot.size * 1.15) * height,
                              slot.clear_to * width,
                              (slot.baseline + 0.004) * height),
                    color=None, fill=(1, 1, 1))
            if slot.cells:
                # each character centred on its own measured box
                try:
                    measure = fitz.Font(fontfile=fontfile)
                except Exception:                 # noqa: BLE001
                    measure = None
                shown = text[:len(slot.cells)]
                for char, centre in zip(shown, slot.cells, strict=False):
                    if char == " ":
                        continue
                    half = (measure.text_length(char, size) / 2
                            if measure else size * 0.25)
                    page.insert_text((centre * width - half,
                                      slot.baseline * height), char,
                                     fontsize=size, fontfile=fontfile,
                                     fontname=fontname, color=(0, 0, 0),
                                     fill_opacity=TEXT_OPACITY)
                continue
            if slot.pitch > 0:
                shown = text[:slot.per_row or len(text)]
                for i, char in enumerate(shown):
                    if char == " ":
                        continue
                    page.insert_text(
                        ((slot.x + i * slot.pitch) * width,
                         slot.baseline * height), char, fontsize=size,
                        fontfile=fontfile, fontname=fontname,
                        color=(0, 0, 0), fill_opacity=TEXT_OPACITY)
                continue
            page.insert_text((slot.x * width, slot.baseline * height), text,
                             fontsize=size, fontfile=fontfile,
                             fontname=fontname, color=(0, 0, 0),
                             fill_opacity=TEXT_OPACITY)
        return doc.tobytes()


def output_name(data: OsagoData) -> str:
    stem = "".join(c for c in (data.sts.plate or "").upper()
                   if c.isalnum()) or "OSAGO"
    return f"{stem}.pdf"
