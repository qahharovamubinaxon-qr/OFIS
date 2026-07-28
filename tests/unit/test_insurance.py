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
            "AF5137466", "AF2703984", "AA0622980", "5036 634917",
            # the страхователь and собственник each template was sold to —
            # two of them sit in text boxes, where nothing used to look
            "ДЕНИСОВА", "Авдодина", "АБДУЛКАПАРОВ",
            # a VIN printed one character per box
            "XTA21150033523017", "XWB4A11CD9A212003")


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
    """Everything the policy says — text boxes and nested tables included.

    Reading only ``doc.paragraphs`` and ``doc.tables`` is what let the
    собственник go on being wrong: one insurer keeps «1. Страхователь»,
    «Собственник транспортного средства» and the seventeen boxes of the VIN
    inside text boxes, and a test that cannot see them passes on a policy that
    still carries the previous customer's name.
    """
    doc = docx.Document(str(path))
    parts = [" ".join(p.text.split())
             for p in insurance_docx._all_paragraphs(doc)]
    for table in insurance_docx._all_tables(doc):
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
    result = _run(code, tmp_path)
    # both forms: a VIN spread over its boxes only reads back squashed
    body = _read(result.docx_path) + "\n" + _squashed(result.docx_path)
    left = [old for old in PREVIOUS if old in body or
            old.replace(" ", "") in body]
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
def test_the_operator_is_reminded_about_the_signature(code, tmp_path) -> None:
    """It is left in place — deleting the operator's template was overreach —
    and the reminder that it has to come from the insurer is carried up."""
    result = _run(code, tmp_path)
    if any("подписан" in line.lower()
           for line in _all_lines(_template(code).template_path)):
        assert any("имзо" in note for note in result.notes), code


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


# ------------------------------------------------ what the upload decides


class _Reader:
    """Stands in for the OCR chain: an СТС photo and licence photos."""

    def __init__(self) -> None:
        self.licences = 0

    def available(self) -> bool:
        return True

    def read_sts(self, front, back=None):
        return STS

    def read_licence(self, image):
        self.licences += 1
        return DriverLicence(surname=f"ВОДИТЕЛЬ{self.licences}", name="ИМЯ",
                             series="AF", number=f"111111{self.licences}")


def _controller(tmp_path):
    from src.controllers.insurance_controller import InsuranceController
    from src.database.connection import Database
    from src.database.repositories.insurance_template_repo import (
        InsuranceTemplateRepository,
    )

    db = Database(tmp_path / "o.db")
    db.migrate()
    templates = InsuranceTemplateService(InsuranceTemplateRepository(db))
    templates.seed_bundled()
    return InsuranceController(templates, _Reader(), InsuranceService()), templates


@pytest.mark.parametrize("code", CODES)
def test_only_the_car_means_the_policy_covers_anyone(code, tmp_path) -> None:
    """No licence photograph — «неограниченного количества лиц» is ticked."""
    controller, templates = _controller(tmp_path)
    template = next(t for t in templates.list() if t.internal_code == code)

    result = controller.generate_from_images(
        template, b"front", b"back", [], start=date(2026, 7, 10))

    assert result.drivers == 0
    body = _read(result.docx_path)
    assert _ticked(body, unlimited=True), (code, body[:400])


@pytest.mark.parametrize("count", [1, 2, 4])
def test_a_licence_photograph_names_the_drivers_instead(count, tmp_path) -> None:
    """The upload decides — the operator is not asked to say it twice."""
    controller, templates = _controller(tmp_path)
    template = next(t for t in templates.list()
                    if t.internal_code == "ingosstrah")

    result = controller.generate_from_images(
        template, b"front", b"back", [b"p"] * count, start=date(2026, 7, 10))

    assert result.drivers == count
    body = _read(result.docx_path)
    assert _ticked(body, unlimited=False)
    assert not _ticked(body, unlimited=True)
    for i in range(1, count + 1):
        assert f"ВОДИТЕЛЬ{i}" in body


def test_uploading_only_the_car_no_longer_refuses_to_run(tmp_path) -> None:
    """This is what stopped RUN: the form said «named», the upload said none."""
    controller, templates = _controller(tmp_path)
    template = templates.list()[0]
    result = controller.generate_from_images(
        template, b"front", b"back", [], start=date(2026, 7, 10))
    assert result.docx_path.exists()


_MARK = __import__("re").compile(r"\s*(\[[XХxх]\]|[XХxх✔✓])")


