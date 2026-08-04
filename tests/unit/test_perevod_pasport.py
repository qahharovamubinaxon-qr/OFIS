"""ПЕРЕВОД — a passport is DRAWN, the way the office types it.

Every number in :mod:`src.pdf.perevod_pasport` was measured off the office's
own sheet, so what is checked here is that the drawing keeps landing where
that sheet has it — and that a card, which has one row more, still fits
between the same two rules.
"""

from __future__ import annotations

import fitz
import pytest
from src.pdf import perevod_pasport as sheet

FIELDS = [
    {"label": "Тип", "value": "P"},
    {"label": "Код государства", "value": "UZB"},
    {"label": "Номер паспорта", "value": "FB0701509"},
    {"label": "Фамилия", "value": "Жураева"},
    {"label": "Имя", "value": "Нафиса"},
    {"label": "Отчество", "value": "Абдуллаевна"},
    {"label": "Гражданство", "value": "Узбекистан"},
    {"label": "Дата рождения", "value": "28.05.1982"},
    {"label": "Место рождения", "value": "Сурхандарьинская область"},
    {"label": "Пол", "value": "женский"},
    {"label": "Дата выдачи", "value": "27.01.2025"},
    {"label": "Действителен до", "value": "26.01.2035"},
    {"label": "Орган, выдавший документ", "value": "МВД 22204"},
]


def _passport(**over) -> sheet.Facsimile:
    made = sheet.from_fields(FIELDS, lang="узбекского",
                            country="Республика Узбекистан", title="Паспорт")
    for key, value in over.items():
        setattr(made, key, value)
    return made


def _drawn(data: sheet.Facsimile):
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    sheet.draw(page, data)
    return page


def _plain(page) -> str:
    """The page as it reads: MuPDF gives spaces and hyphens its own way."""
    raw = page.get_text().replace("\xa0", " ").replace("\xad", "-")
    return " ".join(raw.split())


def _spans(page) -> list[dict]:
    found = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                span["text"] = " ".join(span["text"].split())
                found.append(span)
    return found


def _at(page, text: str) -> tuple[float, float]:
    """Where a line starts, in shares of the page."""
    for span in _spans(page):
        if span["text"] == text:
            return (span["origin"][0] / page.rect.width,
                    span["origin"][1] / page.rect.height)
    raise AssertionError(f"«{text}» варақда йўқ")


# --------------------------------------------------------------- reading
def test_the_reader_s_fields_land_in_the_right_boxes() -> None:
    made = _passport()
    assert made.surname == "ЖУРАЕВА" and made.name == "НАФИСА"
    assert made.patronymic == "АБДУЛЛАЕВНА"
    assert made.citizenship == "УЗБЕКИСТАН"
    assert made.birth_date == "28.05.1982"
    assert made.birth_place == "СУРХАНДАРЬИНСКАЯ ОБЛАСТЬ"
    assert made.sex == "Ж", "«женский» бир ҳарф бўлиб тушиши керак"
    assert made.issue_date == "27.01.2025" and made.expiry_date == "26.01.2035"
    assert made.authority == "МВД 22204"
    assert (made.kind, made.code, made.number) == ("P", "UZB", "FB0701509")
    assert made.country == "РЕСПУБЛИКА УЗБЕКИСТАН" and made.title == "ПАСПОРТ"


@pytest.mark.parametrize("label, key", [
    ("Дата рождения", "birth_date"), ("Место рождения", "birth_place"),
    ("Дата выдачи", "issue_date"), ("Действителен до", "expiry_date"),
    ("Дата окончания срока действия", "expiry_date"),
    ("Орган, выдавший документ", "authority"), ("Кем выдан", "authority"),
    ("ПИНФЛ", "personal_number"), ("Персональный номер", "personal_number"),
    ("Фамилия", "surname"), ("Имя", "name"), ("Отчество", "patronymic"),
])
def test_a_field_never_lands_in_a_neighbouring_box(label, key) -> None:
    assert sheet._slot_of(label) == key


