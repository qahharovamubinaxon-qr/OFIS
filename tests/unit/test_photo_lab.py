"""РАСМ-ФОТО ядроси (photo_tools) устидаги хизмат адаптери — уланиш синови.

Расм мантиғи photo_tools ичида; бу ерда фақат PIL→bytes, вақтинчалик PDF ва
параметр узатиш текширилади. Оғир AI (torch/GFPGAN) керак эмас —
enhance_face=False билан person quvури fallback'сиз ишлайди.
"""

import io

import numpy as np
import pytest
from PIL import Image
from src.services.photo_lab_service import (
    DocScanOutput,
    PersonPhotoOutput,
    PhotoLabService,
)

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _person_src() -> bytes:
    """Оддий портрет-ўлчамли расм — юз йўқ, quvур барибир натижа беради."""
    b = io.BytesIO()
    Image.new("RGB", (600, 800), (185, 172, 160)).save(b, "PNG")
    return b.getvalue()


def _doc_src() -> bytes:
    """Тўқ фонда ёруғ карта — find_document уни тўртбурчак деб топади."""
    arr = np.full((700, 900, 3), 28, np.uint8)
    arr[120:520, 190:720] = 238
    b = io.BytesIO()
    Image.fromarray(arr).save(b, "PNG")
    return b.getvalue()


def test_person_returns_photo_sheet_and_pdf():
    out = PhotoLabService().person(
        _person_src(), size="35x45", background="white",
        enhance_face=False, cols=3, rows=2)
    assert isinstance(out, PersonPhotoOutput)
    assert out.photo_png[:8] == _PNG_MAGIC
    assert out.sheet_png[:8] == _PNG_MAGIC
    assert out.pdf[:4] == b"%PDF"
    assert out.face_found is False           # synthetic image has no face


def test_person_transparent_photo_is_rgba():
    out = PhotoLabService().person(
        _person_src(), size="35x45", background="transparent",
        enhance_face=False)
    assert Image.open(io.BytesIO(out.photo_png)).mode == "RGBA"


def test_document_scan_makes_pdf_preview_and_pages():
    out = PhotoLabService().document(
        [(_doc_src(), "old")], preset="id_card", color="color")
    assert isinstance(out, DocScanOutput)
    assert out.pdf[:4] == b"%PDF"
    assert out.preview_png[:8] == _PNG_MAGIC
    assert len(out.page_pngs) == 1
    assert out.page_pngs[0][:8] == _PNG_MAGIC


def test_document_not_found_raises_valueerror():
    # a black frame has no bright document quad → find_document returns None
    b = io.BytesIO()
    Image.new("RGB", (400, 400), (0, 0, 0)).save(b, "PNG")
    with pytest.raises(ValueError):
        PhotoLabService().document(
            [(b.getvalue(), "old")], preset="id_card", color="color")


def test_models_status_has_the_expected_keys():
    status = PhotoLabService().models_status()
    for key in ("gfpgan", "rembg", "torch", "models_dir"):
        assert key in status
