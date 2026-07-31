"""Arranging a blank's printed values — the store, and ЧЕК using it.

The office drags each value into place against its own blank instead of editing
numbers in a file and rebuilding the program. What it arranges is kept per
section and per blank; nothing else moves.
"""

from __future__ import annotations

import datetime
import tempfile

import fitz
import pytest
from src.config import paths


@pytest.fixture(autouse=True)
def isolated_data_dir(monkeypatch):
    sandbox = tempfile.mkdtemp()
    monkeypatch.setenv("XDG_DATA_HOME", sandbox)
    monkeypatch.setenv("LOCALAPPDATA", sandbox)
    paths.data_dir.cache_clear()
    yield
    paths.data_dir.cache_clear()


# ------------------------------------------------------------- the store


def test_a_layout_is_kept_per_section_and_per_blank(tmp_path) -> None:
    from src.services import blank_layout

    one, two = tmp_path / "СФЕРА.pdf", tmp_path / "ЭКСПЕРТ.pdf"
    assert blank_layout.load("chek", one) == {}
    assert blank_layout.load("chek", None) == {}

    blank_layout.save("chek", one, {"fields": {"fam": [0.3, 0.5, 0.01]}})
    assert blank_layout.load("chek", one)["fields"]["fam"] == [0.3, 0.5, 0.01]
    # the other blank is untouched, and so is the same blank in another section
    assert blank_layout.load("chek", two) == {}
    assert blank_layout.load("registration", one) == {}

    blank_layout.reset("chek", one)
    assert blank_layout.load("chek", one) == {}


def test_it_is_kept_in_appdata_not_beside_the_blank(tmp_path) -> None:
    """ЧЕК keeps its blanks inside the program folder, and anything written
    there is lost the next time the EXE is rebuilt."""
    from src.services import blank_layout

    template = tmp_path / "СФЕРА.pdf"
    blank_layout.save("chek", template, {"fields": {}})
    assert not (tmp_path / "СФЕРА.json").exists()
    assert blank_layout.layout_file("chek", template).is_relative_to(
        paths.user_templates_dir())


def test_a_damaged_layout_file_is_ignored_not_fatal(tmp_path) -> None:
    from src.services import blank_layout

    template = tmp_path / "СФЕРА.pdf"
    blank_layout.save("chek", template, {"fields": {"fam": [0.3, 0.5, 0.01]}})
    blank_layout.layout_file("chek", template).write_text("{ бузуқ",
                                                          encoding="utf-8")
    assert blank_layout.load("chek", template) == {}


# ---------------------------------------------------------------- ЧЕК


def _chek(**over):
    from src.pdf.chek_renderer import ChekData

    base = dict(fam="ИСАКОВ", ism="ШАХБОЗ", otch="БАХТИЁРОВИЧ",
                inn="123456789012", card4="1234",
                when=datetime.datetime(2026, 7, 20, 10, 11, 12),
                rub=15000, kop=50, avtoriz="123456", idci="123456789012ABCD")
    base.update(over)
    return ChekData(**base)


def _origin(pdf: bytes, needle: str):
    page = fitz.open("pdf", pdf)[0]
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                if span["text"].strip() == needle:
                    return (span["origin"][0] / page.rect.width,
                            span["origin"][1] / page.rect.height,
                            span["size"] / page.rect.height)
    raise AssertionError(f"{needle!r} чекда йўқ")


def test_a_chek_with_nothing_arranged_prints_where_it_always_did() -> None:
    from src.pdf.chek_renderer import render_chek
    from src.pdf.chek_spec import FIELDS

    pdf, _name = render_chek(_chek())
    x, baseline, _size = _origin(pdf, "ИСАКОВ")
    page = fitz.open("pdf", pdf)[0]
    rect = FIELDS["fam"]["rect"]
    assert abs(x * page.rect.width - rect[0]) < 0.5
    assert abs(baseline * page.rect.height - (rect[3] - 2.2)) < 0.5


