"""Dashboard — today's count, totals, next number, AI status, recent documents."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QVBoxLayout,
    QWidget,
)

from src.database.repositories.generated_repo import GeneratedRepository
from src.services.company_service import CompanyService
from src.services.generation_service import GenerationService


def _stat(title: str, value: str) -> QWidget:
    box = QWidget()
    box.setObjectName("statCard")
    lay = QVBoxLayout(box)
    v = QLabel(value)
    v.setObjectName("statValue")
    t = QLabel(title)
    t.setObjectName("statLabel")
    lay.addWidget(v)
    lay.addWidget(t)
    return box


class DashboardView(QWidget):
    def __init__(
        self, generated: GeneratedRepository, companies: CompanyService, gen: GenerationService
    ) -> None:
        super().__init__()
        self._generated = generated
        self._companies = companies
        self._gen = gen

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        title = QLabel("Boshqaruv paneli / Панель")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        self._grid = QGridLayout()
        self._grid.setSpacing(12)
        cards = QHBoxLayout()
        cards.addLayout(self._grid)
        root.addLayout(cards)

        recent_label = QLabel("So'nggi yaratilganlar / Недавние:")
        root.addWidget(recent_label)
        self._recent = QListWidget()
        root.addWidget(self._recent, stretch=1)

        self.refresh()

    def refresh(self) -> None:
        for i in reversed(range(self._grid.count())):
            w = self._grid.itemAt(i).widget()
            if w:
                w.setParent(None)
        self._grid.addWidget(_stat("Bugun", str(self._generated.count_today())), 0, 0)
        self._grid.addWidget(_stat("Jami PDF", str(self._generated.count_total())), 0, 1)
        self._grid.addWidget(_stat("Firmalar", str(self._companies.count())), 0, 2)
        self._grid.addWidget(_stat("Keyingi №", str(self._gen.next_reg_number())), 0, 3)

        self._recent.clear()
        for r in self._generated.recent(20):
            self._recent.addItem(f"№{r.reg_number}  ·  {r.full_name}  ·  {r.company_name}  ·  {r.created_at}")
