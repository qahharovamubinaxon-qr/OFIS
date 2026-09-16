"""УНИВЕРСАЛ — кириллча/лотинча ФИО танлови ва бир қийматни кўп марта қўйиш.

Офис бир бланкага ФИОни кириллча, бошқасига лотинча ёзишни сўради; ва битта
қиймат (ФИО, серия, протокол) бир бланканинг 2-3 жойига қўйилиши керак.
"""

from __future__ import annotations

from pathlib import Path

import fitz

from src.pdf.trud8_fields import Field
from src.pdf.universal_fields import CATALOGUE, SAMPLES, UniversalData, values
from src.pdf.universal_renderer import render


def _worker() -> UniversalData:
    return UniversalData(surname="Исоев", name="Аслидин",
                         patronymic="Холбердиевич")


def test_both_scripts_are_offered_in_the_picker():
    for key in ("fio", "surname", "name", "patronymic"):
        assert key in CATALOGUE, key
        assert f"{key}_latin" in CATALOGUE, f"{key}_latin"
    assert "лотин" in CATALOGUE["fio_latin"].lower()
    assert SAMPLES["fio_latin"] == "ISOEV ASLIDIN KHOLBERDIEVICH"


def test_latin_keys_transliterate_and_cyrillic_stays_cyrillic():
    got = values(_worker())
    assert got["fio"] == "Исоев Аслидин Холбердиевич"
    assert got["fio_latin"] == "ISOEV ASLIDIN KHOLBERDIEVICH"
    assert got["surname_latin"] == "ISOEV"
    assert got["patronymic_latin"] == "KHOLBERDIEVICH"


def test_one_value_may_be_placed_in_several_spots(tmp_path: Path):
    blank = tmp_path / "blank.pdf"
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    doc.save(str(blank))
    doc.close()

    # the same key three times, well apart so nothing flows into anything
    placed = [Field(key="fio", page=1, x=0.10, baseline=0.20, size=0.02),
              Field(key="fio", page=1, x=0.10, baseline=0.50, size=0.02),
              Field(key="fio", page=1, x=0.10, baseline=0.80, size=0.02)]
    pdf = render(_worker(), blank, placed)

    with fitz.open("pdf", pdf) as made:
        text = made[0].get_text()
    assert text.count("Исоев") == 3, "every placement must print the value"
