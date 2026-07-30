"""МИГ — the «ИШЧИ КАРТАСИ» the office prints for each of its firms.

Offline: no AI, no network. What is checked is the deterministic half — how a
name is spaced out across the card, which box the X goes in, which job gets a
line under it, and that a firm's blank and its stamp (with the place the mouse
put it) survive being put away and fetched again.
"""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

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


def _blank(path: Path, width: float = 595.0, height: float = 842.0) -> Path:
    doc = fitz.open()
    doc.new_page(width=width, height=height)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))
    return path


def _stamp(path: Path) -> Path:
    doc = fitz.open()
    page = doc.new_page(width=120, height=120)
    page.draw_circle((60, 60), 55, color=(0.1, 0.2, 0.7), width=3)
    path.parent.mkdir(parents=True, exist_ok=True)
    page.get_pixmap().save(str(path))
    doc.close()
    return path


def _plain(text: str) -> str:
    """MuPDF spells a drawn space U+00A0; fold it back to what was printed."""
    return text.replace("\xa0", " ")


# ------------------------------------------------------- how it is typed


def test_a_name_is_typed_a_letter_to_a_box() -> None:
    from src.pdf.mig_renderer import digits_spaced, spaced

    assert spaced("ЖАХОНГИРОВА") == "Ж А Х О Н Г И Р О В А"
    # two words keep a WIDER gap between them, as «РАХИМ  КИЗИ» does
    assert spaced("РАХИМ КИЗИ") == "Р А Х И М   К И З И"
    assert spaced("") == ""
    assert digits_spaced("13.08.2009") == "1 3   0 8   2 0 0 9"
    assert digits_spaced("FB2376204") == "F B 2 3 7 6 2 0 4"


def test_the_latin_line_is_spelled_the_way_the_passport_spells_it() -> None:
    """«ЖАХОНГИРОВА» is «JAKHONGIROVA» on the office's card — a plain J."""
    from src.pdf.mig_renderer import to_latin

    assert to_latin("ЖАХОНГИРОВА") == "JAKHONGIROVA"
    assert to_latin("ХОЛМУРОДОВА") == "KHOLMURODOVA"
    assert to_latin("") == ""


def test_the_x_goes_in_the_box_the_passport_says() -> None:
    from src.pdf.mig_renderer import _sex_key

    assert _sex_key("Женский") == "female"
    assert _sex_key("Мужской") == "male"
    assert _sex_key("F") == "female"
    assert _sex_key("м") == "male"
    assert _sex_key("") == ""
    assert _sex_key("не указан") == ""


# ---------------------------------------------------------- the card


def _card(tmp_path, **over):
    from src.pdf.mig_renderer import MigData, render

    fields = {
        "series": "46 26", "number": "0367598",
        "surname": "ЖАХОНГИРОВА", "name": "МЕХРАНГИЗБОНУ",
        "patronymic": "РАХИМ КИЗИ", "birth_date": date(2009, 8, 13),
        "citizenship": "УЗБЕКИСТАН", "passport": "FB2376204",
        "gender": "Женский", "visa": "АШХ23652",
        "valid_from": date(2026, 7, 20), "valid_to": date(2026, 10, 14),
        "issued_on": date(2026, 3, 15),
    }
    fields.update(over)
    pdf = render(MigData(**fields), _blank(tmp_path / "blank.pdf"))
    return fitz.open("pdf", pdf)[0]


def test_everything_the_card_says_lands_on_it(tmp_path) -> None:
    page = _card(tmp_path)
    text = _plain(page.get_text())

    assert "46 26" in text and "0367598" in text
    assert "Ж А Х О Н Г И Р О В А" in text
    assert "J A K H O N G I R O V A" in text
    assert "М Е Х Р А Н Г И З Б О Н У" in text
    assert "Р А Х И М   К И З И" in text
    assert "1 3   0 8   2 0 0 9" in text
    assert "У З Б Е К И С Т А Н" in text
    assert "F B 2 3 7 6 2 0 4" in text
    assert "АШХ23652" in text
    assert "20.07.2026" in text and "14.10.2026" in text
    # the day it was issued — pairs together, not letter-spaced
    assert "15 03 26" in text
    assert "X" in text


def test_the_issue_date_is_the_only_thing_in_blue(tmp_path) -> None:
    """The office stamps that one in blue; everything else is the typewriter."""
    page = _card(tmp_path)
    blue = [span for block in page.get_text("dict")["blocks"]
            if block["type"] == 0
            for line in block["lines"] for span in line["spans"]
            if span["color"] != 0x000000 and (span["color"] & 0xFF) > 0x80]
    assert [_plain(s["text"]).strip() for s in blue] == ["15 03 26"]


