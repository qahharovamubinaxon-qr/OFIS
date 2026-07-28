"""The machine-readable zone: the one part of a passport that can be proved.

Each value in the zone is followed by a check digit — a weighted sum of the
characters before it — so a misread character almost never adds up. These tests
pin the two consequences: when the arithmetic holds those values overrule the
vision model, and when it does not, nothing is overwritten and the operator is
told to look at the document.
"""

from __future__ import annotations

import pytest

pytest.importorskip("mrz")

from mrz.generator.td3 import TD3CodeGenerator  # noqa: E402

from src.ai.base import AiRawResult, IAiProvider  # noqa: E402
from src.ai.manager import AiManager  # noqa: E402
from src.domain.enums import DocType, Gender  # noqa: E402
from src.ocr import mrz_reader  # noqa: E402
from src.ocr.service import OcrService  # noqa: E402


def _mrz(number: str = "FB1234567", birth: str = "040222",
         expiry: str = "330215", sex: str = "M") -> tuple[str, str]:
    code = str(TD3CodeGenerator("P", "UZB", "NAZAROV", "MURODULLO HAITALIEVICH",
                                number, "UZB", birth, sex, expiry, ""))
    first, second = code.split("\n")
    return first, second


#: what the vision model said — every field of it wrong
MISREAD = {
    "surname": "НАЗАРОВА", "name": "МУРОДУЛЛА", "patronymic": "ХАИТАЛИЕВНА",
    "series": "FB", "number": "1234561", "birth_date": "2004-02-21",
    "gender": "female", "nationality": "ТАДЖИКИСТАН",
    "expiry_date": "2033-02-14", "issued_by": "МВД",
}


class _Provider(IAiProvider):
    name = "fake"

    def __init__(self, fields: dict, text: str = "") -> None:
        self._fields, self._text = fields, text

    def is_configured(self) -> bool:
        return True

    def extract(self, image, doc_type, prompt):
        return AiRawResult(document_type=doc_type, fields=self._fields,
                           provider=self.name, text=self._text)


def _service(fields: dict, text: str = "") -> OcrService:
    return OcrService(AiManager([_Provider(fields, text)]))


# --------------------------------------------------------------- the reader


def test_the_zone_reads_back_what_was_encoded_into_it() -> None:
    result = mrz_reader.read(line1=_mrz()[0], line2=_mrz()[1])
    assert result.trusted
    assert result.fields["surname"] == "НАЗАРОВ"
    assert result.fields["name"] == "МУРОДУЛЛО"
    assert result.fields["patronymic"] == "ХАИТАЛИЕВИЧ"
    assert result.fields["series"] == "FB"
    assert result.fields["number"] == "1234567"
    assert result.fields["birth_date"] == "2004-02-22"
    assert result.fields["expiry_date"] == "2033-02-15"
    assert result.fields["gender"] == "male"
    assert result.fields["nationality"] == "УЗБЕКИСТАН"


def test_the_zone_is_found_inside_a_page_of_ocr_text() -> None:
    """Mistral returns the whole page; the two lines have to be picked out."""
    first, second = _mrz()
    page = f"РЕСПУБЛИКА УЗБЕКИСТАН\nПАСПОРТ\nNAZAROV\n{first}\n{second}\n"
    assert mrz_reader.read(page).trusted


def test_spaces_an_ocr_puts_between_the_groups_are_forgiven() -> None:
    first, second = _mrz()
    spaced = " ".join(first)
    assert mrz_reader.read(f"...\n{spaced}\n{second}").trusted


def test_the_two_lines_joined_into_one_are_still_found() -> None:
    first, second = _mrz()
    assert mrz_reader.read(f"noise\n{first}{second}\nnoise").trusted


@pytest.mark.parametrize("position, field", [
    (9, "паспорт рақами"), (19, "туғилган сана"), (27, "амал муддати")])
def test_a_single_wrong_character_is_caught_and_named(position, field) -> None:
    first, second = _mrz()
    broken = second[:position] + ("8" if second[position] != "8" else "7") \
        + second[position + 1:]
    result = mrz_reader.read(line1=first, line2=broken)
    assert result.found and not result.valid
    assert field in result.problems


