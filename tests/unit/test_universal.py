"""УНИВЕРСАЛ — one section for every form the office will ever upload.

The office asked for this to stop a new section being written for each new
paper: upload the empty form, drag the texts on, name it, keep it. What is
checked here is what it was explicit about — that a form is nothing but a
blank plus placed texts, that a saved blank is never lost until the office
deletes it, that a date can be printed nine different ways, that six free
серия/номер pairs are there, that boxes it invents itself work, and that a
text can be turned to run up the edge of a page.
"""

from __future__ import annotations

import io
import tempfile
from datetime import date
from pathlib import Path

import fitz
import pytest
from src.common.errors import ValidationError
from src.config import paths
from src.pdf import universal_fields as fields
from src.pdf.universal_fields import (
    DOC_SLOTS,
    STAMP,
    Field,
    UniversalData,
    values,
)
from src.pdf.universal_renderer import render
from src.services import universal_service as store


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    sandbox = tempfile.mkdtemp()
    monkeypatch.setenv("XDG_DATA_HOME", sandbox)
    monkeypatch.setenv("LOCALAPPDATA", sandbox)
    paths.data_dir.cache_clear()
    yield
    paths.data_dir.cache_clear()


@pytest.fixture()
def blank(tmp_path) -> Path:
    made = tmp_path / "forma.pdf"
    doc = fitz.open()
    for _ in range(2):
        doc.new_page(width=595, height=842)
    doc.save(str(made))
    doc.close()
    return made


def _worker(**over) -> UniversalData:
    made = UniversalData(
        surname="Исоев", name="Аслидин", patronymic="Холбердиевич",
        gender="Мужской", citizenship="Таджикистан",
        birth_place="Таджикистан", birth_date=date(1999, 7, 25),
        documents={1: ("P", "405847273"), 2: ("77", "2400796702")},
        pass_series="P", pass_number="405847273",
        pass_pin="50707994120019", pass_issued_by="ХШБ дар Ч.Балхи",
        pass_issued=date(2025, 1, 18), pass_expires=date(2035, 1, 17),
        pat_series="77", pat_number="2400796702",
        pat_blank_series="77", pat_blank_number="24012345678",
        pat_issued_by="ГУ МВД России по г. Москве", pat_region="г. Москва",
        pat_issued=date(2025, 3, 4), pat_expires=date(2026, 3, 3),
        issued=date(2025, 1, 18), expires=date(2035, 1, 17),
        issued_by="ХШБ дар Ч.Балхи", region="77",
        address="г Москва, ул Тагильская, д 45",
        position="Подсобный рабочий")
    for key, value in over.items():
        setattr(made, key, value)
    return made


def _stamp() -> bytes:
    from PIL import Image, ImageDraw

    picture = Image.new("RGBA", (300, 200), (0, 0, 0, 0))
    draw = ImageDraw.Draw(picture)
    draw.ellipse((5, 5, 295, 195), outline=(20, 40, 160, 255), width=8)
    buf = io.BytesIO()
    picture.save(buf, "PNG")
    return buf.getvalue()


def _printed(pdf: bytes, page: int = 0) -> str:
    """What the page says, with the reader's own quirks evened out.

    The hyphen is DRAWN correctly — the pixels are there — but PyMuPDF maps
    the glyph back through this font's cmap and hands it over as a soft
    hyphen. Same story for the non-breaking space. Neither is a printing
    fault, so neither is allowed to fail a test about what was printed.
    """
    with fitz.open("pdf", pdf) as doc:
        said = doc[page].get_text().replace("\xad", "-").replace("\xa0", " ")
    return " ".join(said.split())


