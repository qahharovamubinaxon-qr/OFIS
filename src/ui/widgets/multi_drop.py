"""A large drop area accepting MANY files at once (drag&drop or click).

Styled by the active theme (``#dropZone`` in the QSS) rather than a hardcoded
stylesheet, so it matches the rest of the app in both light and dark mode.
Accepts images by default; pass ``exts`` to take PDFs (УМУМИЙ's source
document) instead.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
)

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff")
PDF_EXTS = (".pdf",)


class MultiDropZone(QFrame):
    changed = Signal()

    def __init__(
        self,
        hint: str,
        limit: int = 15,
        *,
        exts: tuple[str, ...] = IMAGE_EXTS,
        icon: str = "🖼️",
        min_height: int = 150,
    ) -> None:
        super().__init__()
        self._hint = hint
        self._limit = limit
        self._exts = exts
        self._icon = icon
        self.files: list[Path] = []

        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(min_height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(6)

        self._icon_label = QLabel(icon)
        self._icon_label.setObjectName("dzIcon")
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title = QLabel(hint)
        self._title.setObjectName("dzTitle")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setWordWrap(True)
        self._sub = QLabel("bosing yoki fayllarni sudrab tashlang")
        self._sub.setObjectName("dzHint")
        self._sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sub.setWordWrap(True)

        layout.addWidget(self._icon_label)
        layout.addWidget(self._title)
        layout.addWidget(self._sub)
        self._render()

    # ------------------------------------------------------------------
    def _render(self) -> None:
        if self.files:
            names = " · ".join(f.name[:26] for f in self.files[:4])
            more = f"  +{len(self.files) - 4}" if len(self.files) > 4 else ""
            self._icon_label.setText("✅")
            self._title.setText(f"{len(self.files)} ta fayl tanlandi")
            self._sub.setText(f"{names}{more}")
        else:
            self._icon_label.setText(self._icon)
            self._title.setText(self._hint)
            self._sub.setText("bosing yoki fayllarni sudrab tashlang")
        self.setProperty("filled", bool(self.files))
        self._restyle()

    def _restyle(self) -> None:
        self.style().unpolish(self)
        self.style().polish(self)

    def clear_files(self) -> None:
        self.files = []
        self._render()

    def _add(self, paths: list[Path]) -> None:
        for p in paths:
            if p.suffix.lower() in self._exts and p not in self.files and p.exists():
                self.files.append(p)
        self.files = self.files[: self._limit]
        self._render()
        self.changed.emit()

    # -- interactions --------------------------------------------------
    def _filter(self) -> str:
        if self._exts == PDF_EXTS:
            return "PDF (*.pdf)"
        return "Rasmlar (*.jpg *.jpeg *.png *.webp *.bmp *.tiff)"

    def mousePressEvent(self, event) -> None:  # noqa: N802
        files, _ = QFileDialog.getOpenFileNames(self, self._hint, "", self._filter())
        if files:
            self._add([Path(f) for f in files])

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            self.setProperty("hover", True)
            self._restyle()
            event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self.setProperty("hover", False)
        self._restyle()

    def dropEvent(self, event) -> None:  # noqa: N802
        self.setProperty("hover", False)
        self._add([Path(u.toLocalFile()) for u in event.mimeData().urls()
                   if u.isLocalFile()])
        event.acceptProposedAction()
