"""СТРАХОВКА МАШИНАГА — ОСАГО for the workers who drive the firm's cars.

Every insurer lays its policy out differently, so these tests run against all
four templates the office actually works with: whatever the layout, the previous
customer's car and drivers must be gone and this one's must be there.
"""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import pytest

docx = pytest.importorskip("docx")

from src.common.errors import ValidationError  # noqa: E402
from src.config import paths  # noqa: E402
from src.domain.insurance_template import InsuranceTemplate  # noqa: E402
from src.domain.vehicle import DriverLicence, Sts  # noqa: E402
from src.services import insurance_docx  # noqa: E402
from src.services.insurance_service import (  # noqa: E402
    BUNDLED,
    MAX_DRIVERS,
    InsuranceService,
    InsuranceTemplateService,
    cover_until,
)

ROOT = Path(__file__).resolve().parents[2]
BLANKS = ROOT / "templates" / "strahovka"
CODES = [code for code, _n, _i in BUNDLED
         if (BLANKS / code / "polis.docx").exists()]

pytestmark = pytest.mark.skipif(not CODES, reason="ОСАГО templates not bundled")

STS = Sts(series="50 ОЕ", number="909090", plate="А123ВС750",
          vin="XWB4A1CD9A2123456", mark="Hyundai", model="Solaris",
          owner_fio="ООО «СФЕРА»")
DRIVERS = [
    DriverLicence(surname="НАЗАРОВ", name="МУРОДУЛЛО", patronymic="ХАИТАЛИЕВИЧ",
                  series="AF", number="1234567"),
    DriverLicence(surname="КАРИМОВ", name="АЗИЗ", patronymic="ОЛИМ УГЛИ",
                  series="AF", number="7654321"),
]

#: The people and cars printed in the templates the office supplied. None of
#: them may survive into the policy made for somebody else.
PREVIOUS = ("KMHDN41BP3U633162", "KNEDE22126611237", "XWB4A1CD9A21203",
            "Т566ВЕ40", "X526AY550", "ЧУНАЕВ", "КАРАЕВ", "Пайзуллаев",
            "Туйчиев", "Кудратов", "МАХМАДОВ", "МАХМАДЗОДА", "AF2970819",
            "AF5137466", "AF2703984", "AA0622980", "5036 634917")