# --------------------------------------------------------------- the dates
def test_a_date_is_offered_every_way_a_russian_form_asks_for_it() -> None:
    """«кун рақам, ой пропис, йил рақам — яъни 11 авг 2026»."""
    said = values(_worker())
    assert said["birth"] == "25.07.1999"
    assert said["birth_day"] == "25"
    assert said["birth_month"] == "07"
    assert said["birth_month_ru"] == "июля"
    assert said["birth_month_short"] == "июл"
    assert said["birth_year"] == "1999"
    assert said["birth_year_short"] == "99"
    assert said["birth_words"] == "25 июля 1999"
    assert said["birth_short"] == "25 июл 1999"


def test_a_date_nobody_filled_in_prints_nothing_anywhere() -> None:
    said = values(_worker(birth_date=None))
    assert said["birth"] == "" and said["birth_words"] == ""
    assert said["birth_month_ru"] == "" and said["birth_year"] == ""


def test_todays_date_is_always_there_without_being_typed() -> None:
    assert values(_worker())["today"] == date.today().strftime("%d.%m.%Y")


# ----------------------------------------------------------- the documents
def test_there_are_six_series_and_number_pairs() -> None:
    """The office counted them out: «серия номер 1 … серия номер 6»."""
    assert DOC_SLOTS == 6
    said = values(_worker())
    for slot in range(1, 7):
        assert f"doc{slot}_series" in said
        assert f"doc{slot}_number" in said
        assert f"doc{slot}_full" in said


def test_a_series_and_number_come_together_and_apart() -> None:
    said = values(_worker())
    assert said["doc1_series"] == "P"
    assert said["doc1_number"] == "405847273"
    assert said["doc1_full"] == "P 405847273"


def test_an_empty_slot_prints_nothing() -> None:
    said = values(_worker())
    assert said["doc6_full"] == "" and said["doc4_series"] == ""


def test_a_slot_with_only_a_number_does_not_print_a_stray_space() -> None:
    said = values(_worker(documents={3: ("", "12345")}))
    assert said["doc3_full"] == "12345"


# ------------------------------------------- the passport, by its own name
def test_the_passport_has_its_own_named_boxes() -> None:
    """The office asked for these by name, not as a numbered slot: «паспорт
    серия номер бирга ва алоҳида, берилган сана, ПИН, кем выдан»."""
    said = values(_worker())
    assert said["pass_series"] == "P"
    assert said["pass_number"] == "405847273"
    assert said["pass_full"] == "P 405847273"
    assert said["pass_pin"] == "50707994120019"
    assert said["pass_issued_by"] == "ХШБ дар Ч.Балхи"
    assert said["pass_issued"] == "18.01.2025"
    assert said["pass_issued_words"] == "18 января 2025"
    assert said["pass_expires"] == "17.01.2035"


# --------------------------------------------- the patent, by its own name
def test_the_patent_has_its_own_named_boxes() -> None:
    """«патент серия номер бирга ва алохида, берилган число, кем выдан,
    регион, патент бланка номер серия бирга ва алохида»."""
    said = values(_worker())
    assert said["pat_series"] == "77"
    assert said["pat_number"] == "2400796702"
    assert said["pat_full"] == "77 2400796702"
    assert said["pat_blank_series"] == "77"
    assert said["pat_blank_number"] == "24012345678"
    assert said["pat_blank_full"] == "77 24012345678"
    assert said["pat_issued"] == "04.03.2025"
    assert said["pat_issued_short"] == "4 мар 2025"
    assert said["pat_expires"] == "03.03.2026"
    assert said["pat_issued_by"] == "ГУ МВД России по г. Москве"
    assert said["pat_region"] == "г. Москва"


def test_the_patent_region_is_worked_out_from_its_series() -> None:
    """Not read off the card — the series IS the region, and reading it
    twice is two chances to get it wrong."""
    moscow = store.data_of(None, _Patent())
    assert moscow.pat_region == "г. Москва"

    class _Region50(_Patent):
        series = "50"

    assert store.data_of(None, _Region50()).pat_region == "Московская область"


def test_a_named_box_left_empty_prints_nothing() -> None:
    bare = UniversalData(surname="Исоев")
    said = values(bare)
    assert said["pass_full"] == "" and said["pat_full"] == ""
    assert said["pat_region"] == "" and said["pass_pin"] == ""
    assert said["pat_issued"] == "" and said["pat_issued_words"] == ""


