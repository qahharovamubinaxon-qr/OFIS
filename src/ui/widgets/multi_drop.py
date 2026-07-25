"""A large drop area accepting MANY images at once (drag&drop or click)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFileDialog, QLabel

_EXT = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


class MultiDropZone(QLabel):
    changed = Signal()

    def __init__(self, hint: str, limit: int = 15) -> None:
        super().__init__()
        self._hint = hint
        self._limit = limit
        self.files: list[Path] = []
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(140)
        self.setWordWrap(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            "QLabel { border: 2px dashed #3a6df0; border-radius: 14px;"
            " color:#8a94a3; font-size: 14px; padding: 12px; }"
        )
        self._render()

    def _render(self) -> None:
        if self.files:
            names = "\n".join(f.name[:40] for f in self.files[:6])
            more = f"\n… +{len(self.files) - 6}" if len(self.files) > 6 else ""
            self.setText(f"✓ {len(self.files)} ta rasm\n{names}{more}")
        else:
            self.setText(f"🖼️\n{self._hint}\n(bosing yoki rasmlarni sudrab tashlang)")

    def clear_files(self) -> None:
        self.files = []
        self._render()

    def _add(self, paths: list[Path]) -> None:
        for p in paths:
            if p.suffix.lower() in _EXT and p not in self.files:
                self.files.append(p)
        self.files = self.files[: self._limit]
        self._render()
        self.changed.emit()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        files, _ = QFileDialog.getOpenFileNames(
            self, "Rasmlar", "", "Rasmlar (*.jpg *.jpeg *.png *.webp *.bmp)")
        if files:
            self._add([Path(f) for f in files])

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        self._add([Path(u.toLocalFile()) for u in event.mimeData().urls()
                   if u.isLocalFile()])
