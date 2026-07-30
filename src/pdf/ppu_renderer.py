"""Fill the ППУ pair from the office's own blanks.

Two sheets — a front and a back. The values come off the регистрация the
operator drops in; the start date they type; the end date the регистрация
itself carries. The worker's photograph goes in the window on the front with
its background cut away and laid on at seven parts in ten, so the sheet's own
paper shows through it the way the office's cards look.

The blanks are pictures, so nothing is rewritten and nothing on them is
touched: every value is drawn at the fraction of the page
:mod:`src.pdf.ppu_spec` puts it at.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import fitz

from src.common.logging import get_logger
from src.pdf.engine import _font_file
from src.pdf.ppu_spec import (
    ADDRESS_CHARS,
    ADDRESS_LEADING,
    ADDRESS_LINES,
    ADDRESS_MAX_WORDS,
    ADDRESS_MIN_WORDS,
    BACK,
    FRONT,
    PHOTO_BOX,
    PHOTO_OPACITY,
    SANS,
    SANS_BOLD,
    TEXT_OPACITY,
    Slot,
)

log = get_logger(__name__)

#: The two halves of a blank, in the order they are printed.
PAGE_FILES = ("front.pdf", "back.pdf")

_FONT_KEYS = {"pp": SANS, "ppb": SANS_BOLD}

#: ICAO Doc 9303, the table the passports themselves use.
_LATIN = {
    "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Е": "E", "Ё": "E",
    "Ж": "ZH", "З": "Z", "И": "I", "Й": "I", "К": "K", "Л": "L", "М": "M",
    "Н": "N", "О": "O", "П": "P", "Р": "R", "С": "S", "Т": "T", "У": "U",
    "Ф": "F", "Х": "KH", "Ц": "TS", "Ч": "CH", "Ш": "SH", "Щ": "SHCH",
    "Ъ": "IE", "Ы": "Y", "Ь": "", "Э": "E", "Ю": "IU", "Я": "IA",
    "Ҳ": "KH", "Қ": "K", "Ғ": "G", "Ӣ": "I", "Ӯ": "U", "Ҷ": "J", "Ө": "O",
    "Ң": "N", "Ү": "U", "Ұ": "U", "Һ": "KH", "Ә": "A", "І": "I", "Ї": "I",
    "Є": "E", "Ґ": "G",
}


@dataclass(frozen=True)
class PpuData:
    """Everything one ППУ pair says."""

    surname: str = ""
    name: str = ""
    patronymic: str = ""
    birth_date: date | None = None
    gender: str = ""
    citizenship: str = ""
    #: the foreign passport as printed — «AL0531591». Printed five times
    #: across the pair, against every «Иностранный паспорт» label.
    document: str = ""
    address: str = ""
    valid_from: date | None = None
    valid_to: date | None = None
    photo: bytes | None = None


def title_case(text: str) -> str:
    """«АРУТЮНЯН АРТАК» → «Арутюнян Артак», hyphens counted as word breaks."""
    def one(word: str) -> str:
        return "-".join(p[:1].upper() + p[1:].lower() for p in word.split("-"))

    return " ".join(one(w) for w in (text or "").split())


def to_latin(text: str) -> str:
    """«Арутюнян Артак Пайлунович» → «Arutiunian Artak Pailunovich»."""
    out = []
    for ch in text or "":
        mapped = _LATIN.get(ch.upper())
        if mapped is None:
            out.append(ch)
        elif ch.islower():
            # «ю» inside a word is «iu», not «Iu» — a capital in the middle of
            # a surname is exactly the kind of thing an inspector notices
            out.append(mapped.lower())
        else:
            out.append(mapped)
    return "".join(out)


def passport_line(document: str) -> str:
    """«FA 1234567» → «№FA1234567», the way the sheet prints it.

    The reader hands the series and the number back with a space between them
    because that is how a passport prints them; the ППУ runs them together
    behind a «№», as the office's own filled pair does.
    """
    packed = "".join((document or "").split())
    return f"№{packed}" if packed else ""


def full_name(surname: str, name: str, patronymic: str = "") -> str:
    parts = [title_case(p) for p in (surname, name, patronymic) if (p or "").strip()]
    return " ".join(parts)


def tidy_address(address: str) -> str:
    """«улДомодедовская» → «ул. Домодедовская».

    The readers run a Russian address abbreviation into the word after it —
    «ул.Домодедовская», or worse «улДомодедовская» with the stop lost as
    well — and the sheet then names a street nobody can find.

    Only a run-together abbreviation is separated, and only where a CAPITAL or
    a digit follows it: that is what makes «улДомодедовская» a join and
    «Тульская» an ordinary word. The match is case-sensitive on purpose —
    folding case would let «кв» split «квартира», and «к» split «кв».
    """
    import re

    short = ("обл", "край", "респ", "р-н", "пгт", "гор", "пос", "мкр",
             "пр-кт", "просп", "б-р", "наб", "пер", "влд", "корп", "стр",
             "ком", "оф", "кв", "ул", "пр", "ш", "д", "г", "с", "к")
    text = " ".join((address or "").split())
    if not text:
        return ""
    for form in short:
        for spelling in (form, form.capitalize()):
            text = re.sub(
                rf"(?<![А-Яа-яЁёA-Za-z]){re.escape(spelling)}"
                rf"\.?(?=[А-ЯЁA-Z0-9])",
                f"{spelling}. ", text)
    return " ".join(text.split())


#: The short forms an address uses. A line may not END on one of these.
_ABBREV = frozenset((
    "обл", "край", "респ", "р-н", "пгт", "гор", "пос", "мкр", "пр-кт",
    "просп", "б-р", "наб", "пер", "влд", "корп", "стр", "ком", "оф",
    "кв", "ул", "пр", "ш", "д", "г", "с", "к",
))


def _is_abbrev(word: str) -> bool:
    return word.rstrip(".").lower() in _ABBREV and word.endswith(".")


def address_lines(address: str, budget: int = ADDRESS_CHARS,
                  max_lines: int = ADDRESS_LINES) -> list[str]:
    """A whole address broken the way the office writes it.

    How many words go on a line is decided by their LENGTH, not their number:
    «Московская обл., Балашихинский р-н,» is four words and already a full
    line, while «г. Москва, ул. Мира, д. 5,» is six and still short. So each
    line is filled to a width and then bounded — never fewer than
    :data:`ADDRESS_MIN_WORDS`, never more than :data:`ADDRESS_MAX_WORDS`.

    Whatever will not fit in the last line is kept on it rather than dropped:
    an address missing its flat number is not the address.
    """
    words = tidy_address(address).split()
    if not words:
        return []
    lines: list[str] = []
    at = 0
    while at < len(words):
        if len(lines) == max_lines - 1:
            lines.append(" ".join(words[at:]))          # the rest, all of it
            break
        take = min(ADDRESS_MIN_WORDS, len(words) - at)
        while (take < ADDRESS_MAX_WORDS and at + take < len(words)
               and len(" ".join(words[at:at + take + 1])) <= budget):
            take += 1
        # never end a line on a bare «д.» or «кв.» — the number it introduces
        # is on the next line and the two read as different things
        while take > 1 and _is_abbrev(words[at + take - 1]):
            take -= 1
        lines.append(" ".join(words[at:at + take]))
        at += take
    return lines


def _dmy(value: date | None) -> str:
    return value.strftime("%d.%m.%Y") if value else ""


def _fonts(page) -> dict[str, str]:
    for handle, key in _FONT_KEYS.items():
        page.insert_font(fontname=handle, fontfile=str(_font_file(key)))
    return {key: handle for handle, key in _FONT_KEYS.items()}


def _write(page, slot: Slot, text: str, fonts: dict[str, str],
           opacity: float | None = None, tilt: float = 0.0) -> None:
    """Draw ``text`` at the slot's fraction of this page, shrinking to fit.

    ``opacity`` overrides :data:`ppu_spec.TEXT_OPACITY` for a sheet the office
    wants a shade fainter — ТРУД ППУ does. Left out, the ППУ pair's own
    strength is used, so nothing here changes for the ППУ itself.

    ``tilt`` turns the line by that many degrees about where it starts. The
    blanks are photographs of a screen and their own rows are never quite level;
    a value set dead flat across a page that leans reads as the crooked one.
    """
    if not text:
        return
    rect = page.rect
    size = slot.size * rect.height
    limit = slot.width * rect.width
    font = fitz.Font(fontfile=str(_font_file(slot.font)))
    while size > 4.0 and font.text_length(text, fontsize=size) > limit:
        size -= 0.4
    where = fitz.Point(slot.x * rect.width, slot.baseline * rect.height)
    morph = None
    if abs(tilt) > 0.05:
        # a positive tilt runs DOWN to the right, which in PDF's y-up space is a
        # negative rotation about the point the line starts at
        morph = (where, fitz.Matrix(-tilt))
    page.insert_text(where, text,
                     fontname=fonts[slot.font], fontsize=size,
                     color=slot.colour, morph=morph,
                     fill_opacity=TEXT_OPACITY if opacity is None else opacity)


def _place_photo(page, photo: bytes | None) -> None:
    """The worker in the window: background cut away, seven parts in ten."""
    if not photo:
        return
    rect = page.rect
    box = fitz.Rect(PHOTO_BOX[0] * rect.width, PHOTO_BOX[1] * rect.height,
                    PHOTO_BOX[2] * rect.width, PHOTO_BOX[3] * rect.height)
    aspect = (box.x1 - box.x0) / (box.y1 - box.y0)
    try:
        from src.services.photo_service import cutout_portrait

        stream = cutout_portrait(photo, aspect=aspect, opacity=PHOTO_OPACITY)
    except Exception as exc:                      # noqa: BLE001
        log.warning("ППУ: расм тайёрланмади (%s) — ўз ҳолича", exc)
        stream = photo
    if stream is None:
        stream = photo
    try:
        page.insert_image(box, stream=stream, keep_proportion=False, overlay=True)
    except Exception as exc:                      # noqa: BLE001
        # Anything at all: MuPDF raises its own error types for a file that is
        # not an image, and one unreadable photograph must cost the operator the
        # photograph, not the whole pair. It comes out without a picture and the
        # sheet is still usable.
        log.warning("ППУ: расм жойлашмади: %s", exc)


def _blanks(template: Path) -> tuple[Path, Path]:
    pages = tuple(Path(template) / name for name in PAGE_FILES)
    for page in pages:
        if not page.exists():
            raise FileNotFoundError(page)
    return pages


def render(data: PpuData, template: Path) -> bytes:
    """The filled pair as a two-page PDF: front, then back."""
    front_blank, back_blank = _blanks(template)
    out = fitz.open()
    out.insert_pdf(fitz.open(str(front_blank)))
    out.insert_pdf(fitz.open(str(back_blank)))

    _fill_front(out[0], data)
    _fill_back(out[1], data)
    log.info("ППУ: %s %s — %s, %s — %s", data.surname, data.name,
             passport_line(data.document),
             _dmy(data.valid_from), _dmy(data.valid_to))
    return out.tobytes()


def _fill_front(page, data: PpuData, opacity: float | None = None) -> None:
    """Fill the front sheet, on whatever blank the office uploaded.

    The slots in :mod:`src.pdf.ppu_spec` are in one reference frame; this blank
    is measured (:func:`src.pdf.blank_fit.fit_front`) and every slot mapped onto
    it. A blank framed like the reference maps to itself, so nothing moves for
    the templates that were already right.
    """
    from src.pdf.blank_fit import fit_front

    fonts = _fonts(page)
    # measure the blank BEFORE anything is laid on it, so nothing this run adds
    # can be mistaken for the sheet's own ink
    fit = fit_front(page)
    _place_photo(page, data.photo)
    cyrillic = full_name(data.surname, data.name, data.patronymic)
    latin = to_latin(cyrillic)
    citizenship = (data.citizenship or "").strip().upper()
    values = {
        "fio": cyrillic,
        "fio_latin": latin,
        "fio_latin_2": latin,
        "birth_date": _dmy(data.birth_date),
        "gender": (data.gender or "").strip(),
        "citizenship": citizenship,
        "citizenship_2": citizenship,
        "country": title_case(citizenship),
        "passport": passport_line(data.document),
    }
    for key, text in values.items():
        _write(page, _mapped(FRONT[key], fit), text, fonts, opacity)


def _mapped(slot: Slot, fit) -> Slot:
    """One slot, moved onto the blank that was actually uploaded.

    ``x`` is SHIFTED by however far this blank's value column is from the
    reference's, not set to it: «Иностранный паспорт» sits at its own indent and
    has to travel with the column rather than be dragged into it.
    """
    from src.pdf.ppu_spec import VALUE_X

    dx = 0.0 if fit.value_x is None else fit.value_x - VALUE_X
    return slot._replace(x=slot.x + dx,
                         baseline=fit.y(slot.baseline),
                         size=fit.size(slot.size))


def _fill_back(page, data: PpuData) -> None:
    fonts = _fonts(page)
    passport = passport_line(data.document)
    for key in ("passport_1", "passport_2", "passport_3", "passport_4"):
        _write(page, BACK[key], passport, fonts)
    _write(page, BACK["date_from"], _dmy(data.valid_from), fonts)
    _write(page, BACK["date_to"], _dmy(data.valid_to), fonts)
    # The address takes as many lines as it needs, and the BLOCK is centred on
    # the dates' own line rather than hung above or below it — a two-line
    # address and a three-line one then both read as level with «с … по …»,
    # which is how the office lines them up by hand.
    lines = address_lines(data.address or "")
    slot = BACK["address"]
    middle = (len(lines) - 1) / 2.0
    for index, line in enumerate(lines):
        offset = (index - middle) * ADDRESS_LEADING
        _write(page, slot._replace(baseline=slot.baseline + offset), line, fonts)


def pages_as_png(pdf: bytes, zoom: float = 3.0) -> list[bytes]:
    """The finished pair as pictures — which is how the office files them."""
    doc = fitz.open("pdf", pdf)
    out = []
    for page in doc:
        shot = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        out.append(shot.tobytes("png"))
    return out
