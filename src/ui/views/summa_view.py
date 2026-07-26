"""СУММА-ДАТА — write a date or an amount out in words (пропись).

Type a date or a sum and the Russian wording appears next to it instantly,
ready to copy into any document: «Двадцать шестое июля две тысячи двадцать
шестого года», «Десять тысяч рублей 00 копеек». Offline — no AI needed.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.ui.widgets.card import Card
from src.utils.rus_words import amount_to_words, date_to_words, format_amount, parse_amount


class SummaView(QWidget):
    def __init__(self) -> None:
        super().__init__()

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        title = QLabel("СУММА-ДАТА — пропись")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        # -- date --------------------------------------------------------
        date_card = Card("📅", "Сана / Дата",
                         "Числони танланг — ёнида прописью чиқади.")
        row = QHBoxLayout()
        self._date = QDateEdit()
        self._date.setDisplayFormat("dd.MM.yyyy")
        self._date.setDate(QDate.currentDate())
        self._date.setCalendarPopup(True)
        self._date.setMinimumWidth(160)
        self._date.dateChanged.connect(self._update_date)
        row.addWidget(self._date)
        row.addStretch(1)
        date_card.add(row)

        self._date_out = _Output()
        self._date_out.copy_clicked.connect(
            lambda: self._copy(self._date_out.text()))
        date_card.add(self._date_out)
        root.addWidget(date_card)

        # -- amount ------------------------------------------------------
        sum_card = Card("💰", "Сумма",
                        "Суммани ёзинг (10000 · 10 000,00 · 27500,50) — "
                        "прописью ва расмий кўриниши чиқади.")
        srow = QHBoxLayout()
        self._sum = QLineEdit()
        self._sum.setPlaceholderText("10000")
        self._sum.setMinimumWidth(200)
        self._sum.textChanged.connect(self._update_sum)
        srow.addWidget(self._sum)
        self._sum_digits = QLabel("")
        self._sum_digits.setObjectName("cardTitle")
        srow.addWidget(self._sum_digits)
        srow.addStretch(1)
        sum_card.add(srow)

        self._sum_out = _Output()
        self._sum_out.copy_clicked.connect(
            lambda: self._copy(self._sum_out.text()))
        sum_card.add(self._sum_out)
        root.addWidget(sum_card)

        self._toast = QLabel("")
        self._toast.setObjectName("cardNote")
        root.addWidget(self._toast)
        root.addStretch(1)

        self._update_date()
        self._update_sum("")

    # ------------------------------------------------------------------
    def reset(self) -> None:
        self._date.setDate(QDate.currentDate())
        self._sum.clear()
        self._toast.setText("")

    def _selected_date(self) -> date:
        q = self._date.date()
        return date(q.year(), q.month(), q.day())

    def _update_date(self, *_args) -> None:
        self._date_out.set_text(date_to_words(self._selected_date()))

    def _update_sum(self, text: str) -> None:
        try:
            rub, kop = parse_amount(text)
        except ValueError:
            self._sum_digits.setText("")
            self._sum_out.set_text("")
            return
        self._sum_digits.setText(f"= {format_amount(rub, kop)} ₽")
        self._sum_out.set_text(amount_to_words(rub, kop))

    def _copy(self, text: str) -> None:
        if not text:
            return
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
            self._toast.setText("✓ Нусха олинди / Скопировано")


class _Output(QWidget):
    """A read-only wording line with a Copy button."""

    copy_clicked = Signal()

    def __init__(self) -> None:
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        self._field = QLineEdit()
        self._field.setReadOnly(True)
        self._field.setCursorPosition(0)
        self._field.setTextMargins(2, 0, 2, 0)
        row.addWidget(self._field, stretch=1)

        copy = QPushButton("📋  Нусха")
        copy.setCursor(Qt.CursorShape.PointingHandCursor)
        copy.clicked.connect(self.copy_clicked.emit)
        row.addWidget(copy)

    def set_text(self, text: str) -> None:
        self._field.setText(text)
        self._field.setCursorPosition(0)

    def text(self) -> str:
        return self._field.text()
