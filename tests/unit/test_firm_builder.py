"""A firm typed in by hand: the program writes its two Word templates.

The point of the pair it builds is that it is filled by the *ordinary* path —
the same :mod:`src.services.docx_worker` that fills a firm's own uploaded Word
file — so these tests end where every other firm's do: a filled document.
"""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import pytest

docx = pytest.importorskip("docx")

from src.config import paths  # noqa: E402
from src.domain.documents import Passport, Patent  # noqa: E402
from src.domain.enums import Gender, LegalForm  # noqa: E402
from src.domain.firm_details import FirmDetails  # noqa: E402
from src.domain.trud_firm import TrudFirm  # noqa: E402
from src.services import firm_builder  # noqa: E402
from src.services.trud_service import TrudService  # noqa: E402

OOO = dict(
    legal_form=LegalForm.OOO,
    name='ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "СФЕРА"',
    short_name='ООО "СФЕРА"', inn="7743447264", kpp="774301001",
    ogrn="1247700301133", okved="42.99",
    address="141008, обл. Московская, г. Мытищи, ул. Мира, д. 37",
    district="г.о. Мытищи",
    mvd_office="ОПВМ ОМВД РОССИИ ПО Г.О. МЫТИЩИ МОСКОВСКОЙ ОБЛАСТИ",
    director="Нуар А. В.", phone="+7 (812) 740 63 70",
)
IP = dict(
    legal_form=LegalForm.IP, name="Индивидуальный предприниматель Гордиенко А. В.",
    short_name="ИП Гордиенко А. В.", inn="772345678901", ogrn="321774600123456",
    address="г. Москва, ул. Мира, д. 1", district="г. Москва",
    mvd_office="ОВМ ОМВД РОССИИ ПО РАЙОНУ ЮЖНОЕ БУТОВО Г. МОСКВЫ",
    director="Гордиенко А. В.",
)

PASSPORT = Passport(
    surname="НАЗАРОВ", name="МУРОДУЛЛО", patronymic="ХАИТАЛИЕВИЧ",
    number="1234567", series="FB", birth_date=date(2004, 2, 22),
    issue_date=date(2023, 2, 16), issued_by="МВД 99999",
    nationality="УЗБЕКИСТАН", gender=Gender.MALE, birth_place="УЗБЕКИСТАН")
PATENT = Patent(
    series="50", number="2600017664", issue_date=date(2026, 4, 14),
    issued_by="ГУ МВД России по Московской области", profession="Штукатур",
    blank_series="ПР", blank_number="4875056")


