"""Print the КАРТА ИНОСТРАННОГО ГРАЖДАНИНА onto its own two blanks."""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import fitz

from src.common.errors import OfisError
from src.pdf.engine import _font_file, _fontname
from src.pdf.karta_spec import (
    CARD_REGION,
    COVER_YEARS,
    FONT_BOLD,
    FONT_MRZ,
    FONT_REGULAR,
    MRZ_FILL,
    MRZ_LEFT,
    MRZ_LEN,
    MRZ_RIGHT,
    MRZ_SIZE,
    PHOTO_BOX,
    QR_BOX,
    QR_INSET,
    SERIES_HEAD,
    SIGN_BOX,
    SLOTS,
    TEXT_OPACITY,
    Slot,
)

#: Cyrillic → Latin for the machine-readable zone.
_LATIN = {
    "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Е": "E", "Ё": "E",
    "Ж": "ZH", "З": "Z", "И": "I", "Й": "Y", "К": "K", "Л": "L", "М": "M",
    "Н": "N", "О": "O", "П": "P", "Р": "R", "С": "S", "Т": "T", "У": "U",
    "Ф": "F", "Х": "KH", "Ц": "TS", "Ч": "CH", "Ш": "SH", "Щ": "SHCH",
    "Ъ": "", "Ы": "Y", "Ь": "", "Э": "E", "Ю": "YU", "Я": "YA",
    "Ў": "U", "Қ": "Q", "Ғ": "G", "Ҳ": "H",
}
#: ISO-3166 for the citizenships this office actually sees.
_COUNTRY = {"УЗБЕКИСТАН": "UZB", "ТАДЖИКИСТАН": "TJK", "КЫРГЫЗСТАН": "KGZ",
            "КИРГИЗИЯ": "KGZ", "КАЗАХСТАН": "KAZ", "РОССИЯ": "RUS",
            "АЗЕРБАЙДЖАН": "AZE", "АРМЕНИЯ": "ARM", "МОЛДОВА": "MDA",
            "УКРАИНА": "UKR", "БЕЛАРУСЬ": "BLR", "ТУРКМЕНИСТАН": "TKM"}


def to_latin(text: str) -> str:
    return "".join(_LATIN.get(c, c) for c in (text or "").upper())


def plus_years(start: date | None, years: int = COVER_YEARS) -> date | None:
    """10.05.2026 → 10.05.2031 — the card runs five full years."""
    if start is None:
        return None
    try:
        return start.replace(year=start.year + years)
    except ValueError:                        # 29 February
        return start.replace(year=start.year + years, day=28)


@dataclass
class KartaData:
    surname: str = ""
    name: str = ""
    patronymic: str = ""
    gender: str = ""                  # "male" | "female"
    citizenship: str = ""
    birth_date: date | None = None
    issued: date | None = None
    expiry: date | None = None
    #: what the operator types: «АА1234567»
    card_code: str = ""
    #: the running numbers the program hands out
    serial: str = ""                  # 964390
    card_number: str = ""             # 70029807586
    series: str = ""                  # 0077
    photo_png: bytes | None = None
    sign_png: bytes | None = None
    layout: dict = field(default_factory=dict)

    def fio(self) -> str:
        parts = [p.strip() for p in (self.surname, self.name, self.patronymic)
                 if (p or "").strip()]
        return " ".join(parts).upper()


def _dots(value: date | None) -> str:
    return f"{value:%d.%m.%Y}" if value else ""


def _country(citizenship: str) -> str:
    return _COUNTRY.get((citizenship or "").strip().upper(), "UZB")


def _check_digit(text: str) -> str:
    """ICAO 7-3-1 — the digit that proves the field was read right."""
    weights = (7, 3, 1)
    total = 0
    for i, ch in enumerate(text):
        if ch.isdigit():
            value = int(ch)
        elif ch.isalpha():
            value = ord(ch.upper()) - 55
        else:
            value = 0
        total += value * weights[i % 3]
    return str(total % 10)


def mrz(data: KartaData) -> tuple[str, str, str]:
    """The card's three machine-readable lines, ICAO TD-1 shaped."""
    code = "".join((data.card_code or "").split()).upper()
    number = "".join((data.card_number or "").split())
    line1 = f"I<MOS{code}{number}"
    line1 = (line1 + MRZ_FILL * MRZ_LEN)[:MRZ_LEN]

    birth = f"{data.birth_date:%y%m%d}" if data.birth_date else "0" * 6
    expiry = f"{data.expiry:%y%m%d}" if data.expiry else "0" * 6
    sex = "F" if data.gender == "female" else "M"
    body = f"{birth}{_check_digit(birth)}{sex}{expiry}" \
           f"{_check_digit(expiry)}{_country(data.citizenship)}"
    line2 = (body + MRZ_FILL * MRZ_LEN)[:MRZ_LEN - 1]
    line2 += _check_digit(line1 + body)

    # the third line carries the SURNAME and the given name only — the
    # office prints no patronymic there
    names = [to_latin(p) for p in (data.surname, data.name)
             if (p or "").strip()]
    line3 = MRZ_FILL.join(names)
    line3 = (line3 + MRZ_FILL * MRZ_LEN)[:MRZ_LEN]
    return line1, line2, line3


