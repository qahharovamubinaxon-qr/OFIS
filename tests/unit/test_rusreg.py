"""РУС РЕГ — the registration sheet for the office's Russian-citizen workers.

The renderer is measured against the office's own filled sheet, the service
against what the office expects to still be there tomorrow, and the bot flow
against the questions it must ask.
"""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import fitz
import pytest
from src.config import paths
from src.pdf.rusreg_renderer import (
    RusRegData,
    fio_born,
    output_name,
    render,
    ru_date,
    split_address,
    values,
)
from src.pdf.rusreg_spec import DOC_BIRTH, DOC_PASSPORT, FIELDS


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    sandbox = tempfile.mkdtemp()
    monkeypatch.setenv("XDG_DATA_HOME", sandbox)
    monkeypatch.setenv("LOCALAPPDATA", sandbox)
    paths.data_dir.cache_clear()
    yield
    paths.data_dir.cache_clear()


def _blank(folder: Path) -> Path:
    blank = folder / "SFERA.pdf"
    doc = fitz.open()
    doc.new_page(width=595, height=425)
    doc.save(str(blank))
    doc.close()
    return blank


_WORKER = dict(
    reg_number="1998/19/126",
    surname="ХУДОЙБЕРДИЕВ", name="ФАРХОД", patronymic="РУЗИМУРАТОВИЧ",
    birth_date=date(1980, 5, 30),
    birth_place="С. НАВОБАД ТАДЖИКСКАЯ ССР",
    address="Г. МОСКВА, УЛ. РЕМИЗОВА, Д. 4, КВ. 16",
    valid_from=date(2026, 7, 31), valid_to=date(2027, 7, 30),
    doc_series="45 25", doc_number="105235",
    doc_issued=date(2025, 6, 4), doc_issued_by="ГУ МВД РОССИИ ПО Г. МОСКВЕ",
    firm="ОТДЕЛ КАДРОВ ООО СФЕРА", signer="ПРОКОПЕНКО А.Г.")


# ------------------------------------------------------------- the values


def test_dates_are_written_the_way_the_form_writes_them() -> None:
    assert ru_date(date(2026, 7, 31)) == ("31", "ИЮЛЯ", "2026")
    assert ru_date(date(2025, 6, 4)) == ("04", "ИЮНЯ", "2025")
    assert ru_date(None) == ("", "", "")


def test_the_vid_line_names_the_document_that_was_uploaded() -> None:
    """A passport prints «ПАСПОРТ РФ»; a birth certificate prints the
    certificate — the sheet must name what it was really issued against."""
    passport = values(RusRegData(**_WORKER, is_passport=True))
    metrka = values(RusRegData(**_WORKER, is_passport=False))
    assert passport["doc_kind"] == DOC_PASSPORT
    assert metrka["doc_kind"] == DOC_BIRTH


def test_the_fio_line_carries_the_birth_date() -> None:
    line = fio_born(RusRegData(**_WORKER))
    assert line.startswith("ХУДОЙБЕРДИЕВ ФАРХОД РУЗИМУРАТОВИЧ")
    assert "30.05.1980" in line and "ГОДА РОЖДЕНИЯ" in line


def test_a_long_address_breaks_at_a_comma_not_mid_word() -> None:
    first, second = split_address(
        "г. Москва, ул. Профсоюзная, д. 144, корп. 2, кв. 165, "
        "этаж 12, домофон 165", limit=60)
    assert first.endswith(",")
    assert not first.endswith(" ,")
    assert second
    assert (first + " " + second).replace(",  ", ", ")  # nothing lost
    short, rest = split_address("Г. МОСКВА, УЛ. МИРА, Д. 1")
    assert rest == ""


def test_the_filename_is_surname_name() -> None:
    assert output_name(RusRegData(**_WORKER)) == "ХУДОЙБЕРДИЕВ_ФАРХОД.pdf"


# ------------------------------------------------------------ the render


def test_every_value_lands_where_the_measured_sheet_put_it(tmp_path) -> None:
    pdf = render(RusRegData(**_WORKER), _blank(tmp_path))
    with fitz.open("pdf", pdf) as doc:
        page = doc[0]
        width, height = page.rect.width, page.rect.height
        spans = {}
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    # MuPDF hands spaces back as \xa0 — normalised, or nothing
                    # multi-word ever matches
                    text = span["text"].replace("\xa0", " ").strip()
                    if text:
                        spans[text] = (span["bbox"][0] / width,
                                       span["origin"][1] / height)
    # the left-anchored fields sit exactly on their measured spots
    for text, key in (("1998/19/126", "reg_number"),
                      ("ПАСПОРТ РФ", "doc_kind"),
                      ("ГУ МВД РОССИИ ПО Г. МОСКВЕ", "issued_by"),
                      ("ОТДЕЛ КАДРОВ ООО СФЕРА", "firm")):
        assert text in spans, f"{key} never printed"
        x, baseline = spans[text]
        want_x, want_y, _ = FIELDS[key]
        assert abs(x - want_x) < 0.004, f"{key} x drifted"
        assert abs(baseline - want_y) < 0.004, f"{key} baseline drifted"
    # the centred day sits INSIDE its rule, not flush on the anchor
    assert "31" in spans


