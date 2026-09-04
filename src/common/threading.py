"""Run a use-case off the UI thread.

OCR, AI, PDF, backup and archive are long-running; they must never block the Qt
event loop (see UI_UX.md — the window stays responsive). ``run_async`` executes a
plain callable on a worker thread and delivers the result/error back to the
caller through Qt signals, so the presentation layer never touches threads
directly and business code stays free of Qt.

The delivery goes through a :class:`_Dispatcher` QObject that lives in the
caller's (UI) thread and holds the callbacks strongly until one of them has
run. Without it a lambda handed to ``run_async`` has no owner, PySide6 keeps
only a weak reference in the connection, the garbage collector eats it — and
the result silently never arrives. Bound methods survived that by accident;
lambdas did not (the IMGBB view hung on «юкланаяпти…» exactly this way).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from src.common.logging import get_logger

log = get_logger(__name__)

#: Dispatchers waiting for their queued delivery — the strong references that
#: keep the callbacks (and the dispatcher itself) alive until they have run.
_PENDING: set[_Dispatcher] = set()


class _WorkerSignals(QObject):
    finished = Signal(object)  # result value
    failed = Signal(Exception)


class _Dispatcher(QObject):
    """Lives in the caller's thread; hands the result to the callbacks there."""

    def __init__(self, on_success: Callable[[Any], None],
                 on_error: Callable[[Exception], None]) -> None:
        super().__init__()
        self._on_success = on_success
        self._on_error = on_error
        _PENDING.add(self)

    def ok(self, value: Any) -> None:
        _PENDING.discard(self)
        self._on_success(value)

    def fail(self, error: Exception) -> None:
        _PENDING.discard(self)
        self._on_error(error)


class _Worker(QRunnable):
    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self.signals = _WorkerSignals()

    def run(self) -> None:
        try:
            result = self._fn(*self._args, **self._kwargs)
        except Exception as exc:  # noqa: BLE001 — boundary: marshalled to the UI thread
            # A background failure used to reach only the on_error callback,
            # which often just sets a status line — so a read that failed on a
            # worker thread left NOTHING in the log and looked, from the office's
            # side, like «ишламаяпти». Every such failure is now written down,
            # with its traceback, so the cause is never invisible again.
            name = getattr(self._fn, "__name__", repr(self._fn))
            log.warning("фон вазифа хато берди: %s(...)", name, exc_info=exc)
            self.signals.failed.emit(exc)
        else:
            self.signals.finished.emit(result)


def run_async(
    fn: Callable[..., Any],
    *args: Any,
    on_success: Callable[[Any], None],
    on_error: Callable[[Exception], None],
    **kwargs: Any,
) -> None:
    """Execute ``fn(*args, **kwargs)`` on the global thread pool.

    ``on_success``/``on_error`` are invoked back on the caller's thread via
    queued signal delivery — lambdas, partials and bound methods all arrive.
    """
    worker = _Worker(fn, *args, **kwargs)
    keeper = _Dispatcher(on_success, on_error)
    worker.signals.finished.connect(keeper.ok)
    worker.signals.failed.connect(keeper.fail)
    QThreadPool.globalInstance().start(worker)
