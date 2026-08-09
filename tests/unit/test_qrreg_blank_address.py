"""КРКОД РЕГ — which address goes on which blank, and asking for it.

The office keeps one blank per dormitory. Two things follow from that, and
both were asked for by name: choosing a blank on the computer should bring
back the address it was last registered with, and the bot should stop taking
that address silently and ask every time.
"""

from __future__ import annotations

import json
import tempfile

import pytest
from src.config import paths
from src.services.qrreg_service import (
    KEY_ADDRESSES,
    KEY_BLANK_ADDRESS,
    QrRegService,
    address_key,
    address_label,
)


class _Settings:
    """Settings that live for the length of one test."""

    def __init__(self) -> None:
        self._kept: dict[str, str] = {}

    def get(self, key, default=None):
        return self._kept.get(key, default)

    def set(self, key, value) -> None:
        self._kept[key] = value


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    sandbox = tempfile.mkdtemp()
    monkeypatch.setenv("XDG_DATA_HOME", sandbox)
    monkeypatch.setenv("LOCALAPPDATA", sandbox)
    paths.data_dir.cache_clear()
    yield
    paths.data_dir.cache_clear()


def _dorm(street: str, dom: str = "45", label: str = "") -> dict:
    return {"label": label, "addr_subject": "г Москва", "addr_district": "",
            "addr_punkt": "г Москва", "addr_street": street, "dom": dom,
            "korpus": "", "kvartira": "12", "code": "7788",
            "host_surname": "Петров", "host_name": "Иван",
            "host_patronymic": "Сергеевич"}


@pytest.fixture()
def service():
    made = QrRegService(_Settings())
    for dorm in (_dorm("ул Тагильская", "45"), _dorm("ул Юных Ленинцев", "8")):
        made.remember_address(dorm)
    return made


# --------------------------------------------------------- what names one
def test_two_savings_of_the_same_place_are_one_entry(service) -> None:
    """The label is not the identity — the office renames those. Where the
    place actually is, is."""
    before = len(service.addresses())
    service.remember_address(_dorm("ул Тагильская", "45", label="Общага №1"))
    assert len(service.addresses()) == before
    assert service.addresses()[0]["label"] == "Общага №1"


def test_a_dormitory_is_named_by_its_label_or_by_where_it_is() -> None:
    assert address_label(_dorm("ул Тагильская", label="Общага №1")) == "Общага №1"
    said = address_label(_dorm("ул Тагильская", "45"))
    assert "ул Тагильская" in said and "45" in said
    assert address_label({}) == "— номсиз —"


def test_spacing_and_case_do_not_make_a_different_place() -> None:
    loose = _dorm("ул   Тагильская", "45")
    loose["addr_subject"] = "Г МОСКВА"
    assert address_key(loose) == address_key(_dorm("ул Тагильская", "45"))


# ------------------------------------------------- the blank's own address
def test_a_blank_with_no_history_offers_nothing(service, tmp_path) -> None:
    assert service.address_for_blank(tmp_path / "Общага-1.pdf") is None
    assert service.address_for_blank(None) is None


def test_the_address_comes_back_with_the_blank_it_was_used_on(
        service, tmp_path) -> None:
    """«бланка танлаганимда ўша бланка билан охирги марта ишлатган адрес
    автоматик чиқсин»."""
    first, second = tmp_path / "Общага-1.pdf", tmp_path / "Общага-2.pdf"
    service.remember_blank_address(first, _dorm("ул Тагильская", "45"))
    service.remember_blank_address(second, _dorm("ул Юных Ленинцев", "8"))

    assert service.address_for_blank(first)["addr_street"] == "ул Тагильская"
    assert service.address_for_blank(second)["addr_street"] == "ул Юных Ленинцев"


def test_a_blank_moved_to_another_folder_keeps_its_address(
        service, tmp_path) -> None:
    """Tied by the blank's NAME, not its path — the office moves folders."""
    service.remember_blank_address(tmp_path / "Общага-1.pdf",
                                   _dorm("ул Тагильская", "45"))
    elsewhere = tmp_path / "eski" / "Общага-1.pdf"
    assert service.address_for_blank(elsewhere)["addr_street"] == "ул Тагильская"


