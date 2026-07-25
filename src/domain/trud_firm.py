"""A Трудовой-Уведомления firm — owns TWO templates.

Each firm uploads its трудовой договор (text PDF whose worker block is
re-written per worker) and its уведомление о заключении трудового договора
(госуслуги form, values printed under the labels). RUN produces both PDFs.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from src.domain.enums import CompanyStatus


class TrudFirm(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: UUID = Field(default_factory=uuid4)
    name: str
    internal_code: str

    trud_template_path: Path  # трудовой договор (text PDF)
    uved_template_path: Path  # уведомление blank (госуслуги form)

    status: CompanyStatus = CompanyStatus.ACTIVE
    notes: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
