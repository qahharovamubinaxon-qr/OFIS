"""One insurer's ОСАГО policy template.

Like a Трудовой firm, a template is registered once and reused: the office
uploads the Word policy an insurer gave it, and every car after that is filled
into a copy of it. The four the office already works with are bundled; more are
added the same way.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from src.domain.enums import CompanyStatus


class InsuranceTemplate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: UUID = Field(default_factory=uuid4)
    name: str                       # СК «Согласие»
    internal_code: str              # soglasie — the folder key
    insurer: str = ""               # the underwriting company, when it differs
    template_path: Path             # the .docx the office was given

    #: The firm this agency agreement belongs to — the office holds agency
    #: status with several insurers through several of its own companies.
    firm: str = ""

    status: CompanyStatus = CompanyStatus.ACTIVE
    notes: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
