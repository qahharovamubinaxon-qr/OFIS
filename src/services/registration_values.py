"""Flatten passport + patent + registration expiry into the field map the
registration template expects (``reg.*`` ids in mapping.v1.json).

Business rules (owner):
* ФИО + гражданство come from the **patent** (printed correctly in Russian),
  falling back to the passport when the patent lacks them.
* birth date, gender, passport серия/№, дата выдачи, срок действия до come from
  the **passport**.
* «Заявленный срок пребывания до» (page 1) and «Поставлен на учет до» (page 2)
  are both the operator-entered registration expiry date.

Date sub-fields (д/м/г) all receive the same ISO date; the mapping formatter
extracts the needed part.
"""

from __future__ import annotations

from datetime import date

from src.domain.documents import Passport, Patent
from src.domain.enums import Gender

_MARK = "V"


def _iso(d: date | None) -> str:
    return d.isoformat() if d else ""


def build_registration_values(
    passport: Passport,
    patent: Patent | None,
    *,
    registration_expiry: date,
) -> dict[str, str]:
    """Produce the flat ``{field_id: value}`` map for the registration form."""
    surname = (patent.holder_surname if patent else None) or passport.surname
    name = (patent.holder_name if patent else None) or passport.name
    patronymic = (patent.holder_patronymic if patent else None) or passport.patronymic or ""
    citizenship = (patent.holder_citizenship if patent else None) or passport.nationality or ""

    birth = _iso(passport.birth_date)
    issue = _iso(passport.issue_date)
    expiry = _iso(passport.expiry_date)
    reg = _iso(registration_expiry)

    values: dict[str, str] = {
        "reg.surname": surname,
        "reg.name": name,
        "reg.patronymic": patronymic,
        "reg.citizenship": citizenship,
        # birth date (passport)
        "reg.birth.d": birth,
        "reg.birth.m": birth,
        "reg.birth.y": birth,
        # passport серия / №
        "reg.passport.series": passport.series or "",
        "reg.passport.number": passport.number,
        # passport дата выдачи
        "reg.passport.issue.d": issue,
        "reg.passport.issue.m": issue,
        "reg.passport.issue.y": issue,
        # passport срок действия до
        "reg.passport.expiry.d": expiry,
        "reg.passport.expiry.m": expiry,
        "reg.passport.expiry.y": expiry,
        # заявленный срок пребывания до (= registration expiry)
        "reg.stay_until.d": reg,
        "reg.stay_until.m": reg,
        "reg.stay_until.y": reg,
        # page 2: поставлен на учет до (= registration expiry)
        "reg.registered_until.d": reg,
        "reg.registered_until.m": reg,
        "reg.registered_until.y": reg,
    }

    # Пол — mark the matching checkbox only.
    if passport.gender == Gender.MALE:
        values["reg.gender.male"] = _MARK
    elif passport.gender == Gender.FEMALE:
        values["reg.gender.female"] = _MARK

    return {k: v for k, v in values.items() if v != ""}
