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

#: Arial Bold — the face the office's own справка is typed in, named the
#: way the font picker in «📐» names it. The weight is a flag of its own,
#: so the office may keep the boldness while changing the face, and the
#: two travel together through the saved arrangement.
FAMILY = "Arial"
BOLD = True
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

#: Cell CENTRES, measured off the bundled blank's own rules. The right
#: table's were a column out at first — its «Месяц» cell begins at 0.5109,
#: it is not centred on it — which is what pushed the months 9–12 outside
#: their boxes. Both tables are now taken from the rules themselves.
LEFT_MONTH, LEFT_CODE, LEFT_MONEY = 0.0820, 0.1454, 0.2367
RIGHT_MONTH, RIGHT_CODE, RIGHT_MONEY = 0.5424, 0.6058, 0.6974

#: «2000» — «Доходы, полученные по трудовому договору»
INCOME_CODE = "2000"
MONTH_SIZE = 0.0116

#: The month tables, as things the office can DRAG. Every firm scans its
#: own sheet — the office's «ООО МЕГАПОЛИС» blank is 842 points tall where
#: the bundled one is 822, and its right-hand table sits elsewhere — so the
#: table cannot be fixed in code. Four handles per table say everything:
#: the three columns of the FIRST row, and the month column of the LAST
#: row, which is what gives the row spacing.
_LAST_ROW = ROW_FIRST + (ROWS_PER_TABLE - 1) * ROW_PITCH
TABLE: dict[str, Slot] = {
    "left_month": Slot(LEFT_MONTH, ROW_FIRST, MONTH_SIZE, "centre", "1",
                       "Чап жадвал — ой рақами (1-қатор)"),
    "left_code": Slot(LEFT_CODE, ROW_FIRST, MONTH_SIZE, "centre",
                      INCOME_CODE, "Чап жадвал — код дохода"),
    "left_money": Slot(LEFT_MONEY, ROW_FIRST, MONTH_SIZE, "centre",
                       "150 000,00 ₽", "Чап жадвал — сумма дохода"),
    "left_last": Slot(LEFT_MONTH, _LAST_ROW, MONTH_SIZE, "centre", "8",
                      "Чап жадвал — ОХИРГИ қатор (қатор оралиғи)"),
    "right_month": Slot(RIGHT_MONTH, ROW_FIRST, MONTH_SIZE, "centre", "9",
                        "Ўнг жадвал — ой рақами (1-қатор)"),
    "right_code": Slot(RIGHT_CODE, ROW_FIRST, MONTH_SIZE, "centre",
                       INCOME_CODE, "Ўнг жадвал — код дохода"),
    "right_money": Slot(RIGHT_MONEY, ROW_FIRST, MONTH_SIZE, "centre",
                        "500 600,00 ₽", "Ўнг жадвал — сумма дохода"),
    "right_last": Slot(RIGHT_MONTH, _LAST_ROW, MONTH_SIZE, "centre", "16",
                       "Ўнг жадвал — ОХИРГИ қатор (қатор оралиғи)"),
}

#: «Доходы, облагаемые по ставке ___ %» — the office's ТРАЙД sheet carries
#: «13» already and its МЕГАПОЛИС sheet leaves the spot empty, so the
#: program always writes it, over a wipe of its own box. Measured off the
#: bundled sheet: the digits run 0.3757–0.3910 (centre 0.3834) and sit on
#: 0.3601, with the dotted rule below at 0.3626 and the «%» from 0.4043.
#: A firm whose sheet puts the sign elsewhere has this measured off it.
RATE: dict[str, Slot] = {
    "rate": Slot(0.3834, 0.3601, 0.0111, "centre", "13",
                 "Ставка (13 %)"),
}

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

ALL_SLOTS: dict[str, Slot] = {**DATE, **PERSON, **RATE, **TOTALS, **TABLE}

#: The handles that describe the month tables rather than printing a value
#: of their own — the renderer reads them, the editor drags them.
TABLE_KEYS = frozenset(TABLE)
