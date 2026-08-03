"""КАРТА ИНОСТРАННОГО ГРАЖДАНИНА — the foreigner's card."""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import fitz
import pytest
from src.config import paths
from src.pdf.karta_renderer import (
    KartaData,
    mrz,
    output_name,
    plus_years,
    qr_payload,
    render,
    values,
)
from src.pdf.karta_spec import PHOTO_BOX, QR_BOX, SLOTS


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    sandbox = tempfile.mkdtemp()
    monkeypatch.setenv("XDG_DATA_HOME", sandbox)
    monkeypatch.setenv("LOCALAPPDATA", sandbox)
    paths.data_dir.cache_clear()
    yield
    paths.data_dir.cache_clear()


_WORKER = dict(
    surname="МАМАТОВ", name="ФАЙЗУЛЛОХОН", patronymic="МАМАТОВИЧ",
    gender="male", citizenship="УЗБЕКИСТАН", birth_date=date(1975, 4, 15),
    issued=date(2026, 5, 20), expiry=date(2031, 5, 20),
    card_code="AA5675223", serial="964390", card_number="70029807586",
    series="0077")


def _blank(folder: Path, name: str) -> Path:
    from PIL import Image

    blank = folder / f"{name}.png"
    Image.new("RGB", (1683, 1058), (250, 250, 250)).save(blank)
    return blank


def test_the_card_runs_five_full_years() -> None:
    assert plus_years(date(2026, 5, 10)) == date(2031, 5, 10)
    assert plus_years(date(2028, 2, 29)) == date(2033, 2, 28)


def test_the_values_read_like_the_sample_card() -> None:
    made = values(KartaData(**_WORKER))
    assert made["fio_surname"] == "МАМАТОВ"
    assert made["fio_rest"] == "ФАЙЗУЛЛОХОН МАМАТОВИЧ"
    assert made["birth_date"] == "15.04.1975"
    assert made["gender"] == "М"
    assert made["citizenship"] == "УЗБЕКИСТАН"
    assert made["card_region"] == "77"
    assert made["card_number"] == "70029807586"
    assert made["card_series"] == "06/30 0077"
    assert made["expiry"] == "20.05.2031"
    assert made["back_number"] == "AA5675223"


def test_the_machine_zone_follows_the_sample() -> None:
    """The sample card's own check digits are hand-typed and do not add up,
    so the program keeps the ICAO arithmetic — every other position is the
    sample's, character for character."""
    line1, line2, line3 = mrz(KartaData(**_WORKER))
    assert line1.startswith("I<MOSAA567522370029807586")
    assert len(line1) == len(line2) == len(line3) == 30
    assert line2[:6] == "750415"          # birth, as the sample
    assert line2[7] == "M"                # sex
    assert line2[8:14] == "310520"        # expiry
    assert line2[15:18] == "UZB"          # nationality
    assert line2[6].isdigit() and line2[14].isdigit()   # ICAO check digits
    assert line3.startswith("MAMATOV<FAYZULLOKHON")


def test_a_woman_is_marked_female_everywhere() -> None:
    data = KartaData(**{**_WORKER, "gender": "female"})
    assert values(data)["gender"] == "Ж"
    assert "F" in mrz(data)[1]
    assert "ПОЛ: Ж" in qr_payload(data)


def test_the_qr_carries_the_owners_own_wording() -> None:
    text = qr_payload(KartaData(**_WORKER))
    assert text.splitlines() == [
        "ФИО: МАМАТОВ ФАЙЗУЛЛОХОН МАМАТОВИЧ",
        "ДАТА РОЖДЕНИЯ: 15.04.1975",
        "ПОЛ: М",
        "ГРАЖДАНСТВО: УЗБЕКИСТАН",
        "НОМЕР КАРТИ: 77 70029807586",
        "ДАТА ОКОНЧАНИЯ СРОКА: 20.05.2031",
    ]


def test_the_machine_zone_fills_the_cards_whole_band(tmp_path) -> None:
    """The office marked both edges: under the photo frame's left corner
    and level with the expiry date. Normal spacing, the sample's letter
    size, chevrons filling whatever is left."""
    from src.pdf.karta_spec import MRZ_LEFT, MRZ_RIGHT, MRZ_SIZE

    pdf = render(KartaData(**_WORKER), _blank(tmp_path, "inner"))
    with fitz.open("pdf", pdf) as doc:
        page = doc[0]
        wide, tall = page.rect.width, page.rect.height
        lines = [s for b in page.get_text("dict")["blocks"]
                 for line in b.get("lines", []) for s in line["spans"]
                 if "<" in s["text"]]
    assert len(lines) == 3, "the three machine lines are not there"
    for span in lines:
        starts = span["bbox"][0] / wide
        ends = span["bbox"][2] / wide
        assert abs(starts - MRZ_LEFT) < 0.005, f"starts at {starts:.4f}"
        assert MRZ_RIGHT - ends < 0.025, f"stops short at {ends:.4f}"
        assert ends <= MRZ_RIGHT + 0.002, f"runs past at {ends:.4f}"
        assert abs(span["size"] / tall - MRZ_SIZE) < 0.001
        assert span["text"].count("<") > 5, "no chevrons were added"


