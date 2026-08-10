"""Arrange a mapping-driven form on one blank — Регистрация and ХОСТЕЛ.

Both print on the МВД «Уведомление о прибытии», both describe where their
values go in a shared ``mapping.vN.json``, and both let the office keep its own
addresses' blanks. So both arrange the same way, and both do it here.

The form runs to two pages, so the office is walked through them in order: the
first page's values, then the second's. What it moves on either is kept
together, against that blank.
"""

from __future__ import annotations

from pathlib import Path

import fitz
from PySide6.QtWidgets import QMessageBox

from src.common.logging import get_logger
from src.pdf.mapping import FieldMapping, anchor_x
from src.services import blank_layout
from src.ui.widgets.layout_editor import Item, LayoutEditor

log = get_logger(__name__)

#: A grid field prints one character to a box, so the sample has to be that
#: long or its width on screen is a lie.
_GRID_FILL = "ХХХХХХХХХХХХХХХХХХХХХХХХХХХХХХХХХХХХХХХХ"


def label_of(field) -> str:
    """«reg.birth.d» → «birth d» — readable without a table to maintain."""
    parts = field.id.split(".")
    return " ".join(parts[1:] or parts).replace("_", " ")


def sample_of(field) -> str:
    if field.type == "mark":
        return field.glyph or "V"
    if field.type == "grid":
        return _GRID_FILL[:max(1, int(field.max_cells or 6))]
    return label_of(field).upper()


def _arrange_richly(parent, *, section: str, template: Path,
                    mapping: FieldMapping, title: str,
                    labels: dict[str, str] | None) -> bool:
    """Every page at once, with the face, the weight, the colour and the rest.

    The pages are drawn at 150 dpi rather than the walk's own resolution: the
    office lines values up against printed rules here, and it can zoom.
    """
    from src.ui.widgets.mapping_arranger import arrange as arrange_fully

    try:
        with fitz.open(str(template)) as raw:
            doc = raw if raw.is_pdf else fitz.open("pdf", raw.convert_to_pdf())
            pages = [page.get_pixmap(dpi=150).tobytes("png") for page in doc]
    except Exception as exc:                          # noqa: BLE001
        QMessageBox.warning(parent, "Xato", f"Бланка очилмади: {exc}")
        return False

    made = arrange_fully(parent, pages=pages, mapping=mapping,
                         layout=blank_layout.load(section, template),
                         title=title, labels=labels)
    if made is None:
        return False
    blank_layout.save(section, template, made)
    log.info("%s: «%s» — %d майдон, %d ўз матни", section, Path(template).stem,
             len(made["fields"]), len(made["texts"]))
    return True


def arrange(parent, *, section: str, template: Path, mapping_path: Path,
            title: str, rich: bool = False,
            labels: dict[str, str] | None = None) -> bool:
    """Walk the office through this blank's pages. True when it saved.

    ``rich`` opens the FULL window instead — the one that also picks a face,
    sets a text bold, colours it, turns it, adds a text of the office's own
    and zooms in on a printed rule. It is opt-in so that a section already
    happy with the plain page-by-page walk is not changed under it.
    """
    template, mapping_path = Path(template), Path(mapping_path)
    if not template.exists():
        QMessageBox.warning(parent, "Diqqat", "Бланка топилмади.")
        return False
    try:
        mapping = FieldMapping.load(mapping_path)
    except Exception as exc:                          # noqa: BLE001
        QMessageBox.warning(parent, "Xato", f"Мапинг ўқилмади: {exc}")
        return False

    if rich:
        return _arrange_richly(parent, section=section, template=template,
                               mapping=mapping, title=title, labels=labels)

    kept = dict(blank_layout.load(section, template).get("fields") or {})
    width, height = mapping.page_size
    pages = sorted({int(f.page) for f in mapping.fields})

    try:
        document = fitz.open(str(template))
    except Exception as exc:                          # noqa: BLE001
        QMessageBox.warning(parent, "Xato", f"Бланка очилмади: {exc}")
        return False

    saved_any = False
    with document:
        for page_no in pages:
            if page_no > document.page_count:
                log.warning("%s: бланкада %d-саҳифа йўқ", section, page_no)
                continue
            page = document[page_no - 1]
            png = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5)).tobytes("png")
            items = []
            for field in mapping.fields:
                if int(field.page) != page_no:
                    continue
                spot = kept.get(field.id)
                if spot and len(spot) == 3:
                    x, y, size = (float(v) for v in spot)
                else:
                    x = anchor_x(field) / width
                    y = float(field.y or 0.0) / height
                    size = float(field.size) / height
                items.append(Item(key=field.id, label=label_of(field),
                                  sample=sample_of(field), x=x, baseline=y,
                                  size=size, font_family="Arial"))
            if not items:
                continue
            editor = LayoutEditor(
                png, items, title=f"{title} — {page_no}-саҳифа", parent=parent)
            if editor.exec() != editor.DialogCode.Accepted:
                return saved_any
            kept.update(editor.result().items)
            saved_any = True

    if saved_any:
        blank_layout.save(section, template, {"fields": kept})
    return saved_any