def qr_payload(data: KartaData) -> str:
    """What the card's QR really carries — the owner's own wording."""
    gender = "Ж" if data.gender == "female" else "М"
    return "\n".join([
        f"ФИО: {data.fio()}",
        f"ДАТА РОЖДЕНИЯ: {_dots(data.birth_date)}",
        f"ПОЛ: {gender}",
        f"ГРАЖДАНСТВО: {(data.citizenship or '').upper()}",
        f"НОМЕР КАРТИ: {CARD_REGION} {data.card_number}",
        f"ДАТА ОКОНЧАНИЯ СРОКА: {_dots(data.expiry)}",
    ])


def make_qr(text: str) -> bytes:
    import qrcode

    maker = qrcode.QRCode(border=1, box_size=8)
    maker.add_data(text)
    maker.make(fit=True)
    out = io.BytesIO()
    maker.make_image(fill_color="black", back_color="white").save(out, "PNG")
    return out.getvalue()


def values(data: KartaData) -> dict[str, str]:
    """Every slot's finished text — the sample card's own manner."""
    line1, line2, line3 = mrz(data)
    rest = " ".join(p.strip().upper() for p in (data.name, data.patronymic)
                    if (p or "").strip())
    return {
        "fio_surname": (data.surname or "").strip().upper(),
        "fio_rest": rest,
        "birth_date": _dots(data.birth_date),
        "gender": "Ж" if data.gender == "female" else "М",
        "citizenship": (data.citizenship or "").strip().upper(),
        "card_region": CARD_REGION,
        "card_number": (data.card_number or "").strip(),
        "card_series": f"{SERIES_HEAD} {data.series}".strip(),
        "expiry": _dots(data.expiry),
        "mrz1": line1, "mrz2": line2, "mrz3": line3,
        "back_number": "".join((data.card_code or "").split()).upper(),
    }


def placed(layout: dict | None) -> dict[str, Slot]:
    """The measured slots plus whatever the office changed — position,
    size, colour and weight all travel in the saved layout."""
    out = dict(SLOTS)
    fields = (layout or {}).get("fields") or {}
    styles = (layout or {}).get("styles") or {}
    for key, moved in fields.items():
        if key in out and len(moved) == 3:
            slot = out[key]
            x, baseline, size = (float(v) for v in moved)
            out[key] = Slot(slot.page, x, baseline, size, bold=slot.bold,
                            colour=slot.colour, mono=slot.mono)
    for key, style in styles.items():
        if key not in out:
            continue
        slot = out[key]
        colour = style.get("colour")
        out[key] = Slot(
            slot.page, slot.x, slot.baseline, slot.size,
            bold=bool(style.get("bold", slot.bold)),
            colour=(tuple(float(c) for c in colour) if colour else slot.colour),
            mono=slot.mono)
    return out


def fill_to_width(text: str, room: float, measure, size: float,
                  tail: str = "") -> str:
    """``text`` padded with «<» until one more would pass ``room``.

    The office asked for this in as many words: normal spacing, the
    sample's own letter size, and the gap filled with chevrons. ``tail``
    is a character that must stay LAST — line 2's check digit does.
    """
    body = text
    while True:
        candidate = body + MRZ_FILL + tail
        wide = (measure.text_length(candidate, size) if measure
                else len(candidate) * size * 0.5)
        if wide > room:
            return body + tail
        body += MRZ_FILL


def _write_mrz(page, text: str, slot: Slot, size: float,
               left: float, right: float, *, fontfile: str,
               fontname: str, tail: str = "") -> None:
    """One machine line: natural spacing, chevrons out to the right edge."""
    width, height = page.rect.width, page.rect.height
    try:
        measure = fitz.Font(fontfile=fontfile)
    except Exception:                             # noqa: BLE001
        measure = None
    room = (right - left) * width
    line = fill_to_width(text, room, measure, size, tail)
    page.insert_text((left * width, slot.baseline * height), line,
                     fontsize=size, fontfile=fontfile, fontname=fontname,
                     color=slot.colour, fill_opacity=TEXT_OPACITY)


def _fit(box, aspect: float, inset: float = 0.0):
    """The biggest rect of ``aspect`` (w/h) inside the box, centred."""
    x0, y0, x1, y1 = box
    if inset:
        dx, dy = (x1 - x0) * inset, (y1 - y0) * inset
        x0, y0, x1, y1 = x0 + dx, y0 + dy, x1 - dx, y1 - dy
    return x0, y0, x1, y1


