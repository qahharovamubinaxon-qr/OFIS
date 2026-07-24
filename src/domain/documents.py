"""The four source documents an operator uploads, as validated models.

Field lists come straight from the МВД Приложение № 7 boxes (see the rendered
sample in ARCHITECTURE.md §5). ``Optional`` mirrors boxes that may legitimately
be blank on the real form. Confidence is *not* stored here — it is OCR metadata
kept in :mod:`src.domain.ocr` so the domain stays clean.
"""

from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel, ConfigDict, field_validator

from src.domain.enums import Gender

_MODEL = ConfigDict(str_strip_whitespace=True, extra="forbid")


def _collapse(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


class Passport(BaseModel):
    model_config = _MODEL

    surname: str
    name: str
    patronymic: str | None = None
    gender: Gender | None = None
    birth_date: date | None = None
    birth_place: str | None = None
    nationality: str | None = None  # Гражданство, e.g. ТАДЖИКИСТАН
    series: str | None = None
    number: str
    issue_date: date | None = None
    issued_by: str | None = None

    @field_validator("surname", "name", "patronymic", "nationality", "issued_by")
    @classmethod
    def _clean_text(cls, v: str | None) -> str | None:
        return _collapse(v) if v else v

    @field_validator("number", "series")
    @classmethod
    def _clean_number(cls, v: str | None) -> str | None:
        return re.sub(r"\s+", "", v) if v else v


class Patent(BaseModel):
    model_config = _MODEL

    doc_name: str = "ПАТЕНТ"
    series: str | None = None  # 77
    number: str  # 26003 14661 (spacing preserved as printed if meaningful)
    issue_date: date | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    issued_by: str | None = None
    profession: str  # ПОДСОБНЫЙ РАБОЧИЙ
    # The worker's ФИО as printed in Russian on the patent — the authoritative
    # name source when the passport uses a non-Cyrillic script.
    holder_surname: str | None = None
    holder_name: str | None = None
    holder_patronymic: str | None = None

    @field_validator("profession", "issued_by", "holder_surname", "holder_name", "holder_patronymic")
    @classmethod
    def _clean(cls, v: str | None) -> str | None:
        return _collapse(v) if v else v


class Registration(BaseModel):
    """Уведомление о прибытии / по месту пребывания."""

    model_config = _MODEL

    address: str
    registration_date: date | None = None
    expiration_date: date | None = None

    @field_validator("address")
    @classmethod
    def _clean(cls, v: str) -> str:
        return _collapse(v)


class MigrationCard(BaseModel):
    model_config = _MODEL

    number: str | None = None
    entry_date: date | None = None
    purpose: str | None = None
