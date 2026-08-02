"""АЛПИНИСТ — the industrial climber's card."""

from __future__ import annotations

import io
import tempfile
from datetime import date
from pathlib import Path

import fitz
import pytest
from src.config import paths
from src.pdf.alpinist_renderer import (
    AlpinistData,
    output_name,
    plus_three_years,
    render,
    values,
)
from src.pdf.alpinist_spec import IMG_SLOTS, SLOTS


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    sandbox = tempfile.mkdtemp()
    monkeypatch.setenv("XDG_DATA_HOME", sandbox)
    monkeypatch.setenv("LOCALAPPDATA", sandbox)
    paths.data_dir.cache_clear()
    yield
    paths.data_dir.cache_clear()


def _blank(folder: Path) -> Path:
    blank = folder / "ALP.pdf"
    doc = fitz.open()
    for _ in range(2):
        doc.new_page(width=842, height=632)          # landscape, as the card
    doc.save(str(blank))
    doc.close()
    return blank


def _png(width: int, height: int, colour) -> bytes:
    from PIL import Image

    out = io.BytesIO()
    Image.new("RGBA", (width, height), colour).save(out, "PNG")
    return out.getvalue()


_WORKER = dict(surname="БАРАТОВ", name="ОЙБЕК", patronymic="БАХРИДДИНОВИЧ",
               ud_number="440144", blank_number="145",
               issue_date=date(2026, 5, 10))


# ------------------------------------------------------------- the values


def test_the_card_runs_exactly_three_years() -> None:
    assert plus_three_years(date(2026, 5, 10)) == date(2029, 5, 10)
    assert plus_three_years(date(2028, 2, 29)) == date(2031, 2, 28)


def test_the_texts_take_the_owners_own_manner() -> None:
    made = values(AlpinistData(**_WORKER))
    assert made["p1_number"] == "440144"
    assert made["p1_fio_surname"] == "БАРАТОВ"
    assert made["p1_issued"] == "10.05.2026 г."
    assert made["p1_until"] == "10.05.2029 г."
    assert made["p2_protocol"] == "145 от 10.05.2026 года"


def test_every_text_slot_has_a_value() -> None:
    assert set(values(AlpinistData(**_WORKER))) == set(SLOTS)


# ------------------------------------------------------------ the render


def test_render_places_texts_and_all_three_pictures(tmp_path) -> None:
    data = AlpinistData(**_WORKER,
                        photo_png=_png(300, 411, (200, 40, 40, 255)),
                        sign_png=_png(200, 120, (61, 49, 162, 255)),
                        stamp_png=_png(240, 240, (40, 40, 200, 120)))
    pdf = render(data, _blank(tmp_path))
    with fitz.open("pdf", pdf) as doc:
        assert doc.page_count == 2
        ink = "".join(p.get_text() for p in doc).replace("\xa0", " ")
        assert "БАРАТОВ" in ink and "10.05.2026 г." in ink
        assert "145 от 10.05.2026 года" in ink
        # photo + signature + печать all stand on the card's FACE
        assert len(doc[0].get_images(full=True)) == 3
        assert len(doc[1].get_images(full=True)) == 0


def test_the_photo_fills_the_printed_frame(tmp_path) -> None:
    import numpy as np

    data = AlpinistData(**_WORKER, photo_png=_png(300, 411, (200, 40, 40, 255)))
    pdf = render(data, _blank(tmp_path))
    with fitz.open("pdf", pdf) as doc:
        pix = doc[0].get_pixmap(dpi=100)
        img = np.frombuffer(pix.samples, np.uint8).reshape(
            pix.height, pix.width, pix.n)[:, :, :3]
    red = (img[:, :, 0] > 150) & (img[:, :, 1] < 120)
    ys, xs = np.nonzero(red)
    assert len(xs), "the photo left no ink"
    frame = IMG_SLOTS["img_photo"]
    x0 = frame.x * pix.width
    y1 = frame.baseline * pix.height
    y0 = (frame.baseline - frame.size) * pix.height
    assert xs.min() >= x0 - 3 and ys.min() >= y0 - 3 and ys.max() <= y1 + 3


def test_the_stamp_lies_over_the_photos_corner() -> None:
    """The печать certifies the picture — its default footprint must
    overlap the photo frame on the card's face."""
    photo, stamp = IMG_SLOTS["img_photo"], IMG_SLOTS["img_stamp"]
    assert photo.page == 1 and stamp.page == 1
    # both as (x0, y0, x1, y1) in page shares, a round stamp (aspect 1)
    page_w, page_h = 842.0, 632.0
    p = (photo.x, photo.baseline - photo.size,
         photo.x + photo.size * page_h * 0.7305 / page_w, photo.baseline)
    s = (stamp.x, stamp.baseline - stamp.size,
         stamp.x + stamp.size * page_h / page_w, stamp.baseline)
    assert s[0] < p[2] and s[2] > p[0], "no horizontal overlap with the photo"
    assert s[1] < p[3] and s[3] > p[1], "no vertical overlap with the photo"


