"""IMGBB — the picture-to-link and picture-to-QR section, and its bot module."""

from __future__ import annotations

import tempfile

import pytest
from src.config import paths


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    sandbox = tempfile.mkdtemp()
    monkeypatch.setenv("XDG_DATA_HOME", sandbox)
    monkeypatch.setenv("LOCALAPPDATA", sandbox)
    paths.data_dir.cache_clear()
    yield
    paths.data_dir.cache_clear()


class _Settings:
    def __init__(self, key="key123"):
        self._key = key

    def get(self, name, default=""):
        from src.services.imgbb import KEY_IMGBB

        return self._key if name == KEY_IMGBB else default


def test_upload_hands_back_the_direct_link(monkeypatch) -> None:
    from src.controllers.imgbb_controller import ImgbbController
    from src.services import imgbb

    def fake_upload(image, key, name=""):
        assert key == "key123" and image == b"picture"
        return "https://i.ibb.co/abc123/x.jpg"

    monkeypatch.setattr(imgbb, "upload", fake_upload)
    ctl = ImgbbController(_Settings())
    assert ctl.upload(b"picture") == "https://i.ibb.co/abc123/x.jpg"


def test_the_qr_decodes_back_to_the_link() -> None:
    import cv2
    import fitz
    import numpy as np
    from src.controllers.imgbb_controller import ImgbbController

    link = "https://i.ibb.co/pjLNhMkV/984-4.jpg"
    png = ImgbbController.qr(link)
    pix = fitz.Pixmap(png)
    img = np.frombuffer(pix.samples, np.uint8).reshape(
        pix.height, pix.width, pix.n)[:, :, :3]
    decoded, _pts, _ = cv2.QRCodeDetector().detectAndDecode(
        np.ascontiguousarray(img))
    assert decoded == link


def test_no_key_is_a_sentence_not_a_traceback() -> None:
    from src.common.errors import OfisError
    from src.controllers.imgbb_controller import ImgbbController

    ctl = ImgbbController(_Settings(key=""))
    with pytest.raises(OfisError):
        ctl.upload(b"picture")


def test_the_bot_module_notes_the_link_and_returns_the_qr(monkeypatch) -> None:
    from src.controllers import ofis_modules

    class _Ctl:
        @staticmethod
        def key():
            return "key123"

        @staticmethod
        def upload(image, name=""):
            return "https://i.ibb.co/zz9/photo.jpg"

        @staticmethod
        def qr(link):
            from src.pdf.qrreg_renderer import make_qr

            return make_qr(link)

    notes: list[str] = []
    ctx = ofis_modules.RunContext({"imgbb": _Ctl()}, note=notes.append)
    state = {**ofis_modules.new_state(), "photos": [b"picture"]}
    files = ofis_modules._run_imgbb(ctx, state)
    assert files and files[0].suffix == ".png" and files[0].exists()
    assert any("i.ibb.co" in note for note in notes)

    module = ofis_modules.BY_KEY["imgbb"]
    assert module.needs_ai is False
    assert module.ready({"imgbb": _Ctl()}) == ""


def test_the_alpinist_bot_module_signs_off_paper(monkeypatch, tmp_path) -> None:
    import io
    from datetime import date

    from PIL import Image
    from src.controllers import ofis_modules

    sheet = io.BytesIO()
    Image.new("RGB", (60, 40), (255, 255, 255)).save(sheet, "PNG")

    seen: dict = {}

    class _Ctl:
        @staticmethod
        def read_documents(passport, patent):
            from src.domain.documents import Passport

            return Passport(surname="БАРАТОВ", name="ОЙБЕК",
                            number="FA1234567")

        @staticmethod
        def next_number():
            return 145

        @staticmethod
        def generate(**kwargs):
            seen.update(kwargs)

            class _R:
                saved = tmp_path / "БАРАТОВ_ОЙБЕК.pdf"

            _R.saved.write_bytes(b"%PDF-")
            return _R

    ctx = ofis_modules.RunContext({"alpinist": _Ctl()})
    state = {**ofis_modules.new_state(), "target": str(tmp_path / "ALP.pdf"),
             "photos": [b"passport", b"worker", sheet.getvalue()],
             "answers": {"issue_date": date(2026, 5, 10),
                         "ud_number": "440258"}}
    files = ofis_modules._run_alpinist(ctx, state)
    assert files and files[0].name == "БАРАТОВ_ОЙБЕК.pdf"
    assert seen["blank_number"] == "145"
    assert seen["ud_number"] == "440258"
    assert seen["signature"][:8] == b"\x89PNG\r\n\x1a\n"