def test_nothing_is_drawn_when_nothing_was_read() -> None:
    assert not sheet.is_drawable(sheet.from_fields(
        [], lang="узбекского", country="Узбекистан", title="Паспорт"))
    assert sheet.is_drawable(_passport())


# --------------------------------------------------------------- drawing
def test_the_sheet_carries_every_word_the_office_s_own_sheet_has() -> None:
    text = _plain(_drawn(_passport()))
    for word in ("Перевод ксерокопии с узбекского языка",
                 "РЕСПУБЛИКА УЗБЕКИСТАН/РЕСПУБЛИКА УЗБЕКИСТАН",
                 "ПАСПОРТ/", "ТИП/ТИП", "КОД СТРАНЫ/ КОДСТРАНЫ",
                 "НОМЕР ПАСПОРТА/НОМЕР ПАСПОРТА", "подпись владельца",
                 "(подпись)", "Личная", "Фотография", "ФАМИЛИЯ/ФАМИЛИЯ",
                 "ИМЯ/ИМЯ", "ОТЧЕСТВО/ОТЧЕСТВО", "ГРАЖДАНСТВО/ГРАЖДАНСТВО",
                 "ДАТА РОЖДЕНИЯ/ДАТАРОЖДЕНИЯ", "ПОЛ/ПОЛ",
                 "МЕСТО РОЖДЕНИЯ / МЕСТО РОЖДЕНИЯ",
                 "ДАТА ВЫДАЧИ / ДАТА ВЫДАЧИ",
                 "ДЕЙСТВИТЕЛЕН ДО/ДЕЙСТВИТЕЛЕН ДО",
                 "ОРГАН, ВЫДАВШИЙ ДОКУМЕНТ", "Машиносчитываемая запись"):
        assert word in text, f"«{word}» йўқ"
    for value in ("UZB", "FB0701509", "ЖУРАЕВА", "НАФИСА", "АБДУЛЛАЕВНА",
                  "УЗБЕКИСТАН", "28.05.1982", "Ж",
                  "СУРХАНДАРЬИНСКАЯ ОБЛАСТЬ", "27.01.2025", "26.01.2035",
                  "МВД 22204"):
        assert value in text, f"«{value}» йўқ"


def test_the_values_sit_where_the_office_s_sheet_has_them() -> None:
    page = _drawn(_passport())
    assert _at(page, "ЖУРАЕВА") == pytest.approx((sheet.DATA_X, 0.5610),
                                                 abs=0.002)
    assert _at(page, "НАФИСА") == pytest.approx((sheet.DATA_X, 0.5880),
                                                abs=0.002)
    assert _at(page, "26.01.2035") == pytest.approx((sheet.DATA_X, 0.7496),
                                                    abs=0.002)
    assert _at(page, "СУРХАНДАРЬИНСКАЯ ОБЛАСТЬ") == \
        pytest.approx((sheet.PLACE_X, 0.6957), abs=0.002)
    assert _at(page, "МВД 22204") == pytest.approx(
        (sheet.ORGAN_VALUE_X, 0.7480), abs=0.002)
    # everything the document says stays inside the frame the office drew
    for span in _spans(page):
        if span["text"] in ("ЖУРАЕВА", "26.01.2035", "МВД 22204"):
            assert sheet.BOX[1] < span["origin"][1] / page.rect.height \
                < sheet.BOX[3]


