"""МВД ТРУДАВОЙ — the ten-page packet, measured and locked.

The renderer is checked against the positions measured off the office's own
filled packet; the cells against the form's grid; the service against its
store; the bot against the questions it must ask.
"""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import fitz
import pytest
from src.config import paths
from src.pdf.mvd_trud_renderer import (
    MvdTrudData,
    output_name,
    placed,
    plus_one_year,
    render,
    split_rep_fio,
    values,
)
from src.pdf.mvd_trud_spec import PAGE_COUNT, SLOTS


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    sandbox = tempfile.mkdtemp()
    monkeypatch.setenv("XDG_DATA_HOME", sandbox)
    monkeypatch.setenv("LOCALAPPDATA", sandbox)
    paths.data_dir.cache_clear()
    yield
    paths.data_dir.cache_clear()


def _blank(folder: Path, pages: int = PAGE_COUNT) -> Path:
    blank = folder / "GLOBALPRO.pdf"
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page(width=595, height=840)
    doc.save(str(blank))
    doc.close()
    return blank


_WORKER = dict(
    surname="ОЙМАХМАДОВ", name="АМИРТЕМИР", patronymic="ХАЙДАРОВИЧ",
    citizenship="ТАДЖИКИСТАН", birth_date=date(1985, 12, 14),
    pass_number="402090755", pass_issued=date(2018, 5, 15),
    pass_issued_by="МВД", pat_series="77", pat_number="2600184371",
    pat_issued=date(2026, 4, 15),
    pat_issued_by="ОТДЕЛ ВНЕШНЕЙ ТРУДОВОЙ МИГРАЦИИ УВМ ГУ МВД РОССИИ ПО Г.МОСКВЕ",
    profession="ПОДСОБНЫЙ РАБОЧИЙ", deal_date=date(2026, 7, 28),
    pat_until=plus_one_year(date(2026, 4, 15)),
    uved_no="1259", spravka_no="160")


# ------------------------------------------------------------- the values


def test_every_slot_points_at_a_real_page() -> None:
    for key, slot in SLOTS.items():
        assert 1 <= slot.page <= PAGE_COUNT, f"{key} on page {slot.page}"


def test_every_value_has_a_slot_and_the_other_way_round() -> None:
    """A value without a slot is silently never printed; a slot without a
    value is dead weight that clutters the layout editor."""
    made = set(values(MvdTrudData(**_WORKER)))
    slotted = set(SLOTS)
    assert made == slotted, (
        f"missing slots: {made - slotted} · dead slots: {slotted - made}")


def test_the_year_after_the_printed_20_is_two_digits() -> None:
    assert values(MvdTrudData(**_WORKER))["p10_year"] == "26"


def test_the_rep_fio_breaks_at_a_word_over_the_designed_gap() -> None:
    line1, line2 = split_rep_fio("ТАДЖИКИСТАН",
                                 "ОЙМАХМАДОВ АМИРТЕМИР ХАЙДАРОВИЧ")
    assert line1 and line2
    assert not line1.endswith(" ") and not line2.startswith(" ")
    assert (line1 + " " + line2) == "ТАДЖИКИСТАН ОЙМАХМАДОВ АМИРТЕМИР ХАЙДАРОВИЧ"


def test_initials_read_like_the_signature_line() -> None:
    assert MvdTrudData(**_WORKER).initials() == "ОЙМАХМАДОВ А.Х."


def test_patent_runs_a_year_from_issue() -> None:
    assert plus_one_year(date(2026, 4, 15)) == date(2027, 4, 15)
    assert plus_one_year(date(2024, 2, 29)) == date(2025, 2, 28)


def test_the_filename_is_surname_name() -> None:
    assert output_name(MvdTrudData(**_WORKER)) == "ОЙМАХМАДОВ_АМИРТЕМИР.pdf"


# ------------------------------------------------------------- the render


def _ink(page: fitz.Page) -> list[tuple[str, float, float]]:
    out = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                text = span["text"].replace("\xa0", " ").strip()
                if text:
                    out.append((text, span["bbox"][0] / page.rect.width,
                                span["origin"][1] / page.rect.height))
    return out