def test_the_passport_and_patent_also_fill_the_first_two_free_slots() -> None:
    """A form arranged the old way — «Бошқа ҳужжат 1» — still prints."""
    read = store.data_of(_Passport(), _Patent())
    said = values(read)
    assert said["doc1_full"] == said["pass_full"] == "P 405847273"
    assert said["doc2_full"] == said["pat_full"] == "77 2400796702"


def test_every_field_in_the_picker_has_something_to_show_while_dragging(
) -> None:
    missing = [k for k in fields.CATALOGUE if not fields.sample_of(k)]
    assert missing == [], f"намунаси йўқ: {missing}"


# --------------------------------------------------------- the whole name
def test_the_name_comes_whole_and_in_three_pieces() -> None:
    said = values(_worker())
    assert said["fio"] == "Исоев Аслидин Холбердиевич"
    assert said["fio_upper"] == "ИСОЕВ АСЛИДИН ХОЛБЕРДИЕВИЧ"
    assert (said["surname"], said["name"], said["patronymic"]) == (
        "Исоев", "Аслидин", "Холбердиевич")


def test_a_worker_with_no_patronymic_leaves_no_double_space() -> None:
    assert values(_worker(patronymic=""))["fio"] == "Исоев Аслидин"


# ------------------------------------------------------ the office's own
def test_the_office_can_invent_a_box_and_name_it() -> None:
    """«кегин чалик керак болса узим майдон кушиш имкони болсин»."""
    key = fields.custom_key("Договор №")
    assert key == "custom:Договор №"
    assert fields.is_custom(key)
    assert fields.custom_name(key) == "Договор №"
    assert "Договор №" in fields.label_of(key)
    said = values(_worker(custom={key: "ТД-118"}))
    assert said[key] == "ТД-118"


def test_an_invented_box_joins_the_picker_list() -> None:
    key = fields.custom_key("Договор №")
    assert key not in fields.CATALOGUE
    assert key in fields.catalogue_with([key])
    assert fields.samples_with([key])[key] == "Договор №"


def test_each_blank_keeps_its_own_boxes(blank) -> None:
    """«ҳар битта юклаган бланкамга ўзининг майдони сақлансин» — a field one
    form needs must never clutter another form's screen."""
    store.add("Договор", blank)
    store.add("Уведомление", blank)
    store.save_fields("Договор", [
        Field(key="fio", page=1),
        Field(key=fields.custom_key("Договор №"), page=1)])
    store.save_fields("Уведомление", [
        Field(key="fio", page=1),
        Field(key=fields.custom_key("Смена"), page=1),
        Field(key=fields.custom_key("Бригада"), page=1)])

    assert store.custom_keys("Договор") == ["custom:Договор №"]
    assert store.custom_keys("Уведомление") == ["custom:Смена",
                                                "custom:Бригада"]
    assert "custom:Смена" not in store.wants("Договор")


def test_a_box_the_office_named_reaches_the_paper(blank, tmp_path) -> None:
    """Naming it is only half — what is typed into it has to print."""
    key = fields.custom_key("Договор №")
    store.add("Договор", blank)
    store.save_fields("Договор", [
        Field(key=key, page=1, x=0.15, baseline=0.30, size=0.016, bold=True)])

    made = store.UniversalService().generate(
        "Договор", UniversalData(surname="Исоев", custom={key: "ТД-118"}))
    assert "ТД-118" in _printed(made.pdf.read_bytes(), 0)


def test_a_named_box_left_blank_prints_nothing(blank) -> None:
    key = fields.custom_key("Договор №")
    store.add("Договор", blank)
    store.save_fields("Договор", [Field(key=key, page=1, x=0.15,
                                        baseline=0.30)])
    made = store.UniversalService().generate(
        "Договор", UniversalData(surname="Исоев", custom={key: ""}))
    assert _printed(made.pdf.read_bytes(), 0) == ""


