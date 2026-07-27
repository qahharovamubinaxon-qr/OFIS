"""Learn where a firm's трудовой договор leaves room for the worker.

A firm that hands its contract in as .docx is filled by text — that path is
older and exact. A firm that hands in a PDF cannot be: the page is a flattened
picture of a Word document, so the gaps have to be found by looking at it.

They are found the way a reader finds them:

* the printed underscore runs — «и ______,», «по должности ______», the
  «"__" ______ ____ г.» of the date — are unmistakable ink and are measured
  directly;
* the requisites at the foot of the contract («Работник Ф.И.О.:», «паспорт
  серия номер:», «выдан:» …) carry no underscore at all: the value simply goes
  after the colon, so the line's own right edge is where it starts;
* the AI is asked only where each of those places begins. They are distinct
  phrases, which is what a model reads reliably; the geometry is ours.

Blue ink is ignored throughout. The last page carries the firm's round stamp
and the director's signature, and their strokes otherwise read as underscores.

Nothing is written where the shape does not add up: a date line that does not
hold three runs, or a requisites block that is not six lines, is reported and
left blank rather than filled at a guess.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.common.errors import OfisError
from src.common.logging import get_logger

log = get_logger(__name__)

MAPPING_NAME = "trud_mapping.json"
MAPPING_VERSION = "1"

# The places the AI is asked to find. Each is a phrase printed on the contract,
# and each is unique on its page — «выдан:» appears twice, so it is never asked
# for: the requisites are taken as one block of six lines in printed order.
ANCHORS: tuple[tuple[str, str], ...] = (
    ("contract_date", 'строка с датой договора: «"___" ________ ____ г.»'),
    ("worker_fio", "строка «…, и ____________, именуемый в дальнейшем "
                   "\"Работник\"»"),
    ("position", "строка «Работник принимается для выполнения работы по "
                 "должности ______»"),
    ("requisites", "строка «Работник Ф.И.О.:» в разделе «АДРЕСА И РЕКВИЗИТЫ "
                   "СТОРОН»"),
    ("sign_fio", "в таблице «ПОДПИСИ СТОРОН», в колонке «Работник:» — строка "
                 "«__________(____________.)»"),
    ("sign_date", "в той же колонке — строка «Экземпляр получен и подписан "
                  "Работником «___» ________ ______ г.»"),
)

# The six requisite lines, in the order the contract prints them.
REQUISITES: tuple[tuple[str, str], ...] = (
    ("trud.req_fio", "Работник Ф.И.О.:"),
    ("trud.req_doc", "Документ, удостоверяющий личность:"),
    ("trud.req_passport", "паспорт серия номер:"),
    ("trud.req_passport_issued", "выдан:"),
    ("trud.req_patent", "Патент … серия номер:"),
    ("trud.req_patent_issued", "выдан:"),
)

# The date lines print three runs: day, month, year.
DATE_PARTS = ("day", "month", "year")

_DPI = 150
_RUN_MIN_PT = 16.0          # shorter than this is a hyphen, not a gap
_RUN_MAX_PT = 400.0         # longer than this is a table border
_NEAR_PT = 14.0             # how far from the AI's answer a line may sit
_CLOSE_PT = 1.6             # a gap this small is inside a line, not between
_INK = 200                  # anything darker counts as print…
_NEUTRAL = 40               # …if it is grey rather than the stamp's blue
_BORDER_MIN_PT = 30.0       # a vertical stroke this long is a table border
_LEAD_PT = 5.0              # a value starts this far after a colon
_SLACK_PT = 6.0             # …and may run a little past its underscore
_DESCENDER = 0.21           # of the size, below the baseline


@dataclass(frozen=True)
class Line:
    """One printed line: its ink box, and any underscore runs on it."""

    page: int
    top: float
    bottom: float
    x0: float
    x1: float
    # each gap as (y of the underscore, its left x, its right x)
    runs: tuple[tuple[float, float, float], ...] = ()


@dataclass(frozen=True)
class Study:
    fields: list[dict]
    missing: list[str]
    pages: int

    @property
    def ok(self) -> bool:
        return bool(self.fields)


# ------------------------------------------------------------------- ink


def read_lines(doc) -> list[Line]:
    """Every printed line of the contract, with the gaps left on it."""
    import numpy as np

    scale = _DPI / 72
    out: list[Line] = []
    for index, page in enumerate(doc):
        pm = page.get_pixmap(dpi=_DPI)
        rgb = np.frombuffer(pm.samples, dtype=np.uint8).reshape(
            pm.height, pm.width, pm.n)[:, :, :3].astype(int)
        # black print only: the stamp and the signature are blue, and their
        # strokes would otherwise read as underscores
        ink = (rgb.mean(2) < _INK) & ((rgb.max(2) - rgb.min(2)) < _NEUTRAL)
        for top, bottom in _bands(_without_borders(ink), scale):
            out.append(_line(ink, scale, index + 1, top, bottom))
    return out


def _without_borders(ink):
    """Blank out the table's vertical rules.

    The signature table at the foot of the contract is drawn with full-height
    borders, so every row of it carries ink and the whole table reads as one
    enormous line. Dropping the columns that run the length of the table lets
    its rows separate again.
    """
    import numpy as np

    # A border is a column drawn as one long unbroken stroke. Total coverage
    # alone would also catch a column of body text that happens to cross many
    # lines, and blanking those split the requisites into two bands each.
    tall = int(_BORDER_MIN_PT * _DPI / 72)
    borders = np.zeros(ink.shape[1], dtype=bool)
    for x in range(ink.shape[1]):
        column = ink[:, x]
        if not column.any():
            continue
        padded = np.concatenate(([False], column, [False]))
        edges = np.flatnonzero(padded[1:] != padded[:-1])
        if (edges[1::2] - edges[::2]).max() >= tall:
            borders[x] = True
    if not borders.any():
        return ink
    # a drawn border is anti-aliased, so its faint neighbours have to go too —
    # one surviving column is enough to hold every row of the table together
    borders = borders | np.roll(borders, 1) | np.roll(borders, -1)
    clean = ink.copy()
    clean[:, borders] = False
    return clean


def _bands(ink, scale: float) -> list[tuple[float, float]]:
    """The y range of each printed line."""
    import numpy as np

    rows = ink.sum(1)
    bands, start = [], None
    for y, count in enumerate(rows):
        if count > 1:
            if start is None:
                start = y
        elif start is not None:
            bands.append([start / scale, y / scale])
            start = None
    if start is not None:
        bands.append([start / scale, len(rows) / scale])
    # A hairline of a letter can leave a single-pixel row blank inside a line,
    # which would split it in two. No two printed lines sit this close, so a
    # gap that small is always inside one of them.
    closed: list[list[float]] = []
    for band in bands:
        if closed and band[0] - closed[-1][1] < _CLOSE_PT:
            closed[-1][1] = band[1]
        else:
            closed.append(band)
    return [(a, b) for a, b in closed]


def _line(ink, scale: float, page: int, top: float, bottom: float) -> Line:
    import numpy as np

    band = ink[int(top * scale):max(int(bottom * scale), int(top * scale) + 1)]
    cols = np.flatnonzero(band.sum(0) > 0)
    if not len(cols):
        return Line(page=page, top=top, bottom=bottom, x0=0.0, x1=0.0)
    seen: list[list[float]] = []
    for offset, row in enumerate(band):
        y = top + offset / scale
        padded = np.concatenate(([False], row, [False]))
        edges = np.flatnonzero(padded[1:] != padded[:-1])
        for a, b in zip(edges[::2], edges[1::2], strict=True):
            width = (b - a) / scale
            if _RUN_MIN_PT <= width <= _RUN_MAX_PT:
                _keep(seen, y, a / scale, b / scale)
    return Line(page=page, top=top, bottom=bottom,
                x0=cols[0] / scale, x1=cols[-1] / scale,
                runs=tuple(sorted((round(y, 1), round(a, 1), round(b, 1))
                                  for y, a, b in seen)))


def _keep(seen: list[list[float]], y: float, a: float, b: float) -> None:
    """Underscores are drawn two or three pixels tall; keep each one once.

    Only a near-identical gap on an adjoining row is the same underscore.
    Folding on overlap instead would let one long gap swallow the shorter ones
    printed inside its span — «« ___ » ____ ___ г.» sitting just above
    «Подпись Работника: ______» is exactly that shape.
    """
    for run in seen:
        if (abs(run[1] - a) < 1.5 and abs(run[2] - b) < 1.5
                and y - run[0] < 2.0):
            run[0] = y
            return
    seen.append([y, a, b])


def body_size(doc) -> float:
    """The size the contract is set in, from the page's own scale.

    These contracts are Word documents at 12pt printed to a page a little
    shorter than A4, so the type lands a touch under 12.
    """
    height = doc[0].rect.height if len(doc) else 842.0
    return round(12.0 * height / 842.0 * 2) / 2


# --------------------------------------------------------------- anchors


def anchor_prompt() -> str:
    named = "\n".join(f'  "{key}" — {what}' for key, what in ANCHORS)
    return (
        "Это страница российского трудового договора с иностранным "
        "гражданином. В нём оставлены пустые места, которые заполняют от "
        "руки.\n"
        "Верни ТОЛЬКО JSON-объект, без пояснений и без markdown. Для каждого "
        "места, которое ВИДНО НА ЭТОЙ странице, дай долю высоты страницы "
        "(число от 0 до 1, сверху вниз), на которой напечатана эта строка. "
        "То, чего на этой странице нет, НЕ включай в ответ.\n"
        "Ключи и их строки:\n" + named + "\n"
        'Пример ответа: {"worker_fio": 0.21}'
    )


def read_anchors(ai, doc) -> dict[str, tuple[int, float]]:
    """key → (page, y in points) for each place the AI could find."""
    from src.domain.enums import DocType

    known = {key for key, _what in ANCHORS}
    found: dict[str, tuple[int, float]] = {}
    for index, page in enumerate(doc):
        pm = page.get_pixmap(dpi=_DPI)
        answer = ai.extract(pm.tobytes("png"), DocType.PASSPORT, anchor_prompt())
        for key, raw in answer.fields.items():
            if key not in known or key in found:
                continue
            try:
                fraction = float(str(raw).replace(",", "."))
            except ValueError:
                continue
            if 0.0 <= fraction <= 1.0:
                found[key] = (index + 1, fraction * page.rect.height)
    return found


def _line_at(lines: list[Line], page: int, y: float,
             *, wants_run: bool) -> Line | None:
    """The printed line the model meant."""
    near = [ln for ln in lines
            if ln.page == page and ln.top - _NEAR_PT <= y <= ln.bottom + _NEAR_PT
            and (bool(ln.runs) if wants_run else True)]
    return min(near, key=lambda ln: abs((ln.top + ln.bottom) / 2 - y)) if near else None


# ----------------------------------------------------------------- study


def study(pdf_path: Path, ai) -> Study:
    """Work out where this firm's contract leaves room for the worker."""
    import fitz

    if not ai.available():
        raise OfisError(
            "Шартномани таҳлил қилиш учун AI калити керак — Sozlamalar → "
            "Gemini калитини киритинг.")
    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:  # noqa: BLE001 - any unreadable file
        raise OfisError("Трудовой договор PDF си очилмади.") from exc
    try:
        lines = read_lines(doc)
        if not lines:
            raise OfisError("Шартномада матн топилмади.")
        size = body_size(doc)
        anchors = read_anchors(ai, doc)
        fields, missing = [], []
        for place, build in (("contract_date", _date_fields),
                             ("worker_fio", _run_field),
                             ("position", _run_field),
                             ("requisites", _requisite_fields),
                             ("sign_fio", _run_field),
                             ("sign_date", _date_fields)):
            spot = anchors.get(place)
            made = build(lines, spot, place, size) if spot else []
            if made:
                fields.extend(made)
            else:
                missing.append(place)
        return Study(fields=sorted(fields, key=lambda f: (f["page"], f["y"])),
                     missing=missing, pages=len(doc))
    finally:
        doc.close()


