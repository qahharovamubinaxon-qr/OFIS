"""How a passport is read — from the PRINTED page, by the office's rules.

The strip of «<<<» at the foot of a passport used to be read and checked
arithmetically, and the office was warned whenever the sums did not come
out. It was removed: the strip carries no patronymic, no issuing office and
no birth place, its own reading was as fallible as any other, and the
warning fired on documents that were perfectly good.

What replaced it is stricter, not looser. A passport does not print a
Russian spelling — it prints the name in LATIN — so the Russian one is
TRANSLITERATED here, by the same table the patents are typed by, instead of
being left to whatever Cyrillic the model wrote out. That is what these
tests hold: «KAKHOROV» is КАХОРОВ, and no model guess overrides it.
"""

from __future__ import annotations

from src.ai.base import AiRawResult, IAiProvider
from src.ai.manager import AiManager
from src.domain.document_number import check_digit, strip_document_check_digit
from src.ocr.service import OcrService


class _Provider(IAiProvider):
    name = "fake"

    def __init__(self, fields: dict, text: str = "",
                 per_type: dict | None = None) -> None:
        self._fields, self._text = fields, text
        self._per_type = per_type or {}

    def is_configured(self) -> bool:
        return True

    def extract(self, image, doc_type, prompt):
        return AiRawResult(document_type=doc_type,
                           fields=self._per_type.get(doc_type, self._fields),
                           provider=self.name, text=self._text)


def _service(fields: dict, text: str = "", per_type: dict | None = None
             ) -> OcrService:
    return OcrService(AiManager([_Provider(fields, text, per_type)]))


#: the office's own case: an Uzbek passport printing KAKHOROV, which the
#: model turned into «КАКОРОВ» — the Х simply dropped out
KAKHOROV = {
    "surname": "КАКОРОВ", "surname_latin": "KAKHOROV",
    "name": "АББОСБЕК", "name_latin": "ABBOSBEK",
    "patronymic": "АНВАРОВИЧ", "patronymic_latin": "ANVAROVICH",
    "series": "FB", "number": "1234567", "nationality": "УЗБЕКИСТАН",
    "birth_date": "2004-02-22", "gender": "male",
}


# ------------------------------------------- the Latin row rules the name
def test_the_printed_latin_decides_the_russian_spelling() -> None:
    """The office's own complaint: KAKHOROV came out КАКОРОВ."""
    passport = _service(KAKHOROV).read_passport(b"x")
    assert passport.surname == "КАХОРОВ"
    assert passport.name == "АББОСБЕК"
    assert passport.patronymic == "АНВАРОВИЧ"


def test_every_letter_rule_is_the_patents_own() -> None:
    """The table is the practical transcription the patents are typed by,
    so a passport and a patent come out as ONE name."""
    cases = {
        "KAKHOROV": "КАХОРОВ", "ZHURAYEV": "ЖУРАЕВ",
        "SHUKUROV": "ШУКУРОВ", "CHORIYEV": "ЧОРИЕВ",
        "YOʻLDOSHEV": "ЮЛДОШЕВ", "OʻKTAMOV": "УКТАМОВ",
        "GʻAYRATOV": "ГАЙРАТОВ", "XOLMATOV": "ХОЛМАТОВ",
        "ERGASHEV": "ЭРГАШЕВ", "QODIROV": "КОДИРОВ",
    }
    for latin, russian in cases.items():
        passport = _service({**KAKHOROV, "surname": "ХХХ",
                             "surname_latin": latin}).read_passport(b"x")
        assert passport.surname == russian, latin


def test_a_name_already_printed_in_russian_is_copied_not_transliterated() -> None:
    """A visa, a миграционная карта or a patent prints the ФИО in Russian.
    That spelling is the best there is: nothing is derived over it."""
    passport = _service({**KAKHOROV, "surname": "КАХОРОВ",
                         "surname_latin": "", "name_latin": "",
                         "patronymic_latin": ""}).read_passport(b"x")
    assert passport.surname == "КАХОРОВ"
    assert passport.name == "АББОСБЕК"