def test_renaming_a_blank_takes_its_boxes_with_it(blank) -> None:
    store.add("Старое", blank)
    store.save_fields("Старое", [Field(key=fields.custom_key("Смена"),
                                       page=1)])
    store.rename("Старое", "Новое")
    assert store.custom_keys("Новое") == ["custom:Смена"]
    assert store.custom_keys("Старое") == []


# ------------------------------------------------------------- the library
def test_a_blank_is_saved_under_the_name_the_office_gave_it(blank) -> None:
    assert store.names() == []
    store.add("Договор ТД", blank)
    assert store.names() == ["Договор ТД"]
    assert store.blank_of("Договор ТД") is not None


def test_the_same_name_twice_is_refused_rather_than_overwritten(blank) -> None:
    store.add("Договор ТД", blank)
    with pytest.raises(ValidationError, match="аллақачон"):
        store.add("Договор ТД", blank)


def test_a_blank_may_be_a_photograph_as_well_as_a_pdf(tmp_path) -> None:
    from PIL import Image

    picture = tmp_path / "forma.png"
    Image.new("RGB", (827, 1169), "white").save(picture)
    store.add("Сканер", picture)
    assert len(store.pages("Сканер")) == 1


def test_a_form_is_never_lost_until_the_office_deletes_it(blank) -> None:
    """«йуклаган бланкаларим узим учирмагунимча хечкачон учмасин»."""
    store.add("Договор ТД", blank)
    store.save_fields("Договор ТД", [Field(key="fio", page=1)])
    # everything that is not `remove` leaves it alone
    for look in (lambda: store.names(),
                 lambda: store.pages("Договор ТД"),
                 lambda: store.fields("Договор ТД"),
                 lambda: store.wants("Договор ТД"),
                 lambda: store.custom_keys("Договор ТД")):
        look()
    assert store.names() == ["Договор ТД"]
    assert len(store.fields("Договор ТД")) == 1

    store.remove("Договор ТД")
    assert store.names() == []


def test_renaming_keeps_the_texts_that_were_arranged(blank) -> None:
    store.add("Старое", blank)
    store.save_fields("Старое", [Field(key="fio", page=1, x=0.33)])
    store.rename("Старое", "Новое")
    assert store.names() == ["Новое"]
    assert store.fields("Новое")[0].x == pytest.approx(0.33)


def test_the_texts_survive_being_written_and_read_back(blank) -> None:
    store.add("Форма", blank)
    placed = [
        Field(key="fio", page=1, x=0.15, baseline=0.2, size=0.016, bold=True,
              colour=(0.1, 0.2, 0.3), font="Arial"),
        Field(key="region", page=2, x=0.85, baseline=0.5, rotate=90),
    ]
    store.save_fields("Форма", placed)
    back = store.fields("Форма")
    assert [f.key for f in back] == ["fio", "region"]
    assert back[0].bold is True and back[0].font == "Arial"
    assert back[0].colour == pytest.approx((0.1, 0.2, 0.3))
    assert back[1].page == 2
    assert back[1].rotate == 90, "тик матн ётиб қолди"


def test_a_form_says_which_boxes_the_screen_should_show(blank) -> None:
    store.add("Форма", blank)
    store.save_fields("Форма", [Field(key="fio_upper"), Field(key="doc3_full"),
                                Field(key=fields.custom_key("Смена"))])
    assert store.wants("Форма") == {"fio_upper", "doc3_full", "custom:Смена"}
    assert store.custom_keys("Форма") == ["custom:Смена"]


def test_a_ruined_fields_file_is_not_a_crash(blank) -> None:
    store.add("Форма", blank)
    (store.folder() / "Форма" / store.FIELDS_FILE).write_text("{ бузилган",
                                                              encoding="utf-8")
    assert store.fields("Форма") == []