@pytest.fixture(autouse=True)
def _appdata(monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", tempfile.mkdtemp())
    paths.data_dir.cache_clear()
    yield
    paths.data_dir.cache_clear()


def _lines(path: Path) -> list[str]:
    return [p.text for p in docx.Document(str(path)).paragraphs if p.text.strip()]


def _joined(path: Path) -> str:
    return "\n".join(" ".join(line.split()) for line in _lines(path))


def _built(tmp_path: Path, base: dict | None = None, **overrides):
    firm = FirmDetails(**{**(base or OOO), **overrides})
    trud, uved = firm_builder.build(firm, tmp_path, header_date="01 января 2026")
    return firm, trud, uved


# ---------------------------------------------------------- what it writes


def test_both_templates_are_written(tmp_path) -> None:
    _firm, trud, uved = _built(tmp_path)
    assert trud.name == firm_builder.TRUD_NAME
    assert uved.name == firm_builder.UVED_NAME
    assert trud.exists() and uved.exists()


def test_the_firms_requisites_are_printed_once_and_correctly(tmp_path) -> None:
    _firm, trud, uved = _built(tmp_path)
    for path in (trud, uved):
        body = _joined(path)
        for value in ("7743447264", "774301001", "1247700301133",
                      "г. Мытищи, ул. Мира, д. 37"):
            assert body.count(value) == 1, (path.name, value)


def test_an_ip_gets_ogrnip_and_no_kpp(tmp_path) -> None:
    _firm, trud, uved = _built(tmp_path, IP)
    body = _joined(uved)
    assert "ОГРНИП 321774600123456" in body.replace("\t", " ")
    assert "КПП" not in body
    assert "Индивидуальный предприниматель" in body
    assert "действующий на основании свидетельства" in _joined(trud)


def test_a_company_signs_through_its_director_in_the_genitive(tmp_path) -> None:
    _firm, trud, _uved = _built(tmp_path)
    assert "в лице Генерального директора Нуар А. В." in _joined(trud)
    assert "на основании Устава" in _joined(trud)


def test_a_position_the_program_cannot_decline_is_left_as_typed(tmp_path) -> None:
    """Better the office's own words than a mangled guess at Russian grammar."""
    _firm, trud, _uved = _built(tmp_path, director_position="Врио руководителя")
    assert "в лице Врио руководителя Нуар А. В." in _joined(trud)


def test_the_mvd_office_lands_on_the_uvedomlenie(tmp_path) -> None:
    _firm, _trud, uved = _built(tmp_path)
    assert OOO["mvd_office"] in _joined(uved)


def test_the_contract_carries_a_real_body_not_a_placeholder(tmp_path) -> None:
    _firm, trud, _uved = _built(tmp_path)
    body = _joined(trud)
    for section in ("1. ПРЕДМЕТ ДОГОВОРА", "4. ОПЛАТА ТРУДА",
                    "5. РАБОЧЕЕ ВРЕМЯ И ВРЕМЯ ОТДЫХА",
                    "9. АДРЕСА, РЕКВИЗИТЫ И ПОДПИСИ СТОРОН"):
        assert section in body, section
    assert len(_lines(trud)) > 40


def test_no_document_number_is_invented(tmp_path) -> None:
    """The office's own numbering — the program must not make one up."""
    _firm, trud, _uved = _built(tmp_path)
    assert "ТРУДОВОЙ ДОГОВОР № ______" in _joined(trud)


def test_the_stamp_is_embedded_when_one_is_given(tmp_path) -> None:
    png = tmp_path / "stamp.png"
    png.write_bytes(_PNG)
    _firm, trud, _uved = _built(tmp_path, stamp_path=png)
    doc = docx.Document(str(trud))
    assert any("graphicData" in p._p.xml for p in doc.paragraphs), "no picture"


def test_a_stamp_that_is_not_a_png_is_refused() -> None:
    with pytest.raises(ValueError):
        FirmDetails(**{**OOO, "stamp_path": Path("pechat.jpg")})


# ------------------------------------------------------------- requisites


@pytest.mark.parametrize("bad, message", [
    ({"inn": "12345"}, "ИНН"),
    ({"kpp": "1234"}, "КПП"),
    ({"ogrn": "123"}, "ОГРН"),
    ({"name": ""}, "номи"),
])
def test_a_requisite_of_the_wrong_length_is_refused(bad, message) -> None:
    with pytest.raises(ValueError) as exc:
        FirmDetails(**{**OOO, **bad})
    assert message in str(exc.value)


def test_an_ip_may_not_carry_a_kpp() -> None:
    with pytest.raises(ValueError):
        FirmDetails(**{**IP, "kpp": "774301001"})


def test_spaces_and_dashes_in_a_number_are_forgiven() -> None:
    firm = FirmDetails(**{**OOO, "inn": "77 43 44 72 64"})
    assert firm.inn == "7743447264"


# ------------------------------------------------------------- end to end


def test_a_built_pair_fills_for_a_worker_like_any_other_firm(tmp_path) -> None:
    details, trud, uved = _built(tmp_path)
    firm = TrudFirm(name=details.name, internal_code="sfera",
                    trud_template_path=trud, uved_template_path=uved,
                    details=details)

    result = TrudService().generate(PASSPORT, PATENT, firm,
                                    form_date=date(2026, 7, 28),
                                    profession="Штукатур",
                                    output_dir=tmp_path / "out")
    for path in (result.trud_path, result.uved_path):
        body = _joined(path).replace("\t", " ")
        for value in ("Назаров", "Муродулло", "Хаиталиевич", "22.02.2004",
                      "Мужской", "Узбекистан", "FB", "1234567", "16.02.2023",
                      "МВД 99999", "Штукатур"):
            assert value in body, (path.name, value)
        assert OOO["name"] in body or 'ООО "СФЕРА"' in body

    uved_body = _joined(result.uved_path).replace("\t", " ")
    assert "Серия 50" in uved_body and "Номер 2600017664" in uved_body
    assert "Номер бланка 4875056" in uved_body
    assert "Дата заключения договора 28.07.2026" in uved_body
    assert "Регион Московская область" in uved_body
    assert "28 июля 2026 года" in _joined(result.trud_path)


def test_every_worker_line_of_the_built_pair_is_actually_filled(tmp_path) -> None:
    """A label left with an empty gap would print as a blank line in Word."""
    details, trud, uved = _built(tmp_path)
    firm = TrudFirm(name=details.name, internal_code="sfera",
                    trud_template_path=trud, uved_template_path=uved,
                    details=details)
    result = TrudService().generate(PASSPORT, PATENT, firm,
                                    form_date=date(2026, 7, 28),
                                    profession="Штукатур",
                                    output_dir=tmp_path / "out")

    # «Адрес места жительства» is the one the office types in Word by hand
    for path in (result.trud_path, result.uved_path):
        for line in _lines(path):
            if "\t" in line and not line.startswith("Адрес места жительства"):
                label, _, value = line.partition("\t")
                assert value.strip(), (path.name, label)


def test_the_service_registers_a_typed_firm_and_keeps_its_stamp(tmp_path) -> None:
    class _Repo:
        def __init__(self) -> None:
            self.saved: list[TrudFirm] = []

        def by_internal_code(self, code):
            return next((f for f in self.saved if f.internal_code == code), None)

        def upsert(self, firm):
            self.saved.append(firm)

    from src.services.trud_service import TrudFirmService

    png = tmp_path / "desktop" / "stamp.png"
    png.parent.mkdir()
    png.write_bytes(_PNG)

    repo = _Repo()
    firm = TrudFirmService(repo).create_manual(
        FirmDetails(**{**OOO, "stamp_path": png}), "SFERA",
        today=date(2026, 7, 28))

    assert repo.saved == [firm]
    assert firm.internal_code == "sfera"
    assert firm.details is not None and firm.details.inn == "7743447264"
    # the печать is kept beside the templates, not left on the desktop
    assert firm.details.stamp_path is not None
    assert firm.details.stamp_path.parent == firm.trud_template_path.parent
    assert firm.details.stamp_path.exists()
    assert firm.trud_template_path.exists() and firm.uved_template_path.exists()
    assert "28 июля 2026 года" in _joined(firm.trud_template_path)


def test_the_same_code_cannot_be_used_twice(tmp_path) -> None:
    from src.common.errors import ValidationError
    from src.services.trud_service import TrudFirmService

    class _Repo:
        def __init__(self) -> None:
            self.saved: list[TrudFirm] = []

        def by_internal_code(self, code):
            return next((f for f in self.saved if f.internal_code == code), None)

        def upsert(self, firm):
            self.saved.append(firm)

    service = TrudFirmService(_Repo())
    service.create_manual(FirmDetails(**OOO), "sfera")
    with pytest.raises(ValidationError):
        service.create_manual(FirmDetails(**OOO), "sfera")


def test_the_requisites_survive_a_restart(tmp_path) -> None:
    from src.database.connection import Database
    from src.database.repositories.trud_firm_repo import TrudFirmRepository
    from src.services.trud_service import TrudFirmService

    db = Database(tmp_path / "ofis.db")
    db.migrate()
    repo = TrudFirmRepository(db)
    saved = TrudFirmService(repo).create_manual(FirmDetails(**OOO), "sfera")

    back = repo.by_internal_code("sfera")
    assert back is not None and back.id == saved.id
    assert back.details is not None
    for field in ("inn", "kpp", "ogrn", "okved", "address", "district",
                  "mvd_office", "director", "director_position", "short_name"):
        assert getattr(back.details, field) == getattr(saved.details, field), field
    assert back.details.legal_form is LegalForm.OOO


def test_a_firm_that_uploaded_templates_has_no_requisites(tmp_path) -> None:
    """``details`` is what tells the two kinds of firm apart on read."""
    from src.database.connection import Database
    from src.database.repositories.trud_firm_repo import TrudFirmRepository

    db = Database(tmp_path / "ofis.db")
    db.migrate()
    repo = TrudFirmRepository(db)
    repo.upsert(TrudFirm(name="МЕГАПОЛИС", internal_code="mega",
                         trud_template_path=tmp_path / "t.pdf",
                         uved_template_path=tmp_path / "u.pdf"))
    assert repo.by_internal_code("mega").details is None


#: 1×1 transparent PNG — enough for Word to embed.
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000a49444154789c636000000200010005fe02fe"
    "0000000049454e44ae426082")
