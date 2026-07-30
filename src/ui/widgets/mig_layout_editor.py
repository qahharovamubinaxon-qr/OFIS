"""Arrange the МИГ card's values on a firm's own blank, with the mouse.

Every firm hands over its own scan of the ИШЧИ КАРТАСИ and no two are typed
quite alike, so instead of the office editing numbers in a file — and rebuilding
the program each time — it drags each value into place against its own blank and
saves. What it arranges is kept beside that blank, so the next firm's card is
untouched by it, and the next card for THIS firm comes out exactly so.

On screen is what comes out of the printer: the blank is drawn at the size it
prints, and every value is drawn in the card's own Courier at the size it will
be printed at.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.pdf.mig_renderer import digits_spaced, spaced
from src.pdf.mig_spec import BLUE, JOBS

_PICKED = QColor("#ff8c1a")
_GHOST = QColor(120, 130, 145, 110)
_RULE = QColor("#0a7d2e")

#: What each value is called on screen, and a sample of it, in printing order.
SAMPLES: tuple[tuple[str, str, str], ...] = (
    ("series", "СЕРИЯ", "46 26"),
    ("number", "НОМЕР", "0367598"),
    ("surname", "ФАМИЛИЯ", spaced("ЖАХОНГИРОВА")),
    ("surname_lat", "ФАМИЛИЯ лотинча", spaced("JAKHONGIROVA")),
    ("name", "ИСМИ", spaced("МЕХРАНГИЗБОНУ")),
    ("patronymic", "ОТЧЕСТВО", spaced("РАХИМ КИЗИ")),
    ("birth_date", "ТУГИЛГАН САНА", digits_spaced("13.08.2009")),
    ("citizenship", "ГРАЖДАНСТВАСИ", spaced("УЗБЕКИСТАН")),
    ("passport", "ПАСПОРТ", digits_spaced("FB2376204")),
    ("visa", "ВИЗА", "АШХ23652"),
    ("valid_from", "МУДДАТ — С", "20.07.2026"),
    ("valid_to", "МУДДАТ — ДО", "14.10.2026"),
    ("issued", "БЕРИЛГАН САНА (кўк)", "15 03 26"),
)

#: One step of the arrow keys, as a share of the page — about a fifth of a
#: millimetre, which is as fine as anyone needs.
_NUDGE_X = 0.0004
_NUDGE_Y = 0.0003


class LayoutCanvas(QWidget):
    """The blank with every value on it — click one, drag it, size it."""

    def __init__(self, page: QPixmap, fields, sex, jobs, parent=None) -> None:
        super().__init__(parent)
        self._page = page
        #: key → [x, baseline, size]; the sex X and the job rules ride along
        self.fields = {k: [s.x, s.baseline, s.size] for k, s in fields.items()}
        self.sex = {k: [s.x, s.baseline, s.size] for k, s in sex.items()}
        self.jobs = {k: [r.x0, r.x1, r.y] for k, r in jobs.items()}
        self.picked: tuple[str, str] | None = None      # ("field", key)
        self._grab = QPoint()
        self.setMinimumSize(page.size())
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # -- what is where -------------------------------------------------
    def _items(self):
        """Every draggable thing: (kind, key, label, text, x, baseline, size)."""
        for key, label, sample in SAMPLES:
            x, base, size = self.fields[key]
            yield ("field", key, label, sample, x, base, size)
        for key, label in (("male", "МУЖ — X"), ("female", "ЖЕН — X")):
            x, base, size = self.sex[key]
            yield ("sex", key, label, "X", x, base, size)

    def _font(self, size: float) -> QFont:
        font = QFont("Courier New")
        font.setPixelSize(max(4, round(size * self._page.height())))
        return font

    def _rect_of(self, text: str, x: float, base: float, size: float) -> QRect:
        metrics = QFontMetrics(self._font(size))
        left = round(x * self._page.width())
        bottom = round(base * self._page.height())
        return QRect(left, bottom - metrics.ascent(),
                     max(6, metrics.horizontalAdvance(text)),
                     metrics.ascent() + metrics.descent())

    # -- painting ------------------------------------------------------
    def paintEvent(self, event) -> None:      # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._page)
        for kind, key, _label, text, x, base, size in self._items():
            rect = self._rect_of(text, x, base, size)
            chosen = self.picked == (kind, key)
            painter.setFont(self._font(size))
            painter.setPen(QPen(QColor(*(int(c * 255) for c in BLUE))
                                if key == "issued" else QColor(20, 20, 20)))
            painter.drawText(QPoint(rect.left(),
                                    round(base * self._page.height())), text)
            painter.setPen(QPen(_PICKED if chosen else _GHOST,
                                2 if chosen else 1, Qt.PenStyle.DashLine))
            painter.drawRect(rect.adjusted(-2, -2, 2, 2))
        for key, (x0, x1, y) in self.jobs.items():
            chosen = self.picked == ("job", key)
            painter.setPen(QPen(_PICKED if chosen else _RULE, 3 if chosen else 2))
            top = round(y * self._page.height())
            painter.drawLine(round(x0 * self._page.width()), top,
                             round(x1 * self._page.width()), top)
        painter.end()

    # -- mouse ---------------------------------------------------------
    def _hit(self, point: QPoint):
        for kind, key, _label, text, x, base, size in self._items():
            if self._rect_of(text, x, base, size).adjusted(-3, -3, 3, 3).contains(point):
                return (kind, key)
        for key, (x0, x1, y) in self.jobs.items():
            top = round(y * self._page.height())
            if (abs(point.y() - top) <= 6
                    and round(x0 * self._page.width()) - 6 <= point.x()
                    <= round(x1 * self._page.width()) + 6):
                return ("job", key)
        return None

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        point = event.position().toPoint()
        self.picked = self._hit(point)
        self._grab = point
        self.setFocus()
        self.update()

    def mouseMoveEvent(self, event) -> None:   # noqa: N802 - Qt override
        if self.picked is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        point = event.position().toPoint()
        dx = (point.x() - self._grab.x()) / self._page.width()
        dy = (point.y() - self._grab.y()) / self._page.height()
        self._grab = point
        self._move(dx, dy)

    def wheelEvent(self, event) -> None:       # noqa: N802 - Qt override
        """The wheel makes the picked value bigger or smaller."""
        if self.picked is None:
            return
        self.resize_picked(1 if event.angleDelta().y() > 0 else -1)

    def keyPressEvent(self, event) -> None:    # noqa: N802 - Qt override
        steps = {Qt.Key.Key_Left: (-_NUDGE_X, 0.0),
                 Qt.Key.Key_Right: (_NUDGE_X, 0.0),
                 Qt.Key.Key_Up: (0.0, -_NUDGE_Y),
                 Qt.Key.Key_Down: (0.0, _NUDGE_Y)}
        if event.key() in steps and self.picked is not None:
            self._move(*steps[event.key()])
            return
        if event.key() in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.resize_picked(1)
        elif event.key() == Qt.Key.Key_Minus:
            self.resize_picked(-1)

    # -- moving --------------------------------------------------------
    def _move(self, dx: float, dy: float) -> None:
        kind, key = self.picked                      # type: ignore[misc]
        if kind == "job":
            x0, x1, y = self.jobs[key]
            self.jobs[key] = [max(0.0, x0 + dx), min(1.0, x1 + dx),
                              min(1.0, max(0.0, y + dy))]
        else:
            store = self.fields if kind == "field" else self.sex
            x, base, size = store[key]
            store[key] = [min(1.0, max(0.0, x + dx)),
                          min(1.0, max(0.0, base + dy)), size]
        self.update()

    def resize_picked(self, direction: int) -> None:
        """One step bigger or smaller — about a point of type."""
        if self.picked is None:
            return
        kind, key = self.picked
        if kind == "job":
            # a rule has no size; the wheel stretches its RIGHT end instead
            x0, x1, y = self.jobs[key]
            self.jobs[key] = [x0, min(1.0, max(x0 + 0.01, x1 + 0.004 * direction)), y]
        else:
            store = self.fields if kind == "field" else self.sex
            x, base, size = store[key]
            store[key] = [x, base, max(0.004, size + 0.0012 * direction)]
        self.update()

    def pick(self, kind: str, key: str) -> None:
        self.picked = (kind, key)
        self.setFocus()
        self.update()


class MigLayoutEditor(QDialog):
    """«Матнларни жойлаш» — drag each value where this firm's card wants it."""

    def __init__(self, page_png: bytes, fields, sex, jobs, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Матнларни жойлаш — сичқонча билан суринг")
        self.setMinimumSize(900, 780)

        page = QPixmap()
        page.loadFromData(page_png)
        self._canvas = LayoutCanvas(page, fields, sex, jobs)

        outer = QVBoxLayout(self)
        hint = QLabel(
            "Матнни босиб ушланг ва суринг — жойи ўзгаради.\n"
            "Танланганини КАТТА-КИЧИК қилиш: сичқонча ғилдираги, ёки + / −.\n"
            "Аниқ суриш: ўқ тугмалари (←↑↓→).\n"
            "Иш ўрни тагидаги яшил чизиқлар ҳам сурилади; ғилдирак уларнинг "
            "узунлигини ўзгартиради.\n"
            "Сақлангач, бу фирманинг ҳар бир картаси шу жойларга тушади.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8a94a3;")
        outer.addWidget(hint)

        picker = QHBoxLayout()
        picker.addWidget(QLabel("Танлаш:"))
        from PySide6.QtWidgets import QComboBox

        self._pick = QComboBox()
        for key, label, _sample in SAMPLES:
            self._pick.addItem(label, ("field", key))
        self._pick.addItem("МУЖ — X", ("sex", "male"))
        self._pick.addItem("ЖЕН — X", ("sex", "female"))
        for key, label, _rule in JOBS:
            self._pick.addItem(f"чизиқ: {label}", ("job", key))
        self._pick.currentIndexChanged.connect(self._on_pick)
        picker.addWidget(self._pick, stretch=1)
        bigger = QPushButton("＋ катта")
        bigger.clicked.connect(lambda: self._canvas.resize_picked(1))
        picker.addWidget(bigger)
        smaller = QPushButton("－ кичик")
        smaller.clicked.connect(lambda: self._canvas.resize_picked(-1))
        picker.addWidget(smaller)
        outer.addLayout(picker)

        scroll = QScrollArea()
        scroll.setWidget(self._canvas)
        scroll.setWidgetResizable(False)
        outer.addWidget(scroll, stretch=1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _on_pick(self) -> None:
        kind, key = self._pick.currentData()
        self._canvas.pick(kind, key)

    def layout_data(self) -> dict:
        """What to keep beside this firm's blank."""
        return {"fields": {k: [round(v, 5) for v in val]
                           for k, val in self._canvas.fields.items()},
                "sex": {k: [round(v, 5) for v in val]
                        for k, val in self._canvas.sex.items()},
                "jobs": {k: [round(v, 5) for v in val]
                         for k, val in self._canvas.jobs.items()}}