def _ticked(body: str, unlimited: bool) -> bool:
    """Is the mark right after that option — the box the form actually offers?

    The two options overlap in wording («неограниченного количества **лиц,
    допущенных к управлению**»), so the option is located the same way the
    program locates it rather than by a naive search.
    """
    pattern = (insurance_docx._UNLIMITED if unlimited
               else insurance_docx._LIMITED)
    for line in body.split("\n"):
        for match in pattern.finditer(line):
            if _MARK.match(line[match.end():match.end() + 6]):
                return True
    return False


# ---------------------------------------------------------------- the screen


def test_the_screen_reads_the_drop_zones_the_way_they_are_declared() -> None:
    """DropZone.path is a property; calling it crashed RUN before it began."""
    import inspect

    from src.ui.views import insurance_view, template_view
    from src.ui.widgets.drop_zone import DropZone

    assert isinstance(DropZone.path, property)
    for module in (insurance_view, template_view):
        assert ".path()" not in inspect.getsource(module), module.__name__


# ------------------------------------------------------- where it was saved


def _view(tmp_path, monkeypatch, *, chosen: Path | None):
    """The insurance screen, with the two dialogs answered for us."""
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

    from src.ui.views import insurance_view

    QApplication.instance() or QApplication([])
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        staticmethod(lambda *a, **k: str(chosen) if chosen else ""))
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    controller, templates = _controller(tmp_path)
    return insurance_view.InsuranceView(controller), controller, templates


def test_a_finished_policy_asks_where_to_save_it(tmp_path, monkeypatch) -> None:
    pytest.importorskip("PySide6")
    desktop = tmp_path / "Ish stoli"
    desktop.mkdir()
    view, controller, templates = _view(tmp_path, monkeypatch, chosen=desktop)

    result = controller.generate_from_images(
        templates.list()[0], b"front", b"back", [], start=date(2026, 7, 10))
    view._done(result)

    # the PDF goes with it wherever Word is installed to make one
    saved = sorted(p.name for p in desktop.iterdir())
    assert result.docx_path.name in saved
    assert saved == sorted(f.name for f in
                           (result.docx_path, result.pdf_path) if f)
    assert str(desktop) in view._status.text()


def test_declining_still_says_where_the_file_is(tmp_path, monkeypatch) -> None:
    """A file the operator cannot find is not a finished job."""
    pytest.importorskip("PySide6")
    view, controller, templates = _view(tmp_path, monkeypatch, chosen=None)

    result = controller.generate_from_images(
        templates.list()[0], b"front", b"back", [], start=date(2026, 7, 10))
    view._done(result)

    assert str(result.docx_path.parent) in view._status.text()
    assert result.docx_path.exists()


def test_the_drop_zones_are_cleared_for_the_next_car(tmp_path, monkeypatch) -> None:
    pytest.importorskip("PySide6")
    view, controller, templates = _view(tmp_path, monkeypatch, chosen=None)
    view._sts_front._set_path(tmp_path / "a.jpg")
    view._licences[0]._set_path(tmp_path / "b.jpg")

    result = controller.generate_from_images(
        templates.list()[0], b"front", b"back", [b"p"], start=date(2026, 7, 10))
    view._done(result)

    assert view._sts_front.path is None
    assert view._uploaded_licences() == []
    assert "неограниченного" in view._coverage.text(), \
        "with the zones cleared the next car starts from «covers anyone»"


# --------------------------------------- the operator's template is not ours


def _all_lines(path: Path) -> list[str]:
    document = docx.Document(str(path))
    out = [" ".join(p.text.split())
           for p in insurance_docx._all_paragraphs(document)]
    for table in insurance_docx._all_tables(document):
        for row in table.rows:
            out.append(" | ".join(" ".join(c.text.split()) for c in row.cells))
    return out


@pytest.mark.parametrize("code", CODES)
def test_not_one_line_of_the_template_is_deleted(code, tmp_path) -> None:
    """An earlier version erased the insurer's signature lines outright."""
    template = _template(code)
    before = _all_lines(template.template_path)
    after = _all_lines(_run(code, tmp_path).docx_path)

    assert len(before) == len(after), code
    assert sum(1 for line in after if line.strip()) == \
        sum(1 for line in before if line.strip()), "a line was emptied"


#: A line of the insurer's own prose: long, and mostly words rather than data.
def _is_prose(line: str) -> bool:
    import re

    words = re.findall(r"[А-Яа-яЁё]{4,}", line)
    return len(line) >= 70 and len(words) >= 8


