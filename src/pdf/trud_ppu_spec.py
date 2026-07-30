"""Where every value sits on the ТРУД ППУ package, as fractions of the page.

Three sheets:

* **sheet 1** — the ППУ front, exactly as :mod:`src.pdf.ppu_spec` lays it out.
  Nothing is duplicated here: the same slots, the same filling, the same photo
  window, so a correction to the ППУ front corrects this too.
* **sheet 2** — the Госуслуги patent page. Seven values, numbered ①–⑦ by the
  office on the copy it handed over.
* **sheet 3** — the Госуслуги «Уведомления о трудовой деятельности» page. Two
  values, ⑧ and ⑨.

Sheets 2 and 3 are photographs of a screen, so nothing on them is a printed
rule: the values simply sit where the site put them. Both were measured, not
guessed — the office handed over a filled sheet AND the same sheet with the
values cleared, framed identically, so subtracting one from the other left
exactly the ink of each value and its box could be read off directly. The
numbers below are those boxes: ``x`` the left edge, ``baseline`` the bottom of
the digits, both as shares of the page.

Fractions rather than points, because the office may re-photograph the pages at
another size; a fraction lands correctly on whatever comes in.
"""

from __future__ import annotations

from src.pdf.ppu_spec import BLACK, SANS, Slot

#: The three blanks of a package. Sheet 1 is taken from the ППУ template the
#: operator already selected, so only sheets 2 and 3 are uploaded here.
PAGE_FILES = ("page2.pdf", "page3.pdf")

#: The Госуслуги link colour — «Номер дела» and «Источник уведомления» are
#: links on the site and read blue on the office's own filled sheet.
LINK = (0.10, 0.44, 0.77)

#: Sheets 2 and 3 are photographs of a screen, so their own text is never solid
#: black. Values laid on at full strength stand out as printed-on-top; at just
#: under nine parts in ten they sit in the picture the way the site's own text
#: does. The office asked for 85–90%.
TEXT_OPACITY = 0.87

#: Every value on sheet 2 is the site's own UI size: 17.9 pt on the 900 pt-high
#: sheet the office handed over.
_P2 = 0.0199

#: Sheet 2 — the patent page.
PAGE2: dict[str, Slot] = {
    # ① «Серия и номер» — «77 № 2400328451»
    "patent_serial": Slot(0.3609, 0.4583, _P2, SANS, BLACK, width=0.15),
    # ② «Дата выдачи»
    "issue_date":    Slot(0.5975, 0.4567, _P2, SANS, BLACK, width=0.10),
    # ③ «Срок действия» — issued and expiring, ONE ABOVE THE OTHER, the first
    #    line carrying the dash exactly as the site prints it
    "term_from":     Slot(0.6950, 0.4439, _P2, SANS, BLACK, width=0.10),
    "term_to":       Slot(0.6950, 0.4728, _P2, SANS, BLACK, width=0.10),
    # ④ «Номер дела» — the patent number and series the other way round
    "case_number":   Slot(0.1462, 0.6556, _P2, SANS, LINK, width=0.15),
    # ⑤ «Дата создания дела» — the patent's issue date again
    "case_date":     Slot(0.5878, 0.6561, _P2, SANS, BLACK, width=0.10),
    # ⑥ «Дата приема уведомления» — the employment contract's date
    "contract_date": Slot(0.1512, 0.8694, _P2, SANS, BLACK, width=0.10),
    # ⑦ «Источник уведомления» — the firm on the contract
    "firm":          Slot(0.5544, 0.8667, _P2, SANS, LINK, width=0.21),
}

#: Sheet 3 — the notification page. Read off the office's own filled copy,
#: where both values are real text objects, so these are its exact baselines.
PAGE3: dict[str, Slot] = {
    # ⑧ the number under the page title — «№ 4785796716»
    "uved_number": Slot(0.0734, 0.2957, 0.01573, SANS, BLACK, width=0.34),
    # ⑨ «Гражданин» — the worker's Ф.И.О.
    "fio":         Slot(0.1331, 0.5988, 0.01311, SANS, BLACK, width=0.62),
}
