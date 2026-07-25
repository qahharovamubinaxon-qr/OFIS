"""Address-template builder: blank → per-address template, stored fields."""

from __future__ import annotations

import tempfile
from pathlib import Path

import fitz
import pytest

from src.app import build_container
from src.domain.registration_address import RegistrationAddress
from src.services.registration_address_service import RegistrationAddressService

ROOT = Path(__file__).resolve().parents[2]
HAS_BLANK = (ROOT / "templates" / "registration" / "blank.pdf").exists()


@pytest.fixture()
def container(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("XDG_DATA_HOME", tempfile.mkdtemp())
    from src.config import paths

    paths.data_dir.cache_clear()
    return build_container()


@pytest.mark.skipif(not HAS_BLANK, reason="registration blank missing")
def test_build_address_from_blank(container, tmp_path, monkeypatch) -> None:
    # keep the generated template out of the repo's templates/ dir
    from src.config import paths as p

    monkeypatch.setattr(p, "templates_dir", lambda: tmp_path / "templates")
    (tmp_path / "templates" / "registration").mkdir(parents=True)
    import shutil

    for name in ("blank.pdf", "address_mapping.v1.json"):
        shutil.copyfile(
            ROOT / "templates" / "registration" / name,
            tmp_path / "templates" / "registration" / name,
        )

    svc = container.resolve(RegistrationAddressService)
    address = RegistrationAddress(
        label="ТЕСТ УЛ 7", internal_code="test7", address_text="Г МОСКВА, ТЕСТОВАЯ, д. 7",
        host_fio="ИВАНОВ ИВАН ИВАНОВИЧ",
        oblast="Г МОСКВА", ulitsa="ТЕСТОВАЯ", dom="7", kvartira="12",
        regional_number="02/770-039/26/000001",
        template_path=Path("unused.pdf"),
    )
    created = svc.create(address, build_from_blank=True)
    assert created.template_path.exists()

    doc = fitz.open(str(created.template_path))
    page1 = "".join(doc[0].get_text().split())
    page2 = "".join(doc[1].get_text().split())
    doc.close()
    assert "МОСКВА" in page1 and "ТЕСТОВАЯ" in page1 and "дом7" in page1
    assert "ИВАНОВ" in page2  # host surname grid
    assert "02/770-039/26/000001" in page2  # regional number

    # stored structured fields survive the DB round-trip
    loaded = svc.list()
    match = [a for a in loaded if a.internal_code == "test7"]
    assert match and match[0].ulitsa == "ТЕСТОВАЯ" and match[0].dom == "7"
