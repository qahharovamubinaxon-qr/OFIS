"""Clear a view's inputs so the next document can be loaded without a restart.

Views may define their own ``reset()``; when they do not, :func:`reset_view`
clears every upload tile, free-text box and progress bar it can find on the
view. Pickers (company/address/firm) and dates are deliberately left alone —
the operator usually processes several workers for the same firm.
"""

from __future__ import annotations

from PySide6.QtWidgets import QListWidget, QPlainTextEdit, QTextEdit, QWidget


def reset_view(view: QWidget) -> bool:
    """Reset ``view``. Returns False when there was nothing resettable."""
    own = getattr(view, "reset", None)
    if callable(own):
        own()
        return True

    from src.ui.widgets.drop_zone import DropZone
    from src.ui.widgets.multi_drop import MultiDropZone
    from src.ui.widgets.run_progress import RunProgress

    touched = False
    for child in view.findChildren(QWidget):
        if isinstance(child, DropZone):
            child.clear()
            touched = True
        elif isinstance(child, MultiDropZone):
            child.clear_files()
            touched = True
        elif isinstance(child, (QTextEdit, QPlainTextEdit)):
            if not child.isReadOnly():
                child.clear()
                touched = True
        elif isinstance(child, QListWidget) and child.objectName() != "navList":
            if child.dragDropMode() == QListWidget.DragDropMode.InternalMove:
                child.clear()  # the JPG→PDF page list
                touched = True
        elif isinstance(child, RunProgress):
            child.hide()

    status = getattr(view, "_status", None)
    if status is not None and hasattr(status, "setText"):
        hint = getattr(view, "_hint", None)
        status.setText(hint() if callable(hint) else "")
        touched = True
    return touched
