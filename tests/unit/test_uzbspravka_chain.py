"""One worker's four certificates, from the passport to four saved PDFs.

The chain the office described: draw → photograph → imgbb → qrixtools, which
locks the picture behind the four-digit code printed at the foot → the QR of
that short link → saved. Nothing here goes near the network: the uploader and
the link-maker are handed in, which is also how the real ones are swapped.
"""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import fitz
import pytest
from src.common.errors import ValidationError
from src.config import paths
from src.domain.documents import Passport
from src.services import uzbspravka_service as store
from src.services.qrixtools import SETTING_KEY, ShortLink
from src.services.uzbspravka_service import (
    SheetNumbers,
    UzbSpravkaService,
    data_of,
)


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    sandbox = tempfile.mkdtemp()
    monkeypatch.setenv("XDG_DATA_HOME", sandbox)
    monkeypatch.setenv("LOCALAPPDATA", sandbox)
    paths.data_dir.cache_clear()
    yield
    paths.data_dir.cache_clear()


class _Settings:
    def __init__(self, **kept) -> None:
        self._kept = kept

    def get(self, key, default=""):
        return self._kept.get(key, default)


def _keys() -> _Settings:
    from src.services.imgbb import KEY_IMGBB

    return _Settings(**{KEY_IMGBB: "imgbb-key", SETTING_KEY: "qrix-key"})


class _Site:
    """imgbb and qrixtools, standing still so the chain can be watched."""

    def __init__(self) -> None:
        self.uploaded: list[bytes] = []
        self.asked: list[tuple[str, str]] = []      # (link, code)

    def upload(self, png: bytes, key: str, name: str = "") -> str:
        assert key, "imgbb калитисиз юборилди"
        self.uploaded.append(png)
        return f"https://i.ibb.co/{len(self.uploaded)}/{name}.png"

    def link(self, target: str, code: str, title: str = "", *,
             key: str = "") -> ShortLink:
        assert key, "qrixtools калитисиз юборилди"
        self.asked.append((target, code))
        return ShortLink(id=code, url=f"https://qrixtools.com/s/{code}")


def _printed(pdf: Path) -> str:
    """What one certificate says, read back off the page.

    The embedded font hands its hyphen back as a SOFT hyphen and its space as
    a no-break space, so «1547-1548» would never be found by eye. That is how
    the glyphs map, not what was written — both are put back here.
    """
    with fitz.open(pdf) as doc:
        return doc[0].get_text().replace("\xad", "-").replace("\xa0", " ")


def _blanks(tmp_path: Path, sheets=(1, 2, 3, 4)) -> None:
    made = tmp_path / "blank.pdf"
    with fitz.open() as doc:
        doc.new_page(width=595, height=842)
        doc.save(str(made))
    for sheet in sheets:
        store.set_blank(sheet, made)


def _seal(tmp_path: Path, firm: str = "ООО СФЕРА") -> None:
    made = tmp_path / "seal.png"
    with fitz.open() as doc:
        page = doc.new_page(width=80, height=80)
        page.draw_circle(fitz.Point(40, 40), 30)
        page.get_pixmap(dpi=72).save(str(made))
    store.add_seal(firm, made)


def _worker(firm: str = "ООО СФЕРА"):
    passport = Passport(
        surname="ЭРГАШЕВ", name="УМИДЖОН", patronymic="ШУХРАТ УГЛИ",
        series="FA", number="3445084", birth_date=date(2002, 10, 2),
        nationality="УЗБЕКИСТАН", surname_latin="ERGASHEV",
        name_latin="UMIDJON", patronymic_latin="SHUKHRAT UGLI")
    return data_of(passport, firm=firm, pinfl="50210025720042")


def _ready(tmp_path: Path):
    _blanks(tmp_path)
    _seal(tmp_path)
    return UzbSpravkaService(_keys()), _Site(), _worker()


# ----------------------------------------------------------- the worker
def test_the_passport_gives_the_worker_the_certificates_name_him_by() -> None:
    data = _worker()
    assert data.fio() == "ЭРГАШЕВ УМИДЖОН ШУХРАТ УГЛИ"
    assert data.latin_name == "ERGASHEV UMIDJON SHUKHRAT UGLI"
    assert data.passport == "FA3445084", "серия ва номер бирга ёзилади"
    assert data.pinfl == "50210025720042"
    assert data.birth_date == date(2002, 10, 2)


# ------------------------------------------------------------ the chain
def test_all_four_are_drawn_saved_and_gated(tmp_path) -> None:
    service, site, data = _ready(tmp_path)
    made = service.generate(data, uploader=site.upload, linker=site.link)

    assert sorted(made.pdfs) == [1, 2, 3, 4]
    for sheet, path in made.pdfs.items():
        assert path.exists() and path.stat().st_size > 0
        assert path.name == f"ЭРГАШЕВ_УМИДЖОН_{sheet}.pdf"
    assert len(site.uploaded) == 4, "ҳар справка ўзи юкланиши керак"
    assert set(made.links) == {1, 2, 3, 4}


