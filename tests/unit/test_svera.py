"""СФЕРА: dative names, value building, counters, and 2-page generation."""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import fitz
import pytest

from src.app import build_container
from src.domain.documents import Passport
from src.domain.profession import Profession
from src.services.profession_service import ProfessionService
from src.services.svera_service import SveraService
from src.services.svera_values import build_svera_values, format_reg13
from src.utils.ru_names import to_dative

ROOT = Path(__file__).resolve().parents[2]
HAS_TEMPLATE = (ROOT / "templates" / "svera" / "mapping.v1.json").exists()


@pytest.fixture()
def container(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("XDG_DATA_HOME", tempfile.mkdtemp())
    from src.config import paths

    paths.data_dir.cache_clear()
    return build_container()


def test_dative_declension() -> None:
    assert to_dative("РАСУЛОВ", "АЗИЗ", "АНВАРОВИЧ") == "Расулову Азизу Анваровичу"
    assert to_dative("ШУКУРОВ", "ЗАРИФ", "СЕВИНОВИЧ") == "Шукурову Зарифу Севиновичу"
    # «угли» patronymics are not declined, and each word is capitalised the way
    # the centre's certificates print them
    assert to_dative("АХМЕДОВ", "ЖАСУР", "БАХТИЯР УГЛИ") == "Ахмедову Жасуру Бахтияр Угли"


def test_reg13_format() -> None:
    assert format_reg13(1800359856150) == "180035 9856150"
    assert format_reg13(1800359856151) == "180035 9856151"


def test_profession_text() -> None:
    p = Profession(name="Арматурщик", grade=5)
    assert p.quoted == "«Арматурщик»"
    # the протокол «Заключение» column reads «5-й разряд»
    assert p.qualification_short == "Арматурщик 5-й разряд"
    assert p.qualification_full == "Арматурщик 5 (пятого) разряда"


def test_values_split_case() -> None:
    p = Passport(surname="ШУКУРОВ", name="ЗАРИФ", patronymic="СЕВИНОВИЧ", number="1")
    v = build_svera_values(
        p.surname, p.name, p.patronymic, Profession(name="Арматурщик"),
        issue_date=date(2023, 11, 6), photo_path=None,
        po_number=3963, udo_number=606, reg13=1800359856150,
    )
    # protocol ФИО is nominative Title-case, certificate ФИО is dative
    assert v["svera.fio_protocol"] == "Шукуров\nЗариф\nСевинович"
    assert v["svera.fio_udo_right"] == "Шукурову Зарифу Севиновичу"
    # the same ПО number heads the protocol and is cited on the certificate
    assert v["svera.protocol_title"] == "ПРОТОКОЛ № ПО3963"
    assert "ПО3963" in str(v["svera.osnovanie"])
    # the certificate number doubles as the protocol's регистрац. №
    assert v["svera.udo_number"] == "606"
    assert str(v["svera.result"]).splitlines() == ["Сдал,", "606", "180035 9856150"]
    # dates carry exactly one Russian year marker
    assert str(v["svera.date_long_top"]).count("г.") == 1
    assert str(v["svera.prikaz"]).count("г.") == 1


@pytest.mark.skipif(not HAS_TEMPLATE, reason="svera template missing")
def test_seed_and_generate(container) -> None:
    professions = container.resolve(ProfessionService)
    svera = container.resolve(SveraService)
    assert professions.count() == 5
    prof = professions.list()[0]

    passport = Passport(surname="ШУКУРОВ", name="ЗАРИФ", patronymic="СЕВИНОВИЧ", number="1")
    po = svera.next_po_number()
    result = svera.generate(passport, prof, issue_date=date(2023, 11, 6), photo_path=None)

    assert result.pdf_path.exists()
    assert result.pdf_path.name == "ШУКУРОВ_ЗАРИФ.pdf"
    assert result.po_number == po
    doc = fitz.open(str(result.pdf_path))
    assert doc.page_count == 2
    protocol, udo = doc[0].get_text(), doc[1].get_text()
    assert f"ПРОТОКОЛ № ПО{po}" in " ".join(protocol.split())
    assert "Шукурову Зарифу Севиновичу" in " ".join(udo.split())
    # the centre's round stamp is printed on the certificate page
    assert doc[1].get_images(), "stamp/photo images missing on the certificate"
    doc.close()
    # ПО counter advances
    assert svera.next_po_number() == po + 1


# ------------------------------------------------- a name typed by hand


class _FakeOcr:
    """Stands in for Gemini: returns a deliberately misread name."""

    def __init__(self) -> None:
        self.calls = 0

    def available(self) -> bool:
        return True

    def read_passport(self, _image: bytes) -> Passport:
        self.calls += 1
        return Passport(surname="ВОЛТАЗОДА", name="РУСТАН",
                        patronymic="МАХМАД", number="402565897")


def _controller(ocr):
    from src.controllers.svera_controller import SveraController

    return SveraController(professions=None, ocr=ocr, svera=None)


def test_a_typed_name_overrides_what_the_passport_was_read_as() -> None:
    """The centre saw OCR misread surnames, so a typed one must win."""
    ocr = _FakeOcr()
    student = _controller(ocr)._student(b"img", "БОЛТАЗОДА", "РУСТАМ", "")
    assert (student.surname, student.name) == ("БОЛТАЗОДА", "РУСТАМ")
    # the part left blank still comes off the passport
    assert student.patronymic == "МАХМАД"
    assert student.number == "402565897"


def test_an_untouched_name_is_left_to_the_passport() -> None:
    student = _controller(_FakeOcr())._student(b"img", "", "", "")
    assert student.surname == "ВОЛТАЗОДА"


def test_a_certificate_can_be_made_with_no_passport_at_all() -> None:
    ocr = _FakeOcr()
    student = _controller(ocr)._student(None, "БОЛТАЗОДА", "РУСТАМ", "МАХМАД")
    assert (student.surname, student.name, student.patronymic) == (
        "БОЛТАЗОДА", "РУСТАМ", "МАХМАД")
    assert ocr.calls == 0, "the passport reader should not have been called"


def test_no_passport_and_no_name_is_refused() -> None:
    from src.common.errors import OfisError

    with pytest.raises(OfisError):
        _controller(_FakeOcr())._student(None, "", "", "")


# ------------------------------------------- a long profession wraps


@pytest.mark.skipif(not HAS_TEMPLATE, reason="СФЕРА template not bundled")
@pytest.mark.parametrize(
    ("profession", "expected_lines"),
    [("Электрогазосварщик", 1),
     ("Монтажник по монтажу стальных и железобетонных конструкций", 2)],
)
def test_a_long_profession_wraps_instead_of_shrinking(
        profession, expected_lines) -> None:
    """It used to be squeezed onto one line until it was unreadable."""
    from src.pdf.svera_udo import (
        _L_PROF_SIZE,
        _L_PROF_WIDTH,
        UdoData,
        render_udostoverenie,
    )

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    render_udostoverenie(page, UdoData(
        number="3606", fio_dative=["Болтазоду", "Рустаму", "Махмаду"],
        profession=profession, qualification="—",
        issue_date="27.07.2026 г.", basis="—"))

    lines = [sp for b in page.get_text("dict")["blocks"]
             for ln in b.get("lines", []) for sp in ln["spans"]
             if "“" in sp["text"] or "”" in sp["text"]
             or (sp["bbox"][1] > 180 and sp["bbox"][3] < 205
                 and sp["bbox"][2] < 290 and sp["text"].strip())]
    assert len(lines) == expected_lines, [sp["text"] for sp in lines]
    if expected_lines == 1:
        assert lines[0]["size"] >= _L_PROF_SIZE - 0.01
        return

    # the two lines share a size and come out roughly even, so they read as one
    # block rather than a long line with a stub under it
    assert lines[0]["size"] == lines[1]["size"]
    widths = [sp["bbox"][2] - sp["bbox"][0] for sp in lines]
    assert max(widths) / min(widths) < 2.0, widths

    # and the whole point: far bigger than squeezing it all onto one line,
    # which is what the card used to do
    from src.pdf.engine import _font_file

    font = fitz.Font(fontfile=str(_font_file("OfisSerifBoldItalic")))
    one_line = _L_PROF_SIZE * _L_PROF_WIDTH / font.text_length(
        f"“{profession}”", fontsize=_L_PROF_SIZE)
    assert lines[0]["size"] > one_line * 1.5, (lines[0]["size"], one_line)
