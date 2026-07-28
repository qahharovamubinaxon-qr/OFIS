"""Swapping a value on a PDF, and proving the swap actually happened.

The complaint these tests exist for: sometimes a value was not written at all,
sometimes it landed in the wrong place, and sometimes the previous worker's
value was still there underneath. So nothing here trusts the writing — every
test reads the finished file back, exactly as the program itself now does.
"""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from src.pdf import rewrite
from src.pdf.engine import _font_file
from src.pdf.trud_editor import TrudDocEditor

OLD = {
    "surname": "Абдимуминов", "birth": "31.12.1993", "passport": "FA4956294",
    "issued": "08.02.2022", "profession": "Подсобный рабочий", "date": "01.01.2020",
}
CONTRACT = [
    (90, "ТРУДОВОЙ ДОГОВОР"),
    (120, OLD["date"]),
    (200, f"Работник: {OLD['surname']} Хусниддин Рашид,"),
    (218, f"Дата рождения {OLD['birth']} Гражданство Узбекистан"),
    (236, f"Иностранный паспорт Номер {OLD['passport']} Дата выдачи {OLD['issued']}"),
    (300, "1. ПРЕДМЕТ ДОГОВОРА"),
    (330, f"1.1. Работник принимается в должности: {OLD['profession']}"),
]


