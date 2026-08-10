"""КРКОД РЕГ — the QR-code dormitory registration."""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import fitz
import pytest
from src.config import paths
from src.pdf.qrreg_renderer import (
    QrRegData,
    make_qr,
    output_name,
    podt_values,
    reg_values,
    render_podt,
    render_registration,
)
from src.pdf.qrreg_spec import PODT_SLOTS, QR_FRAME, REG_SLOTS


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    sandbox = tempfile.mkdtemp()
    monkeypatch.setenv("XDG_DATA_HOME", sandbox)
    monkeypatch.setenv("LOCALAPPDATA", sandbox)
    paths.data_dir.cache_clear()
    yield
    paths.data_dir.cache_clear()


def _reg_blank(folder: Path) -> Path:
    blank = folder / "REG.pdf"
    doc = fitz.open()
    for _ in range(2):
        doc.new_page(width=595, height=842)
    doc.save(str(blank))
    doc.close()
    return blank


def _podt_blank(folder: Path) -> Path:
    blank = folder / "PODT.pdf"
    doc = fitz.open()
    doc.new_page(width=284, height=453)
    doc.save(str(blank))
    doc.close()
    return blank


_WORKER = dict(
    surname="ИБАДУЛЛАЕВ", name="АНВАР", patronymic="ОЙБЕК УГЛИ",
    citizenship="УЗБЕКИСТАН", birth_date=date(2004, 6, 17), gender="male",
    pass_series="FA", pass_number="3028791",
    pass_issued=date(2021, 6, 9), pass_expiry=date(2031, 6, 8),
    valid_from=date(2026, 7, 21), valid_to=date(2026, 10, 18),
    addr_subject="ГОРОД МОСКВА", addr_district="ОБРУЧЕВСКИЙ РАЙОН",
    addr_street="УЛ НОВАТОРОВ", dom="34", korpus="3", kvartira="50",
    code="02/770-152/26/156651",
    host_surname="АЛЕКСАНДРОВА", host_name="НИНА",
    host_patronymic="ВЛАДИМИРОВНА")


# ------------------------------------------------------------- the values


def test_every_value_has_a_slot_both_ways() -> None:
    data = QrRegData(**_WORKER)
    assert set(reg_values(data)) == set(REG_SLOTS)
    assert set(podt_values(data)) == set(PODT_SLOTS)


def test_the_sex_is_a_plus_in_the_right_box() -> None:
    male = reg_values(QrRegData(**_WORKER))
    assert male["f_sex_male"] == "+" and male["f_sex_female"] == ""
    female = reg_values(QrRegData(**{**_WORKER, "gender": "female"}))
    assert female["f_sex_female"] == "+" and female["f_sex_male"] == ""


def test_the_card_writes_names_and_address_its_own_way() -> None:
    made = podt_values(QrRegData(**_WORKER))
    assert made["c_fio"] == "Ибадуллаев Анвар Ойбек Угли"
    assert made["c_passport"] == "FA3028791"
    assert made["c_address"] == ("ГОРОД МОСКВА, ОБРУЧЕВСКИЙ РАЙОН, "
                                 "УЛ НОВАТОРОВ, д. 34, к. 3, кв. 50")
    assert made["c_from"] == "21.07.2026" and made["c_to"] == "18.10.2026"
    assert made["c_code"] == "02/770-152/26/156651"


# ---------------------------------------------------------------- the QR


def test_the_qr_decodes_back_to_the_exact_link(tmp_path) -> None:
    """The whole point: a phone scanning the print must open imgbb."""
    import cv2
    import numpy as np

    link = "https://i.ibb.co/pjLNhMkV/984-4.jpg"
    pdf = render_registration(QrRegData(**_WORKER), _reg_blank(tmp_path),
                              make_qr(link))
    with fitz.open("pdf", pdf) as doc:
        pix = doc[1].get_pixmap(dpi=200)
        img = np.frombuffer(pix.samples, np.uint8).reshape(
            pix.height, pix.width, pix.n)[:, :, :3]
    decoded, pts, _ = cv2.QRCodeDetector().detectAndDecode(img)
    assert decoded == link, f"QR decoded to {decoded!r}"
    # and the whole code sits INSIDE the printed frame, off its border
    height, width = img.shape[:2]
    x0, y0, x1, y1 = QR_FRAME
    xs, ys = pts[0][:, 0] / width, pts[0][:, 1] / height
    assert xs.min() >= x0 - 0.003 and xs.max() <= x1 + 0.003
    assert ys.min() >= y0 - 0.003 and ys.max() <= y1 + 0.003


