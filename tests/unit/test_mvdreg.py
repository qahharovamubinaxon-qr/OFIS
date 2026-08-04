"""МВД РЕГИСТРАЦИЯ — the office's own отрывная часть, blue stamp and all."""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import fitz
import pytest
from src.config import paths
from src.domain.documents import Passport
from src.domain.registration_address import RegistrationAddress


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    sandbox = tempfile.mkdtemp()
    monkeypatch.setenv("XDG_DATA_HOME", sandbox)
    monkeypatch.setenv("LOCALAPPDATA", sandbox)
    paths.data_dir.cache_clear()
    yield
    paths.data_dir.cache_clear()


def _passport() -> Passport:
    return Passport(
        surname="ЖУРАЕВА", name="НАФИСА", patronymic="АБДУЛЛАЕВНА",
        nationality="УЗБЕКИСТАН", birth_date=date(1982, 5, 28),
        gender="female", series="FB", number="0701509",
        issue_date=date(2025, 1, 27), expiry_date=date(2035, 1, 26),
        issued_by="МВД 22204")


def _address(tmp: Path) -> RegistrationAddress:
    from src.services.mvdreg_service import MvdRegTemplateBuilder

    address = RegistrationAddress(
        label="БАЛАШИХА", internal_code="balashiha",
        address_text="г. Балашиха, ул. Ленина, д. 33",
        host_fio="ПОПОВ ВЛАДИМИР ГЕННАДЬЕВИЧ", kind="mvdreg",
        oblast="МОСКОВСКАЯ ОБЛАСТЬ", gorod="Г. БАЛАШИХА",
        ulitsa="УЛ. ЛЕНИНА", dom="33", kvartira="15",
        organization_name="ООО СФЕРА", inn="7733481040",
        regional_number="02\\770-2026",
        template_path=tmp / "template.pdf")
    MvdRegTemplateBuilder().build(address.template_path, address)
    return address


def _text(pdf: Path, page: int) -> str:
    with fitz.open(str(pdf)) as doc:
        return " ".join(doc[page - 1].get_text().split())


def _generate(tmp: Path, **kw):
    from src.services.mvdreg_service import MvdRegService

    return MvdRegService().generate(
        _passport(), None, _address(tmp),
        registration_expiry=kw.pop("expiry", date(2026, 11, 8)),
        registration_start=kw.pop("start", date(2026, 8, 10)),
        output_dir=tmp / "out")


def test_the_stamp_formatter_prints_like_the_mvd_stamp() -> None:
    from src.pdf.formatters import FORMATTERS

    stamp = FORMATTERS["date_stamp_ru"]
    assert stamp(date(2026, 8, 10)) == "10 АВГ 2026"
    assert stamp(date(2026, 6, 15)) == "15 ИЮН 2026"
    assert stamp("2026-07-27") == "27 ИЮЛ 2026"
    assert stamp("") == ""


def test_the_template_carries_the_address_and_the_host(tmp_path) -> None:
    address = _address(tmp_path)
    assert address.template_path.exists()
    # the blank is image-only, so any text is what the builder printed
    front = _text(address.template_path, 1)
    assert "МОСКОВСКАЯ ОБЛАСТЬ".replace(" ", "") in front.replace(" ", "")
    assert "ДОМ 33" in front and "КВ. 15" in front
    back = _text(address.template_path, 2)
    assert "ПОПОВ" in back.replace(" ", "")
    assert "7733481040" in back.replace(" ", "")


def test_the_worker_and_both_dates_land_on_the_form(tmp_path) -> None:
    result = _generate(tmp_path)
    assert result.pdf_path.name == "ЖУРАЕВА_НАФИСА.pdf"
    front = _text(result.pdf_path, 1).replace(" ", "")
    for value in ("ЖУРАЕВА", "НАФИСА", "АБДУЛЛАЕВНА", "УЗБЕКИСТАН",
                  "0701509"):
        assert value in front, value
    back = _text(result.pdf_path, 2).replace(" ", "")
    assert "08" in back and "2026" in back


def test_the_start_date_is_a_blue_stamp_in_the_box(tmp_path) -> None:
    """«10 АВГ 2026» — blue, inside the confirmation box, the sample gone."""
    result = _generate(tmp_path)
    with fitz.open(str(result.pdf_path)) as doc:
        page = doc[2 - 1]
        spans = [s for b in page.get_text("dict")["blocks"]
                 for line in b.get("lines", []) for s in line["spans"]]
    stamped = [s for s in spans if "АВГ" in s["text"]]
    assert stamped, "кўк штамп йўқ"
    span = stamped[0]
    assert " ".join(span["text"].split()) == "10 АВГ 2026"
    r = (span["color"] >> 16) & 255
    b = span["color"] & 255
    assert b > 150 and b > r, f"штамп кўк эмас: #{span['color']:06x}"
    # inside the «Отметка о подтверждении» box (upper-right of the back)
    x = span["origin"][0] / 595.28
    y = span["origin"][1] / 841.79
    assert 0.55 < x < 0.85 and 0.18 < y < 0.33