def _pdf(path: Path, rows: list[tuple[int, str]], *, size: float = 11.0) -> Path:
    """A contract page in the app's own Cyrillic face — as a real one is."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_font(fontname="F", fontfile=str(_font_file("OfisSansRegular")))
    for y, text in rows:
        page.insert_text((60, y), text, fontname="F", fontsize=size)
    doc.save(str(path))
    doc.close()
    return path


def _block(surname: str, name: str, birth: str, passport: str, issued: str,
           country: str = "Узбекистан") -> str:
    return (f"Работник: {surname} {name} Хаиталиевич, Дата рождения {birth} "
            f"Гражданство {country} Иностранный паспорт Номер {passport} "
            f"Дата выдачи {issued}")


# ------------------------------------------------------------ the primitives


def test_erasing_really_removes_the_text_not_just_covers_it(tmp_path) -> None:
    """A white rectangle leaves the old passport number in the file."""
    source = _pdf(tmp_path / "a.pdf", CONTRACT)
    doc = fitz.open(str(source))
    rewrite.erase(doc[0], [OLD["passport"]])
    out = tmp_path / "b.pdf"
    doc.save(str(out))
    doc.close()
    assert OLD["passport"] not in rewrite.read_text(out)


def test_a_value_that_is_not_there_is_not_an_error(tmp_path) -> None:
    doc = fitz.open(str(_pdf(tmp_path / "a.pdf", CONTRACT)))
    assert rewrite.erase(doc[0], ["НЕТ ТАКОГО"]) == 0
    doc.close()


def test_a_long_value_is_shrunk_until_it_fits(tmp_path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=300, height=200)
    name, font = rewrite.install_font(page)
    box = fitz.Rect(20, 50, 140, 66)
    used = rewrite.write(page, box, "Электрогазосварщик ручной сварки",
                         fontname=name, font=font, size=12.0)
    assert used < 12.0
    assert font.text_length("Электрогазосварщик ручной сварки",
                            fontsize=used) <= box.width
    doc.close()


def test_a_value_that_cannot_fit_is_written_and_reported(tmp_path) -> None:
    """Never trimmed in silence — the operator is told to look at it."""
    doc = fitz.open()
    page = doc.new_page(width=300, height=200)
    name, font = rewrite.install_font(page)
    report = rewrite.Report()
    rewrite.write(page, fitz.Rect(20, 50, 34, 66),
                  "Электрогазосварщик ручной сварки и резки металла",
                  fontname=name, font=font, size=11.0,
                  name="должность", report=report)
    out = tmp_path / "o.pdf"
    doc.save(str(out))
    doc.close()
    assert report.overflow == ["должность"]
    assert "Электрогазосварщик" in rewrite.read_text(out)


def test_a_value_the_pdf_spaced_out_is_still_found(tmp_path) -> None:
    out = _pdf(tmp_path / "a.pdf", [(100, "F A 4 9 5 6 2 9 4")])
    report = rewrite.verify(out, must_contain={"паспорт": "FA4956294"})
    assert report.ok, report.problems()


# --------------------------------------------------------------- the proving


def test_a_value_that_failed_to_land_is_named(tmp_path) -> None:
    out = _pdf(tmp_path / "a.pdf", CONTRACT)
    report = rewrite.verify(out, must_contain={"должность": "Штукатур",
                                               "дата": OLD["date"]})
    assert not report.ok
    assert report.missing == ["должность"]
    assert "«должность» ёзилмади" in report.problems()


def test_an_old_value_still_on_the_page_is_named(tmp_path) -> None:
    out = _pdf(tmp_path / "a.pdf", CONTRACT)
    report = rewrite.verify(out, must_contain={}, must_not_contain=[OLD["passport"]])
    assert report.left_over == [OLD["passport"]]


def test_a_value_both_workers_share_is_not_a_leftover(tmp_path) -> None:
    """Both are from Uzbekistan — that is not the old worker surviving."""
    out = _pdf(tmp_path / "a.pdf", [(100, "Гражданство Узбекистан")])
    report = rewrite.verify(out, must_contain={"блок": "Гражданство Узбекистан"},
                            must_not_contain=["Узбекистан"])
    assert report.ok, report.problems()


def test_a_failed_check_can_stop_the_run(tmp_path) -> None:
    out = _pdf(tmp_path / "a.pdf", CONTRACT)
    with pytest.raises(rewrite.FillNotVerified) as exc:
        rewrite.verify_or_raise(out, must_contain={"должность": "Штукатур"})
    assert "должность" in exc.value.message


# --------------------------------------------------------------- end to end


def test_the_previous_worker_is_replaced_and_the_result_proves_it(tmp_path):
    template = _pdf(tmp_path / "t.pdf", CONTRACT)
    out = tmp_path / "out.pdf"
    report = TrudDocEditor().fill(
        template, out, date_text="28.07.2026",
        worker_block=_block("Назаров", "Муродулло", "22.02.2004",
                            "FB1234567", "16.02.2023"),
        profession="Штукатур")

    assert report.ok, report.problems()
    text = rewrite.read_text(out)
    for gone in (OLD["surname"], OLD["birth"], OLD["passport"], OLD["issued"],
                 OLD["profession"], OLD["date"]):
        assert gone not in text, gone
    for present in ("Назаров", "Муродулло", "22.02.2004", "FB1234567",
                    "16.02.2023", "Штукатур", "28.07.2026"):
        assert present in text, present


def test_filling_twice_in_a_row_leaves_only_the_last_worker(tmp_path) -> None:
    """The case the office actually hits: yesterday's output, filled again."""
    editor = TrudDocEditor()
    first = tmp_path / "one.pdf"
    editor.fill(_pdf(tmp_path / "t.pdf", CONTRACT), first, date_text="28.07.2026",
                worker_block=_block("Назаров", "Муродулло", "22.02.2004",
                                    "FB1234567", "16.02.2023"),
                profession="Штукатур")

    second = tmp_path / "two.pdf"
    report = editor.fill(first, second, date_text="01.09.2026",
                         worker_block=_block("Каримов", "Азиз", "15.05.1990",
                                             "AC7654321", "03.03.2021",
                                             country="Таджикистан"),
                         profession="Маляр")

    assert report.ok, report.problems()
    text = rewrite.read_text(second)
    for gone in (OLD["surname"], OLD["passport"], "Назаров", "22.02.2004",
                 "FB1234567", "Штукатур", "28.07.2026"):
        assert gone not in text, f"{gone} survived into the third fill"
    for present in ("Каримов", "15.05.1990", "AC7654321", "Маляр", "01.09.2026"):
        assert present in text, present


def test_the_service_hands_the_verification_notes_to_the_operator(tmp_path):
    """A problem is carried up, not written into a log nobody reads."""
    import inspect

    from src.services import trud_service

    source = inspect.getsource(trud_service)
    assert "report.problems()" in source
    assert "notes" in inspect.getsource(trud_service.TrudResult)


def test_verification_can_be_switched_off_for_a_dry_run(tmp_path) -> None:
    report = TrudDocEditor().fill(
        _pdf(tmp_path / "t.pdf", CONTRACT), tmp_path / "o.pdf",
        date_text="28.07.2026",
        worker_block=_block("Назаров", "Муродулло", "22.02.2004",
                            "FB1234567", "16.02.2023"),
        profession="Штукатур", verify=False)
    assert report.ok and not report.written
