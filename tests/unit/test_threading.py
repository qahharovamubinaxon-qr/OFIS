"""run_async must deliver to EVERY callable shape — lambdas included.

The IMGBB view hung forever on «юкланаяпти…» because a lambda handed to
``run_async`` had no owner: PySide6 kept only a weak reference in the signal
connection and the garbage collector ate it before the queued delivery
landed. Bound methods of live QObjects survived by accident, which is why
every other view seemed fine. These tests pin the fix.
"""

from __future__ import annotations

import gc
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _app():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _spin(app, done, timeout=6.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline and not done():
        gc.collect()          # the old bug needed GC to strike — force it
        app.processEvents()
        time.sleep(0.01)


def test_a_lambda_callback_still_receives_the_result() -> None:
    from src.common.threading import run_async

    app = _app()
    got: list = []
    run_async(lambda: 41 + 1,
              on_success=lambda value: got.append(value),
              on_error=lambda error: got.append(error))
    _spin(app, lambda: got)
    assert got == [42], f"the lambda never heard back: {got}"


def test_a_lambda_error_callback_still_fires() -> None:
    from src.common.threading import run_async

    def blow_up():
        raise ValueError("бум")

    app = _app()
    got: list = []
    run_async(blow_up,
              on_success=lambda value: got.append(("ok", value)),
              on_error=lambda error: got.append(("err", str(error))))
    _spin(app, lambda: got)
    assert got == [("err", "бум")]


def test_many_parallel_lambdas_all_arrive() -> None:
    from src.common.threading import run_async

    app = _app()
    got: list = []
    for n in range(12):
        run_async(lambda v=n: v * 10,
                  on_success=lambda value: got.append(value),
                  on_error=lambda error: got.append(error))
    _spin(app, lambda: len(got) >= 12, timeout=10.0)
    assert sorted(got) == [n * 10 for n in range(12)]
