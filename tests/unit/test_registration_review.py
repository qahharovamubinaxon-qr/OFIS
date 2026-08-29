"""РЕГИСТРАЦИЯ — read, show, correct, then print from the boxes.

Reading and printing used to be one press, so a wrong name off a misread
patent went straight onto a filed «Уведомление о прибытии» with nobody having
seen it. The office asked for the two to be separated, the way ДМС already is:
the documents are read the moment they are dropped, shown in editable boxes,
and the form is printed from whatever is IN THE BOXES — never from the raw
reading again.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from src.domain.documents import Passport, Patent
from src.domain.enums import Gender
from src.domain.registration_address import RegistrationAddress

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


def _address() -> RegistrationAddress:
    return RegistrationAddress(label="ПАРКОВАЯ 55", internal_code="p55",
                               address_text="Москва", host_fio="Иванов",
                               template_path=Path("x.pdf"))


class _Controller:
    """A stand-in: hands back documents to read, records what RUN prints."""

    def __init__(self, passport, patent) -> None:
        self._passport, self._patent = passport, patent
        self.printed: dict = {}

    def ai_available(self) -> bool:
        return True

    def addresses(self) -> list[RegistrationAddress]:
        return [_address()]

    def read_image(self, path):
        return b"img"

    def read_documents(self, passport, patent, patent_back):
        return self._passport, self._patent

    def generate(self, passport, patent, address, *, registration_expiry):
        self.printed = {"passport": passport, "patent": patent,
                        "address": address, "expiry": registration_expiry}

        class _Result:
            pdf_path = Path("OUT.pdf")

        return _Result()


@pytest.fixture
def view(monkeypatch):
    """The screen, with its background reads and prints made synchronous."""
    import src.ui.views.registration_view as rv

    def run_now(fn, *a, on_success=None, on_error=None, **k):
        try:
            result = fn(*a, **k)
        except Exception as exc:  # noqa: BLE001 - the view's own error path
            if on_error:
                on_error(exc)
        else:
            if on_success:
                on_success(result)

    monkeypatch.setattr(rv, "run_async", run_now)
    return rv


class _Drop:
    def __init__(self, path=None) -> None:
        self.path = path

    def clear(self) -> None:
        self.path = None


def _make(view_mod, passport, patent):
    controller = _Controller(passport, patent)
    screen = view_mod.RegistrationView(controller, None)
    screen._done = lambda result: None            # skip the save dialog
    return screen, controller


def _worker() -> tuple[Passport, Patent]:
    passport = Passport(
        surname="PALVANOV", name="DOVLETGELDI", number="046688", series="A2",
        nationality="ТУРКМЕНИСТАН", gender=Gender.MALE,
        birth_date=date(1990, 5, 15), issue_date=date(2023, 3, 13),
        expiry_date=date(2028, 3, 12))
    patent = Patent(number="240", profession="рабочий",
                    holder_surname="ПАЛВАНОВ", holder_name="ДОВЛЕТГЕЛДИ",
                    holder_patronymic="БАЙРАМОВИЧ",
                    holder_citizenship="ТУРКМЕНИСТАН")
    return passport, patent


# --------------------------------------------------------- read and show
def test_the_boxes_are_hidden_until_something_is_read(view) -> None:
    screen, _ = _make(view, *_worker())
    assert screen._read.isHidden()


def test_dropping_the_passport_reads_it_at_once(view) -> None:
    passport, patent = _worker()
    screen, _ = _make(view, passport, patent)
    screen._dz_passport = _Drop("passport.jpg")
    screen._read_now()
    assert not screen._read.isHidden()
    assert screen._boxes["surname"].text() == "ПАЛВАНОВ"
    assert screen._boxes["name"].text() == "ДОВЛЕТГЕЛДИ"


def test_the_patents_russian_name_is_what_is_shown(view) -> None:
    """The patent prints the name in Russian; that is the one to show."""
    passport, patent = _worker()
    passport.surname = "PALVANOV"        # latin, off the passport page
    screen, _ = _make(view, passport, patent)
    screen._dz_passport = _Drop("p.jpg")
    screen._read_now()
    assert screen._boxes["surname"].text() == "ПАЛВАНОВ"      # patent wins
    assert screen._boxes["patronymic"].text() == "БАЙРАМОВИЧ"


def test_the_passport_dates_and_gender_are_shown(view) -> None:
    passport, patent = _worker()
    screen, _ = _make(view, passport, patent)
    screen._dz_passport = _Drop("p.jpg")
    screen._read_now()
    assert screen._boxes["issue_date"].text() == "13.03.2023"
    assert screen._boxes["expiry_date"].text() == "12.03.2028"
    assert screen._gender.currentText() == "Мужской"
    assert screen._born.date().toString("dd.MM.yyyy") == "15.05.1990"


# ----------------------------------------------------- print from the boxes
def test_run_prints_what_is_in_the_boxes_not_what_was_read(view) -> None:
    """The whole point: the operator's correction reaches the form."""
    passport, patent = _worker()
    screen, controller = _make(view, passport, patent)
    screen._dz_passport = _Drop("p.jpg")
    screen._read_now()

    screen._boxes["surname"].setText("ПАЛВАНОВА")   # operator fixes a misread
    screen._boxes["patronymic"].setText("БАЙРАМОВНА")
    screen._run_ai()

    printed = controller.printed["passport"]
    assert printed.surname == "ПАЛВАНОВА"
    assert printed.patronymic == "БАЙРАМОВНА"


