"""КУК ПАТЕНТ — the card the office prints on its own two scans.

The map was measured off the blanks the office sent, which came back FILLED
and with a red rule drawn under every value that changes. What is checked
here is what the office asked for in so many words: the values land where
they belong, the picture fills its 3×4 window, the card's number moves on by
TWO for the next worker, and nothing the program adds is laid on at full
strength — «текстлар ва расм бироз хира, 85 % ли бўлсин».
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
from src.pdf.kukpatent_renderer import (
    KukPatentData,
    faded,
    firm_lines,
    output_stem,
    placed,
    placed_photo,
    render,
    values,
)
from src.pdf.kukpatent_spec import (
    BACK,
    FRONT,
    OPACITY,
    PAGE_H,
    PAGE_W,
    PHOTO_DEFAULT,
    PHOTO_KEY,
)
from src.services import kukpatent_service as store


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    sandbox = tempfile.mkdtemp()
    monkeypatch.setenv("XDG_DATA_HOME", sandbox)
    monkeypatch.setenv("LOCALAPPDATA", sandbox)
    paths.data_dir.cache_clear()
    yield
    paths.data_dir.cache_clear()


def _worker(**over) -> KukPatentData:
    made = KukPatentData(
        surname="Эргешов", name="Омурбек", patronymic="Куштарович",
        birth_date=date(1998, 6, 16), gender="М", citizenship="Киргизия",
        document="Иностранный паспорт ID3956001",
        series="88", number="3259366",
        firm='Общество с ограниченной ответственностью ООО "Сфера" отдел кадров',
        issued=date(2024, 9, 3), card_no="АА3915699")
    for key, value in over.items():
        setattr(made, key, value)
    return made


def _png(width: int = 300, height: int = 400) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), (200, 40, 40)).save(buf, "PNG")
    return buf.getvalue()


def _pdf(tmp_path: Path, name: str) -> Path:
    made = tmp_path / name
    with fitz.open() as doc:
        doc.new_page(width=PAGE_W, height=PAGE_H)
        doc.save(str(made))
    return made


def _printed(pdf: bytes) -> dict[str, tuple[float, float]]:
    found = {}
    with fitz.open("pdf", pdf) as doc:
        for block in doc[0].get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    text = " ".join(span["text"].split())
                    if text:
                        found[text] = (span["origin"][0] / PAGE_W,
                                       span["origin"][1] / PAGE_H)
    return found


# ------------------------------------------------------------ the sides
def test_the_front_names_the_worker_and_the_back_says_where_he_is_from(
) -> None:
    front = _printed(render(_worker(), FRONT))
    assert "Эргешов" in front and "Омурбек" in front
    assert "Куштарович" in front
    assert "16.06.1998" in front and "М" in front
    assert "88" in front and "3259366" in front

    back = _printed(render(_worker(), BACK))
    assert "Киргизия" in back
    assert "Иностранный паспорт ID3956001" in back
    assert "03.09.2024" in back and "АА3915699" in back
    # neither side carries the other's values
    assert "Киргизия" not in front and "Эргешов" not in back


@pytest.mark.parametrize("side", [FRONT, BACK])
def test_each_side_comes_out_the_size_of_the_office_blank(side) -> None:
    with fitz.open("pdf", render(_worker(), side)) as doc:
        assert doc.page_count == 1
        assert doc[0].rect.width == pytest.approx(PAGE_W)
        assert doc[0].rect.height == pytest.approx(PAGE_H)


def test_the_values_land_on_the_rules_the_office_drew() -> None:
    """Measured off its own filled sample — this keeps them there."""
    front = _printed(render(_worker(), FRONT))
    assert front["Эргешов"][0] == pytest.approx(0.5289, abs=0.002)
    assert front["Эргешов"][1] == pytest.approx(0.4895, abs=0.002)
    assert front["3259366"][0] == pytest.approx(0.5646, abs=0.002)
    back = _printed(render(_worker(), BACK))
    assert back["АА3915699"][1] == pytest.approx(0.6145, abs=0.002)


# ---------------------------------------------------------- the firm
def test_the_firm_breaks_across_the_two_lines_the_card_gives_it() -> None:
    first, second = firm_lines(
        'Общество с ограниченной ответственностью ООО "Сфера" отдел кадров')
    assert first == "Общество с ограниченной ответственностью ООО"
    assert second == '"Сфера" отдел кадров'


def test_the_office_may_break_the_firm_where_it_likes() -> None:
    assert firm_lines("ООО САТУРН\nотдел кадров") == ("ООО САТУРН",
                                                      "отдел кадров")


def test_a_short_firm_keeps_the_second_line_empty() -> None:
    assert firm_lines("ООО САТУРН") == ("ООО САТУРН", "")
    assert firm_lines("") == ("", "")


# --------------------------------------------------------- the picture
def test_the_picture_fills_the_window_the_blank_leaves_for_it() -> None:
    made = render(_worker(photo_png=_png()), FRONT)
    with fitz.open("pdf", made) as doc:
        boxes = [doc[0].get_image_bbox(i) for i in doc[0].get_images(full=True)]
    assert len(boxes) == 1, "расм тушмади"
    left, top, width, height = PHOTO_DEFAULT
    assert boxes[0].x0 == pytest.approx(left * PAGE_W, abs=1.0)
    assert boxes[0].y0 == pytest.approx(top * PAGE_H, abs=1.0)
    assert boxes[0].width == pytest.approx(width * PAGE_W, abs=1.0)
    assert boxes[0].height == pytest.approx(height * PAGE_H, abs=1.0)


def test_the_window_is_three_by_four() -> None:
    left, top, width, height = PHOTO_DEFAULT
    assert (width * PAGE_W) / (height * PAGE_H) == pytest.approx(0.75, abs=0.03)


def test_the_back_never_carries_the_picture() -> None:
    with fitz.open("pdf", render(_worker(photo_png=_png()), BACK)) as doc:
        assert not doc[0].get_images(full=True)


def test_the_picture_is_laid_on_at_eighty_five_percent() -> None:
    """«расм бироз хира, 85 % ли бўлсин» — over the blank, not on top of it."""
    from PIL import Image

    with Image.open(io.BytesIO(faded(_png()))) as shown:
        assert shown.mode == "RGBA"
        alpha = shown.getchannel("A").getextrema()
    assert alpha == (int(255 * OPACITY), int(255 * OPACITY))


def test_the_text_is_laid_on_at_eighty_five_percent_too() -> None:
    """A card's ink sits IN the paper; at full strength it reads as a sticker."""
    import inspect

    from src.pdf import kukpatent_renderer

    source = inspect.getsource(kukpatent_renderer._write)
    assert "fill_opacity=OPACITY" in source
    assert OPACITY == 0.85


