"""КРКОД РЕГ — print the registration, the подтверждение, and the QR.

The order of work is the section's whole point: the подтверждение card is
filled FIRST and photographed to imgbb; the QR of that direct link goes into
the box on the registration's back, so anyone scanning the printed sheet sees
the dormitory's own confirmation of this worker.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import fitz

from src.common.errors import OfisError
from src.pdf.engine import _font_file, _fontname
from src.pdf.qrreg_spec import (
    FONT,
    PODT_FONT,
    PODT_RIGHT_EDGE,
    PODT_SLOTS,
    QR_FRAME,
    QR_INSET,
    REG_PAGES,
    REG_SLOTS,
    TEXT_OPACITY,
    Slot,
)


@dataclass
class QrRegData:
    """One worker's registration — everything as it gets printed."""

    surname: str = ""
    name: str = ""
    patronymic: str = ""
    citizenship: str = ""
    birth_date: date | None = None
    gender: str = ""                  # "male" | "female"
    pass_series: str = ""
    pass_number: str = ""
    pass_issued: date | None = None
    pass_expiry: date | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    #: the dormitory address, in the form's own pieces
    addr_subject: str = ""            # ГОРОД МОСКВА
    addr_district: str = ""           # ОБРУЧЕВСКИЙ РАЙОН
    addr_punkt: str = ""              # населённый пункт, кўпинча бўш
    addr_street: str = ""             # УЛ НОВАТОРОВ
    dom: str = ""
    korpus: str = ""
    kvartira: str = ""
    #: the dormitory's own «Уведомление зарегистрировано №»
    code: str = ""
    #: the host person — принимающая сторона on the back
    host_surname: str = ""
    host_name: str = ""
    host_patronymic: str = ""
    layout: dict = field(default_factory=dict)

    def fio(self) -> str:
        parts = [p.strip() for p in (self.surname, self.name, self.patronymic)
                 if (p or "").strip()]
        return " ".join(parts).upper()

    def fio_title(self) -> str:
        """«Ибадуллаев Анвар Ойбек Угли» — the card writes names this way."""
        return " ".join(w.capitalize() for w in self.fio().split())

    def host_fio(self) -> str:
        parts = [p.strip() for p in (self.host_surname, self.host_name,
                                     self.host_patronymic) if (p or "").strip()]
        return " ".join(w.capitalize() for w in " ".join(parts).split())

    def full_address(self) -> str:
        """One line for the card: «г. Москва, ул. Новаторов, д. 34, к. 3…»."""
        head = [p for p in (self.addr_subject, self.addr_district,
                            self.addr_punkt, self.addr_street)
                if (p or "").strip()]
        tail = []
        if (self.dom or "").strip():
            tail.append(f"д. {self.dom.strip()}")
        if (self.korpus or "").strip():
            tail.append(f"к. {self.korpus.strip()}")
        if (self.kvartira or "").strip():
            tail.append(f"кв. {self.kvartira.strip()}")
        return ", ".join([" ".join(h.split()) for h in head] + tail)


def _dmy(value: date | None) -> tuple[str, str, str]:
    if value is None:
        return "", "", ""
    return f"{value.day:02d}", f"{value.month:02d}", str(value.year)


def _dots(value: date | None) -> str:
    return f"{value:%d.%m.%Y}" if value else ""


