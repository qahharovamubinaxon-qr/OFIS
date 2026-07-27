"""БЕЙДЖИК — the office's own worker badge: layout, numbering, blanks."""

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


class _Settings:
    def __init__(self) -> None:
        self._d: dict = {}

    def get(self, key, default=None):
        return self._d.get(key, default)

    def set(self, key, value) -> None:
        self._d[key] = value


@pytest.fixture()
def settings() -> _Settings:
    s = _Settings()
    s.set("beydjik.pr_next", 4476661)
    return s


@pytest.fixture()
def svc(settings):
    from src.services.beydjik_service import BeydjikService

    return BeydjikService(settings)


def _passport(**kw) -> Passport:
    base = dict(
        surname="БОЛТАЗОДА", name="РУСТАМ", patronymic="МАХМАД",
        nationality="ТАДЖИКИСТАН", birth_date=date(1994, 8, 1),
        gender=Gender.MALE, series="", number="402565897")
    base.update(kw)
    return Passport(**base)


def _make(svc, **kw):
    args = dict(region="77", personal_number="2600586935",
                inn="772998449826", issue_date=date(2026, 6, 24),
                firm="ООО СФЕРА")
    args.update(kw)
    return svc.generate(_passport(), **args)


def _flat(path) -> str:
    return " ".join(fitz.open(path)[0].get_text().split())


# --------------------------------------------------------------- the card


def test_the_badge_carries_every_value(svc) -> None:
    r = _make(svc)
    flat = _flat(r.pdf_path)

    assert "Болтазода" in flat and "Рустам" in flat and "Махмад" in flat
    assert "01.08.1994" in flat
    assert "Таджикистан" in flat
    assert "402565897" in flat          # паспорт
    assert "772998449826" in flat       # ИНН
    assert "2600586935" in flat         # шахсий номер
    assert "24.06.2026" in flat         # дата выдачи
    assert "ООО СФЕРА" in flat          # кем выдано
    # the blank's own labels survive (only the front ones are live text —
    # the back's «Кем выдано» is part of the card's raster artwork)
    assert "Гражданство" in flat and "Документ удост.личность/ИНН" in flat


def test_the_page_stays_the_badge_card_size(svc) -> None:
    page = fitz.open(_make(svc).pdf_path)[0]
    assert 260 < page.rect.width < 266
    assert 368 < page.rect.height < 373


def test_a_moscow_badge_names_moscow_not_the_oblast(svc) -> None:
    """Both blanks print «Московская область», so the line must be rewritten."""
    flat = _flat(_make(svc, region="77").pdf_path)
    assert "г. Москва" in flat
    assert "Московская область" not in flat


def test_an_oblast_badge_keeps_the_oblast(svc) -> None:
    flat = _flat(_make(svc, region="50", dolzhnost="Водитель").pdf_path)
    assert "Московская область" in flat
    assert "г. Москва" not in flat


def test_the_old_region_line_is_actually_erased(svc) -> None:
    """Not just overwritten — the printed «Московская область» must be gone.

    The text layer alone would not catch it, because the line is part of the
    blank's raster artwork, so the ink itself is measured.
    """
    import numpy as np

    page = fitz.open(_make(svc, region="77").pdf_path)[0]
    # the strip that carried «…область» beyond where the shorter «г. Москва»
    # reaches (that one starts at x≈214.5)
    pm = page.get_pixmap(dpi=600, clip=fitz.Rect(184.0, 324.5, 213.0, 332.5))
    arr = np.frombuffer(pm.samples, dtype=np.uint8).reshape(
        pm.height, pm.width, pm.n)[:, :, :3]
    assert (arr.max(2) < 110).sum() == 0, "the old region line is still printed"


def test_the_dolzhnost_line_is_only_on_the_oblast_layout(svc) -> None:
    assert "Водитель" in _flat(
        _make(svc, region="50", dolzhnost="Водитель").pdf_path)
    # Москва has no профессия row, so the value is dropped rather than misplaced
    assert "Водитель" not in _flat(
        _make(svc, region="77", dolzhnost="Водитель").pdf_path)


