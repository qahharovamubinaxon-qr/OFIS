"""Where THIS firm's 2 НДФЛ sheet keeps its month table — read off the sheet.

Every firm scans its own справка: the office's «ООО ТРАЙД» sheet is 822
points tall, its «ООО МЕГАПОЛИС» one 842, and the right-hand table sits a
whole column further right on the second. Rather than have the office drag
the table into place for every new firm, the table is MEASURED off the
sheet — its rules are printed lines, and lines are easy to find.

What comes back is the same handles the office can drag in «📐», so a
reading that is a shade out is still corrected by hand in ten seconds.
Nothing here guesses: if the rules do not look like a two-table row of
eight, it returns nothing and the defaults stand.
"""

from __future__ import annotations

from pathlib import Path

from src.common.logging import get_logger
from src.pdf.ndfl2_spec import ROWS_PER_TABLE

log = get_logger(__name__)

#: The income table lives in this band of the sheet, on every version of
#: the form — «3. Доходы» sits under the person and over the deductions.
BAND = (0.33, 0.58)
#: A rule counts as a rule when it runs across most of a table's width.
RULE_INK = 0.85
#: How far the baseline sits above the row's bottom rule, as a share of
#: the row's height — measured off the office's own filled sample.
BASELINE_LIFT = 0.22
#: «3. Доходы, облагаемые по ставке ___ %» — the «%» is the landmark the
#: figure is set against. On the office's ТРАЙД sheet the printed «13»
#: stops this far short of the sign; its МЕГАПОЛИС sheet leaves the spot
#: empty altogether, which is why the program writes it either way.
RATE_GAP = 0.0133
#: How wide a «%» is, as a share of the page — anything else at the end of
#: that line is not the sign, and the rate is left where the spec put it.
RATE_SIGN = (0.007, 0.022)
#: How tall a «%» stands, in ems. Taller than a digit, which is why the
#: figure beside it is not simply the sign's own height: calibrated on the
#: office's ТРАЙД sheet, whose «13» measures 0.0111 of the page.
RATE_SIGN_EM = 0.83


def _page_ink(blank: Path, dpi: int = 200):
    import fitz
    import numpy as np

    with fitz.open(str(blank)) as doc:
        if not doc.page_count:
            return None
        pix = doc[0].get_pixmap(dpi=dpi)
    grey = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
        pix.height, pix.width, pix.n)[:, :, :3].mean(axis=2)
    return grey < 150


def _even_run(rules: list[int]) -> list[int] | None:
    """The nine rules of the eight data rows, out of everything found.

    The table's header («Месяц | Код дохода | Сумма дохода…») is two lines
    tall and rules its own box, so the first rule found is NOT the first
    row. The data rows are the ones evenly spaced, so the longest stretch
    of equal gaps is the table.
    """
    if len(rules) < ROWS_PER_TABLE + 1:
        return None
    best: list[int] = []
    start = 0
    for i in range(1, len(rules)):
        gap = rules[i] - rules[i - 1]
        first_gap = rules[start + 1] - rules[start] if i > start + 1 else gap
        if abs(gap - first_gap) > max(2.0, first_gap * 0.18):
            start = i - 1
        run = rules[start:i + 1]
        if len(run) > len(best):
            best = run
    if len(best) < ROWS_PER_TABLE + 1:
        return None
    return best[:ROWS_PER_TABLE + 1]


def _runs(flags) -> list[tuple[int, int]]:
    """Where a boolean row turns on and off again."""
    found, start = [], None
    for i, on in enumerate(flags):
        if on and start is None:
            start = i
        elif not on and start is not None:
            found.append((start, i))
            start = None
    if start is not None:
        found.append((start, len(flags)))
    return found


def _rate(dark, table_top: int, width: int, height: int
          ) -> tuple[float, float, float] | None:
    """(«%» left edge, baseline, text size) of the «по ставке» line.

    That line is the last one printed above the table, and the «%» is the
    last thing on it. The sign has no descender, so where its ink stops is
    the baseline, and how tall it is gives the size of the figure beside it.
    """
    top = max(0, table_top - int(0.060 * height))
    foot = max(top + 1, table_top - int(0.004 * height))
    band = dark[top:foot]
    # the LAST thing above the table is the dotted rule the figure sits
    # on, one or two pixels tall — the line wanted is the last one as tall
    # as printed words
    lines = [(a, b) for a, b in _runs(band.mean(axis=1) > 0.004)
             if (b - a) / height >= 0.004]
    if not lines:
        return None
    a, b = lines[-1]
    columns = _runs(band[a:b].mean(axis=0) > 0.02)
    if not columns:
        return None
    x0, x1 = columns[-1]
    if not RATE_SIGN[0] <= (x1 - x0) / width <= RATE_SIGN[1]:
        return None
    inked = [i for i, v in enumerate(band[a:b, x0:x1].mean(axis=1)) if v > 0.02]
    if not inked:
        return None
    baseline = (top + a + inked[-1] + 1) / height
    size = (inked[-1] - inked[0] + 1) / height / RATE_SIGN_EM
    return x0 / width, baseline, size


