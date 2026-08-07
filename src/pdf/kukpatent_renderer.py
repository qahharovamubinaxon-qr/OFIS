"""КУК ПАТЕНТ — one worker's card, drawn onto the office's own two scans.

Both sides are filled the same way: the office's scan underneath, the
worker's values on top, and on the front his photograph in the white 3×4
window — cut out of whatever picture was dropped, stood on white, and fitted
to the frame edge to edge.

Everything the program adds is laid on at 85 %, on the office's own
instruction. Ink at full strength sits ON a scan and reads as a sticker; at
85 % it sinks into the paper's own tone the way a printed card does.

Nothing here talks to the network and nothing here decides anything: the
values arrive finished, the card's number arrives finished, and the picture
arrives already cut.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import fitz

from src.common.errors import OfisError
from src.pdf.fonts import font_file, font_id
from src.pdf.kukpatent_spec import (
    BACK,
    FRONT,
    OPACITY,
    PAGE_H,
    PAGE_W,
    PHOTO_DEFAULT,
    PHOTO_KEY,
    SIDES,
    Slot,
    slots_of,
)

#: How thickly a one-weight face is stroked when bold was asked for.
FAUX_BOLD = 0.03


@dataclass
class KukPatentData:
    """One worker, as the two sides of the card name him."""

    surname: str = ""
    name: str = ""
    patronymic: str = ""
    birth_date: date | None = None
    #: «М» / «Ж», as the card prints it
    gender: str = ""
    citizenship: str = ""
    #: what the card calls the document — «Иностранный паспорт ID3956001»
    document: str = ""
    #: «88» and «3259366», typed by the operator off the card in its hand
    series: str = ""
    number: str = ""
    #: the firm, as the office saved it — one or two lines
    firm: str = ""
    issued: date | None = None
    #: «АА3915699» — the card's own number, made by the service
    card_no: str = ""
    photo_png: bytes | None = None
    layout: dict = field(default_factory=dict)

    def fio(self) -> str:
        return " ".join(p for p in (self.surname, self.name, self.patronymic)
                        if (p or "").strip())


def firm_lines(firm: str) -> tuple[str, str]:
    """The firm's name across the two lines the card gives it.

    A newline typed by the office wins — it knows where its own name should
    break. Otherwise the break falls before the quoted part, which is where
    it falls on the office's own sample: «…ответственностью ООО» / «"Сфера"
    отдел кадров».
    """
    text = " ".join((firm or "").split("\n"))
    if "\n" in (firm or ""):
        first, _, second = (firm or "").partition("\n")
        return first.strip(), " ".join(second.split())
    words = text.split()
    if not words:
        return "", ""
    for index, word in enumerate(words):
        if word.startswith(('"', "«", "'")) and index:
            return " ".join(words[:index]), " ".join(words[index:])
    if len(words) <= 5:
        return " ".join(words), ""
    half = (len(words) + 1) // 2
    return " ".join(words[:half]), " ".join(words[half:])


def values(data: KukPatentData, side: str) -> dict[str, str]:
    """Every named value on one side, finished."""
    if side == BACK:
        first, second = firm_lines(data.firm)
        return {
            "citizenship": (data.citizenship or "").strip(),
            "document": (data.document or "").strip(),
            "firm1": first,
            "firm2": second,
            "issued": data.issued.strftime("%d.%m.%Y") if data.issued else "",
            "card_no": (data.card_no or "").strip(),
        }
    born = data.birth_date
    return {
        "series": (data.series or "").strip(),
        "number": (data.number or "").strip(),
        "surname": (data.surname or "").strip(),
        "name": (data.name or "").strip(),
        "patronymic": (data.patronymic or "").strip(),
        "birth_date": born.strftime("%d.%m.%Y") if born else "",
        "gender": (data.gender or "").strip(),
    }


def placed(side: str, layout: dict) -> dict[str, Slot]:
    """The side's slots, wearing whatever the office dragged and restyled."""
    moved = ((layout or {}).get("fields") or {}).get(side) or {}
    styles = ((layout or {}).get("styles") or {}).get(side) or {}
    out: dict[str, Slot] = {}
    for key, slot in slots_of(side).items():
        x, baseline, size = slot.x, slot.baseline, slot.size
        spot = moved.get(key)
        if spot and len(spot) == 3:
            x, baseline, size = (float(v) for v in spot)
        chosen = styles.get(key) or {}
        out[key] = Slot(
            x, baseline, float(chosen.get("size") or size),
            bool(chosen.get("bold", slot.bold)),
            tuple(chosen.get("colour") or slot.colour)[:3],
            str(chosen.get("font") or slot.family),
            slot.sample, slot.label)
    return out


def placed_photo(layout: dict) -> tuple[float, float, float, float]:
    """The photo window: «left, top, width, height», all page shares."""
    moved = ((layout or {}).get("images") or {}).get(FRONT) or {}
    got = moved.get(PHOTO_KEY)
    if got and len(got) == 4:
        return tuple(float(v) for v in got)          # type: ignore[return-value]
    if got and len(got) == 3:
        # the editor hands back «left, BOTTOM, height» — the photo keeps its
        # own 3×4, so the width follows from the height and nothing is squashed
        left, bottom, height = (float(v) for v in got)
        width = height * PAGE_H * 0.75 / PAGE_W
        return (left, bottom - height, width, height)
    return PHOTO_DEFAULT


