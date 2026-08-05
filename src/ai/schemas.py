"""The one shape every provider's answer has to fit.

Three providers read the same passport and each phrases its JSON a little
differently. Rather than teach the OCR service three dialects, every answer is
validated here first: the keys the document model needs must be present and
readable, or the answer is rejected and the next provider gets its turn. A
provider that returns confident nonsense is therefore no better placed than one
that returns nothing.
"""

from __future__ import annotations

import re
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, field_validator

from src.common.errors import AiInvalidJsonError
from src.domain.enums import DocType

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_NOISE = {"n/a", "none", "null", "-", "—", "unknown", "не указано", "нет данных"}


class _Answer(BaseModel):
    """Base: every field is a string, blanks allowed, junk normalised away."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="allow")

    #: at least one of these must carry something, or the answer says nothing
    required_any: ClassVar[tuple[str, ...]] = ()
    #: keys that must parse as YYYY-MM-DD when they are not blank
    dates: ClassVar[tuple[str, ...]] = ()

    @field_validator("*", mode="before")
    @classmethod
    def _clean(cls, value: object) -> object:
        if value is None:
            return ""
        text = " ".join(str(value).split())
        return "" if text.lower() in _NOISE else text


class PassportAnswer(_Answer):
    surname: str = ""
    name: str = ""
    patronymic: str = ""
    #: The same three names as the page prints them in LATIN. The Russian
    #: spelling is transliterated from these by the program's own table, so
    #: the office's rules decide it rather than the model's freehand.
    surname_latin: str = ""
    name_latin: str = ""
    patronymic_latin: str = ""
    nationality: str = ""
    birth_date: str = ""
    birth_place: str = ""
    gender: str = ""
    series: str = ""
    number: str = ""
    issue_date: str = ""
    expiry_date: str = ""
    issued_by: str = ""

    required_any: ClassVar[tuple[str, ...]] = ("surname", "surname_latin",
                                               "number")
    dates: ClassVar[tuple[str, ...]] = ("birth_date", "issue_date", "expiry_date")


class PatentAnswer(_Answer):
    surname: str = ""
    name: str = ""
    patronymic: str = ""
    citizenship: str = ""
    series: str = ""
    number: str = ""
    profession: str = ""
    blank_series: str = ""
    blank_number: str = ""
    issue_date: str = ""
    issued_by: str = ""

    required_any: ClassVar[tuple[str, ...]] = ("number", "surname", "blank_number",
                                               "issued_by", "issue_date")
    dates: ClassVar[tuple[str, ...]] = ("issue_date",)


class StsAnswer(_Answer):
    series: str = ""
    number: str = ""
    plate: str = ""
    vin: str = ""
    mark: str = ""
    model: str = ""
    year: str = ""
    category: str = ""
    owner_fio: str = ""
    owner_address: str = ""
    issue_date: str = ""

    required_any: ClassVar[tuple[str, ...]] = ("vin", "plate", "number", "owner_fio")
    dates: ClassVar[tuple[str, ...]] = ("issue_date",)


class LicenceAnswer(_Answer):
    surname: str = ""
    name: str = ""
    patronymic: str = ""
    series: str = ""
    number: str = ""
    birth_date: str = ""
    issue_date: str = ""
    expiry_date: str = ""
    categories: str = ""

    required_any: ClassVar[tuple[str, ...]] = ("number", "surname")
    dates: ClassVar[tuple[str, ...]] = ("birth_date", "issue_date", "expiry_date")


class FreeAnswer(_Answer):
    """For the callers that invent their own keys — the template studies do.

    Nothing is required of them beyond being a flat object of strings, because
    the caller, not this module, knows what it asked for.
    """


_SCHEMAS: dict[DocType, type[_Answer]] = {
    DocType.PASSPORT: PassportAnswer,
    DocType.PATENT: PatentAnswer,
    DocType.STS: StsAnswer,
    DocType.DRIVER_LICENCE: LicenceAnswer,
}


def schema_for(doc_type: DocType) -> type[_Answer]:
    return _SCHEMAS.get(doc_type, FreeAnswer)


def validate(fields: dict[str, str], doc_type: DocType) -> dict[str, str]:
    """Put one provider's answer through the common shape.

    Raises :class:`AiInvalidJsonError` when the answer says nothing useful or
    when a date is unreadable — the manager then moves on to the next provider
    instead of writing a wrong value onto a document.
    """
    schema = schema_for(doc_type)
    answer = schema.model_validate(fields)
    data = {k: str(v) for k, v in answer.model_dump().items()}

    if schema.required_any and not any(data.get(k, "").strip()
                                       for k in schema.required_any):
        raise AiInvalidJsonError(
            f"{doc_type.value}: жавобда керакли майдонлар йўқ",
            context={"expected": list(schema.required_any)})

    for key in schema.dates:
        value = data.get(key, "").strip()
        if value and not _DATE.fullmatch(value):
            raise AiInvalidJsonError(
                f"{doc_type.value}: «{key}» санаси ўқилмади",
                context={"field": key, "value": value[:32]})
    return data
