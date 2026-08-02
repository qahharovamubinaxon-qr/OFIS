"""СТРАХОВКА МАШИНАГА — the ОСАГО policy on the insurer's own PDF blank."""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import fitz
import pytest
from src.config import paths
from src.domain.vehicle import DriverLicence, Sts
from src.pdf.osago_renderer import OsagoData, output_name, render, values
from src.pdf.osago_spec import BASES, INGO_MAP, RESO_MAP


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    sandbox = tempfile.mkdtemp()
    monkeypatch.setenv("XDG_DATA_HOME", sandbox)
    monkeypatch.setenv("LOCALAPPDATA", sandbox)
    paths.data_dir.cache_clear()
    yield
    paths.data_dir.cache_clear()


def _blank(folder: Path) -> Path:
    blank = folder / "POLIS.pdf"
    doc = fitz.open()
    doc.new_page(width=596, height=842)
    doc.save(str(blank))
    doc.close()
    return blank


_CAR = Sts(series="9981", number="585582", plate="М765НК193",
           vin="ХТА21150033523017", mark="VAZ", model="21150",
           owner_fio="ДЕНИСОВА МАРИЯ СЕРГЕЕВНА")
_DRIVER = DriverLicence(surname="НАЙДЕНОВ", name="АЛЕКСЕЙ",
                        patronymic="ВЛАДИМИРОВИЧ",
                        series="9931", number="829630")


def _data(**over) -> OsagoData:
    base = dict(sts=_CAR, drivers=[], unlimited=True,
                start=date(2026, 7, 15), until=date(2027, 7, 14))
    base.update(over)
    return OsagoData(**base)


# ------------------------------------------------------------- the values


def test_no_licences_marks_the_unlimited_box_with_stars() -> None:
    made = values(_data(), "ingosstrah")
    assert made["tick_unlimited"] == "X" and made["tick_named"] == ""
    assert made["dr1_fio"].startswith("****")
    assert made["dr1_vu"] == "****" and made["dr1_kbm"] == "**"
    assert made["dr5_num"] == "-"


def test_licences_mark_the_named_box_and_fill_the_rows() -> None:
    made = values(_data(drivers=[_DRIVER], unlimited=False), "reso")
    assert made["tick_named"] == "V" and made["tick_unlimited"] == ""
    assert made["dr1_fio"] == "НАЙДЕНОВ АЛЕКСЕЙ ВЛАДИМИРОВИЧ"
    assert made["dr1_vu"] == "9931 829630"
    assert made["dr2_fio"] == ""            # the rest of the table stays empty


def test_each_style_prints_its_own_manner() -> None:
    ingo = values(_data(), "ingosstrah")
    assert ingo["srok_from"] == "15.07.2026 г."
    assert ingo["use_period"] == "с 15.07.2026 г. по 14.07.2027 г.,"
    assert ingo["doc_number"] == "585582"
    reso = values(_data(), "reso")
    assert reso["srok_from"] == "00 ч. 00 мин. 15.07.2026 г."
    assert reso["doc_number"] == "9981585582"       # joined, as the sample
    assert reso["vin"] == "ХТА21150033523017"
    assert values(_data(sts=Sts(plate="С336ТУ28")), "reso")["vin"] \
        == "ОТСУТСТВУЕТ"


def test_every_value_key_has_a_slot_in_some_style() -> None:
    made = set(values(_data(), "ingosstrah"))
    known = set(INGO_MAP) | set(RESO_MAP) | {"deal_dots"}
    assert set(INGO_MAP) <= made and set(RESO_MAP) <= made
    assert made <= known, f"orphan values: {made - known}"


# ------------------------------------------------------------- the render


def test_render_puts_the_vin_into_its_cells(tmp_path) -> None:
    import numpy as np

    pdf = render(_data(), _blank(tmp_path), "ingosstrah")
    with fitz.open("pdf", pdf) as doc:
        ink = doc[0].get_text().replace("\xa0", " ")
        assert "ДЕНИСОВА МАРИЯ СЕРГЕЕВНА" in ink
        assert "15.07.2026 г." in ink
        pix = doc[0].get_pixmap(dpi=150)
        img = np.frombuffer(pix.samples, np.uint8).reshape(
            pix.height, pix.width, pix.n)[:, :, :3]
    from src.pdf.osago_spec import VIN_CELLS

    band = img[int(0.384 * pix.height):int(0.396 * pix.height),
               int(0.30 * pix.width):int(0.75 * pix.width)].mean(axis=2)
    _ys, xs = (band < 128).nonzero()
    assert len(xs), "the VIN left no ink"
    # the row starts and ends on its measured cell centres
    first = (VIN_CELLS[0] - 0.30) * pix.width
    last = (VIN_CELLS[-1] - 0.30) * pix.width
    assert abs(xs.min() - first) < 0.012 * pix.width
    assert abs(xs.max() - last) < 0.012 * pix.width


def test_the_service_keeps_the_style_and_prints(tmp_path) -> None:
    from src.services.osago_service import OsagoService, cover_until

    service = OsagoService()
    blank = service.add_template("РЕСО", _blank(tmp_path), base="reso")
    assert service.base_of(blank) == "reso"

    data = _data(drivers=[_DRIVER], unlimited=False,
                 start=date(2026, 7, 10), until=cover_until(date(2026, 7, 10)))
    result = service.generate(data, blank)
    assert result.saved.exists() and result.drivers == 1
    assert result.saved.name.startswith("М765НК193")
    with fitz.open(str(result.saved)) as doc:
        ink = doc[0].get_text().replace("\xa0", " ")
        assert "НАЙДЕНОВ АЛЕКСЕЙ ВЛАДИМИРОВИЧ" in ink
        assert "по 09.07.2027 г." in ink

    # a dragged slot survives beside the style
    service.save_layout(blank, {"fields": {"plate": [0.5, 0.5, 0.02]}})
    assert service.base_of(blank) == "reso"
    assert service.layout(blank)["fields"]["plate"] == [0.5, 0.5, 0.02]


def test_cover_runs_a_year_less_a_day() -> None:
    from src.services.osago_service import cover_until

    assert cover_until(date(2026, 7, 10)) == date(2027, 7, 9)
    assert cover_until(date(2028, 2, 29)) == date(2029, 2, 28)


def test_the_filename_is_the_plate() -> None:
    assert output_name(_data()) == "М765НК193.pdf"
    assert set(BASES) == {"ingosstrah", "reso"}