def test_a_latin_row_that_did_not_read_cleanly_is_not_used() -> None:
    """Nothing is derived from a misreading: a «Latin» row with digits or
    marks in it is dropped and the model's own Cyrillic stands."""
    for rubbish in ("KAKH0R0V", "<<<<<<", "KAKHOROV<<ABBOSBEK", "  "):
        passport = _service({**KAKHOROV, "surname": "КАХОРОВ",
                             "surname_latin": rubbish}).read_passport(b"x")
        assert passport.surname == "КАХОРОВ", rubbish


def test_the_citizenship_still_decides_the_one_letter_that_depends_on_it() -> None:
    """A Tajik Jamshed is ДЖАМШЕД where an Uzbek Jasur is ЖАСУР."""
    uzbek = _service({**KAKHOROV, "name_latin": "JASUR",
                      "nationality": "УЗБЕКИСТАН"}).read_passport(b"x")
    assert uzbek.name == "ЖАСУР"
    tajik = _service({**KAKHOROV, "name_latin": "JAMSHED", "series": "",
                      "number": "406576690",
                      "nationality": "ТАДЖИКИСТАН"}).read_passport(b"x")
    assert tajik.name == "ДЖАМШЕД"


def test_the_fathers_name_and_ugli_stay_two_words() -> None:
    """The office's own output carried «ЖУРАМУРОДУГЛИ»: the reader ran the
    father's name and «ўғли» together. They are two words on the passport,
    two on the patent, and two on the form."""
    from src.domain.documents import Passport, Patent
    from src.domain.passport_rules import split_son_of

    assert split_son_of("ЖУРАМУРОДУГЛИ") == "ЖУРАМУРОД УГЛИ"
    assert split_son_of("JURAMURODUGLI") == "JURAMUROD UGLI"
    assert split_son_of("АНВАРОВНАКИЗИ") == "АНВАРОВНА КИЗИ"
    # already right, or not a patronymic at all — left exactly as it stands
    assert split_son_of("ЖУРАМУРОД УГЛИ") == "ЖУРАМУРОД УГЛИ"
    assert split_son_of("АНВАРОВИЧ") == "АНВАРОВИЧ"
    assert split_son_of("") == ""

    # and it holds however the name reached the form
    read = _service({**KAKHOROV, "patronymic": "",
                     "patronymic_latin": "JURAMURODUGLI"}).read_passport(b"x")
    assert read.patronymic == "ЖУРАМУРОД УГЛИ"
    assert Passport(surname="К", name="А", patronymic="ЖУРАМУРОДУГЛИ",
                    number="1").patronymic == "ЖУРАМУРОД УГЛИ"
    assert Patent(number="1", profession="П",
                  holder_patronymic="ЖУРАМУРОДУГЛИ"
                  ).holder_patronymic == "ЖУРАМУРОД УГЛИ"


def test_the_patent_still_outranks_the_passport_for_the_name() -> None:
    """The office's own order: the patent prints the ФИО in Russian, so
    when there is one it is the name — the passport supplies the rest."""
    from src.domain.enums import DocType

    service = _service(KAKHOROV, per_type={
        DocType.PATENT: {"surname": "КАХОРОВ", "name": "АББОСБЕК",
                         "patronymic": "АНВАР УГЛИ", "number": "26003 14661",
                         "citizenship": "УЗБЕКИСТАН", "profession": "ПОВАР"}})
    passport, patent = service.read_documents(b"p", b"pat")
    assert patent is not None
    assert passport.surname == "КАХОРОВ"
    # the patent's patronymic, not the passport's «АНВАРОВИЧ»
    assert passport.patronymic == "АНВАР УГЛИ"
    # and everything the patent does not carry still comes off the passport
    assert passport.series == "FB" and passport.number == "1234567"


