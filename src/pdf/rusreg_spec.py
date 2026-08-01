"""Where every value sits on the РУС РЕГ blank — «ИШЧИНИ РЕГИСТРАЦИЯСИ».

The office registers its **Russian-citizen** workers at a flat the firm
provides, on a form of its own: a свидетельство о регистрации по месту
пребывания. Everything the program prints goes on one of the form's ruled
lines, so the numbers here were measured off the office's own filled sheet by
finding those rules — 21 of them — and reading their position back.

Positions are **shares of the page**, never points. The office scans and
re-prints its blanks, and a blank that comes back at another size or margin
would otherwise put every value in the wrong place. A share survives all of it,
and the same numbers still mean something after the operator has dragged a
value with the mouse (:mod:`src.ui.widgets.layout_editor`).

``x`` is where the value starts, ``baseline`` is where it sits — a little above
its rule, the way a pen writes on a line — and ``size`` is the type size, also
as a share of the page height so it scales with the sheet.

To nudge one value: change its three numbers here, or — easier — open
«📐 Матнларни жойлаш» in the section and drag it.
"""

from __future__ import annotations

#: The ruled lines, measured on the office's own sheet. Each is
#: ``(x, baseline, size)`` as a share of page width / height.
FIELDS: dict[str, tuple[float, float, float]] = {
    # «ИШЧИНИ РЕГИСТРАЦИЯСИ № ____» — the office's own running number
    "reg_number":   (0.5420, 0.0806, 0.0230),

    # Выдано …, ГОДА РОЖДЕНИЯ  /  место рождения
    "fio_born":     (0.1360, 0.1472, 0.0230),
    "birth_place":  (0.0570, 0.1840, 0.0230),

    # …зарегистрирован(а) по месту пребывания по адресу:
    "address_1":    (0.0570, 0.2836, 0.0230),
    "address_2":    (0.0570, 0.3204, 0.0230),

    # На срок с «дд» месяц гггг  по  «дд» месяц гггг
    "from_day":     (0.1960, 0.3781, 0.0230),
    "from_month":   (0.2700, 0.3781, 0.0230),
    "from_year":    (0.4180, 0.3781, 0.0230),
    "to_day":       (0.6240, 0.3781, 0.0230),
    "to_month":     (0.6980, 0.3781, 0.0230),
    "to_year":      (0.8460, 0.3781, 0.0230),

    # Свидетельство выдано к документу…  вид ____, серия ___, № ___
    "doc_kind":     (0.1400, 0.4696, 0.0230),
    "doc_series":   (0.6500, 0.4696, 0.0230),
    "doc_number":   (0.7900, 0.4696, 0.0230),

    # дата выдачи “дд” месяц гггг
    "issued_day":   (0.2610, 0.5313, 0.0230),
    "issued_month": (0.3400, 0.5313, 0.0230),
    "issued_year":  (0.5060, 0.5313, 0.0230),

    # наименование органа, выдавшего документ
    "issued_by":    (0.0570, 0.5831, 0.0230),

    # наименование органа регистрационного учёта — «ОТДЕЛ КАДРОВ ООО …»
    "firm":         (0.0570, 0.7005, 0.0230),

    # (подпись) (фамилия)
    "signer":       (0.4300, 0.8258, 0.0230),

    # «дд» месяц гггг — the day the sheet is issued
    "made_day":     (0.5760, 0.9194, 0.0230),
    "made_month":   (0.6400, 0.9194, 0.0230),
    "made_year":    (0.8130, 0.9194, 0.0230),
}

#: Values that must be centred on their rule rather than started at its left —
#: the day boxes are narrow and a day written flush left looks knocked over.
CENTRED: frozenset[str] = frozenset({
    "from_day", "to_day", "made_day", "issued_day",
    "from_month", "to_month", "issued_month", "made_month",
    "from_year", "to_year", "issued_year", "made_year",
})

#: How wide each centred value's rule is, as a share of the page — needed to
#: centre on it. Measured with the positions above.
WIDTHS: dict[str, float] = {
    "from_day": 0.0328, "to_day": 0.0334, "made_day": 0.0419, "issued_day": 0.0441,
    "from_month": 0.1643, "to_month": 0.1636,
    "issued_month": 0.1749, "made_month": 0.1764,
    "from_year": 0.0654, "to_year": 0.0654,
    "issued_year": 0.0882, "made_year": 0.0839,
}

#: Russian months in the genitive — «31 ИЮЛЯ 2026», never «ИЮЛЬ».
MONTHS_RU: tuple[str, ...] = (
    "ЯНВАРЯ", "ФЕВРАЛЯ", "МАРТА", "АПРЕЛЯ", "МАЯ", "ИЮНЯ",
    "ИЮЛЯ", "АВГУСТА", "СЕНТЯБРЯ", "ОКТЯБРЯ", "НОЯБРЯ", "ДЕКАБРЯ",
)

#: What goes on the «вид» line. Which one is decided by what was uploaded: a
#: grown worker brings a passport, a child brings a birth certificate, and the
#: form must name the document it was actually issued against.
DOC_PASSPORT = "ПАСПОРТ РФ"
DOC_BIRTH = "СВИДЕТЕЛЬСТВО О РОЖДЕНИИ"

#: The form is set in a serif face; the office's own sheets are Times.
FONT = "OfisSerif"

#: Printed at 88% so the values read as filled in rather than typeset — the
#: same weight the other sections use.
TEXT_OPACITY = 0.88

#: An address longer than this many characters is carried onto the second
#: ruled line instead of running off the first.
ADDRESS_WRAP = 78