def test_what_the_office_dragged_wins_over_the_measured_spot(tmp_path) -> None:
    moved = RusRegData(**_WORKER,
                       layout={"fields": {"firm": [0.30, 0.50, 0.030]}})
    pdf = render(moved, _blank(tmp_path))
    with fitz.open("pdf", pdf) as doc:
        page = doc[0]
        rect = page.search_for("ОТДЕЛ КАДРОВ ООО СФЕРА")[0]
        assert abs(rect.x0 / page.rect.width - 0.30) < 0.01
        # size is a share of page height — 0.030 * 425 ≈ 12.75pt tall ink
        assert rect.height > 10


def test_a_picture_blank_is_accepted_too(tmp_path) -> None:
    """The office scans blanks as JPGs as often as PDFs."""
    import PIL.Image

    picture = tmp_path / "blank.png"
    PIL.Image.new("RGB", (1190, 850), (255, 255, 255)).save(picture)
    pdf = render(RusRegData(**_WORKER), picture)
    assert pdf[:5] == b"%PDF-"
    with fitz.open("pdf", pdf) as doc:
        assert doc[0].search_for("ПАСПОРТ РФ")


# ------------------------------------------------------------ the service


def _service():
    from src.app import build_container
    from src.config.settings_service import SettingsService
    from src.services.rusreg_service import RusRegService

    return RusRegService(build_container().resolve(SettingsService))


def test_what_the_office_types_once_is_still_there_tomorrow() -> None:
    service = _service()
    service.remember(address="Г. МОСКВА, УЛ. РЕМИЗОВА, Д. 4, КВ. 16",
                     firm="ОТДЕЛ КАДРОВ ООО СФЕРА",
                     reg_number="1998/19/126", signer="ПРОКОПЕНКО А.Г.")
    assert service.firm() == "ОТДЕЛ КАДРОВ ООО СФЕРА"
    assert service.reg_number() == "1998/19/126"
    assert service.address() == "Г. МОСКВА, УЛ. РЕМИЗОВА, Д. 4, КВ. 16"


def test_the_address_list_moves_a_reused_flat_up_instead_of_doubling_it() -> None:
    service = _service()
    service.remember(address="Г. МОСКВА, УЛ. РЕМИЗОВА, Д. 4, КВ. 16")
    service.remember(address="Г. МОСКВА, ПР-КТ МИРА, Д. 1")
    # the same flat again, typed in another case — moved up, not doubled
    service.remember(address="г. москва, ул. ремизова, д. 4, кв. 16")
    known = service.addresses()
    assert len(known) == 2
    assert known[0].upper() == "Г. МОСКВА, УЛ. РЕМИЗОВА, Д. 4, КВ. 16"


def test_generate_writes_the_sheet_and_remembers_everything(tmp_path) -> None:
    service = _service()
    blank = service.add_template("СФЕРА", _blank(tmp_path))
    assert blank in service.templates()

    result = service.generate(RusRegData(**_WORKER, is_passport=True), blank)
    assert result.saved.exists()
    assert result.saved.name.startswith("ХУДОЙБЕРДИЕВ_ФАРХОД")
    assert service.address() == _WORKER["address"]
    assert service.firm() == _WORKER["firm"]

    service.remove_template(blank)
    assert blank not in service.templates()


def test_generate_without_a_blank_says_so() -> None:
    from src.common.errors import ValidationError

    with pytest.raises(ValidationError):
        _service().generate(RusRegData(**_WORKER), None)


# ---------------------------------------------- the patronymic guarantee


def test_the_passport_prompt_demands_the_printed_page_not_only_the_mrz() -> None:
    """A Tajik MRZ never prints the patronymic; the page above does.

    Registrations were coming out with no отчество because the model fixated
    on the machine zone. The prompt now says in so many words: whatever the
    MRZ lacks comes from the printed part of the page.
    """
    from src.ai.prompts import _PASSPORT

    assert "patronymic" in _PASSPORT
    assert "MRZ often has NO patronymic" in _PASSPORT