# ------------------------------------------------------------ the printing
def test_the_worker_is_printed_onto_the_office_own_blank(blank) -> None:
    placed = [Field(key="fio", page=1, x=0.15, baseline=0.20, size=0.016),
              Field(key="birth_words", page=1, x=0.15, baseline=0.26),
              Field(key="position", page=2, x=0.15, baseline=0.20)]
    pdf = render(_worker(), blank, placed)
    with fitz.open("pdf", pdf) as doc:
        assert doc.page_count == 2
    assert "Исоев Аслидин Холбердиевич" in _printed(pdf, 0)
    assert "25 июля 1999" in _printed(pdf, 0)
    assert "Подсобный рабочий" in _printed(pdf, 1)
    assert "Подсобный" not in _printed(pdf, 0), "2-саҳифаники 1-га тушди"


def test_a_value_nobody_filled_in_leaves_the_blank_alone(blank) -> None:
    pdf = render(_worker(position=""), blank,
                 [Field(key="position", page=1, x=0.2, baseline=0.2)])
    assert _printed(pdf, 0) == ""


def test_a_text_placed_on_a_page_that_is_not_there_is_skipped(blank) -> None:
    """A blank re-uploaded with fewer pages must not bring the section down."""
    pdf = render(_worker(), blank,
                 [Field(key="fio", page=9, x=0.2, baseline=0.2)])
    with fitz.open("pdf", pdf) as doc:
        assert doc.page_count == 2


@pytest.mark.parametrize("turn", [90, 270])
def test_a_text_can_be_turned_to_run_up_the_edge(blank, turn) -> None:
    """«текстларни вертикал горизонтал килишхам болсин».

    Checked by comparing the SAME words flat and turned, not by assuming a
    shape: two digits set flat are already taller than they are wide, so an
    absolute test would pass on a bug.
    """
    words = "ХШБ дар Ч.Балхи"
    made = {t: render(_worker(issued_by=words), blank,
                      [Field(key="issued_by", page=1, x=0.5, baseline=0.5,
                             size=0.014, rotate=t)])
            for t in (0, turn)}
    boxes = {}
    for at, pdf in made.items():
        with fitz.open("pdf", pdf) as doc:
            found = doc[0].search_for("ХШБ")
            assert found, f"rotate={at} да матн чиқмади"
            boxes[at] = found[0]

    flat, turned = boxes[0], boxes[turn]
    assert flat.width > flat.height, "ётиқ матн эндан баланд чиқди"
    assert turned.height > turned.width, "тик қўйилгани ётиб турибди"
    # the turn swaps the two, it does not resize the words
    assert turned.height == pytest.approx(flat.width, abs=1.0)
    assert turned.width == pytest.approx(flat.height, abs=1.0)


def test_a_stamp_is_drawn_as_itself_and_keeps_its_shape(blank) -> None:
    pdf = render(_worker(stamp_png=_stamp()), blank,
                 [Field(key=STAMP, page=1, x=0.5, baseline=0.3, size=0.08)])
    with fitz.open("pdf", pdf) as doc:
        boxes = [doc[0].get_image_bbox(i)
                 for i in doc[0].get_images(full=True)]
    assert len(boxes) == 1, "печать тушмади"
    assert boxes[0].width / boxes[0].height == pytest.approx(1.5, abs=0.15)


def test_a_stamp_slot_with_no_stamp_prints_nothing(blank) -> None:
    pdf = render(_worker(), blank,
                 [Field(key=STAMP, page=1, x=0.5, baseline=0.3, size=0.08)])
    with fitz.open("pdf", pdf) as doc:
        assert not doc[0].get_images(full=True)


# ------------------------------------------------------------- the service
def test_generating_needs_a_blank_and_at_least_one_text(blank) -> None:
    service = store.UniversalService()
    with pytest.raises(ValidationError, match="топилмади"):
        service.generate("йўқ", _worker())
    store.add("Форма", blank)
    with pytest.raises(ValidationError, match="жойлаштирилмаган"):
        service.generate("Форма", _worker())


