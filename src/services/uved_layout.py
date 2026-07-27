"""Learn where a firm's «Уведомление» blank wants each worker value.

Every firm hands in its own Госуслуги blank. They differ: the employer block is
a different length, the form runs to two pages for one firm and three for
another, and some worker rows come pre-filled. A single hand-measured mapping
therefore cannot serve them all — reusing one is what put a worker's surname on
the «Отчество» line.

So each blank is studied when the firm is added:

* the form's field rules are found by ink — a long, light horizontal line;
* the rules that already carry a value (the employer block) are measured to
  learn the form's own house style: where a value starts, how far above its
  rule it sits, and at what size;
* the AI reads the four section headings and says where each begins — they are
  large and unique, which is the one thing a model reads reliably here;
* inside a section the form's own field order does the rest: the empty lines,
  top to bottom, are that section's fields in order.

That split matters. The form prints «Серия» and «Номер» twice — once for the
passport, once for the patent — and asking a model to tell those apart left
all three of them blank on a real уведомление. Section boundaries plus order
cannot make that mistake.

The result is a mapping in the same shape as the bundled one, saved beside that
firm's template, so filling stays the plain `src.pdf.engine.fill` it always was.

Nothing here guesses across a boundary: if a section does not hold exactly the
lines its fields need, those fields are reported missing and left blank rather
than shifted onto whichever line happened to be free.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.common.errors import OfisError
from src.common.logging import get_logger

log = get_logger(__name__)

MAPPING_NAME = "uved_mapping.json"
MAPPING_VERSION = "1"

# The form repeats «Серия» and «Номер» — once for the passport and once for the
# patent — so every field is named with the section it lives in.
_WORKER = "2. Сведения об иностранном гражданине"
_DOC = "3. Документ, удостоверяющий личность иностранного гражданина"
_PATENT = "4. Сведения о разрешении на работу или патенте"
_WORK = "5. Сведения о трудовой деятельности"
# nothing of ours lives in section 6, but its heading is what stops section 5
_MVD = "6. Выбор подразделения МВД России"

# The worker values this module places, and the label printed above each on the
# Госуслуги form. The key is what the AI is asked for; the id is the mapping id
# `TrudService` already fills.

FIELDS: tuple[tuple[str, str, str, str], ...] = (
    ("surname", "uved.surname", "Фамилия (рус.)", _WORKER),
    ("name", "uved.name", "Имя (рус.)", _WORKER),
    ("patronymic", "uved.patronymic", "Отчество (рус.)", _WORKER),
    ("birth_date", "uved.birth_date", "Дата рождения", _WORKER),
    ("gender", "uved.gender", "Пол", _WORKER),
    ("citizenship", "uved.citizenship", "Гражданство", _WORKER),
    ("birth_place", "uved.birth_place", "Место рождения, населенный пункт",
     _WORKER),
    ("passport_series", "uved.passport.series", "Серия", _DOC),
    ("passport_number", "uved.passport.number", "Номер", _DOC),
    ("passport_issue_date", "uved.passport.issue_date", "Дата выдачи", _DOC),
    ("passport_issued_by", "uved.passport.issued_by", "Кем выдан", _DOC),
    ("patent_series", "uved.patent.series", "Серия", _PATENT),
    ("patent_number", "uved.patent.number", "Номер", _PATENT),
    ("patent_region", "uved.patent.region", "Регион", _PATENT),
    ("patent_blank_series", "uved.patent.blank_series", "Серия бланка", _PATENT),
    ("patent_blank_number", "uved.patent.blank_number", "Номер бланка", _PATENT),
    ("profession", "uved.profession",
     "Профессия, специальность, должность, вид трудовой деятельности по договору",
     _WORK),
    ("contract_date", "uved.contract_date", "Дата заключения договора", _WORK),
)

# The sections, in the order the form prints them, and every line each one
# prints — not only the ones we fill. Госуслуги put «Вид документа» at the top
# of section 3 and «Адрес места работы» at the foot of section 5, and one blank
# even carries the literal «Не заполнено» on a line that is ours to write on.
# Counting the whole sequence is what makes those harmless: our fields are
# picked out of it by position, and a section whose line count does not match
# is left alone rather than filled one row out.
SECTIONS: tuple[tuple[str, str, tuple[str | None, ...]], ...] = (
    ("worker", _WORKER, (
        "surname", "name", "patronymic", "birth_date", "gender",
        "citizenship", "birth_place")),
    ("doc", _DOC, (
        None,                                   # Вид документа
        "passport_series", "passport_number",
        "passport_issue_date", "passport_issued_by")),
    ("patent", _PATENT, (
        None,                                   # Документ
        "patent_series", "patent_number", "patent_region",
        "patent_blank_series", "patent_blank_number")),
    ("work", _WORK, (
        "profession",
        None,                                   # Нет подходящей профессии
        None,                                   # Вид договора
        "contract_date",
        None)),                                 # Адрес места работы
    ("mvd", _MVD, ()),                          # boundary only — nothing of ours
)

# a study that finds fewer than this is not trustworthy enough to print from
MIN_FIELDS = 14

_DPI = 150
_RULE_MIN_PT = 120          # a field rule is at least this long…
_RULE_MAX_PT = 400          # …and shorter than the page-wide header divider
_VALUE_BAND_PT = 22.0       # how far above a rule its own value can sit
_LABEL_GAP_PT = 46.0        # …and how far above the rule its label can sit
_FONT = "OfisSansRegular"


@dataclass(frozen=True)
class Rule:
    """One of the form's field lines, and the value already sitting on it."""

    page: int                       # 1-based, as the mapping stores it
    y: float
    value_x: float | None = None    # where an existing value starts
    value_baseline: float | None = None
    value_height: float | None = None

    @property
    def filled(self) -> bool:
        return self.value_baseline is not None


