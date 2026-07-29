"""The worker's ИНН read off the патент, and everything it must refuse to read.

A патент is covered in numbers. Only one of them is the person's — the
twelve-digit ИНН. The issuing office's ИНН is ten digits, its ОГРН thirteen,
and the patent's own номер is neither. A reader having a bad day will offer any
of them, so the gate is arithmetic and not trust: twelve digits or nothing.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image
from src.ai.base import AiRawResult
from src.domain.enums import DocType
from src.ocr.service import OcrService


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (600, 400), (230, 230, 230)).save(buf, format="JPEG")
    return buf.getvalue()


class _Reader:
    """An AI that answers with whatever the test tells it to."""

    def __init__(self, answer=None, blow_up: Exception | None = None) -> None:
        self.answer = answer
        self.blow_up = blow_up
        self.prompts: list[str] = []
        self.doc_types: list[DocType] = []

    def available(self) -> bool:
        return True

    def extract(self, image: bytes, doc_type: DocType, prompt: str) -> AiRawResult:
        self.prompts.append(prompt)
        self.doc_types.append(doc_type)
        if self.blow_up is not None:
            raise self.blow_up
        return AiRawResult(document_type=doc_type, fields={"inn": self.answer})


def _read(answer, blow_up=None) -> tuple[str, _Reader]:
    reader = _Reader(answer, blow_up)
    return OcrService(reader).read_inn(_jpeg()), reader


# ------------------------------------------------------------ what is taken
def test_a_twelve_digit_inn_is_taken():
    got, _ = _read("772365215425")
    assert got == "772365215425"


def test_spacing_and_the_label_are_stripped():
    """«ИНН 77 23 65 21 54 25» is one number with decoration round it."""
    assert _read("ИНН 77 23 65 21 54 25")[0] == "772365215425"
    assert _read("772365215425\n")[0] == "772365215425"


# --------------------------------------------------------- what is refused
def test_an_organisations_ten_digit_inn_is_refused():
    """The office that issued the patent has an ИНН too. It is not the worker's."""
    assert _read("7723652154")[0] == ""


def test_an_ogrn_is_refused():
    assert _read("1234567890123")[0] == ""      # ОГРН, 13
    assert _read("123456789012345")[0] == ""    # ОГРНИП, 15


def test_a_blank_answer_is_refused_quietly():
    for answer in ("", None, "—", "не указан"):
        assert _read(answer)[0] == ""


def test_a_reader_that_fails_gives_an_empty_box_not_an_error():
    """The ИНН screen still works with no AI; reading is a convenience."""
    got, _ = _read(None, blow_up=RuntimeError("429 Too Many Requests"))
    assert got == ""


# --------------------------------------------------------------- the asking
def test_the_reader_is_told_what_not_to_bring_back():
    _, reader = _read("772365215425")
    prompt = reader.prompts[0]
    assert "12" in prompt
    assert "10-digit" in prompt and "ОГРН" in prompt
    assert "empty string" in prompt, "it must be allowed to say «I could not read it»"


# ------------------------------------------------------------- the screen
@pytest.fixture()
def screen():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from src.controllers.inn_controller import InnController
    from src.services.inn_service import InnService
    from src.ui.views.inn_view import InnView

    view = InnView(InnController(OcrService(_Reader("772365215425")), InnService()))
    yield view, app
    view.deleteLater()


def test_the_box_the_operator_typed_is_never_overwritten(screen):
    """«агар бошқа ИННни қилиш керак бўлса ўчириб қўлда ёзаман» — so what is
    typed by hand outranks anything the reader offers."""
    view, _app = screen
    view._inn.setText("111122223333")
    view._inn_read("772365215425")
    assert view._inn.text() == "111122223333"


def test_an_empty_box_is_filled(screen):
    view, _app = screen
    view._inn.clear()
    view._inn_read("772365215425")
    assert view._inn.text() == "772365215425"


def test_nothing_found_says_so_and_leaves_the_box_alone(screen):
    view, _app = screen
    view._inn.clear()
    view._inn_read("")
    assert view._inn.text() == ""
    assert "ўзингиз" in view._status.text()


