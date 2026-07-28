"""A form nobody taught the program about: work it out, confirm it, fill it.

The operator uploads their own PDF or Word file. The program finds where each
value goes, shows that map so a wrong guess can be corrected or removed, keeps
what was confirmed against the file's contents, and fills it — checking the
result the same way every other document is checked.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import fitz
import pytest

docx = pytest.importorskip("docx")

from src.common.errors import ValidationError  # noqa: E402
from src.domain.documents import Passport, Patent  # noqa: E402
from src.domain.enums import Gender  # noqa: E402
from src.pdf import rewrite  # noqa: E402
from src.pdf.engine import _font_file  # noqa: E402
from src.services import template_fill, template_study  # noqa: E402

PASSPORT = Passport(surname="НАЗАРОВ", name="МУРОДУЛЛО", patronymic="ХАИТАЛИЕВИЧ",
                    number="1234567", series="FB", birth_date=date(2004, 2, 22),
                    issue_date=date(2023, 2, 16), issued_by="МВД РУЗ",
                    nationality="УЗБЕКИСТАН", gender=Gender.MALE,
                    birth_place="УЗБЕКИСТАН")
PATENT = Patent(series="77", number="2600017664", issue_date=date(2026, 4, 14),
                profession="Штукатур")
FORM_LINES = [
    (100, "Фамилия ______________________"),
    (130, "Имя ______________________"),
    (160, "Отчество ______________________"),
    (190, "Дата рождения ____________"),
    (220, "Гражданство ______________________"),
    (250, "Серия ________ Номер ______________"),
    (280, "Кем выдан _________________________________"),
    (310, "Профессия: ____________________"),
]


def _flat_pdf(path: Path, lines=None) -> Path:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_font(fontname="F", fontfile=str(_font_file("OfisSansRegular")))
    for y, text in (lines or FORM_LINES):
        page.insert_text((60, y), text, fontname="F", fontsize=11)
    doc.save(str(path))
    doc.close()
    return path


def _acroform(path: Path) -> Path:
    doc = fitz.open()
    page = doc.new_page()
    for name, y in (("Фамилия", 100), ("Имя", 130), ("Дата рождения", 160),
                    ("Гражданство", 190), ("что-то ещё", 220)):
        widget = fitz.Widget()
        widget.field_name = name
        widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        widget.rect = fitz.Rect(220, y, 460, y + 18)
        page.add_widget(widget)
    doc.save(str(path))
    doc.close()
    return path


def _word(path: Path) -> Path:
    document = docx.Document()
    document.add_paragraph("Фамилия:")
    document.add_paragraph("Дата рождения:")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Гражданство"
    table.cell(1, 0).text = "Профессия"
    document.save(str(path))
    return path


def _values() -> dict[str, str]:
    return template_fill.values_for(PASSPORT, PATENT, form_date=date(2026, 7, 28),
                                    profession="Штукатур")


# ----------------------------------------------------------------- reading


def test_a_pdf_with_real_form_fields_needs_no_guessing(tmp_path) -> None:
    study = template_study.study(_acroform(tmp_path / "f.pdf"))
    assert study.kind == template_study.PDF_FORM
    keys = {spot.key for spot in study.spots}
    assert keys == {"surname", "name", "birth_date", "citizenship"}
    assert all(spot.widget for spot in study.spots)


def test_a_flat_pdf_is_read_off_its_own_words(tmp_path) -> None:
    study = template_study.study(_flat_pdf(tmp_path / "f.pdf"))
    assert study.kind == template_study.PDF_FLAT
    assert {s.key for s in study.spots} >= {
        "surname", "name", "patronymic", "birth_date", "citizenship",
        "passport_series", "passport_number", "passport_issued_by", "profession"}


def test_the_writing_spot_is_the_gap_not_the_next_label(tmp_path) -> None:
    """«Серия ____ Номер ____» — each value belongs in its own gap."""
    study = template_study.study(_flat_pdf(tmp_path / "f.pdf"))
    series = next(s for s in study.spots if s.key == "passport_series")
    number = next(s for s in study.spots if s.key == "passport_number")
    assert series.rect[2] <= number.rect[0], "the two gaps must not overlap"
    assert series.rect[2] - series.rect[0] < 60, "«Номер» was swallowed"


def test_a_label_with_no_room_beside_it_is_not_offered(tmp_path) -> None:
    pdf = _flat_pdf(tmp_path / "f.pdf", [(100, "Фамилия Имя Отчество Гражданство")])
    study = template_study.study(pdf)
    assert not any(s.key == "citizenship" for s in study.spots)


def test_word_paragraphs_and_table_cells_are_both_found(tmp_path) -> None:
    study = template_study.study(_word(tmp_path / "f.docx"))
    assert study.kind == template_study.DOCX
    by_key = {s.key: s for s in study.spots}
    assert by_key["surname"].paragraph >= 0
    assert by_key["citizenship"].cell == (0, 0, 1), "the value's own cell"
    assert by_key["profession"].cell == (0, 1, 1)


@pytest.mark.parametrize("text, key", [
    ("Фамилия", "surname"), ("Ф.И.О.", "fio"), ("дата рождения", "birth_date"),
    ("Кем выдан", "passport_issued_by"), ("Профессия, должность:", "profession"),
    ("surname", "surname"), ("Гражданство:", "citizenship"),
    ("совершенно посторонний текст", None),
])
def test_a_label_is_recognised_however_the_form_words_it(text, key) -> None:
    assert template_study.match_label(text) == key


def test_a_file_that_is_neither_is_refused(tmp_path) -> None:
    junk = tmp_path / "x.txt"
    junk.write_text("hello")
    with pytest.raises(ValidationError):
        template_study.study(junk)


def test_a_form_nothing_was_found_in_says_so(tmp_path) -> None:
    study = template_study.study(_flat_pdf(tmp_path / "f.pdf",
                                           [(100, "Просто текст без полей")]))
    assert not study.ok
    assert study.notes


# ----------------------------------------------------------------- filling


def test_a_flat_pdf_is_filled_and_the_result_is_checked(tmp_path) -> None:
    template = _flat_pdf(tmp_path / "f.pdf")
    study = template_study.study(template)
    result = template_fill.fill(study, template, tmp_path / "out.pdf", _values())

    assert result.ok, result.problems
    text = rewrite.read_text(result.path)
    for value in ("НАЗАРОВ", "МУРОДУЛЛО", "ХАИТАЛИЕВИЧ", "22.02.2004",
                  "УЗБЕКИСТАН", "FB", "1234567", "МВД РУЗ", "Штукатур"):
        assert value in text, value


def test_the_forms_own_words_survive_the_fill(tmp_path) -> None:
    """Only the gap is written on — the printed labels stay put."""
    template = _flat_pdf(tmp_path / "f.pdf")
    study = template_study.study(template)
    result = template_fill.fill(study, template, tmp_path / "out.pdf", _values())
    text = rewrite.read_text(result.path)
    for label in ("Фамилия", "Имя", "Отчество", "Дата рождения", "Гражданство",
                  "Серия", "Номер", "Кем выдан", "Профессия"):
        assert label in text, label


def test_the_underscores_are_gone_where_a_value_went(tmp_path) -> None:
    template = _flat_pdf(tmp_path / "f.pdf")
    study = template_study.study(template)
    result = template_fill.fill(study, template, tmp_path / "out.pdf", _values())
    assert "______" not in rewrite.read_text(result.path)


def test_an_acroform_is_filled_and_flattened(tmp_path) -> None:
    template = _acroform(tmp_path / "f.pdf")
    study = template_study.study(template)
    result = template_fill.fill(study, template, tmp_path / "out.pdf", _values())

    assert result.ok, result.problems
    text = rewrite.read_text(result.path)
    assert "НАЗАРОВ" in text and "22.02.2004" in text


def test_a_word_template_keeps_its_labels_and_gains_the_values(tmp_path) -> None:
    template = _word(tmp_path / "f.docx")
    study = template_study.study(template)
    result = template_fill.fill(study, template, tmp_path / "out.docx", _values())

    assert result.ok, result.problems
    document = docx.Document(str(result.path))
    paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
    assert "Фамилия: НАЗАРОВ" in paragraphs
    assert "Дата рождения: 22.02.2004" in paragraphs
    rows = [[c.text for c in row.cells] for row in document.tables[0].rows]
    assert rows == [["Гражданство", "УЗБЕКИСТАН"], ["Профессия", "Штукатур"]]


def test_filling_without_a_map_is_refused(tmp_path) -> None:
    empty = template_study.Study(kind=template_study.PDF_FLAT, source="x")
    with pytest.raises(ValidationError):
        template_fill.fill(empty, _flat_pdf(tmp_path / "f.pdf"),
                           tmp_path / "o.pdf", _values())


def test_a_value_that_did_not_land_is_named(tmp_path) -> None:
    """The map points off the page; the check has to notice."""
    template = _flat_pdf(tmp_path / "f.pdf")
    study = template_study.study(template)
    study.spots = [template_study.Spot(key="surname", label="Фамилия", page=1,
                                       rect=(3000, 3000, 3100, 3020))]
    result = template_fill.fill(study, template, tmp_path / "o.pdf", _values())
    assert not result.ok
    assert any("Фамилия" in problem for problem in result.problems)


# -------------------------------------------------------------- remembering


def _controller(tmp_path):
    from src.controllers.template_controller import TemplateController
    from src.database.connection import Database
    from src.database.repositories.template_profile_repo import (
        TemplateProfileRepository,
    )

    db = Database(tmp_path / "o.db")
    db.migrate()
    return TemplateController(TemplateProfileRepository(db), ocr=None)


def test_a_confirmed_map_is_not_asked_for_twice(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    from src.config import paths

    paths.data_dir.cache_clear()
    controller = _controller(tmp_path)
    template = _flat_pdf(tmp_path / "f.pdf")

    study, remembered = controller.study(template)
    assert not remembered
    study.spots = [s for s in study.spots if s.key != "profession"]
    kept = controller.remember("Менинг анкетам", template, study)

    again, remembered = controller.study(kept)
    assert remembered, "the same file must not be studied a second time"
    assert not any(s.key == "profession" for s in again.spots), \
        "what the operator removed stays removed"
    paths.data_dir.cache_clear()


def test_a_template_is_recognised_by_its_contents_not_its_name(tmp_path,
                                                               monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    from src.config import paths

    paths.data_dir.cache_clear()
    controller = _controller(tmp_path)
    first = _flat_pdf(tmp_path / "a.pdf")
    study, _ = controller.study(first)
    controller.remember("A", first, study)

    same_bytes = tmp_path / "renamed.pdf"
    same_bytes.write_bytes(first.read_bytes())
    _again, remembered = controller.study(same_bytes)
    assert remembered
    paths.data_dir.cache_clear()


def test_a_map_can_be_forgotten_and_studied_afresh(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    from src.config import paths

    paths.data_dir.cache_clear()
    controller = _controller(tmp_path)
    template = _flat_pdf(tmp_path / "f.pdf")
    study, _ = controller.study(template)
    kept = controller.remember("A", template, study)

    controller.forget(kept)
    _again, remembered = controller.study(kept)
    assert not remembered
    paths.data_dir.cache_clear()


def test_the_map_survives_a_round_trip_through_json() -> None:
    study = template_study.Study(
        kind=template_study.DOCX, source="x",
        spots=[template_study.Spot(key="surname", label="Фамилия",
                                   cell=(0, 1, 2), confirmed=True)])
    back = template_study.Study.from_json(study.to_json())
    assert back.spots[0].cell == (0, 1, 2)
    assert back.spots[0].confirmed
