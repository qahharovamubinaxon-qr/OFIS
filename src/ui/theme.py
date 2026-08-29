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
    "nav.ppu": "sage",             # регистрация оиласи
    "nav.snils": "house",          # оддий оқ варақ
    "nav.mig": "sage",             # ИШЧИ КАРТАСИ — регистрация оиласи
    "nav.strahovka": "blue",       # ОСАГО полиси
    "nav.dms": "red",              # ДМС
    "nav.svera": "violet",         # свера
    "nav.sertifikat": "rose",      # рус тили сертификати — малина гильош
    "nav.dover": "brass",          # нотариус — муҳр
    "nav.perevod": "brass",
    "nav.uzbspravka": "sage",      # ўзбек давлат портали — яшил муҳр
    "nav.kukpatent": "sage",       # картанинг ўзи яшил-кўк
    "nav.amina": "violet",         # телефондаги илова
    "nav.universal": "brass",      # ҳар хил бланка — нейтрал
}

#: The text colours each theme sets its own ink in, for the parts of the window
#: that are painted rather than styled — currently the brand mark. (ink, muted)
INKS: dict[str, tuple[str, str]] = {
    "dark": ("#E8E6E3", "#8E8B96"),
    "light": ("#1B1A18", "#6E6A62"),
}

#: The section's colour on the night ground. Vivid mid-tones — a saturated
#: version of the paper the section prints on — so the RUN button, the nav
#: rail and the focus ring read as a confident, modern accent rather than a
#: washed-out pastel. The ink is near-black, which sits cleanly on every one
#: of these tones (the RUN button is coloured with dark text, like a printed
#: chip). Softer, brighter twin for hover.
DARK: dict[str, Stock] = {
    "pink": Stock("#E86A93", "#F07EA3", "#2A0C16"),
    "sage": Stock("#4FB185", "#61C296", "#06160E"),
    "blue": Stock("#559FD9", "#6DB0E5", "#071726"),
    "red": Stock("#E2685F", "#EE7C73", "#290C0A"),
    "violet": Stock("#9A85E2", "#AC98ED", "#150E2C"),
    "rose": Stock("#DC6BA9", "#E87FB8", "#2A0D1E"),
    "brass": Stock("#D2A54C", "#E0B563", "#241A06"),
    "house": Stock("#6198D6", "#79AAE2", "#0A1626"),
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