def test_the_document_line_uses_the_blank_s_own_slash(svc) -> None:
    """The blank already prints «/» between паспорт and ИНН.

    Writing another one produced a visible double slash, so the two numbers
    are placed on either side of the printed separator instead.
    """
    from src.services.beydjik_service import _DOC_INN_X, _DOC_PASSPORT_MAX_X

    page = fitz.open(_make(svc).pdf_path)[0]
    spans = [s for b in page.get_text("dict")["blocks"]
             for ln in b.get("lines", []) for s in ln["spans"]]
    passport = next(s for s in spans if s["text"].strip() == "402565897")
    inn = next(s for s in spans if s["text"].strip() == "772998449826")

    assert "/" not in passport["text"] and "/" not in inn["text"]
    assert passport["bbox"][2] <= _DOC_PASSPORT_MAX_X
    assert inn["bbox"][0] >= _DOC_INN_X - 0.5


def test_the_values_are_set_in_arial(svc) -> None:
    """The office asked for Arial Regular, matching the blank's own labels."""
    fonts = {f[3] for f in fitz.open(_make(svc).pdf_path)[0].get_fonts()}
    assert any("Arial" in f or "LiberationSans" in f for f in fonts), fonts


def test_a_long_name_shrinks_instead_of_running_off_the_card(svc) -> None:
    from src.services.beydjik_service import _SIZE

    long_name = _passport(surname="Абдурахманбековхудойбердиев")
    r = svc.generate(long_name, region="77", personal_number="2600586935",
                     inn="772998449826", issue_date=date(2026, 6, 24))
    page = fitz.open(r.pdf_path)[0]
    span = next(s for b in page.get_text("dict")["blocks"]
                for ln in b.get("lines", []) for s in ln["spans"]
                if "Абдурахман" in s["text"])
    assert span["bbox"][2] < 263.04, "the name runs off the card"
    assert span["size"] < _SIZE, "the name should have shrunk to fit"


def test_a_long_firm_name_wraps_onto_a_second_line(svc) -> None:
    """«Кем выдано» is followed by the firm, which may need two lines.

    The back prints rotated, so line two sits *above* line one on the page.
    """
    from src.services.beydjik_service import _FIRM_BASE, _FIRM_LINE

    r = _make(svc, firm="ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ СФЕРА")
    page = fitz.open(r.pdf_path)[0]
    lines = [s for b in page.get_text("dict")["blocks"]
             for ln in b.get("lines", []) for s in ln["spans"]
             if "ОБЩЕСТВО" in s["text"] or "ОТВЕТСТВЕННОСТЬЮ" in s["text"]]
    assert len(lines) >= 2, "the firm name did not wrap"
    tops = sorted(round(s["origin"][1], 1) for s in lines)
    assert abs((tops[-1] - tops[0]) - _FIRM_LINE) < 0.2
    assert abs(tops[-1] - _FIRM_BASE) < 0.2


# ------------------------------------------------------------- numbering


def test_the_pr_serial_counts_up_by_one(svc, settings) -> None:
    first = _make(svc)
    second = _make(svc)
    assert first.pr_number == "4476661"
    assert second.pr_number == "4476662"
    assert settings.get("beydjik.pr_next") == 4476663
    assert "4476661" in "".join(_flat(first.pdf_path).split())


def test_the_next_serial_can_be_read_without_spending_it(svc, settings) -> None:
    assert svc.peek_pr() == "4476661"
    assert svc.peek_pr() == "4476661"
    assert settings.get("beydjik.pr_next") == 4476661


def test_the_firm_falls_back_to_the_office_default(settings) -> None:
    from src.services.beydjik_service import DEFAULT_FIRM, BeydjikService

    assert BeydjikService(settings).firm() == DEFAULT_FIRM
    settings.set("beydjik.firm", "ООО ГРАД")
    assert BeydjikService(settings).firm() == "ООО ГРАД"


def test_each_worker_gets_their_own_file(svc) -> None:
    first, second = _make(svc), _make(svc)
    assert first.pdf_path != second.pdf_path
    assert first.pdf_path.exists() and second.pdf_path.exists()


# ------------------------------------------------------------- validation


def test_an_unknown_region_is_refused(svc) -> None:
    from src.common.errors import OfisError

    with pytest.raises(OfisError):
        _make(svc, region="99")


