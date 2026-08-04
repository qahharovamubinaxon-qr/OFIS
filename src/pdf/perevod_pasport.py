"""The translation sheet as the office types it: a drawing of the document.

A notarial translation of a passport is not a list of «поле: значение» — it
is the data page itself, redrawn on white paper with every word in Russian:
the frame, the emblem, the (UZB) oval, the signature rule, the boxes with
their double labels, and «Машиносчитываемая запись» along the bottom. The
office handed over its own sheet as the pattern and asked for it 1:1, so
every number here was measured off that sheet and is a share of the page —
an A4 or anything else, it lands the same.

The same drawing serves an ID card: the frame and the labels are the same,
only the rows differ (:data:`ID_ROWS`).
"""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass, field

import fitz

from src.pdf.engine import _font_file, _fontname

# --------------------------------------------------------------- the faces
LABEL = "OfisArial"          # the small double labels and the headings
LABEL_BOLD = "OfisArialBold"
VALUE = "OfisSerif"          # what is typed into the boxes
SIGN = "OfisArialBoldItalic"

INK = (0.0, 0.0, 0.0)
RULE = 0.9                   # line thickness in points

# ------------------------------------------------------------ the heading
HEAD_X, HEAD_Y, HEAD_SIZE = 0.4850, 0.1137, 0.0127
COUNTRY_X, COUNTRY_Y = 0.3590, 0.1333
TITLE_Y = 0.1470
HEAD_SMALL = 0.0117

# ---------------------------------------------------------------- the box
BOX = (0.1663, 0.1533, 0.8004, 0.7903)

#: The emblem's window at the top of the box.
EMBLEM = (0.2700, 0.1640, 0.6930, 0.2205)
#: The state's name, in the type the passport prints it in.
BIG_COUNTRY_Y, BIG_COUNTRY_SIZE = 0.2489, 0.0186
#: The oval with the country code in it.
OVAL = (0.4700, 0.3250, 0.5170, 0.3430)
OVAL_SIZE = 0.0100
#: «(подпись)» over the rule the holder signs on.
SIGN_Y, SIGN_SIZE = 0.4287, 0.0147
SIGN_RULE = (0.2150, 0.4360, 0.7410)
SIGN_LABEL_Y = 0.4507

#: The rules that divide the box, top to bottom.
DIV_STATE = 0.4640           # under «подпись владельца»
DIV_HEAD = 0.4900            # under «РЕСПУБЛИКА .../РЕСПУБЛИКА ...»
DIV_ROW = 0.5390             # under тип / код / номер
DIV_MRZ = 0.7569             # over «Машиносчитываемая запись»

STATE_LINE_Y, STATE_LINE_SIZE = 0.4777, 0.0122

#: The тип / код страны / номер паспорта row.
COL_KIND, COL_CODE, COL_NUMBER = 0.3155, 0.3845, 0.5540
ROW_LABEL_Y, ROW_VALUE_Y = 0.5030, 0.5265
ROW_LABEL_SIZE, ROW_VALUE_SIZE = 0.0074, 0.0147
#: «ПАСПОРТ/» «ПАСПОРТ» in the leftmost column, on two lines.
KIND_X, KIND_Y1, KIND_Y2 = 0.1960, 0.5075, 0.5185

#: The photograph's window.
PHOTO = (0.1788, 0.5537, 0.3098, 0.7496)
PHOTO_LABEL_SIZE = 0.0083

