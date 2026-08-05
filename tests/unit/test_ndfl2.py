"""2 НДФЛ — the office's own справка, its arithmetic and its places.

Every expected number here is taken from the pair the office handed over:
its empty sheet and the same sheet filled in for ЭШДАВЛАТОВ.
"""

from __future__ import annotations

import tempfile
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import fitz
import pytest
from src.common.errors import ValidationError
from src.config import paths
from src.pdf.ndfl2_renderer import Ndfl2Data, money, month_rows, values
from src.pdf.ndfl2_spec import ALL_SLOTS, ROWS_PER_TABLE, TABLE_KEYS

#: the sheet groups thousands with a NO-BREAK space, the way Russian
#: typing does — the expectations below carry it too
NB = " "


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    sandbox = tempfile.mkdtemp()
    monkeypatch.setenv("XDG_DATA_HOME", sandbox)
    monkeypatch.setenv("LOCALAPPDATA", sandbox)
    paths.data_dir.cache_clear()
    yield
    paths.data_dir.cache_clear()


#: what the office typed on the sample it sent
_SAMPLE = {1: "150000", 2: "150000", 3: "160000", 4: "165000",
           5: "170000", 6: "180000", 7: "190000"}


def _data(**over) -> Ndfl2Data:
    made = Ndfl2Data(
        surname="ЭШДАВЛАТОВ", name="МАЪРУФДЖОН",
        patronymic="НЕГЪМАТУЛЛАЕВИЧ", inn="771686014578",
        birth_date=date(1996, 5, 10), doc_number="402716706",
        months={m: Decimal(v) for m, v in _SAMPLE.items()},
        year=2026, form_date=date(2026, 8, 5))
    for key, value in over.items():
        setattr(made, key, value)
    return made


def _spans(pdf: Path) -> list[dict]:
    found = []
    with fitz.open(str(pdf)) as doc:
        for block in doc[0].get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    span["text"] = " ".join(span["text"].split())
                    found.append(span)
    return found


# ------------------------------------------------------------ arithmetic
def test_the_program_adds_the_months_the_way_the_office_did() -> None:
    """The office's own sample: seven months, 1 165 000, tax 151 450."""
    data = _data()
    assert data.total() == Decimal("1165000")
    assert data.tax_base() == Decimal("1165000")
    assert data.tax() == Decimal("151450.00")
    text = values(data)
    assert text["total_income"] == f"1{NB}165{NB}000.00"
    assert text["tax_base"] == f"1{NB}165{NB}000.00"
    assert text["tax_calculated"] == f"151{NB}450,00"
    assert text["tax_withheld"] == text["tax_calculated"]


@pytest.mark.parametrize("months, total, tax", [
    ({1: "100000"}, f"100{NB}000,00", f"13{NB}000,00"),
    ({1: "50000.55", 2: "49999.45"}, f"100{NB}000,00", f"13{NB}000,00"),
    ({m: "100000" for m in range(1, 13)}, f"1{NB}200{NB}000,00", f"156{NB}000,00"),
])
def test_the_tax_is_thirteen_per_cent_rounded(months, total, tax) -> None:
    data = _data(months={int(m): Decimal(v) for m, v in months.items()})
    assert money(data.total()) == total
    assert money(data.tax()) == tax


def test_money_reads_the_way_the_sheet_prints_it() -> None:
    assert money(Decimal("1165000")) == f"1{NB}165{NB}000,00"
    assert money(Decimal("1165000"), comma=False) == f"1{NB}165{NB}000.00"
    assert money(Decimal("999.5")) == "999,50"
    assert money(0) == "0,00"


def test_the_months_fill_the_left_table_then_the_right() -> None:
    rows = month_rows({m: Decimal("1") for m in range(1, 13)})
    assert len(rows) == 12
    assert [m for m, _b, _c in rows] == list(range(1, 13))
    assert all(column == 0 for _m, _b, column in rows[:ROWS_PER_TABLE])
    assert all(column == 1 for _m, _b, column in rows[ROWS_PER_TABLE:])
    tops = [b for _m, b, _c in rows]
    assert tops[:ROWS_PER_TABLE] == sorted(tops[:ROWS_PER_TABLE])
    # the right table starts again at the top
    assert tops[ROWS_PER_TABLE] == tops[0]


# --------------------------------------------------------------- service
def _service():
    from src.services.ndfl2_service import Ndfl2Service

    return Ndfl2Service()


