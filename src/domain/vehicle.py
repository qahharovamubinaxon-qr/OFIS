"""What an ОСАГО policy needs about a car and the people who drive it.

Both come off photographs: the СТС (свидетельство о регистрации ТС, front and
back) for the car and its owner, and each driver's водительское удостоверение.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict


def _clean(value: str | None) -> str:
    return " ".join((value or "").split())


class Sts(BaseModel):
    """Свидетельство о регистрации транспортного средства."""

    model_config = ConfigDict(str_strip_whitespace=True)

    series: str = ""            # 50 ОЕ
    number: str = ""            # 202246
    plate: str = ""             # Т566ВЕ40 — государственный регистрационный знак
    vin: str = ""               # KMHDN41BP3U633162
    mark: str = ""              # Hyundai
    model: str = ""             # Elantra
    year: str = ""              # год выпуска
    category: str = ""          # B
    owner_fio: str = ""         # собственник, as printed on the back
    owner_address: str = ""
    issue_date: date | None = None

    @property
    def vehicle(self) -> str:
        """«Hyundai Elantra» — as the policy prints it on one line."""
        return _clean(f"{self.mark} {self.model}")

    @property
    def document(self) -> str:
        """«50ОЕ 202246» — the СТС as one string."""
        return _clean(f"{self.series} {self.number}")


class DriverLicence(BaseModel):
    """Водительское удостоверение of one person allowed to drive."""

    model_config = ConfigDict(str_strip_whitespace=True)

    surname: str = ""
    name: str = ""
    patronymic: str = ""
    series: str = ""
    number: str = ""
    birth_date: date | None = None
    issue_date: date | None = None
    expiry_date: date | None = None
    categories: str = ""

    @property
    def fio(self) -> str:
        return _clean(f"{self.surname} {self.name} {self.patronymic}")

    @property
    def licence(self) -> str:
        """«AF2970819» or «5036 634917» — however the licence itself is split."""
        return _clean(f"{self.series} {self.number}")

    def is_empty(self) -> bool:
        return not (self.fio or self.licence)