def test_every_certificate_is_locked_behind_its_own_code(tmp_path) -> None:
    """A sheet that travels alone must open itself and nothing else."""
    service, site, data = _ready(tmp_path)
    made = service.generate(data, uploader=site.upload, linker=site.link)

    codes = list(made.codes.values())
    assert len(set(codes)) == 4, "тўртта справкада битта код қолди"
    assert all(len(c) == 4 and c.isdigit() for c in codes)
    # and the code sent to the site is the one printed on that certificate
    assert [code for _link, code in site.asked] == [made.codes[s]
                                                    for s in (1, 2, 3, 4)]


def test_the_code_on_the_paper_is_the_code_in_the_link(tmp_path) -> None:
    service, site, data = _ready(tmp_path)
    made = service.generate(data, uploader=site.upload, linker=site.link)
    printed = _printed(made.pdfs[1])
    assert made.codes[1] in printed, "код қоғозга тушмади"
    assert made.codes[1] in made.links[1]


def test_the_seal_and_the_qr_are_both_on_every_sheet(tmp_path) -> None:
    service, site, data = _ready(tmp_path)
    made = service.generate(data, uploader=site.upload, linker=site.link)
    for path in made.pdfs.values():
        with fitz.open(path) as doc:
            assert len(doc[0].get_images(full=True)) == 2, (
                f"{path.name}: печать ёки QR тушмади")


def test_only_the_certificates_asked_for_are_made(tmp_path) -> None:
    service, site, data = _ready(tmp_path)
    made = service.generate(data, sheets=(2, 4), uploader=site.upload,
                            linker=site.link)
    assert sorted(made.pdfs) == [2, 4]
    assert len(site.uploaded) == 2


# ----------------------------------------------------------- the numbers
def test_a_number_the_office_typed_is_never_overwritten(tmp_path) -> None:
    """When the portal has already numbered a certificate, THAT is the number."""
    service, site, data = _ready(tmp_path)
    made = service.generate(
        data, sheets=(1,), numbers={1: SheetNumbers(
            code="3255", number_tail="1547-1548", request_no="1094441630")},
        uploader=site.upload, linker=site.link)
    assert made.codes[1] == "3255"
    printed = _printed(made.pdfs[1])
    assert "3255" in printed and "1547-1548" in printed
    assert "1094441630" in printed


def test_a_fresh_set_is_offered_for_each_worker() -> None:
    first = store.new_numbers()
    second = store.new_numbers()
    assert sorted(first) == [1, 2, 3, 4]
    assert all(len(n.code) == 4 and n.code.isdigit() for n in first.values())
    assert [n.code for n in first.values()] != [n.code for n in second.values()]


# ----------------------------------------------------------- without QR
def test_the_office_may_print_without_the_qr(tmp_path) -> None:
    _blanks(tmp_path)
    _seal(tmp_path)
    service = UzbSpravkaService(_Settings())          # no keys at all
    made = service.generate(_worker(), sheets=(1,), with_qr=False)
    assert made.links == {}
    with fitz.open(made.pdfs[1]) as doc:
        assert len(doc[0].get_images(full=True)) == 1, "фақат печать қолиши керак"


def test_asking_for_a_qr_without_the_keys_says_which_ones(tmp_path) -> None:
    _blanks(tmp_path)
    _seal(tmp_path)
    service = UzbSpravkaService(_Settings())
    with pytest.raises(ValidationError, match="QRIXTOOLS"):
        service.generate(_worker(), sheets=(1,))
    assert service.can_make_qr() is False


# ------------------------------------------------------- what is refused
def test_a_certificate_without_its_blank_is_refused(tmp_path) -> None:
    """The scan IS the document — numbers on a white page are of no use."""
    _blanks(tmp_path, sheets=(1, 2))
    _seal(tmp_path)
    service = UzbSpravkaService(_keys())
    with pytest.raises(ValidationError, match="3, 4"):
        service.generate(_worker(), uploader=_Site().upload,
                         linker=_Site().link)


def test_a_worker_without_a_firm_or_its_seal_is_refused(tmp_path) -> None:
    _blanks(tmp_path)
    service = UzbSpravkaService(_keys())
    with pytest.raises(ValidationError, match="Фирмани танланг"):
        service.generate(_worker(firm=""), sheets=(1,), with_qr=False)
    with pytest.raises(ValidationError, match="печати юкланмаган"):
        service.generate(_worker(), sheets=(1,), with_qr=False)


def test_a_nameless_worker_is_refused(tmp_path) -> None:
    service, _site, data = _ready(tmp_path)
    data.surname = ""
    with pytest.raises(ValidationError, match="Фамилия"):
        service.generate(data, sheets=(1,), with_qr=False)


# ------------------------------------------------------------- the files
def test_the_next_worker_never_writes_over_the_last(tmp_path) -> None:
    service, site, data = _ready(tmp_path)
    first = service.generate(data, sheets=(1,), uploader=site.upload,
                             linker=site.link)
    second = service.generate(data, sheets=(1,), uploader=site.upload,
                              linker=site.link)
    assert first.pdfs[1] != second.pdfs[1]
    assert first.pdfs[1].exists() and second.pdfs[1].exists()
    assert second.pdfs[1].name == "ЭРГАШЕВ_УМИДЖОН_1_002.pdf"
