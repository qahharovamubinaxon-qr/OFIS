"""Applies a Qt stylesheet (light/dark) to the running app at runtime.

Themes are plain ``.qss`` files in ``resources/qss`` so designers can tweak them
without touching Python. Switching is instant — no restart.

**The colour on screen is the colour of the paper.** This program prints
migration documents, and each of them comes on its own stock: the патент card
is pink, the разрешение sage, the ОСАГО policy blue, the ДМС red. So the
section you are working in colours the three places that say *where you are* —
the rail beside it in the sidebar, the hairline under the screen's title, and
the RUN button — and nothing else on screen is coloured at all. The operator
learns the program the way they know their own stack of blanks.

The stylesheets carry ``@ACCENT@`` where that colour goes; this module fills it
in and re-applies the sheet whenever the section changes. Re-applying costs
milliseconds and cannot half-happen, which a per-widget property dance can.
"""

from __future__ import annotations

from typing import NamedTuple

from PySide6.QtWidgets import QApplication

from src.common.logging import get_logger
from src.config import constants, paths

log = get_logger(__name__)


class Stock(NamedTuple):
    """A paper: its colour, the colour it lightens to, and what reads on it."""

    base: str
    soft: str
    ink: str


#: Which paper each section prints on. Sections that print no card of their
#: own — the dashboard, the archive, settings, the МВД paperwork — take
#: ``house``, the ink those forms are set in.
PAPER: dict[str, str] = {
    "nav.patent": "pink",          # пушти патент картаси
    "nav.beydjik": "pink",         # ўша бланка
    "nav.chek": "pink",            # патентнинг чеки — ўша дастада юради
    "nav.razreshenie": "sage",     # яшил разрешение
    "nav.strahovka": "blue",       # ОСАГО полиси
    "nav.dms": "red",              # ДМС
    "nav.svera": "violet",         # свера
    "nav.sertifikat": "rose",      # рус тили сертификати — малина гильош
    "nav.dover": "brass",          # нотариус — муҳр
    "nav.perevod": "brass",
}

#: The text colours each theme sets its own ink in, for the parts of the window
#: that are painted rather than styled — currently the brand mark. (ink, muted)
INKS: dict[str, tuple[str, str]] = {
    "dark": ("#E8E6E3", "#8E8B96"),
    "light": ("#1B1A18", "#6E6A62"),
}

#: On ink, the card's own pastel: this is the colour of the blank itself, and
#: on a dark ground it reads the way ink reads on a plate.
DARK: dict[str, Stock] = {
    "pink": Stock("#E9A7BF", "#F2B9CD", "#2A1720"),
    "sage": Stock("#A9CBB7", "#BADCC7", "#16261D"),
    "blue": Stock("#9DC0E0", "#AFD0EC", "#10202E"),
    "red": Stock("#E3A6A2", "#EEB7B3", "#2A1513"),
    "violet": Stock("#BDB2DE", "#CEC4EA", "#1D1830"),
    "rose": Stock("#DFA3C4", "#EBB5D2", "#2B1523"),
    "brass": Stock("#DCC38A", "#E9D3A0", "#2A2212"),
    "house": Stock("#A8BEDC", "#BACEE9", "#121A26"),
}

#: On paper, the same document's *ink* rather than its stock — a pastel on
#: cream would be a smudge, and the eye is looking for the printed line.
LIGHT: dict[str, Stock] = {
    "pink": Stock("#A8446B", "#BC5480", "#FFFFFF"),
    "sage": Stock("#3F7D5F", "#4C9070", "#FFFFFF"),
    "blue": Stock("#2E6494", "#3B76AA", "#FFFFFF"),
    "red": Stock("#A4423D", "#B8514C", "#FFFFFF"),
    "violet": Stock("#5F4F94", "#6F5EA8", "#FFFFFF"),
    "rose": Stock("#9B2D68", "#B03B7A", "#FFFFFF"),
    "brass": Stock("#7A6028", "#8D7133", "#FFFFFF"),
    "house": Stock("#2F5580", "#3D6693", "#FFFFFF"),
}


def stock_for(nav_key: str, theme: str = "dark") -> Stock:
    """The colour this section is written in, for this theme."""
    table = LIGHT if theme == "light" else DARK
    return table[PAPER.get(nav_key, "house")]


def apply_theme(app: QApplication, theme: str, nav_key: str = "") -> None:
    """Paint the app in ``theme``, in the colour of ``nav_key``'s document."""
    name = theme if theme in constants.SUPPORTED_THEMES else constants.DEFAULT_THEME
    qss_path = paths.resources_dir() / "qss" / f"{name}.qss"
    if not qss_path.exists():
        log.warning("Theme file missing: %s", qss_path)
        return
    stock = stock_for(nav_key, name)
    sheet = (qss_path.read_text(encoding="utf-8")
             .replace("@ACCENT_SOFT@", stock.soft)
             .replace("@ACCENT_INK@", stock.ink)
             .replace("@ACCENT@", stock.base))
    app.setStyleSheet(sheet)
    log.info("Applied theme: %s (%s → %s)", name,
             PAPER.get(nav_key, "house"), stock.base)