@dataclass(frozen=True)
class Study:
    """What a blank turned out to want."""

    fields: list[dict]
    missing: list[str]              # labels the AI did not find
    rules: int
    pages: int

    @property
    def ok(self) -> bool:
        return len(self.fields) >= MIN_FIELDS


# ------------------------------------------------------------------ ink


def detect_rules(doc) -> list[Rule]:
    """Every field line in the document, with whatever value already sits on it."""
    import numpy as np

    scale = _DPI / 72
    found: list[Rule] = []
    for index, page in enumerate(doc):
        pm = page.get_pixmap(dpi=_DPI)
        grey = np.frombuffer(pm.samples, dtype=np.uint8).reshape(
            pm.height, pm.width, pm.n)[:, :, :3].mean(2)
        for y in _rule_rows(grey, scale):
            found.append(_with_value(grey, scale, index + 1, y))
    return found


def _rule_rows(grey, scale: float) -> list[float]:
    """The y of each field line, in points, one entry per line."""
    import numpy as np

    ink = grey < 240
    rows: list[float] = []
    for y in range(ink.shape[0]):
        run = _longest_run(ink[y])
        if _RULE_MIN_PT <= run / scale <= _RULE_MAX_PT:
            point = y / scale
            # a drawn line is two or three pixels tall; keep it as one rule
            if rows and point - rows[-1] < 1.2:
                rows[-1] = point
            else:
                rows.append(point)
    return rows


def _longest_run(row) -> int:
    import numpy as np

    if not row.any():
        return 0
    # run lengths of consecutive True, without a Python loop over every pixel
    padded = np.concatenate(([False], row, [False]))
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    return int((edges[1::2] - edges[::2]).max())


