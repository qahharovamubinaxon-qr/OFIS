"""УЗБ СПРАВКАЛАР — where each value goes on the office's four sheets.

The office marked every value that changes from worker to worker with a
BLUE rule under it. Those rules were found by colour and measured, and
what is below is where each one sits. The text stands ON the rule, so a
value's baseline is the rule's own line.

Two maps, not four: certificates 1, 2 and 3 came back with the SAME
eighteen rules in the SAME places — they are one sheet with different
words — while certificate 4 lays its worker out down the page and has its
own. Everything is a share of the sheet, and every one of them can be
dragged in «📐 Созлаш», because a first measurement off a scan is a
starting point and the office's own eye is the judge.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The office's sheets are plain A4.
PAGE_W, PAGE_H = 595.0, 842.0

INK = (0.0, 0.0, 0.0)
FAMILY = "Arial"
#: The big four-digit code at the foot is set larger than everything else.
CODE_SIZE = 0.0300
SIZE = 0.0110


@dataclass(frozen=True)
class Slot:
    """One printed value: where it starts, how big, and how it sits."""

    x: float
    baseline: float
    size: float = SIZE
    bold: bool = False
    colour: tuple[float, float, float] = INK
    family: str = FAMILY
    #: "left" | "centre" | "right"
    align: str = "left"
    sample: str = ""
    label: str = ""


#: ---- 1, 2, 3-справка — one map, three sets of words -------------------
#: «хулқ-атвори», «маоши» and «оила ҳолати» are the same sheet: their blue
#: rules came back identical to four decimal places.
SHEET123: dict[str, Slot] = {
    "made_at": Slot(0.7768, 0.0430, 0.0100, False, INK, FAMILY, "left",
                    "2026-07-09 10:15:08", "Юқори ўнг — сана ва вақт"),
    "number_tail": Slot(0.2683, 0.2528, 0.0100, False, INK, FAMILY, "left",
                        "1547-1548", "№ — охирги иккита гуруҳ"),
    "latin_name": Slot(0.6446, 0.2562, 0.0095, False, INK, FAMILY, "left",
                       "ABDULLAEV BAKHODIRJON MUKUMOVICH",
                       "Документ выдан — лотинча ФИО"),
    "pinfl_top": Slot(0.8445, 0.2710, 0.0085, False, INK, FAMILY, "left",
                      "31301954050087", "Юқоридаги ПИНФЛ"),
    "created": Slot(0.2820, 0.2750, 0.0100, False, INK, FAMILY, "left",
                    "2026-07-09", "Дата создания документа"),
    "request_no": Slot(0.1805, 0.2910, 0.0100, False, INK, FAMILY, "left",
                       "1094441630", "Номер заявки"),
    "issued_at": Slot(0.2780, 0.4375, 0.0105, False, INK, FAMILY, "left",
                      "2026-07-09 10:15:08", "Дата выдачи справки"),
    "fio": Slot(0.1410, 0.5230, 0.0110, False, INK, FAMILY, "left",
                "АБДУЛЛАЕВ БАХОДИРЖОН МУКУМОВИЧ", "Ф.И.О."),
    "passport": Slot(0.3086, 0.5413, 0.0110, False, INK, FAMILY, "left",
                     "FA3445084", "Серия ва номер паспорта"),
    "pinfl": Slot(0.1700, 0.5538, 0.0110, False, INK, FAMILY, "left",
                  "31301954050087", "ПИНФЛ"),
    "birth_date": Slot(0.2224, 0.5772, 0.0110, False, INK, FAMILY, "left",
                       "25.05.1973", "Дата рождения"),
    "code": Slot(0.7083, 0.6986, CODE_SIZE, True, INK, FAMILY, "left",
                 "3255", "Пастдаги 4 хонали код"),
}

#: ---- 4-справка — «ишчининг справка потверждениеси» ---------------------
#: Its worker runs down the page, a line per value, so it keeps its own map.
SHEET4: dict[str, Slot] = {
    "made_at": Slot(0.7865, 0.0395, 0.0100, True, INK, FAMILY, "left",
                    "2026-07-28 13:03:46", "Юқори ўнг — сана ва вақт"),
    "number_tail": Slot(0.2853, 0.2043, 0.0100, False, INK, FAMILY, "left",
                        "9330-6055", "№ — охирги иккита гуруҳ"),
    "latin_name": Slot(0.6696, 0.2043, 0.0095, False, INK, FAMILY, "left",
                       "ERGASHEV UMIDJON SHUKHRAT UGLI",
                       "Документ выдан — лотинча ФИО"),
    "created": Slot(0.2675, 0.2169, 0.0100, False, INK, FAMILY, "left",
                    "2026-07-28", "Дата создания документа"),
    "pinfl_top": Slot(0.8018, 0.2169, 0.0085, False, INK, FAMILY, "left",
                      "50210025720042", "Юқоридаги ПИНФЛ"),
    "request_no": Slot(0.1821, 0.2311, 0.0100, False, INK, FAMILY, "left",
                       "170387888", "Номер заявки"),
    "surname": Slot(0.2160, 0.3047, 0.0110, False, INK, FAMILY, "left",
                    "ЭРГАШЕВ", "Фамилия"),
    "name": Slot(0.2160, 0.3335, 0.0110, False, INK, FAMILY, "left",
                 "УМИДЖОН", "Имя"),
    "patronymic": Slot(0.2160, 0.3623, 0.0110, False, INK, FAMILY, "left",
                       "ШУХРАТ УГЛИ", "Отчество"),
    "birth_date": Slot(0.2160, 0.4520, 0.0110, False, INK, FAMILY, "left",
                       "02.10.2002", "Год рождения"),
    "pinfl": Slot(0.2160, 0.5040, 0.0110, False, INK, FAMILY, "left",
                  "50210025720042", "ПИНФЛ"),
    "issued_at": Slot(0.2160, 0.6060, 0.0110, False, INK, FAMILY, "left",
                      "28.07.2026 13:03", "Дата выдачи справки"),
    "code": Slot(0.7083, 0.7360, CODE_SIZE, True, INK, FAMILY, "left",
                 "1548", "Пастдаги 4 хонали код"),
}

#: certificate number → its own map
SHEETS: dict[int, dict[str, Slot]] = {1: SHEET123, 2: SHEET123,
                                      3: SHEET123, 4: SHEET4}

#: Where the chosen firm's seal starts out, as «left, BOTTOM, height».
SEAL_DEFAULT = (0.6200, 0.8200, 0.1300)
SEAL_KEY = "img_seal"
SEAL_LABEL = "⬤ ФИРМА ПЕЧАТИ"


def slots_of(sheet: int) -> dict[str, Slot]:
    return SHEETS.get(sheet, SHEET123)
