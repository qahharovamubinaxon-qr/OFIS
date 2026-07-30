"""Fill the МИГ «ИШЧИ КАРТАСИ» on the firm's own blank.

Everything the card says comes from two places: the worker's passport, which the
reader takes the name, birth date, citizenship, sex and passport number off, and
the four things the office types itself — the card's series and number, the visa
if there is one, which of the four jobs the worker holds, and the dates.

Nothing else is printed. Every other word on the card is already on the blank.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import fitz

from src.common.logging import get_logger
from src.pdf.engine import _font_file
from src.pdf.mig_spec import (
    AKSHAR,
    CODE_SLOTS,
    DEFAULT_STAMP,
    FIELDS,
    JOBS,
    MONO,
    RULE_WIDTH,
    SEX_X,
    STROKE_SHARE,
    TEXT_OPACITY,
    TIMES,
    Rule,
    Slot,
)

log = get_logger(__name__)

#: One handle per face registered on the page.
_HANDLES = {MONO: "mig", AKSHAR: "migA", TIMES: "migT"}

#: How the card spells a surname in Latin, under the Cyrillic one.
#:
#: This is the UZBEK passport's table, not the Russian one: «ЖАХОНГИРОВА» is
#: «JAKHONGIROVA» on the office's own card, with a plain J — the Russian «ZH»
#: would put a letter on the card that is not on the worker's passport, and the
#: passport is what an inspector holds the card against.
_LATIN = {
    "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Е": "E", "Ё": "E",
    "Ж": "J", "З": "Z", "И": "I", "Й": "I", "К": "K", "Л": "L", "М": "M",
    "Н": "N", "О": "O", "П": "P", "Р": "R", "С": "S", "Т": "T", "У": "U",
    "Ф": "F", "Х": "KH", "Ц": "TS", "Ч": "CH", "Ш": "SH", "Щ": "SHCH",
    "Ъ": "IE", "Ы": "Y", "Ь": "", "Э": "E", "Ю": "IU", "Я": "IA",
    "Ҳ": "KH", "Қ": "K", "Ғ": "G", "Ӣ": "I", "Ӯ": "U", "Ҷ": "J", "Ө": "O",
    "Ң": "N", "Ү": "U", "Ұ": "U", "Һ": "KH", "Ә": "A", "І": "I", "Ї": "I",
    "Є": "E", "Ґ": "G",
}


@dataclass(frozen=True)
class MigData:
    """Everything one ИШЧИ КАРТАСИ says."""

    # --- typed by the office
    series: str = ""
    number: str = ""
    visa: str = ""
    #: which of :data:`src.pdf.mig_spec.JOBS` the worker holds — keys
    jobs: tuple[str, ...] = ()
    valid_from: date | None = None
    valid_to: date | None = None
    issued_on: date | None = None
    # --- read off the passport
    surname: str = ""
    #: the surname in Latin; derived from the Cyrillic one when not given
    surname_latin: str = ""
    name: str = ""
    patronymic: str = ""
    birth_date: date | None = None
    citizenship: str = ""
    passport: str = ""
    #: «Мужской» / «Женский» — an X goes in that box
    gender: str = ""
    #: the office's own 3-4 digit code, printed at all four corners round the
    #: issue date
    code: str = ""
    # --- the firm's stamp
    stamp: bytes | None = None
    #: (left, top, right, bottom) shares of the page
    stamp_box: tuple[float, float, float, float] = field(default=DEFAULT_STAMP)


def to_latin(text: str) -> str:
    """«ЖАХОНГИРОВА» → «JAKHONGIROVA», the way the passport spells it."""
    out = []
    for ch in text or "":
        mapped = _LATIN.get(ch.upper())
        if mapped is None:
            out.append(ch)
        elif ch.islower():
            out.append(mapped.lower())
        else:
            out.append(mapped)
    return "".join(out)


def spaced(text: str) -> str:
    """«ЖАХОНГИРОВА» → «Ж А Х О Н Г И Р О В А».

    The card is typed a letter to a box, so every letter stands apart. Runs of
    space in the original become a DOUBLE gap, which is how «РАХИМ  КИЗИ» reads
    on the office's own card — one word ending and the next beginning.
    """
    words = (text or "").split()
    return "   ".join(" ".join(w) for w in words)


def digits_spaced(text: str) -> str:
    """«13.08.2009» → «1 3   0 8   2 0 0 9», the way a date is typed in."""
    parts = [p for p in (text or "").replace("-", ".").split(".") if p]
    return "   ".join(" ".join(p) for p in parts) if parts else spaced(text)


def _dmy(value: date | None) -> str:
    return value.strftime("%d.%m.%Y") if value else ""


def _fonts(page) -> None:
    for family, handle in _HANDLES.items():
        page.insert_font(fontname=handle, fontfile=str(_font_file(family)))


def _write(page, slot: Slot, text: str) -> None:
    """Draw one value at its fraction of the page, shrinking it to fit."""
    if not text:
        return
    rect = page.rect
    size = slot.size * rect.height
    limit = slot.width * rect.width
    family = getattr(slot, "font", MONO)
    font = fitz.Font(fontfile=str(_font_file(family)))
    while size > 3.0 and font.text_length(text, fontsize=size) > limit:
        size -= 0.3
    # filled AND stroked, so the type comes out a shade heavier than the plain
    # face — the way a typewriter strikes, and what the office asked for
    page.insert_text((slot.x * rect.width, slot.baseline * rect.height), text,
                     fontname=_HANDLES.get(family, "mig"), fontsize=size,
                     color=slot.colour, fill=slot.colour,
                     render_mode=2, border_width=STROKE_SHARE,
                     fill_opacity=TEXT_OPACITY, stroke_opacity=TEXT_OPACITY)


def _underline(page, rule) -> None:
    """The line under the job the worker holds, corner to corner of the word."""
    rect = page.rect
    y = rule.y * rect.height
    page.draw_line((rule.x0 * rect.width, y), (rule.x1 * rect.width, y),
                   color=(0.05, 0.05, 0.05),
                   width=max(0.5, RULE_WIDTH * rect.height))


def _place_stamp(page, stamp: bytes | None, box) -> None:
    """The firm's stamp, where and how big the office put it."""
    if not stamp:
        return
    rect = page.rect
    where = fitz.Rect(box[0] * rect.width, box[1] * rect.height,
                      box[2] * rect.width, box[3] * rect.height)
    try:
        page.insert_image(where, stream=stamp, keep_proportion=True,
                          overlay=True)
    except Exception as exc:                          # noqa: BLE001
        # anything at all: one unreadable stamp costs the stamp, not the card
        log.warning("МИГ: печат жойлашмади: %s", exc)


