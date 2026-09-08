import io
from datetime import date
from pathlib import Path

import fitz
from PIL import Image
from src.pdf import alliance_renderer as ar
from src.pdf.alliance_fields import Field


def _blank(tmp_path: Path, pages: int = 1) -> Path:
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page(width=842, height=632)
    p = tmp_path / "blank.pdf"
    doc.save(str(p))
    doc.close()
    return p


def _png() -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (300, 400), "white").save(b, "PNG")
    return b.getvalue()


def test_end_date_is_exactly_three_years():
    assert ar.end_date(date(2026, 9, 7)) == date(2029, 9, 7)


def test_values_cover_the_catalogue():
    from src.pdf.alliance_fields import CATALOGUE
    v = ar.values(ar.AllianceData(
        surname="АШУРОВ", name="ДИЛМУРОД", patronymic="СУЮНБОЕВИЧ",
        gender="Мужской", ud_number="2400-0145", dolzhnost="РАБОЧИЙ",
        start_date=date(2026, 9, 7)))
    assert v["end_date"] == "07.09.2029"
    assert v["start_date"] == "07.09.2026"
    assert v["fio_upper"] == "АШУРОВ ДИЛМУРОД СУЮНБОЕВИЧ"
    assert set(CATALOGUE) <= set(v)


def test_render_places_text_and_photo(tmp_path: Path):
    blank = _blank(tmp_path, pages=2)
    layout = {"fields": [
        Field(key="surname", page=1, x=0.4, baseline=0.4, size=0.04).as_dict(),
        Field(key="img_photo", page=1, x=0.15, baseline=0.78,
              size=0.42).as_dict(),
    ]}
    data = ar.AllianceData(
        surname="АШУРОВ", name="Д", patronymic="С", gender="М",
        ud_number="1", dolzhnost="Р", start_date=date(2026, 9, 7),
        photo_png=_png(), sign_png=None)
    pdf = ar.render(data, blank, layout)
    assert pdf[:4] == b"%PDF" and len(pdf) > 1000


def test_render_ignores_a_photo_field_with_no_photo(tmp_path: Path):
    blank = _blank(tmp_path, pages=1)
    layout = {"fields": [
        Field(key="img_photo", page=1, x=0.1, baseline=0.5, size=0.3).as_dict(),
    ]}
    data = ar.AllianceData(surname="АШУРОВ", name="Д", photo_png=None)
    pdf = ar.render(data, blank, layout)          # must not raise
    assert pdf[:4] == b"%PDF"


def test_output_name_is_surname_name():
    n = ar.output_name(ar.AllianceData(
        surname="Ашуров", name="Дилмурод", patronymic="", gender="",
        ud_number="", dolzhnost="", start_date=None))
    assert n == "АШУРОВ_ДИЛМУРОД.pdf"
