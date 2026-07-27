"""УМУМИЙ (document re-use) and ПЕРЕВОД (notarial translation) — offline tests.

The AI call is stubbed; what is verified is the deterministic half: which
replacements get applied to the PDF, which are refused, and how a translation
payload is laid out on the page.
"""

from __future__ import annotations

import json
import tempfile
from datetime import date
from pathlib import Path

import fitz
import pytest

from src.config import paths
from src.domain.documents import Passport
from src.domain.enums import Gender


@pytest.fixture(autouse=True)
def isolated_data_dir(monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", tempfile.mkdtemp())
    paths.data_dir.cache_clear()
    yield
    paths.data_dir.cache_clear()


def _passport() -> Passport:
    return Passport(
        surname="ИСАКОВ", name="ШАХБОЗ", patronymic="АКМАЛЖОН УГЛИ",
        nationality="УЗБЕКИСТАН", birth_date=date(2000, 12, 27), gender=Gender.MALE,
        number="FA7822242", issue_date=date(2021, 5, 6), expiry_date=date(2031, 5, 5),
    )


def _contract(path: Path) -> Path:
    """A tiny text PDF standing in for one of the office's contracts.

    Uses the bundled Cyrillic font — the PDF built-in fonts have no Cyrillic
    glyphs, so text written with them cannot be searched or replaced.
    """
    from src.pdf.engine import _font_file

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_font(fontname="cyr", fontfile=str(_font_file("OfisSerif")))
    lines = [
        "ТРУДОВОЙ ДОГОВОР № 12",
        "г. Москва                                   23.07.2026",
        "Работник: РАХИМОВ БАДРИДДИН НОРМУРОДОВИЧ",
        "Паспорт: 405314544",
        "Гражданство: ТАДЖИКИСТАН",
        "ООО СТРОЙИНВЕСТ, ИНН 7733481040",
    ]
    y = 90
    for text in lines:
        page.insert_text((70, y), text, fontname="cyr", fontsize=11)
        y += 26
    doc.save(str(path))
    doc.close()
    return path


class _StubService:
    """UmumiyService with the AI reply pinned."""

    def __init__(self, edits: list[dict]) -> None:
        from src.services.umumiy_service import UmumiyService

        self.inner = UmumiyService(key_getter=lambda: "test-key")
        self._edits = edits

    def run(self, monkeypatch, source: Path, **kw):
        monkeypatch.setattr("src.services.umumiy_service.ask",
                            lambda *a, **k: json.dumps(self._edits))
        return self.inner.generate(source, _passport(), None, **kw)


def test_worker_data_replaced(monkeypatch, tmp_path) -> None:
    source = _contract(tmp_path / "dogovor.pdf")
    svc = _StubService([
        {"line": 2, "old": "РАХИМОВ БАДРИДДИН НОРМУРОДОВИЧ",
         "new": "ИСАКОВ ШАХБОЗ АКМАЛЖОН УГЛИ"},
        {"line": 3, "old": "405314544", "new": "FA7822242"},
        {"line": 4, "old": "ТАДЖИКИСТАН", "new": "УЗБЕКИСТАН"},
    ])
    result = svc.run(monkeypatch, source, form_date=date(2026, 7, 26))

    assert result.replacements == 3
    text = "".join(p.get_text() for p in fitz.open(result.pdf_path))
    assert "ИСАКОВ ШАХБОЗ" in text
    assert "РАХИМОВ" not in text
    assert "FA7822242" in text
    assert "405314544" not in text
    assert "УЗБЕКИСТАН" in text


def test_company_requisites_are_protected(monkeypatch, tmp_path) -> None:
    """A model that tries to rewrite the firm's ИНН must be refused."""
    source = _contract(tmp_path / "dogovor.pdf")
    svc = _StubService([
        {"line": 5, "old": "ИНН 7733481040", "new": "ИНН 9999999999"},
    ])
    result = svc.run(monkeypatch, source, form_date=date(2026, 7, 26))

    assert result.replacements == 0
    text = "".join(p.get_text() for p in fitz.open(result.pdf_path))
    assert "7733481040" in text
    assert "9999999999" not in text


def test_scanned_pdf_is_rejected_with_a_clear_message(monkeypatch, tmp_path) -> None:
    from src.common.errors import OfisError
    from src.services.umumiy_service import UmumiyService

    blank = tmp_path / "scan.pdf"
    doc = fitz.open()
    doc.new_page(width=595, height=842)  # no text at all
    doc.save(str(blank))
    doc.close()

    svc = UmumiyService(key_getter=lambda: "test-key")
    with pytest.raises(OfisError) as exc:
        svc.generate(blank, _passport(), None, form_date=date(2026, 7, 26))
    assert "matn" in exc.value.message.lower()


# -- ПЕРЕВОД ---------------------------------------------------------------

_TRANSLATION = {
    "doc_type": "passport",
    "source_language": "узбекского",
    "title": "ПАСПОРТ",
    "issuing_country": "РЕСПУБЛИКА УЗБЕКИСТАН",
    "fields": [
        {"label": "Дата рождения", "value": "27.12.2000"},
        {"label": "Фамилия", "value": "ИСАКОВ"},
        {"label": "Номер паспорта", "value": "FA7822242"},
        {"label": "Имя", "value": "ШАХБОЗ"},
    ],
    "stamps": ["Штамп: Отдел внутренних дел города Ташкента"],
    "notes": [],
}


def _valid_png() -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (600, 400), (200, 200, 200)).save(buf, format="PNG")
    return buf.getvalue()


