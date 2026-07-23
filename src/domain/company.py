"""Company (employer) model — the static §1–1.2 block of the МВД form.

One company owns one current PDF template (plus historical versions). All the
employer boxes on the form are filled from here, so adding a company never
touches source code.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.domain.enums import CompanyStatus, EmployerType


class Company(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: UUID = Field(default_factory=uuid4)
    name: str
    internal_code: str
    employer_type: EmployerType = EmployerType.IP

    okved: str  # 46.21.19
    ogrn: str  # ОГРН / ОГРНИП
    inn: str

    address_index: str  # 111677
    address_text: str  # МОСКВА УЛ. ВЕРТОЛЁТЧИКОВ Д4 К2
    phone: str | None = None

    director_position: str = "ГЕНЕРАЛЬНЫЙ ДИРЕКТОР"
    director_fio: str  # ГОРДИЕНКО АЛЕКСЕЙ АНАТОЛЬЕВИЧ

    logo_path: Path | None = None
    template_path: Path
    template_version: str = "1"

    status: CompanyStatus = CompanyStatus.ACTIVE
    notes: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    @field_validator("inn")
    @classmethod
    def _inn_digits(cls, v: str) -> str:
        digits = re.sub(r"\D", "", v)
        if len(digits) not in (10, 12):
            raise ValueError("INN must be 10 (legal entity) or 12 (individual) digits")
        return digits

    @field_validator("ogrn")
    @classmethod
    def _ogrn_digits(cls, v: str) -> str:
        digits = re.sub(r"\D", "", v)
        if len(digits) not in (13, 15):
            raise ValueError("OGRN must be 13 or OGRNIP 15 digits")
        return digits

    @field_validator("okved")
    @classmethod
    def _okved_format(cls, v: str) -> str:
        v = v.strip()
        if not re.fullmatch(r"\d{2}(\.\d{1,2}){0,2}", v):
            raise ValueError("OKVED must look like 46.21.19")
        return v
