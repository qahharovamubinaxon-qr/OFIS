"""Putting a car and its drivers into any insurer's ОСАГО policy template.

Every insurer lays the policy out differently — Ингосстрах, РЕСО and Согласие
share almost no wording — but the form itself is set by the Bank of Russia, so
the *labels* are the same everywhere: «Марка, модель транспортного средства»,
«Идентификационный номер», «Государственный регистрационный знак», «Срок
страхования с … по …», and the table of «Лица, допущенные к управлению».

So the previous customer is swapped out the way the previous worker is in
:mod:`src.services.docx_worker`: by those labels, keeping each value's own font.
Some insurers print a value one character per table cell (a VIN, a date) — that
is handled too.

What this module will never do
------------------------------
* **invent a policy серия/номер.** РСА allocates those to the agency through the
  insurer; the operator records the block they were given and the program hands
  them out in order (same rule as ДМС). A made-up number is a policy that covers
  nobody.
* **write or carry over an electronic signature.** The certificate, the МЧД and
  the доверенность number belong to the insurer's signing system. The previous
  policy's are *erased* — leaving them would make an unsigned document look
  signed, which is exactly what the templates themselves warn about.
* **invent КБМ or the premium.** Those come from the РСА database and the
  insurer's calculation; whatever the operator did not supply is left blank.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from src.common.logging import get_logger
from src.services.docx_worker import (
    iter_paragraphs,
    replace_span,
    runs_of,
    text_of,
)

log = get_logger(__name__)

# --------------------------------------------------------------- the labels

#: key · label · whether a colon is required before the value.
#:
#: «Страхователь» needs one. Without it the word also opens the signature line
#: «Страхователь        Представитель страховщика», and writing there replaced
#: the form's own wording with a company name.
_SLOTS: tuple[tuple[str, str, bool], ...] = (
    ("vehicle", r"Марка,?\s*модель\s+транспортного\s+средства", False),
    ("vin", r"Идентификационный\s+номер\s+транспортного\s+средства|"
            r"Идентификационный\s+номер\s*\(VIN\)|Идентификационный\s+номер", False),
    ("plate", r"Государственный\s+регистрационный\s+(?:знак|номер)"
              r"(?:\s+транспортного\s+средства)?", False),
    ("sts", r"Свидетельство\s+о\s+регистрации(?:\s+ТС)?", False),
    ("policy_holder", r"(?:\d\.\s*)?Страхователь(?!\w)", True),
    # «Страхователем <ФИО> при получении настоящего страхового полиса…» on the
    # back of the policy — a sentence, so the name is always right after it
    ("policy_holder", r"(?:\d\.\s*)?Страхователем(?!\w)", False),
    ("owner", r"Собственник\s+транспортного\s+средства", True),
)
_LABELS = re.compile("|".join(f"(?P<g{i}>{p})" for i, (_k, p, _c) in enumerate(_SLOTS)))
_SEPARATOR = " "

#: Everything after a label that is the form's own small print, not a value.
_NOTE = re.compile(r"^\s*\(?\s*(?:полное наименование|фамилия|серия|номер|"
                   r"отметить|заполняется|указывается|при наличии)", re.IGNORECASE)

#: «неограниченного количества лиц…» / «лиц, допущенных…» — the one choice the
#: operator makes that changes what the policy means.
#: The mark goes after the WHOLE option, not after the first few words of it —
#: putting it after «…к управлению» landed it in the middle of the sentence and
#: left the real box untouched.
_OPTION_TAIL = r"лиц,?\s*допущенн\w+\s+к\s+управлению\s+транспортным\s+средством\s*\d*"
_UNLIMITED = re.compile(r"неограниченн\w*\s+количеств\w*\s+" + _OPTION_TAIL,
                        re.IGNORECASE)
_LIMITED = re.compile(r"(?<!количества\s)(?<!\w)" + _OPTION_TAIL, re.IGNORECASE)
_TICKS = ("X", "Х", "[X]", "[Х]", "[x]", "[х]", "V", "✔", "✓")
_EMPTY_TICK = ("[ ]", "[]", "□", "")

#: An electronic signature belongs to the insurer, never to this program.
_SIGNATURE = re.compile(
    r"подписан\w*\s+(?:электронной|с использованием|усиленной)|"
    r"электронно[-\s]?цифровой\s+подпис|"
    r"удостоверяющий\s+центр|сертификат\s+[0-9A-F]|"
    r"мчд\s*№|доверенность\s*№|действительн\w*\s+до:", re.IGNORECASE)

_DASH = "—"


@dataclass
class Report:
    filled: dict[str, str] = field(default_factory=dict)
    drivers: int = 0
    cleared: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ helpers


def _hits(text: str, values: dict[str, str]) -> list[tuple[str, int, int]]:
    """Every label on a line that this fill has a value for, with its span."""
    out: list[tuple[str, int, int]] = []
    for m in _LABELS.finditer(text):
        idx = next(i for i in range(len(_SLOTS)) if m.group(f"g{i}") is not None)
        key, _pattern, needs_colon = _SLOTS[idx]
        if key not in values:
            continue
        span = _value_span(text, m.start(), m.end(), needs_colon=needs_colon)
        if span is not None:
            out.append((key, *span))
    return out


def _value_span(text: str, start: int, end: int, *,
                needs_colon: bool) -> tuple[int, int] | None:
    """Where the value beside a label at [start, end) sits on the same line.

    ``None`` when what follows is the form's own bracketed explanation rather
    than a value — «Страхователь (полное наименование юридического лица…)» —
    or when a label that demands a colon does not have one.
    """
    rest = text[end:]
    if _NOTE.match(rest):
        return None
    if needs_colon and not re.match(r"\s*:", rest):
        return None
    lead = re.match(r"[\s:№]*", rest)
    value_start = end + len(lead.group(0) if lead else "")
    stop = len(text)
    nxt = _LABELS.search(text, value_start)
    if nxt:
        stop = nxt.start()
    bracket = rest.find("(")
    if bracket >= 0 and end + bracket < stop:
        stop = end + bracket
    return value_start, value_start + len(text[value_start:stop].rstrip())


def _cells(row) -> list:
    """A table row's cells, with merged repeats collapsed."""
    out, seen = [], set()
    for cell in row.cells:
        key = id(cell._tc)
        if key in seen:
            continue
        seen.add(key)
        out.append(cell)
    return out


