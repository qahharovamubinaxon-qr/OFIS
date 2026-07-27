"""ИНН record sheet: validation, layout and the replaceable blank."""

from __future__ import annotations

import tempfile
from datetime import date

import fitz
import pytest

from src.config import paths
from src.domain.documents import Passport
from src.domain.enums import Gender


@pytest.fixture(autouse=True)
def _appdata(monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", tempfile.mkdtemp())
    paths.data_dir.cache_clear()
    yield
    paths.data_dir.cache_clear()


@pytest.fixture()
def svc():
    from src.services.inn_service import InnService

    return InnService()


def _passport(**kw) -> Passport:
    base = dict(
        surname="ИСАКОВ", name="ШАХБОЗ", patronymic="АКМАЛЖОН УГЛИ",
        nationality="УЗБЕКИСТАН", birth_date=date(2000, 12, 27),
        gender=Gender.MALE, series="FA", number="7822242")
    base.update(kw)
    return Passport(**base)


def _make(svc, **kw):
    args = dict(inn="770912345678", form_date=date(2026, 7, 27))
    args.update(kw)
    return svc.generate(_passport(), **args)


# ------------------------------------------------------------ the number


@pytest.mark.parametrize("raw", ["770912345678", "77 09 1234 5678", "7709-1234-5678"])
def test_the_number_is_read_however_it_is_typed(raw) -> None:
    from src.services.inn_service import normalise_inn

    assert normalise_inn(raw) == "770912345678"


@pytest.mark.parametrize("raw", ["", "   ", "7709123456", "7709123456789", "abc"])
def test_a_number_that_is_not_twelve_digits_is_refused(raw) -> None:
    from src.common.errors import OfisError
    from src.services.inn_service import normalise_inn

    with pytest.raises(OfisError):
        normalise_inn(raw)


def test_generate_refuses_a_short_number(svc) -> None:
    from src.common.errors import OfisError

    with pytest.raises(OfisError):
        _make(svc, inn="12345")


# ---------------------------------------------------------------- layout


def test_the_sheet_carries_every_value(svc) -> None:
    r = _make(svc)
    assert r.inn == "770912345678"
    page = fitz.open(r.pdf_path)[0]
    flat = " ".join(page.get_text().split())

    assert "ИСАКОВ ШАХБОЗ АКМАЛЖОН УГЛИ" in flat
    assert "мужской" in flat
    assert "27.12.2000" in flat        # туғилган санаси
    assert "УЗБЕКИСТАН" in flat
    assert "27.07.2026" in flat        # кун
    # the company's own labels survive
    assert "ООО «СФЕРА»" in flat
    assert "ишчининг инн номери" in flat


def test_the_twelve_digits_sit_one_per_cell(svc) -> None:
    from src.services.inn_service import _INN_FIRST_CENTRE, _INN_PITCH

    page = fitz.open(_make(svc, inn="770912345678").pdf_path)[0]
    digits = [(s["bbox"], s["text"]) for b in page.get_text("dict")["blocks"]
              for ln in b.get("lines", []) for s in ln["spans"]
              if s["text"].strip().isdigit() and len(s["text"].strip()) == 1
              and s["bbox"][1] > 410]
    assert len(digits) == 12, digits
    digits.sort(key=lambda d: d[0][0])
    assert "".join(t.strip() for _, t in digits) == "770912345678"

    # each one is centred in its own cell
    for i, (bbox, _) in enumerate(digits):
        centre = (bbox[0] + bbox[2]) / 2
        assert abs(centre - (_INN_FIRST_CENTRE + i * _INN_PITCH)) < 1.5


def test_a_woman_is_labelled_correctly(svc) -> None:
    r = svc.generate(_passport(gender=Gender.FEMALE), inn="770912345678",
                     form_date=date(2026, 7, 27))
    assert "женский" in fitz.open(r.pdf_path)[0].get_text()


def test_an_unknown_sex_leaves_the_line_blank(svc) -> None:
    r = svc.generate(_passport(gender=None), inn="770912345678",
                     form_date=date(2026, 7, 27))
    text = fitz.open(r.pdf_path)[0].get_text()
    assert "мужской" not in text and "женский" not in text
    assert "ИСАКОВ ШАХБОЗ АКМАЛЖОН УГЛИ" in " ".join(text.split())


def test_values_are_set_in_times_new_roman(svc) -> None:
    """The office asked for New Times Roman, like the sheet's own labels."""
    fonts = {f[3] for f in fitz.open(_make(svc).pdf_path)[0].get_fonts()}
    assert any("Times" in f or "Serif" in f for f in fonts), fonts


def test_a_long_name_shrinks_instead_of_overflowing(svc) -> None:
    long_name = _passport(surname="АБДУРАХМАНОВБЕКОВ",
                          name="ХУДОЙБЕРДИМУРОД",
                          patronymic="РУЗИМУХАММАДЖОНОВИЧ")
    r = svc.generate(long_name, inn="770912345678", form_date=date(2026, 7, 27))
    page = fitz.open(r.pdf_path)[0]
    fio = [s for b in page.get_text("dict")["blocks"]
           for ln in b.get("lines", []) for s in ln["spans"]
           if "АБДУРАХМАНОВБЕКОВ" in s["text"]]
    assert fio, "the name was not written"
    assert fio[0]["size"] < 11.4, "the name should have shrunk to fit"
    assert fio[0]["bbox"][2] < 612, "the name runs off the page"


def test_each_worker_gets_their_own_file(svc) -> None:
    first = _make(svc)
    second = _make(svc)
    assert first.pdf_path != second.pdf_path
    assert first.pdf_path.exists() and second.pdf_path.exists()


# ------------------------------------------------------ replaceable blank


def test_the_office_can_supply_its_own_sheet(svc, tmp_path) -> None:
    from src.services.inn_service import blank_source, import_blank, user_blank_path

    _bundled, own = blank_source()
    assert own is False

    mine = tmp_path / "yangi.pdf"
    doc = fitz.open()
    doc.new_page(width=612, height=842).insert_text(
        (60, 700), "YANGI VARAQ", fontsize=9)
    doc.save(str(mine))
    doc.close()

    saved = import_blank(mine)
    assert saved == user_blank_path()

    used, own = blank_source()
    assert own is True and used == saved

    text = fitz.open(_make(svc).pdf_path)[0].get_text()
    assert "YANGI VARAQ" in text, "the uploaded sheet was not used"
    assert "770912345678" in "".join(text.split())


def test_the_sheet_lives_outside_the_program_folder() -> None:
    from src.services.inn_service import user_blank_path

    own = user_blank_path()
    assert paths.data_dir() in own.parents
    assert paths.app_root() not in own.parents


def test_a_non_a4_sheet_is_refused(tmp_path) -> None:
    from src.common.errors import OfisError
    from src.services.inn_service import import_blank

    small = tmp_path / "small.pdf"
    doc = fitz.open()
    doc.new_page(width=200, height=200)
    doc.save(str(small))
    doc.close()
    with pytest.raises(OfisError) as exc:
        import_blank(small)
    assert "A4" in exc.value.message


def test_an_unreadable_sheet_is_refused(tmp_path) -> None:
    from src.common.errors import OfisError
    from src.services.inn_service import import_blank

    junk = tmp_path / "junk.pdf"
    junk.write_bytes(b"not a pdf")
    with pytest.raises(OfisError):
        import_blank(junk)


def test_the_bundled_blank_carries_no_previous_worker() -> None:
    """The sample's data was stripped when the blank was made."""
    from src.services.inn_service import blank_source

    blank, _ = blank_source()
    text = " ".join(fitz.open(blank)[0].get_text().split())
    assert "ГУЛЖОНОВ" not in text
    assert "505925473322" not in text.replace(" ", "")
    assert "16.06.1987" not in text
    # …but the sheet itself is intact
    assert "ООО «СФЕРА»" in text and "фукаролиги" in text