def detect(blank: Path) -> dict[str, list[float]] | None:
    """This sheet's eight table handles and its rate, or None when unsure.

    Returned the way a saved layout stores them — «key: [x, baseline,
    size]», with x the LEFT edge the editor drags by, so the result can be
    written straight into the firm's arrangement. The rate is only added
    when the «%» was actually found; the table always comes as a set.
    """
    try:
        dark = _page_ink(Path(blank))
    except Exception as exc:                          # noqa: BLE001
        log.warning("2НДФЛ: бланка ўқилмади — %s", exc)
        return None
    if dark is None:
        return None
    height, width = dark.shape

    top, bottom = int(BAND[0] * height), int(BAND[1] * height)
    # the rows: rules that cross the left half of the sheet
    rules = []
    for y in range(top, bottom):
        if dark[y, int(0.07 * width):int(0.45 * width)].mean() > RULE_INK:
            if not rules or y - rules[-1] > 3:
                rules.append(y)
    rows = _even_run(rules)
    if rows is None:
        log.info("2НДФЛ: жадвал қаторлари топилмади (%d та чизиқ)", len(rules))
        return None
    row_height = (rows[-1] - rows[0]) / ROWS_PER_TABLE
    first = (rows[1] - row_height * BASELINE_LIFT) / height
    last = (rows[-1] - row_height * BASELINE_LIFT) / height

    # the columns: verticals that run the whole height of the table
    band = dark[rows[0]:rows[-1]]
    columns = [x for x, _ in _runs(band.mean(axis=0) > RULE_INK)]
    edges = sorted({round(x / width, 4) for x in columns})
    # both tables carry the same five columns, so the edges split in half
    if len(edges) < 10 or len(edges) % 2:
        log.info("2НДФЛ: жадвал устунлари топилмади (%d та)", len(edges))
        return None
    half = len(edges) // 2
    left, right = edges[:half], edges[half:]
    if left[-1] > right[0]:
        return None

    size = round(min(0.0130, row_height / height * 0.80), 5)
    # a saved arrangement holds the LEFT edge the editor drags by, while a
    # cell gives its CENTRE — so each is converted the way the renderer
    # will convert it back
    from src.pdf.ndfl2_renderer import anchor_offset, measured_width
    from src.pdf.ndfl2_spec import ALL_SLOTS

    def _left(key: str, centre: float) -> float:
        return round(centre - anchor_offset(ALL_SLOTS[key], size), 5)

    made: dict[str, list[float]] = {}
    for side, cols in (("left", left), ("right", right)):
        # month | код дохода | сумма дохода — the first three cells
        for part, (a, b) in (("month", (cols[0], cols[1])),
                             ("code", (cols[1], cols[2])),
                             ("money", (cols[2], cols[3]))):
            key = f"{side}_{part}"
            made[key] = [_left(key, (a + b) / 2), round(first, 5), size]
        key = f"{side}_last"
        made[key] = [_left(key, (cols[0] + cols[1]) / 2),
                     round(last, 5), size]
    log.info("2НДФЛ: жадвал ўлчанди — қатор %.4f..%.4f, %d устун",
             first, last, len(edges))

    sign = _rate(dark, rules[0], width, height)
    if sign is not None:
        pct, baseline, rate_size = sign
        rate_size = round(min(0.0160, max(0.0080, rate_size)), 5)
        # the figure's RIGHT edge stops short of the sign; the arrangement
        # holds its left edge, and «13» is what the slot is measured with
        span = measured_width(ALL_SLOTS["rate"], rate_size)
        made["rate"] = [round(pct - RATE_GAP - span, 5),
                        round(baseline, 5), rate_size]
        log.info("2НДФЛ: ставка ўлчанди — «%%» %.4f да, чизиқ %.4f",
                 pct, baseline)
    return made


def with_detected(blank: Path, layout: dict) -> dict:
    """The firm's arrangement, with the table filled in if it has none.

    What the office dragged always wins: detection only fills what is not
    there yet.
    """
    fields = dict((layout or {}).get("fields") or {})
    wanted = ["rate"] + [f"{side}_{part}"
                         for side in ("left", "right")
                         for part in ("month", "code", "money", "last")]
    if all(key in fields for key in wanted):
        return layout or {}
    found = detect(blank)
    if not found:
        return layout or {}
    for key, spot in found.items():
        fields.setdefault(key, spot)
    return {**(layout or {}), "fields": fields}