def _set_cell(cell, value: str) -> None:
    """Write a cell, keeping the first run's formatting."""
    paragraph = cell.paragraphs[0]
    runs = runs_of(paragraph)
    text = text_of(runs)
    if runs:
        replace_span(runs, 0, len(text), value)
    else:
        paragraph.add_run(value)
    for extra in cell.paragraphs[1:]:
        for run in runs_of(extra):
            run.text = ""


def _spread(cells: list, value: str) -> bool:
    """Write one character per cell, the way a VIN grid wants it.

    Only when the row really is a grid: a run of cells each holding at most one
    character. Returns False so the caller can fall back to a plain write.
    """
    grid = [c for c in cells if len(c.text.strip()) <= 1]
    if len(grid) < 6 or len(grid) < len(value) * 0.8:
        return False
    for cell, char in zip(grid, value.ljust(len(grid))):
        _set_cell(cell, char.strip())
    return True


# ------------------------------------------------------------------- values


def _paragraph_values(doc, values: dict[str, str], report: Report) -> None:
    """Replace a value that sits beside its label on the same line.

    A label with nothing after it is a column *heading* — every insurer has
    those, and the value belongs to some cell or line further on that only the
    layout knows about. Those are left to :func:`_by_pattern`, which finds the
    previous customer's data by its shape instead of by its label.
    """
    lines = [(p, r, text_of(r)) for p in iter_paragraphs(doc)
             if (r := runs_of(p)) and text_of(r).strip()]
    replaced: list[tuple[str, str]] = []
    for i, (_p, runs, text) in enumerate(lines):
        for key, lo, hi in reversed(_hits(text, values)):     # right to left
            old = text[lo:hi]
            if old.strip():
                replace_span(runs, lo, hi, values[key])
                report.filled[key] = values[key]
                if key in ("policy_holder", "owner"):
                    replaced.append((old.strip(), values[key]))
                continue
            if key not in ("policy_holder", "owner"):
                continue
            # «Собственник транспортного средства:» with the name a line or two
            # below, the notes about what to write in between
            below = _below(lines, i)
            if below is None:
                report.skipped.append(key)
                continue
            _bp, brun, btext = below
            replace_span(brun, 0, len(btext), values[key])
            report.filled[key] = values[key]
            replaced.append((btext.strip(), values[key]))

    # The same name is often printed twice — once for the страхователь and once
    # for the собственник. Whatever was replaced by label is replaced elsewhere.
    for old, new in replaced:
        if len(old) < 6:
            continue
        for _p, runs, _text in lines:
            text = text_of(runs)
            at = text.find(old)
            if at >= 0 and new not in text:
                replace_span(runs, at, at + len(old), new)