def _blank_page(doc, template: Path):
    """Start the card on the firm's own blank, PDF or picture."""
    template = Path(template)
    if template.suffix.lower() == ".pdf":
        with fitz.open(str(template)) as source:
            if source.page_count:
                doc.insert_pdf(source, from_page=0, to_page=0)
                return doc[-1]
        raise ValueError(f"бўш бланка: {template.name}")
    picture = fitz.Pixmap(str(template))
    width, height = 595.0, 842.0
    if picture.width and picture.height:
        if picture.width > picture.height:
            width, height = 842.0, 842.0 * picture.height / picture.width
        else:
            height, width = 842.0, 842.0 * picture.width / picture.height
    page = doc.new_page(width=width, height=height)
    page.insert_image(page.rect, filename=str(template), keep_proportion=False)
    return page


def effective(layout: dict | None):
    """The slots this blank actually uses: the measured ones, plus any the
    office moved with the mouse on its own copy of the card."""
    fields = dict(FIELDS)
    sex = dict(SEX_X)
    jobs = {key: rule for key, _label, rule in JOBS}
    moved = layout or {}
    for key, value in (moved.get("fields") or {}).items():
        if key in fields and len(value) == 3:
            fields[key] = fields[key]._replace(
                x=float(value[0]), baseline=float(value[1]), size=float(value[2]))
    for key, value in (moved.get("sex") or {}).items():
        if key in sex and len(value) == 3:
            sex[key] = sex[key]._replace(
                x=float(value[0]), baseline=float(value[1]), size=float(value[2]))
    for key, value in (moved.get("jobs") or {}).items():
        if key in jobs and len(value) == 3:
            jobs[key] = Rule(float(value[0]), float(value[1]), float(value[2]))
    return fields, sex, jobs


def render(data: MigData, template: Path, layout: dict | None = None) -> bytes:
    """One filled ИШЧИ КАРТАСИ, as a one-page PDF."""
    fields, sex_slots, job_rules = effective(layout)
    doc = fitz.open()
    page = _blank_page(doc, template)
    _place_stamp(page, data.stamp, data.stamp_box)
    _fonts(page)

    latin = (data.surname_latin or to_latin(data.surname)).upper()
    values = {
        "series": (data.series or "").strip(),
        "number": (data.number or "").strip(),
        "surname": (data.surname or "").strip().upper(),
        "surname_lat": latin,
        "name": (data.name or "").strip().upper(),
        "patronymic": (data.patronymic or "").strip().upper(),
        "birth_date": _dmy(data.birth_date),
        "citizenship": (data.citizenship or "").strip().upper(),
        "passport": "".join((data.passport or "").split()).upper(),
        "visa": "".join((data.visa or "").split()).upper(),
        "valid_from": _dmy(data.valid_from),
        "valid_to": _dmy(data.valid_to),
        "issued": data.issued_on.strftime("%d %m %y") if data.issued_on else "",
    }
    code = "".join(ch for ch in (data.code or "") if ch.isdigit())
    values.update({key: code for key in CODE_SLOTS})
    for key, text in values.items():
        slot = fields[key]
        if not text:
            continue
        if slot.spaced:
            text = (digits_spaced(text) if key in ("birth_date", "passport")
                    else spaced(text))
        _write(page, slot, text)

    sex = _sex_key(data.gender)
    if sex:
        _write(page, sex_slots[sex], "X")
    for key, rule in job_rules.items():
        if key in data.jobs:
            _underline(page, rule)

    log.info("МИГ: %s %s — %s №%s, %s — %s", data.surname, data.name,
             data.series, data.number, _dmy(data.valid_from), _dmy(data.valid_to))
    out = doc.tobytes()
    doc.close()
    return out


def _sex_key(gender: str) -> str:
    """«Женский», «Ж», «female» → «female»; «Мужской», «М» → «male»."""
    word = (gender or "").strip().lower()
    if not word:
        return ""
    if word.startswith(("ж", "f", "w", "аёл", "ayol")):
        return "female"
    if word.startswith(("м", "m", "эрк", "erk")):
        return "male"
    return ""


def as_png(pdf: bytes, zoom: float = 3.0) -> bytes:
    """The finished card as a picture, for the screen and for the phone."""
    with fitz.open("pdf", pdf) as doc:
        return doc[0].get_pixmap(matrix=fitz.Matrix(zoom, zoom)).tobytes("png")
