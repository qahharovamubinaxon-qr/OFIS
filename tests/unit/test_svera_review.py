"""СФЕРА cert — read the (optional) passport ФИО into the boxes to check.

The cert already let the operator type the ФИО; when a passport was dropped it
was read inside the print step, unseen. Now the drop reads the ФИО straight
into the name boxes, and the cert is printed from those boxes.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from src.domain.documents import Passport
from src.domain.enums import Gender

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


class _Controller:
    def __init__(self, passport) -> None:
        self._passport = passport
        self.printed: dict = {}

    def professions(self):
        return [SimpleNamespace(name="Сварщик", note="")]

    def next_po_number(self) -> int:
        return 1

    def ai_available(self) -> bool:
        return True

    def read_image(self, path):
        return b"img"

    def read_passport(self, data):
        return self._passport

    def generate_from_images(self, profession, passport, photo_path, *,
                             issue_date, surname, name, patronymic):
        self.printed = {"profession": profession, "passport": passport,
                        "surname": surname, "name": name,
                        "patronymic": patronymic}
        return SimpleNamespace(pdf_path=Path("OUT.pdf"), udo_number="1",
                               po_number="1")


@pytest.fixture
def view(monkeypatch):
    import src.ui.views.svera_view as sv

    def run_now(fn, *a, on_success=None, on_error=None, **k):
        try:
            result = fn(*a, **k)
        except Exception as exc:  # noqa: BLE001 - the view's own error path
            if on_error:
                on_error(exc)
        else:
            if on_success:
                on_success(result)

    monkeypatch.setattr(sv, "run_async", run_now)
    return sv


class _Drop:
    def __init__(self, path=None) -> None:
        self.path = path

    def clear(self) -> None:
        self.path = None


def _passport():
    return Passport(surname="ПАЛВАНОВ", name="ДОВЛЕТ", patronymic="БАЙРАМОВИЧ",
                    number="046688", gender=Gender.MALE)


def _make(view_mod):
    controller = _Controller(_passport())
    screen = view_mod.SveraView(controller)
    screen._done = lambda r: None
    return screen, controller


def test_dropping_the_passport_reads_the_fio_into_the_boxes(view) -> None:
    screen, _ = _make(view)
    screen._dz_passport = _Drop("p.jpg")
    screen._read_passport()
    assert screen._surname.text() == "ПАЛВАНОВ"
    assert screen._name.text() == "ДОВЛЕТ"
    assert screen._patronymic.text() == "БАЙРАМОВИЧ"


def test_run_prints_the_boxes_without_re_reading(view) -> None:
    screen, controller = _make(view)
    screen._dz_passport = _Drop("p.jpg")
    screen._read_passport()
    screen._surname.setText("ПАЛВАНОВА")          # operator corrects
    screen._dz_photo = _Drop("photo.jpg")
    screen._run_ai()
    assert controller.printed["passport"] is None   # no second read
    assert controller.printed["surname"] == "ПАЛВАНОВА"


def test_run_refuses_with_no_name(view) -> None:
    from PySide6.QtWidgets import QMessageBox

    screen, controller = _make(view)
    QMessageBox.warning = staticmethod(lambda *a: None)
    screen._dz_photo = _Drop("photo.jpg")
    screen._run_ai()
    assert not controller.printed
