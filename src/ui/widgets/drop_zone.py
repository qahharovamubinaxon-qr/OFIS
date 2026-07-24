"""A large, modern upload tile: click to browse OR drag & drop a file onto it.

Used for passport / patent images. Holds the chosen path; shows the filename and
a "filled" style once set. Accepts a drag from Explorer or a click that opens a
file dialog.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QFileDialog, QFrame, QLabel, QVBoxLayout

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}


class DropZone(QFrame):
    changed = Signal()

    def __init__(self, icon: str, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(112)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._title = title
        self._path: Path | None = None

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(4)

        self._icon = QLabel(icon)
        self._icon.setObjectName("dzIcon")
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label = QLabel(title)
        self._label.setObjectName("dzTitle")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setWordWrap(True)
        self._hint = QLabel("Bosing yoki rasmni sudrab tashlang")
        self._hint.setObjectName("dzHint")
        self._hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self._icon)
        layout.addWidget(self._label)
        layout.addWidget(self._hint)

    @property
    def path(self) -> Path | None:
        return self._path

    def clear(self) -> None:
        self._path = None
        self._label.setText(self._title)
        self._hint.setText("Bosing yoki rasmni sudrab tashlang")
        self.setProperty("filled", False)
        self._restyle()

    def _set_path(self, path: Path) -> None:
        self._path = path
        self._label.setText(f"✓ {path.name}")
        self._hint.setText("Almashtirish uchun bosing")
        self.setProperty("filled", True)
        self._restyle()
        self.changed.emit()

    def _restyle(self) -> None:
        self.style().unpolish(self)
        self.style().polish(self)

    # -- interactions ------------------------------------------------------
    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        path, _ = QFileDialog.getOpenFileName(
            self, self._title, "", "Images (*.jpg *.jpeg *.png *.webp *.bmp *.tiff)"
        )
        if path:
            self._set_path(Path(path))

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if self._first_image(event):
            self.setProperty("hover", True)
            self._restyle()
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self.setProperty("hover", False)
        self._restyle()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        path = self._first_image(event)
        self.setProperty("hover", False)
        self._restyle()
        if path:
            self._set_path(path)
            event.acceptProposedAction()

    @staticmethod
    def _first_image(event) -> Path | None:
        mime = event.mimeData()
        if not mime.hasUrls():
            return None
        for url in mime.urls():
            p = Path(url.toLocalFile())
            if p.suffix.lower() in _IMAGE_EXTS and p.exists():
                return p
        return None
