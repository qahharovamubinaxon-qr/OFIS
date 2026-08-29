"""A large, modern upload tile: click to browse OR drag & drop a file onto it.

Used for passport / patent images, and — where the caller passes ``extensions``
— for ready documents such as the трудовой договор and the уведомление, which
arrive as PDFs rather than photographs. Holds the chosen path; shows the
filename and a "filled" style once set. Accepts a drag from Explorer or a click
that opens a file dialog.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QFileDialog, QFrame, QLabel, QVBoxLayout

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}
#: Tiles that take a ready document rather than a photograph of one — the
#: трудовой договор and the уведомление arrive as PDFs.
PDF_EXTS = {".pdf"}
DOCUMENT_EXTS = _IMAGE_EXTS | PDF_EXTS


class DropZone(QFrame):
    changed = Signal()

    def __init__(self, icon: str, title: str, parent=None,
                 multiple: bool = False,
                 extensions: set[str] | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(120)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        from src.ui.widgets.shadow import add_shadow
        add_shadow(self, blur=18, dy=3, alpha=45)
        self._title = title
        #: What this tile takes. Photographs unless the caller says otherwise.
        self._exts = ({e.lower() for e in extensions} if extensions
                      else set(_IMAGE_EXTS))
        self._path: Path | None = None
        #: In ``multiple`` mode every drop *adds* to the pile rather than
        #: replacing it — a licence is photographed front and then back, and
        #: the second photo must not throw the first one away.
        self._multiple = multiple
        self._paths: list[Path] = []

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

    @property
    def paths(self) -> list[Path]:
        """Everything dropped so far, in the order it arrived."""
        return list(self._paths)

    def clear(self) -> None:
        self._path = None
        self._paths = []
        self._label.setText(self._title)
        self._hint.setText("Bosing yoki rasmni sudrab tashlang")
        self.setProperty("filled", False)
        self._restyle()

    def _set_path(self, path: Path) -> None:
        self._add([path])

    def _add(self, paths: list[Path]) -> None:
        if not paths:
            return
        if self._multiple:
            self._paths += [p for p in paths if p not in self._paths]
        else:
            self._paths = paths[:1]
        self._path = self._paths[-1]
        if self._multiple and len(self._paths) > 1:
            self._label.setText(f"✓ {len(self._paths)} ta fayl")
            self._hint.setText("Yana qo'shish uchun bosing yoki tashlang")
        else:
            self._label.setText(f"✓ {self._path.name}")
            self._hint.setText("Yana qo'shish uchun bosing yoki tashlang"
                               if self._multiple else "Almashtirish uchun bosing")
        self.setProperty("filled", True)
        self._restyle()
        self.changed.emit()

    def _restyle(self) -> None:
        self.style().unpolish(self)
        self.style().polish(self)

    # -- interactions ------------------------------------------------------
    def _dialog_filter(self) -> str:
        patterns = " ".join(f"*{e}" for e in sorted(self._exts))
        label = "Fayllar" if self._exts >= PDF_EXTS else "Images"
        return f"{label} ({patterns})"

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        allowed = self._dialog_filter()
        if self._multiple:
            chosen, _ = QFileDialog.getOpenFileNames(self, self._title, "", allowed)
            self._add([Path(p) for p in chosen])
            return
        path, _ = QFileDialog.getOpenFileName(self, self._title, "", allowed)
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
        dropped = self._images(event)
        self.setProperty("hover", False)
        self._restyle()
        if dropped:
            self._add(dropped if self._multiple else dropped[:1])
            event.acceptProposedAction()

    def _images(self, event) -> list[Path]:
        mime = event.mimeData()
        if not mime.hasUrls():
            return []
        out = []
        for url in mime.urls():
            p = Path(url.toLocalFile())
            if p.suffix.lower() in self._exts and p.exists():
                out.append(p)
        return out

    def _first_image(self, event) -> Path | None:
        found = self._images(event)
        return found[0] if found else None
