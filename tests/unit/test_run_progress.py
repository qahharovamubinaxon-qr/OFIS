"""Жараён ҳалқаси: ўртадаги фоиз ҲАҚИҚИЙ бўлсин.

Аввалги кўрсаткич ҳеч нарса санамасди — таймер билан 90% гача судралиб,
жавоб келганда 100% га сакрарди. Яъни рақам бор эди, маъноси йўқ. Энди:

* қадамлари номаълум иш — ҳалқа АЙЛАНАДИ, ўртасида рақам йўқ;
* қадамлари маълум иш — ҳалқа қадамлар бўйича тўлади, фоиз рост.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


def _progress():
    from src.ui.widgets.run_progress import RunProgress

    return RunProgress()


# ------------------------------------------------------------- айланиш
def test_work_with_no_countable_steps_shows_no_number() -> None:
    bar = _progress()
    bar.start("Ҳужжатлар ўқиляпти…")
    assert bar.percent() == 0
    assert bar._ring.centre_text() == "", "номаълум ишга фоиз ёзилди"


def test_a_sweep_cannot_be_nudged_into_inventing_a_figure() -> None:
    bar = _progress()
    bar.start("ўқиляпти…")
    bar.step_done()
    bar.step_done()
    assert bar.percent() == 0


def test_an_empty_step_list_is_not_a_finished_job() -> None:
    bar = _progress()
    bar.start_steps([], "иш")
    assert bar.percent() == 0
    assert bar._ring.centre_text() == ""


# -------------------------------------------------------------- қадамлар
def test_the_ring_fills_by_the_steps_that_really_finished() -> None:
    bar = _progress()
    bar.start_steps(["бир", "икки", "уч"], "PDF")
    assert bar.percent() == 0
    bar.step_done()
    assert bar.percent() == 33
    bar.step_done()
    assert bar.percent() == 67
    bar.step_done()
    assert bar.percent() == 100
    assert bar._ring.progress() == pytest.approx(1.0)


def test_the_middle_says_the_percent() -> None:
    bar = _progress()
    bar.start_steps(["бир", "икки"], "PDF")
    bar.step_done()
    assert bar._ring.centre_text() == "50"


def test_more_reports_than_steps_do_not_overfill_the_ring() -> None:
    bar = _progress()
    bar.start_steps(["бир", "икки"], "PDF")
    for _ in range(9):
        bar.step_done()
    assert bar.percent() == 100
    assert bar._ring.progress() == 1.0


def test_a_failure_keeps_the_figure_it_reached() -> None:
    """Қаергача етгани — энг керакли маълумот."""
    bar = _progress()
    bar.start_steps(["бир", "икки", "уч", "тўрт"], "PDF")
    bar.step_done()
    bar.fail("бланка топилмади")
    assert bar.percent() == 25


# ------------------------------------- хизмат ҳақиқий қадамларни хабар қилади
class _Settings:
    def __init__(self) -> None:
        self._v: dict = {}

    def get(self, key, default=None):
        return self._v.get(key, default)

    def set(self, key, value) -> None:
        self._v[key] = value


_FIRM = uuid4()


def _employee():
    from src.domain.documents import Passport, Patent
    from src.domain.employee import Employee
    from src.domain.enums import Gender

    passport = Passport(
        surname="ИСОЕВ", name="АСЛИДИН", patronymic="ХОЛБЕРДИЕВИЧ",
        series="A", number="405847273", nationality="ТАДЖИКИСТАН",
        gender=Gender.MALE, birth_date=date(1999, 7, 25),
        issue_date=date(2021, 3, 1), expiry_date=date(2031, 3, 1))
    patent = Patent(series="77", number="2400328451", profession="РАЗНОРАБОЧИЙ",
                    issue_date=date(2026, 7, 18))
    return Employee(company_id=_FIRM, passport=passport, patent=patent,
                    profession="РАЗНОРАБОЧИЙ", contract_date=date(2026, 11, 16))


def _company():
    from src.config import paths

    return SimpleNamespace(
        id=_FIRM, name="ООО ТЕСТ",
        template_path=paths.templates_dir() / "mvd_prilozhenie_7" / "template.pdf")


def test_generation_reports_each_step_as_it_finishes(tmp_path) -> None:
    from src.services.generation_service import STEPS, GenerationService

    said: list[str] = []
    service = GenerationService(_Settings(), None)
    service.generate(_employee(), _company(), form_date=date(2026, 11, 16),
                     output_dir=tmp_path, on_step=said.append)
    assert said == list(STEPS), "қадамлар тартиби ҳалқадагидан бошқача"


def test_the_screen_cannot_stop_a_document_being_made(tmp_path) -> None:
    """Хабар ета олмаса ҳам ҳужжат чиқсин — кўрсаткич иш эмас."""
    from src.services.generation_service import GenerationService

    def broken(_step: str) -> None:
        raise RuntimeError("ойна ёпилган")

    service = GenerationService(_Settings(), None)
    result = service.generate(_employee(), _company(),
                              form_date=date(2026, 11, 16),
                              output_dir=tmp_path, on_step=broken)
    assert result.pdf_path.exists()


def test_the_steps_the_service_reports_are_the_ones_the_ring_shows() -> None:
    """Иккови бир рўйхатдан — акс ҳолда ҳалқа 75% да қотиб қоларди."""
    from src.services.generation_service import STEPS

    bar = _progress()
    bar.start_steps(list(STEPS), "PDF")
    for _ in STEPS:
        bar.step_done()
    assert bar.percent() == 100