def test_the_office_s_own_sheet_is_there_from_the_first_run() -> None:
    firms = _service().firms()
    assert [f.name for f in firms] == ["ООО ТРАЙД"]
    assert (firms[0] / "blank.pdf").exists()


def test_the_spravka_lands_where_the_sample_has_it(tmp_path) -> None:
    service = _service()
    firm = service.firms()[0]
    result = service.generate(_data(), firm, output_dir=tmp_path)
    assert result.pdf_path.name == "ЭШДАВЛАТОВ_МАЪРУФДЖОН.pdf"
    assert result.total == Decimal("1165000")
    assert result.tax == Decimal("151450.00")

    spans = _spans(result.pdf_path)
    printed = {s["text"] for s in spans}
    for must in ("Эшдавлатов", "Маъруфджон", "Негъматуллаевич",
                 "771686014578", "402716706", "10", "05", "1996",
                 "1 165 000.00", "151 450,00", "2026"):
        assert must in printed, must
    # seven month rows: the number, the code 2000 and the sum
    assert sum(1 for s in spans if s["text"] == "2000") == 7
    assert sum(1 for s in spans if s["text"].endswith("₽")) == 7

    page_w, page_h = 595.28, 822.05
    where = {s["text"]: (s["origin"][0] / page_w, s["origin"][1] / page_h)
             for s in spans}
    # the four sums are RIGHT-aligned against their cells
    for text, right in (("1 165 000.00", 0.4589),
                        ("151 450,00", 0.4589)):
        span = next(s for s in spans if s["text"] == text)
        assert span["bbox"][2] / page_w == pytest.approx(right, abs=0.01)
    assert where["Эшдавлатов"][1] == pytest.approx(0.2995, abs=0.003)
    assert where["771686014578"][1] == pytest.approx(0.2790, abs=0.003)


def test_the_sheet_s_own_date_is_replaced_not_doubled(tmp_path) -> None:
    """The blank carries a date; the operator's must be the only one."""
    service = _service()
    result = service.generate(_data(form_date=date(2027, 3, 19), year=2027),
                              service.firms()[0], output_dir=tmp_path)
    spans = _spans(result.pdf_path)
    top = [s["text"] for s in spans if s["origin"][1] / 822.05 < 0.16]
    assert "19" in top and "03" in top and top.count("2027") == 2
    assert "05" not in top and "08" not in top, "эски сана қолиб кетган"


def test_it_refuses_what_it_cannot_print(tmp_path) -> None:
    service = _service()
    firm = service.firms()[0]
    with pytest.raises(ValidationError, match="Фирма"):
        service.generate(_data(), None)
    with pytest.raises(ValidationError, match="ой"):
        service.generate(_data(months={}), firm, output_dir=tmp_path)
    with pytest.raises(ValidationError, match="Фамилия"):
        service.generate(_data(surname=""), firm, output_dir=tmp_path)


def test_each_firm_keeps_its_own_sheet_and_arrangement(tmp_path) -> None:
    from src.services.ndfl2_service import load_layout, save_layout

    service = _service()
    first = service.firms()[0]
    second = service.add_firm("ООО ВТОРАЯ", first / "blank.pdf")
    assert second.name == "ООО ВТОРАЯ"
    assert {f.name for f in service.firms()} == {"ООО ТРАЙД", "ООО ВТОРАЯ"}

    save_layout(first, {"fields": {"surname": [0.30, 0.40, 0.02]}})
    assert load_layout(second) == {}, "бир фирма созлови бошқасига ўтган"
    assert load_layout(first).get("fields")

    # and a dragged value really moves on the printed sheet
    result = service.generate(_data(), first, output_dir=tmp_path)
    span = next(s for s in _spans(result.pdf_path) if s["text"] == "Эшдавлатов")
    assert span["origin"][0] / 595.28 == pytest.approx(0.30, abs=0.01)
    assert span["origin"][1] / 822.05 == pytest.approx(0.40, abs=0.01)


def test_every_slot_has_a_label_and_a_sample() -> None:
    """The «📐» window shows a name and a preview for each — none may be
    left blank or the office cannot tell what it is dragging."""
    for key, slot in ALL_SLOTS.items():
        assert slot.label, key
        assert slot.sample, key