def test_a_page_with_no_zone_is_simply_no_zone() -> None:
    assert not mrz_reader.read("ПАСПОРТ\nНАЗАРОВ МУРОДУЛЛО\n1234567").found


def test_a_check_digit_is_the_icao_weighted_sum() -> None:
    """Worked out here, so the operator can be told which field is wrong."""
    assert mrz_reader.check_digit("FB1234567") == _mrz()[1][9]
    assert mrz_reader.check_digit("040222") == _mrz()[1][19]


def test_a_woman_is_read_as_one() -> None:
    first, second = _mrz(sex="F")
    assert mrz_reader.read(line1=first, line2=second).fields["gender"] == "female"


def test_a_birth_year_is_put_in_the_right_century() -> None:
    """«70» is 1970, «04» is 2004 — an expiry is always ahead."""
    first, second = _mrz(birth="700315", expiry="300101")
    fields = mrz_reader.read(line1=first, line2=second).fields
    assert fields["birth_date"] == "1970-03-15"
    assert fields["expiry_date"] == "2030-01-01"


# -------------------------------------------------------- against the model


def test_a_verified_zone_overrules_the_vision_model() -> None:
    first, second = _mrz()
    passport = _service({**MISREAD, "mrz_line1": first,
                         "mrz_line2": second}).read_passport(b"x")

    assert passport.surname == "НАЗАРОВ"
    assert passport.name == "МУРОДУЛЛО"
    assert passport.number == "1234567"
    assert passport.birth_date.isoformat() == "2004-02-22"
    assert passport.gender is Gender.MALE
    assert passport.nationality == "УЗБЕКИСТАН"
    assert passport.mrz_checked and passport.mrz_warning is None


def test_the_zone_is_used_even_when_the_model_did_not_quote_it() -> None:
    """Mistral hands back the page text; the lines are found in there."""
    first, second = _mrz()
    passport = _service(MISREAD, text=f"ПАСПОРТ\n{first}\n{second}").read_passport(b"x")
    assert passport.number == "1234567" and passport.mrz_checked


def test_a_zone_that_does_not_add_up_changes_nothing() -> None:
    """Better the model's reading plus a warning than a silent wrong number."""
    first, second = _mrz()
    broken = second[:9] + ("8" if second[9] != "8" else "7") + second[10:]
    passport = _service({**MISREAD, "mrz_line1": first,
                         "mrz_line2": broken}).read_passport(b"x")

    assert passport.number == "1234561", "the model's value is left as it was"
    assert passport.surname == "НАЗАРОВА"
    assert not passport.mrz_checked
    assert passport.mrz_warning and "текшириб чиқинг" in passport.mrz_warning


def test_a_passport_with_no_zone_behaves_exactly_as_before() -> None:
    passport = _service(MISREAD).read_passport(b"x")
    assert passport.number == "1234561"
    assert not passport.mrz_checked
    assert passport.mrz_warning is None


def test_what_the_zone_does_not_carry_is_left_to_the_model() -> None:
    """Place of birth, issue date and issuing office are not in the zone."""
    first, second = _mrz()
    passport = _service({**MISREAD, "birth_place": "УЗБЕКИСТАН",
                         "issue_date": "2023-02-16", "issued_by": "МВД РУЗ",
                         "mrz_line1": first, "mrz_line2": second}).read_passport(b"x")
    assert passport.birth_place == "УЗБЕКИСТАН"
    assert passport.issue_date.isoformat() == "2023-02-16"
    assert passport.issued_by == "МВД РУЗ"


def test_the_warning_reaches_the_screen_the_operator_is_looking_at() -> None:
    from src.services.generation_service import GenerationResult

    result = GenerationResult(pdf_path=__import__("pathlib").Path("x.pdf"),
                              reg_number=1, surname="НАЗАРОВА",
                              mrz_warning="MRZ мос келмади — текшириб чиқинг")
    assert result.mrz_warning
    # …and the view puts it under the success line rather than swallowing it
    import inspect

    from src.ui.views import process_view

    assert "mrz_warning" in inspect.getsource(process_view)


def test_no_api_and_no_key_is_involved() -> None:
    """The whole check is arithmetic on text already in hand."""
    import inspect

    source = inspect.getsource(mrz_reader)
    for forbidden in ("requests", "urllib", "http", "api_key"):
        assert forbidden not in source, forbidden