def _below(lines: list, i: int):
    """The line a label's value sits on, past the form's own small print."""
    for _p, runs, text in lines[i + 1:i + 4]:
        if _NOTE.match(text.strip()) or not text.strip():
            continue
        if _LABELS.search(text):
            return None                # the next field, not this one's value
        return _p, runs, text
    return None


def _table_values(doc, values: dict[str, str], report: Report, *,
                  skip: frozenset[str] = frozenset()) -> None:
    """Insurers print the vehicle block inside a table as often as not.

    ``skip`` names values already written somewhere better — a VIN that
    went into its own grid of boxes must not be printed twice.
    """
    for table in doc.tables:
        for row in table.rows:
            for cell in _cells(row):
                text = " ".join(cell.text.split())
                found = _hits(text, values)
                if not found:
                    continue
                key, lo, hi = found[0]
                if text[lo:hi].strip():
                    _set_cell(cell, text[:lo] + values[key])
                elif len(found) == 1 and hi >= len(text.rstrip()):
                    # the cell holds the label and nothing else — several
                    # insurers leave the value's own cell like that
                    if key in skip:
                        continue
                    _set_cell(cell, text.rstrip() + _SEPARATOR + values[key])
                else:
                    continue
                report.filled[key] = values[key]


# --------------------------------------------------- by shape, not by label

#: The previous customer's data, recognised by how it is written. A VIN is 17
#: characters with no I/O/Q; a Russian plate is a letter, three digits, two
#: letters and a region; a СТС is two digits, two letters and six digits.
#: A plate's letters are the twelve that look the same in both alphabets, and
#: templates are typed in whichever the keyboard was on — so both are accepted.
_PLATE_LETTER = "АВЕКМНОРСТУХABEKMHOPCTYX"
_SHAPES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("vin", re.compile(r"(?<![A-Z0-9])(?=[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z])"
                       r"[A-HJ-NPR-Z0-9]{15,17}(?![A-Z0-9])")),
    ("plate", re.compile(rf"(?<![\w])[{_PLATE_LETTER}]\s?\d{{3}}\s?"
                         rf"[{_PLATE_LETTER}]{{2}}\s?\d{{2,3}}(?!\w)")),
    ("sts", re.compile(r"(?<!\d)\d{2}\s?[А-Яа-я]{2}\s?\d{6}(?!\d)")),
)


def _by_pattern(doc, values: dict[str, str], report: Report) -> None:
    """Swap the previous customer's car for this one wherever it is written.

    Layout-independent: an insurer that prints its headings on one line and the
    data on another is handled here rather than by guessing which line is which.
    Make and model have no shape of their own, so they are taken to be whatever
    stands in front of the VIN on the same line.
    """
    for paragraph in iter_paragraphs(doc):
        _swap_shapes(runs_of(paragraph), values, report)
    for table in doc.tables:
        for row in table.rows:
            for cell in _cells(row):
                for paragraph in cell.paragraphs:
                    _swap_shapes(runs_of(paragraph), values, report)


_VEHICLE_HEAD = re.compile(r"^\s*([A-Za-zА-Яа-я][\w\-. ]{2,40}?)\s+$")


