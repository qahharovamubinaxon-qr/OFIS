"""МЕРКУРИЙ — ёзув, сайт саҳифаси ва бланка."""

from datetime import date

import fitz
import pytest
from src.domain.vetdoc import (
    CODE_LEN,
    Animal,
    DocRef,
    Shop,
    Treatment,
    VetRecord,
    new_code,
)
from src.pdf.vetdoc_renderer import output_name, render
from src.services.vetdoc_page import index_html, page_html
from src.services.vetdoc_service import VetDocService, from_dict, to_dict


class _Settings:
    """Созламанинг энг кичик ўрнига қўювчиси."""

    def __init__(self) -> None:
        self._values: dict[str, object] = {}

    def get(self, key, default=None):
        return self._values.get(key, default)

    def set(self, key, value) -> None:
        self._values[key] = value


@pytest.fixture
def appdata(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    from src.config import paths
    paths.data_dir.cache_clear()
    yield tmp_path
    paths.data_dir.cache_clear()


def _flat(text: str) -> str:
    """Матнни битта қаторга келтириш.

    HTML да жумла манба файлда қаторга бўлинган, PDF дан эса бўшлиқ `` ``
    бўлиб чиқади — текширувни шу иккаласидан ҳоли қилади.
    """
    return " ".join(text.replace(" ", " ").split())


def _shop(site: str = "https://shop.example/vet") -> Shop:
    return Shop(name="МЕРКУРИЙ", legal="ИП МЕРКУРИЙ",
                address="г. Ижевск, ул. Примерная, 1",
                phone="+7 900 000-00-00", site=site, inn="1234567890")


def _record() -> VetRecord:
    return VetRecord(
        number="MR-2026-000142", issued=date(2026, 4, 29),
        product="птица", species="курица (0105)", title="Петух",
        volume="4 головы", buyer="Иванов Иван Иванович",
        vet_name="Петрова А. С.",
        animals=[Animal(group_no="1", nickname="б/н", sex="Самец",
                        breed="Петух", age="01.2026", weight="1", count="1")],
        treatments=[Treatment(kind="обработка", name="эндопаразиты",
                              done="29.04.2026", drug="Альбен")],
        docs=[DocRef(series="МР", number="000142", issued="29.04.2026",
                     kind="товарный чек")],
    )


def test_code_is_unambiguous():
    codes = {new_code() for _ in range(200)}
    assert len(codes) > 190                      # такрор деярли учрамайди
    for code in codes:
        assert len(code) == CODE_LEN
        assert not set(code) & set("O0I1")       # адашадиган белгилар йўқ


def test_record_round_trip():
    record = _record()
    back = from_dict(to_dict(record))
    assert back.code == record.code
    assert back.issued == date(2026, 4, 29)
    assert back.title == "Петух"
    assert [a.breed for a in back.animals] == ["Петух"]
    assert [t.drug for t in back.treatments] == ["Альбен"]
    assert [d.number for d in back.docs] == ["000142"]


def test_from_dict_survives_unknown_keys():
    data = to_dict(_record())
    data["registry_extra"] = "кейин қўшилган майдон"
    data["animals"][0]["unknown"] = "x"
    assert from_dict(data).title == "Петух"


def test_page_has_every_registry_section():
    html = _flat(page_html(_record(), _shop()))
    for section in ("Общие сведения", "Информация о продукции",
                    "Сведения о транспорте", "Сведения об оформлении",
                    "Сведения о происхождении продукции",
                    "Сведения о получателе", "Сведения об отправителе",
                    "Сведения о документах", "Опись живых животных"):
        assert section in html
    # бўш майдон ҳам реестрдагидек кўринади
    assert "Номер производственной партии" in html
    assert "не является ветеринарным сопроводительным документом" in html


def test_page_escapes_values():
    """Оператор ёзган матн ҳеч қачон жонли HTML бўлмайди.

    Саҳифанинг ўзида тил алмаштирадиган ``<script>`` бор, шунинг учун
    текширув айнан киритилган қийматга қаралади.
    """
    record = _record()
    record.buyer = '<script>alert("x")</script>'
    html = page_html(record, _shop())
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html


def test_index_lists_the_code():
    html = _flat(index_html([_record()], _shop()))
    record = _record()
    assert ".html" in html
    assert "Проверка справки" in html
    assert record.number[:3] in html


def test_blank_prints_filled_rows_only():
    record = _record()
    doc = render(record, _shop(), link="https://shop.example/vet/X.html")
    text = _flat("".join(page.get_text() for page in doc))
    doc.close()
    assert "Петух" in text
    assert "Иванов Иван Иванович" in text
    # тўлдирилмаган майдон қоғозга чиқмайди
    assert "Место для карантинирования" not in text
    assert "не является ветеринарным сопроводительным" in text


def test_blank_fits_one_page_for_a_small_sale():
    doc = render(_record(), _shop())
    assert doc.page_count == 1
    doc.close()


def test_blank_carries_a_scannable_qr():
    link = "https://shop.example/vet/ABC123.html"
    doc = render(_record(), _shop(), link=link)
    page = doc[0]
    pixmap = page.get_pixmap(dpi=200)
    png = pixmap.tobytes("png")
    doc.close()
    cv2 = pytest.importorskip("cv2")
    import numpy as np
    image = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_GRAYSCALE)
    found, _points = cv2.QRCodeDetector().detectAndDecode(image)[:2]
    assert found == link


def test_output_name_uses_the_buyer():
    record = _record()
    assert output_name(record) == f"ИВАНОВ_{record.code}.pdf"
    record.buyer = ""
    assert output_name(record) == "MR-2026-000142.pdf"


def test_publish_writes_record_page_and_pdf(appdata):
    service = VetDocService(_Settings())
    service.save_shop(_shop())
    record = _record()
    result = service.publish(record)
    assert result.pdf.exists()
    assert result.page.exists()
    assert result.link == f"https://shop.example/vet/{record.code}.html"
    assert fitz.open(str(result.pdf)).page_count >= 1
    # ёзув ва рўйхат ҳам ёзилган
    assert service.load(record.code).title == "Петух"
    index = (result.page.parent / "index.html").read_text(encoding="utf-8")
    assert record.code in index
    assert [r.code for r in service.records()] == [record.code]


def test_publish_needs_a_product(appdata):
    from src.common.errors import ValidationError

    service = VetDocService(_Settings())
    with pytest.raises(ValidationError):
        service.publish(VetRecord())


def test_link_falls_back_to_the_code_without_a_site(appdata):
    service = VetDocService(_Settings())
    service.save_shop(_shop(site=""))
    record = _record()
    assert service.link_for(record) == record.code


def test_site_is_rebuilt_from_the_records(appdata):
    service = VetDocService(_Settings())
    service.save_shop(_shop())
    first, second = _record(), _record()
    service.publish(first)
    service.publish(second)
    folder = service.rebuild_site()
    assert (folder / f"{first.code}.html").exists()
    assert (folder / f"{second.code}.html").exists()
    index = (folder / "index.html").read_text(encoding="utf-8")
    assert first.code in index and second.code in index
