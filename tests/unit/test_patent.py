"""ПАТЕНТ — the badge, printed on the patent blanks instead.

The office asked for this section to be one-to-one with БЕЙДЖИК, so most of
what is worth testing is that it really is the badge: the tests below check the
two things that differ (two pages instead of one, and where the file lands) and
then check that the card still says everything a badge says.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz")

from src.common.errors import OfisError  # noqa: E402
from src.domain.documents import Passport  # noqa: E402
from src.services import beydjik_service as badge  # noqa: E402
from src.services import patent_service  # noqa: E402
from src.services.patent_service import PatentService  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
BLANKS = ROOT / "templates" / "patent"

pytestmark = pytest.mark.skipif(
    not (BLANKS / "77" / "front.pdf").exists(), reason="патент бланкалари йўқ")

PASSPORT = Passport(surname="ТОШПУЛАТОВ", name="ХУДОЙБЕРДИ",
                    patronymic="МУРОДОВИЧ", nationality="УЗБЕКИСТАН",
                    birth_date=date(1996, 4, 8), series="FB",
                    number="2582213", issued_by="МВД 22220")


class _Settings(dict):
    def get(self, key, default=None):
        return dict.get(self, key, default)

    def set(self, key, value):
        self[key] = value


def _service() -> PatentService:
    return PatentService(_Settings({"beydjik.pr_next": "1234567"}))


def _make(tmp_path: Path, region: str = "77", **over):
    fields = dict(region=region, personal_number="2600586935",
                  inn="772365215425", issue_date=date(2026, 7, 17),
                  firm="ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ ТРИУМФ",
                  dolzhnost="ПОДСОБНЫЙ РАБОЧИЙ", output_dir=tmp_path)
    fields.update(over)
    return _service().generate(PASSPORT, **fields)


def _text(path: Path) -> str:
    doc = fitz.open(str(path))
    return "\n".join(" ".join(page.get_text().split()) for page in doc)


# ------------------------------------------------- what makes it a patent


def test_the_card_is_one_pdf_front_then_back(tmp_path) -> None:
    """«олди орқани битта пдфга 1 2 саҳифа қилиб»."""
    doc = fitz.open(str(_make(tmp_path).pdf_path))
    assert len(doc) == 2
    assert doc[0].rect.width > doc[0].rect.height, "карта кўндаланг"
    front, back = doc[0].get_text(), doc[1].get_text()
    assert "Фамилия" in front or doc[0].get_images()
    assert "Дата выдачи" in back or doc[1].get_images()


def test_the_file_is_filed_under_the_worker_surname(tmp_path) -> None:
    assert _make(tmp_path).pdf_path.name == "ТОШПУЛАТОВ.pdf"


def test_a_card_already_there_is_never_overwritten(tmp_path) -> None:
    first = _make(tmp_path).pdf_path
    second = _make(tmp_path).pdf_path
    assert first.name == "ТОШПУЛАТОВ.pdf"
    assert second.name == "ТОШПУЛАТОВ (2).pdf"
    assert first.exists() and second.exists()


def test_the_photograph_is_laid_on_at_nine_parts_in_ten() -> None:
    assert pytest.approx(0.90) == patent_service.PHOTO_OPACITY


def test_the_frame_is_three_by_four() -> None:
    x0, y0, x1, y1 = patent_service.PHOTO_BOX
    assert abs((x1 - x0) / (y1 - y0) - 0.75) < 0.01


# --------------------------------------------- and it is still the badge


def test_it_is_the_badge(tmp_path) -> None:
    """Not a copy of it — the badge's own service, with other blanks."""
    assert issubclass(PatentService, badge.BeydjikService)


def test_both_regions_are_offered() -> None:
    assert set(badge.REGIONS) == {"77", "50"}
    for region in badge.REGIONS:
        for side in patent_service.SIDES:
            assert patent_service.bundled_blank(region, side).exists(), \
                (region, side)


@pytest.mark.parametrize("region, expected", [
    ("77", "г. Москва"),
    ("50", "Московская область"),
])
def test_each_region_names_its_own_territory(region, expected, tmp_path) -> None:
    assert expected in _text(_make(tmp_path, region=region).pdf_path)


def test_the_card_carries_the_worker(tmp_path) -> None:
    body = _text(_make(tmp_path).pdf_path)
    for value in ("Тошпулатов", "Худойберди", "Муродович", "08.04.1996",
                  "Узбекистан", "FB2582213", "772365215425", "2600586935"):
        assert value in body, value


def test_the_serial_steps_by_one(tmp_path) -> None:
    """The badge's own ПР numbering, shared with it."""
    service = _service()
    first = service.generate(PASSPORT, region="77",
                             personal_number="2600586935", inn="",
                             issue_date=date(2026, 7, 17), firm="ООО СФЕРА",
                             output_dir=tmp_path)
    second = service.generate(PASSPORT, region="77",
                              personal_number="2600586936", inn="",
                              issue_date=date(2026, 7, 17), firm="ООО СФЕРА",
                              output_dir=tmp_path)
    assert int(second.pr_number) == int(first.pr_number) + 1


def test_only_the_region_blank_carries_a_profession(tmp_path) -> None:
    """50 prints «Профессия», 77 does not — as on the office's own blanks."""
    assert "ПОДСОБНЫЙ РАБОЧИЙ" in _text(_make(tmp_path, region="50").pdf_path)
    assert "ПОДСОБНЫЙ РАБОЧИЙ" not in _text(_make(tmp_path, region="77").pdf_path)


# ------------------------------------------------------------- refusals


def test_a_card_is_not_made_without_a_personal_number(tmp_path) -> None:
    with pytest.raises(OfisError):
        _make(tmp_path, personal_number="")


def test_a_card_is_not_made_for_an_unknown_region(tmp_path) -> None:
    with pytest.raises(OfisError):
        _make(tmp_path, region="99")


def test_an_uploaded_blank_has_to_be_a_card(tmp_path) -> None:
    """A portrait page is not one side of a card."""
    doc = fitz.open()
    doc.new_page(width=300, height=800)
    tall = tmp_path / "tall.pdf"
    doc.save(str(tall))
    with pytest.raises(OfisError):
        patent_service.import_blank("77", "front", tall)


def test_an_uploaded_blank_is_used_instead(tmp_path, monkeypatch) -> None:
    """«кейинчалик бу шаблонни ҳам фонини ўзгартириб юклашим мумкин»."""
    store = tmp_path / "appdata"
    monkeypatch.setattr(patent_service.paths, "user_templates_dir",
                        lambda: store)
    assert patent_service.blank_source("77", "front")[1] is False
    patent_service.import_blank("77", "front", BLANKS / "50" / "front.pdf")
    used, own = patent_service.blank_source("77", "front")
    assert own is True
    assert used == store / "patent" / "77" / "front.pdf"
