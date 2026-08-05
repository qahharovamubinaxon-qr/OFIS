"""The four source documents an operator uploads, as validated models.

Field lists come straight from the МВД Приложение № 7 boxes (see the rendered
sample in ARCHITECTURE.md §5). ``Optional`` mirrors boxes that may legitimately
be blank on the real form. Confidence is *not* stored here — it is OCR metadata
kept in :mod:`src.domain.ocr` so the domain stays clean.
"""

from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.domain.enums import Gender
from src.domain.passport_rules import (
    in_russian_letters,
    issuer_in_russian,
    normalise_document,
    split_son_of,
)

_MODEL = ConfigDict(str_strip_whitespace=True, extra="forbid")


def _collapse(value: str) -> str:
    """One line, no double spaces."""
    return re.sub(r"\s+", " ", value).strip()


def _russian(value: str) -> str:
    """One line, and in RUSSIAN letters.

    A Tajik document is printed in the Tajik alphabet (Хоҷа, Ғафуров,
    Қӯрғонтеппа) and a Russian form has no such letters, so every name and
    place is spelled the Russian way here — whichever road it came in by:
    read off a photograph, taken out of the machine-readable zone, or typed
    by the operator. See :func:`in_russian_letters`.

    NOT applied to «кем выдан»: that field has a rule of its own
    (:func:`issuer_in_russian`), which recognises the office by its Tajik
    initials — «ХШБ ВКД ҶТ» — and would no longer know «ҶТ» once it had
    been spelled out as «ДЖТ». Its own rule ends with the same letters.
    """
    return in_russian_letters(_collapse(value))


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
    expiry_date: date | None = None  # Срок действия — needed by the registration form
    issued_by: str | None = None

    # The name as the page prints it in LATIN, kept because the Russian
    # spelling is TRANSLITERATED from it: when the patent disagrees, this
    # is what says which of the two was misread. Empty for a document that
    # prints no Latin at all.
    surname_latin: str = ""
    name_latin: str = ""
    patronymic_latin: str = ""

    @field_validator("surname", "name", "nationality", "birth_place")
    @classmethod
    def _clean_text(cls, v: str | None) -> str | None:
        return _russian(v) if v else v

    @field_validator("patronymic")
    @classmethod
    def _clean_patronymic(cls, v: str | None) -> str | None:
        # «ЖУРАМУРОДУГЛИ» is a reading that ran two words together — the
        # father's name and «ўғли» are separate words on every document
        return split_son_of(_russian(v)) if v else v

    @field_validator("issued_by")
    @classmethod
    def _clean_issuer(cls, v: str | None) -> str | None:
        # left in its own alphabet here — issuer_in_russian reads it below
        return _collapse(v) if v else v

    @field_validator("number", "series")
    @classmethod
    def _clean_number(cls, v: str | None) -> str | None:
        return re.sub(r"\s+", "", v) if v else v

    @model_validator(mode="after")
    def _as_a_russian_form_needs_it(self) -> Passport:
        """The office's two rules, applied wherever a passport comes from.

        Here rather than in the OCR service because the passport reaches the
        forms three ways — read from an image, typed by hand, or carried in
        from свера — and the rules are not about reading. See
        :mod:`src.domain.passport_rules`.
        """
        self.series, self.number = normalise_document(
            self.series, self.number, self.nationality)
        self.issued_by = issuer_in_russian(self.issued_by) or None
        return self


class Patent(BaseModel):
    model_config = _MODEL

    doc_name: str = "ПАТЕНТ"
    series: str | None = None  # 77
    number: str  # 26003 14661 (spacing preserved as printed if meaningful)
    blank_series: str | None = None  # серия бланка, e.g. ПР
    blank_number: str | None = None  # номер бланка, e.g. 6164274
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
    holder_citizenship: str | None = None

    @field_validator("profession", "issued_by", "holder_surname", "holder_name",
                     "holder_citizenship")
    @classmethod
    def _clean(cls, v: str | None) -> str | None:
        return _russian(v) if v else v

    @field_validator("holder_patronymic")
    @classmethod
    def _clean_patronymic(cls, v: str | None) -> str | None:
        return split_son_of(_russian(v)) if v else v


class Registration(BaseModel):
    """Уведомление о прибытии / по месту пребывания."""

    model_config = _MODEL

    address: str
    registration_date: date | None = None
    expiration_date: date | None = None

    @field_validator("address")
    @classmethod
    def _clean(cls, v: str) -> str:
        return _russian(v)


class MigrationCard(BaseModel):
    model_config = _MODEL

    number: str | None = None
    entry_date: date | None = None
    purpose: str | None = None

    @field_validator("purpose")
    @classmethod
    def _clean(cls, v: str | None) -> str | None:
        return _russian(v) if v else v