@pytest.mark.parametrize("code", CODES)
def test_the_insurers_own_wording_is_never_rewritten(code, tmp_path) -> None:
    """The legal text, the headings and the notes are the operator's file.

    This is the failure that made the module unusable: “Оборотная сторона
    страхового полиса…” — a heading — was overwritten with a company name.
    """
    import re

    before = _all_lines(_template(code).template_path)
    after = _all_lines(_run(code, tmp_path).docx_path)
    # «Вид документа … серия … номер …» is a field too, however much of the
    # form's own wording shares the line with it
    a_field = re.compile(r"\d{2}\.\d{2}\.\d{4}|допущенн|Вид\s+документа|"
                         + insurance_docx._LABELS.pattern)

    for old, new in zip(before, after):
        # a line that carries one of the form's own field labels is a field —
        # everything else is the insurer's prose and must come out untouched
        if not _is_prose(old) or a_field.search(old):
            continue
        assert old == new, (code, old[:90], new[:90])


@pytest.mark.parametrize("code", CODES)
def test_the_insurers_signature_is_left_where_it_is(code, tmp_path) -> None:
    """Not the program's to delete — the operator is told about it instead."""
    result = _run(code, tmp_path)
    before, after = (_all_lines(_template(code).template_path),
                     _all_lines(result.docx_path))
    for line in before:
        if "подписан" in line.lower() or "сертификат" in line.lower():
            assert line in after, (code, line[:60])


def test_a_vin_grid_is_written_one_character_per_box(tmp_path) -> None:
    result = _run("soglasie", tmp_path)
    document = docx.Document(str(result.docx_path))
    for table in insurance_docx._all_tables(document):
        for row in table.rows:
            seen: list[str] = []
            for cell in row.cells:
                value = " ".join(cell.text.split())
                if not seen or value != seen[-1]:
                    seen.append(value)
            boxes = [v for v in seen if len(v) <= 1]
            if len(boxes) >= 10:
                assert "".join(boxes) == STS.vin
                return
    pytest.fail("the VIN grid was not found")


# ------------------- the four the office reported off its own policies


@pytest.mark.parametrize("code", CODES)
def test_the_owner_of_the_car_is_written(code, tmp_path) -> None:
    """«Собственник транспортного средства» was coming out blank.

    Every one of these forms prints the label with its own explanation of what
    to write — «(полное наименование юридического лица или фамилия, имя,
    отчество физического лица)» — and the name on the line under it. Read as
    "the label has no value beside it, so there is no such field", the
    собственник kept the previous customer's name or none at all.
    """
    body = _read(_run(code, tmp_path).docx_path)
    if "Собственник транспортного средства" not in body:
        pytest.skip(f"{code} does not print a собственник")
    assert STS.owner_fio in body, code


@pytest.mark.parametrize("code", CODES)
def test_a_value_is_never_appended_to_its_own_label(code, tmp_path) -> None:
    """The value goes on its own line, not onto the end of the heading.

    Writing «Марка, модель транспортного средства HYUNDAI SOLARIS» into one
    paragraph put the car inside the insurer's heading — and in the heading's
    colour, which is why the office saw the make come out blue.
    """
    document = docx.Document(str(_run(code, tmp_path).docx_path))
    for paragraph in insurance_docx._all_paragraphs(document):
        text = " ".join((paragraph.text or "").split())
        head = insurance_docx._LABELS.match(text)
        if head is None:
            continue
        for value in (STS.vehicle.upper(), STS.vin, STS.plate):
            assert value not in text[head.end():], (code, text[:90])


@pytest.mark.parametrize("code", CODES)
def test_the_registration_document_is_written(code, tmp_path) -> None:
    """«Вид документа … серия … номер …» — the СТС was not written at all.

    Most of these forms head the row with the whole of the Bank of Russia's
    wording, «Паспорт транспортного средства, свидетельство о регистрации
    транспортного средства, паспорт(свидетельство) на шасси…», so looking for
    «Свидетельство о регистрации» as a label of its own found nothing.
    """
    body = _read(_run(code, tmp_path).docx_path)
    assert STS.series in body and STS.number in body, code
    # «Вид документа Серия Номер» with no digits on it is the column heading,
    # which one insurer prints above the document rather than beside it
    filled = [ln for ln in body.split("\n")
              if "Вид документа" in ln and any(c.isdigit() for c in ln)]
    for line in filled:
        assert STS.number in line, (code, line[:90])
        assert "аспорт ТС" not in line, (code, line[:90])   # it is a СТС now


def test_a_footnote_row_under_the_driver_table_is_not_dashed(tmp_path) -> None:
    """«-» under the table is the form's own note, not an empty driver slot."""
    before = _all_lines(_template("ingosstrah").template_path)
    after = _all_lines(_run("ingosstrah", tmp_path).docx_path)
    for old, new in zip(before, after):
        if old.startswith("- |") and "*" not in old:
            assert old == new, (old, new)
