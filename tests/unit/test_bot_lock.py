"""One bot at a time — the lock that keeps the desktop app and bot.bat apart.

Telegram allows a single long-polling consumer per token; two collide on 409.
Whoever runs the bot writes a fresh lock, and the other stands aside. A crashed
owner leaves a stale lock that the next start is allowed to take over.
"""

from __future__ import annotations

import os
import time

import pytest
from src.common import bot_lock
from src.config import paths


@pytest.fixture
def appdata(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    paths.data_dir.cache_clear()
    yield tmp_path
    paths.data_dir.cache_clear()


def test_nothing_is_running_at_first(appdata) -> None:
    assert not bot_lock.running()


def test_acquire_makes_it_running(appdata) -> None:
    bot_lock.acquire()
    assert bot_lock.running()


def test_the_lock_holds_this_processs_pid(appdata) -> None:
    bot_lock.acquire()
    assert bot_lock._path().read_text() == str(os.getpid())


def test_a_stale_lock_is_not_running(appdata) -> None:
    """A crashed owner must not keep the token hostage for ever."""
    bot_lock.acquire()
    old = time.time() - bot_lock.STALE_S - 30
    os.utime(bot_lock._path(), (old, old))
    assert not bot_lock.running()


def test_a_heartbeat_keeps_it_fresh(appdata) -> None:
    bot_lock.acquire()
    old = time.time() - bot_lock.STALE_S - 30
    os.utime(bot_lock._path(), (old, old))
    assert not bot_lock.running()
    bot_lock.touch()
    assert bot_lock.running()


def test_release_frees_it(appdata) -> None:
    bot_lock.acquire()
    bot_lock.release()
    assert not bot_lock.running()
    assert not bot_lock._path().exists()


def test_touch_creates_the_lock_if_it_vanished(appdata) -> None:
    bot_lock.acquire()
    bot_lock.release()
    bot_lock.touch()                 # e.g. someone deleted the file under us
    assert bot_lock.running()


def test_the_desktop_app_stands_aside_when_the_lock_is_held() -> None:
    """app.py must consult the lock before starting its own bot."""
    import pathlib

    import src.app as app_module

    text = pathlib.Path(app_module.__file__).read_text(encoding="utf-8")
    assert "bot_lock.running()" in text
    # and only start the in-app bot when it is NOT held
    start = text.index("bot_lock.running()")
    assert "bot.start()" in text[start:start + 400]
