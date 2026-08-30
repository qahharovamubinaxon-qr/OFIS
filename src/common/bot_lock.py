"""One bot at a time: which process owns the Telegram token right now.

Telegram allows a single long-polling consumer per token. Two — the desktop
app's in-app bot and the headless ``bot.bat`` — polling at once means one of
them gets 409 Conflict and the bot answers unreliably.

So whoever runs the bot writes a small lock file and keeps it fresh; the other
sees the fresh lock and stands aside. If the owner crashes, the lock goes
stale within a minute or two and the next start takes over — no manual cleanup.
The file lives in AppData beside the database, so both processes see the same
one.
"""

from __future__ import annotations

import contextlib
import os
import time
from pathlib import Path

from src.common.logging import get_logger
from src.config import paths

log = get_logger(__name__)

#: How long a lock is trusted after its last heartbeat. The owner touches it
#: every :data:`HEARTBEAT_S`; three missed beats and it is considered dead.
STALE_S = 90
HEARTBEAT_S = 30


def _path() -> Path:
    return paths.data_dir() / "bot.lock"


def running(max_age: float = STALE_S) -> bool:
    """Is another process already running the bot (a fresh lock present)?"""
    lock = _path()
    try:
        return lock.exists() and (time.time() - lock.stat().st_mtime) < max_age
    except OSError:
        return False


def acquire() -> None:
    """Claim the lock for this process (its PID, for the curious)."""
    try:
        _path().write_text(str(os.getpid()), encoding="utf-8")
    except OSError as exc:  # noqa: BLE001 - the lock is best-effort
        log.debug("bot.lock ёзилмади: %s", exc)


def touch() -> None:
    """Keep the lock fresh — called on a heartbeat while the bot runs."""
    lock = _path()
    try:
        if lock.exists():
            os.utime(lock, None)
        else:
            acquire()
    except OSError:  # noqa: BLE001 - never let a heartbeat crash the bot
        pass


def release() -> None:
    """Drop the lock on a clean shutdown."""
    with contextlib.suppress(OSError):
        _path().unlink(missing_ok=True)
