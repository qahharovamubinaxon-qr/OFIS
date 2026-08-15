"""Sweeping yesterday's finished documents off the office machine.

Twice now ``output/`` has filled the C: drive and stopped the program — 538
files, 1.8 GB, of which 1.67 GB had been sitting there over a day. The office
hands the worker his copy the minute it is printed and never goes back for it,
so it asked for a one-day sweep.

The thing that must be beyond doubt is what it does NOT touch. The blanks the
office uploaded are 2.2 GB of scans in ``templates/`` that cannot be replaced,
and it has said more than once that they must never be deleted.
"""

from __future__ import annotations

import os
import time

import pytest
from src.config import paths
from src.services.housekeeping import (
    DEFAULT_KEEP_DAYS,
    KEY_KEEP_DAYS,
    keep_days,
    sweep_output,
)

DAY = 86_400


@pytest.fixture
def data(tmp_path, monkeypatch):
    """A whole AppData tree of its own, so no real document is at risk."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    paths.data_dir.cache_clear()
    yield tmp_path
    paths.data_dir.cache_clear()


def _put(folder, name: str, *, days_old: float, size: int = 32):
    made = folder / name
    made.parent.mkdir(parents=True, exist_ok=True)
    made.write_bytes(b"x" * size)
    when = time.time() - days_old * DAY
    os.utime(made, (when, when))
    return made


# ------------------------------------------------------------ what it sweeps
def test_yesterdays_documents_go(data) -> None:
    old = _put(paths.output_dir(), "ISOEV_ASLIDIN.pdf", days_old=3)
    made = sweep_output(1)
    assert not old.exists()
    assert made.removed == 1 and made.freed == 32


def test_todays_work_stays(data) -> None:
    """A document made this morning survives however often OFIS is opened."""
    fresh = _put(paths.output_dir(), "SEGODNYA.pdf", days_old=0.2)
    made = sweep_output(1)
    assert fresh.exists()
    assert made.removed == 0 and made.kept == 1


def test_it_reaches_into_the_sections_own_folders(data) -> None:
    """Sections file their work in output/dover, output/dms and so on."""
    deep = _put(paths.output_dir() / "dover", "DOVER_СОГЛАСИЕ.pdf", days_old=5)
    sweep_output(1)
    assert not deep.exists()


def test_an_emptied_folder_is_tidied_away(data) -> None:
    _put(paths.output_dir() / "dover" / "2026", "old.pdf", days_old=5)
    sweep_output(1)
    assert not (paths.output_dir() / "dover" / "2026").exists()
    assert paths.output_dir().exists(), "output папкасининг ўзи қолиши керак"


# ------------------------------------------------- what it must never touch
def test_the_uploaded_blanks_are_never_touched(data) -> None:
    """«ПУСТОЙ БЛАНКАЛАР ЙУКЛАГАНМАН УЛАР УЧМАСИН»."""
    blanks = [
        _put(paths.user_templates_dir() / "universal" / "СПРАВКА",
             "blank.pdf", days_old=400),
        _put(paths.user_templates_dir(), "hostel_blank.pdf", days_old=900),
    ]
    _put(paths.output_dir(), "throwaway.pdf", days_old=5)
    made = sweep_output(1)
    assert made.removed == 1, "фақат output дан ўчириши керак"
    assert all(b.exists() for b in blanks)


@pytest.mark.parametrize("folder", ["archive", "backups", "models", "logs"])
def test_the_other_folders_are_left_alone(data, folder) -> None:
    kept = _put(data / "OFIS" / folder, "keep-me.bin", days_old=500)
    if not kept.exists():                    # non-Windows layout
        kept = _put(data / "ofis" / folder, "keep-me.bin", days_old=500)
    sweep_output(1)
    assert kept.exists()


def test_a_shortcut_out_of_the_folder_is_refused_not_followed(data) -> None:
    """One junction is all that stands between the sweep and the blanks."""
    outside = _put(paths.user_templates_dir(), "precious.pdf", days_old=900)
    link = paths.output_dir() / "shortcut.pdf"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("бу машинада symlink яратиб бўлмайди")
    sweep_output(1)
    assert outside.exists(), "ташқаридаги файл ўчирилибди"


# ------------------------------------------------------------ how long
def test_zero_days_means_keep_everything(data) -> None:
    """The safe reading of a nought typed by mistake is «keep», not «wipe»."""
    old = _put(paths.output_dir(), "ancient.pdf", days_old=900)
    made = sweep_output(0)
    assert old.exists()
    assert made.disabled and made.removed == 0


def test_a_longer_retention_is_honoured(data) -> None:
    week = _put(paths.output_dir(), "five-days.pdf", days_old=5)
    fortnight = _put(paths.output_dir(), "twenty-days.pdf", days_old=20)
    sweep_output(14)
    assert week.exists() and not fortnight.exists()


def test_the_office_asked_for_one_day() -> None:
    assert DEFAULT_KEEP_DAYS == 1


class _Settings:
    def __init__(self, value=None) -> None:
        self._value = value

    def get(self, key, default=None):
        return default if self._value is None or key != KEY_KEEP_DAYS \
            else self._value


@pytest.mark.parametrize("stored,wanted", [
    (None, 1), (7, 7), ("3", 3), (0, 0), (-5, 0), ("kun", 1), (None, 1)])
def test_the_setting_is_read_sanely(stored, wanted) -> None:
    assert keep_days(_Settings(stored)) == wanted


# --------------------------------------------------------------- mishaps
def test_a_file_in_use_does_not_stop_the_sweep(data, monkeypatch) -> None:
    """A PDF open in a viewer must not leave the rest of the folder unswept."""
    busy = _put(paths.output_dir(), "open-in-acrobat.pdf", days_old=5)
    rest = [_put(paths.output_dir(), f"other{n}.pdf", days_old=5)
            for n in range(3)]
    real = type(busy).unlink

    def unlink(self, *a, **k):
        if self.name == busy.name:
            raise PermissionError("used by another process")
        return real(self, *a, **k)

    monkeypatch.setattr(type(busy), "unlink", unlink)
    made = sweep_output(1)
    assert busy.exists() and made.locked == 1
    assert made.removed == 3 and not any(f.exists() for f in rest)


def test_an_empty_folder_sweeps_quietly(data) -> None:
    made = sweep_output(1)
    assert made.removed == 0 and made.kept == 0 and not made.disabled