@pytest.fixture(autouse=True)
def _appdata(monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", tempfile.mkdtemp())
    paths.data_dir.cache_clear()
    yield
    paths.data_dir.cache_clear()


def _template(code: str) -> InsuranceTemplate:
    return InsuranceTemplate(name=code, internal_code=code,
                             template_path=BLANKS / code / "polis.docx")


def _read(path: Path) -> str:
    doc = docx.Document(str(path))
    parts = [" ".join(p.text.split()) for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.append(" | ".join(" ".join(c.text.split()) for c in row.cells))
    return "\n".join(p for p in parts if p.strip())


def _squashed(path: Path) -> str:
    """The same text with the cell separators gone — a value an insurer
    prints one character per box reads as «X | W | B | …» otherwise."""
    return _read(path).replace(" ", "").replace("|", "")


def _run(code: str, tmp_path: Path, *, unlimited: bool = False,
         drivers=None, start=date(2026, 7, 10)):
    return InsuranceService().generate(
        STS, DRIVERS if drivers is None else drivers, _template(code),
        start=start, unlimited=unlimited, output_dir=tmp_path)


# --------------------------------------------------------------- the dates


@pytest.mark.parametrize("start, end", [
    (date(2026, 7, 10), date(2027, 7, 9)),
    (date(2026, 1, 1), date(2026, 12, 31)),
    (date(2028, 2, 29), date(2029, 2, 28)),      # cover taken out on a leap day
    (date(2026, 3, 1), date(2027, 2, 28)),
])
def test_cover_runs_a_year_to_the_day_before(start, end) -> None:
    assert cover_until(start) == end


@pytest.mark.parametrize("code", CODES)
def test_both_dates_are_written_where_the_form_prints_them(code, tmp_path):
    result = _run(code, tmp_path)
    body = _read(result.docx_path)
    assert "10.07.2026" in body or "«10» июля 2026" in body, code
    if "term" in body or "Срок страхования" in body:
        assert "09.07.2027" in body or any(
            "катак-катак" in n for n in result.notes), code


# -------------------------------------------------------------- the filling


@pytest.mark.parametrize("code", CODES)
def test_the_previous_customer_is_gone(code, tmp_path) -> None:
    body = _read(_run(code, tmp_path).docx_path)
    left = [old for old in PREVIOUS if old in body]
    assert not left, (code, left)


@pytest.mark.parametrize("code", CODES)
def test_this_car_is_in_the_policy(code, tmp_path) -> None:
    result = _run(code, tmp_path)
    body = _read(result.docx_path)
    assert STS.vin in body or STS.vin in _squashed(result.docx_path), code
    assert STS.plate in body, code


@pytest.mark.parametrize("code", CODES)
def test_the_named_drivers_are_listed(code, tmp_path) -> None:
    body = _read(_run(code, tmp_path).docx_path)
    for driver in DRIVERS:
        assert driver.surname in body, (code, driver.surname)
        assert driver.licence in body, (code, driver.licence)


@pytest.mark.parametrize("code", CODES)
def test_unused_driver_rows_are_dashed_not_left_with_someone_else(code, tmp_path):
    body = _read(_run(code, tmp_path, drivers=DRIVERS[:1]).docx_path)
    assert DRIVERS[0].surname in body
    assert DRIVERS[1].surname not in body


@pytest.mark.parametrize("code", CODES)
def test_covering_anyone_clears_the_named_list(code, tmp_path) -> None:
    """«неограниченного количества лиц» means the table names nobody."""
    body = _read(_run(code, tmp_path, unlimited=True).docx_path)
    for driver in DRIVERS:
        assert driver.surname not in body, (code, driver.surname)


def test_more_drivers_than_the_form_has_rows_is_reported(tmp_path) -> None:
    many = [DriverLicence(surname=f"ВОДИТЕЛЬ{i}", name="ИМЯ", series="AF",
                          number=f"111111{i}") for i in range(MAX_DRIVERS)]
    result = InsuranceService().generate(
        STS, many, _template(CODES[0]), start=date(2026, 7, 10),
        unlimited=False, output_dir=tmp_path)
    body = _read(result.docx_path)
    written = sum(1 for d in many if d.surname in body)
    assert written == result.drivers
    if written < len(many):
        assert any("қатор" in note for note in result.notes)


def test_only_four_drivers_are_taken(tmp_path) -> None:
    five = [DriverLicence(surname=f"ВОДИТЕЛЬ{i}", name="ИМЯ", series="AF",
                          number=f"222222{i}") for i in range(5)]
    result = InsuranceService().generate(
        STS, five, _template(CODES[0]), start=date(2026, 7, 10),
        unlimited=False, output_dir=tmp_path)
    assert "ВОДИТЕЛЬ4" not in _read(result.docx_path)


def test_a_named_policy_needs_at_least_one_licence(tmp_path) -> None:
    with pytest.raises(ValidationError):
        InsuranceService().generate(STS, [], _template(CODES[0]),
                                    start=date(2026, 7, 10), unlimited=False,
                                    output_dir=tmp_path)


# ------------------------------------------------------- what it will not do


@pytest.mark.parametrize("code", CODES)
def test_the_previous_electronic_signature_is_erased(code, tmp_path) -> None:
    """A stale certificate would make an unsigned policy look signed."""
    body = _read(_run(code, tmp_path).docx_path).lower()
    for trace in ("подписано электронной подписью", "удостоверяющий центр",
                  "усиленной квалифицированной электронно"):
        assert trace not in body, (code, trace)


@pytest.mark.parametrize("code", CODES)
def test_no_policy_number_is_invented(code, tmp_path) -> None:
    """РСА allocates those through the insurer — the program never makes one."""
    before = _read(_template(code).template_path)
    after = _read(_run(code, tmp_path).docx_path)
    import re

    shape = re.compile(r"№\s*[A-ZА-Я]{3}\s*\d{10}")
    assert set(shape.findall(after)) <= set(shape.findall(before)), code


@pytest.mark.parametrize("code", CODES)
def test_the_operator_is_told_what_was_left_alone(code, tmp_path) -> None:
    notes = _run(code, tmp_path).notes
    assert any("серия/номер" in n for n in notes)
    assert any("КБМ" in n for n in notes)


def test_a_number_is_only_handed_out_from_a_block_that_was_allocated() -> None:
    class _Settings(dict):
        def get(self, key, default=None):
            return super().get(key, default)

        def set(self, key, value):
            self[key] = value

    settings = _Settings()
    assert InsuranceService(settings).policy_number() == ""   # nothing recorded

    settings.update({"osago.series": "ХХХ", "osago.number_from": "0000000001",
                     "osago.number_to": "0000000002"})
    service = InsuranceService(settings)
    assert service.policy_number() == "ХХХ 0000000001"
    assert service.policy_number() == "ХХХ 0000000002"
    with pytest.raises(ValidationError):
        service.policy_number()                  # the block is used up


# ------------------------------------------------------------- the registry


def test_the_bundled_templates_are_offered_once(tmp_path) -> None:
    from src.database.connection import Database
    from src.database.repositories.insurance_template_repo import (
        InsuranceTemplateRepository,
    )

    db = Database(tmp_path / "ofis.db")
    db.migrate()
    service = InsuranceTemplateService(InsuranceTemplateRepository(db))
    assert service.seed_bundled() == len(CODES)
    assert service.seed_bundled() == 0
    assert {t.internal_code for t in service.list()} == set(CODES)


def test_another_insurers_template_can_be_added(tmp_path) -> None:
    from src.database.connection import Database
    from src.database.repositories.insurance_template_repo import (
        InsuranceTemplateRepository,
    )

    db = Database(tmp_path / "ofis.db")
    db.migrate()
    repo = InsuranceTemplateRepository(db)
    service = InsuranceTemplateService(repo)
    source = BLANKS / CODES[0] / "polis.docx"

    added = service.create("АльфаСтрахование", "ALFA", source,
                           insurer="АО «АльфаСтрахование»", firm="ООО СФЕРА")
    assert added.internal_code == "alfa"
    assert added.template_path.exists()
    assert added.template_path != source, "the upload is copied, not referenced"
    assert repo.by_internal_code("alfa").firm == "ООО СФЕРА"

    with pytest.raises(ValidationError):
        service.create("Дубликат", "alfa", source)

    service.archive(added.id)
    assert "alfa" not in {t.internal_code for t in service.list()}


def test_only_a_word_template_is_accepted(tmp_path) -> None:
    from src.database.connection import Database
    from src.database.repositories.insurance_template_repo import (
        InsuranceTemplateRepository,
    )

    db = Database(tmp_path / "ofis.db")
    db.migrate()
    service = InsuranceTemplateService(InsuranceTemplateRepository(db))
    pdf = tmp_path / "polis.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    with pytest.raises(ValidationError):
        service.create("PDF", "pdf", pdf)


# -------------------------------------------------------------- the shapes


def test_a_plate_typed_in_either_alphabet_is_recognised() -> None:
    """Templates are typed with whichever keyboard was on."""
    for shape_key, pattern in insurance_docx._SHAPES:
        if shape_key == "plate":
            assert pattern.search("X526AY550")      # latin look-alikes
            assert pattern.search("Т566ВЕ40")       # cyrillic
            assert not pattern.search("ЯЯ123ЯЯ")
