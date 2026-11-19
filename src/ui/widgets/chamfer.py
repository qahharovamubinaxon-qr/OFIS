"""The cut corner — the one shape the HUD surfaces are built from.

Two opposite corners of every panel are cut off at 45°. It is a single line of
geometry, but it is what makes a surface read as an instrument panel rather
than a web page, and it is the one thing a Qt stylesheet cannot express
(``border-radius`` rounds; nothing chamfers). So the shape lives here, in one
place, and every surface that wants it paints through this path.

The cut is always on the top-left and bottom-right corners — the same two,
every time. A shape that flips its cut from panel to panel stops being a
language and becomes decoration.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QPainterPath

#: How deep the cut is on an ordinary panel, in device-independent pixels.
CUT = 13.0
#: …and on something small — a chip, an input, a toolbar button.
CUT_SMALL = 8.0


def chamfer_path(rect: QRectF, cut: float = CUT) -> QPainterPath:
    """The outline of ``rect`` with its top-left and bottom-right cut off.

    A cut deeper than half the shorter side would make the two cuts meet and
    the panel collapse into a lozenge, so it is held below that.
    """
    limit = min(rect.width(), rect.height()) / 2.0
    cut = max(0.0, min(float(cut), limit))

    path = QPainterPath()
    path.moveTo(rect.left() + cut, rect.top())
    path.lineTo(rect.right(), rect.top())
    path.lineTo(rect.right(), rect.bottom() - cut)
    path.lineTo(rect.right() - cut, rect.bottom())
    path.lineTo(rect.left(), rect.bottom())
    path.lineTo(rect.left(), rect.top() + cut)
    path.closeSubpath()
    return path