def _swap_shapes(runs: list, values: dict[str, str], report: Report) -> None:
    text = text_of(runs)
    if not text.strip():
        return
    for key, shape in _SHAPES:
        new = values.get(key)
        if not new:
            continue
        for m in reversed(list(shape.finditer(text))):
            if m.group(0).replace(" ", "") == new.replace(" ", ""):
                continue                       # already this car
            if key == "vin" and values.get("vehicle"):
                head = _VEHICLE_HEAD.match(text[:m.start()])
                if head and not _LABELS.search(head.group(1)):
                    replace_span(runs, head.start(1), head.end(1),
                                 values["vehicle"])
                    report.filled["vehicle"] = values["vehicle"]
                    text = text_of(runs)
                    m = next((x for x in shape.finditer(text)), m)
            replace_span(runs, m.start(), m.end(), new)
            report.filled[key] = new
            text = text_of(runs)


_VIN = re.compile(r"^[A-HJ-NPR-Z0-9]{15,17}$")


def _vin_grids(doc, vin: str, report: Report) -> None:
    """Some insurers print the VIN one character per box — rewrite those too.

    Only a run of single-character cells that already spells out a VIN is
    touched, so no other grid on the page can be mistaken for it.
    """
    if not vin:
        return
    for table in doc.tables:
        for row in table.rows:
            grid = [c for c in _cells(row) if len(c.text.strip()) <= 1]
            joined = "".join(c.text.strip() for c in grid).upper()
            if len(grid) < 15 or not _VIN.fullmatch(joined):
                continue
            for cell, char in zip(grid, vin.ljust(len(grid))):
                _set_cell(cell, char.strip())
            report.filled["vin_grid"] = vin


# ------------------------------------------------------------------ drivers

_DRIVER_HEADER = re.compile(
    r"Лица,\s*допущенн\w+\s+к\s+управлению\s+транспортным\s+средством",
    re.IGNORECASE)
_LICENCE_HEADER = re.compile(r"Водительское\s+удостоверение", re.IGNORECASE)


def _driver_table(doc):
    """The table whose header row names the drivers and their licences."""
    for table in doc.tables:
        for ri, row in enumerate(table.rows):
            joined = " ".join(c.text for c in _cells(row))
            if _DRIVER_HEADER.search(joined) and _LICENCE_HEADER.search(joined):
                return table, ri
    return None, 0


def _column_numbers(cells: list) -> bool:
    """«1 | 2 | 3 | 4» — the form numbering its columns, not a driver row.

    Its first cell is «1» just like a real first driver's, so the whole row has
    to be read: consecutive integers all the way across and nothing else.
    """
    texts = [c.text.strip() for c in cells]
    if len(texts) < 3 or not all(t.isdigit() for t in texts):
        return False
    return [int(t) for t in texts] == list(range(1, len(texts) + 1))


def _fill_drivers(doc, drivers: list[tuple[str, str]], report: Report) -> None:
    """Write each driver into the table, and dash out the rows left over.

    The КБМ column is not touched: that coefficient comes from the РСА database
    and this program has no way to know it.
    """
    table, header = _driver_table(doc)
    if table is None:
        if not _fill_driver_lines(doc, drivers, report):
            report.skipped.append("drivers — бланкада ҳайдовчилар рўйхати топилмади")
        return
    body = [row for row in table.rows[header + 1:] if _cells(row)]
    while body and _column_numbers(_cells(body[0])):
        body = body[1:]
    for i, row in enumerate(body):
        cells = _cells(row)
        if len(cells) < 3:
            continue
        fio, licence = drivers[i] if i < len(drivers) else (_DASH, _DASH)
        _set_cell(cells[1], fio)
        _set_cell(cells[2], licence)
        if i >= len(drivers) and len(cells) > 3:
            _set_cell(cells[3], _DASH)
    report.drivers = min(len(drivers), len(body))
    if len(drivers) > len(body):
        report.skipped.append(
            f"drivers:{len(drivers) - len(body)} — бланкада фақат "
            f"{len(body)} та қатор бор")


#: «ЧУНАЕВ БАХРОМЖОН ЭШМИРЗОЕВИЧ 5036 634917 0.63» — a driver written as a
#: plain line, which is how an insurer that draws no table prints them.
_DRIVER_LINE = re.compile(
    r"^(?P<fio>[А-ЯЁ][А-ЯЁа-яё\-]+(?:\s+[А-ЯЁ][А-ЯЁа-яё\-]+){1,3})\s+"
    r"(?P<licence>[A-ZА-Я0-9]{2,4}\s?\d{6,9})"
    r"(?P<tail>\s+\d[.,]\d{1,2})?\s*$")


