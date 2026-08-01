"""IMGBB — расм ташла, ҳавола ол; иккинчи майдонда ҳавола QR бўлади.

Both fields take any number of pictures dragged in with the cursor (or
picked with a click). Every picture goes up to the owner's imgbb account
public, and only the DIRECT https://i.ibb.co/… link is taken — the first
field hands the link itself back, the second folds it into a QR code with
copy and download buttons.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.common.threading import run_async
from src.controllers.imgbb_controller import ImgbbController

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


class _DropArea(QLabel):
    """Takes any number of pictures dragged in — or a click to browse."""

    dropped = Signal(list)

    def __init__(self, hint: str) -> None:
        super().__init__(hint)
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setMinimumHeight(88)
        self.setStyleSheet(
            "QLabel {border: 2px dashed #8a93a6; border-radius: 10px;"
            " padding: 12px; color: #6a7386;}")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt override
        files = [Path(u.toLocalFile()) for u in event.mimeData().urls()]
        files = [f for f in files
                 if f.suffix.lower() in _IMAGE_SUFFIXES and f.exists()]
        if files:
            self.dropped.emit(files)

    def mousePressEvent(self, _event) -> None:  # noqa: N802 - Qt override
        names, _ = QFileDialog.getOpenFileNames(
            self, "Расмларни танланг", "",
            "Расм (*.jpg *.jpeg *.png *.webp *.bmp *.gif)")
        if names:
            self.dropped.emit([Path(n) for n in names])


class ImgbbView(QWidget):
    def __init__(self, controller: ImgbbController) -> None:
        super().__init__()
        self._c = controller
        self._qr_by_row: dict[int, tuple[str, bytes]] = {}
        self._busy = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        root = QVBoxLayout(body)
        root.setContentsMargins(28, 24, 28, 16)
        root.setSpacing(12)

        title = QLabel("IMGBB — расм → ҳавола ва QR код")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        # -- 1: pictures to links --------------------------------------
        links_box = QGroupBox("1-майдон: расм → прямой ҳавола (i.ibb.co)")
        links_lay = QVBoxLayout(links_box)
        drop1 = _DropArea("Расмларни шу ерга ташланг (ёки босиб танланг) —\n"
                          "ҳар бирига ҳавола чиқади")
        drop1.dropped.connect(self._to_links)
        links_lay.addWidget(drop1)
        self._links = QListWidget()
        self._links.setMinimumHeight(110)
        links_lay.addWidget(self._links)
        row1 = QHBoxLayout()
        copy_one = QPushButton("📋 Ҳаволани нусхалаш")
        copy_one.clicked.connect(self._copy_link)
        row1.addWidget(copy_one)
        copy_all = QPushButton("📋 Ҳаммасини нусхалаш")
        copy_all.clicked.connect(self._copy_all_links)
        row1.addWidget(copy_all)
        row1.addStretch(1)
        links_lay.addLayout(row1)
        root.addWidget(links_box)

        # -- 2: pictures to QR codes -----------------------------------
        qr_box = QGroupBox("2-майдон: расм → QR код (ҳаволадан)")
        qr_lay = QVBoxLayout(qr_box)
        drop2 = _DropArea("Расмларни шу ерга ташланг — ҳаволаси QR бўлади")
        drop2.dropped.connect(self._to_qr)
        qr_lay.addWidget(drop2)
        mid = QHBoxLayout()
        self._qr_list = QListWidget()
        self._qr_list.setMinimumHeight(150)
        self._qr_list.currentRowChanged.connect(self._show_qr)
        mid.addWidget(self._qr_list, stretch=1)
        self._qr_preview = QLabel("QR шу ерда кўринади")
        self._qr_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._qr_preview.setMinimumSize(180, 180)
        mid.addWidget(self._qr_preview)
        qr_lay.addLayout(mid)
        row2 = QHBoxLayout()
        copy_qr = QPushButton("📋 QR ни нусхалаш")
        copy_qr.clicked.connect(self._copy_qr)
        row2.addWidget(copy_qr)
        save_qr = QPushButton("💾 QR ни скачать қилиш")
        save_qr.clicked.connect(self._save_qr)
        row2.addWidget(save_qr)
        row2.addStretch(1)
        qr_lay.addLayout(row2)
        root.addWidget(qr_box)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        root.addWidget(self._status)
        root.addStretch(1)

    # ------------------------------------------------------------ uploads
    def _ready(self) -> bool:
        if not self._c.key():
            self._status.setText(
                "⚠️ imgbb API калити йўқ — Sozlamalar'даги «🔳 КРКОД РЕГ — "
                "imgbb» картасига калитни киритинг.")
            return False
        return True

    def _to_links(self, files: list[Path]) -> None:
        if not self._ready():
            return
        for file in files:
            data = file.read_bytes()
            self._begin(f"«{file.name}» юкланаяпти…")
            run_async(
                lambda d=data, n=file.stem: self._c.upload(d, name=n),
                on_success=lambda link, f=file: self._link_done(f, link),
                on_error=self._failed)

    def _link_done(self, file: Path, link: str) -> None:
        self._links.addItem(link)
        self._links.setCurrentRow(self._links.count() - 1)
        QApplication.clipboard().setText(link)
        self._end(f"✅ {file.name} → {link} (ҳавола нусхаланди)")

    def _to_qr(self, files: list[Path]) -> None:
        if not self._ready():
            return
        for file in files:
            data = file.read_bytes()

            def work(d=data, n=file.stem):
                link = self._c.upload(d, name=n)
                return link, self._c.qr(link)

            self._begin(f"«{file.name}» юкланаяпти…")
            run_async(work,
                      on_success=lambda got, f=file: self._qr_done(f, got),
                      on_error=self._failed)

    def _qr_done(self, file: Path, got: tuple[str, bytes]) -> None:
        link, qr = got
        row = self._qr_list.count()
        self._qr_by_row[row] = (link, qr)
        self._qr_list.addItem(QListWidgetItem(f"{file.name} → {link}"))
        self._qr_list.setCurrentRow(row)
        self._end(f"✅ {file.name} → QR тайёр")

    # ------------------------------------------------------------ buttons
    def _copy_link(self) -> None:
        item = self._links.currentItem() or (
            self._links.item(self._links.count() - 1)
            if self._links.count() else None)
        if item is None:
            self._status.setText("⚠️ Ҳали ҳавола йўқ.")
            return
        QApplication.clipboard().setText(item.text())
        self._status.setText(f"📋 Нусхаланди: {item.text()}")

    def _copy_all_links(self) -> None:
        links = [self._links.item(i).text() for i in range(self._links.count())]
        if not links:
            self._status.setText("⚠️ Ҳали ҳавола йўқ.")
            return
        QApplication.clipboard().setText("\n".join(links))
        self._status.setText(f"📋 {len(links)} та ҳавола нусхаланди.")

    def _current_qr(self) -> tuple[str, bytes] | None:
        row = self._qr_list.currentRow()
        if row < 0 and self._qr_list.count():
            row = self._qr_list.count() - 1
        return self._qr_by_row.get(row)

    def _show_qr(self, row: int) -> None:
        got = self._qr_by_row.get(row)
        if got:
            image = QImage.fromData(got[1], "PNG")
            self._qr_preview.setPixmap(QPixmap.fromImage(image).scaled(
                200, 200, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))

    def _copy_qr(self) -> None:
        got = self._current_qr()
        if got is None:
            self._status.setText("⚠️ Ҳали QR йўқ.")
            return
        QApplication.clipboard().setImage(QImage.fromData(got[1], "PNG"))
        self._status.setText("📋 QR нусхаланди — истаган жойга қўйинг.")

    def _save_qr(self) -> None:
        got = self._current_qr()
        if got is None:
            self._status.setText("⚠️ Ҳали QR йўқ.")
            return
        target, _ = QFileDialog.getSaveFileName(
            self, "QR ни сақлаш", "qr.png", "PNG (*.png)")
        if not target:
            return
        Path(target).write_bytes(got[1])
        self._status.setText(f"💾 Сақланди: {target}")

    # ------------------------------------------------------------- state
    def _begin(self, message: str) -> None:
        self._busy += 1
        self._status.setText(f"⏳ {message}")

    def _end(self, message: str) -> None:
        self._busy = max(0, self._busy - 1)
        self._status.setText(message)

    def _failed(self, error: Exception) -> None:
        self._busy = max(0, self._busy - 1)
        message = getattr(error, "message", None) or str(error)
        self._status.setText(f"❌ {message}")

    def reset(self) -> None:
        pass
