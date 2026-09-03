"""«Ҳужжатлардан ўқилгани» — the read-then-check panel every section shares.

Reading and printing used to be one press across the app, so a name misread
off a passport or patent went straight onto a filed document with nobody
having seen it. The office asked for the same thing РЕГИСТРАЦИЯ and ХОСТЕЛ got,
everywhere: the moment the passport lands it is read, the values appear in
editable boxes, the operator checks and corrects, and the form is printed from
what is IN THE BOXES — never from the raw reading again.

This is that panel, in one place, so a section adds the whole flow in a few
lines instead of copying it. Drop it under the upload zones, connect the
passport drop to a read, call :meth:`fill` with what came back, and print from
:meth:`edited`.
"""

from __future__ import annotations

from datetime import date, datetime

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
)

#: Everything a form prints off the worker's documents, shown for the operator
#: to check. The name and citizenship come off the patent when there is one (it
#: prints them in Russian), the rest off the passport — but once here they are
#: just the values, and these boxes are the single source the form prints from.
_BOXES: tuple[tuple[str, str, str], ...] = (
    ("surname", "Фамилия:", "Исоев"),
    ("name", "Имя:", "Аслидин"),
    ("patronymic", "Отчество:", "Холбердиевич"),
    ("citizenship", "Гражданство:", "ТАДЖИКИСТАН"),
    ("series", "Паспорт серия:", "P"),
    ("number", "Паспорт номер:", "405847273"),
    ("issue_date", "Паспорт берилган:", "18.01.2025"),
    ("expiry_date", "Паспорт амал охири:", "17.01.2035"),
)

_TITLE = "Ҳужжатлардан ўқилгани — текширинг, хатоси бўлса тўғриланг"


def _date_text(when: date | None) -> str:
    return when.strftime("%d.%m.%Y") if when else ""


def _date_of(said: str) -> date | None:
    """«18.01.2025» → a date, or nothing when it is not one."""
    said = (said or "").strip()
    for shape in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(said, shape).date()
        except ValueError:
            continue
    return None


class PassportReview(QGroupBox):
    """Editable boxes for what a passport (and optional patent) said.

    Starts hidden; :meth:`fill` reveals it. Print from :meth:`edited`.
    """

    def __init__(self, title: str = _TITLE, parent=None) -> None:
        super().__init__(title, parent)
        grid = QGridLayout(self)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        self._boxes: dict[str, QLineEdit] = {}
        for at, (key, label, hint) in enumerate(_BOXES):
            box = QLineEdit()
            box.setPlaceholderText(hint)
            grid.addWidget(QLabel(label), at // 2, (at % 2) * 2)
            grid.addWidget(box, at // 2, (at % 2) * 2 + 1)
            self._boxes[key] = box
        last = len(_BOXES) // 2
        grid.addWidget(QLabel("Жинси:"), last, 0)
        self._gender = QComboBox()
        self._gender.addItems(["Мужской", "Женский"])
        grid.addWidget(self._gender, last, 1)
        grid.addWidget(QLabel("Туғилган сана:"), last, 2)
        self._born = QDateEdit(QDate(2000, 1, 1))
        self._born.setCalendarPopup(True)
        self._born.setDisplayFormat("dd.MM.yyyy")
        grid.addWidget(self._born, last, 3)
        self.setVisible(False)
        from src.ui.widgets.shadow import add_shadow
        add_shadow(self)

    # ------------------------------------------------------------------
    def fill(self, passport, patent=None) -> None:
        """Show what was read and reveal the panel.

        The patent's name wins when there is one — it is already the Russian
        form the document prints; otherwise the passport's own values are used,
        resolved the same way the printed form resolves them.
        """
        from src.domain.enums import Gender

        resolved = {
            "surname": (patent.holder_surname if patent else None) or passport.surname,
            "name": (patent.holder_name if patent else None) or passport.name,
            "patronymic": (patent.holder_patronymic if patent else None)
            or passport.patronymic or "",
            "citizenship": (patent.holder_citizenship if patent else None)
            or passport.nationality or "",
            "series": passport.series or "",
            "number": passport.number or "",
            "issue_date": _date_text(passport.issue_date),
            "expiry_date": _date_text(passport.expiry_date),
        }
        for key, box in self._boxes.items():
            box.setText(str(resolved.get(key, "")))
        self._gender.setCurrentText(
            "Женский" if passport.gender == Gender.FEMALE else "Мужской")
        if passport.birth_date:
            self._born.setDate(QDate(passport.birth_date.year,
                                     passport.birth_date.month,
                                     passport.birth_date.day))
        self.setVisible(True)

    def reveal(self) -> None:
        """Open the empty panel — e.g. after a failed read, to type by hand."""
        self.setVisible(True)

    def has_surname(self) -> bool:
        return bool(self._boxes["surname"].text().strip())

    def reset(self) -> None:
        for box in self._boxes.values():
            box.clear()
        self.setVisible(False)

    def edited(self):
        """The worker as it stands IN THE BOXES — never as it was read.

        A single Passport carries every value a form needs, so the patent is
        not returned: its only job was to supply a Russian name when the
        passport had none, and that name is already in a box.
        """
        from src.domain.documents import Passport
        from src.domain.enums import Gender

        said = {key: box.text().strip() for key, box in self._boxes.items()}
        return Passport(
            surname=said.get("surname") or "—",
            name=said.get("name") or "—",
            patronymic=said.get("patronymic") or None,
            gender=(Gender.FEMALE if self._gender.currentText() == "Женский"
                    else Gender.MALE),
            birth_date=self._born.date().toPython(),
            nationality=said.get("citizenship") or None,
            series=said.get("series") or None,
            number=said.get("number") or "—",
            issue_date=_date_of(said.get("issue_date", "")),
            expiry_date=_date_of(said.get("expiry_date", "")),
        )
