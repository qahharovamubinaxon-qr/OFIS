"""Manual-fill support: the 16-field table spec + building an Employee from it.

Used by the offline fallback (no AI). Each row is labeled with what goes there,
exactly as the owner asked. Fields 11 (patent expiry), 14 (reg number) and 15
(ФИО+гражданство) are computed downstream, so the operator never types them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from src.common.errors import ValidationError
from src.domain.documents import Passport, Patent
from src.domain.employee import Employee

DEFAULT_PROFESSION = "ПОДСОБНЫЙ РАБОЧИЙ"


@dataclass(frozen=True)
class ManualField:
    key: str
    label_ru: str
    label_uz: str
    required: bool = False
    is_date: bool = False


# The operator-entered rows (marks 1–10, 12, 16). Dates as ДД.ММ.ГГГГ.
MANUAL_FIELDS: list[ManualField] = [
    ManualField("surname", "1. Фамилия", "1. Familiya", required=True),
    ManualField("name", "2. Имя", "2. Ism", required=True),
    ManualField("patronymic", "3. Отчество", "3. Otasining ismi"),
    ManualField("citizenship", "4. Гражданство", "4. Fuqaroligi"),
    ManualField("birth_date", "5. Дата рождения (ДД.ММ.ГГГГ)", "5. Tug'ilgan sana", is_date=True),
    ManualField("passport_series", "6a. Паспорт серия", "6a. Pasport seriya"),
    ManualField("passport_number", "6b. Паспорт номер", "6b. Pasport raqami", required=True),
    ManualField("passport_issue_date", "7. Дата выдачи паспорта", "7. Pasport berilgan sana", is_date=True),
    ManualField("passport_issued_by", "8. Кем выдан паспорт", "8. Pasportni bergan"),
    ManualField("patent_series", "9a. Патент серия", "9a. Patent seriya"),
    ManualField("patent_number", "9b. Патент номер", "9b. Patent raqami"),
    ManualField("patent_issue_date", "10. Дата выдачи патента", "10. Patent berilgan sana", is_date=True),
    ManualField("patent_issued_by", "12. Кем выдан патент", "12. Patentni bergan"),
    ManualField("profession", "16. Должность", "16. Lavozimi (bo'sh = ПОДСОБНЫЙ РАБОЧИЙ)"),
]


def parse_date(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValidationError(f"Invalid date: {value}", context={"value": value})


def build_employee(values: dict[str, str], company_id: UUID, *, contract_date: date) -> Employee:
    """Assemble a validated Employee from the manual table values."""
    v = {k: (values.get(k) or "").strip() for k in {f.key for f in MANUAL_FIELDS}}
    if not v["surname"] or not v["name"]:
        raise ValidationError("Surname and name are required")

    profession = v["profession"] or DEFAULT_PROFESSION
    passport = Passport(
        surname=v["surname"], name=v["name"], patronymic=v["patronymic"] or None,
        nationality=v["citizenship"] or None, series=v["passport_series"] or None,
        number=v["passport_number"], birth_date=parse_date(v["birth_date"]),
        issue_date=parse_date(v["passport_issue_date"]), issued_by=v["passport_issued_by"] or None,
    )
    patent = None
    if v["patent_number"]:
        patent = Patent(
            series=v["patent_series"] or None, number=v["patent_number"],
            issue_date=parse_date(v["patent_issue_date"]), issued_by=v["patent_issued_by"] or None,
            profession=profession,
        )
    return Employee(
        company_id=company_id, passport=passport, patent=patent,
        profession=profession, contract_date=contract_date,
    )