# --------------------------------------------------------- the dragging
def test_a_dragged_value_moves_on_that_side_only() -> None:
    moved = {"fields": {BACK: {"issued": [0.30, 0.60, 0.02]}}}
    assert placed(BACK, moved)["issued"].x == pytest.approx(0.30)
    assert "issued" not in placed(FRONT, moved)


def test_the_office_may_restyle_a_value() -> None:
    styled = {"styles": {FRONT: {"surname": {
        "size": 0.03, "bold": False, "colour": [0.1, 0.2, 0.3],
        "font": "Arial"}}}}
    slot = placed(FRONT, styled)["surname"]
    assert slot.size == pytest.approx(0.03)
    assert slot.bold is False
    assert slot.family == "Arial"
    assert slot.colour == (0.1, 0.2, 0.3)


def test_the_picture_can_be_dragged_and_resized() -> None:
    moved = {"images": {FRONT: {PHOTO_KEY: [0.10, 0.20, 0.12, 0.30]}}}
    assert placed_photo(moved) == (0.10, 0.20, 0.12, 0.30)
    assert placed_photo({}) == PHOTO_DEFAULT


def test_the_editor_hands_the_picture_back_by_its_bottom() -> None:
    """The shared arranger works in «left, BOTTOM, height» — and the photo
    keeps its 3×4, so the width follows the height instead of being squashed."""
    left, top, width, height = placed_photo(
        {"images": {FRONT: {PHOTO_KEY: [0.20, 0.70, 0.30]}}})
    assert (left, height) == (0.20, 0.30)
    assert top == pytest.approx(0.40)
    assert (width * PAGE_W) / (height * PAGE_H) == pytest.approx(0.75, abs=0.01)


