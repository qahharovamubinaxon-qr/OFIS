"""Flatten a student + profession + date + counters into the СФЕРА field map.

Page 1 (Протокол) uses the nominative ФИО; page 2 (Удостоверение) addresses the
holder in the dative case («Шукурову Зарифу Севиновичу»). Both pages share the
profession text and the same ПО number; the 13-digit reg number is protocol-only.
"""

from __future__ import annotations

from datetime import date

from src.domain.profession import Profession
from src.pdf.formatters import _date_dmy, _date_long_g
from src.utils.ru_names import to_dative_parts

_PROVERKA = (
    "провела проверку знаний по программе профессионального обучения "
    "{quoted} в объёме 160 ч."
)


def _title(s: str) -> str:
    return (s or "").strip().title()


def format_reg13(n: int) -> str:
    """1800359856150 → '180035 9856150' (6 + space + 7 digits)."""
    return f"{n // 10_000_000:06d} {n % 10_000_000:07d}"


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
) -> dict[str, object]:
    fio_nom = "\n".join(x for x in (_title(surname), _title(name), _title(patronymic or "")) if x)
    dative = to_dative_parts(surname, name, patronymic)

    def note(base: str) -> str:
        return base + (f"\n({profession.note})" if profession.note else "")

    values: dict[str, object] = {
        # --- protocol ---
        "svera.po_protocol": str(po_number),
        "svera.date_short": _date_dmy(issue_date),
        "svera.date_long_top": _date_long_g(issue_date),
        "svera.date_long_prikaz": _date_long_g(issue_date),
        "svera.proverka": _PROVERKA.format(quoted=profession.quoted),
        "svera.fio_protocol": fio_nom,
        "svera.reg13": format_reg13(reg13),
        "svera.zaklyuchenie": note(profession.qualification_short),
        # --- udostoverenie ---
        "svera.udo_number": str(udo_number),
        "svera.fio_udo_left": "\n".join(dative),
        "svera.prof_udo_left": note(profession.quoted),
        "svera.date_udo": _date_dmy(issue_date),
        "svera.fio_udo_right": " ".join(dative),
        "svera.qual_udo_right": note(profession.qualification_full),
        "svera.po_udo": str(po_number),
        "svera.date_udo_right": _date_dmy(issue_date),
    }
    if photo_path:
        values["svera.photo"] = photo_path
    return values
