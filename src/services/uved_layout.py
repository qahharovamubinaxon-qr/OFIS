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
* the AI reads the printed grey labels and reports where each one is, and every
  field is snapped to the first rule below its own label.

The result is a mapping in the same shape as the bundled one, saved beside that
firm's template, so filling stays the plain `src.pdf.engine.fill` it always was.

Nothing here guesses: a field whose label the AI did not find is left out and
reported, rather than placed on whichever line happened to be free.
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


# ------------------------------------------------------------------ labels


def label_prompt() -> str:
    keys = "\n".join(f'  "{key}" — «{label}» в разделе «{section}»'
                     for key, _id, label, section in FIELDS)
    return (
        "Это страница российской формы Госуслуг «Уведомление о заключении "
        "трудового договора с иностранным гражданином». Над каждой линией "
        "напечатан СЕРЫЙ заголовок поля. Заголовки «Серия» и «Номер» "
        "встречаются дважды — различай их по номеру раздела.\n"
        "Верни ТОЛЬКО JSON-объект, без пояснений и без markdown. Для каждого "
        "заголовка, который ВИДЕН НА ЭТОЙ странице, дай долю высоты страницы "
        "(число от 0 до 1, сверху вниз), на которой он напечатан. Заголовок, "
        "которого на этой странице нет, НЕ включай в ответ.\n"
        "Ключи и их заголовки:\n" + keys + "\n"
        "Пример ответа: {\"surname\": 0.71, \"name\": 0.76}"
    )


def read_labels(ai, doc) -> dict[str, tuple[int, float]]:
    """key → (page, y in points) for every label the AI could find."""
    from src.domain.enums import DocType

    found: dict[str, tuple[int, float]] = {}
    for index, page in enumerate(doc):
        pm = page.get_pixmap(dpi=_DPI)
        answer = ai.extract(pm.tobytes("png"), DocType.PASSPORT, label_prompt())
        height = page.rect.height
        known = {key for key, _id, _label, _section in FIELDS}
        for key, raw in answer.fields.items():
            if key not in known or key in found:
                continue
            try:
                fraction = float(str(raw).replace(",", "."))
            except ValueError:
                continue
            if 0.0 <= fraction <= 1.0:
                found[key] = (index + 1, fraction * height)
    return found


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
        labels = read_labels(ai, doc)
        fields, missing, used = [], [], set()
        for key, field_id, label, _section in FIELDS:
            spot = labels.get(key)
            if spot is None:
                missing.append(label)
                continue
            rule = _rule_below(rules, *spot)
            if rule is None or (rule.page, rule.y) in used:
                missing.append(label)
                continue
            used.add((rule.page, rule.y))
            fields.append({
                "id": field_id, "type": "text", "page": rule.page,
                "x": round(x, 1), "y": round(rule.y - gap, 1),
                "font": _FONT, "size": size, "align": "left",
            })
        return Study(fields=fields, missing=missing, rules=len(rules),
                     pages=len(doc))
    finally:
        doc.close()


def _rule_below(rules: list[Rule], page: int, label_y: float) -> Rule | None:
    """The field line this label belongs to: the first one under it."""
    below = [r for r in rules
             if r.page == page and 0 < r.y - label_y <= _LABEL_GAP_PT]
    return min(below, key=lambda r: r.y) if below else None


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