# ------------------------------- when the two documents do not agree
def test_a_vowel_apart_is_one_man_a_consonant_apart_is_a_misreading() -> None:
    """Two offices transliterating one passport disagree about vowels and
    never about consonants — which is how a misread patent is spotted."""
    from src.domain.passport_rules import same_name

    for one, other in (("ХУДОЙБЕРДИЕВ", "ХУДАЙБЕРДИЕВ"),
                       ("ЮЛДАШЕВ", "ЙУЛДАШЕВ"),
                       ("ДЖУМАЕВ", "ЖУМАЕВ"),
                       ("ЖУРАМУРОД УГЛИ", "ЖУРАМУРОДУГЛИ"),
                       ("КАХОРОВ", "КАХОРОВ")):
        assert same_name(one, other), f"{one} / {other}"
    for one, other in (("КАХОРОВ", "КАКАРОВ"),
                       ("КАХОРОВ", "КАКОРОВ"),
                       ("САФАРОВ", "САФОНОВ"),
                       ("РАХМОНОВ", "РАХМАТОВ")):
        assert not same_name(one, other), f"{one} / {other}"


def test_a_misread_patent_does_not_overrule_the_passports_own_letters() -> None:
    """The office's own case, exactly as it happened: the patent card was
    photographed badly and read «Какаров», while the passport's Latin row
    read KAKHOROV perfectly. The form must carry КАХОРОВ."""
    from src.domain.enums import DocType

    service = _service(KAKHOROV, per_type={
        DocType.PATENT: {"surname": "КАКАРОВ", "name": "АББОСБЕК",
                         "patronymic": "ЖУРАМУРОД УГЛИ",
                         "number": "50 2600194831",
                         "citizenship": "УЗБЕКИСТАН",
                         "profession": "ПОДСОБНЫЙ РАБОЧИЙ"}})
    passport, _ = service.read_documents(b"p", b"pat")
    assert passport.surname == "КАХОРОВ"
    assert passport.patronymic == "ЖУРАМУРОД УГЛИ"


def test_a_patent_that_merely_spells_it_differently_still_wins() -> None:
    """«ХУДАЙБЕРДИЕВ» on the patent is the spelling Russia registered him
    under — a vowel apart is not a misreading, and the patent is the name."""
    from src.domain.enums import DocType

    service = _service({**KAKHOROV, "surname": "ХУДОЙБЕРДИЕВ",
                        "surname_latin": "XUDOYBERDIYEV"}, per_type={
        DocType.PATENT: {"surname": "ХУДАЙБЕРДИЕВ", "name": "АББОСБЕК",
                         "number": "1", "citizenship": "УЗБЕКИСТАН",
                         "profession": "ПОВАР"}})
    passport, _ = service.read_documents(b"p", b"pat")
    assert passport.surname == "ХУДАЙБЕРДИЕВ"


def test_without_a_latin_row_the_patent_wins_as_the_office_asked() -> None:
    """Nothing to prove the passport's spelling by — so the patent, printed
    in Russian, is the name, exactly as before."""
    from src.domain.enums import DocType

    service = _service({**KAKHOROV, "surname": "КАХОРОВ",
                        "surname_latin": ""}, per_type={
        DocType.PATENT: {"surname": "КАКАРОВ", "name": "АББОСБЕК",
                         "number": "1", "citizenship": "УЗБЕКИСТАН",
                         "profession": "ПОВАР"}})
    passport, _ = service.read_documents(b"p", b"pat")
    assert passport.surname == "КАКАРОВ"


# ------------------------------------------------- the strip is not read
def test_the_machine_strip_is_neither_read_nor_complained_about() -> None:
    """The office asked for it to go. A page whose strip is unreadable —
    or absent — reads exactly like any other, with no warning anywhere."""
    passport = _service(
        KAKHOROV,
        text="P<UZBKAKHOROV<<ABBOSBEK<<<<<<<<<<<<<<<<<<<<<\n"
             "FB12345671UZB0402220M3302150<<<<<<<<<<<<<<00").read_passport(b"x")
    assert passport.surname == "КАХОРОВ"
    assert not hasattr(passport, "mrz_warning")
    assert not hasattr(passport, "mrz_checked")


