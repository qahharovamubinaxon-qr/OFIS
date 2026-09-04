"""ТРУД / карта sections — read on upload, check the ФИО, print from the boxes.

mvd_trud, trud8, qrreg, alpinist and spr3 all read the passport (and, for the
ТРУД packets, the patent) and printed in one press. They now show the read ФИО
in the shared check panel and print from what is IN THE BOXES. The two ТРУД
packets carry the patent's own number and dates, so the corrected name is made
to ride on the patent too.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from src.domain.documents import Passport, Patent
from src.domain.enums import Gender

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


class _Ctl:
    """Enough of a controller to build any of these screens and record RUN.

    The screens ask their controller for template/firm lists, layouts and the
    like while building; anything not spelled out here answers with a harmless
    empty default so construction never crashes.
    """

    def __init__(self, passport, patent=None) -> None:
        self._passport, self._patent = passport, patent
        self.printed: dict = {}

    def ai_available(self) -> bool:
        return True

    def read_image(self, path):
        return b"img"

    # lists the combos are built from
    def templates(self, *a, **k):
        return []

    def firms(self, *a, **k):
        return []

    def addresses(self, *a, **k):
        return []

    def pages(self, *a, **k):
        return []

    def work_address(self):
        return ""

    def next_number(self):
        return "1"

    def until(self, *a, **k):
        return None

    def __getattr__(self, name):
        # any other build-time query (layout, stamp, blank, fields…) is inert
        return lambda *a, **k: None


@pytest.fixture
def run_now(monkeypatch):
    def _install(module):
        def run(fn, *a, on_success=None, on_error=None, **k):
            try:
                result = fn(*a, **k)
            except Exception as exc:  # noqa: BLE001 - the view's own error path
                if on_error:
                    on_error(exc)
            else:
                if on_success:
                    on_success(result)
        monkeypatch.setattr(module, "run_async", run)
    return _install


class _Drop:
    def __init__(self, path=None) -> None:
        self.path = path

    def clear(self) -> None:
        self.path = None


def _passport() -> Passport:
    return Passport(
        surname="PALVANOV", name="DOVLETGELDI", number="046688", series="A2",
        nationality="ТУРКМЕНИСТАН", gender=Gender.MALE,
        birth_date=date(1990, 5, 15), issue_date=date(2023, 3, 13),
        expiry_date=date(2028, 3, 12))


def _patent() -> Patent:
    return Patent(number="240", series="77", profession="рабочий",
                  holder_surname="ПАЛВАНОВ", holder_name="ДОВЛЕТГЕЛДИ",
                  holder_citizenship="ТУРКМЕНИСТАН")


# ---------------------------------------------------------- passport-only
def test_qrreg_reads_shows_and_prints_the_boxes(run_now) -> None:
    import src.ui.views.qrreg_view as qv
    run_now(qv)

    passport = _passport()

    def read_documents(passport_bytes, patent_bytes):
        return passport
    ctl = _Ctl(passport)
    ctl.read_documents = read_documents
    ctl.generate = lambda **k: ctl.printed.update(k) or SimpleNamespace(
        saved=Path("OUT.pdf"), link="http://x")
    screen = qv.QrRegView(ctl)
    screen._done = lambda r: None

    screen._passport = _Drop("p.jpg")
    screen._read_now()
    assert not screen._review.isHidden()
    assert screen._review._boxes["surname"].text() == "PALVANOV"

    screen._review._boxes["surname"].setText("ПАЛВАНОВА")
    screen._template.addItem("t", Path("t.pdf"))
    screen._template.setCurrentIndex(screen._template.count() - 1)
    screen._generate()
    assert screen.__dict__  # sanity
    assert ctl.printed["passport"].surname == "ПАЛВАНОВА"


def test_spr3_reads_and_prints_the_boxes(run_now) -> None:
    import src.ui.views.spr3_view as sv
    run_now(sv)

    passport = _passport()
    ctl = _Ctl(passport)
    ctl.read_documents = lambda a, b: passport
    ctl.generate = lambda **k: ctl.printed.update(k) or SimpleNamespace(
        saved=Path("OUT.pdf"))
    screen = sv.Spr3View(ctl)
    screen._done = lambda r: None

    screen._passport = _Drop("p.jpg")
    screen._read_now()
    screen._review._boxes["surname"].setText("ПАЛВАНОВА")
    screen._template.addItem("t", Path("t.pdf"))
    screen._template.setCurrentIndex(screen._template.count() - 1)
    screen._generate()
    assert ctl.printed["passport"].surname == "ПАЛВАНОВА"


# ------------------------------------------------------- patent is printed
def test_mvd_trud_makes_the_corrected_name_ride_the_patent(run_now) -> None:
    import src.ui.views.mvd_trud_view as mv
    run_now(mv)

    passport, patent = _passport(), _patent()
    ctl = _Ctl(passport, patent)
    ctl.read_documents = lambda a, b, c: (passport, patent)
    ctl.generate = lambda **k: ctl.printed.update(k) or SimpleNamespace(
        saved=Path("OUT.pdf"))
    screen = mv.MvdTrudView(ctl)
    screen._done = lambda r: None

    screen._passport = _Drop("p.jpg")
    screen._front = _Drop("front.jpg")
    screen._read_now()
    assert not screen._review.isHidden()

    screen._review._boxes["surname"].setText("ПАЛВАНОВА")
    screen._template.addItem("t", Path("t.pdf"))
    screen._template.setCurrentIndex(screen._template.count() - 1)
    screen._generate()
    assert ctl.printed["passport"].surname == "ПАЛВАНОВА"
    # the packet prints patent details, and the fix rides the patent too
    assert ctl.printed["patent"].holder_surname == "ПАЛВАНОВА"
    assert ctl.printed["patent"].number == "240"


def test_mvd_trud_run_starts_the_read_when_pressed_early(run_now) -> None:
    """The office dropped the images and pressed Тайёрлаш before the (slow
    first) read had begun. That press must START the read, not scold «upload
    the images» when they are plainly there."""
    import src.ui.views.mvd_trud_view as mv
    run_now(mv)

    passport, patent = _passport(), _patent()
    ctl = _Ctl(passport, patent)
    ctl.read_documents = lambda a, b, c: (passport, patent)
    ctl.generate = lambda **k: ctl.printed.update(k) or SimpleNamespace(
        saved=Path("OUT.pdf"))

    screen = mv.MvdTrudView(ctl)
    screen._done = lambda r: None
    screen._passport = _Drop("p.jpg")
    screen._front = _Drop("front.jpg")
    screen._template.addItem("t", Path("t.pdf"))
    screen._template.setCurrentIndex(screen._template.count() - 1)

    # pressing Тайёрлаш with the panel still hidden kicks off the read
    assert screen._review.isHidden()
    screen._generate()
    assert not screen._review.isHidden()     # the read ran and the boxes filled
    assert not ctl.printed                   # nothing printed yet

    # now the second press prints (the patent's Russian ФИО having won)
    screen._generate()
    assert ctl.printed["passport"].surname == "ПАЛВАНОВ"


def test_mvd_trud_reads_the_passport_alone_no_silent_wait(run_now) -> None:
    """The office dropped a passport in ТРУД and the screen sat dead: the read
    used to wait — unseen — for the patent front too. «ишламаяпти». It must
    read the passport the moment it lands, like every other section; the patent
    is asked for only at print time (the ТРУД prints its number and dates)."""
    import src.ui.views.mvd_trud_view as mv
    run_now(mv)

    passport, patent = _passport(), _patent()
    ctl = _Ctl(passport, patent)
    ctl.read_documents = lambda a, b, c: (passport, patent)
    ctl.generate = lambda **k: ctl.printed.update(k) or SimpleNamespace(
        saved=Path("OUT.pdf"))

    screen = mv.MvdTrudView(ctl)
    screen._done = lambda r: None
    screen._template.addItem("t", Path("t.pdf"))
    screen._template.setCurrentIndex(screen._template.count() - 1)

    # ONLY the passport — the old code did nothing here
    screen._passport = _Drop("p.jpg")
    screen._front = _Drop(None)
    screen._read_now()
    assert not screen._review.isHidden()      # it read; the screen is not dead
    assert screen._review._boxes["surname"].text() == "ПАЛВАНОВ"

    # printing still needs the patent front, so it asks — it does not print blank
    screen._generate()
    assert not ctl.printed

    # add the patent front → now it prints
    screen._front = _Drop("front.jpg")
    screen._generate()
    assert ctl.printed["passport"].surname == "ПАЛВАНОВ"


def test_trud8_prints_the_boxes_with_the_patent(run_now) -> None:
    import src.ui.views.trud8_view as tv
    run_now(tv)

    passport, patent = _passport(), _patent()
    ctl = _Ctl(passport, patent)
    ctl.read_documents = lambda a, b, c: (passport, patent)
    ctl.generate = lambda **k: ctl.printed.update(k) or SimpleNamespace(
        saved=[Path("OUT.pdf")])
    ctl._firm_now = None
    screen = tv.Trud8View(ctl)
    screen._done = lambda r: None
    screen._firm_now = lambda: Path("firm.pdf")     # a firm is chosen

    screen._passport = _Drop("p.jpg")
    screen._front = _Drop("front.jpg")
    screen._read_now()
    screen._review._boxes["surname"].setText("ПАЛВАНОВА")
    screen._generate()
    assert ctl.printed["passport"].surname == "ПАЛВАНОВА"
    assert ctl.printed["patent"].holder_surname == "ПАЛВАНОВА"


# ------------------------------------------------ the one-shot paths stay
@pytest.mark.parametrize("module,cls", [
    ("qrreg_controller", "QrRegController"),
    ("alpinist_controller", "AlpinistController"),
    ("spr3_controller", "Spr3Controller"),
    ("mvd_trud_controller", "MvdTrudController"),
    ("trud8_controller", "Trud8Controller"),
])
def test_read_and_generate_still_exist(module, cls) -> None:
    import importlib

    controller = getattr(importlib.import_module(
        f"src.controllers.{module}"), cls)
    assert hasattr(controller, "read_documents")
    assert hasattr(controller, "generate")