def test_the_frame_and_its_rules_are_drawn() -> None:
    page = _drawn(_passport())
    rects = [d["rect"] for d in page.get_drawings()]
    width, height = page.rect.width, page.rect.height
    frame = [r for r in rects
             if abs(r.x0 / width - sheet.BOX[0]) < 0.004
             and abs(r.y1 / height - sheet.BOX[3]) < 0.004]
    assert frame, "рамка чизилмаган"
    photo = [r for r in rects
             if abs(r.x0 / width - sheet.PHOTO[0]) < 0.004
             and abs(r.y0 / height - sheet.PHOTO[1]) < 0.004]
    assert photo, "расм катаги чизилмаган"
    rules = {round(r.y0 / height, 3) for r in rects
             if r.height < 2 and r.width > width * 0.4}
    for y in (sheet.DIV_STATE, sheet.DIV_HEAD, sheet.DIV_ROW, sheet.DIV_MRZ):
        assert any(abs(y - seen) < 0.004 for seen in rules), f"{y} чизиғи йўқ"


def test_the_punched_number_runs_down_the_side() -> None:
    page = _drawn(_passport())
    perf = [s for s in _spans(page) if s["text"] == "FB0701509"]
    assert len(perf) == 2, "рақам катакда ҳам, ён томонда ҳам бўлиши керак"
    side = max(perf, key=lambda s: s["origin"][0])
    assert side["origin"][0] / page.rect.width == \
        pytest.approx(sheet.PERF_X, abs=0.01)
    assert side["bbox"][3] - side["bbox"][1] > page.rect.height * 0.12


def test_stamps_are_set_under_the_frame_never_inside_it() -> None:
    data = _passport(stamps=["Штамп: Отдел внутренних дел города Ташкента"],
                     notes=["дата нечитаема"])
    page = _drawn(data)
    text = _plain(page)
    assert "Отдел внутренних дел города Ташкента" in text
    assert "Примечание переводчика: дата нечитаема" in text
    for span in _spans(page):
        if "Ташкента" in span["text"] or "Примечание" in span["text"]:
            assert span["origin"][1] / page.rect.height > sheet.BOX[3]


# ------------------------------------------------------------------ card
def test_a_card_gets_its_own_row_and_still_fits_the_frame() -> None:
    card = _passport(personal_number="31234567890123", number="AA1234567",
                     title="ID-КАРТА")
    assert card.is_card()
    rows = sheet.rows_of(card)
    assert len(rows) == len(sheet.ROWS) + 1
    assert rows[0][2] == sheet.ROWS[0][2] and rows[-1][2] == sheet.ROWS[-1][2]
    baselines = [round(value_y, 4) for _l, _k, _ly, value_y in rows]
    assert len(set(baselines)) == len(baselines), "иккита матн устма-уст"

    page = _drawn(card)
    text = _plain(page)
    assert "ПИНФЛ/ПИНФЛ" in text and "31234567890123" in text
    assert "НОМЕР ID-КАРТЫ/НОМЕР ID-КАРТЫ" in text
    for span in _spans(page):
        if span["text"] in ("31234567890123", "26.01.2035"):
            assert span["origin"][1] / page.rect.height < sheet.DIV_MRZ


def test_a_long_value_is_typed_smaller_never_past_the_frame() -> None:
    """A notarial sheet may not lose a letter — nor run off the box."""
    long = _passport(
        birth_place="КАШКАДАРЬИНСКАЯ ОБЛАСТЬ, КАРШИНСКИЙ РАЙОН, КИШЛАК ЯНГИОБОД",
        authority="ГУ МВД РОССИИ ПО МОСКОВСКОЙ ОБЛАСТИ",
        surname="АБДУРАХМАНОВ-ТУРСУНБАЕВ")
    page = _drawn(long)
    text = _plain(page)
    for whole in ("КАШКАДАРЬИНСКАЯ ОБЛАСТЬ, КАРШИНСКИЙ РАЙОН, КИШЛАК ЯНГИОБОД",
                  "ГУ МВД РОССИИ ПО МОСКОВСКОЙ ОБЛАСТИ",
                  "АБДУРАХМАНОВ-ТУРСУНБАЕВ"):
        assert whole in text, f"«{whole}» бутун ёзилмаган"
    over = [span["text"] for span in _spans(page)
            if span["origin"][1] / page.rect.height > sheet.DIV_ROW
            and span["bbox"][2] / page.rect.width > sheet.BOX[2] + 0.002]
    assert over == [], f"рамкадан чиқиб кетган: {over}"


