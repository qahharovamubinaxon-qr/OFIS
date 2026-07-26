"""Dover blank rendering: layout roles, counters block, blank backgrounds."""

from __future__ import annotations

from pathlib import Path

from src.pdf.dover_renderer import _classify, finalize_notarial_text, render_dover_pdf

_SAMPLE = """СОГЛАСИЕ
Город Москва.
Двадцать шестое июля две тысячи двадцать шестого года.

Я, гражданин Республики Таджикистан Тестов Тест Тестович, 01 января 1990 года рождения, паспорт 400000000, настоящим даю согласие на выезд.

Подпись: ________________________________________

Город Москва.
Двадцать шестое июля две тысячи двадцать шестого года.
Настоящее согласие удостоверено мной, Другановой Маргаритой Владимировной, нотариусом города Москвы.
Зарегистрировано в реестре: № ________
Уплачено по тарифу: ____ руб.
Нотариус: ________
"""


def test_finalize_replaces_reestr_block() -> None:
    final = finalize_notarial_text(_SAMPLE, reestr=12855, tarif="1500",
                                   notary_short="Друганова М.В.")
    assert "№ 12855" in final
    assert "1500 руб." in final
    assert final.count("Зарегистрировано в реестре") == 1
    assert final.count("по тарифу") == 1
    assert final.rstrip().endswith("Друганова М.В.")


def test_classify_roles() -> None:
    roles = _classify(_SAMPLE.splitlines())
    tagged = [(r, t) for r, t in roles if t]
    assert tagged[0] == ("title", "СОГЛАСИЕ")
    assert tagged[1][0] == "center"          # Город Москва.
    assert tagged[2][0] == "center"          # дата прописью
    assert any(r == "notary" for r, _ in tagged)
    # both «Город Москва.» occurrences centered (also in удостоверительная надпись)
    assert sum(1 for r, t in tagged if r == "center" and t.startswith("Город")) == 2


def test_render_pdf_with_series(tmp_path: Path) -> None:
    import fitz

    final = finalize_notarial_text(_SAMPLE, reestr=12855, tarif="1500",
                                   notary_short="Друганова М.В.")
    out = tmp_path / "dover.pdf"
    render_dover_pdf(final, out, series="77 АВ 2463964")
    doc = fitz.open(out)
    assert doc.page_count >= 1
    page_text = doc[0].get_text()
    assert "77 АВ 2463964" in page_text
    assert "СОГЛАСИЕ" in page_text
    full = "".join(p.get_text() for p in doc)
    assert "№ 12855" in full
    # blank background image present on page 1 (bundled scan)
    assert doc[0].get_images()
