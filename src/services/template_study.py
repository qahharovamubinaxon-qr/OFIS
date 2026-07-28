"""Working out where a document wants each value written.

The office uploads a form nobody has taught the program about — a PDF or a Word
file — and this finds the places a worker's data goes. Three ways, cheapest and
surest first:

1. **AcroForm.** A PDF with real form fields already says where everything goes
   and what each box is called. Nothing to guess: the field names are matched to
   what the office knows about a worker.
2. **Word.** Paragraphs and table cells carry the label and the gap beside it, so
   the map is the label's position in the document, not a coordinate.
3. **A flat PDF.** Every word and its rectangle are pulled out, the labels are
   recognised from the words themselves, and the writing spot is the run of
   underscores or the empty space that follows each one. The AI chain is asked
   only about the labels it cannot place — never about geometry, which is
   measured here.

Whatever comes out is shown to the operator before it is used: a map that was
guessed wrong is corrected or deleted on screen, and only then saved as that
template's profile, so the same file is never studied twice.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from src.common.errors import ValidationError
from src.common.logging import get_logger

log = get_logger(__name__)

PDF_FORM, PDF_FLAT, DOCX = "pdf_form", "pdf_flat", "docx"

#: What the office can put on a document, and how each one is asked for. The
#: labels are the ones these forms actually print — Russian, in the wording
#: Госуслуги and the МВД use.
FIELDS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("fio", "Ф.И.О.",
     ("ф.и.о", "фио", "фамилия, имя, отчество", "полное имя", "fio", "full name")),
    ("surname", "Фамилия", ("фамилия", "surname", "lastname", "last name")),
    ("name", "Имя", ("имя", "firstname", "first name")),
    ("patronymic", "Отчество", ("отчество", "patronymic", "middle name")),
    ("birth_date", "Дата рождения",
     ("дата рождения", "год рождения", "birth date", "birthdate", "birth_date")),
    ("birth_place", "Место рождения", ("место рождения", "birth place")),
    ("gender", "Пол", ("пол", "gender", "sex")),
    ("citizenship", "Гражданство",
     ("гражданство", "подданство", "citizenship", "nationality")),
    ("passport_series", "Паспорт: серия", ("серия",)),
    ("passport_number", "Паспорт: номер", ("номер",)),
    ("passport_issue", "Паспорт: дата выдачи", ("дата выдачи",)),
    ("passport_issued_by", "Паспорт: кем выдан", ("кем выдан", "кем выдано")),
    ("passport_expiry", "Паспорт: срок действия", ("срок действия",)),
    ("patent_series", "Патент: серия", ("серия патента",)),
    ("patent_number", "Патент: номер", ("номер патента",)),
    ("patent_issue", "Патент: дата выдачи", ("дата выдачи патента",)),
    ("profession", "Профессия / должность",
     ("профессия", "должность", "специальность", "profession", "position")),
    ("address", "Адрес", ("адрес",)),
    ("phone", "Телефон", ("телефон",)),
    ("inn", "ИНН", ("инн",)),
    ("date", "Дата документа", ("дата", "дата составления")),
)

LABELS = {key: label for key, label, _a in FIELDS}
#: alias → field key, longest alias first so «серия патента» beats «серия»
_ALIASES: tuple[tuple[str, str], ...] = tuple(sorted(
    ((alias, key) for key, _label, aliases in FIELDS for alias in aliases),
    key=lambda pair: -len(pair[0])))

_UNDERSCORE = re.compile(r"_{3,}")
_GAP_MIN = 28.0          # a writing space narrower than this is not one
_LINE_TOLERANCE = 3.0    # words within this many points share a line


@dataclass
class Spot:
    """One place a value goes, in whichever way its document addresses it."""

    key: str                    # fio, birth_date, …
    label: str                  # what the document calls it
    page: int = 1               # PDF only, 1-based
    rect: tuple[float, float, float, float] | None = None   # PDF only
    widget: str = ""            # AcroForm field name
    paragraph: int = -1         # Word: index into the flattened paragraph list
    cell: tuple[int, int, int] | None = None   # Word: table, row, column
    confirmed: bool = False     # the operator has looked at it

    def describe(self) -> str:
        if self.widget:
            return f"AcroForm «{self.widget}»"
        if self.cell is not None:
            table, row, column = self.cell
            return f"жадвал {table + 1}, қатор {row + 1}, устун {column + 1}"
        if self.paragraph >= 0:
            return f"абзац {self.paragraph + 1}"
        if self.rect:
            return f"бет {self.page}, x={self.rect[0]:.0f} y={self.rect[1]:.0f}"
        return "—"


@dataclass
class Study:
    """The map of one template, as found and then as the operator left it."""

    kind: str
    source: str
    pages: int = 0
    spots: list[Spot] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.spots)

    def to_json(self) -> dict:
        return {"kind": self.kind, "source": self.source, "pages": self.pages,
                "spots": [asdict(s) for s in self.spots], "notes": self.notes}

    @staticmethod
    def from_json(data: dict) -> "Study":
        return Study(kind=data["kind"], source=data.get("source", ""),
                     pages=int(data.get("pages", 0)),
                     spots=[Spot(**s) for s in data.get("spots", [])],
                     notes=list(data.get("notes", [])))


# ------------------------------------------------------------------ labels


def match_label(text: str) -> str | None:
    """Which of the office's fields a printed label is asking for."""
    low = " ".join((text or "").lower().split()).strip(" :№.-")
    if not low:
        return None
    for alias, key in _ALIASES:
        if low == alias or low.startswith(alias + " ") or low.endswith(" " + alias):
            return key
    for alias, key in _ALIASES:
        # whole words only: «пол» must not be found inside «полей»
        if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", low):
            return key
    return None