def test_every_letter_sits_in_the_middle_of_its_own_box(tmp_path) -> None:
    """The passport number's characters must land on the cells' centres —
    the office saw them leaning on the boxes' left borders."""
    import numpy as np

    pdf = render_registration(QrRegData(**_WORKER), _reg_blank(tmp_path), None)
    with fitz.open("pdf", pdf) as doc:
        pix = doc[0].get_pixmap(dpi=200)
        img = np.frombuffer(pix.samples, np.uint8).reshape(
            pix.height, pix.width, pix.n)[:, :, :3]
    gray = img.mean(axis=2)
    height, width = gray.shape
    slot = REG_SLOTS["f_doc_number"]
    band = gray[int((slot.baseline - 0.016) * height):
                int((slot.baseline + 0.004) * height)]
    text = reg_values(QrRegData(**_WORKER))["f_doc_number"]
    assert text == "FA3028791"
    for i, char in enumerate(text):
        centre = (slot.x + i * slot.pitch) * width
        half = slot.pitch * width / 2
        window = band[:, int(centre - half):int(centre + half)]
        _ys, xs = np.nonzero(window < 128)
        assert len(xs), f"«{char}» left no ink"
        centroid = xs.mean() + int(centre - half)
        assert abs(centroid - centre) < 0.006 * width, \
            f"«{char}» off-centre by {abs(centroid - centre):.1f}px"


def test_the_card_values_take_the_samples_own_colours(tmp_path) -> None:
    """Brown rows print sandy-gold, light rows dark maroon — never white."""
    import numpy as np

    pdf, _png = render_podt(QrRegData(**_WORKER), _podt_blank(tmp_path))
    with fitz.open("pdf", pdf) as doc:
        pix = doc[0].get_pixmap(dpi=150)
        img = np.frombuffer(pix.samples, np.uint8).reshape(
            pix.height, pix.width, pix.n)[:, :, :3]
    height, width = img.shape[:2]

    def ink(base):
        band = img[int((base - 0.014) * height):int((base + 0.004) * height),
                   int(0.30 * width):int(0.95 * width)].reshape(-1, 3)
        marked = band[band.sum(1) < 3 * 245]
        assert len(marked), "no ink in the band"
        # glyph cores only — the anti-aliased edges blend toward the white
        lum = marked.sum(1)
        core = marked[lum <= np.percentile(lum, 30)]
        return np.median(core, axis=0) / 255.0

    gold = ink(PODT_SLOTS["c_birth"].baseline)      # a brown-row value
    assert gold[0] > 0.6 and gold[0] > gold[1] > gold[2], gold
    maroon = ink(PODT_SLOTS["c_fio"].baseline)      # a light-row value
    assert maroon[0] < 0.55 and maroon[1] < 0.3, maroon


def test_the_card_is_set_in_arial_bold_italic() -> None:
    import os

    from src.pdf.engine import _font_file
    from src.pdf.qrreg_spec import PODT_FONT

    assert PODT_FONT == "OfisArialBoldItalic"
    if os.name == "nt":
        assert _font_file(PODT_FONT).name.lower() == "arialbi.ttf"


def test_a_saved_legacy_layout_no_longer_pins_the_letters(tmp_path) -> None:
    """The office saved the old defaults wholesale before the cells were
    re-measured — those numbers must give way; a genuine drag must stay."""
    from src.pdf.qrreg_spec import LEGACY_REG
    from src.services.qrreg_service import QrRegService

    service = QrRegService()
    reg = service.add_template("МОСКВА", _reg_blank(tmp_path))
    fields = {key: list(value) for key, value in LEGACY_REG.items()}
    fields["f_dom"] = [0.1094, 0.5495, 0.0122]          # the office's nudge
    service.save_layout(reg, {"fields": fields})
    kept = service.layout(reg)
    assert list(kept.get("fields") or {}) == ["f_dom"]


