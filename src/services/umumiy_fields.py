"""The field vocabulary shared by the УМУМИЙ template store.

A template records WHERE each worker value goes; this module says WHAT each
value is. Keys are stable strings saved inside ``fields.v1.json``, so a template
built today keeps working after the program is updated.
"""

from __future__ import annotations

from datetime import date

from src.domain.documents import Passport, Patent
from src.pdf.formatters import _date_dmy

# key → human label shown in the UI (Uzbek/Russian mix, as the office speaks)
FIELD_LABELS: dict[str, str] = {
    "fio_full": "Ф.И.О. полностью",
    "fio_short": "Фамилия И.О.",
    "surname": "Фамилия",
    "name": "Имя",
    "patronymic": "Отчество",
    "citizenship": "Гражданство",
    "birth_date": "Дата рождения",
    "passport_full": "Паспорт серия и номер",
    "passport_series": "Паспорт: серия",
    "passport_number": "Паспорт: номер",
    "passport_issue_date": "Паспорт: дата выдачи",
    "passport_issued_by": "Паспорт: кем выдан",
    "passport_expiry": "Паспорт: действителен до",
    "patent_full": "Патент серия и номер",
    "patent_series": "Патент: серия",
    "patent_number": "Патент: номер",
    "patent_issue_date": "Патент: дата выдачи",
    "profession": "Профессия",
    "form_date": "Дата документа",
}

FIELD_KEYS = tuple(FIELD_LABELS)


def _initials(passport: Passport) -> str:
    parts = [passport.name, passport.patronymic]
    letters = "".join(f"{p[0]}." for p in parts if p)
    return f"{passport.surname} {letters}".strip()


def field_value(key: str, passport: Passport, patent: Patent | None,
                form_date: date) -> str:
    """Resolve one field key for this worker. Unknown keys give ""."""
    p, pt = passport, patent
    values: dict[str, str] = {
        "fio_full": " ".join(x for x in (p.surname, p.name, p.patronymic) if x),
        "fio_short": _initials(p),
        "surname": p.surname or "",
        "name": p.name or "",
        "patronymic": p.patronymic or "",
        "citizenship": p.nationality or "",
        "birth_date": _date_dmy(p.birth_date) if p.birth_date else "",
        "passport_full": f"{p.series or ''}{p.number or ''}".strip(),
        "passport_series": p.series or "",
        "passport_number": p.number or "",
        "passport_issue_date": _date_dmy(p.issue_date) if p.issue_date else "",
        "passport_issued_by": p.issued_by or "",
        "passport_expiry": _date_dmy(p.expiry_date) if p.expiry_date else "",
        "form_date": _date_dmy(form_date),
    }
    if pt is not None:
        values.update({
            "patent_full": f"{pt.series or ''}{pt.number or ''}".strip(),
            "patent_series": pt.series or "",
            "patent_number": pt.number or "",
            "patent_issue_date": _date_dmy(pt.issue_date) if pt.issue_date else "",
            "profession": pt.profession or "",
        })
    return values.get(key, "")


def apply_case(value: str, case: str | None) -> str:
    """Match the casing the original document used at that spot."""
    if not value or not case:
        return value
    if case == "upper":
        return value.upper()
    if case == "lower":
        return value.lower()
    if case == "title":
        return " ".join(w[:1].upper() + w[1:].lower() for w in value.split())
    return value


def detect_case(sample: str) -> str:
    """Read the casing style off the text that used to sit there."""
    letters = [c for c in sample if c.isalpha()]
    if not letters:
        return "none"
    if all(c.isupper() for c in letters):
        return "upper"
    if all(c.islower() for c in letters):
        return "lower"
    return "none"
