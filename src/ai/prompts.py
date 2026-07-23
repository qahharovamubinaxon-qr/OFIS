"""Per-document extraction prompts. Each asks for strict JSON with exactly the
keys the domain models need — never prose. Versioned so a prompt change is
traceable. Field keys match what :mod:`src.ocr.service` maps into the models.
"""

from __future__ import annotations

from src.domain.enums import DocType

_COMMON = (
    "You are an OCR extraction engine for Russian migration documents. "
    "Read the image and return ONLY a JSON object, no explanation, no markdown. "
    "Use empty string for anything you cannot read. Dates as YYYY-MM-DD. "
    "Keep Cyrillic text exactly as printed, uppercased.\n"
)

_PASSPORT = _COMMON + (
    'Keys: {"document_type":"passport","surname","name","patronymic",'
    '"nationality","birth_date","series","number","issue_date","issued_by"}'
)

_PATENT = _COMMON + (
    'This is a Russian work patent (патент). The issuing organization is on the '
    'back side ("Кем выдан"). '
    'Keys: {"document_type":"patent","series","number","issue_date","issued_by",'
    '"profession"}'
)

_PROMPTS: dict[DocType, str] = {
    DocType.PASSPORT: _PASSPORT,
    DocType.PATENT: _PATENT,
}


def prompt_for(doc_type: DocType) -> str:
    return _PROMPTS.get(doc_type, _COMMON)