def test_the_packet_renders_all_ten_pages(tmp_path) -> None:
    pdf = render(MvdTrudData(**_WORKER), _blank(tmp_path))
    with fitz.open("pdf", pdf) as doc:
        assert doc.page_count == PAGE_COUNT
        # page 1 — the справка values sit on their measured lines
        ink1 = {t: (x, y) for t, x, y in _ink(doc[0])}
        assert "ОЙМАХМАДОВ АМИРТЕМИР ХАЙДАРОВИЧ" in ink1
        assert "1259" in ink1
        x, y = ink1["1259"]
        assert abs(x - SLOTS["p1_uved_no"].x) < 0.004
        assert abs(y - SLOTS["p1_uved_no"].baseline) < 0.004
        # page 3 — cells: one glyph per box at the measured pitch
        cells = [(t, x) for t, x, y in _ink(doc[2])
                 if abs(y - SLOTS["p3_surname"].baseline) < 0.005]
        letters = sorted(cells, key=lambda c: c[1])
        assert "".join(t for t, _ in letters) == "ОЙМАХМАДОВ"
        steps = [round(letters[i + 1][1] - letters[i][1], 4)
                 for i in range(len(letters) - 1)]
        for step in steps:
            assert abs(step - SLOTS["p3_surname"].pitch) < 0.002, steps
        # page 9 — the issuer wraps to the margin row, nothing lost
        ink9 = "".join(t for t, _, _ in _ink(doc[8]))
        assert "МОСКВЕ" in ink9.replace(" ", "")
        # page 10 — the year is two digits after the pre-printed «20»
        ink10 = [t for t, _, _ in _ink(doc[9])]
        assert "26" in ink10 and "2026" not in ink10


def test_a_short_blank_is_refused_with_a_sentence(tmp_path) -> None:
    from src.common.errors import OfisError

    with pytest.raises(OfisError):
        render(MvdTrudData(**_WORKER), _blank(tmp_path, pages=3))


def test_what_the_office_dragged_wins(tmp_path) -> None:
    moved = MvdTrudData(**_WORKER, layout={
        "fields": {"p2_fio": [0.10, 0.60, 0.0135]}})
    pdf = render(moved, _blank(tmp_path))
    with fitz.open("pdf", pdf) as doc:
        found = [(x, y) for t, x, y in _ink(doc[1]) if "ОЙМАХМАДОВ" in t]
        assert found and abs(found[0][0] - 0.10) < 0.01


def test_a_moved_cell_slot_keeps_its_pitch_scaled() -> None:
    grown = placed({"fields": {"p3_surname": [0.25, 0.36, 0.025]}})["p3_surname"]
    base = SLOTS["p3_surname"]
    assert grown.pitch == pytest.approx(base.pitch * 0.025 / base.size)
    assert grown.per_row == base.per_row


# ------------------------------------------------------------- the service


def test_the_service_stores_blanks_and_prints(tmp_path) -> None:
    from src.app import build_container
    from src.config.settings_service import SettingsService
    from src.services.mvd_trud_service import MvdTrudService

    service = MvdTrudService(build_container().resolve(SettingsService))
    blank = service.add_template("ГЛОБАЛПРО", _blank(tmp_path))
    assert blank in service.templates()

    result = service.generate(MvdTrudData(**_WORKER), blank)
    assert result.saved.exists()
    assert result.saved.name.startswith("ОЙМАХМАДОВ_АМИРТЕМИР")
    with fitz.open(str(result.saved)) as doc:
        assert doc.page_count == PAGE_COUNT

    service.remove_template(blank)
    assert blank not in service.templates()


# ----------------------------------------------------------------- the bot


def test_the_bot_asks_the_date_and_the_dolzhnost() -> None:
    from src.controllers.ofis_modules import BY_KEY

    module = BY_KEY["mvd_trud"]
    assert module.photo_labels == ("Паспорт", "Патент олди", "Патент орқаси")
    fields = [a.field for a in module.asks]
    assert "deal_date" in fields and "profession" in fields


def test_the_packet_is_set_in_bold_times() -> None:
    """The owner asked for the values to stand off the form — жирний."""
    from src.pdf.mvd_trud_spec import FONT

    assert FONT == "OfisSerifBold"


def test_the_fio_comes_off_the_patent_not_the_passport(monkeypatch) -> None:
    """The patent prints the ФИО in Russian, ready for the packet; the
    passport keeps supplying its own numbers, dates and орган."""
    from src.controllers.mvd_trud_controller import MvdTrudController
    from src.domain.documents import Passport, Patent
    from src.ocr.service import OcrService
    from src.services.mvd_trud_service import MvdTrudService

    controller = MvdTrudController.__new__(MvdTrudController)
    controller._ocr = OcrService.__new__(OcrService)
    controller._service = MvdTrudService()

    monkeypatch.setattr(
        OcrService, "read_passport",
        lambda self, image: Passport(surname="АКДО", name="ДЖОСЕЛИН",
                                     patronymic="ДЖЕЛИН", number="P9314956C",
                                     issue_date=date(2025, 3, 27)))
    monkeypatch.setattr(
        OcrService, "read_patent",
        lambda self, front, back=None: Patent(
            series="77", number="2600184371", profession="ПОДСОБНЫЙ РАБОЧИЙ",
            holder_surname="АНДО", holder_name="ДЖОСЕЛИН"))

    passport, patent = controller.read_documents(b"pass", b"front", None)
    assert passport.surname == "АНДО", "the patent's Russian ФИО must win"
    assert passport.patronymic is None
    assert passport.number == "P9314956C", "the passport keeps its own numbers"
    assert patent.number == "2600184371"


