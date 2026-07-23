"""Run a use-case off the UI thread.

OCR, AI, PDF, backup and archive are long-running; they must never block the Qt
event loop (see UI_UX.md — the window stays responsive). ``run_async`` executes a
plain callable on a worker thread and delivers the result/error back to the
caller through Qt signals, so the presentation layer never touches threads
directly and business code stays free of Qt.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class _WorkerSignals(QObject):
    finished = Signal(object)  # result value
    failed = Signal(Exception)


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

    ``on_success``/``on_error`` are invoked back on the UI thread via queued
    signal delivery.
    """
    worker = _Worker(fn, *args, **kwargs)
    worker.signals.finished.connect(on_success)
    worker.signals.failed.connect(on_error)
    QThreadPool.globalInstance().start(worker)