def _at(line: Line, size: float) -> float:
    """The baseline of a printed line, from the bottom of its ink."""
    return round(line.bottom - _DESCENDER * size, 1)


def _baseline(rule_y: float, size: float) -> float:
    """A value written on an underscore sits just above it."""
    return round(rule_y - _DESCENDER * size, 1)


def _field(field_id: str, page: int, x: float, y: float, size: float,
           width: float | None = None) -> dict:
    out = {"id": field_id, "type": "text", "page": page,
           "x": round(x, 1), "y": y, "font": "OfisSerif", "size": size,
           "align": "left"}
    if width:
        out["width"] = round(width, 1)
        out["overflow"] = "shrink"
    return out


def _run_field(lines: list[Line], spot: tuple[int, float], place: str,
               size: float) -> list[dict]:
    """A single value written on the underscore left for it.

    «__________(____________.)» in the signature cell leaves two: the first is
    where the worker signs by hand, the second is where the name is printed, so
    that line takes the last run rather than the longest.
    """
    line = _line_at(lines, *spot, wants_run=True)
    if line is None:
        return []
    row = _row_nearest(line, spot[1])
    y, start, end = (row[-1] if place == "sign_fio"
                     else max(row, key=lambda r: r[2] - r[1]))
    return [_field(f"trud.{place}", line.page, start + 1.0,
                   _baseline(y, size), size,
                   width=end - start - 1.0 + _SLACK_PT)]


