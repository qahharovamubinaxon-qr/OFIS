"""РАСМ-ФОТО экрани — режим алмашиши, тугма ҳолати ва хатосиз қурилиши.

Оғир пакетлар (photo_tools, cv2, rembg) керак эмас — сохта хизмат берилади,
ва RUN синалмайди (у фон оқимига ўтади). Мақсад: экран қурилади, режим
алмашганда керакли панеллар кўринади/яширинади ва бўш RUN синдирмайди.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


class _FakeService:
    """photo_tools'ни чақирмайдиган сохта хизмат — фақат UI мантиғи учун."""

    def models_status(self) -> dict:
        return {"gfpgan": False, "rembg": True, "torch": False, "models_dir": "x"}


def _view():
    from src.ui.views.photo_view import PhotoView

    return PhotoView(_FakeService(), settings=None)


def test_builds_in_person_mode_by_default():
    v = _view()
    assert v._document_mode() is False
    assert v._person_opts.isHidden() is False
    assert v._doc_opts.isHidden() is True
    assert v._dz.isHidden() is False
    assert v._doc_box.isHidden() is True


def test_switches_to_document_mode():
    v = _view()
    v._mode.setCurrentIndex(v._mode.findData("document"))
    assert v._document_mode() is True
    assert v._doc_opts.isHidden() is False
    assert v._person_opts.isHidden() is True
    assert v._doc_box.isHidden() is False
    assert v._dz.isHidden() is True


def test_grid_choice_parses_to_cols_rows():
    v = _view()
    v._pick(v._grid, "4x2")
    assert v._grid_cols_rows() == (4, 2)


def test_run_without_any_upload_warns_and_does_not_crash():
    v = _view()
    v._on_run()                       # person mode, no photo dropped
    assert "yukla" in v._status.text().lower()
    v._mode.setCurrentIndex(v._mode.findData("document"))
    v._on_run()                       # document mode, no front dropped
    assert "yukla" in v._status.text().lower()
