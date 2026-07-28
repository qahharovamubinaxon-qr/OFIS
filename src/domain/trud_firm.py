"""A Трудовой-Уведомления firm — owns TWO templates.

Each firm uploads its трудовой договор (text PDF whose worker block is
re-written per worker) and its уведомление о заключении трудового договора
(госуслуги form, values printed under the labels). RUN produces both PDFs.

A firm the office has no Word file for is typed in instead: its ``details``
hold the requisites, and the same two templates are built from them.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from src.domain.enums import CompanyStatus
from src.domain.firm_details import FirmDetails


class TrudFirm(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: UUID = Field(default_factory=uuid4)
    name: str
    internal_code: str

    trud_template_path: Path  # трудовой договор (text PDF)
    uved_template_path: Path  # уведомление blank (госуслуги form)
    hod_template_path: Path | None = None  # ходатайство (optional, .docx)

    #: set when the firm was typed in rather than uploaded — the requisites its
    #: two templates were built from, so they can be rebuilt after an edit
    details: FirmDetails | None = None

    status: CompanyStatus = CompanyStatus.ACTIVE
    notes: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