def _rows(line: Line) -> list[list[tuple[float, float, float]]]:
    """The line's gaps, grouped by the underscore they are drawn on."""
    grouped: list[list[tuple[float, float, float]]] = []
    for run in sorted(line.runs):
        if grouped and abs(grouped[-1][0][0] - run[0]) < 2.5:
            grouped[-1].append(run)
        else:
            grouped.append([run])
    for group in grouped:
        group.sort(key=lambda r: r[1])
    return grouped


def _row_nearest(line: Line, y: float) -> list[tuple[float, float, float]]:
    """The underscore row the model meant.

    A band can hold two printed lines — the signature table packs them tight —
    so the gaps are grouped by the rule they sit on and the nearest group wins.
    """
    return min(_rows(line), key=lambda g: abs(g[0][0] - y))


def _date_fields(lines: list[Line], spot: tuple[int, float], place: str,
                 size: float) -> list[dict]:
    """«"__" ______ ____ г.» — three runs, in the order they are printed."""
    line = _line_at(lines, *spot, wants_run=True)
    if line is None:
        return []
    row = _row_nearest(line, spot[1])
    if len(row) != len(DATE_PARTS):
        return []
    baseline = _baseline(row[0][0], size)
    out = []
    for part, (_y, start, end) in zip(DATE_PARTS, row, strict=True):
        out.append(_field(f"trud.{place}_{part}", line.page,
                          start + 1.0, baseline, size,
                          width=end - start - 1.0 + _SLACK_PT))
    return out