def test_a_layout_saved_before_the_stamp_moved_lets_it_go(tmp_path) -> None:
    from src.pdf.alpinist_spec import LEGACY_STAMP
    from src.services.alpinist_service import AlpinistService

    service = AlpinistService()
    blank = service.add_template("ПРОФИ", _blank(tmp_path))
    service.save_layout(blank, {"fields": {
        "img_stamp": list(LEGACY_STAMP),           # the old back-page spot
        "p1_number": [0.60, 0.34, 0.04],           # a genuine drag
    }})
    kept = service.layout(blank)
    assert list(kept.get("fields") or {}) == ["p1_number"]


# ---------------------------------------------------------- the portrait


def test_the_card_photo_takes_the_sfera_crop(monkeypatch) -> None:
    """The owner: «СФЕРА кесгандек кессин» — the card photo must go through
    the ONE crop (photo_service.prepare_portrait), at the frame's aspect."""
    from src.controllers import alpinist_controller
    from src.pdf.alpinist_spec import PHOTO_RATIO

    seen = {}

    def fake_prepare(data, aspect=0.75, height=800):
        seen["aspect"] = aspect
        return b"\x89PNG\r\n\x1a\nmade"

    monkeypatch.setattr(alpinist_controller, "prepare_portrait", fake_prepare)
    made = alpinist_controller._card_photo(b"snapshot")
    assert made.startswith(b"\x89PNG")
    assert seen["aspect"] == PHOTO_RATIO


def test_an_unreadable_photo_is_a_sentence_not_a_traceback(monkeypatch) -> None:
    from src.common.errors import OfisError
    from src.controllers import alpinist_controller

    monkeypatch.setattr(alpinist_controller, "prepare_portrait",
                        lambda *a, **k: None)
    with pytest.raises(OfisError):
        alpinist_controller._card_photo(b"not a picture")


def test_the_real_pipeline_hands_back_the_frames_aspect() -> None:
    import cv2
    import numpy as np
    from src.pdf.alpinist_spec import PHOTO_RATIO
    from src.services.photo_service import prepare_portrait

    canvas = np.full((800, 600, 3), (140, 120, 100), np.uint8)
    cv2.ellipse(canvas, (300, 300), (120, 160), 0, 0, 360, (30, 30, 60), -1)
    cv2.rectangle(canvas, (140, 430), (460, 800), (40, 35, 70), -1)
    ok, jpg = cv2.imencode(".jpg", canvas)
    assert ok
    out = prepare_portrait(jpg.tobytes(), aspect=PHOTO_RATIO)
    assert out is not None
    cut = cv2.imdecode(np.frombuffer(out, np.uint8), cv2.IMREAD_COLOR)
    ratio = cut.shape[1] / cut.shape[0]
    assert abs(ratio - PHOTO_RATIO) < 0.02, f"cut ratio {ratio:.3f}"


# ----------------------------------------------------------- the service


def test_the_blank_number_counts_up_by_itself(tmp_path) -> None:
    from src.app import build_container
    from src.config.settings_service import SettingsService
    from src.services.alpinist_service import AlpinistService

    service = AlpinistService(build_container().resolve(SettingsService))
    assert service.next_number() == 145                  # the owner's start
    blank = service.add_template("ПРОФИ", _blank(tmp_path))
    service.generate(AlpinistData(**_WORKER), blank)
    assert service.next_number() == 146
    # a hand-typed word must not break the counting
    service.generate(AlpinistData(**{**_WORKER, "blank_number": "б/н"}), blank)
    assert service.next_number() == 146


def test_the_stamps_paper_goes_transparent(tmp_path) -> None:
    import numpy as np
    from PIL import Image
    from src.services.alpinist_service import AlpinistService

    source = tmp_path / "stamp.jpg"
    Image.new("RGB", (200, 200), (255, 255, 255)).save(source)
    with Image.open(source) as im:
        px = im.load()
        for i in range(60, 140):
            for j in range(60, 140):
                px[i, j] = (40, 40, 190)
        im.save(source)

    service = AlpinistService()
    kept = service.set_stamp(source)
    with Image.open(kept) as done:
        arr = np.array(done)
    assert arr[5, 5, 3] == 0, "the white paper stayed opaque"
    assert arr[100, 100, 3] == 255, "the ink itself vanished"
    assert service.stamp() == kept
    service.remove_stamp()
    assert service.stamp() is None


def test_the_filename_is_surname_name() -> None:
    assert output_name(AlpinistData(**_WORKER)) == "БАРАТОВ_ОЙБЕК.pdf"
