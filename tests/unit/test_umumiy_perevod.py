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
    # both roots: paths.data_dir() reads LOCALAPPDATA on Windows and
    # XDG_DATA_HOME elsewhere, and these tests must not touch the real one
    sandbox = tempfile.mkdtemp()
    monkeypatch.setenv("XDG_DATA_HOME", sandbox)
    monkeypatch.setenv("LOCALAPPDATA", sandbox)
    paths.data_dir.cache_clear()
    yield
    paths.data_dir.cache_clear()


def _plain(text: str) -> str:
    """PDF text as it reads, not as MuPDF spells it.

    MuPDF hands the spaces a :class:`fitz.TextWriter` laid down back as
    NO-BREAK SPACE (U+00A0), so a plain «Номер паспорта» never matches. Fold
    them, and the newlines, into ordinary spaces before looking for anything.
    """
    return " ".join(text.replace("\xa0", " ").split())


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


def _scan_pdf(tmp_path) -> Path:
    """A PDF with no text layer at all — the shape a scan has."""
    blank = tmp_path / "scan.pdf"
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    doc.save(str(blank))
    doc.close()
    return blank


def test_scanned_pdf_is_read_as_images_not_rejected(monkeypatch, tmp_path) -> None:
    """A scan used to dead-end with «matn topilmadi». Now the pages are read
    visually and the worker's data is typed into the boxes the AI returns."""
    from src.services.umumiy_service import UmumiyService

    boxes = [{"page": 0, "text": "РАХИМОВ БАДРИДДИН", "field": "fio_full",
              "box": {"x0": 0.1, "y0": 0.2, "x1": 0.6, "y1": 0.23}}]
    monkeypatch.setattr("src.services.umumiy_templates.ask",
                        lambda *a, **k: json.dumps(boxes))

    svc = UmumiyService(key_getter=lambda: "test-key")
    result = svc.generate(_scan_pdf(tmp_path), _passport(), None,
                          form_date=date(2026, 7, 26))

    assert result.replacements == 1
    text = "".join(p.get_text() for p in fitz.open(result.pdf_path))
    assert "ИСАКОВ" in text, "the new worker's name was not written in"


def test_scan_with_no_worker_data_says_so(monkeypatch, tmp_path) -> None:
    from src.common.errors import OfisError
    from src.services.umumiy_service import UmumiyService

    monkeypatch.setattr("src.services.umumiy_templates.ask",
                        lambda *a, **k: "[]")
    svc = UmumiyService(key_getter=lambda: "test-key")
    with pytest.raises(OfisError) as exc:
        svc.generate(_scan_pdf(tmp_path), _passport(), None,
                     form_date=date(2026, 7, 26))
    assert "ma'lumot" in exc.value.message.lower()


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
    # sheet 1 = the original, sheet 2 = the translation, sheet 3 = untouched
    assert len(doc) == 3
    translation = _plain(doc[1].get_text())
    assert "ПЕРЕВОД С УЗБЕКСКОГО ЯЗЫКА НА РУССКИЙ ЯЗЫК" in translation
    assert "ПАСПОРТ" in translation and "ИСАКОВ" in translation
    assert "FA7822242" in translation and "Отдел внутренних дел" in translation
    # the translation page itself carries no translator name and no date —
    # those belong on the notary's own sheet, which he completes by hand
    assert "переводчик" not in translation.lower()
    assert "нотариус" not in translation.lower()


def test_the_original_is_on_sheet_one_and_the_translation_fits_one_sheet(
        monkeypatch) -> None:
    """Sheet 1 carries the copy of the original; the translation is set to fit
    sheet 2 whole, so the package is always exactly three sheets."""
    from src.services.perevod_service import PerevodService

    long_answer = dict(_TRANSLATION)
    long_answer["fields"] = _TRANSLATION["fields"] + [
        {"label": f"Дополнительное поле {i}",
         "value": "Отдел внутренних дел города Ташкента Республики Узбекистан"}
        for i in range(40)
    ]
    monkeypatch.setattr("src.services.perevod_service.ask",
                        lambda *a, **k: json.dumps(long_answer))
    monkeypatch.setattr("src.ocr.preprocess.prepare_image", lambda b: b)

    svc = PerevodService(key_getter=lambda: "test-key")
    result = svc.translate([_valid_png(), _valid_png()], doc_type="passport")

    doc = fitz.open(result.pdf_path)
    assert len(doc) == 3, "package must stay three sheets however long the text"
    # both photographs of the original are pasted on sheet 1, not on later ones
    assert len(doc[0].get_images()) == 2
    assert not _plain(doc[0].get_text())
    assert "Дополнительное поле 39" in _plain(doc[1].get_text())
    # sheet 3 is the notary's — nothing at all is printed or drawn on it
    assert not _plain(doc[2].get_text())
    assert not doc[2].get_images()


def test_blanks_are_kept_and_used_for_every_sheet(monkeypatch, tmp_path) -> None:
    """The office uploads its three sheets once; every package is laid on them."""
    from src.services import perevod_service as ps

    monkeypatch.setattr(ps, "ask", lambda *a, **k: json.dumps(_TRANSLATION))
    monkeypatch.setattr("src.ocr.preprocess.prepare_image", lambda b: b)
    monkeypatch.setattr(ps.paths, "user_templates_dir", lambda: tmp_path)

    # a blank with a word on it, so it can be recognised in the output
    marks = []
    for index in range(1, 4):
        blank = tmp_path / f"blank{index}.pdf"
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        page.insert_text((60, 60), f"BLANKA-{index}", fontsize=20)
        doc.save(str(blank))
        marks.append(ps.set_blank(index, blank))

    assert [p.name for p in ps.blanks()] == ["page1.pdf", "page2.pdf", "page3.pdf"]
    assert all(m.exists() for m in marks)

    svc = ps.PerevodService(key_getter=lambda: "test-key")
    result = svc.translate([_valid_png()], doc_type="passport")

    doc = fitz.open(result.pdf_path)
    assert len(doc) == 3
    for index in range(3):
        assert f"BLANKA-{index + 1}" in _plain(doc[index].get_text())
    # sheet 3 carries the blank's own text and NOTHING the program added
    assert _plain(doc[2].get_text()) == "BLANKA-3"

    ps.clear_blank(2)
    assert ps.blank_path(2) is None and ps.blank_path(1) is not None


def test_fields_follow_the_standard_order(monkeypatch) -> None:
    """The bundled form template fixes the field order regardless of AI order."""
    from src.services.perevod_service import PerevodService

    monkeypatch.setattr("src.services.perevod_service.ask",
                        lambda *a, **k: json.dumps(_TRANSLATION))
    monkeypatch.setattr("src.ocr.preprocess.prepare_image", lambda b: b)

    svc = PerevodService(key_getter=lambda: "test-key")
    result = svc.translate([b"x"], doc_type="passport", form_date=date(2026, 7, 26))

    text = _plain("".join(p.get_text() for p in fitz.open(result.pdf_path)))
    # Номер паспорта precedes Фамилия, which precedes Имя, which precedes
    # Дата рождения — the canonical passport order, not the AI's order.
    assert (text.index("Номер паспорта") < text.index("Фамилия")
            < text.index("Имя") < text.index("Дата рождения"))