def _evenly_spaced(block: list[Line]) -> bool:
    """True when these lines really are one block of running text.

    Without this the six lines could be taken from wherever the page happened
    to have ink next — a contract that prints only four of them would borrow
    two rows of the signature table below.
    """
    gaps = [b.top - a.top for a, b in zip(block, block[1:], strict=False)]
    if not gaps:
        return True
    pitch = sorted(gaps)[len(gaps) // 2]
    return pitch > 0 and all(gap <= pitch * 1.8 for gap in gaps)


def _requisite_fields(lines: list[Line], spot: tuple[int, float], place: str,
                      size: float) -> list[dict]:
    """The six «…:» lines, each value written straight after its colon."""
    first = _line_at(lines, *spot, wants_run=False)
    if first is None:
        return []
    block = sorted((ln for ln in lines
                    if ln.page == first.page and ln.top >= first.top - 0.5),
                   key=lambda ln: ln.top)[:len(REQUISITES)]
    if len(block) != len(REQUISITES) or not _evenly_spaced(block):
        return []
    return [_field(field_id, ln.page, ln.x1 + _LEAD_PT, _at(ln, size), size)
            for (field_id, _label), ln in zip(REQUISITES, block, strict=True)]


# ------------------------------------------------------------------ save


def save(study_result: Study, template: Path, target_dir: Path) -> Path:
    import fitz

    doc = fitz.open(template)
    try:
        size = [round(doc[0].rect.width, 1), round(doc[0].rect.height, 1)]
    finally:
        doc.close()
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / MAPPING_NAME
    path.write_text(json.dumps({
        "template": template.name,
        "template_version": "1",
        "mapping_version": MAPPING_VERSION,
        "page_size": size,
        "fields": study_result.fields,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    log.info("Трудовой mapping learned for %s: %d fields", template,
             len(study_result.fields))
    return path


def mapping_for(template: Path) -> Path | None:
    own = template.parent / MAPPING_NAME
    return own if own.exists() else None