def render(data: KartaData, inner: Path | str,
           outer: Path | str | None = None) -> bytes:
    """The finished card: inner page first, the outer side after it."""
    inner = Path(inner)
    if not inner.exists():
        raise OfisError("Карта бланкаси топилмади — бўлимда юкланг.")

    def _open(path: Path) -> fitz.Document:
        with fitz.open(str(path)) as raw:
            source = (raw if raw.is_pdf
                      else fitz.open("pdf", raw.convert_to_pdf()))
            return fitz.open("pdf", source.tobytes())

    doc = _open(inner)
    with doc:
        if outer is not None and Path(outer).exists():
            with _open(Path(outer)) as back:
                doc.insert_pdf(back)
        slots = placed(data.layout)
        texts = values(data)
        # the strip must END where the expiry date above it ends — measure
        # that line rather than trusting a fixed number, so moving the date
        # in the layout editor keeps the two flush
        right = MRZ_RIGHT
        expiry_slot = slots.get("expiry")
        if expiry_slot is not None and texts.get("expiry"):
            family = FONT_BOLD if expiry_slot.bold else FONT_REGULAR
            try:
                measure = fitz.Font(fontfile=str(_font_file(family)))
                page0 = doc[0]
                grown = measure.text_length(
                    texts["expiry"], expiry_slot.size * page0.rect.height)
                right = expiry_slot.x + grown / page0.rect.width
            except Exception:                     # noqa: BLE001
                right = MRZ_RIGHT
        for key, text in texts.items():
            slot = slots.get(key)
            if slot is None or not text or slot.page > doc.page_count:
                continue
            page = doc[slot.page - 1]
            width, height = page.rect.width, page.rect.height
            family = (FONT_MRZ if slot.mono
                      else (FONT_BOLD if slot.bold else FONT_REGULAR))
            fontfile = str(_font_file(family))
            fontname = _fontname(family)
            size = slot.size * height
            if slot.mono:
                # The machine zone is one fixed strip, not free text: it
                # always starts under the photo frame, ends level with the
                # expiry date and prints at the sample card's own letter
                # size. A saved layout may still raise or lower a line —
                # only that. (Honouring a saved x/size is what left the
                # strip short and small on the office's own card.)
                size = MRZ_SIZE * height
                tail = text[-1] if key == "mrz2" else ""
                body = text[:-1] if tail else text
                _write_mrz(page, body.rstrip(MRZ_FILL), slot, size, MRZ_LEFT,
                           right, fontfile=fontfile, fontname=fontname,
                           tail=tail)
                continue
            page.insert_text((slot.x * width, slot.baseline * height), text,
                             fontsize=size, fontfile=fontfile,
                             fontname=fontname,
                             color=slot.colour, fill_opacity=TEXT_OPACITY)
        page = doc[0]
        width, height = page.rect.width, page.rect.height
        if data.photo_png:
            # the frame is filled edge to edge: the crop already carries the
            # frame's own shape, so anything left over is trimmed, never
            # letterboxed into a grey band
            x0, y0, x1, y1 = PHOTO_BOX
            page.insert_image(fitz.Rect(x0 * width, y0 * height,
                                        x1 * width, y1 * height),
                              stream=data.photo_png, keep_proportion=False)
        x0, y0, x1, y1 = _fit(QR_BOX, 1.0, QR_INSET)
        side = min((x1 - x0) * width, (y1 - y0) * height)
        cx = (x0 + x1) / 2 * width
        cy = (y0 + y1) / 2 * height
        page.insert_image(fitz.Rect(cx - side / 2, cy - side / 2,
                                    cx + side / 2, cy + side / 2),
                          stream=make_qr(qr_payload(data)))
        if data.sign_png:
            x0, y0, x1, y1 = SIGN_BOX
            pix = fitz.Pixmap(data.sign_png)
            aspect = pix.width / pix.height if pix.height else 1.0
            box_w, box_h = (x1 - x0) * width, (y1 - y0) * height
            tall = min(box_h, box_w / aspect)
            wide = tall * aspect
            cx = (x0 + x1) / 2 * width
            cy = (y0 + y1) / 2 * height
            page.insert_image(fitz.Rect(cx - wide / 2, cy - tall / 2,
                                        cx + wide / 2, cy + tall / 2),
                              stream=data.sign_png)
        return doc.tobytes()


def output_name(data: KartaData) -> str:
    parts = [p.strip().upper() for p in (data.surname, data.name)
             if (p or "").strip()]
    stem = "_".join(parts) or "KARTA"
    keep = "".join(c for c in stem if c.isalnum() or c in "_-")
    return f"{keep or 'KARTA'}.pdf"
