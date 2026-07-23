"""The Employee aggregate — the single validated object the PDF engine fills a
template from. It composes the four source documents plus the employment facts
that come from the operator, not from a scan (profession, contract type/date).
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from src.domain.documents import MigrationCard, Passport, Patent, Registration
from src.domain.enums import ContractType


class Employee(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: UUID = Field(default_factory=uuid4)
    company_id: UUID

    passport: Passport
    patent: Patent | None = None
    registration: Registration | None = None
    migration_card: MigrationCard | None = None

    # Employment facts (operator-entered, not scanned)
    profession: str
    contract_type: ContractType = ContractType.LABOR
    contract_date: date
    work_address: str | None = None

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    @property
    def full_name(self) -> str:
        parts = [self.passport.surname, self.passport.name, self.passport.patronymic or ""]
        return " ".join(p for p in parts if p).strip()

    def output_basename(self) -> str:
        """``SURNAME_NAME`` — the default PDF filename stem (see PDF_ENGINE.md)."""
        stem = f"{self.passport.surname}_{self.passport.name}".upper()
        return "".join(c if c.isalnum() or c in "_-" else "_" for c in stem)
