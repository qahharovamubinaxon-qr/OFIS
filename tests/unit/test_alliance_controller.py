from datetime import date

from src.controllers.alliance_controller import AllianceController


def test_controller_has_the_view_facing_methods():
    for m in ("read_image", "read_documents", "generate", "until",
              "set_blank", "blank", "pages", "layout", "save_layout",
              "ai_available"):
        assert hasattr(AllianceController, m), m


def test_read_image_returns_the_bytes(tmp_path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"hello-bytes")
    assert AllianceController.read_image(p) == b"hello-bytes"


def test_until_is_plus_three_years():
    c = AllianceController(ocr=None, service=None)
    assert c.until(date(2026, 9, 7)) == date(2029, 9, 7)