def test_signature_and_stamp_print_once_uploaded(tmp_path) -> None:
    from src.services.mvdreg_service import set_signature, set_stamp

    doodle = fitz.open()
    page = doodle.new_page(width=120, height=60)
    page.draw_line((10, 30), (110, 30), color=(0.1, 0.1, 0.5), width=3)
    set_signature(page.get_pixmap(alpha=True).tobytes("png"))
    stamp_png = tmp_path / "stamp.png"
    page.get_pixmap().save(str(stamp_png))
    set_stamp(stamp_png)

    result = _generate(tmp_path)
    with fitz.open(str(result.pdf_path)) as doc:
        assert len(doc[1].get_images()) >= 3, "имзо ва печать босилмаган"


def test_without_them_nothing_extra_is_printed(tmp_path) -> None:
    result = _generate(tmp_path)
    with fitz.open(str(result.pdf_path)) as doc:
        assert len(doc[1].get_images()) == 1  # the scanned blank itself


def test_the_office_s_own_texts_fonts_and_colours(tmp_path) -> None:
    from src.services import blank_layout
    from src.services.mvdreg_service import SECTION

    address = _address(tmp_path)
    blank_layout.save(SECTION, address.template_path, {
        "fields": {}, "images": {},
        "styles": {"reg.surname": {"colour": [1.0, 0.0, 0.0]}},
        "extra": [{"key": "host_fio", "page": 1, "x": 0.10,
                   "baseline": 0.95, "size": 0.012,
                   "font": "Times New Roman", "colour": [0.0, 0.5, 0.0]}]})
    from src.services.mvdreg_service import MvdRegService

    result = MvdRegService().generate(
        _passport(), None, address, registration_expiry=date(2026, 11, 8),
        registration_start=date(2026, 8, 10), output_dir=tmp_path / "out")
    with fitz.open(str(result.pdf_path)) as doc:
        spans = [s for b in doc[0].get_text("dict")["blocks"]
                 for line in b.get("lines", []) for s in line["spans"]]
    reds = [s for s in spans if s["color"] == 0xFF0000]
    assert "".join(s["text"] for s in reds).replace(" ", "") \
        .startswith("ЖУРАЕВА"[:1]), "фамилия қизил эмас"
    greens = [s for s in spans if s["color"] == 0x008000]
    assert any("ПОПОВ" in s["text"] for s in greens), "қўшимча матн йўқ"


def test_meanings_cover_what_the_form_knows(tmp_path) -> None:
    from src.services.mvdreg_service import (
        CATALOGUE,
        SAMPLES,
        texts_of,
    )

    texts = texts_of(_passport(), _address(tmp_path),
                     date(2026, 8, 10), date(2026, 11, 8))
    missing = [k for k in CATALOGUE if not texts.get(k)]
    assert missing == [], missing
    assert sorted(SAMPLES) == sorted(CATALOGUE)
    assert texts["start_stamp"] == "10 АВГ 2026"
    assert texts["pass_full"] == "FB 0701509"


def test_old_saved_layouts_are_cleared_once(tmp_path) -> None:
    """The first editor pinned every value at the OLD wrong spots on OK —
    those saved positions must not override the corrected map."""
    from src.services import blank_layout
    from src.services.mvdreg_service import (
        LAYOUT_V,
        SECTION,
        refresh_templates,
    )

    address = _address(tmp_path)
    blank_layout.save(SECTION, address.template_path, {
        "fields": {"reg.surname": [0.5, 0.5, 0.02],
                   "host.surname": [0.6, 0.6, 0.02]},
        "extra": [{"key": "fio", "page": 1, "x": 0.1, "baseline": 0.9,
                   "size": 0.012}],
        "styles": {"reg.surname": {"colour": [1, 0, 0]}}})
    refresh_templates([address])
    kept = blank_layout.load(SECTION, address.template_path)
    assert kept.get("v") == LAYOUT_V
    assert not kept.get("fields"), "эски жойлар ўчмаган"
    assert kept.get("extra") and kept.get("styles"), "эганики сақланиши керак"
    # and never again: a layout the office saves NOW stays untouched
    kept["fields"] = {"reg.surname": [0.4, 0.4, 0.02]}
    blank_layout.save(SECTION, address.template_path, kept)
    refresh_templates([address])
    again = blank_layout.load(SECTION, address.template_path)
    assert again.get("fields") == {"reg.surname": [0.4, 0.4, 0.02]}