def test_only_the_ticked_job_is_underlined(tmp_path) -> None:
    from src.pdf.mig_spec import JOBS

    none_ticked = _card(tmp_path, jobs=())
    assert not none_ticked.get_drawings(), "nothing is ticked, nothing is drawn"

    one = _card(tmp_path, jobs=("uchenik",))
    lines = one.get_drawings()
    assert len(lines) == 1
    rule = next(r for key, _label, r in JOBS if key == "uchenik")
    drawn = lines[0]["rect"]
    assert abs(drawn.x0 / one.rect.width - rule.x0) < 0.01
    assert abs(drawn.x1 / one.rect.width - rule.x1) < 0.01
    assert abs(drawn.y0 / one.rect.height - rule.y) < 0.01

    two = _card(tmp_path, jobs=("kom", "chastniy"))
    assert len(two.get_drawings()) == 2


def test_a_worker_with_no_visa_leaves_that_line_empty(tmp_path) -> None:
    page = _card(tmp_path, visa="")
    assert "АШХ" not in _plain(page.get_text())


def test_nothing_of_the_blanks_own_words_is_reprinted(tmp_path) -> None:
    """Only the passport's data and what the office types goes on. Every other
    word — «ФАМИЛИЯ:», «МУЖ», «М.П.» — is already printed on the blank."""
    page = _card(tmp_path)
    text = _plain(page.get_text())
    for word in ("ФАМИЛИЯ", "ИШЧИ КАРТАСИ", "МУЖ", "ЖЕН", "М.П.",
                 "ТУГИЛГАН", "ГРАЖДАНСТВАСИ", "УЧЕНИК", "РАЗНОРАБОЧИЙ"):
        assert word not in text, f"«{word}» бланкада бор, қайта ёзилмаслиги керак"


# ------------------------------------------- the firm's blank and stamp


def test_every_firms_blank_and_stamp_are_kept(tmp_path) -> None:
    from src.services.mig_service import MigService

    service = MigService()
    assert service.templates() == [] and service.stamps() == []

    first = service.add_template("СФЕРА", _blank(tmp_path / "a.pdf"))
    second = service.add_template("ЭКСПЕРТ", _blank(tmp_path / "b.pdf"))
    assert sorted(p.stem for p in service.templates()) == ["СФЕРА", "ЭКСПЕРТ"]
    assert first.exists() and second.exists()

    service.add_stamp("СФЕРА", _stamp(tmp_path / "s1.png"))
    service.add_stamp("ЭКСПЕРТ", _stamp(tmp_path / "s2.png"))
    assert [s.name for s in service.stamps()] == ["СФЕРА", "ЭКСПЕРТ"]

    service.remove_template(first)
    assert [p.stem for p in service.templates()] == ["ЭКСПЕРТ"]


def test_where_the_mouse_put_a_stamp_is_remembered(tmp_path) -> None:
    """The office drags it once; every card for that firm has it there after."""
    from src.pdf.mig_spec import DEFAULT_STAMP
    from src.services.mig_service import MigService

    service = MigService()
    stamp = service.add_stamp("СФЕРА", _stamp(tmp_path / "s.png"))
    assert stamp.box == DEFAULT_STAMP

    service.place_stamp(stamp, (0.55, 0.70, 0.80, 0.92))
    # a NEW service object, as the next run of the program would be
    again = MigService().stamps()[0]
    assert again.box == (0.55, 0.70, 0.80, 0.92)

    # and the other firm's stamp is untouched by it
    other = service.add_stamp("ЭКСПЕРТ", _stamp(tmp_path / "s2.png"))
    assert other.box == DEFAULT_STAMP

    service.remove_stamp(again)
    assert [s.name for s in service.stamps()] == ["ЭКСПЕРТ"]


def test_a_stamp_off_the_page_is_refused(tmp_path) -> None:
    from src.common.errors import ValidationError
    from src.services.mig_service import MigService

    service = MigService()
    stamp = service.add_stamp("СФЕРА", _stamp(tmp_path / "s.png"))
    for bad in ((0.5, 0.5, 0.4, 0.9), (0.5, 0.5, 0.9, 1.4), (-0.1, 0.5, 0.9, 0.9)):
        with pytest.raises(ValidationError):
            service.place_stamp(stamp, bad)


def test_the_stamp_is_printed_where_it_was_put(tmp_path) -> None:
    from src.services.mig_service import MigService

    service = MigService()
    template = service.add_template("СФЕРА", _blank(tmp_path / "a.pdf"))
    stamp = service.add_stamp("СФЕРА", _stamp(tmp_path / "s.png"))
    service.place_stamp(stamp, (0.55, 0.70, 0.80, 0.92))
    placed = service.stamps()[0]

    result = service.generate(template=template, surname="ЖАХОНГИРОВА",
                              number="0367598", stamp=placed)
    page = fitz.open("pdf", result.pdf)[0]
    images = page.get_image_info()
    assert len(images) == 1, "the stamp did not reach the card"
    where = images[0]["bbox"]
    assert abs(where[0] / page.rect.width - 0.55) < 0.02
    assert abs(where[1] / page.rect.height - 0.70) < 0.02
    assert result.saved.exists() and result.png


def test_a_card_without_a_blank_says_which_one_is_missing() -> None:
    from src.common.errors import ValidationError
    from src.services.mig_service import MigService

    with pytest.raises(ValidationError, match="бланкаси юкланмаган"):
        MigService().generate(template=None, surname="ЖАХОНГИРОВА")