def test_the_month_table_can_be_dragged_like_everything_else() -> None:
    """The office asked to move the month rows too, so the table is eight
    handles in the «📐» list — three columns and the last row per side."""
    for side in ("left", "right"):
        for part in ("month", "code", "money", "last"):
            assert f"{side}_{part}" in ALL_SLOTS
    assert TABLE_KEYS == {f"{s}_{p}" for s in ("left", "right")
                          for p in ("month", "code", "money", "last")}


def test_the_rows_follow_the_handles_the_office_dragged() -> None:
    """Dragging the last row apart from the first widens every row."""
    slots = dict(ALL_SLOTS)
    first = slots["left_month"]
    slots["left_last"] = replace(slots["left_last"],
                                 baseline=first.baseline + 0.21)
    rows = month_rows({m: Decimal("1") for m in range(1, 4)}, slots)
    pitch = rows[1][1] - rows[0][1]
    assert pitch == pytest.approx(0.03, abs=1e-6)
    assert rows[2][1] - rows[1][1] == pytest.approx(pitch, abs=1e-9)


# --------------------------------------------------- read off the blank
def test_the_table_is_measured_off_the_firm_s_own_sheet() -> None:
    """Every firm scans its own справка, so the rows and columns are read
    from its rules rather than fixed in code."""
    from src.pdf.ndfl2_detect import detect

    found = detect(_service().firms()[0] / "blank.pdf")
    assert found is not None
    for key in TABLE_KEYS:
        assert key in found, key
    # the right table sits a little over half the page across from the left
    assert found["right_month"][0] - found["left_month"][0] == \
        pytest.approx(0.46, abs=0.02)
    # the rows run down the sheet, first above last
    assert found["left_last"][1] > found["left_month"][1]
    assert found["rate"][1] == pytest.approx(0.360, abs=0.004)


def test_a_sheet_that_is_not_the_form_is_left_alone(tmp_path) -> None:
    """Nothing is guessed: a blank whose rules do not look like the table
    keeps whatever the office arranged."""
    from src.pdf.ndfl2_detect import detect, with_detected

    empty = tmp_path / "empty.pdf"
    with fitz.open() as doc:
        doc.new_page()
        doc.save(str(empty))
    assert detect(empty) is None
    assert with_detected(empty, {"fields": {"surname": [0.1, 0.2, 0.01]}}) == \
        {"fields": {"surname": [0.1, 0.2, 0.01]}}


def test_the_rate_is_written_whether_the_sheet_carries_it_or_not(
        tmp_path) -> None:
    """«Доходы, облагаемые по ставке ___ %» — one firm's sheet prints the
    13 already and another leaves it empty, so the program always writes
    it, and never over the sign or the rule."""
    service = _service()
    result = service.generate(_data(), service.firms()[0],
                              output_dir=tmp_path)
    rate = [s for s in _spans(result.pdf_path) if s["text"] == "13"]
    assert len(rate) == 1, "ставка ёзилмади ёки икки марта ёзилди"
    assert rate[0]["origin"][1] / 822.05 == pytest.approx(0.360, abs=0.004)
    # it stops short of the «%», which the office's sheet prints at 0.404
    assert rate[0]["bbox"][2] / 595.28 < 0.400


def test_the_passport_series_and_number_are_written_together() -> None:
    """«Серия и номер документа» takes both, with no space between."""
    from src.services.ndfl2_service import data_of

    passport = SimpleNamespace(surname="ЗАХИДОВ", name="ДИЛШОДЖАН",
                               patronymic="ИСРАИЛЖАНОВИЧ",
                               birth_date=date(1983, 3, 14),
                               series="FB", number="0757126")
    made = data_of(passport, None, months={1: Decimal("1")}, year=2026,
                   form_date=date(2026, 8, 5))
    assert made.doc_number == "FB0757126"
    assert values(made)["doc_number"] == "FB0757126"
    # a Tajik passport carries digits only
    passport.series = None
    assert data_of(passport, None, months={1: Decimal("1")}, year=2026,
                   form_date=None).doc_number == "0757126"


def test_the_sheet_keeps_its_boldness_when_only_a_face_was_saved() -> None:
    """An arrangement saved before the weight was remembered must still
    print Arial BOLD — the face the office's own справка is typed in."""
    from src.pdf.ndfl2_renderer import _style

    assert _style(None)["bold"] is True
    assert _style({"font": "Arial"})["bold"] is True
    assert _style({"font": "Arial", "bold": False})["bold"] is False
