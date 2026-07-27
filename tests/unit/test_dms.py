"""ДМС polis: the one-year-less-a-day rule, the allocated number block, the
filled layout and the Code 128 barcode."""

from __future__ import annotations

import tempfile
from datetime import date

import fitz
import pytest

from src.config import paths
from src.domain.documents import Passport
from src.domain.enums import Gender


@pytest.fixture()
def svc(monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", tempfile.mkdtemp())
    paths.data_dir.cache_clear()
    from src.app import build_container
    from src.config.settings_service import SettingsService
    from src.services.dms_service import KEY_FROM, KEY_TO, DmsService

    settings = build_container().resolve(SettingsService)
    settings.set(KEY_FROM, "50682676085")
    settings.set(KEY_TO, "50682676088")      # a block of four
    yield DmsService(settings)
    paths.data_dir.cache_clear()


def _passport() -> Passport:
    return Passport(
        surname="ТОШПУЛАТОВ", name="ХУДОЙБЕРДИ", patronymic="МУРОДОВИЧ",
        nationality="УЗБЕКИСТАН", birth_date=date(1996, 4, 8), gender=Gender.MALE,
        series="FB", number="2582213", issue_date=date(2026, 6, 13),
        issued_by="МВД 22220", expiry_date=date(2036, 6, 12))


def _make(svc, **kw):
    args = dict(start_date=date(2026, 7, 27), phone="+79683941008",
                address="Москва Вяземская улица, 1к1, кв. 62", region="Москва")
    args.update(kw)
    return svc.generate(_passport(), **args)


# ------------------------------------------------------------- dates


@pytest.mark.parametrize(("start", "end"), [
    ((2026, 7, 27), (2027, 7, 26)),     # the owner's own example
    ((2026, 7, 10), (2027, 7, 9)),      # the sample policy
    ((2026, 1, 1), (2026, 12, 31)),
    ((2026, 3, 1), (2027, 2, 28)),
    ((2024, 2, 29), (2025, 2, 28)),     # leap day
])
def test_cover_is_one_year_less_a_day(start, end) -> None:
    from src.services.dms_service import policy_end_date

    assert policy_end_date(date(*start)) == date(*end)


def test_result_carries_both_dates(svc) -> None:
    r = _make(svc)
    assert r.start_date == date(2026, 7, 27)
    assert r.end_date == date(2027, 7, 26)


# ----------------------------------------------------------- numbering


def test_numbers_come_from_the_allocated_block_in_order(svc) -> None:
    assert svc.peek_number() == "50682676085"
    assert svc.remaining() == 4
    assert [_make(svc).policy_number for _ in range(3)] == [
        "50682676085", "50682676086", "50682676087"]
    assert svc.peek_number() == "50682676088"
    assert svc.remaining() == 1


def test_the_block_cannot_be_overrun(svc) -> None:
    """When РЕСО's numbers run out the program stops — it never invents one."""
    from src.common.errors import OfisError

    for _ in range(4):
        _make(svc)
    assert svc.remaining() == 0
    assert svc.peek_number() == ""
    with pytest.raises(OfisError) as exc:
        _make(svc)
    assert "тугади" in exc.value.message


def test_without_a_block_nothing_is_issued(monkeypatch) -> None:
    from src.app import build_container
    from src.common.errors import OfisError
    from src.config.settings_service import SettingsService
    from src.services.dms_service import DmsService

    monkeypatch.setenv("XDG_DATA_HOME", tempfile.mkdtemp())
    paths.data_dir.cache_clear()
    bare = DmsService(build_container().resolve(SettingsService))
    assert bare.peek_number() == "" and bare.remaining() == 0
    with pytest.raises(OfisError) as exc:
        bare.generate(_passport(), start_date=date(2026, 7, 27),
                      phone="+7", address="Москва")
    assert "киритилмаган" in exc.value.message
    paths.data_dir.cache_clear()


def test_address_is_required(svc) -> None:
    from src.common.errors import OfisError

    with pytest.raises(OfisError):
        _make(svc, address="   ")


# -------------------------------------------------------------- layout


def test_the_policy_carries_the_worker_and_the_dates(svc) -> None:
    r = _make(svc)
    text = fitz.open(r.pdf_path)[0].get_text()

    # both blocks (Страхователь and Застрахованный) name the same worker
    assert text.count("Тошпулатов Худойберди Муродович") == 2
    assert text.count("Москва Вяземская улица, 1к1, кв. 62") == 2
    assert text.count("FB2582213, 13.06.2026, МВД 22220") == 2
    assert text.count("+79683941008") == 2
    assert text.count("Узбекистан") == 2
    assert text.count("Мужской") == 2
    assert text.count("08.04.1996") == 2
    assert "Москва" in text                       # регион действия патента

    # the validity sentence, in the insurer's own long-date wording
    flat = " ".join(text.split())
    assert "вступает в силу с 27 июля 2026 г. 00 ч. 00 мин." in flat
    assert "действует по 26 июля 2027 г. 24 ч. 00 мин." in flat

    # the number appears twice: red under the title and under the barcode
    assert text.count("50682676085") == 2


def test_a_woman_is_labelled_correctly(svc) -> None:
    p = _passport().model_copy(update={"gender": Gender.FEMALE})
    r = svc.generate(p, start_date=date(2026, 7, 27), phone="+7",
                     address="Москва")
    assert "Женский" in fitz.open(r.pdf_path)[0].get_text()


def test_each_policy_gets_its_own_file(svc) -> None:
    first, second = _make(svc), _make(svc)
    assert first.pdf_path != second.pdf_path
    assert first.pdf_path.exists() and second.pdf_path.exists()


def test_output_keeps_both_pages_of_the_form(svc) -> None:
    assert len(fitz.open(_make(svc).pdf_path)) == 2


# ------------------------------------------------------------- barcode


def test_barcode_encodes_exactly_the_policy_number() -> None:
    from src.pdf.barcode import code128_values

    values = code128_values("50682676085")
    assert values[0] == 104 and values[-1] == 106      # start-B … stop
    digits = [chr(v + 32) for v in values[1:-2]]
    assert "".join(digits) == "50682676085"

    # the checksum is the documented modulo-103 weighted sum
    expected = (values[0] + sum(i * v for i, v in enumerate(values[1:-2], 1))) % 103
    assert values[-2] == expected


def test_barcode_is_drawn_as_vector_bars(svc) -> None:
    """Bars are real rectangles, so they stay sharp at any print resolution."""
    page = fitz.open(_make(svc).pdf_path)[0]
    bars = [d for d in page.get_drawings()
            if d["rect"].y0 > 50 and d["rect"].y1 < 70
            and 420 < d["rect"].x0 < 510 and d["rect"].width < 4]
    assert len(bars) > 20, "the barcode bars were not drawn"


def test_barcode_rejects_non_ascii() -> None:
    from src.pdf.barcode import code128_modules

    with pytest.raises(ValueError):
        code128_modules("50682Ж76085")


# --------------------------------------------------------- typography


def test_values_are_set_in_arial(svc) -> None:
    """The office asked for Arial; the bundled fallback is Liberation Sans,
    which is metric-compatible, so either is acceptable."""
    page = fitz.open(_make(svc).pdf_path)[0]
    fonts = {f[3] for f in page.get_fonts()}
    assert any("Arial" in f or "Liberation" in f for f in fonts), fonts
    assert not any("Times" in f or "Serif" in f for f in fonts), fonts


def test_text_is_small_enough_for_the_cells(svc) -> None:
    page = fitz.open(_make(svc).pdf_path)[0]
    sizes = [round(s["size"], 1)
             for b in page.get_text("dict")["blocks"]
             for ln in b.get("lines", [])
             for s in ln.get("spans", [])]
    assert sizes, "no text was written"
    # everything except the red policy number stays at or under 10pt
    body = [s for s in sizes if s < 12]
    assert body and max(body) <= 10.0, sizes


def test_the_blank_is_not_painted_over(svc) -> None:
    """The form's guilloche must show through — no flat filled patches."""
    import numpy as np

    from src.services.dms_service import blank_source

    blank, _own = blank_source()
    page = fitz.open(blank)[0]
    pm = page.get_pixmap(dpi=200)
    a = np.frombuffer(pm.samples, dtype=np.uint8).reshape(pm.height, pm.width, pm.n)
    s = 200 / 72
    # a cleared value cell still varies in tone, like the paper around it
    cell = a[int(300 * s):int(315 * s), int(200 * s):int(400 * s), :3]
    assert cell.std() > 2.0, "the cell looks like a flat painted rectangle"


# ------------------------------------------------------ replaceable blank


def test_the_office_can_supply_its_own_blank(svc, tmp_path) -> None:
    """A clean scan dropped in AppData wins over the bundled one, and the
    program prints on it."""
    from src.services.dms_service import blank_source, import_blank, user_blank_path

    bundled, own = blank_source()
    assert own is False, "no upload yet, so the bundled blank is used"

    # a marked A4 stand-in for the office's own scan
    mine = tmp_path / "clean.pdf"
    doc = fitz.open()
    doc.new_page(width=595, height=842).insert_text(
        (60, 700), "MENING BLANKAM", fontsize=9)
    doc.save(str(mine))
    doc.close()

    saved = import_blank(mine)
    assert saved == user_blank_path()
    assert saved.exists()

    used, own = blank_source()
    assert own is True and used == saved

    text = fitz.open(_make(svc).pdf_path)[0].get_text()
    assert "MENING BLANKAM" in text, "the upload was not used"
    assert "Тошпулатов Худойберди Муродович" in text


def test_the_blank_lives_outside_the_program_folder() -> None:
    """An EXE rebuild or `git pull` must never wipe the office's blank."""
    from src.config import paths
    from src.services.dms_service import user_blank_path

    own = user_blank_path()
    assert paths.data_dir() in own.parents
    assert paths.app_root() not in own.parents


def test_a_non_a4_file_is_refused(tmp_path) -> None:
    from src.common.errors import OfisError
    from src.services.dms_service import import_blank

    small = tmp_path / "small.pdf"
    doc = fitz.open()
    doc.new_page(width=200, height=200)
    doc.save(str(small))
    doc.close()
    with pytest.raises(OfisError) as exc:
        import_blank(small)
    assert "A4" in exc.value.message


def test_an_unreadable_file_is_refused(tmp_path) -> None:
    from src.common.errors import OfisError
    from src.services.dms_service import import_blank

    junk = tmp_path / "junk.pdf"
    junk.write_bytes(b"not a pdf at all")
    with pytest.raises(OfisError):
        import_blank(junk)