def test_the_podt_renders_both_pdf_and_png(tmp_path) -> None:
    pdf, png = render_podt(QrRegData(**_WORKER), _podt_blank(tmp_path))
    assert pdf[:5] == b"%PDF-"
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    with fitz.open("pdf", pdf) as doc:
        # MuPDF hands spaces back as \xa0 and hyphens as \xad — normalised,
        # or nothing with a dash ever matches
        ink = doc[0].get_text().replace("\xa0", " ").replace("\xad", "-")
        assert "Ибадуллаев Анвар Ойбек Угли" in ink
        assert "02/770-152/26/156651" in ink


# ------------------------------------------------------------- the chain


def test_generate_runs_the_whole_chain_and_lands_on_the_desktop(
        tmp_path, monkeypatch) -> None:
    from src.app import build_container
    from src.config.settings_service import SettingsService
    from src.services import qrreg_service
    from src.services.qrreg_service import QrRegService

    monkeypatch.setattr(qrreg_service, "desktop_dir", lambda: tmp_path)
    service = QrRegService(build_container().resolve(SettingsService))
    reg = service.add_template("СФЕРА", _reg_blank(tmp_path))
    service.set_podt_template(_podt_blank(tmp_path))

    sent: dict = {}

    def fake_upload(png, key, name=""):
        sent["png"] = png
        sent["name"] = name
        return "https://i.ibb.co/abc123/IBADULLAEV.jpg"

    result = service.generate(QrRegData(**_WORKER), reg, uploader=fake_upload)
    assert result.saved.parent == tmp_path, "not on the Desktop"
    assert result.saved.name.startswith("ИБАДУЛЛАЕВ_АНВАР")
    assert result.link.startswith("https://i.ibb.co/")
    assert sent["png"][:8] == b"\x89PNG\r\n\x1a\n", "imgbb got no picture"

    # the dormitory is remembered whole — address, code and host together
    kept = service.addresses()
    assert kept and kept[0]["code"] == "02/770-152/26/156651"
    assert kept[0]["host_surname"] == "АЛЕКСАНДРОВА"

    # the finished PDF really carries a scannable QR
    import cv2
    import numpy as np

    with fitz.open(str(result.saved)) as doc:
        assert doc.page_count == 2
        pix = doc[1].get_pixmap(dpi=200)
        img = np.frombuffer(pix.samples, np.uint8).reshape(
            pix.height, pix.width, pix.n)[:, :, :3]
    decoded, _pts, _ = cv2.QRCodeDetector().detectAndDecode(img)
    assert decoded == result.link


def test_a_viewer_page_link_is_refused() -> None:
    """Only the DIRECT i.ibb.co address may go into the QR."""
    from src.common.errors import OfisError
    from src.services import imgbb

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            import json
            return json.dumps({"success": True, "data": {
                "url": "https://ibb.co/viewer123",
                "image": {"url": "https://ibb.co/viewer123"}}}).encode()

    import urllib.request
    old = urllib.request.urlopen
    urllib.request.urlopen = lambda *a, **k: _Resp()
    try:
        with pytest.raises(OfisError):
            imgbb.upload(b"png", "key123")
    finally:
        urllib.request.urlopen = old


def test_no_api_key_is_a_sentence_not_a_traceback() -> None:
    from src.common.errors import OfisError
    from src.services.imgbb import upload

    with pytest.raises(OfisError) as exc:
        upload(b"png", "")
    assert "Sozlamalar" in str(exc.value.message)


def test_the_filename_is_surname_name() -> None:
    assert output_name(QrRegData(**_WORKER)) == "ИБАДУЛЛАЕВ_АНВАР.pdf"


def test_the_bot_needs_a_saved_dormitory_first() -> None:
    """…and now ASKS which one, rather than taking the newest in silence.

    It used to go straight to the dates and use whichever dormitory was
    saved last. That is right until the office registers somebody at a
    different one, and then it is wrong without anybody seeing it — so the
    address became the first question.
    """
    from src.controllers.ofis_modules import BY_KEY

    module = BY_KEY["qrreg"]
    assert module.photo_labels == ("Паспорт", "Патент")
    fields = [a.field for a in module.asks]
    assert fields == ["address", "valid_from", "valid_to"]
    assert module.asks[0].kind == "choice"
