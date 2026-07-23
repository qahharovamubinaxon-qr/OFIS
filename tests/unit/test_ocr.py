"""OCR service maps provider output → validated domain models (via FakeProvider)."""

from __future__ import annotations

from datetime import date

from src.ai.fake_provider import FakeProvider
from src.ai.manager import AiManager
from src.domain.enums import DocType
from src.ocr.service import OcrService


def _service() -> OcrService:
    canned = {
        DocType.PASSPORT: {
            "surname": "РАСУЛОВ", "name": "МУСТАФО", "patronymic": "АЗИЗЖОН УГЛИ",
            "nationality": "УЗБЕКИСТАН", "number": "5512345678",
            "birth_date": "1992-03-15", "issue_date": "2019-06-20", "issued_by": "МВД",
        },
        DocType.PATENT: {
            "series": "77", "number": "2612345678", "issue_date": "2026-05-10",
            "issued_by": "ОВМ", "profession": "ВОДИТЕЛЬ",
        },
    }
    return OcrService(AiManager([FakeProvider(canned)]))


def test_read_passport_builds_model() -> None:
    p = _service().read_passport(b"img")
    assert p.surname == "РАСУЛОВ"
    assert p.birth_date == date(1992, 3, 15)
    assert p.number == "5512345678"


def test_read_patent_builds_model() -> None:
    pat = _service().read_patent(b"img")
    assert pat.number == "2612345678"
    assert pat.issue_date == date(2026, 5, 10)
    assert pat.profession == "ВОДИТЕЛЬ"


def test_patent_profession_defaults_when_empty() -> None:
    svc = OcrService(AiManager([FakeProvider({DocType.PATENT: {"number": "1"}})]))
    assert svc.read_patent(b"x").profession == "ПОДСОБНЫЙ РАБОЧИЙ"


def test_manager_reports_availability() -> None:
    assert AiManager([FakeProvider()]).available() is True