def test_what_the_office_arranged_is_what_gets_printed() -> None:
    from src.pdf.chek_renderer import render_chek

    pdf, _name = render_chek(_chek(),
                             layout={"fields": {"fam": [0.30, 0.50, 0.010]}})
    x, baseline, size = _origin(pdf, "ИСАКОВ")
    assert abs(x - 0.30) < 0.002
    assert abs(baseline - 0.50) < 0.002
    assert abs(size - 0.010) < 0.0005
    # and only that one moved
    from src.pdf.chek_spec import FIELDS

    page = fitz.open("pdf", pdf)[0]
    ism_x, _b, _s = _origin(pdf, "ШАХБОЗ")
    assert abs(ism_x * page.rect.width - FIELDS["ism"]["rect"][0]) < 0.5


def test_the_chek_screen_offers_every_field_to_arrange() -> None:
    """A field the office cannot reach on the screen can never be corrected."""
    from src.pdf.chek_spec import FIELDS, SAMPLES

    assert {key for key, _label, _sample in SAMPLES} == set(FIELDS)
    assert all(label and sample for _key, label, sample in SAMPLES)


# ------------------------------------ every section builds the same editor


def test_the_mig_card_hands_the_editor_every_value_it_prints() -> None:
    """МИГ and ЧЕК share one editor; МИГ only says WHAT is on its card."""
    from src.pdf.mig_renderer import effective
    from src.ui.widgets.mig_layout_editor import build

    fields, sex, jobs = effective(None)
    items, rules = build(fields, sex, jobs)

    keys = {i.key for i in items}
    assert keys == set(fields) | {"sex:male", "sex:female"}
    assert {r.key for r in rules} == set(jobs)
    assert all(i.sample and i.label for i in items)
    # the issue date is the one printed in blue, and stays blue on screen
    issued = next(i for i in items if i.key == "issued")
    assert issued.colour[2] > issued.colour[0]


def test_what_the_editor_returns_is_what_the_renderer_reads() -> None:
    """The shape saved by the screen must be the shape ``effective`` expects —
    otherwise an afternoon of arranging silently does nothing."""
    from src.pdf.mig_renderer import effective

    saved = {"fields": {"surname": [0.40, 0.30, 0.030]},
             "sex": {"female": [0.90, 0.42, 0.034]},
             "jobs": {"uchenik": [0.10, 0.25, 0.70]}}
    fields, sex, jobs = effective(saved)
    assert (fields["surname"].x, fields["surname"].baseline) == (0.40, 0.30)
    assert sex["female"].x == 0.90
    assert (jobs["uchenik"].x0, jobs["uchenik"].y) == (0.10, 0.70)


# ------------------------------------------ Регистрация / ХОСТЕЛ mappings


def test_a_mapping_takes_what_the_office_arranged_on_one_blank() -> None:
    """The МВД form's mapping is shared by every address; arranging one
    address's own scan must move that one only."""
    from src.pdf.mapping import FieldMapping, anchor_x, with_layout
    from src.services.registration_service import MAPPING_PATH

    mapping = FieldMapping.load(MAPPING_PATH)
    width, height = mapping.page_size
    before = {f.id: (anchor_x(f), f.y, f.size) for f in mapping.fields}

    moved = with_layout(mapping, {"fields": {"reg.surname": [0.30, 0.20, 0.014]}})
    changed = next(f for f in moved.fields if f.id == "reg.surname")
    assert abs(anchor_x(changed) - 0.30 * width) < 0.1
    assert abs(changed.y - 0.20 * height) < 0.1
    assert abs(changed.size - 0.014 * height) < 0.01
    # every other field is exactly as it was, and the original is untouched
    for field in moved.fields:
        if field.id != "reg.surname":
            assert (anchor_x(field), field.y, field.size) == before[field.id]
    assert anchor_x(next(f for f in mapping.fields
                         if f.id == "reg.surname")) == before["reg.surname"][0]


