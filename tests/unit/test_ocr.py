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


def test_patent_back_merges_issue_and_issuer() -> None:
    from datetime import date

    canned = {
        DocType.PATENT: {"series": "50", "number": "2600168448", "profession": "ВОДИТЕЛЬ",
                         "issue_date": "", "issued_by": ""},
    }
    # Front has no date/issuer; the back supplies both (patent_back_prompt reuses
    # DocType.PATENT canned data in this fake, standing in for the real back read).
    back = {DocType.PATENT: {"issue_date": "2026-05-31",
                             "issued_by": "ГУ МВД РОССИИ ПО МОСКОВСКОЙ ОБЛАСТИ",
                             "series": "50", "number": "2600168448", "profession": "ВОДИТЕЛЬ"}}
    svc = OcrService(AiManager([FakeProvider(canned)]))
    front_only = svc.read_patent(b"front")
    assert front_only.issue_date is None  # nothing on the front

    svc2 = OcrService(AiManager([FakeProvider(back)]))
    merged = svc2.read_patent(b"front", b"back")
    assert merged.issue_date == date(2026, 5, 31)
    assert "МОСКОВСКОЙ" in (merged.issued_by or "")