def _fill_driver_lines(doc, drivers: list[tuple[str, str]],
                       report: Report) -> bool:
    """Rewrite a driver list an insurer printed as paragraphs, not a table.

    The КБМ that trails each line belongs to the person who was there before,
    so it is dropped rather than handed to somebody else — it comes from the
    РСА database, and this program has no way to look it up.
    """
    lines = [(p, r, text_of(r)) for p in iter_paragraphs(doc)
             if (r := runs_of(p)) and text_of(r).strip()]
    start = next((i for i, (_p, _r, t) in enumerate(lines)
                  if _DRIVER_HEADER.search(t)), None)
    if start is None:
        return False
    block: list[tuple] = []
    for entry in lines[start + 1:]:
        if _DRIVER_LINE.match(entry[2].strip()):
            block.append(entry)
        elif block:
            break
    if not block:
        return False
    for i, (_p, runs, text) in enumerate(block):
        if i < len(drivers):
            fio, licence = drivers[i]
            new = f"{fio} {licence}"
        else:
            new = f"{_DASH} {_DASH}"
        replace_span(runs, 0, len(text), new)
    report.drivers = min(len(drivers), len(block))
    if len(drivers) > len(block):
        report.skipped.append(
            f"drivers:{len(drivers) - len(block)} — бланкада фақат "
            f"{len(block)} та қатор бор")
    return True


# -------------------------------------------------------------- the choice


def _tick(text: str, m: re.Match, on: bool) -> str:
    """Put or remove the mark that follows one of the two options."""
    tail = text[m.end():]
    marked = re.match(r"\s*(\[[^\]]{0,3}\]|[XХxхV✔✓])", tail)
    if on:
        if marked and marked.group(1).strip("[]").strip():
            return text
        if marked:
            return text[:m.end()] + tail.replace(marked.group(1), "[X]", 1)
        return text[:m.end()] + " [X]" + tail
    if not marked:
        return text
    replacement = "[ ]" if marked.group(1).startswith("[") else ""
    return text[:m.end()] + tail.replace(marked.group(1), replacement, 1)


def _choose(doc, unlimited: bool, report: Report) -> None:
    """Mark «неограниченного количества лиц» or «лиц, допущенных к управлению».

    Which one is ticked decides who the policy actually covers, so it is never
    guessed — the operator picks it on the screen.
    """
    wanted = _UNLIMITED if unlimited else _LIMITED
    offered = False
    for paragraph in iter_paragraphs(doc):
        runs = runs_of(paragraph)
        text = text_of(runs)
        if not (_UNLIMITED.search(text) or _LIMITED.search(text)):
            continue
        offered = offered or bool(wanted.search(text))
        new = text
        for pattern, on in ((_UNLIMITED, unlimited), (_LIMITED, not unlimited)):
            m = pattern.search(new)
            if m:
                new = _tick(new, m, on)
        if new != text:
            replace_span(runs, 0, len(text), new)
    report.filled["coverage"] = ("неограниченное количество лиц" if unlimited
                                 else "лица, допущенные к управлению")
    if not offered:
        # this insurer's template prints only the other option — ticking it
        # would say something the form does not offer
        report.skipped.append("coverage — бланкада бу вариант йўқ")


# ----------------------------------------------------------- the signature


def _clear_signature(doc, report: Report) -> None:
    """Erase the previous policy's electronic signature. Never re-create one."""
    for paragraph in iter_paragraphs(doc):
        runs = runs_of(paragraph)
        text = text_of(runs)
        if text.strip() and _SIGNATURE.search(text):
            replace_span(runs, 0, len(text), "")
            report.cleared.append(" ".join(text.split())[:60])


# ------------------------------------------------------------------ public