def test_the_form_keeps_its_own_stamp_so_it_is_uploaded_once(
        blank, tmp_path) -> None:
    store.add("Форма", blank)
    store.save_fields("Форма", [Field(key=STAMP, page=1, x=0.5, baseline=0.3,
                                      size=0.08)])
    kept = tmp_path / "pechat.png"
    kept.write_bytes(_stamp())
    store.set_picture("Форма", "stamp", kept)

    made = store.UniversalService().generate("Форма", _worker())
    with fitz.open(made.pdf) as doc:
        assert doc[0].get_images(full=True), "сақланган печать ишлатилмади"


def test_two_workers_do_not_overwrite_each_other(blank) -> None:
    store.add("Форма", blank)
    store.save_fields("Форма", [Field(key="fio", page=1, x=0.2, baseline=0.2)])
    service = store.UniversalService()
    first = service.generate("Форма", _worker())
    second = service.generate("Форма", _worker())
    assert first.pdf != second.pdf
    assert first.pdf.exists() and second.pdf.exists()


def test_the_file_is_named_after_the_worker(blank) -> None:
    store.add("Форма", blank)
    store.save_fields("Форма", [Field(key="fio", page=1, x=0.2, baseline=0.2)])
    made = store.UniversalService().generate("Форма", _worker())
    assert made.pdf.stem == "ИСОЕВ_АСЛИДИН"


def test_a_form_with_no_worker_yet_is_named_after_the_form(blank) -> None:
    store.add("Пустой", blank)
    store.save_fields("Пустой", [Field(key="note", page=1, x=0.2,
                                       baseline=0.2)])
    made = store.UniversalService().generate("Пустой",
                                             UniversalData(note="изоҳ"))
    assert "Пустой" in made.pdf.stem


# ------------------------------------------------------------- the reading
class _Passport:
    surname, name, patronymic = "ИСОЕВ", "АСЛИДИН", "ХОЛБЕРДИЕВИЧ"
    gender, nationality, birth_place = "M", "ТАДЖИКИСТАН", "ТАДЖИКИСТАН"
    birth_date = date(1999, 7, 25)
    series, number = "P", "405847273"


class _Patent:
    series, number = "77", "2400796702"
    issue_date, expire_date = date(2025, 1, 18), date(2026, 1, 17)
    profession = "Подсобный рабочий"


def test_what_the_passport_gives_lands_in_the_right_boxes() -> None:
    read = store.data_of(_Passport(), _Patent())
    assert read.fio() == "Исоев Аслидин Холбердиевич"
    assert read.birth_date == date(1999, 7, 25)
    assert read.documents[1] == ("P", "405847273")
    assert read.documents[2] == ("77", "2400796702")
    assert read.position == "Подсобный рабочий"
    assert read.expires == date(2026, 1, 17)


def test_either_document_on_its_own_is_enough() -> None:
    """«бази хужатларга ишчи расми керак, базисига керак эмас»."""
    assert store.data_of(_Passport(), None).fio() == "Исоев Аслидин Холбердиевич"
    assert store.data_of(None, _Patent()).position == "Подсобный рабочий"
    assert store.data_of(None, None).fio() == ""


# ---------------------------------------------------------------- the bot
def test_the_bot_offers_every_saved_form(blank) -> None:
    from src.controllers.ofis_modules import MODULES

    module = next(m for m in MODULES if m.key == "universal")
    store.add("Договор ТД", blank)
    store.add("Уведомление", blank)

    class _Controller:
        @staticmethod
        def names():
            return store.names()

        @staticmethod
        def fields(name):
            return store.fields(name)

    assert module.targets({"universal": _Controller()}) == ["Договор ТД",
                                                            "Уведомление"]
    # …and says why it cannot run while no form has any texts on it
    assert "матн" in module.ready({"universal": _Controller()})
    store.save_fields("Договор ТД", [Field(key="fio", page=1)])
    assert module.ready({"universal": _Controller()}) == ""