# ------------------------------------- the line the патент actually prints
def test_the_inn_is_taken_out_of_the_passport_slash_inn_line():
    """«Документ удост. личность/ИНН» holds two numbers. Only one is the ИНН.

    The office's own card reads «FB0717527 / 072501692992», and the reader
    hands that line back whole. Joining its digits would give a 19-digit number
    belonging to nobody — the passport's seven followed by the ИНН's twelve.
    """
    assert _read("FB0717527 / 072501692992")[0] == "072501692992"
    assert _read("FB0717527/072501692992")[0] == "072501692992"
    assert _read("Документ удост. личность/ИНН  FB0717527 / 072501692992")[0] \
        == "072501692992"


def test_a_leading_zero_survives():
    """«072501692992» is not «72501692992» — it is somebody else's number."""
    got, _ = _read("072501692992")
    assert got == "072501692992"
    assert got.startswith("0")


def test_digits_glued_across_the_boundary_are_refused():
    """If the reading has already lost the slash, nothing can be trusted."""
    assert _read("0717527072501692992")[0] == ""


def test_the_patents_own_number_is_not_mistaken_for_an_inn():
    assert _read("Серия 77 №2500523150")[0] == ""


def test_two_different_twelve_digit_numbers_are_refused():
    """Ambiguity is not resolved by guessing; the operator types it."""
    assert _read("072501692992 и 111122223333")[0] == ""


def test_the_transcript_is_the_second_chance():
    """An empty field but a card read cleanly into the transcript still works."""
    from src.ai.base import AiRawResult

    class _Silent(_Reader):
        def extract(self, image, doc_type, prompt):
            return AiRawResult(
                document_type=doc_type, fields={"inn": ""},
                text="Документ удост. личность/ИНН\nFB0717527 / 072501692992")

    assert OcrService(_Silent()).read_inn(_jpeg()) == "072501692992"


def test_the_reader_is_told_where_to_look_on_a_patent():
    _, reader = _read("072501692992")
    prompt = reader.prompts[0]
    assert "Документ удост" in prompt, "it must be told which line carries it"
    assert "slash" in prompt.lower()
    assert "leading zero" in prompt.lower()


def test_the_line_is_used_when_the_reader_will_not_commit():
    """«I read the line but cannot tell you which half» is a good answer."""
    from src.ai.base import AiRawResult

    class _Unsure(_Reader):
        def extract(self, image, doc_type, prompt):
            return AiRawResult(document_type=doc_type, fields={
                "inn": "", "line": "FB0717527 / 072501692992"})

    assert OcrService(_Unsure()).read_inn(_jpeg()) == "072501692992"


def test_a_wrong_inn_beside_a_right_line_is_still_refused():
    """The field is tried first, but a bad one does not poison the line."""
    from src.ai.base import AiRawResult

    class _Muddled(_Reader):
        def extract(self, image, doc_type, prompt):
            return AiRawResult(document_type=doc_type, fields={
                "inn": "FB0717527", "line": "FB0717527 / 072501692992"})

    assert OcrService(_Muddled()).read_inn(_jpeg()) == "072501692992"


def test_the_reader_is_asked_for_the_whole_line():
    _, reader = _read("072501692992")
    assert '"line"' in reader.prompts[0]


def test_the_answer_is_not_judged_against_the_patent_schema():
    """This request asks for a number, not for a патент.

    Every answer is validated against the schema for its DocType, and PATENT
    requires the card's own fields — номер, фамилия, бланк. Asked under PATENT,
    an answer carrying only «inn» was thrown away as «керакли майдонлар йўқ»
    before anything here ever saw it, which is why reading a real card returned
    nothing at all. The free-form schema requires none of those.
    """
    from src.ai.schemas import schema_for

    _, reader = _read("072501692992")
    used = reader.doc_types[0]
    assert not schema_for(used).required_any, (
        f"{used} demands fields this request never asks for")