#: «14.07.2027г.» — the «г.» runs straight into the year on some forms,
#: so a word boundary would miss it.
_DMY = re.compile(r"(?<!\d)\d{2}\.\d{2}\.\d{4}(?!\d)")
#: Capitalised: the same words appear mid-sentence in the small print.
_TERM = re.compile(r"(?<![А-Яа-яЁё])Срок\s+страхования")
_SIGNED_ON = re.compile(r"Дата\s+(?:заключения\s+договора|выдачи\s+полиса)",
                        re.IGNORECASE)
_LONG_DATE = re.compile(
    r"«?\d{1,2}»?\s+[А-Яа-яЁё]{3,8}\s+\d{4}", re.IGNORECASE)


def _dates(doc, *, start: str, end: str, signed: str, report: Report) -> None:
    """Write the policy's own dates wherever the form prints them as text.

    The «Срок страхования» line carries two: the first is the start, the second
    the end. Where an insurer prints those dates one digit per box instead, the
    boxes are reported rather than half-filled — a date with three of its eight
    digits changed is worse than one the operator finishes by hand.
    """
    lines = [(r, t) for p in iter_paragraphs(doc)
             if (r := runs_of(p)) and (t := text_of(r)).strip()]

    # «Срок страхования с … 15.07.2026 г.» and «по … 14.07.2027 г.» are one
    # field, but an insurer may wrap them onto two lines — so the pair of dates
    # is taken across the lines that follow, not only the one with the label.
    for i, (_runs, text) in enumerate(lines):
        if not _TERM.search(text):
            continue
        wanted = [start, end]
        for runs, line in lines[i:i + 3]:
            if not wanted:
                break
            if line is not text and (_TERM.search(line) or not _DMY.search(line)):
                break
            new = _DMY.sub(lambda m: wanted.pop(0) if wanted else m.group(0), line)
            if new != line:
                replace_span(runs, 0, len(line), new)
                report.filled["term"] = f"{start} — {end}"
        break

    for paragraph in iter_paragraphs(doc):
        runs = runs_of(paragraph)
        text = text_of(runs)
        if not text.strip():
            continue
        if _SIGNED_ON.search(text):
            new = _LONG_DATE.sub(_long(signed), text, count=1)
            new = _DMY.sub(signed, new, count=1)
            if new != text:
                replace_span(runs, 0, len(text), new)
                report.filled["signed_on"] = signed

    if "term" in report.filled:
        return
    # No line carried the dates as text: this insurer prints them one digit per
    # box. Say so rather than change three of the eight digits.
    for table in doc.tables:
        for row in table.rows:
            if _TERM.search(" ".join(c.text for c in _cells(row))):
                report.skipped.append(
                    "Срок страхования — бланкада катак-катак ёзилган, "
                    "қўлда тўлдиринг")
                return


_MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня",
           "июля", "августа", "сентября", "октября", "ноября", "декабря")


def _long(dmy: str) -> str:
    """«28.07.2026» → «28» июля 2026 — the shape those templates print."""
    day, month, year = dmy.split(".")
    return f"«{day}» {_MONTHS[int(month) - 1]} {year}"


def fill(template: Path, out: Path, *, values: dict[str, str],
         drivers: list[tuple[str, str]], unlimited: bool,
         start: str = "", end: str = "", signed: str = "") -> Report:
    """Fill one insurer's policy template for one car and up to four drivers."""
    import docx

    doc = docx.Document(str(template))
    report = Report()
    _clear_signature(doc, report)
    _paragraph_values(doc, values, report)
    _vin_grids(doc, values.get("vin", ""), report)
    _table_values(doc, values, report,
                  skip=frozenset({"vin"} if "vin_grid" in report.filled
                                 else ()))
    _by_pattern(doc, values, report)
    _fill_drivers(doc, [] if unlimited else drivers, report)
    _choose(doc, unlimited, report)
    if start and end:
        _dates(doc, start=start, end=end, signed=signed or start, report=report)
    for key in values:
        if key not in report.filled and values[key]:
            report.skipped.append(f"{key} — бланкада бу жой топилмади, қўлда ёзинг")
    seen: list[str] = []
    for note in report.skipped:
        if note not in seen:
            seen.append(note)
    report.skipped = seen
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    log.info("ОСАГО filled from %s → %s (%d drivers)",
             template.name, out.name, report.drivers)
    return report