# ---------------------------------------------------------- the numbers
def test_the_card_number_moves_on_by_two() -> None:
    """«ҳар ишчида 2 рақамдан ўзгариб туради» — the office's own rule."""
    assert store.step_number("АА3915699") == "АА3915701"
    assert store.step_number("АА3915701") == "АА3915703"


def test_the_letters_and_the_width_of_the_number_are_kept() -> None:
    assert store.step_number("АА0000001") == "АА0000003"
    assert store.step_number("3915699") == "3915701"


def test_a_number_that_is_not_one_is_handed_back_untouched() -> None:
    """The office alone knows how its own series runs."""
    for said in ("", "   ", "АА-39/15", "бор"):
        assert store.step_number(said) == said.strip()


def test_the_next_worker_is_offered_the_next_number() -> None:
    assert store.next_number() == ""
    store.remember_number("АА3915699")
    assert store.next_number() == "АА3915701"


# ------------------------------------------------------------ the store
def test_each_side_keeps_its_own_blank(tmp_path) -> None:
    assert store.blanks() == {}
    store.set_blank(FRONT, _pdf(tmp_path, "one.pdf"))
    assert set(store.blanks()) == {FRONT}
    store.set_blank(BACK, _pdf(tmp_path, "two.pdf"))
    assert set(store.blanks()) == {FRONT, BACK}
    store.clear_blank(FRONT)
    assert set(store.blanks()) == {BACK}


def test_a_blank_that_is_not_one_is_refused(tmp_path) -> None:
    with pytest.raises(ValidationError, match="олди"):
        store.set_blank("yon", _pdf(tmp_path, "a.pdf"))
    with pytest.raises(ValidationError, match="топилмади"):
        store.set_blank(FRONT, tmp_path / "yoq.pdf")


def test_every_firm_typed_is_kept_for_next_time() -> None:
    assert store.firms() == []
    store.remember_firm("ООО САТУРН")
    store.remember_firm('ООО "Сфера" отдел кадров')
    assert store.firms()[0] == 'ООО "Сфера" отдел кадров'
    assert "ООО САТУРН" in store.firms()
    # typing one again moves it up, it does not double
    store.remember_firm("ООО САТУРН")
    assert store.firms()[0] == "ООО САТУРН"
    assert len(store.firms()) == 2
    store.forget_firm("ООО САТУРН")
    assert store.firms() == ['ООО "Сфера" отдел кадров']


# ----------------------------------------------------------- the making
def test_both_sides_come_out_as_one_document(tmp_path) -> None:
    """«олди орқани битта PDF га сақлаберадиган қил» — front first, back second."""
    store.set_blank(FRONT, _pdf(tmp_path, "f.pdf"))
    store.set_blank(BACK, _pdf(tmp_path, "b.pdf"))
    made = store.KukPatentService().generate(_worker(photo_png=_png()))
    assert made.pdf.name == "ЭРГЕШОВ_ОМУРБЕК.pdf"
    assert made.pdf.exists()
    with fitz.open(made.pdf) as doc:
        assert doc.page_count == 2, "иккита бет бўлиши керак"
        front = doc[0].get_text()
        back = doc[1].get_text()
    assert "Эргешов" in front and "Киргизия" not in front
    assert "АА3915699" in back and "Эргешов" not in back
    assert store.next_number() == "АА3915701"
    assert store.firms()[0] == _worker().firm