def faded(png: bytes, opacity: float = OPACITY) -> bytes:
    """The same picture, laid on at ``opacity`` — the office asked for 85 %."""
    from PIL import Image

    with Image.open(io.BytesIO(png)) as image:
        rgba = image.convert("RGBA")
        alpha = rgba.getchannel("A").point(
            lambda a: int(a * max(0.0, min(1.0, opacity))))
        rgba.putalpha(alpha)
        out = io.BytesIO()
        rgba.save(out, "PNG")
        return out.getvalue()


def render(data: KukPatentData, side: str, blank: Path | None = None) -> bytes:
    """One side of the card, ready for the printer."""
    text = values(data, side)
    slots = placed(side, data.layout)
    doc = fitz.open()
    try:
        page = doc.new_page(width=PAGE_W, height=PAGE_H)
        _lay_blank(page, blank)
        if side == FRONT and data.photo_png:
            _lay_photo(page, data.photo_png, placed_photo(data.layout))
        for key, slot in slots.items():
            _write(page, slot, text.get(key, ""))
        for extra in ((data.layout or {}).get("extra") or []):
            if str(extra.get("side", side)) != side:
                continue
            _write(page, Slot(
                float(extra.get("x", 0.1)), float(extra.get("baseline", 0.1)),
                float(extra.get("size", 0.0165)),
                bool(extra.get("bold", False)),
                tuple(extra.get("colour") or (0.0, 0.0, 0.0))[:3],
                str(extra.get("font") or "Times New Roman")),
                str(extra.get("text") or ""))
        return _packed(doc)
    finally:
        doc.close()


def _packed(doc) -> bytes:
    """The document, squeezed — losslessly, and it is worth a great deal.

    The office's blanks are photographs, and a page carrying one came out at
    14 MB with the picture stored raw. Zlib brings the same pixels down to
    1.7 MB, so a card is a file that can be sent rather than one that fills
    a disk. Nothing is re-encoded: what comes out is what went in.
    """
    return doc.tobytes(garbage=4, deflate=True, deflate_images=True)


def render_both(data: KukPatentData,
                blanks: dict[str, Path]) -> dict[str, bytes]:
    """Both sides, each on its own blank, as its own document."""
    return {side: render(data, side, blanks.get(side)) for side in SIDES}


def render_pair(data: KukPatentData, blanks: dict[str, Path]) -> bytes:
    """ONE document, the front its first page and the back its second.

    The office asked for this in so many words: «олди орқани битта PDF га
    сақлаберадиган қил». A card is one thing, and two files for it means two
    things to find, two to attach and one to forget.
    """
    made = fitz.open()
    try:
        for side in SIDES:
            with fitz.open("pdf", render(data, side, blanks.get(side))) as one:
                made.insert_pdf(one)
        return _packed(made)
    finally:
        made.close()


def _lay_blank(page, blank: Path | None) -> None:
    if blank is None:
        return
    blank = Path(blank)
    if not blank.exists():
        raise OfisError(f"Бланка топилмади: {blank.name}")
    if blank.suffix.lower() == ".pdf":
        with fitz.open(str(blank)) as raw:
            # a sheet scanned by a phone often arrives named «.pdf» while
            # being something else inside; whatever it is, it becomes a PDF
            source = raw if raw.is_pdf else fitz.open(
                "pdf", raw.convert_to_pdf())
            try:
                if source.page_count:
                    page.show_pdf_page(page.rect, source, 0)
            finally:
                if source is not raw:
                    source.close()
        return
    page.insert_image(page.rect, filename=str(blank))


def _lay_photo(page, png: bytes, where) -> None:
    """The worker's picture, filling its window and faded to 85 %."""
    left, top, width, height = where
    page.insert_image(
        fitz.Rect(left * PAGE_W, top * PAGE_H,
                  (left + width) * PAGE_W, (top + height) * PAGE_H),
        stream=faded(png), keep_proportion=False)


def _write(page, slot: Slot, text: str) -> None:
    if not text:
        return
    size = slot.size * PAGE_H
    face, faux = font_file(slot.family, slot.bold)
    page.insert_text((slot.x * PAGE_W, slot.baseline * PAGE_H), text,
                     fontsize=size, fontfile=str(face),
                     fontname=font_id(slot.family, slot.bold),
                     color=slot.colour, render_mode=2 if faux else 0,
                     border_width=FAUX_BOLD if faux else 0.0,
                     fill_opacity=OPACITY, stroke_opacity=OPACITY)


def output_stem(data: KukPatentData, side: str | None = None) -> str:
    """«ЭРГЕШОВ_ОМУРБЕК» — one card, one name, whichever way it is saved.

    ``side`` is only given when the two sides are wanted as separate files;
    the office prints them as one document with two pages, so the plain name
    is what it sees.
    """
    parts = [p.strip().upper() for p in (data.surname, data.name)
             if (p or "").strip()]
    tail = "" if side is None else ("oldi" if side == FRONT else "orqa")
    if not parts:
        return f"KUKPATENT_{tail}" if tail else "KUKPATENT"
    stem = "_".join([*parts, tail] if tail else parts)
    return "".join(c for c in stem if c.isalnum() or c in "_-") or "KUKPATENT"
