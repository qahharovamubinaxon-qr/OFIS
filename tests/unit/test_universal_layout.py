"""УНИВЕРСАЛ — ёнма-ён майдонлар устма-уст тушмаслиги ва узун матн қаторланиши.

Офис ФИО, туғилган сана ва жинсни бир қаторга ёнма-ён қўяди. Узун ФИО
қўшниларининг устига ёзиб юборарди; энди ҳар қиймат ўлчанади ва устига
тушадигани олдингиси тугаган жойдан бошланади. Узун матн эса «wrap» кенглиги
берилса, сўз чегарасидан бўлиниб 2-3 қаторга тушади.
"""

from __future__ import annotations

import fitz
import pytest

from src.pdf.trud8_fields import Field
from src.pdf.universal_renderer import _lines, flowed, text_width


@pytest.fixture
def page_doc():
    doc = fitz.open()
    doc.new_page(width=595, height=842)          # A4
    yield doc
    doc.close()


def _f(key, x, baseline=0.5, size=0.02, **kw):
    return Field(key=key, page=1, x=x, baseline=baseline, size=size, **kw)


def test_long_value_pushes_its_neighbour_right(page_doc):
    long_fio = "Абдурахмонов Шухратжон Бахтиёрович"
    items = [(1, _f("fio", 0.10), long_fio),
             (1, _f("birth", 0.30), "11.08.1994"),
             (1, _f("sex", 0.45), "Мужской")]
    out = {i.key: i for _, i, _ in flowed(page_doc, items)}
    page = page_doc[0]
    fio_end = 0.10 * page.rect.width + text_width(page, items[0][1], long_fio)
    assert out["birth"].x * page.rect.width >= fio_end, "birth must clear ФИО"
    assert out["sex"].x > 0.45, "sex must be pushed along too"


def test_short_value_leaves_neighbour_where_it_was(page_doc):
    items = [(1, _f("sex", 0.10), "М"),
             (1, _f("birth", 0.60), "11.08.1994")]
    out = {i.key: i for _, i, _ in flowed(page_doc, items)}
    assert out["birth"].x == pytest.approx(0.60), "no overlap → no move"


def test_values_on_different_lines_do_not_affect_each_other(page_doc):
    long_fio = "Абдурахмонов Шухратжон Бахтиёрович"
    items = [(1, _f("fio", 0.10, baseline=0.30), long_fio),
             (1, _f("birth", 0.30, baseline=0.70), "11.08.1994")]
    out = {i.key: i for _, i, _ in flowed(page_doc, items)}
    assert out["birth"].x == pytest.approx(0.30), "another line is untouched"


def test_turned_value_never_flows(page_doc):
    items = [(1, _f("fio", 0.10), "Абдурахмонов Шухратжон Бахтиёрович"),
             (1, _f("edge", 0.12, rotate=90), "МВД")]
    out = {i.key: i for _, i, _ in flowed(page_doc, items)}
    assert out["edge"].x == pytest.approx(0.12), "a turned value stays put"


def test_wrap_breaks_a_long_value_into_lines(page_doc):
    page = page_doc[0]
    item = _f("fio", 0.1, wrap=0.25)
    text = "Абдурахмонов Шухратжон Бахтиёрович"
    lines = _lines(page, item, text)
    assert len(lines) > 1, "a long ФИО must wrap"
    limit = item.wrap * page.rect.width
    for line in lines:
        assert text_width(page, item, line) <= limit + 0.5
    assert " ".join(lines).split() == text.split(), "no word is lost"


def test_without_wrap_the_value_stays_on_one_line(page_doc):
    page = page_doc[0]
    item = _f("fio", 0.1)                     # wrap = 0
    text = "Абдурахмонов Шухратжон Бахтиёрович"
    assert _lines(page, item, text) == [text]