#: Where the worker's own values are typed.
DATA_X = 0.3290
LABEL_SIZE, VALUE_SIZE = 0.0074, 0.0147
#: (label baseline, value baseline) of every row, measured off the sheet.
ROWS: tuple[tuple[str, str, float, float], ...] = (
    ("ФАМИЛИЯ/ФАМИЛИЯ", "surname", 0.5439, 0.5610),
    ("ИМЯ/ИМЯ", "name", 0.5723, 0.5880),
    ("ОТЧЕСТВО/ОТЧЕСТВО", "patronymic", 0.5990, 0.6150),
    ("ГРАЖДАНСТВО/ГРАЖДАНСТВО", "citizenship", 0.6262, 0.6418),
    ("ДАТА РОЖДЕНИЯ/ДАТАРОЖДЕНИЯ", "birth_date", 0.6526, 0.6688),
    ("ПОЛ/ПОЛ", "sex", 0.6796, 0.6957),
    ("ДАТА ВЫДАЧИ / ДАТА ВЫДАЧИ", "issue_date", 0.7065, 0.7227),
    ("ДЕЙСТВИТЕЛЕН ДО/ДЕЙСТВИТЕЛЕН ДО", "expiry_date", 0.7334, 0.7496),
)

#: An ID card carries a personal number a passport does not, so its rows are
#: one more and sit a little closer together — between the same two rules.
ID_EXTRA = ("ПИНФЛ/ПИНФЛ", "personal_number")
VALUE_GAP = 0.0160

#: «Место рождения» shares its line with «Пол», wherever that line ends up.
PLACE_X = 0.4400
#: «Орган, выдавший документ» — two label lines and the value under them,
#: measured from the LAST row's own baselines so the block follows the grid.
ORGAN_X, ORGAN_VALUE_X = 0.6000, 0.6300
ORGAN_LIFT1, ORGAN_LIFT2, ORGAN_VALUE_LIFT = 0.0134, 0.0039, 0.0016

MRZ_Y, MRZ_SIZE = 0.7766, 0.0152
MRZ_TEXT = "«««««« Машиносчитываемая запись »»»»»»"

#: «НОМЕР ПАСПОРТА» — the document's name in the genitive, as the box wants it.
_OF: dict[str, str] = {
    "ПАСПОРТ": "ПАСПОРТА",
    "ID-КАРТА": "ID-КАРТЫ",
    "ID КАРТА": "ID-КАРТЫ",
    "УДОСТОВЕРЕНИЕ ЛИЧНОСТИ": "УДОСТОВЕРЕНИЯ ЛИЧНОСТИ",
    "БИОМЕТРИЧЕСКИЙ ПАСПОРТ": "ПАСПОРТА",
}


def number_label(title: str) -> str:
    """«ПАСПОРТ» → «НОМЕР ПАСПОРТА»; anything else → «НОМЕР ДОКУМЕНТА»."""
    return f"НОМЕР {_OF.get((title or '').upper(), 'ДОКУМЕНТА')}"

#: The punched number down the right-hand side of the page. It is drawn in
#: outline, not solid — on the passport itself it is punched through the
#: paper, and the office's sheet shows it as hollow figures.
PERF_X, PERF_TOP, PERF_SIZE = 0.7620, 0.2150, 0.0320
PERF_STROKE = 0.03


@dataclass
class Facsimile:
    """Everything the drawn sheet needs, already in Russian."""

    lang: str = "узбекского"
    country: str = "РЕСПУБЛИКА УЗБЕКИСТАН"
    title: str = "ПАСПОРТ"
    code: str = "UZB"
    kind: str = "P"
    number: str = ""
    surname: str = ""
    name: str = ""
    patronymic: str = ""
    citizenship: str = ""
    birth_date: str = ""
    sex: str = ""
    birth_place: str = ""
    issue_date: str = ""
    expiry_date: str = ""
    authority: str = ""
    personal_number: str = ""
    #: visas, stamps and the translator's notes — set UNDER the frame, so the
    #: drawing itself stays exactly the office's own sheet
    stamps: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    #: the state emblem the office uploaded once
    emblem: bytes | None = field(default=None, repr=False)

    def is_card(self) -> bool:
        return bool(self.personal_number)

    def value(self, key: str) -> str:
        return str(getattr(self, key, "") or "")


