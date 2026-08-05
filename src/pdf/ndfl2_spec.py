"""2 НДФЛ — «Справка о доходах и суммах налога физического лица».

Where every value lands on the office's own blank, measured off the pair
the office handed over: its empty sheet and the same sheet filled in. The
blank already carries the firm — ОКТМО, ИНН, КПП, телефон, налоговый
агент, his signature and the stamp — so the program writes only the
worker, his months and the four sums at the foot.

Everything is a SHARE of the page, so a firm that scans its own sheet a
shade differently is put right by dragging in «📐», not by editing code.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Arial Bold — the face the office's own справка is typed in.
FONT = "OfisArialBold"
INK = (0.0, 0.0, 0.0)


@dataclass(frozen=True)
class Slot:
    """One printed value: where it starts, how big, and how it sits."""

    x: float
    baseline: float
    size: float = 0.0116
    #: "left" | "centre" | "right" — «right» is what the money columns use
    align: str = "left"
    #: what to show while the office drags it
    sample: str = "0"
    label: str = ""


#: ---- 2. Сведения о физическом лице ------------------------------------
PERSON: dict[str, Slot] = {
    "inn": Slot(0.1016, 0.2790, 0.0116, "left", "771686014578",
                "ИНН физлица"),
    "surname": Slot(0.1445, 0.2995, 0.0116, "left", "Эшдавлатов",
                    "Фамилия"),
    "name": Slot(0.4407, 0.2995, 0.0116, "left", "Маъруфджон", "Имя"),
    "patronymic": Slot(0.7999, 0.2995, 0.0116, "left", "Негъматуллаевич",
                       "Отчество"),
    "birth_d": Slot(0.4178, 0.3165, 0.0116, "left", "10",
                    "Дата рождения — число"),
    "birth_m": Slot(0.4577, 0.3165, 0.0116, "left", "05",
                    "Дата рождения — месяц"),
    "birth_y": Slot(0.4946, 0.3165, 0.0116, "left", "1996",
                    "Дата рождения — год"),
    "doc_code": Slot(0.3730, 0.3358, 0.0116, "left", "10",
                     "Код документа"),
    "doc_number": Slot(0.6385, 0.3358, 0.0116, "left", "402716706",
                       "Серия и номер документа"),
}

#: ---- «за … год от … . … . …» — the sheet's own date -------------------
#: The office's blank carries a date already, so these are drawn over a
#: small whiteout (see ``DATE_CLEAR``) and always read as the operator
#: typed them.
DATE: dict[str, Slot] = {
    "year": Slot(0.4150, 0.1418, 0.0113, "centre", "2026", "За какой год"),
    "day": Slot(0.5285, 0.1418, 0.0113, "centre", "05", "Справка — число"),
    "month": Slot(0.5680, 0.1418, 0.0113, "centre", "08", "Справка — месяц"),
    "date_year": Slot(0.6195, 0.1418, 0.0113, "centre", "2026",
                      "Справка — год"),
}
#: One narrow (x0, y0, x1, y1) per figure. The words «за», «год», «от»
#: between them survive, and so does the dotted rule each figure sits on:
#: the digits end at 0.1413 and the rule runs at 0.1424–0.1437, so the
#: wipe stops at 0.1420.
DATE_CLEAR = (
    (0.3900, 0.1325, 0.4420, 0.1420),
    (0.5115, 0.1325, 0.5460, 0.1420),
    (0.5510, 0.1325, 0.5850, 0.1420),
    (0.5900, 0.1325, 0.6490, 0.1420),
)

#: ---- 3. Доходы, облагаемые по ставке ---------------------------------
#: Two tables of eight rows: months 1–8 on the left, 9–12 on the right.
ROW_FIRST = 0.4067
ROW_PITCH = 0.01527
ROWS_PER_TABLE = 8

#: cell centres, measured off the blank's own rules
LEFT_MONTH, LEFT_CODE = 0.0820, 0.1454
LEFT_MONEY = (0.1771, 0.2963)          # the cell the sum is centred in
RIGHT_MONTH, RIGHT_CODE = 0.4991, 0.5424
RIGHT_MONEY = (0.6378, 0.7570)

#: «2000» — «Доходы, полученные по трудовому договору»
INCOME_CODE = "2000"
MONTH_SIZE = 0.0116

#: ---- 5. Общая сумма дохода и сумма налога ----------------------------
#: All four are right-aligned against their cell's right edge.
TOTALS: dict[str, Slot] = {
    "total_income": Slot(0.4589, 0.6371, 0.0116, "right", "1 165 000.00",
                         "Общая сумма дохода"),
    "tax_base": Slot(0.9474, 0.6362, 0.0116, "right", "1 165 000.00",
                     "Налоговая база"),
    "tax_calculated": Slot(0.4589, 0.6630, 0.0116, "right", "151 450,00",
                           "Сумма налога исчисленная"),
    "tax_withheld": Slot(0.4601, 0.7243, 0.0116, "right", "151 450,00",
                         "Сумма налога удержанная"),
}

#: The rate the справка is issued at — printed on the blank as «13 %».
TAX_RATE = 0.13

ALL_SLOTS: dict[str, Slot] = {**DATE, **PERSON, **TOTALS}