def reg_values(data: QrRegData) -> dict[str, str]:
    """The registration's texts — front cells and the back."""
    birth = _dmy(data.birth_date)
    issue = _dmy(data.pass_issued)
    expiry = _dmy(data.pass_expiry)
    stay = _dmy(data.valid_to)
    number = "".join((data.pass_series or "").split()) + \
        "".join((data.pass_number or "").split())
    return {
        "f_surname": (data.surname or "").upper(),
        "f_name": (data.name or "").upper(),
        "f_patronymic": (data.patronymic or "").upper(),
        "f_citizenship": (data.citizenship or "").upper(),
        "f_birth_day": birth[0], "f_birth_month": birth[1],
        "f_birth_year": birth[2],
        # the form marks the sex with a «+» in its box
        "f_sex_male": "+" if data.gender == "male" else "",
        "f_sex_female": "+" if data.gender == "female" else "",
        "f_doc_number": number,
        "f_issue_day": issue[0], "f_issue_month": issue[1],
        "f_issue_year": issue[2],
        "f_until_day": expiry[0], "f_until_month": expiry[1],
        "f_until_year": expiry[2],
        "f_addr_subject": (data.addr_subject or "").upper(),
        "f_addr_district": (data.addr_district or "").upper(),
        "f_addr_punkt": (data.addr_punkt or "").upper(),
        "f_addr_street": (data.addr_street or "").upper(),
        "f_dom": f"дом {data.dom.strip()}" if (data.dom or "").strip() else "",
        "f_korpus": (f"корпус {data.korpus.strip()}"
                     if (data.korpus or "").strip() else ""),
        "f_kvartira": (f"квартира {data.kvartira.strip()}"
                       if (data.kvartira or "").strip() else ""),
        "f_stay_day": stay[0], "f_stay_month": stay[1],
        "f_stay_year": stay[2],
        "b_host_surname": (data.host_surname or "").upper(),
        "b_host_name": (data.host_name or "").upper(),
        "b_host_patronymic": (data.host_patronymic or "").upper(),
        "b_uchet_day": stay[0], "b_uchet_month": stay[1],
        "b_uchet_year": stay[2],
        "b_gosuslugi_owner": data.host_fio(),
        "b_code": f"№ {data.code.strip()}" if (data.code or "").strip() else "",
    }


def podt_values(data: QrRegData) -> dict[str, str]:
    """The подтверждение card's texts — same worker, the card's own manner."""
    number = "".join((data.pass_series or "").split()) + \
        "".join((data.pass_number or "").split())
    return {
        "c_fio": data.fio_title(),
        "c_birth": _dots(data.birth_date),
        "c_birth_place": (data.citizenship or "").capitalize(),
        "c_sex": "Мужской" if data.gender != "female" else "Женский",
        "c_citizenship": (data.citizenship or "").capitalize(),
        "c_passport": number,
        "c_uchet": _dots(data.valid_from),
        "c_address": data.full_address(),
        "c_from": _dots(data.valid_from),
        "c_to": _dots(data.valid_to),
        "c_code": (data.code or "").strip(),
    }


def make_qr(link: str) -> bytes:
    """The QR of the direct link, as PNG bytes."""
    import qrcode

    maker = qrcode.QRCode(border=1, box_size=8)
    maker.add_data(link)
    maker.make(fit=True)
    image = maker.make_image(fill_color="black", back_color="white")
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def _placed(base: dict[str, Slot], layout: dict | None) -> dict[str, Slot]:
    out = dict(base)
    for key, moved in ((layout or {}).get("fields") or {}).items():
        if key not in out or len(moved) != 3:
            continue
        slot = out[key]
        x, baseline, size = (float(v) for v in moved)
        scale = size / slot.size if slot.size else 1.0
        out[key] = Slot(slot.page, x, baseline, size,
                        pitch=slot.pitch * scale, per_row=slot.per_row,
                        colour=slot.colour, font=slot.font)
    return out


def _open_blank(template: Path | str, wanted: int, what: str) -> fitz.Document:
    blank = Path(template)
    if not blank.exists():
        raise OfisError(f"{what} бланкаси топилмади — бўлимда юкланг.")
    with fitz.open(str(blank)) as raw:
        source = raw if raw.is_pdf else fitz.open("pdf", raw.convert_to_pdf())
        doc = fitz.open("pdf", source.tobytes())
    if doc.page_count < wanted:
        doc.close()
        raise OfisError(f"{what}: бланкада {wanted} та саҳифа бўлиши керак.")
    return doc


