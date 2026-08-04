"""МВД РЕГИСТРАЦИЯ — the office's own отрывная часть, filled and sent as PDF.

Passport in, the address picked, the two dates typed — the МВД form comes
out with the worker in its cells and the start date stamped in BLUE
(«10 АВГ 2026») in the confirmation box on the back. Everything else is the
office's own doing, in ONE window: every value moved, resized, recoloured,
set in any installed font; extra texts added by meaning; the signature
drawn with the mouse; the stamp uploaded.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.common.threading import run_async
from src.controllers.mvdreg_controller import MvdRegController
from src.domain.registration_address import RegistrationAddress
from src.services import mvdreg_service
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress

#: what the add-address dialog asks — the same things the РЕГИСТРАЦИЯ
#: section's addresses carry
_FIELDS = (
    ("label", "Қисқа ном (рўйхатда кўринади)"),
    ("internal_code", "Ички код (папка номи, лотинча)"),
    ("oblast", "Область / субъект РФ"),
    ("raion", "Район / поселение"),
    ("gorod", "Город / населённый пункт"),
    ("ulitsa", "Улица"),
    ("dom", "Дом"),
    ("korpus", "Корпус"),
    ("stroenie", "Строение / литера"),
    ("kvartira", "Квартира / помещение"),
    ("host_fio", "Қабул қилувчи ФИО (принимающая сторона)"),
    ("organization_name", "Ташкилот номи (бўлса)"),
    ("inn", "Ташкилот ИНН (бўлса)"),
    ("regional_number", "Уведомление № (бўлса)"),
)

#: how a mapping family reads in the font picker
_FACE_NAMES = {"OfisSerif": "Times New Roman", "OfisSerifBold": "Times New Roman",
               "OfisSans": "Calibri", "OfisSansRegular": "Calibri",
               "OfisArial": "Arial", "OfisArialBold": "Arial",
               "OfisMono": "Courier New"}


class AddMvdRegDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Янги адрес — МВД РЕГИСТРАЦИЯ")
        self.setMinimumWidth(600)
        self._template: Path | None = None

        outer = QVBoxLayout(self)
        form = QFormLayout()
        self._edits: dict[str, QLineEdit] = {}
        for key, label in _FIELDS:
            edit = QLineEdit()
            form.addRow(label, edit)
            self._edits[key] = edit
        outer.addLayout(form)

        pick = QHBoxLayout()
        self._tpl_label = QLabel("Тайёр шаблон танланмаган (ихтиёрий)")
        self._tpl_label.setStyleSheet("color:#8a94a3;")
        btn = QPushButton("Тайёр шаблон PDF…")
        btn.clicked.connect(self._pick_template)
        pick.addWidget(self._tpl_label, stretch=1)
        pick.addWidget(btn)
        outer.addLayout(pick)

        # печать ва имзо шу ернинг ўзида — адрес билан бирга сақланади
        self.stamp_path: Path | None = None
        self.sign_png: bytes | None = None
        assets = QHBoxLayout()
        self._asset_label = QLabel("Печать/имзо: кейин ҳам қўшса бўлади")
        self._asset_label.setStyleSheet("color:#8a94a3;")
        assets.addWidget(self._asset_label, stretch=1)
        stamp_btn = QPushButton("⚙ Печать танлаш…")
        stamp_btn.clicked.connect(self._pick_stamp)
        assets.addWidget(stamp_btn)
        sign_btn = QPushButton("✍ Имзо чизиш…")
        sign_btn.clicked.connect(self._draw_sign)
        assets.addWidget(sign_btn)
        outer.addLayout(assets)

        from PySide6.QtWidgets import QDialogButtonBox

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _pick_template(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Тайёр шаблон PDF", "",
                                              "PDF (*.pdf)")
        if path:
            self._template = Path(path)
            self._tpl_label.setText(f"✓ {Path(path).name}")

    def _pick_stamp(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Печать расми", "", "Расм (*.png *.jpg *.jpeg)")
        if path:
            self.stamp_path = Path(path)
            self._show_assets()

    def _draw_sign(self) -> None:
        from src.services.mvdreg_service import SIGN_INK
        from src.ui.widgets.signature_pad import SignaturePad

        pad = SignaturePad(self)
        pad.set_ink(tuple(int(c * 255) for c in SIGN_INK))
        if pad.exec() == QDialog.DialogCode.Accepted:
            self.sign_png = pad.signature_png()
            self._show_assets()

    def _show_assets(self) -> None:
        parts = []
        if self.stamp_path is not None:
            parts.append(f"печать ✓ {self.stamp_path.name}")
        if self.sign_png:
            parts.append("имзо ✓")
        self._asset_label.setText(
            " · ".join(parts) or "Печать/имзо: кейин ҳам қўшса бўлади")

    def build(self) -> tuple[RegistrationAddress, Path | None]:
        v = {k: e.text().strip() for k, e in self._edits.items()}
        summary = ", ".join(x for x in (
            v["oblast"], v["raion"], v["gorod"], v["ulitsa"],
            f"д. {v['dom']}" if v["dom"] else "",
            f"к. {v['korpus']}" if v["korpus"] else "",
            f"стр. {v['stroenie']}" if v["stroenie"] else "",
            f"кв. {v['kvartira']}" if v["kvartira"] else "") if x)
        label = v["label"] or summary or "Адрес"
        slug = "".join(c.lower() if c.isalnum() else "-" for c in label)
        slug = "-".join(p for p in slug.split("-") if p)[:40]
        address = RegistrationAddress(
            label=label,
            internal_code=v["internal_code"] or slug or "adres",
            address_text=summary or "-", host_fio=v["host_fio"] or "-",
            kind="mvdreg",
            oblast=v["oblast"] or None, raion=v["raion"] or None,
            gorod=v["gorod"] or None, ulitsa=v["ulitsa"] or None,
            dom=v["dom"] or None, korpus=v["korpus"] or None,
            stroenie=v["stroenie"] or None, kvartira=v["kvartira"] or None,
            organization_name=v["organization_name"] or None,
            inn=v["inn"] or None,
            regional_number=v["regional_number"] or None,
            template_path=self._template or Path("missing.pdf"))
        return address, self._template


class MvdRegView(QWidget):
    def __init__(self, controller: MvdRegController) -> None:
        super().__init__()
        self._c = controller

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

        title = QLabel("МВД РЕГИСТРАЦИЯ — рўйхатга қўйиш бланкаси")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        addr_row = QHBoxLayout()
        addr_row.addWidget(QLabel("Адрес:"))
        self._address = QComboBox()
        self._address.currentIndexChanged.connect(
            lambda _: self._refresh_state())
        addr_row.addWidget(self._address, stretch=1)
        add = QPushButton("➕ Адрес")
        add.clicked.connect(self._add)
        addr_row.addWidget(add)
        drop = QPushButton("🗑")
        drop.clicked.connect(self._remove)
        addr_row.addWidget(drop)
        root.addLayout(addr_row)

        tool_row = QHBoxLayout()
        blank = QPushButton("📄 Бланка юклаш")
        blank.setToolTip("Ўз бўш бланкангиз — янги адреслар шунга қурилади")
        blank.clicked.connect(self._set_blank)
        tool_row.addWidget(blank)
        sign = QPushButton("✍ Имзо")
        sign.setToolTip("Сичқонча билан имзо чизиш — бланкага босилади")
        sign.clicked.connect(self._draw_sign)
        tool_row.addWidget(sign)
        stamp = QPushButton("⚙ Печать юклаш")
        stamp.setToolTip("Оқ фони ўзи шаффоф бўлади")
        stamp.clicked.connect(self._set_stamp)
        tool_row.addWidget(stamp)
        wipe = QPushButton("🗑 Имзо/Печать")
        wipe.clicked.connect(self._clear_assets)
        tool_row.addWidget(wipe)
        arrange = QPushButton("📐 Созлаш — ҳамма нарса шу ойнада")
        arrange.setToolTip("Матн қўшиш, суриш, катта-кичик, ранг, шрифт, "
                           "имзо ва печать жойлари")
        arrange.clicked.connect(self._arrange)
        tool_row.addWidget(arrange)
        tool_row.addStretch(1)
        root.addLayout(tool_row)

        self._state = QLabel("")
        self._state.setWordWrap(True)
        self._state.setStyleSheet("color:#8a94a3;")
        root.addWidget(self._state)

        docs = QHBoxLayout()
        self._passport = DropZone("🛂", "Паспорт")
        docs.addWidget(self._passport)
        self._front = DropZone("🩷", "Патент олди (ихтиёрий)")
        docs.addWidget(self._front)
        root.addLayout(docs)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        root.addLayout(grid)
        grid.addWidget(QLabel("Бошланиш санаси (кўк штамп):"), 0, 0)
        self._start = QDateEdit(QDate.currentDate())
        self._start.setCalendarPopup(True)
        self._start.setDisplayFormat("dd.MM.yyyy")
        grid.addWidget(self._start, 0, 1)
        grid.addWidget(QLabel("Тугаш санаси:"), 0, 2)
        self._expiry = QDateEdit(QDate.currentDate().addDays(90))
        self._expiry.setCalendarPopup(True)
        self._expiry.setDisplayFormat("dd.MM.yyyy")
        grid.addWidget(self._expiry, 0, 3)

        run_row = QHBoxLayout()
        self._run = QPushButton("🖨 Тайёрлаш")
        self._run.setObjectName("primaryButton")
        self._run.clicked.connect(self._generate)
        run_row.addWidget(self._run)
        open_out = QPushButton("📂 Папкани очиш")
        open_out.clicked.connect(self._open_folder)
        run_row.addWidget(open_out)
        run_row.addStretch(1)
        root.addLayout(run_row)

        self._progress = RunProgress(self)
        self._status = QLabel("")
        self._status.setWordWrap(True)
        root.addWidget(self._status)
        root.addStretch(1)
        self._reload()

    # ------------------------------------------------------------- state
    def _reload(self) -> None:
        current = self._address.currentData()
        self._address.blockSignals(True)
        self._address.clear()
        for address in self._c.addresses():
            self._address.addItem(address.label, str(address.id))
        if self._address.count() == 0:
            self._address.addItem("— адрес йўқ, «➕ Адрес» —", None)
        elif current:
            index = self._address.findData(current)
            if index >= 0:
                self._address.setCurrentIndex(index)
        self._address.blockSignals(False)
        self._refresh_state()

    def _refresh_state(self) -> None:
        chosen = self._selected()
        template = chosen.template_path if chosen else None
        parts = [f"Бланка: {self._c.blank().name}"]
        parts.append("Имзо: бор ✅" if self._c.asset("sign", template)
                     else "Имзо: йўқ")
        parts.append("Печать: бор ✅" if self._c.asset("stamp", template)
                     else "Печать: йўқ")
        if chosen:
            parts.append(f"(«{chosen.label}» учун)")
        self._state.setText(" · ".join(parts))

    def _selected(self) -> RegistrationAddress | None:
        chosen = self._address.currentData()
        if not chosen:
            return None
        for address in self._c.addresses():
            if str(address.id) == chosen:
                return address
        return None

    # ----------------------------------------------------------- address
    def _add(self) -> None:
        dialog = AddMvdRegDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            address, template = dialog.build()
            made = self._c.add_address(address, template)
            if dialog.stamp_path is not None:
                self._c.set_stamp(dialog.stamp_path, made.template_path)
            if dialog.sign_png:
                self._c.set_signature(dialog.sign_png, made.template_path)
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._reload()
        index = self._address.findData(str(made.id))
        if index >= 0:
            self._address.setCurrentIndex(index)
        self._status.setText(f"✅ «{made.label}» қўшилди — жойларини "
                             "текшириб чиқинг.")
        # straight into the one window: печать, имзо ва матнлар шу ерда
        # жойлаштирилади ва ФАҚАТ шу адрес учун сақланади
        self._arrange()

    def _remove(self) -> None:
        address = self._selected()
        if address is None:
            return
        if QMessageBox.question(self, "Ўчириш",
                                f"«{address.label}» олиб ташлансинми?") \
                != QMessageBox.StandardButton.Yes:
            return
        self._c.archive_address(address.id)
        self._reload()

    # ------------------------------------------------------------ assets
    def _set_blank(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Бўш бланка PDF", "",
                                              "PDF (*.pdf)")
        if not path:
            return
        try:
            self._c.set_blank(Path(path))
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._reload()
        self._status.setText("✅ Бланка сақланди — энди қўшиладиган адреслар "
                             "шу бланкага қурилади.")

    def _draw_sign(self) -> None:
        from src.services.mvdreg_service import SIGN_INK
        from src.ui.widgets.signature_pad import SignaturePad

        pad = SignaturePad(self)
        pad.set_ink(tuple(int(c * 255) for c in SIGN_INK))
        if pad.exec() != QDialog.DialogCode.Accepted:
            return
        png = pad.signature_png()
        if png:
            chosen = self._selected()
            self._c.set_signature(
                png, chosen.template_path if chosen else None)
            self._reload()
            self._status.setText(
                f"✅ Имзо {'«' + chosen.label + '» учун ' if chosen else ''}"
                "сақланди — жойини «📐» да суринг.")

    def _set_stamp(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Печать расми", "", "Расм (*.png *.jpg *.jpeg)")
        if not path:
            return
        chosen = self._selected()
        try:
            self._c.set_stamp(Path(path),
                              chosen.template_path if chosen else None)
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._reload()
        self._status.setText(
            f"✅ Печать {'«' + chosen.label + '» учун ' if chosen else ''}"
            "сақланди — жойини «📐» да суринг.")

    def _clear_assets(self) -> None:
        picked, ok = QInputDialog.getItem(
            self, "Ўчириш", "Нимани ўчирамиз?", ["Имзо", "Печать"], 0, False)
        if not ok:
            return
        chosen = self._selected()
        self._c.clear_asset("sign" if picked == "Имзо" else "stamp",
                            chosen.template_path if chosen else None)
        self._reload()

    # ----------------------------------------------------------- arrange
    def _arrange(self) -> None:
        """One window: the form's values, the office's texts, the pictures."""
        address = self._selected()
        if address is None:
            self._warn("Аввал адресни танланг ёки қўшинг.")
            return
        import fitz

        from src.pdf.mapping import FieldMapping, anchor_x
        from src.pdf.trud8_fields import Field
        from src.ui.widgets.arrange_mapping import label_of, sample_of
        from src.ui.widgets.field_editor import FieldEditor

        template = address.template_path
        try:
            pages = []
            with fitz.open(str(template)) as doc:
                for page in doc:
                    pages.append(page.get_pixmap(dpi=100).tobytes("png"))
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        layout = mvdreg_service.load_layout(template)
        moved = layout.get("fields") or {}
        styles = layout.get("styles") or {}
        images = layout.get("images") or {}

        import fitz as _fitz

        from src.pdf.engine import _font_file

        fields: list[Field] = []
        opened: dict[str, tuple[float, float, float]] = {}
        catalogue = dict(mvdreg_service.CATALOGUE)
        samples = dict(mvdreg_service.SAMPLES)
        frozen: set[str] = set()
        pitches: dict[str, float] = {}
        #: tag → half the gap between the box's width and the printed
        #: text's, as a share of the page — a centred value (the blue date)
        #: is SHOWN where its letters really start, and the anchor is put
        #: back on save, so the screen and the print are the same place
        centre_shift: dict[str, float] = {}
        # the worker's values AND the address's own texts — the owner asked
        # to be able to drag the address, the host's name and the dates too
        for source in (mvdreg_service.mapping_path(),
                       mvdreg_service.bundled_dir() / "address_mapping.v1.json"):
            mapping = FieldMapping.load(source)
            width, height = mapping.page_size
            for item in mapping.fields:
                tag = f"map:{item.id}"
                frozen.add(tag)
                catalogue[tag] = label_of(item)
                sample = sample_of(item)
                samples[tag] = sample
                if item.type == "grid" and item.pitch:
                    pitches[tag] = float(item.pitch) / width
                elif (item.type == "text" and item.width
                      and item.align == "center"):
                    try:
                        face = _fitz.Font(fontfile=str(_font_file(item.font)))
                        text_w = face.text_length(sample,
                                                  fontsize=float(item.size))
                    except Exception:             # noqa: BLE001
                        text_w = 0.0
                    centre_shift[tag] = (float(item.width) - text_w) \
                        / 2.0 / width
                spot = moved.get(item.id)
                if spot and len(spot) == 3:
                    x, baseline, size = (float(v) for v in spot)
                else:
                    x = anchor_x(item) / width
                    baseline = float(item.y or 0.0) / height
                    size = float(item.size) / height
                opened[item.id] = (round(x, 5), round(baseline, 5),
                                   round(size, 5))
                chosen = styles.get(item.id) or {}
                colour = tuple(chosen.get("colour")
                               or (item.model_extra or {}).get("colour")
                               or (0.0, 0.0, 0.0))[:3]
                fields.append(Field(
                    key=tag, page=int(item.page),
                    x=x + centre_shift.get(tag, 0.0), baseline=baseline,
                    size=size, colour=colour,
                    font=chosen.get("font")
                    or _FACE_NAMES.get(item.font, "Times New Roman")))
        for extra in layout.get("extra") or []:
            fields.append(Field.from_dict(extra))
        for key in mvdreg_service.IMG_KEYS:
            if self._c.asset(key.removeprefix("img_"), template) is None:
                continue
            frozen.add(key)
            catalogue[key] = mvdreg_service.IMG_LABELS[key]
            samples[key] = mvdreg_service.IMG_LABELS[key]
            page, x, bottom, h = images.get(key) \
                or mvdreg_service.IMG_DEFAULTS[key]
            fields.append(Field(key=key, page=int(page), x=float(x),
                                baseline=float(bottom), size=float(h)))
        # the real pictures — the office drags ITS печать and ITS имзо,
        # at their true size, not a word standing in for them
        pictures = {}
        for key in mvdreg_service.IMG_KEYS:
            found = self._c.asset(key.removeprefix("img_"), template)
            if found is not None:
                pictures[key] = found.read_bytes()

        dialog = FieldEditor(pages, fields, title=f"{address.label}",
                             parent=self, catalogue=catalogue,
                             samples=samples, frozen=frozen,
                             images=pictures, pitches=pitches)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        new_fields: dict[str, list[float]] = {}
        new_styles: dict[str, dict] = {}
        new_extra: list[dict] = []
        new_images: dict[str, list[float]] = {}
        for made in dialog.fields():
            if made.key.startswith("map:"):
                name = made.key[4:]
                spot = [round(made.x - centre_shift.get(made.key, 0.0), 5),
                        round(made.baseline, 5), round(made.size, 5)]
                # only what the office actually MOVED is written down; a
                # value left where the program put it keeps following the
                # program — so a corrected map is never pinned to an old spot
                if tuple(spot) != opened.get(name):
                    new_fields[name] = spot
                new_styles[name] = {"font": made.font,
                                    "colour": list(made.colour)}
            elif made.key in mvdreg_service.IMG_KEYS:
                new_images[made.key] = [made.page, round(made.x, 5),
                                        round(made.baseline, 5),
                                        round(made.size, 5)]
            else:
                new_extra.append(made.as_dict())
        mvdreg_service.save_layout(template,
                          {"v": mvdreg_service.LAYOUT_V, "fields": new_fields,
                           "styles": new_styles, "extra": new_extra,
                           "images": new_images})
        # the address's own texts are printed INTO the template when it is
        # built, so a moved address/host/дата needs the template rebuilt
        if any(name.startswith("host.") for name in new_fields):
            try:
                mvdreg_service.MvdRegTemplateBuilder().build(template, address)
            except Exception as error:            # noqa: BLE001
                self._failed(error)
                return
        self._status.setText("✅ Ҳамма жой ва созламалар сақланди.")

    # ---------------------------------------------------------- printing
    def _generate(self) -> None:
        address = self._selected()
        if address is None:
            self._warn("Аввал адресни танланг.")
            return
        if self._passport.path is None:
            self._warn("Паспорт расмини ташланг.")
            return
        if not self._c.ai_available():
            self._warn("AI калити йўқ — Sozlamalar бўлимига калит киритинг.")
            return
        passport = Path(self._passport.path).read_bytes()
        front = (Path(self._front.path).read_bytes()
                 if self._front.path is not None else None)
        start = self._start.date().toPython()
        expiry = self._expiry.date().toPython()

        self._run.setEnabled(False)
        self._progress.start("Паспорт ўқилиб, бланка тўлдириляпти…")

        def work():
            return self._c.generate_from_images(
                address, passport, front,
                registration_expiry=expiry, registration_start=start)

        run_async(work, on_success=self._done, on_error=self._failed)

    def _done(self, result) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        self._status.setText(f"✅ Тайёр: {result.pdf_path}")

    def _failed(self, error: Exception) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        message = getattr(error, "message", None) or str(error)
        self._status.setText(f"❌ {message}")

    def _open_folder(self) -> None:
        from src.config import paths
        from src.ui.views.settings_view import _open_folder

        folder = paths.output_dir() / "mvdreg"
        folder.mkdir(parents=True, exist_ok=True)
        _open_folder(folder)

    def _warn(self, message: str) -> None:
        self._status.setText(f"⚠️ {message}")

    def reset(self) -> None:
        pass