def test_a_valid_mrz_without_a_patronymic_keeps_the_models_one(monkeypatch) -> None:
    """Proven MRZ values win — but a value the zone does not carry must never
    erase what the model read off the printed page."""
    from src.domain.documents import Passport
    from src.ocr import service as ocr_service

    class _Zone:
        found = True
        valid = True
        problems = ()
        fields = {"surname": "ХУДОЙБЕРДИЕВ", "name": "ФАРХОД",
                  "number": "401234567"}          # no patronymic — Tajik zone

    monkeypatch.setattr(ocr_service.mrz_reader, "read",
                        lambda *a, **k: _Zone())

    class _Answer:
        text = ""
        fields = {"mrz_line1": "", "mrz_line2": ""}

    before = Passport(surname="ХУДОЙБЕРДИЕВ", name="ФАРХОД",
                      patronymic="РУЗИМУРАТОВИЧ", number="401234567")
    after = ocr_service.OcrService._with_mrz(before, _Answer())
    assert after.patronymic == "РУЗИМУРАТОВИЧ", (
        "the patronymic read off the printed page was thrown away")
    assert after.mrz_checked


# ------------------------------------------- the two reported read failures


def test_rusreg_reads_through_the_schemaless_door(monkeypatch) -> None:
    """The PASSPORT schema insists on ISO dates; these prompts ask ДД.ММ.ГГГГ.

    Read through it, every answer died with «birth_date санаси ўқилмади» and
    the operator saw an error instead of fields — for the паспорт РФ and the
    birth certificate alike. The reader must go through UNKNOWN, which takes
    flat strings as they are.
    """
    from src.app import build_container
    from src.config.settings_service import SettingsService
    from src.controllers.rusreg_controller import RusRegController
    from src.domain.enums import DocType
    from src.ocr.service import OcrService
    from src.services.rusreg_service import RusRegService

    container = build_container()
    controller = RusRegController(container.resolve(OcrService),
                                  RusRegService(container.resolve(SettingsService)))
    seen = {}

    class _Answer:
        text = ""
        fields = {"surname": "КИРИЕНКО", "name": "ЛУИЗА",
                  "patronymic": "ИЛЬИНИЧНА", "birth_date": "25.05.1990",
                  "series": "46 15", "number": "974527"}

    def fake_extract(image, doc_type, prompt):
        seen["doc_type"] = doc_type
        return _Answer()

    monkeypatch.setattr(controller._ocr.ai, "extract", fake_extract)
    monkeypatch.setattr("src.controllers.rusreg_controller.prepare_image",
                        lambda image: image)

    fields = controller.read_document(b"img", is_passport=True)
    assert seen["doc_type"] == DocType.UNKNOWN, (
        "the schema door died on ДД.ММ.ГГГГ dates")
    assert fields["surname"] == "КИРИЕНКО"
    assert fields["birth_date"] == "25.05.1990"


def test_an_invented_patronymic_that_is_the_name_is_dropped() -> None:
    """The Philippine passport: name ДЖОСЕЛИН, «patronymic» ДЖЕЛИН.

    The model had mangled the given name into the отчество field, and the
    invented отчество went onto a registration. A real patronymic comes from
    the father's name and never resembles the worker's own.
    """
    from src.ocr.service import _mangled_name, _passport_from

    assert _mangled_name("ДЖЕЛИН", "ДЖОСЕЛИН")
    read = _passport_from({"surname": "АНДО", "name": "ДЖОСЕЛИН",
                           "patronymic": "ДЖЕЛИН", "number": "P9314956C"})
    assert read.patronymic is None

    # real patronymics survive — including one derived from a first name
    for patronymic, name in (("РУЗИМУРАТОВИЧ", "ФАРХОД"),
                             ("ИЛЬИНИЧНА", "ЛУИЗА"),
                             ("ИВАНОВИЧ", "ИВАН")):
        assert not _mangled_name(patronymic, name)


def test_the_patent_name_wins_including_its_missing_patronymic(monkeypatch) -> None:
    """The patent prints the full ФИО in Russian — a patent with no отчество
    means the worker HAS none, and the passport's invented one must not
    slip back in through the fallback."""
    from src.domain.documents import Passport, Patent
    from src.ocr.service import OcrService

    service = OcrService.__new__(OcrService)
    monkeypatch.setattr(
        OcrService, "read_passport",
        lambda self, image: Passport(surname="АКДО", name="ДЖОСЕЛИН",
                                     patronymic="ДЖЕЛИН", number="P9314956C"))
    monkeypatch.setattr(
        OcrService, "read_patent",
        lambda self, front, back=None: Patent(
            number="2600184371", profession="ПОДСОБНЫЙ РАБОЧИЙ",
            holder_surname="АНДО", holder_name="ДЖОСЕЛИН"))

    passport, _patent = service.read_documents(b"pass", b"front", None)
    assert passport.surname == "АНДО", "the patent's Russian ФИО must win"
    assert passport.patronymic is None, (
        "the passport's invented отчество slipped back through the fallback")