def test_nothing_in_the_program_still_warns_about_a_machine_zone() -> None:
    """No check digits, no verdict, no warning — none of it is left."""
    import inspect

    from src.ocr import service
    from src.services import generation_service
    from src.ui.views import process_view

    for module in (service, process_view, generation_service):
        assert "mrz" not in inspect.getsource(module).lower(), module.__name__


def test_the_strip_is_a_spelling_aid_and_the_prompt_says_only_that() -> None:
    """The office's question, in its own words: «Mistral used to read it
    right — why not now?» Because the prompt had been told to ignore the
    strip outright, and the strip is where the letters are machine-printed.

    It is a spelling aid for the LATIN name and nothing else: it must never
    take away a father's name that the printed rows carry, because many
    countries put none in it.
    """
    from src.ai.prompts import _PASSPORT

    assert "IGNORE the" not in _PASSPORT, "бутунлай тақиқлаб қўйилган"
    assert "most reliable place" in _PASSPORT
    assert "the strip has the letters right" in _PASSPORT
    # ...but never as a source of the fields it does not carry
    assert "father's name IS there" in _PASSPORT
    assert "no issuing authority" in _PASSPORT
    # and the word break the strip spells with «<»
    assert "JURAMUROD UGLI" in _PASSPORT
    assert "K-A-K-H-O-R-O-V" in _PASSPORT


# --------------------------------------- the check digit taken back off
class TestStripDocumentCheckDigit:
    """«FB22548766» → «FB2254876».

    This is the ONE piece of that arithmetic worth keeping, and it warns
    about nothing: the model reads the number off the strip, where the nine
    document characters are followed by their check digit, and hands both
    back. That extra digit went straight onto registrations — the office
    filed «FB22548766» for a passport that is really «FB2254876».
    """

    def test_the_owners_own_case(self) -> None:
        assert strip_document_check_digit("FB22548766") == "FB2254876"
        assert strip_document_check_digit("fb 2254876 6") == "FB2254876"

    def test_a_correct_reading_is_left_alone(self) -> None:
        assert strip_document_check_digit("FB2254876") == "FB2254876"
        assert strip_document_check_digit("AA1234567") == "AA1234567"

    def test_an_unproven_tenth_digit_is_kept(self) -> None:
        """Only arithmetic removes a digit — never the length alone."""
        assert strip_document_check_digit("FB22548767") == "FB22548767"

    def test_digits_only_documents_are_never_touched(self) -> None:
        """A Russian internal passport is 4+6 = ten digits with no letters;
        one time in ten the arithmetic would «prove» the wrong thing."""
        for base in ("452510523", "401234567"):
            whole = base + check_digit(base)      # last digit DOES add up
            assert strip_document_check_digit(whole) == whole

    def test_the_service_splits_the_cleaned_document_back(self) -> None:
        from src.ocr.service import _clean_document

        assert _clean_document("FB", "22548766") == ("FB", "2254876")
        assert _clean_document("", "FB22548766") == ("FB", "2254876")
        assert _clean_document("45 25", "105235") == ("45 25", "105235")

    def test_the_trud_ppu_reader_strips_it_too(self) -> None:
        from src.controllers.trud_ppu_controller import _passport

        assert _passport("FB22548766 / 072501692992") == "FB2254876"
        assert _passport("FB 2254876") == "FB2254876"

    def test_no_api_and_no_key_is_involved(self) -> None:
        """The whole thing is arithmetic on text already in hand."""
        import inspect

        from src.domain import document_number

        source = inspect.getsource(document_number)
        for forbidden in ("requests", "urllib", "http", "api_key"):
            assert forbidden not in source, forbidden
