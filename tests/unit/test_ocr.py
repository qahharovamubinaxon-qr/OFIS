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


def test_a_patent_that_will_not_read_does_not_sink_the_passport() -> None:
    """The office saw a good passport read and then «openrouter: лимит тугади»
    because the PATENT alone had exhausted the provider chain. The patent only
    improves the Russian name — its failure must leave the passport standing.
    """
    from src.common.errors import AiRateLimitError

    service = _service()

    def _boom(*_a, **_k):
        raise AiRateLimitError("openrouter: лимит тугади")

    service.read_patent = _boom
    passport, patent = service.read_documents(b"passport", b"patent")
    assert patent is None
    assert passport.surname == "РАСУЛОВ"      # the passport still read


def test_no_patent_image_is_simply_no_patent() -> None:
    passport, patent = _service().read_documents(b"passport")
    assert patent is None
    assert passport.surname == "РАСУЛОВ"


def test_a_patent_that_reads_still_supplies_the_russian_name() -> None:
    """The fix must not stop a good patent from doing its job."""
    passport, patent = _service().read_documents(b"passport", b"patent")
    assert patent is not None
    assert patent.series == "77"
