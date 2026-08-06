"""The ПИНФЛ read off the strip at the foot of an Uzbek passport.

The office's four Uzbek certificates name the worker by his ПИНФЛ, and the
passport prints it nowhere on its face. So it is read out of the machine
strip — and the reader is asked for the LINE, never for the number: a line
is taken apart here by arithmetic, and arithmetic cannot invent a digit.

The number in these tests is КАХОРОВ's own: 31301954050087, whose middle
six digits say 13.01.1995 — the date printed on the face of his passport.
"""

from __future__ import annotations

import io
from datetime import date

from PIL import Image
from src.ai.base import AiRawResult
from src.domain.enums import DocType
from src.ocr.service import OcrService

#: A real second line ends with sixteen digits: the ПИНФЛ and two check digits.
LINE2 = "AA12345671UZB9501134M300511<<3130195405008764"
LINE1 = "P<UZBKAHOROV<<AZIZBEK<<<<<<<<<<<<<<<<<<<<<<<"
BORN = date(1995, 1, 13)


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (600, 400), (230, 230, 230)).save(buf, format="JPEG")
    return buf.getvalue()


class _Reader:
    """An AI that answers with whatever the test tells it to."""

    def __init__(self, fields: dict | None = None,
                 blow_up: Exception | None = None) -> None:
        self.fields = fields or {}
        self.blow_up = blow_up
        self.prompts: list[str] = []
        self.doc_types: list[DocType] = []

    def available(self) -> bool:
        return True

    def extract(self, image: bytes, doc_type: DocType,
                prompt: str) -> AiRawResult:
        self.prompts.append(prompt)
        self.doc_types.append(doc_type)
        if self.blow_up is not None:
            raise self.blow_up
        return AiRawResult(document_type=doc_type, fields=self.fields)


def _read(fields=None, born: date | None = BORN,
          blow_up=None) -> tuple[str, _Reader]:
    reader = _Reader(fields, blow_up)
    return OcrService(reader).read_pinfl(_jpeg(), born), reader


# --------------------------------------------------------- what is taken
def test_the_number_is_cut_out_of_the_second_line() -> None:
    got, _ = _read({"line1": LINE1, "line2": LINE2})
    assert got == "31301954050087"


def test_a_swapped_answer_still_gives_the_number() -> None:
    """A reader that put the second line in «line1» is not a lost reading."""
    assert _read({"line1": LINE2, "line2": LINE1})[0] == "31301954050087"


def test_it_is_read_without_a_birth_date_too() -> None:
    """The check is a guard, not a requirement — свера has no date to give."""
    assert _read({"line2": LINE2}, born=None)[0] == "31301954050087"


# ------------------------------------------------------- what is refused
def test_a_number_that_disagrees_with_the_passport_is_refused() -> None:
    """13.01.1995 in the strip against 20.05.1973 on the face is a misreading.

    An empty box the operator fills in from the passport is right; a wrong
    ПИНФЛ on a certificate filed with the agency is not.
    """
    assert _read({"line2": LINE2}, born=date(1973, 5, 20))[0] == ""


def test_a_strip_that_could_not_be_read_gives_nothing() -> None:
    for fields in ({}, {"line1": "", "line2": ""},
                   {"line2": "не видно"}, {"line2": LINE1}):
        assert _read(fields)[0] == ""


def test_a_reader_that_fails_gives_an_empty_box_not_an_error() -> None:
    """The screen still works with no AI; reading is a convenience."""
    got, _ = _read(blow_up=RuntimeError("429 Too Many Requests"))
    assert got == ""


# ------------------------------------------------------------ the asking
def test_the_reader_is_asked_for_the_line_and_not_for_the_number() -> None:
    _, reader = _read({"line2": LINE2})
    prompt = reader.prompts[0]
    assert '"line2"' in prompt and '"line1"' in prompt
    assert "machine-readable" in prompt
    assert "character for character" in prompt
    assert "empty" in prompt, "it must be allowed to say «I could not read it»"


def test_the_reader_is_forbidden_to_tidy_the_strip() -> None:
    """«<» and the check digits are the arithmetic. Tidying them destroys it."""
    _, reader = _read({"line2": LINE2})
    prompt = reader.prompts[0]
    assert "do not remove" in prompt.lower()
    assert "correct" in prompt.lower()


def test_the_answer_is_not_judged_against_the_passport_schema() -> None:
    """This request asks for two lines, not for a passport.

    Under DocType.PASSPORT the answer would be thrown away as «керакли
    майдонлар йўқ» before anything here ever saw it.
    """
    from src.ai.schemas import schema_for

    _, reader = _read({"line2": LINE2})
    assert not schema_for(reader.doc_types[0]).required_any, (
        f"{reader.doc_types[0]} demands fields this request never asks for")
