"""Registration address — a pre-filled «Уведомление о прибытии» template.

Works exactly like a :class:`~src.domain.company.Company`: each address is a
blank registration form whose address block (page 1) and host ФИО (page 2) are
already printed. The program fills only the worker/date boxes, so adding an
address never touches source code — one shared mapping fills any address.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from src.domain.enums import CompanyStatus


class RegistrationAddress(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: UUID = Field(default_factory=uuid4)
    label: str  # short name in the picker, e.g. "5-Я ПАРКОВАЯ 55-55"
    internal_code: str  # unique folder key, e.g. "parkovaya55"
    address_text: str  # human summary of the printed address (for the list)
    host_fio: str  # ПОПОВ ВЛАДИМИР ГЕННАДЬЕВИЧ — the принимающая сторона (printed)

    template_path: Path
    template_version: str = "1"

    status: CompanyStatus = CompanyStatus.ACTIVE
    notes: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