def test_a_saved_layout_keeps_the_continuation_row(tmp_path) -> None:
    """Saving the layout dialog rebuilds every slot — and the rebuild used to
    lose the wrap geometry. After one save «Кем выдан»'s continuation forgot
    the margin row and printed «БЛАСТИ» UNDER the boxes instead of in them.
    """
    base = SLOTS["p9_pat_issuer"]
    moved = placed({"fields": {"p9_pat_issuer": [base.x, base.baseline,
                                                 base.size]}})["p9_pat_issuer"]
    assert moved.wrap_x == base.wrap_x, "the margin row was forgotten"
    assert moved.wrap_per_row == base.wrap_per_row
    assert moved.wrap_pitch == base.wrap_pitch
    assert moved.row_step == base.row_step

    # and through a real render: the issuer's tail sits ON the margin row
    data = MvdTrudData(**_WORKER, layout={
        "fields": {"p9_pat_issuer": [base.x, base.baseline, base.size]}})
    pdf = render(data, _blank(tmp_path))
    with fitz.open("pdf", pdf) as doc:
        tail = [(x, y) for t, x, y in _ink(doc[8]) if t.strip() == "И"]
        row2 = [x for x, y in tail
                if abs(y - (base.baseline + base.row_step)) < 0.004]
        assert row2, "the continuation row lost its place after a save"
        assert min(row2) < 0.12, "the continuation no longer starts at the margin"


# --------------------------------------------------- МОСКОВСКАЯ ОБЛАСТЬ


def _oblast_blank(folder: Path) -> Path:
    blank = folder / "RADISYE.pdf"
    doc = fitz.open()
    for _ in range(11):
        doc.new_page(width=595, height=842)
    doc.save(str(blank))
    doc.close()
    return blank


def test_the_oblast_map_covers_real_pages_and_has_no_dead_slots() -> None:
    from src.pdf.mvd_trud_renderer import oblast_values
    from src.pdf.mvd_trud_spec import OBLAST_SLOTS, PAGE_COUNTS

    for key, slot in OBLAST_SLOTS.items():
        assert 1 <= slot.page <= PAGE_COUNTS["oblast"], key
    made = set(oblast_values(MvdTrudData(**_WORKER)))
    slotted = set(OBLAST_SLOTS)
    assert made == slotted, (
        f"missing slots: {made - slotted} · dead slots: {slotted - made}")


def test_the_oblast_packet_renders_eleven_pages(tmp_path) -> None:
    pdf = render(MvdTrudData(**_WORKER), _oblast_blank(tmp_path), "oblast")
    with fitz.open("pdf", pdf) as doc:
        assert doc.page_count == 11
        # Прил.№1 runs the issue date as ONE row of eight boxes
        ink6 = "".join(t for t, _, _ in _ink(doc[5]))
        assert "15052018" in ink6.replace(" ", "")
        # the справка о приеме writes «б/н» when the уведомление has a number
        ink11 = " ".join(t for t, _, _ in _ink(doc[10]))
        assert "1259 от 28.07.2026" in ink11
        # a Moscow blank of ten pages is refused for the область packet
    from src.common.errors import OfisError

    with pytest.raises(OfisError):
        render(MvdTrudData(**_WORKER), _blank(tmp_path), "oblast")


def test_each_region_keeps_its_own_blanks_and_layouts(tmp_path) -> None:
    from src.app import build_container
    from src.config.settings_service import SettingsService
    from src.services.mvd_trud_service import MvdTrudService, region_of

    service = MvdTrudService(build_container().resolve(SettingsService))
    moscow = service.add_template("ГЛОБАЛПРО", _blank(tmp_path))
    oblast = service.add_template("РАДИСЬЕ", _oblast_blank(tmp_path), "oblast")

    assert region_of(moscow) == "moscow" and region_of(oblast) == "oblast"
    assert moscow in service.templates("moscow")
    assert oblast in service.templates("oblast")
    assert oblast not in service.templates("moscow")

    # the same blank NAME in the two regions must not share a layout
    twin = service.add_template("ГЛОБАЛПРО", _oblast_blank(tmp_path), "oblast")
    service.save_layout(moscow, {"fields": {"p1_fio": [0.1, 0.2, 0.012]}})
    assert service.layout(twin) == {}, "the область twin inherited Moscow's dragging"
    assert service.layout(moscow)["fields"]["p1_fio"] == [0.1, 0.2, 0.012]