def test_using_a_blank_again_moves_its_address_on(service, tmp_path) -> None:
    blank = tmp_path / "Общага-1.pdf"
    service.remember_blank_address(blank, _dorm("ул Тагильская", "45"))
    service.remember_blank_address(blank, _dorm("ул Юных Ленинцев", "8"))
    assert service.address_for_blank(blank)["addr_street"] == "ул Юных Ленинцев"


def test_an_address_deleted_from_the_book_is_not_conjured_up(
        tmp_path) -> None:
    """The tie is a reference. If the dormitory is gone, so is the answer —
    better nothing than an address the office no longer keeps."""
    settings = _Settings()
    service = QrRegService(settings)
    dorm = _dorm("ул Тагильская", "45")
    service.remember_address(dorm)
    service.remember_blank_address(tmp_path / "Общага-1.pdf", dorm)
    settings.set(KEY_ADDRESSES, json.dumps([]))
    assert service.address_for_blank(tmp_path / "Общага-1.pdf") is None


def test_a_ruined_setting_is_not_a_crash(tmp_path) -> None:
    settings = _Settings()
    settings.set(KEY_BLANK_ADDRESS, "{ бузилган")
    assert QrRegService(settings).blank_addresses() == {}
    settings.set(KEY_BLANK_ADDRESS, json.dumps(["рўйхат бўлмаслиги керак"]))
    assert QrRegService(settings).blank_addresses() == {}


# ------------------------------------------------------------ in the bot
class _Controller:
    def __init__(self, service: QrRegService) -> None:
        self._service = service

    def addresses(self):
        return self._service.addresses()

    def address_for_blank(self, template):
        return self._service.address_for_blank(template)

    @staticmethod
    def address_label(entry):
        return address_label(entry)


def test_the_bot_asks_for_the_address_now(service) -> None:
    """«ботда регистрация адресларини сорамайапти, сорасин доим» — it used
    to take the newest saved one without a word."""
    from src.controllers.ofis_modules import MODULES

    module = next(m for m in MODULES if m.key == "qrreg")
    fields = [a.field for a in module.asks]
    assert "address" in fields, "адрес сўралмаяпти"
    assert fields.index("address") == 0, "адрес биринчи сўралсин"
    assert module.asks[0].kind == "choice"


def test_the_bot_lists_every_saved_dormitory(service) -> None:
    from src.controllers.ofis_modules import MODULES

    ask = next(m for m in MODULES if m.key == "qrreg").asks[0]
    offered = ask.options({"qrreg": _Controller(service)}, {})
    assert len(offered) == 2
    assert any("Тагильская" in o for o in offered)


def test_the_blanks_own_address_is_offered_first(service, tmp_path) -> None:
    """Pressing «Тайёрла» without choosing takes option one, so option one
    had better be the address that blank is actually used with."""
    from src.controllers.ofis_modules import MODULES

    blank = tmp_path / "Общага-2.pdf"
    service.remember_blank_address(blank, _dorm("ул Юных Ленинцев", "8"))
    ask = next(m for m in MODULES if m.key == "qrreg").asks[0]

    offered = ask.options({"qrreg": _Controller(service)},
                          {"target": str(blank)})
    assert "Юных Ленинцев" in offered[0]
    assert len(offered) == 2, "адрес рўйхатда иккита бўлиб қолди"


def test_the_bot_refuses_before_asking_when_nothing_is_saved() -> None:
    from src.controllers.ofis_modules import MODULES

    module = next(m for m in MODULES if m.key == "qrreg")
    empty = _Controller(QrRegService(_Settings()))
    assert "Адрес" in module.ready({"qrreg": empty})


def test_a_list_that_cannot_be_built_is_empty_not_a_crash() -> None:
    """The poller must survive a section whose settings are in pieces."""
    from src.controllers.ofis_modules import MODULES

    class _Broken:
        def addresses(self):
            raise RuntimeError("сақлагич бузилди")

    ask = next(m for m in MODULES if m.key == "qrreg").asks[0]
    assert ask.options({"qrreg": _Broken()}, {}) == []