#: Which box of the drawing each field the reader hands back belongs in.
#: Longest first, so «дата рождения» never lands in «дата выдачи».
_WHERE: tuple[tuple[str, str], ...] = (
    ("дата рождения", "birth_date"), ("место рождения", "birth_place"),
    ("дата выдачи", "issue_date"),
    ("действителен", "expiry_date"), ("окончания срока", "expiry_date"),
    ("срок действия", "expiry_date"),
    ("орган", "authority"), ("кем выдан", "authority"),
    ("персональный номер", "personal_number"), ("пинфл", "personal_number"),
    ("пин", "personal_number"),
    ("номер паспорта", "number"), ("номер документа", "number"),
    ("серия и номер", "number"), ("номер", "number"),
    ("фамилия", "surname"), ("отчество", "patronymic"), ("имя", "name"),
    ("гражданство", "citizenship"), ("пол", "sex"),
    ("код государства", "code"), ("код страны", "code"), ("тип", "kind"),
)

_SEX = {"женский": "Ж", "жен": "Ж", "ж": "Ж", "f": "Ж", "female": "Ж",
        "мужской": "М", "муж": "М", "м": "М", "m": "М", "male": "М"}


def _slot_of(label: str) -> str:
    low = " ".join(str(label or "").split()).lower().strip(" .:")
    for needle, key in _WHERE:
        if needle in low:
            return key
    return ""


def from_fields(fields: list[dict], *, lang: str, country: str,
                title: str, stamps: list[str] | None = None,
                notes: list[str] | None = None,
                emblem: bytes | None = None) -> Facsimile:
    """The drawn sheet's values, out of what the reader returned."""
    made = Facsimile(lang=lang or "иностранного",
                     country=(country or "").upper() or "РЕСПУБЛИКА",
                     title=(title or "ПАСПОРТ").upper(),
                     stamps=list(stamps or ()), notes=list(notes or ()),
                     emblem=emblem)
    for item in fields:
        key = _slot_of(item.get("label", ""))
        value = " ".join(str(item.get("value", "") or "").split())
        if not key or not value or getattr(made, key):
            continue
        if key == "sex":
            value = _SEX.get(value.lower(), value.upper()[:1])
        elif key in ("surname", "name", "patronymic", "citizenship",
                     "birth_place", "authority"):
            value = value.upper()
        setattr(made, key, value)
    if not made.kind:
        made.kind = "I" if made.personal_number else "P"
    return made


def rows_of(data: Facsimile) -> list[tuple[str, str, float, float]]:
    """The rows of this document, each with its label and value baselines.

    A passport keeps the baselines measured off the office's own sheet. A
    card has one row more, so the same space is shared out evenly between
    the first and the last of them — the block never grows past its rule.
    """
    if not data.is_card():
        return list(ROWS)
    labels = [(label, key) for label, key, _, _ in ROWS] + [ID_EXTRA]
    top, bottom = ROWS[0][2], ROWS[-1][2]
    pitch = (bottom - top) / (len(labels) - 1)
    return [(label, key, top + i * pitch, top + i * pitch + VALUE_GAP)
            for i, (label, key) in enumerate(labels)]


def is_drawable(data: Facsimile) -> bool:
    """Whether there is enough to draw the document rather than list it."""
    return bool(data.surname and (data.number or data.birth_date))


def _text(page, x: float, y: float, text: str, size: float, family: str,
          *, centre_in: tuple[float, float] | None = None,
          opacity: float = 1.0) -> None:
    """One line, placed by shares of the page."""
    if not text:
        return
    width, height = page.rect.width, page.rect.height
    points = size * height
    if centre_in is not None:
        font = fitz.Font(fontfile=str(_font_file(family)))
        span = font.text_length(text, fontsize=points)
        left, right = centre_in
        x = (left + right) / 2 - span / (2 * width)
    page.insert_text((x * width, y * height), text, fontsize=points,
                     fontfile=str(_font_file(family)),
                     fontname=_fontname(family), color=INK,
                     fill_opacity=opacity)


def _line(page, x0: float, y0: float, x1: float, y1: float) -> None:
    width, height = page.rect.width, page.rect.height
    page.draw_line((x0 * width, y0 * height), (x1 * width, y1 * height),
                   color=INK, width=RULE)