def test_translation_pdf_and_docx(monkeypatch) -> None:
    from src.services.perevod_service import PerevodService

    monkeypatch.setattr("src.services.perevod_service.ask",
                        lambda *a, **k: json.dumps(_TRANSLATION))
    monkeypatch.setattr("src.ocr.preprocess.prepare_image", lambda b: b)

    svc = PerevodService(key_getter=lambda: "test-key")
    result = svc.translate([_valid_png()], doc_type="auto",
                           form_date=date(2026, 7, 26))

    assert result.doc_type == "passport"
    assert result.pdf_path.exists() and result.docx_path.exists()

    doc = fitz.open(result.pdf_path)
    # page 1 = scan of the original, page 2 = translation, page 3 = certification
    assert len(doc) == 3
    translation = doc[1].get_text().replace("\n", " ")
    assert "ПЕРЕВОД С УЗБЕКСКОГО ЯЗЫКА НА РУССКИЙ ЯЗЫК" in translation
    assert "ПАСПОРТ" in translation and "ИСАКОВ" in translation
    assert "FA7822242" in translation and "Отдел внутренних дел" in translation
    # the translation page itself carries no translator name and no date —
    # those belong on the separate certification sheet
    assert "переводчик" not in translation.lower()
    assert "нотариус" not in translation.lower()


def test_certification_page_is_a_blank_the_notary_completes(monkeypatch) -> None:
    """Page 3 prints the standard wording but NEVER a seal, a signature or a
    registry number — the notary applies those in person."""
    import re

    from src.services.perevod_service import PerevodService

    monkeypatch.setattr("src.services.perevod_service.ask",
                        lambda *a, **k: json.dumps(_TRANSLATION))
    monkeypatch.setattr("src.ocr.preprocess.prepare_image", lambda b: b)

    svc = PerevodService(
        key_getter=lambda: "test-key",
        cert_getter=lambda: {"notary": "Акимов Глеб Борисович",
                             "translator": "Варавва Мария Васильевна",
                             "city": "город Москва"})
    result = svc.translate([_valid_png()], form_date=date(2026, 7, 26))
    cert = fitz.open(result.pdf_path)[2].get_text()

    # the wording and the configured names are printed …
    assert "свидетельствую подлинность подписи" in cert.replace("\n", " ")
    assert "нотариус города Москвы" in cert.replace("\n", " ")
    assert "Акимов Глеб Борисович" in cert
    assert "Варавва Мария Васильевна" in cert
    # … but the registry number, fee and date are left blank
    assert "Зарегистрировано в реестре: №" in cert.replace("\n", " ")
    tail = cert.replace("\n", " ").split("реестре: №", 1)[1][:30]
    assert not re.search(r"\d", tail), f"registry number must be blank: {tail!r}"
    # no image is drawn on the page (no reproduced seal or signature)
    assert not fitz.open(result.pdf_path)[2].get_images()


def test_fields_follow_the_standard_order(monkeypatch) -> None:
    """The bundled form template fixes the field order regardless of AI order."""
    from src.services.perevod_service import PerevodService

    monkeypatch.setattr("src.services.perevod_service.ask",
                        lambda *a, **k: json.dumps(_TRANSLATION))
    monkeypatch.setattr("src.ocr.preprocess.prepare_image", lambda b: b)

    svc = PerevodService(key_getter=lambda: "test-key")
    result = svc.translate([b"x"], doc_type="passport", form_date=date(2026, 7, 26))

    text = "".join(p.get_text() for p in fitz.open(result.pdf_path))
    # Номер паспорта precedes Фамилия, which precedes Имя, which precedes
    # Дата рождения — the canonical passport order, not the AI's order.
    assert (text.index("Номер паспорта") < text.index("Фамилия")
            < text.index("Имя") < text.index("Дата рождения"))
