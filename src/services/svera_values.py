"""Flatten a student + profession + date + counters into the СФЕРА field map.

Page 1 (Протокол) uses the nominative ФИО; page 2 (Удостоверение) addresses the
holder in the dative case («Шукурову Зарифу Севиновичу»). Both pages share the
profession text and the same ПО number.

Every line the centre's real documents carry — including the fixed wording of
the protocol header and the приказ line — is typeset by the program, because
the bundled blanks contain only the letterhead, the commission block, the table
frame and the signatures.
"""

from __future__ import annotations

from datetime import date

from src.domain.profession import Profession
from src.pdf.formatters import _date_dmy, _date_dmy_g, _date_long_g
from src.utils.ru_names import to_dative_parts

CENTRE_NAME = 'ООО УЦ "СФЕРА"'
CITY = "Ижевск"
PROTOCOL_SUBTITLE = "заседания комиссии по проверке знаний профессионального обучения"
DEFAULT_HOURS = 160
DEFAULT_PRIKAZ_NO = 4


def _title(s: str) -> str:
    return (s or "").strip().title()


def format_reg13(n: int) -> str:
    """1800359856150 → '180035 9856150' (6 + space + 7 digits)."""
    return f"{n // 10_000_000:06d} {n % 10_000_000:07d}"


def _with_note(base: str, profession: Profession) -> str:
    return base + (f" ({profession.note})" if profession.note else "")


def build_svera_values(
    surname: str,
    name: str,
    patronymic: str | None,
    profession: Profession,
    *,
    issue_date: date,
    photo_path: str | None,
    po_number: int,
    udo_number: int,
    reg13: int,
    stamp_path: str | None = None,
    hours: int = DEFAULT_HOURS,
    prikaz_no: int = DEFAULT_PRIKAZ_NO,
) -> dict[str, object]:
    fio_nom = "\n".join(
        x for x in (_title(surname), _title(name), _title(patronymic or "")) if x
    )
    dative = to_dative_parts(surname, name, patronymic)
    long_date = _date_long_g(issue_date)

    values: dict[str, object] = {
        # ---------- протокол ----------
        "svera.protocol_title": f"ПРОТОКОЛ № ПО{po_number}",
        "svera.protocol_sub": PROTOCOL_SUBTITLE,
        "svera.date_short": f"от {_date_dmy(issue_date)}",
        "svera.date_long_top": long_date,
        "svera.gorod": CITY,
        "svera.prikaz": (f"В соответствии с приказом от {long_date} "
                         f"№ {prikaz_no} комиссия в составе:"),
        "svera.proverka": (
            "провела проверку знаний по программе профессионального обучения "
            f"{_with_note(profession.quoted, profession)} в объёме {hours} ч."
        ),
        "svera.fio_protocol": fio_nom,
        # «Результат проверки знаний, регистрац. №, номер свидетельства»
        "svera.result": f"Сдал,\n{udo_number}\n{format_reg13(reg13)}",
        "svera.zaklyuchenie": _with_note(profession.qualification_short, profession),

        # ---------- удостоверение ----------
        "svera.udo_title": f"УДОСТОВЕРЕНИЕ № {udo_number}",
        "svera.fio_udo_left": "\n".join(dative),
        "svera.prof_udo_left": f"“{_with_note(profession.name, profession)}”",
        "svera.date_udo": f"Дата выдачи: {_date_dmy_g(issue_date)}",
        "svera.fio_udo_right": " ".join(dative),
        "svera.qual_udo_right": _with_note(profession.qualification_full, profession),
        "svera.osnovanie": (f"{CENTRE_NAME} № ПО{po_number} "
                            f"от {_date_dmy_g(issue_date)}"),
    }
    if photo_path:
        values["svera.photo"] = photo_path
    if stamp_path:
        values["svera.stamp_left"] = stamp_path
        values["svera.stamp_right"] = stamp_path
    return values