def _rect(page, box: tuple[float, float, float, float]) -> None:
    width, height = page.rect.width, page.rect.height
    page.draw_rect(fitz.Rect(box[0] * width, box[1] * height,
                             box[2] * width, box[3] * height),
                   color=INK, width=RULE)


#: Where stamps and notes start under the frame, and how they are set.
UNDER_Y, UNDER_SIZE, UNDER_LEAD = 0.8130, 0.0110, 1.45


def _under_frame(page, data: Facsimile) -> None:
    """Visas, stamps and notes — under the drawing, never inside it."""
    lines: list[str] = []
    if data.stamps:
        lines.append("Печати и штампы:")
        lines += [" ".join(str(s).split()) for s in data.stamps if str(s).strip()]
    lines += [f"Примечание переводчика: {' '.join(str(n).split())}"
              for n in data.notes if str(n).strip()]
    if not lines:
        return
    width, height = page.rect.width, page.rect.height
    font = fitz.Font(fontfile=str(_font_file(VALUE)))
    points = UNDER_SIZE * height
    room = (BOX[2] - BOX[0]) * width
    y = UNDER_Y
    for line in lines:
        for row in _wrap(line, font, points, room) or [""]:
            if y > 0.97:
                return
            _text(page, BOX[0], y, row, UNDER_SIZE, VALUE)
            y += UNDER_SIZE * UNDER_LEAD


def _wrap(text: str, font, points: float, room: float) -> list[str]:
    rows: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and font.text_length(candidate, fontsize=points) > room:
            rows.append(current)
            current = word
        else:
            current = candidate
    if current:
        rows.append(current)
    return rows


