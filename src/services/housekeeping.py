"""Sweeping the finished documents off the disk.

Every paper the office prints is written to ``output/`` and stays there. Nobody
goes back for it — the worker was handed his copy the same minute — but it
accumulates, and twice now it has filled the C: drive of the office machine and
stopped the whole program. 538 files, 1.8 GB, of which 1.67 GB had been sitting
there for over a day.

So finished documents are swept after a day. Two things make that safe to do
without asking:

*It only ever touches ``output``.* The blanks the office uploaded live in
``templates`` — a different folder, 2.2 GB of scans it cannot replace — and the
office has said more than once that they must never be deleted. Every path is
resolved and checked to be inside the output folder before anything happens to
it, so a shortcut or a junction pointing elsewhere is refused rather than
followed. ``archive`` and ``backups`` are left alone too.

*It never touches today's work.* The cut is by modification time, and the
shortest retention the office can set is a whole day, so a document made this
morning survives however many times the program is opened.

Setting ``output.keep_days`` to 0 turns the sweep off entirely — the safe
reading of a number typed by mistake is «keep everything», never «delete
everything».
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from src.common.logging import get_logger
from src.config import paths

log = get_logger(__name__)

#: How long a finished document stays on the disk. The office asked for one
#: day: it hands the worker his copy the same minute it is printed, and the
#: archive keeps what has to be kept.
DEFAULT_KEEP_DAYS = 1
#: Where the office may change that.
KEY_KEEP_DAYS = "output.keep_days"

_DAY_S = 86_400


@dataclass(frozen=True)
class SweepResult:
    """What the sweep did, for the log and for the tests."""

    removed: int = 0
    freed: int = 0
    kept: int = 0
    #: files that could not be deleted — open in a viewer, most likely
    locked: int = 0
    #: True when the office has turned the sweep off
    disabled: bool = False

    @property
    def freed_mb(self) -> float:
        return self.freed / 1_048_576


def keep_days(settings) -> int:
    """How many days the office wants kept, sanely."""
    try:
        wanted = int(settings.get(KEY_KEEP_DAYS, DEFAULT_KEEP_DAYS))
    except (TypeError, ValueError):
        return DEFAULT_KEEP_DAYS
    return max(0, wanted)


def sweep_output(days: int = DEFAULT_KEEP_DAYS, *,
                 now: float | None = None) -> SweepResult:
    """Delete finished documents older than ``days``. ``0`` sweeps nothing."""
    if days <= 0:
        log.info("Тозалаш ўчирилган (output.keep_days=0)")
        return SweepResult(disabled=True)

    root = paths.output_dir().resolve()
    cut = (now if now is not None else time.time()) - days * _DAY_S
    removed = freed = kept = locked = 0

    for item in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        try:
            if item.is_symlink() or not _inside(item, root):
                # a shortcut out of the folder is refused, never followed:
                # the blanks in templates/ are one junction away
                log.warning("Тозалаш: %s четда — тегилмади", item.name)
                continue
            if item.is_dir():
                if not any(item.iterdir()):
                    item.rmdir()            # an emptied day's folder
                continue
            if item.stat().st_mtime >= cut:
                kept += 1
                continue
            size = item.stat().st_size
            item.unlink()
            removed += 1
            freed += size
        except (PermissionError, OSError) as exc:
            # open in a viewer, or vanished under us — neither is worth
            # stopping the sweep, and neither is worth troubling the office
            locked += 1
            log.debug("Тозалаш: %s ўчмади (%s)", item.name, exc.__class__.__name__)

    made = SweepResult(removed=removed, freed=freed, kept=kept, locked=locked)
    if removed or locked:
        log.info("Тозаланди: %d та ҳужжат, %.0f MB бўшади · %d та қолди"
                 "%s", removed, made.freed_mb, kept,
                 f" · {locked} та банд" if locked else "")
    return made


def _inside(item: Path, root: Path) -> bool:
    """Is this really under the output folder, once every link is resolved?"""
    try:
        return root == item.resolve(strict=False) or \
            root in item.resolve(strict=False).parents
    except OSError:
        return False