def test_a_saved_layout_never_shortens_the_machine_zone(tmp_path) -> None:
    """The office had already arranged the card — a saved x or size for a
    machine line must not shrink the strip; it is one fixed band."""
    from src.pdf.karta_spec import MRZ_LEFT, MRZ_RIGHT

    layout = {"fields": {"mrz1": [0.1700, 0.7155, 0.0450],
                         "mrz2": [0.1700, 0.7684, 0.0450],
                         "mrz3": [0.1700, 0.8214, 0.0450]}}
    pdf = render(KartaData(**_WORKER, layout=layout),
                 _blank(tmp_path, "inner"))
    with fitz.open("pdf", pdf) as doc:
        page = doc[0]
        wide = page.rect.width
        lines = [s for b in page.get_text("dict")["blocks"]
                 for line in b.get("lines", []) for s in line["spans"]
                 if "<" in s["text"]]
    assert len(lines) == 3
    for span in lines:
        assert abs(span["bbox"][0] / wide - MRZ_LEFT) < 0.005
        assert MRZ_RIGHT - span["bbox"][2] / wide < 0.025


def test_the_check_digit_stays_last_after_the_filling() -> None:
    from src.pdf.karta_renderer import fill_to_width

    class _Measure:
        @staticmethod
        def text_length(text, size):
            return len(text) * 10.0

    made = fill_to_width("7504150M3105205UZB", 300.0, _Measure(), 1.0,
                         tail="6")
    assert made.endswith("6"), "the check digit was buried in the chevrons"
    assert made.startswith("7504150M3105205UZB<")
    assert len(made) == 30


def test_the_machine_zone_is_set_in_franklin_gothic() -> None:
    import os

    from src.pdf.engine import _font_file
    from src.pdf.karta_spec import FONT_MRZ

    assert FONT_MRZ == "OfisFranklin"
    if os.name == "nt":
        assert _font_file(FONT_MRZ).name.upper() == "FRABK.TTF"


def test_render_puts_the_qr_photo_and_both_sides(tmp_path) -> None:
    import cv2
    import numpy as np
    from PIL import Image

    photo = tmp_path / "photo.png"
    Image.new("RGB", (300, 400), (200, 40, 40)).save(photo)
    data = KartaData(**_WORKER, photo_png=photo.read_bytes())
    pdf = render(data, _blank(tmp_path, "inner"), _blank(tmp_path, "outer"))
    with fitz.open("pdf", pdf) as doc:
        assert doc.page_count == 2
        ink = "".join(p.get_text() for p in doc).replace("\xa0", " ")
        assert "МАМАТОВ" in ink and "06/30 0077" in ink
        # the machine zone is stepped glyph by glyph so it fills the
        # card's whole band — extraction sees the spacing, so compare
        # without it
        assert "I<MOSAA5675223" in "".join(ink.split())
        assert "AA5675223" in doc[1].get_text()      # the outer side
        assert len(doc[0].get_images(full=True)) >= 2  # photo + QR
        pix = doc[0].get_pixmap(dpi=150)
        img = np.frombuffer(pix.samples, np.uint8).reshape(
            pix.height, pix.width, pix.n)[:, :, :3]

    x0, y0, x1, y1 = QR_BOX
    crop = np.ascontiguousarray(img[int(y0 * pix.height):int(y1 * pix.height),
                                    int(x0 * pix.width):int(x1 * pix.width)])
    decoded, _pts, _ = cv2.QRCodeDetector().detectAndDecode(crop)
    assert decoded == qr_payload(data), "the QR does not read back"

    fx0, fy0, fx1, fy1 = PHOTO_BOX
    spot = img[int((fy0 + fy1) / 2 * pix.height),
               int((fx0 + fx1) / 2 * pix.width)]
    assert spot[0] > 150 and spot[1] < 120, "the photo is not in its frame"


def test_the_numbers_count_up_by_themselves(tmp_path) -> None:
    from src.app import build_container
    from src.config.settings_service import SettingsService
    from src.services.karta_service import KartaService

    service = KartaService(build_container().resolve(SettingsService))
    service.set_blank("inner", _blank(tmp_path, "inner"))
    first = service.next_numbers()
    assert first == {"serial": "964390", "card_number": "70029807586",
                     "series": "0077"}
    service.generate(KartaData(**{**_WORKER, "serial": "", "card_number": "",
                                  "series": ""}))
    second = service.next_numbers()
    assert second["serial"] == "964391"
    assert second["card_number"] == "70029807587"
    assert second["series"] == "0078"


def test_colour_and_weight_travel_in_the_layout(tmp_path) -> None:
    from src.pdf.karta_renderer import placed
    from src.services.karta_service import KartaService

    service = KartaService()
    service.set_blank("inner", _blank(tmp_path, "inner"))
    assert SLOTS["fio_surname"].bold is True
    service.save_layout({"styles": {"fio_surname": {
        "colour": [1.0, 0.0, 0.0], "bold": False}}})
    slot = placed(service.layout())["fio_surname"]
    assert slot.colour == (1.0, 0.0, 0.0) and slot.bold is False


def test_the_bot_needs_a_blank_first() -> None:
    from src.controllers.ofis_modules import BY_KEY

    module = BY_KEY["karta"]
    assert module.photo_labels == ("Паспорт", "Ишчи расми")
    assert [a.field for a in module.asks] == ["issued", "card_code"]

    class _Ctl:
        @staticmethod
        def blank(side):
            return None

    assert "бланкаси йўқ" in module.ready({"karta": _Ctl()})


def test_the_filename_is_surname_name() -> None:
    assert output_name(KartaData(**_WORKER)) == "МАМАТОВ_ФАЙЗУЛЛОХОН.pdf"