def _with_value(grey, scale: float, page: int, y: float) -> Rule:
    """Measure the value printed just above ``y``, if the line carries one."""
    import numpy as np

    top = max(0, int((y - _VALUE_BAND_PT) * scale))
    bottom = max(top + 1, int((y - 1.0) * scale))
    band = grey[top:bottom, int(100 * scale):int(380 * scale)]
    dark = band < 120                      # a value is black; a label is grey
    rows = np.flatnonzero(dark.sum(1) > 2)
    if not len(rows):
        return Rule(page=page, y=y)
    cols = np.flatnonzero(dark.sum(0) > 0)
    return Rule(
        page=page, y=y,
        value_x=100 + cols[0] / scale,
        value_baseline=top / scale + rows[-1] / scale,
        value_height=(rows[-1] - rows[0]) / scale,
    )


def house_style(rules: list[Rule]) -> tuple[float, float, float]:
    """(x, gap above the rule, font size) — as the blank prints its own values.

    The employer block at the top of every one of these forms is already filled
    in, so the blank carries a worked example of exactly how a value should sit.
    That is measured rather than assumed.
    """
    filled = [r for r in rules if r.filled]
    if not filled:
        raise OfisError(
            "Бланкада тўлдирилган қатор топилмади — бу Госуслуги "
            "«Уведомление» бланкаси эканига ишонч ҳосил қилинг.")
    xs = sorted(r.value_x for r in filled)
    gaps = sorted(r.y - r.value_baseline for r in filled)
    # Values that wrapped onto two lines measure far taller than the type they
    # are set in, so the tallest quarter is dropped before the height is read.
    heights = sorted(r.value_height for r in filled if r.value_height)
    kept = heights[:max(1, len(heights) * 3 // 4)]
    cap = kept[len(kept) // 2] if kept else 7.2
    size = min(12.0, max(8.0, round(cap / 0.716 * 2) / 2))
    return xs[len(xs) // 2], gaps[len(gaps) // 2], size


# -------------------------------------------------------------- sections


def heading_prompt() -> str:
    named = "\n".join(f'  "{key}" — раздел «{title}»'
                     for key, title, _lines in SECTIONS)
    return (
        "Это страница российской формы Госуслуг «Уведомление о заключении "
        "трудового договора с иностранным гражданином». Крупным шрифтом "
        "напечатаны заголовки разделов, пронумерованные 1–6.\n"
        "Верни ТОЛЬКО JSON-объект, без пояснений и без markdown. Для каждого "
        "заголовка раздела, который ВИДЕН НА ЭТОЙ странице, дай долю высоты "
        "страницы (число от 0 до 1, сверху вниз), на которой он напечатан. "
        "Раздел, которого на этой странице нет, НЕ включай в ответ.\n"
        "Ключи и их разделы:\n" + named + "\n"
        'Пример ответа: {"worker": 0.63}'
    )


def read_headings(ai, doc) -> dict[str, tuple[int, float]]:
    """key → (page, y in points) for each section heading the AI could find."""
    from src.domain.enums import DocType

    known = {key for key, _title, _lines in SECTIONS}
    found: dict[str, tuple[int, float]] = {}
    for index, page in enumerate(doc):
        pm = page.get_pixmap(dpi=_DPI)
        answer = ai.extract(pm.tobytes("png"), DocType.PASSPORT, heading_prompt())
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


def section_lines(rules: list[Rule],
                  headings: dict[str, tuple[int, float]]) -> dict[str, list[Rule]]:
    """Every line each section prints, in order, across a page break.

    A section runs from its own heading to the next one. Lines the firm already
    filled in are kept: they are part of the sequence, and leaving them out is
    what let a pre-printed «Не заполнено» shift the rest of a section by one.
    """
    order = [key for key, _title, _lines in SECTIONS if key in headings]
    snapped = {key: _snap(rules, *headings[key]) for key in order}
    bounds = {}
    for position, key in enumerate(order):
        nxt = snapped[order[position + 1]] if position + 1 < len(order) else None
        bounds[key] = (snapped[key], nxt)

    buckets: dict[str, list[Rule]] = {key: [] for key in order}
    for rule in sorted(rules, key=lambda r: (r.page, r.y)):
        for key, (start, stop) in bounds.items():
            if (rule.page, rule.y) <= start:
                continue
            if stop is not None and (rule.page, rule.y) >= stop:
                continue
            buckets[key].append(rule)
            break
    return buckets


def _snap(rules: list[Rule], page: int, y: float) -> tuple[int, float]:
    """Move a heading into the blank band it actually sits in.

    A heading always falls in a wider-than-usual gap between two lines, so the
    model only has to be roughly right: its answer is pulled to the middle of
    the nearest such gap. Without this a heading reported a few points low
    swallows the line above it and the whole section is refused.
    """
    same = sorted((r.y for r in rules if r.page == page))
    if not same:
        return page, y
    gaps = [(0.0, same[0])] + list(zip(same, same[1:], strict=False))
    pitch = min((b - a for a, b in gaps if b > a), default=40.0)
    wide = [(a, b) for a, b in gaps if b - a > pitch * 1.4]
    if not wide:
        return page, y
    best = min(wide, key=lambda g: abs((g[0] + g[1]) / 2 - y))
    # only trust the correction when the model was in the neighbourhood
    if not best[0] - 40 <= y <= best[1] + 40:
        return page, y
    return page, (best[0] + best[1]) / 2


def _by_key() -> dict[str, tuple[str, str]]:
    """AI key → (mapping id, label)."""
    return {key: (field_id, label) for key, field_id, label, _s in FIELDS}


# ------------------------------------------------------------------ study


def study(pdf_path: Path, ai) -> Study:
    """Work out where this firm's blank wants each worker value."""
    import fitz

    if not ai.available():
        raise OfisError(
            "Бланкани таҳлил қилиш учун AI калити керак — Sozlamalar → "
            "Gemini калитини киритинг.")
    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:  # noqa: BLE001 - any unreadable file
        raise OfisError("Уведомление PDF си очилмади.") from exc
    try:
        rules = detect_rules(doc)
        if not rules:
            raise OfisError(
                "Бланкада тўлдириладиган чизиқлар топилмади — Госуслуги "
                "«Уведомление» PDF сини юкланг.")
        x, gap, size = house_style(rules)
        buckets = section_lines(rules, read_headings(ai, doc))
        return Study(fields=_place(buckets, x, gap, size),
                     missing=_missing(buckets), rules=len(rules), pages=len(doc))
    finally:
        doc.close()


def _place(buckets: dict[str, list[Rule]], x: float, gap: float,
           size: float) -> list[dict]:
    """Pick our fields out of each section's printed line sequence.

    A section that prints a different number of lines than the form is known to
    have is skipped whole: shifting the rest of it by one is exactly the
    mistake this module exists to prevent.
    """
    known = _by_key()
    fields: list[dict] = []
    for key, _title, sequence in SECTIONS:
        lines = buckets.get(key, [])
        if len(lines) != len(sequence):
            continue
        for slot, rule in zip(sequence, lines, strict=True):
            if slot is None:                    # a line the firm fills, not us
                continue
            field_id, _label = known[slot]
            fields.append({
                "id": field_id, "type": "text", "page": rule.page,
                "x": round(x, 1), "y": round(rule.y - gap, 1),
                "font": _FONT, "size": size, "align": "left",
            })
    return sorted(fields, key=lambda f: (f["page"], f["y"]))


def _missing(buckets: dict[str, list[Rule]]) -> list[str]:
    """The labels left blank, because their section did not add up."""
    known = _by_key()
    missing: list[str] = []
    for key, _title, sequence in SECTIONS:
        if len(buckets.get(key, [])) == len(sequence):
            continue
        missing.extend(known[slot][1] for slot in sequence if slot is not None)
    return missing


def save(study_result: Study, template: Path, target_dir: Path) -> Path:
    """Write the mapping beside the firm's own template."""
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
    log.info("Уведомление mapping learned for %s: %d fields", template,
             len(study_result.fields))
    return path


def mapping_for(template: Path) -> Path | None:
    """This firm's own learned mapping, if the blank was studied."""
    own = template.parent / MAPPING_NAME
    return own if own.exists() else None