def test_the_patent_is_not_needed_at_print_time(view) -> None:
    """A single Passport carries every value the form needs; the patent's
    only job was to supply a Russian name, and that is already in a box."""
    passport, patent = _worker()
    screen, controller = _make(view, passport, patent)
    screen._dz_passport = _Drop("p.jpg")
    screen._read_now()
    screen._run_ai()
    assert controller.printed["patent"] is None


def test_the_expiry_date_reaches_the_form(view) -> None:
    passport, patent = _worker()
    screen, controller = _make(view, passport, patent)
    screen._dz_passport = _Drop("p.jpg")
    screen._read_now()
    screen._expiry.setDate(screen._expiry.date())
    screen._run_ai()
    assert controller.printed["expiry"] == screen._expiry_date()


def test_run_refuses_before_anything_is_read(view) -> None:
    from PySide6.QtWidgets import QMessageBox

    passport, patent = _worker()
    screen, controller = _make(view, passport, patent)
    warned = []
    QMessageBox.warning = staticmethod(lambda *a: warned.append(a))
    screen._dz_passport = _Drop(None)
    screen._run_ai()
    assert warned and not controller.printed


def test_a_blank_surname_is_refused(view) -> None:
    from PySide6.QtWidgets import QMessageBox

    passport, patent = _worker()
    screen, controller = _make(view, passport, patent)
    screen._dz_passport = _Drop("p.jpg")
    screen._read_now()
    screen._boxes["surname"].clear()
    warned = []
    QMessageBox.warning = staticmethod(lambda *a: warned.append(a))
    screen._run_ai()
    assert warned and not controller.printed


# ------------------------------------------------------ if the read fails
def test_a_failed_read_still_opens_the_boxes_for_typing(view) -> None:
    from src.common.errors import OfisError

    passport, patent = _worker()
    screen, _ = _make(view, passport, patent)
    screen._c.read_documents = lambda *a: (_ for _ in ()).throw(
        OfisError("AI жавоб бермади"))
    screen._dz_passport = _Drop("p.jpg")
    screen._read_now()
    assert not screen._read.isHidden(), "хатода ҳам қўлда ёзиш учун очилиши керак"


# --------------------------------------------------- the bot is unaffected
def test_the_bot_still_reads_and_prints_in_one_call() -> None:
    """The phone has no screen, so its one-shot path must stay."""
    from src.controllers.registration_controller import RegistrationController

    assert hasattr(RegistrationController, "generate_from_images")
    assert hasattr(RegistrationController, "read_documents")
    assert hasattr(RegistrationController, "generate")