# --------------------------------------------------------------- AcroForm


def _acroform(doc, source: Path) -> Study | None:
    """A PDF that already has form fields tells us everything itself."""
    study = Study(kind=PDF_FORM, source=str(source), pages=len(doc))
    for number, page in enumerate(doc, start=1):
        for widget in page.widgets() or []:
            key = match_label(widget.field_name or "") or match_label(
                widget.field_label or "")
            if key is None:
                continue
            study.spots.append(Spot(key=key, label=LABELS[key], page=number,
                                    rect=tuple(widget.rect),
                                    widget=widget.field_name or ""))
    return study if study.spots else None


# -------------------------------------------------------------- a flat PDF


def _words(page) -> list[tuple[float, float, float, float, str]]:
    return [(w[0], w[1], w[2], w[3], w[4]) for w in page.get_text("words")]


def _lines(page) -> list[list[tuple]]:
    """Words grouped into the lines the eye sees."""
    out: list[list[tuple]] = []
    for word in sorted(_words(page), key=lambda w: (round(w[1], 1), w[0])):
        if out and abs(out[-1][0][1] - word[1]) <= _LINE_TOLERANCE:
            out[-1].append(word)
        else:
            out.append([word])
    return out


def _writing_spot(line: list[tuple], after: int, page_width: float):
    """Where the value goes: the underscores or the empty room after a label."""
    import fitz

    tail = line[after + 1:]
    # Only the underscores that come *straight* after this label. Taking the
    # last run on the line instead swallowed the next label with it — «Серия
    # ____ Номер ____» erased the word «Номер».
    underscores: list[tuple] = []
    for word in tail:
        if _UNDERSCORE.fullmatch(word[4]):
            underscores.append(word)
        elif underscores:
            break
        else:
            break
    if underscores:
        first, last = underscores[0], underscores[-1]
        return fitz.Rect(first[0], first[1], last[2], last[3])

    # No underscores. Room to the right counts as a writing space only when
    # this label is the whole line, or the line ends with it after a colon —
    # otherwise «Фамилия Имя Отчество Гражданство» is a header row and the
    # value would be written into blank paper beside it.
    label_text = " ".join(w[4] for w in line[:after + 1])
    alone = after == len(line) - 1 and (
        line[0] is line[after] or label_text.rstrip().endswith(":"))
    if not alone:
        return None
    left = line[after][2] + 2.0
    right = min(page_width - 40.0, left + 260.0)
    if right - left < _GAP_MIN:
        return None
    top, bottom = line[after][1], line[after][3]
    return fitz.Rect(left, top, right, bottom)