def test_a_moved_host_text_moves_on_the_rebuilt_template(tmp_path) -> None:
    from src.services import blank_layout
    from src.services.mvdreg_service import (
        LAYOUT_V,
        SECTION,
        MvdRegTemplateBuilder,
    )

    address = _address(tmp_path)
    blank_layout.save(SECTION, address.template_path, {
        "v": LAYOUT_V,
        "fields": {"host.surname": [0.30, 0.30, 0.0140]}})
    MvdRegTemplateBuilder().build(address.template_path, address)
    with fitz.open(str(address.template_path)) as doc:
        spans = [s for b in doc[1].get_text("dict")["blocks"]
                 for line in b.get("lines", []) for s in line["spans"]]
    first = min((s for s in spans if s["text"] == "П"),
                key=lambda s: s["origin"][1])
    assert first["origin"][0] / 595.28 == pytest.approx(0.30, abs=0.02)
    assert first["origin"][1] / 842.03 == pytest.approx(0.30, abs=0.01)


def test_the_address_book_keeps_mvdreg_apart(tmp_path) -> None:
    from src.app import build_container
    from src.services.registration_address_service import (
        RegistrationAddressService,
    )

    service = build_container().resolve(RegistrationAddressService)
    made = service.create_mvdreg(_address(tmp_path))
    assert made.kind == "mvdreg"
    assert [a.id for a in service.list(kind="mvdreg")] == [made.id]
    assert all(a.kind != "mvdreg" for a in service.list(kind="hostel"))


def test_adding_a_second_address_never_fails_on_the_code(tmp_path) -> None:
    """«Адрес қўшиб бўлмаяпти» — the second address with the same (or an
    empty) internal code used to be refused. Now it gets its own."""
    from src.app import build_container
    from src.services.registration_address_service import (
        RegistrationAddressService,
    )

    service = build_container().resolve(RegistrationAddressService)
    first = service.create_mvdreg(_address(tmp_path))
    second = service.create_mvdreg(_address(tmp_path))
    third = service.create_mvdreg(_address(tmp_path))
    codes = {first.internal_code, second.internal_code, third.internal_code}
    assert len(codes) == 3, "коды такрорланган"
    assert len(service.list(kind="mvdreg")) == 3
    for made in (second, third):
        assert made.template_path.exists()


def test_a_new_address_inherits_the_newest_arrangement(tmp_path) -> None:
    """One настройка, then every new address starts from it."""
    from src.app import build_container
    from src.services import blank_layout
    from src.services.mvdreg_service import LAYOUT_V, SECTION
    from src.services.registration_address_service import (
        RegistrationAddressService,
    )

    service = build_container().resolve(RegistrationAddressService)
    first = service.create_mvdreg(_address(tmp_path))
    blank_layout.save(SECTION, first.template_path, {
        "v": LAYOUT_V, "fields": {"host.surname": [0.30, 0.30, 0.0140]},
        "extra": [{"key": "free1", "page": 1, "x": 0.1, "baseline": 0.9,
                   "size": 0.012}],
        "images": {"img_stamp": [2, 0.2, 0.5, 0.1]}})

    second = service.create_mvdreg(_address(tmp_path))
    inherited = blank_layout.load(SECTION, second.template_path)
    assert inherited.get("images") == {"img_stamp": [2, 0.2, 0.5, 0.1]}
    assert inherited.get("extra"), "қўшимча матн мерос ўтмаган"
    # the inherited host position is already printed into the new template
    with fitz.open(str(second.template_path)) as doc:
        spans = [s for b in doc[1].get_text("dict")["blocks"]
                 for line in b.get("lines", []) for s in line["spans"]]
    first_letter = min((s for s in spans if s["text"] == "П"),
                       key=lambda s: s["origin"][1])
    assert first_letter["origin"][1] / 841.79 == pytest.approx(0.30, abs=0.01)


def test_each_address_keeps_its_own_stamp(tmp_path) -> None:
    from src.services.mvdreg_service import MvdRegService, asset, set_stamp

    one = _address(tmp_path / "a")
    two = _address(tmp_path / "b")
    picture = fitz.open()
    page = picture.new_page(width=80, height=80)
    page.draw_circle((40, 40), 30, color=(0, 0, 0.6), width=3)
    png = tmp_path / "stamp.png"
    page.get_pixmap().save(str(png))
    set_stamp(png, one.template_path)

    assert asset("stamp", one.template_path) is not None
    assert asset("stamp", two.template_path) is None, "печать бошқасига ўтган"
    made = MvdRegService().generate(
        _passport(), None, one, registration_expiry=date(2026, 11, 8),
        registration_start=date(2026, 8, 10), output_dir=tmp_path / "out")
    with fitz.open(str(made.pdf_path)) as doc:
        assert len(doc[1].get_images()) >= 2