def draw(page, data: Facsimile) -> None:
    """The whole sheet, drawn onto ``page`` exactly as the office types it."""
    width, height = page.rect.width, page.rect.height
    left, top, right, bottom = BOX
    rows = rows_of(data)
    last_label, last_value = rows[-1][2], rows[-1][3]
    organ_y1 = last_label - ORGAN_LIFT1
    organ_y2 = last_label - ORGAN_LIFT2
    organ_value_y = last_value - ORGAN_VALUE_LIFT
    place_label_y, place_value_y = next(
        (label_y, value_y) for _l, key, label_y, value_y in rows
        if key == "sex")

    # ---- what stands above the frame
    _text(page, HEAD_X, HEAD_Y, f"Перевод ксерокопии с  {data.lang} языка",
          HEAD_SIZE, LABEL)
    _text(page, COUNTRY_X, COUNTRY_Y, data.country, HEAD_SMALL, LABEL)
    _text(page, COUNTRY_X, TITLE_Y, data.title, HEAD_SMALL, LABEL)

    # ---- the frame and its rules
    _rect(page, BOX)
    for y in (DIV_STATE, DIV_HEAD, DIV_ROW, DIV_MRZ):
        _line(page, left, y, right, y)
    for x in (COL_KIND, COL_CODE, COL_NUMBER):
        _line(page, x, DIV_HEAD, x, DIV_ROW)
    _line(page, COL_KIND, DIV_ROW, COL_KIND, DIV_MRZ)
    _line(page, ORGAN_X, organ_y1 - 0.012, ORGAN_X, DIV_MRZ)

    # ---- the upper half: emblem, state, code, signature
    if data.emblem:
        with suppress(RuntimeError, ValueError):
            page.insert_image(
                fitz.Rect(EMBLEM[0] * width, EMBLEM[1] * height,
                          EMBLEM[2] * width, EMBLEM[3] * height),
                stream=data.emblem, keep_proportion=True)
    _text(page, 0.0, BIG_COUNTRY_Y, data.country, BIG_COUNTRY_SIZE, LABEL_BOLD,
          centre_in=(left, right))
    page.draw_oval(fitz.Rect(OVAL[0] * width, OVAL[1] * height,
                             OVAL[2] * width, OVAL[3] * height),
                   color=INK, width=RULE)
    page.draw_oval(fitz.Rect((OVAL[0] - 0.006) * width, (OVAL[1] - 0.003) * height,
                             (OVAL[2] + 0.006) * width, (OVAL[3] + 0.003) * height),
                   color=INK, width=RULE)
    _text(page, 0.0, OVAL[3] - 0.005, data.code, OVAL_SIZE, LABEL_BOLD,
          centre_in=(OVAL[0], OVAL[2]))
    _text(page, 0.0, SIGN_Y, "(подпись)", SIGN_SIZE, SIGN,
          centre_in=(left, right))
    _line(page, SIGN_RULE[0], SIGN_RULE[1], SIGN_RULE[2], SIGN_RULE[1])
    _text(page, 0.0, SIGN_LABEL_Y, "подпись владельца", HEAD_SMALL, LABEL,
          centre_in=(left, right))
    _text(page, 0.0, STATE_LINE_Y, f"{data.country}/{data.country}",
          STATE_LINE_SIZE, LABEL, centre_in=(left, right))

    # ---- тип / код страны / номер
    _text(page, KIND_X, KIND_Y1, f"{data.title}/", PHOTO_LABEL_SIZE, LABEL)
    _text(page, KIND_X, KIND_Y2, data.title, PHOTO_LABEL_SIZE, LABEL)
    columns = ((COL_KIND, COL_CODE, "ТИП/ТИП", data.kind),
               (COL_CODE, COL_NUMBER, "КОД СТРАНЫ/ КОДСТРАНЫ", data.code),
               (COL_NUMBER, right,
                f"{number_label(data.title)}/{number_label(data.title)}",
                data.number))
    for col_left, col_right, label, value in columns:
        _text(page, 0.0, ROW_LABEL_Y, label, ROW_LABEL_SIZE, LABEL,
              centre_in=(col_left, col_right))
        _text(page, 0.0, ROW_VALUE_Y, value, ROW_VALUE_SIZE, VALUE,
              centre_in=(col_left, col_right))

    # ---- the photograph's window
    _rect(page, PHOTO)
    _text(page, 0.0, 0.6390, "Личная", PHOTO_LABEL_SIZE, LABEL_BOLD,
          centre_in=(PHOTO[0], PHOTO[2]))
    _text(page, 0.0, 0.6500, "Фотография", PHOTO_LABEL_SIZE, LABEL_BOLD,
          centre_in=(PHOTO[0], PHOTO[2]))

    # ---- the worker's own values
    for label, key, label_y, value_y in rows:
        _text(page, DATA_X, label_y, label, LABEL_SIZE, LABEL)
        _text(page, DATA_X, value_y, data.value(key), VALUE_SIZE, VALUE)
    _text(page, PLACE_X, place_label_y, "МЕСТО РОЖДЕНИЯ / МЕСТО РОЖДЕНИЯ",
          LABEL_SIZE, LABEL)
    _text(page, PLACE_X, place_value_y, data.birth_place, VALUE_SIZE, VALUE)
    _text(page, ORGAN_X, organ_y1, "ОРГАН, ВЫДАВШИЙ ДОКУМЕНТ /", LABEL_SIZE,
          LABEL)
    _text(page, ORGAN_X, organ_y2, "ОРГАН, ВЫДАВШИЙ ДОКУМЕНТ", LABEL_SIZE,
          LABEL)
    _text(page, ORGAN_VALUE_X, organ_value_y, data.authority, VALUE_SIZE,
          VALUE)

    # ---- the machine-readable zone, named rather than copied
    _text(page, 0.0, MRZ_Y, MRZ_TEXT, MRZ_SIZE, LABEL, centre_in=(left, right))

    # ---- what the frame has no box for: visas, stamps, the reader's notes
    _under_frame(page, data)

    # ---- the punched number down the side, outlined the way it is punched
    if data.number:
        page.insert_text((PERF_X * width, PERF_TOP * height), data.number,
                         fontsize=PERF_SIZE * height, rotate=270,
                         fontfile=str(_font_file("OfisMono")),
                         fontname=_fontname("OfisMono"), color=INK,
                         render_mode=1, border_width=PERF_STROKE)
