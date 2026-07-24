"""A СФЕРА training profession (сфера обучения).

Drives the certificate + protocol text. Each profession knows its display name,
an optional qualifier note (e.g. «аргонодуговая»), and the разряд (grade) with
its spelled-out word for the certificate ("5 (пятого) разряда").
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from src.domain.enums import CompanyStatus

_GRADE_WORDS = {
    1: "первого", 2: "второго", 3: "третьего", 4: "четвёртого", 5: "пятого",
    6: "шестого", 7: "седьмого", 8: "восьмого",
}


class Profession(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: UUID = Field(default_factory=uuid4)
    name: str  # Арматурщик
    note: str | None = None  # аргонодуговая (printed in parentheses)
    grade: int = 5  # разряд
    status: CompanyStatus = CompanyStatus.ACTIVE
    created_at: datetime = Field(default_factory=datetime.now)

    @property
    def grade_word(self) -> str:
        return _GRADE_WORDS.get(self.grade, "")

    @property
    def quoted(self) -> str:
        """«Арматурщик» — used on the протокол line and certificate front."""
        return f"«{self.name}»"

    @property
    def qualification_short(self) -> str:
        """Арматурщик 5 разряда — протокол «Заключение» column."""
        return f"{self.name} {self.grade} разряда"

    @property
    def qualification_full(self) -> str:
        """Арматурщик 5 (пятого) разряда — certificate right page."""
        return f"{self.name} {self.grade} ({self.grade_word}) разряда"