def test_a_missing_personal_number_is_refused(svc) -> None:
    from src.common.errors import OfisError

    with pytest.raises(OfisError):
        _make(svc, personal_number="  ")


# ------------------------------------------------- replaceable blanks


def test_each_region_has_its_own_replaceable_blank(svc, tmp_path) -> None:
    from src.services.beydjik_service import (
        blank_source,
        import_blank,
        user_blank_path,
    )

    for code in ("77", "50"):
        _bundled, own = blank_source(code)
        assert own is False

    mine = tmp_path / "yangi.pdf"
    doc = fitz.open()
    doc.new_page(width=263.04, height=370.32).insert_text(
        (30, 300), "YANGI BEYDJIK", fontsize=9)
    doc.save(str(mine))
    doc.close()

    saved = import_blank("77", mine)
    assert saved == user_blank_path("77")

    used, own = blank_source("77")
    assert own is True and used == saved
    # …and the other region is untouched
    assert blank_source("50")[1] is False

    assert "YANGI BEYDJIK" in _flat(_make(svc, region="77").pdf_path)
    assert "YANGI BEYDJIK" not in _flat(
        _make(svc, region="50", dolzhnost="Водитель").pdf_path)


def test_the_blanks_live_outside_the_program_folder() -> None:
    from src.services.beydjik_service import user_blank_path

    own = user_blank_path("77")
    assert paths.data_dir() in own.parents
    assert paths.app_root() not in own.parents


def test_an_a4_sheet_is_refused_as_a_badge_blank(tmp_path) -> None:
    from src.common.errors import OfisError
    from src.services.beydjik_service import import_blank

    a4 = tmp_path / "a4.pdf"
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    doc.save(str(a4))
    doc.close()
    with pytest.raises(OfisError):
        import_blank("77", a4)


def test_an_unreadable_blank_is_refused(tmp_path) -> None:
    from src.common.errors import OfisError
    from src.services.beydjik_service import import_blank

    junk = tmp_path / "junk.pdf"
    junk.write_bytes(b"not a pdf")
    with pytest.raises(OfisError):
        import_blank("77", junk)


def test_the_bundled_blanks_carry_no_previous_worker() -> None:
    """The office's sample data was stripped when the blanks were made."""
    from src.services.beydjik_service import blank_source

    for code in ("77", "50"):
        blank, _ = blank_source(code)
        flat = " ".join(fitz.open(blank)[0].get_text().split())
        assert "Болтазода" not in flat
        assert "4476661" not in flat.replace(" ", "")
        # …but the card itself is intact
        assert "Гражданство" in flat and "Документ удост.личность/ИНН" in flat


# ------------------------------------------------------------- the photo


def test_the_photo_fills_the_frame_edge_to_edge(svc, tmp_path) -> None:
    from src.services.beydjik_service import PHOTO_BOX

    photo = tmp_path / "ishchi.png"
    doc = fitz.open()
    page = doc.new_page(width=300, height=300)
    page.draw_rect(fitz.Rect(0, 0, 300, 300), color=None, fill=(0.1, 0.2, 0.9))
    page.get_pixmap(dpi=72).save(str(photo))
    doc.close()

    r = _make(svc, photo_path=photo)
    placed = fitz.open(r.pdf_path)[0].get_image_info()
    frame = fitz.Rect(*PHOTO_BOX)
    assert any(abs(im["bbox"][0] - frame.x0) < 1.0
               and abs(im["bbox"][1] - frame.y0) < 1.0
               and abs(im["bbox"][2] - frame.x1) < 1.0
               and abs(im["bbox"][3] - frame.y1) < 1.0
               for im in placed), placed


def test_a_missing_photo_leaves_the_frame_empty(svc) -> None:
    """The badge is still produced — the operator can glue a photo in."""
    r = _make(svc, photo_path=None)
    assert r.pdf_path.exists()
    assert "Болтазода" in _flat(r.pdf_path)


# ------------------------------------------------- the remote front ends


def test_the_module_is_offered_to_the_bot_and_mini_app() -> None:
    from src.controllers.ofis_modules import MODULES

    module = next(m for m in MODULES if m.key == "beydjik")
    assert module.min_photos == 2
    assert [a.field for a in module.asks] == [
        "region", "personal_number", "inn", "firm", "dolzhnost", "issue_date"]