def _tajik() -> sheet.Facsimile:
    return sheet.from_fields(
        [{"label": "Фамилия", "value": "Абдулхаков"},
         {"label": "Имя", "value": "Сунатулло"},
         {"label": "Номер паспорта", "value": "402543058"},
         {"label": "Гражданство", "value": "Таджикистан"},
         {"label": "Дата рождения", "value": "08.12.1990"},
         {"label": "Пол", "value": "мужской"},
         {"label": "Орган, выдавший документ", "value": "МВД 14505"},
         {"label": "Код государства", "value": "TJK"}],
        lang="таджикского", country="Республика Таджикистан",
        title="Паспорт")


def test_the_office_s_sheet_serves_uzbek_documents_only() -> None:
    """The office said it plainly: the uploaded pattern is the UZBEK
    passport's — other passports are shaped differently."""
    assert sheet.is_uzbek(_passport())
    assert not sheet.is_uzbek(_tajik())


def test_another_republic_s_passport_gets_its_own_data_page() -> None:
    """A Tajik passport is drawn as ITS OWN page, not as the Uzbek sheet."""
    tajik = _tajik()
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    sheet.draw_generic(page, tajik)
    text = _plain(page)
    assert "Перевод ксерокопии с таджикского языка" in text
    assert "РЕСПУБЛИКА ТАДЖИКИСТАН" in text
    assert "TJK" in text and "402543058" in text
    assert "МВД 14505" in text
    assert "ФАМИЛИЯ/SURNAME" in text and "АБДУЛХАКОВ" in text
    assert "Машиносчитываемая запись" in text
    # nothing of the Uzbek sheet's own furniture leaks in
    assert "подпись владельца" not in text
    assert "РЕСПУБЛИКА ТАДЖИКИСТАН/РЕСПУБЛИКА ТАДЖИКИСТАН" not in text
    # rows that are empty (отчество, ПИНФЛ) leave no orphan label behind
    assert "ОТЧЕСТВО" not in text and "ПЕРСОНАЛЬНЫЙ" not in text
    # and everything INSIDE the frame stays inside it (the «Перевод
    # ксерокопии…» heading stands above the frame, as on the office's sheet)
    over = [span["text"] for span in _spans(page)
            if sheet.G_BOX[1] < span["origin"][1] / page.rect.height
            < sheet.G_BOX[3]
            and span["bbox"][2] / page.rect.width > sheet.G_BOX[2] + 0.002]
    assert over == [], f"рамкадан чиқиб кетган: {over}"


def test_the_number_box_is_named_after_the_document() -> None:
    assert sheet.number_label("ПАСПОРТ") == "НОМЕР ПАСПОРТА"
    assert sheet.number_label("ID-КАРТА") == "НОМЕР ID-КАРТЫ"
    assert sheet.number_label("СПРАВКА") == "НОМЕР ДОКУМЕНТА"


def test_the_emblem_the_office_uploaded_is_put_at_the_head() -> None:
    doc = fitz.open()
    picture = fitz.open()
    page = picture.new_page(width=200, height=80)
    page.draw_rect(fitz.Rect(10, 10, 190, 70), color=(0, 0, 0))
    png = page.get_pixmap().tobytes("png")
    picture.close()

    sheet.draw(doc.new_page(width=595, height=842), _passport(emblem=png))
    images = doc[0].get_images()
    assert len(images) == 1
    box = doc[0].get_image_rects(images[0][0])[0]
    assert box.y1 / doc[0].rect.height < sheet.BIG_COUNTRY_Y
    assert box.x0 / doc[0].rect.width >= sheet.EMBLEM[0] - 0.01