def _flat_pdf(doc, source: Path) -> Study:
    """Read the labels off the page and measure the gap beside each one."""
    study = Study(kind=PDF_FLAT, source=str(source), pages=len(doc))
    seen: set[str] = set()
    for number, page in enumerate(doc, start=1):
        for line in _lines(page):
            for index in range(len(line)):
                for span in (3, 2, 1):          # «дата выдачи патента» first
                    if index + span > len(line):
                        continue
                    words = line[index:index + span]
                    # A label is words, not the gap after it: joining «Серия»
                    # with the underscores that follow made the rule swallow
                    # them and put the value one field to the right.
                    if any(_UNDERSCORE.fullmatch(w[4]) for w in words):
                        continue
                    phrase = " ".join(w[4] for w in words)
                    key = match_label(phrase)
                    if key is None or key in seen:
                        continue
                    rect = _writing_spot(line, index + span - 1, page.rect.width)
                    if rect is None:
                        continue
                    seen.add(key)
                    study.spots.append(Spot(key=key, label=LABELS[key],
                                            page=number, rect=tuple(rect)))
                    break
    return study


# ------------------------------------------------------------------- Word


def _docx(source: Path) -> Study:
    """Labels in paragraphs and in table cells, with the gap beside each."""
    import docx

    from src.services.docx_worker import iter_paragraphs

    document = docx.Document(str(source))
    study = Study(kind=DOCX, source=str(source))
    seen: set[str] = set()

    # Tables first: a cell address is more exact than a paragraph index, and
    # ``iter_paragraphs`` walks into cells too — so the loose pass would
    # otherwise claim a label that a table already places precisely.
    for t, table in enumerate(document.tables):
        for r, row in enumerate(table.rows):
            cells = list(row.cells)
            for c, cell in enumerate(cells):
                key = match_label(cell.text)
                if key is None or key in seen:
                    continue
                # the value lives in this cell after the label, or in the next
                target = (t, r, c + 1) if c + 1 < len(cells) else (t, r, c)
                seen.add(key)
                study.spots.append(Spot(key=key, label=LABELS[key], cell=target))

    for index, paragraph in enumerate(iter_paragraphs(document)):
        text = " ".join(paragraph.text.split())
        if not text:
            continue
        key = match_label(text)
        if key and key not in seen:
            seen.add(key)
            study.spots.append(Spot(key=key, label=LABELS[key], paragraph=index))
    return study


# ------------------------------------------------------------------ public


def study(source: Path) -> Study:
    """Work out where this template wants each value. Never guesses geometry."""
    if not source.exists():
        raise ValidationError("Файл топилмади", context={"path": str(source)})
    suffix = source.suffix.lower()
    if suffix == ".docx":
        result = _docx(source)
    elif suffix == ".pdf":
        import fitz

        try:
            doc = fitz.open(str(source))
        except Exception as exc:  # noqa: BLE001 - not a PDF
            raise ValidationError("PDF ўқилмади",
                                  context={"path": str(source)}) from exc
        try:
            result = _acroform(doc, source) or _flat_pdf(doc, source)
        finally:
            doc.close()
    else:
        raise ValidationError("Фақат PDF ёки Word (.docx) бўлади",
                              context={"suffix": suffix})

    if not result.spots:
        result.notes.append(
            "Ҳеч қандай майдон топилмади — жойларни қўлда белгилашингиз керак")
    log.info("Studied %s (%s): %d spots", source.name, result.kind,
             len(result.spots))
    return result
