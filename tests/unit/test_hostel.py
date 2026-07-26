"""ХОСТЕЛ module: template building, worker fill, kind isolation, legality."""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import pytest

from src.config import paths


@pytest.fixture()
def container(monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", tempfile.mkdtemp())
    paths.data_dir.cache_clear()
    from src.app import build_container

    yield build_container()
    paths.data_dir.cache_clear()


def _hostel(code: str = "testhostel1"):
    from src.domain.registration_address import RegistrationAddress

    return RegistrationAddress(
        label="ХОСТЕЛ ЛУЖСКАЯ 10", internal_code=code,
        address_text="САНКТ-ПЕТЕРБУРГ Г, ЛУЖСКАЯ УЛ, ДОМ 10",
        host_fio="ДЯГИЛЕВА ЮЛИЯ ГЕННАДЬЕВНА", kind="hostel",
        oblast="САНКТ-ПЕТЕРБУРГ Г", ulitsa="ЛУЖСКАЯ УЛ",
        dom="10", korpus="1", stroenie="В",
        organization_name="ИНДИВИДУАЛЬНЫЙ ПРЕДПРИНИМАТЕЛЬ ДЯГИЛЕВ",
        inn="780401098145",
        template_path=Path("missing.pdf"),
    )


def _passport():
    from src.domain.documents import Passport
    from src.domain.enums import Gender

    return Passport(
        surname="КОБУЛОВ", name="ШЕРАЛИ", patronymic="ШЕРЗОД УГЛИ",
        nationality="УЗБЕКИСТАН", birth_date=date(2001, 5, 19), gender=Gender.MALE,
        number="FA7394930", issue_date=date(2023, 3, 10), expiry_date=date(2028, 3, 9),
    )


def test_template_built_from_blank_carries_host_block(container) -> None:
    import fitz

    from src.services.registration_address_service import RegistrationAddressService

    svc = container.resolve(RegistrationAddressService)
    saved = svc.create_hostel(_hostel(), None)
    assert saved.template_path.exists()

    doc = fitz.open(saved.template_path)
    p1, p2 = doc[0].get_text(), doc[1].get_text()
    assert "ЛУЖСКАЯ" in p1.replace("\n", "") .replace(" ", "") or "ЛУЖСКАЯ" in p1
    assert "780401098145" in p2.replace("\n", "").replace(" ", "")
    assert "ДЯГИЛЕВА" in p2.replace("\n", "").replace(" ", "")


def test_generate_fills_worker_and_dates(container) -> None:
    import fitz

    from src.services.hostel_service import HostelService
    from src.services.registration_address_service import RegistrationAddressService

    svc = container.resolve(RegistrationAddressService)
    saved = svc.create_hostel(_hostel(), None)
    result = HostelService().generate(
        _passport(), None, saved, registration_expiry=date(2026, 7, 24)
    )
    assert result.pdf_path.exists()
    assert result.surname == "КОБУЛОВ"

    text = "".join(p.get_text() for p in fitz.open(result.pdf_path))
    flat = text.replace("\n", "").replace(" ", "")
    assert "КОБУЛОВ" in flat
    assert "FA7394930" in flat
    # stay-until date parts land as separate boxes (24 · 07 · 2026)
    assert "2026" in flat


def test_values_land_inside_their_boxes(container) -> None:
    """Regression: гражданство and паспорт серия must sit on their own box
    centres (they were drawn below/left of the grid before)."""
    import fitz

    from src.services.hostel_service import HostelService
    from src.services.registration_address_service import RegistrationAddressService

    svc = container.resolve(RegistrationAddressService)
    saved = svc.create_hostel(_hostel(), None)
    # a passport whose серия is printed separately, so both fields are drawn
    passport = _passport().model_copy(update={"series": "FA", "number": "7394930"})
    result = HostelService().generate(
        passport, None, saved, registration_expiry=date(2026, 7, 24)
    )

    centres: dict[str, list[tuple[float, float]]] = {}
    for span in _spans(fitz.open(result.pdf_path)[0]):
        cx = (span["bbox"][0] + span["bbox"][2]) / 2
        centres.setdefault(span["text"], []).append((round(cx, 1), span["origin"][1]))

    # citizenship: first letter «У» of УЗБЕКИСТАН on box-1 centre 124.5, y 92.2
    assert any(abs(cx - 124.5) < 1.0 and abs(y - 92.2) < 1.0
               for cx, y in centres.get("У", [])), "citizenship off its boxes"
    # passport series «FA» starts on box-1 centre 285.6 of the серия run
    assert any(abs(cx - 285.6) < 1.0 for cx, _y in centres.get("F", [])), \
        "passport series off its boxes"


def _spans(page):
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            yield from line["spans"]


def test_never_reproduces_mvd_signature_or_reg_number(container) -> None:
    """Legality guard: the generated form is a blank application — it must not
    carry МВД's electronic-signature block or a registration number."""
    import fitz

    from src.services.hostel_service import HostelService
    from src.services.registration_address_service import RegistrationAddressService

    svc = container.resolve(RegistrationAddressService)
    saved = svc.create_hostel(_hostel(), None)
    result = HostelService().generate(
        _passport(), None, saved, registration_expiry=date(2026, 7, 24)
    )
    text = "".join(p.get_text() for p in fitz.open(result.pdf_path)).upper()
    for forbidden in ("ПОДПИСАН ЭЛЕКТРОННОЙ", "СЕРТИФИКАТ:", "ДЕЙСТВИТЕЛЕН ДО"):
        assert forbidden not in text


def test_hostels_are_isolated_from_regular_addresses(container) -> None:
    from src.services.registration_address_service import RegistrationAddressService

    svc = container.resolve(RegistrationAddressService)
    svc.create_hostel(_hostel(), None)

    hostel_codes = [a.internal_code for a in svc.list(kind="hostel")]
    regular_codes = [a.internal_code for a in svc.list(kind="regular")]
    assert "testhostel1" in hostel_codes
    assert "testhostel1" not in regular_codes
    # the seeded ПАРКОВАЯ address stays a regular one, ЛУЖСКАЯ a hostel
    assert "parkovaya55" in regular_codes
    assert "luzhskaya10" in hostel_codes