def test_nothing_prints_without_the_blanks_or_the_numbers(tmp_path) -> None:
    with pytest.raises(ValidationError, match="бланкаси юкланмаган"):
        store.KukPatentService().generate(_worker())
    store.set_blank(FRONT, _pdf(tmp_path, "f.pdf"))
    store.set_blank(BACK, _pdf(tmp_path, "b.pdf"))
    with pytest.raises(ValidationError, match="Серия ва номер"):
        store.KukPatentService().generate(_worker(series="", number=""))
    with pytest.raises(ValidationError, match="Фирма"):
        store.KukPatentService().generate(_worker(firm=""))
    with pytest.raises(ValidationError, match="Фамилия"):
        store.KukPatentService().generate(_worker(surname=""))


def test_the_next_worker_never_writes_over_the_last(tmp_path) -> None:
    store.set_blank(FRONT, _pdf(tmp_path, "f.pdf"))
    store.set_blank(BACK, _pdf(tmp_path, "b.pdf"))
    service = store.KukPatentService()
    first = service.generate(_worker())
    second = service.generate(_worker())
    assert first.pdf != second.pdf
    assert first.pdf.exists() and second.pdf.exists()


# ------------------------------------------------------- from a passport
def test_the_passport_gives_the_card_everything_it_can() -> None:
    from src.domain.documents import Passport
    from src.domain.enums import Gender

    passport = Passport(
        surname="ЭРГЕШОВ", name="ОМУРБЕК", patronymic="КУШТАРОВИЧ",
        series="ID", number="3956001", birth_date=date(1998, 6, 16),
        nationality="КИРГИЗИЯ", gender=Gender.MALE)
    data = store.data_of(passport, firm="ООО САТУРН", series="88",
                         number="3259366", issued=date(2024, 9, 3))
    assert data.surname == "Эргешов" and data.name == "Омурбек"
    assert data.citizenship == "Киргизия"
    assert data.document == "Иностранный паспорт ID3956001"
    assert data.gender == "М"
    assert data.birth_date == date(1998, 6, 16)


def test_the_file_is_named_by_the_worker() -> None:
    assert output_stem(_worker()) == "ЭРГЕШОВ_ОМУРБЕК"
    assert output_stem(KukPatentData()) == "KUKPATENT"
    # ...and by the side too, for a caller that wants them apart
    assert output_stem(_worker(), FRONT) == "ЭРГЕШОВ_ОМУРБЕК_oldi"
    assert output_stem(_worker(), BACK) == "ЭРГЕШОВ_ОМУРБЕК_orqa"


def test_the_numbers_the_office_typed_survive_the_program_closing() -> None:
    """«киритган номерларим майдонда доим турсин, ўзим ўзгартирмагунимча»."""
    assert store.typed() == {}
    store.remember_typed(series="88", number="3259366")
    assert store.typed() == {"series": "88", "number": "3259366"}
    # changing one leaves the other where it was
    store.remember_typed(number="3259400")
    assert store.typed() == {"series": "88", "number": "3259400"}


def test_printing_a_card_keeps_its_numbers_too(tmp_path) -> None:
    store.set_blank(FRONT, _pdf(tmp_path, "f.pdf"))
    store.set_blank(BACK, _pdf(tmp_path, "b.pdf"))
    store.KukPatentService().generate(_worker())
    assert store.typed() == {"series": "88", "number": "3259366"}


def test_a_worker_without_a_date_leaves_the_box_empty() -> None:
    written = values(_worker(issued=None, birth_date=None), BACK)
    assert written["issued"] == ""
    assert values(_worker(birth_date=None), FRONT)["birth_date"] == ""
