"""РАЗРЕШЕНИЯ — the work permit card the office prints for its own workers.

The card is a picture, so nothing about it can be checked by reading a template:
these tests render it and look at where the ink landed, which is the same thing
the operator will do when the card comes out of the printer.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz")

from src.common.errors import ValidationError  # noqa: E402
from src.pdf import razreshenie_spec as spec  # noqa: E402
from src.pdf.razreshenie_renderer import (  # noqa: E402
    RazreshenieData,
    cover_until,
    document_line,
    render,
)
from src.services.razreshenie_service import (  # noqa: E402
    DEFAULT_BACK,
    DEFAULT_NUMBER,
    RazreshenieService,
)

ROOT = Path(__file__).resolve().parents[2]
BLANKS = ROOT / "templates" / "razreshenie" / "standart"

pytestmark = pytest.mark.skipif(
    not (BLANKS / "front.pdf").exists(), reason="бланкалар йўқ")


class _Settings(dict):
    """The settings repository, as far as this section uses it."""

    def get(self, key):
        return dict.get(self, key)

    def set(self, key, value):
        self[key] = value


def _service() -> RazreshenieService:
    return RazreshenieService(_Settings())


def _data(**over) -> RazreshenieData:
    fields = dict(
        surname="Сейтимов", name="Гулхумар", patronymic="",
        birth_date=date(1976, 9, 1), citizenship="Туркменистан",
        document="A2311191", inn="", activity="Разнорабочий",
        valid_from=date(2026, 7, 17),
        firm_name='ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ТРИУМФ"',
        firm_inn="7730321507", seria="77", number="1354593",
        back_number="0035453")
    fields.update(over)
    return RazreshenieData(**fields)


def _pages(data: RazreshenieData):
    return fitz.open("pdf", render(data, BLANKS))


def _words(page) -> dict[str, tuple[float, float]]:
    """Every word the program wrote, by the bottom-left of its line box.

    The box's bottom sits a descender below the baseline, so a value set at
    23.5 pt reads about 5 pt low — the checks below allow for that rather than
    pretending the box bottom is the baseline.
    """
    return {w[4]: (w[0], w[3]) for w in page.get_text("words")}


def _on_line(page, baseline: float, slack: float = 9.0) -> str:
    """Everything printed on one line of the card, left to right."""
    words = [w for w in page.get_text("words") if abs(w[3] - baseline) < slack]
    return " ".join(w[4] for w in sorted(words, key=lambda w: w[0]))


# ------------------------------------------------------------- the dates


@pytest.mark.parametrize("start, end", [
    (date(2026, 7, 10), date(2027, 7, 9)),      # the office's own example
    (date(2026, 7, 17), date(2027, 7, 16)),     # …and its own card
    (date(2026, 1, 1), date(2026, 12, 31)),
    (date(2028, 2, 29), date(2029, 2, 28)),     # issued on a leap day
])
def test_the_permit_runs_a_year_to_the_day_before(start, end) -> None:
    assert cover_until(start) == end


@pytest.mark.parametrize("shouted, written", [
    ("САИДОВ", "Саидов"),
    ("САРДОР", "Сардор"),
    ("САИДОВИЧ", "Саидович"),
    ("ТАДЖИКИСТАН", "Таджикистан"),
    ("АБДУЛЛА-ЗОДА", "Абдулла-Зода"),      # a hyphen starts a word too
    ("Саидов", "Саидов"),                  # already written — left alone
    ("", ""),
])
def test_a_name_is_written_not_shouted(shouted, written) -> None:
    """«САИДОВ САРДОР» эмас, «Саидов Сардор» — the card writes names.

    A passport prints in capitals and the readers hand them over that way; the
    card does not.
    """
    from src.pdf.razreshenie_renderer import title_case

    assert title_case(shouted) == written


def test_the_card_carries_the_name_in_case() -> None:
    page = _pages(_data(surname="САИДОВ", name="САРДОР",
                        patronymic="САИДОВИЧ",
                        citizenship="ТАДЖИКИСТАН"))[0]
    words = _words(page)
    for written in ("Саидов", "Сардор", "Саидович", "Таджикистан"):
        assert written in words, written
    for shouted in ("САИДОВ", "САРДОР", "САИДОВИЧ", "ТАДЖИКИСТАН"):
        assert shouted not in words, shouted


def test_both_dates_are_printed_on_the_front() -> None:
    page = _pages(_data())[0]
    words = _words(page)
    assert "17.07.2026" in words
    assert "16.07.2027" in words


# ---------------------------------------------- the passport and the ИНН


@pytest.mark.parametrize("document, inn, expected", [
    ("A2311191", "772365215425", "A2311191 / 772365215425"),
    ("A2311191", "", "A2311191"),
    ("A2311191", "   ", "A2311191"),
    ("", "772365215425", "772365215425"),
])
def test_the_inn_rides_behind_the_passport(document, inn, expected) -> None:
    """«… / ИНН» is one field: with an ИНН it is joined, without it is not."""
    assert document_line(document, inn) == expected


def test_the_joined_document_is_what_the_card_carries() -> None:
    page = _pages(_data(inn="772365215425"))[0]
    assert _on_line(page, spec.FRONT["document"].baseline + 4.5) == \
        "A2311191 / 772365215425"


# ------------------------------------------------------------ the numbers


def test_each_worker_steps_both_numbers_by_one() -> None:
    service = _service()
    assert service.next_numbers() == ("77", DEFAULT_NUMBER, DEFAULT_BACK)
    service.remember_numbers("77", "1354593", "0035453")
    assert service.next_numbers() == ("77", "1354594", "0035454")
    service.remember_numbers("77", "1354594", "0035454")
    assert service.next_numbers() == ("77", "1354595", "0035455")


def test_the_back_number_keeps_its_leading_zeros() -> None:
    """«0035453» is seven boxes wide — «35454» would sit in the wrong ones."""
    service = _service()
    service.remember_numbers("77", "1", "0035453")
    assert service.next_numbers()[2] == "0035454"


def test_counting_goes_on_from_whatever_was_printed() -> None:
    """The operator may correct the number; the next one follows theirs."""
    service = _service()
    service.remember_numbers("50", "9000000", "0099998")
    assert service.next_numbers() == ("50", "9000001", "0099999")


def test_the_number_is_written_one_digit_per_box() -> None:
    """«ВВ 0035453» is a grid, not a word — one digit per box, evenly spaced."""
    page = _pages(_data())[1]
    digits = [w for w in page.get_text("words")
              if w[4].isdigit() and len(w[4]) == 1
              and abs(w[3] - (spec.NUMBER_BASELINE + spec.NUMBER_SIZE * 0.22)) < 12]
    assert "".join(w[4] for w in sorted(digits, key=lambda w: w[0])) == "0035453"
    lefts = sorted(w[0] for w in digits)
    gaps = [round(b - a, 1) for a, b in zip(lefts, lefts[1:], strict=False)]
    assert all(abs(g - spec.NUMBER_PITCH) < 1.0 for g in gaps), gaps


# -------------------------------------------------------------- the firm


def test_the_firm_stays_until_a_different_one_is_typed() -> None:
    service = _service()
    service.remember_firm('ООО "ТРИУМФ"', "7730321507")
    assert service.firm().name == 'ООО "ТРИУМФ"'
    assert service.firm().inn == "7730321507"


def test_the_firm_before_is_kept_in_the_list() -> None:
    """The office issues for several of its own companies and goes back."""
    service = _service()
    service.remember_firm('ООО "ТРИУМФ"', "7730321507")
    service.remember_firm('ООО "СФЕРА"', "7701234567")
    assert service.firm().name == 'ООО "СФЕРА"'
    assert [f.name for f in service.firms()] == ['ООО "СФЕРА"', 'ООО "ТРИУМФ"']


def test_the_same_firm_twice_is_listed_once() -> None:
    service = _service()
    for _ in range(3):
        service.remember_firm('ООО "ТРИУМФ"', "7730321507")
    assert len(service.firms()) == 1


def test_a_long_firm_name_is_set_smaller_rather_than_cut() -> None:
    """Two lines is all the card has; a name is never printed half-finished."""
    long_name = ("ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "
                 "«СТРОИТЕЛЬНО-МОНТАЖНОЕ УПРАВЛЕНИЕ НОМЕР ПЯТНАДЦАТЬ»")
    page = _pages(_data(firm_name=long_name))[1]
    printed = " ".join(w[4] for w in page.get_text("words")
                       if w[1] < spec.BACK["firm_inn"].baseline)
    # the font maps its hyphen to the soft one when the text is read back
    printed = printed.replace("\xad", "-")
    for word in long_name.split():
        assert word in printed, word


# --------------------------------------------------------- the whole card


def test_the_card_comes_out_front_then_back() -> None:
    doc = _pages(_data())
    assert len(doc) == 2
    assert "РАЗРЕШЕНИЕ" in doc[0].get_text() or doc[0].get_images()
    assert "Особые отметки" in doc[1].get_text() or doc[1].get_images()


def test_every_value_lands_where_the_office_prints_it() -> None:
    page = _pages(_data())[0]
    words = _words(page)
    for word, key in (("Сейтимов", "surname"), ("Гулхумар", "name"),
                      ("01.09.1976", "birth_date"),
                      ("Туркменистан", "citizenship"),
                      ("Разнорабочий", "activity"), ("1354593", "number")):
        assert word in words, word
        x, bottom = words[word]
        slot = spec.FRONT[key]
        assert abs(x - slot.x) < 2.0, (word, x, slot.x)
        # the box bottom is a descender below the baseline
        assert 0 <= bottom - slot.baseline < slot.size * 0.3, \
            (word, bottom, slot.baseline)


def test_the_photograph_fills_its_frame() -> None:
    """«расмини қирқиб рамкага 100 фоиз тўлиқ қўяди» — no green at the edges."""
    doc = fitz.open(str(BLANKS / "front.pdf"))
    photo = doc[0].get_pixmap(clip=fitz.Rect(500, 550, 700, 800),
                              dpi=72).tobytes("png")
    page = _pages(_data(photo=photo))[0]
    placed = [fitz.Rect(page.get_image_bbox(info)) for info in page.get_images(True)]
    frame = fitz.Rect(*spec.PHOTO_BOX)
    assert any(abs(r.x0 - frame.x0) < 2 and abs(r.y0 - frame.y0) < 2
               and abs(r.x1 - frame.x1) < 2 and abs(r.y1 - frame.y1) < 2
               for r in placed), placed


def test_the_frame_is_three_by_four() -> None:
    x0, y0, x1, y1 = spec.PHOTO_BOX
    assert abs((x1 - x0) / (y1 - y0) - 0.75) < 0.01


@pytest.mark.parametrize("size", [(1200, 600), (600, 1600), (600, 800),
                                  (1000, 1000)])
def test_a_photograph_is_cropped_to_the_frame_never_stretched(size) -> None:
    """Whatever shape it arrives in, the picture is trimmed — not squashed.

    Filling the window edge to edge is only safe because what reaches it is
    already 3 : 4; a face stretched to fit is worse than no card at all.
    """
    image = pytest.importorskip("PIL.Image")
    from io import BytesIO

    from src.pdf.razreshenie_renderer import _cover_crop

    buf = BytesIO()
    image.new("RGB", size, (200, 30, 30)).save(buf, format="PNG")
    out = image.open(BytesIO(_cover_crop(buf.getvalue(), 0.75)))
    assert abs(out.size[0] / out.size[1] - 0.75) < 0.01, out.size
    assert out.size[0] <= size[0] and out.size[1] <= size[1]


# ------------------------------------------------------------ refusals


@pytest.mark.parametrize("missing", ["surname", "activity", "firm_name"])
def test_the_card_is_not_printed_half_empty(missing) -> None:
    """A permit with no job on it, or no firm, is not a permit."""
    fields = dict(surname="Сейтимов", name="Гулхумар",
                  activity="Разнорабочий", valid_from=date(2026, 7, 17),
                  firm_name='ООО "ТРИУМФ"')
    fields[missing] = ""
    with pytest.raises(ValidationError):
        _service().generate(**fields)


def test_a_template_needs_both_of_its_sides(tmp_path) -> None:
    front = tmp_path / "front.pdf"
    front.write_bytes(b"%PDF-1.4\n")
    with pytest.raises(ValidationError):
        _service().add_template("test", front, tmp_path / "yoq.pdf")


def test_the_bundled_blank_is_offered() -> None:
    assert any(p.name == "standart" for p in _service().templates())


# --------------------------------------------------- where the card goes


def test_the_card_is_filed_under_the_worker_surname() -> None:
    result = _service().generate(
        surname="Сейтимов", name="Гулхумар", activity="Разнорабочий",
        valid_from=date(2026, 7, 17), firm_name='ООО "ТРИУМФ"')
    assert result.filename == "Сейтимов.pdf"


def test_a_card_already_on_the_desktop_is_never_overwritten(monkeypatch,
                                                            tmp_path) -> None:
    """Two workers can share a surname; the first card is not the program's
    to throw away."""
    from src.config import paths
    from src.services import razreshenie_service as service

    monkeypatch.setattr(paths, "desktop_dir", lambda: tmp_path)
    monkeypatch.setattr(service.paths, "desktop_dir", lambda: tmp_path)

    first = service.desktop_target("Сейтимов.pdf")
    first.write_bytes(b"%PDF-1.4\n")
    second = service.desktop_target("Сейтимов.pdf")
    assert second.name == "Сейтимов (2).pdf"
    second.write_bytes(b"%PDF-1.4\n")
    assert service.desktop_target("Сейтимов.pdf").name == "Сейтимов (3).pdf"


def test_the_photograph_is_laid_on_at_nine_parts_in_ten() -> None:
    """«100 эмас 90 қилиб» — the card shows through the picture a little."""
    image = pytest.importorskip("PIL.Image")
    from io import BytesIO

    from src.pdf.razreshenie_renderer import _soften

    assert pytest.approx(0.90) == spec.PHOTO_OPACITY
    buf = BytesIO()
    image.new("RGB", (60, 80), (200, 30, 30)).save(buf, format="PNG")
    out = image.open(BytesIO(_soften(buf.getvalue(), spec.PHOTO_OPACITY)))
    assert out.mode == "RGBA"
    assert out.getchannel("A").getextrema() == (230, 230)
