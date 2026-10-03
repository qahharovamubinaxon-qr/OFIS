"""МЕРКУРИЙ экрани — қурилиши, AI жавобини жойлаши ва шакл йиғилиши.

AI ҳам, PDF ҳам чақирилмайди: сохта контроллер берилади. Мақсад — экран
хатосиз қурилсин, ўқилган қийматлар керакли майдонга тушсин ва «Тайёрлаш»
босилмасдан ҳам шаклдан тўғри ёзув йиғилсин.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from src.domain.vetdoc import Shop

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


class _FakeController:
    """OCR ҳам, диск ҳам йўқ — фақат экран мантиғи учун."""

    def __init__(self) -> None:
        self.saved: Shop | None = None

    def ai_available(self) -> bool:
        return True

    def shop(self) -> Shop:
        return Shop(name="МЕРКУРИЙ", site="https://shop.example/vet")

    def save_shop(self, shop: Shop) -> None:
        self.saved = shop

    def logo(self) -> Path | None:
        return None


def _view():
    from src.ui.views.vetdoc_view import VetDocView

    return VetDocView(_FakeController())


def test_builds_with_every_registry_field():
    view = _view()
    for key in ("number", "kind", "product", "species", "title", "volume",
                "quarantine_days", "sender_company", "receiver_company",
                "buyer", "vet_name", "institution", "remark"):
        assert key in view._fields


def test_shop_is_loaded_into_the_boxes():
    view = _view()
    assert view._shop_fields["name"].text() == "МЕРКУРИЙ"
    assert view._shop_fields["site"].text() == "https://shop.example/vet"


def test_ai_answer_fills_fields_and_the_animal_row():
    view = _view()
    view._filled({"title": "Петух", "volume": "4 головы",
                  "animal.sex": "Самец", "animal.breed": "Петух"})
    assert view._fields["title"].text() == "Петух"
    assert view._animals.first_row_values()["sex"] == "Самец"


def test_ai_never_overwrites_what_the_operator_typed():
    view = _view()
    view._fields["title"].setText("Курица")
    view._filled({"title": "Петух"})
    assert view._fields["title"].text() == "Курица"


def test_form_builds_a_record():
    view = _view()
    view._fields["title"].setText("Петух")
    view._fields["buyer"].setText("Иванов Иван Иванович")
    view._animals.set_first_row({"breed": "Петух", "count": "1"})
    view._treatments.add_row({"kind": "обработка", "drug": "Альбен"})
    record = view._record()
    assert record.title == "Петух"
    assert record.buyer == "Иванов Иван Иванович"
    assert record.issued is not None
    assert record.status == "оформлен"
    assert [a.breed for a in record.animals] == ["Петух"]
    assert [t.drug for t in record.treatments] == ["Альбен"]
    assert record.docs == []


def test_clear_empties_the_form():
    view = _view()
    view._fields["title"].setText("Петух")
    view._treatments.add_row({"kind": "обработка"})
    view._clear()
    assert view._fields["title"].text() == ""
    assert view._record().treatments == []