def test_a_grid_field_moves_by_its_own_anchor() -> None:
    """A grid prints one character to a box and is anchored on ``x0``; a text
    field on ``x``. Moving the wrong one would leave the value where it was."""
    from src.pdf.mapping import FieldMapping, with_layout
    from src.services.registration_service import MAPPING_PATH

    mapping = FieldMapping.load(MAPPING_PATH)
    grid = next(f for f in mapping.fields if f.type == "grid")
    moved = with_layout(mapping, {"fields": {grid.id: [0.25, 0.30, 0.013]}})
    changed = next(f for f in moved.fields if f.id == grid.id)
    assert abs(changed.x0 - 0.25 * mapping.page_size[0]) < 0.1
    assert changed.x == grid.x, "the text anchor must not be invented"


def test_nothing_arranged_leaves_the_mapping_alone() -> None:
    from src.pdf.mapping import FieldMapping, with_layout
    from src.services.registration_service import MAPPING_PATH

    mapping = FieldMapping.load(MAPPING_PATH)
    assert with_layout(mapping, None) is mapping
    assert with_layout(mapping, {}) is mapping
    assert with_layout(mapping, {"fields": {}}) is mapping


def test_the_arranging_screen_names_and_sizes_every_field() -> None:
    from src.pdf.mapping import FieldMapping
    from src.services.registration_service import MAPPING_PATH
    from src.ui.widgets.arrange_mapping import label_of, sample_of

    for field in FieldMapping.load(MAPPING_PATH).fields:
        assert label_of(field), field.id
        sample = sample_of(field)
        assert sample, field.id
        if field.type == "grid":
            assert len(sample) == int(field.max_cells or 6)


# ------------------------------------------- the phone prints the same sheet


def _controller():
    """A ЧЕК controller on an isolated settings table."""
    from src.app import build_container
    from src.config.settings_service import SettingsService
    from src.controllers.chek_controller import ChekController
    from src.ocr.service import OcrService

    container = build_container()
    controller = ChekController(container.resolve(OcrService),
                                container.resolve(SettingsService))
    controller.set_company_id("123456789012ABCD")
    return controller


_RECEIPT = dict(fam="ИСАКОВ", ism="ШАХБОЗ", otch="БАХТИЁРОВИЧ",
                inn="123456789012", card4="1234", rub=15000, kop=50,
                avtoriz="123456",
                when=datetime.datetime(2026, 7, 20, 10, 11, 12))


def _surname_spots(pdf: bytes) -> list[tuple[float, float, float]]:
    """Where the surname landed, and how tall it came out."""
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        return [(round(r.x0, 1), round(r.y0, 1), round(r.height, 1))
                for r in doc[0].search_for("ИСАКОВ")]


def test_the_phone_prints_on_the_blank_the_office_arranged() -> None:
    """The bot names no blank — it must still get the arranged one.

    Naming none used to mean ``layout(None)`` → ``{}``: the receipt came back
    in the untouched, measured positions while the desktop printed the arranged
    ones. On the phone that reads as «the program is right, the bot gives me
    the old one».
    """
    controller = _controller()
    template = controller.templates()[0]

    plain = _surname_spots(controller.generate(**_RECEIPT)[0])

    from src.pdf.chek_spec import FIELDS

    with fitz.open(str(template)) as doc:
        width, height = doc[0].rect.width, doc[0].rect.height
    x0, _, _, y1 = FIELDS["fam"]["rect"]
    controller.save_layout(template, {"fields": {
        "fam": [(x0 + 60) / width, y1 / height,
                (FIELDS["fam"]["size"] * 1.6) / height]}})

    from_phone = _surname_spots(controller.generate(**_RECEIPT)[0])
    from_desk = _surname_spots(
        controller.generate(**_RECEIPT, template=template)[0])

    assert from_phone == from_desk, "the phone still prints the old positions"
    assert from_phone != plain, "the arrangement was not applied at all"


def test_the_blank_the_desktop_used_is_the_one_the_phone_follows() -> None:
    """There is no picker on the phone, so the desktop's choice is the answer."""
    controller = _controller()
    template = controller.templates()[0]

    assert controller.default_template() == template     # the only one there is

    controller.set_default_template(template)
    assert controller.default_template() == template

    # a blank that has been deleted since must not take the receipt down
    controller.set_default_template(template.parent / "yo'q-bo'lgan.pdf")
    assert controller.default_template() == template