def _write(doc: fitz.Document, slots: dict[str, Slot],
           texts: dict[str, str], *, font: str = FONT,
           shrink_edge: float = 0.0) -> None:
    for key, text in texts.items():
        slot = slots.get(key)
        if slot is None or not text:
            continue
        family = slot.font or font
        fontfile = str(_font_file(family))
        fontname = _fontname(family)
        page = doc[slot.page - 1]
        width, height = page.rect.width, page.rect.height
        size = slot.size * height
        if slot.pitch > 0:
            # slot.x is the CENTRE of the first box — every character is
            # centred in its own box, never leaned on the left border
            try:
                measure = fitz.Font(fontfile=fontfile)
            except Exception:                     # noqa: BLE001
                measure = None
            per_row = slot.per_row or len(text)
            for i, char in enumerate(text[:per_row]):
                if char == " ":
                    continue
                half = (measure.text_length(char, size) / 2
                        if measure else size * 0.25)
                page.insert_text(((slot.x + i * slot.pitch) * width - half,
                                  slot.baseline * height), char,
                                 fontsize=size, fontfile=fontfile,
                                 fontname=fontname, color=slot.colour,
                                 fill_opacity=TEXT_OPACITY)
            continue
        squeeze = 1.0
        if shrink_edge:
            room = (shrink_edge - slot.x) * width
            try:
                text_width = fitz.Font(fontfile=fontfile).text_length(text, size)
            except Exception:                     # noqa: BLE001
                text_width = len(text) * size * 0.5
            if text_width > room > 0:
                size *= max(0.66, room / text_width)
                try:
                    text_width = fitz.Font(fontfile=fontfile).text_length(text, size)
                except Exception:                 # noqa: BLE001
                    text_width = len(text) * size * 0.5
                if text_width > room:
                    squeeze = room / text_width
        point = fitz.Point(slot.x * width, slot.baseline * height)
        morph = ((point, fitz.Matrix(squeeze, 0, 0, 1, 0, 0))
                 if squeeze < 1.0 else None)
        page.insert_text(point, text, fontsize=size, fontfile=fontfile,
                         fontname=fontname, color=slot.colour,
                         fill_opacity=TEXT_OPACITY, morph=morph)


def render_podt(data: QrRegData, template: Path | str) -> tuple[bytes, bytes]:
    """The filled подтверждение — as PDF bytes AND as a PNG photograph.

    The PNG is what goes to imgbb: whoever scans the QR opens exactly this
    picture on the phone, so it is rendered sharp (2× the card's size).
    """
    doc = _open_blank(template, 1, "Подтверждение")
    with doc:
        slots = _placed(PODT_SLOTS, data.layout)
        _write(doc, slots, podt_values(data), font=PODT_FONT,
               shrink_edge=PODT_RIGHT_EDGE)
        pdf = doc.tobytes()
        png = doc[0].get_pixmap(matrix=fitz.Matrix(3, 3)).tobytes("png")
    return pdf, png


def render_registration(data: QrRegData, template: Path | str,
                        qr_png: bytes | None) -> bytes:
    """The two-page registration, the QR seated in its printed box."""
    doc = _open_blank(template, REG_PAGES, "КРКОД РЕГ")
    with doc:
        slots = _placed(REG_SLOTS, data.layout)
        _write(doc, slots, reg_values(data))
        if qr_png:
            back = doc[1]
            x0, y0, x1, y1 = QR_FRAME
            frame_w = (x1 - x0) * back.rect.width
            frame_h = (y1 - y0) * back.rect.height
            side = min(frame_w, frame_h) * (1 - 2 * QR_INSET)
            cx = (x0 + x1) / 2 * back.rect.width
            cy = (y0 + y1) / 2 * back.rect.height
            rect = fitz.Rect(cx - side / 2, cy - side / 2,
                             cx + side / 2, cy + side / 2)
            back.insert_image(rect, stream=qr_png)
        return doc.tobytes()


def output_name(data: QrRegData) -> str:
    parts = [p.strip().upper() for p in (data.surname, data.name)
             if (p or "").strip()]
    stem = "_".join(parts) or "QRREG"
    keep = "".join(c for c in stem if c.isalnum() or c in "_-")
    return f"{keep or 'QRREG'}.pdf"
