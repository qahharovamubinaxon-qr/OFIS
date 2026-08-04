"""The fonts THIS computer has, by the names a person knows them by.

The office chooses a face for each text it places — «Arial», «Times New
Roman», whatever else is installed — so the program has to know two things
about every font on the machine: what it is called, and which file holds
its regular and its bold. Windows keeps neither in the file name (``ARIALBD
.TTF`` is «Arial / Bold», ``timesbd.ttf`` is «Times New Roman / Bold»), so
the name is read out of the font's own name table, the way every text
program does it.

Nothing here depends on Qt: the bot prints the same papers with no window
open, and it must resolve exactly the same face as the desktop.
"""

from __future__ import annotations

import os
import struct
from functools import lru_cache
from pathlib import Path

from src.common.logging import get_logger
from src.pdf.engine import _font_file

log = get_logger(__name__)

#: What the office gets when it has picked nothing — Times, as the forms use.
DEFAULT_FAMILY = "Times New Roman"

_SUFFIXES = (".ttf", ".ttc", ".otf")
#: nameID 1 is the family, nameID 2 the style («Regular», «Bold», «Italic»).
_FAMILY, _SUBFAMILY = 1, 2


def _font_dirs() -> list[Path]:
    found = []
    windir = os.environ.get("WINDIR")
    if windir:
        found.append(Path(windir) / "Fonts")
    local = os.environ.get("LOCALAPPDATA")
    if local:
        found.append(Path(local) / "Microsoft" / "Windows" / "Fonts")
    if os.name != "nt":                       # so the tests run anywhere
        found += [Path("/usr/share/fonts"), Path.home() / ".fonts"]
    return [p for p in found if p.is_dir()]


def _names_at(data: bytes, start: int) -> tuple[str, str]:
    """One sfnt font's family and style, out of its own name table."""
    if start + 12 > len(data):
        return "", ""
    tables = struct.unpack_from(">H", data, start + 4)[0]
    table = None
    for i in range(tables):
        head = start + 12 + i * 16
        if head + 16 > len(data):
            break
        tag, _, offset, _ = struct.unpack_from(">4sIII", data, head)
        if tag == b"name":
            table = offset
            break
    if table is None or table + 6 > len(data):
        return "", ""
    count, strings = struct.unpack_from(">HH", data, table + 2)
    best: dict[int, tuple[int, str]] = {}
    for i in range(count):
        head = table + 6 + i * 12
        if head + 12 > len(data):
            break
        platform, encoding, language, name_id, length, offset = \
            struct.unpack_from(">6H", data, head)
        if name_id not in (_FAMILY, _SUBFAMILY):
            continue
        at = table + strings + offset
        raw = data[at:at + length]
        if not raw:
            continue
        try:
            if platform == 3:                 # Windows, UTF-16BE
                text = raw.decode("utf-16-be", "ignore")
            elif platform == 1:               # Macintosh, Roman
                text = raw.decode("mac-roman", "ignore")
            else:
                continue
        except (UnicodeDecodeError, LookupError):
            continue
        text = text.strip("\x00 ").strip()
        if not text:
            continue
        # English (US) on Windows wins; anything readable beats nothing
        rank = 2 if (platform == 3 and language == 0x409) else 1
        if rank >= best.get(name_id, (0, ""))[0]:
            best[name_id] = (rank, text)
    return best.get(_FAMILY, (0, ""))[1], best.get(_SUBFAMILY, (0, ""))[1]


def _fonts_in(path: Path) -> list[tuple[str, str]]:
    """Every face a file holds — a .ttc collection holds several."""
    try:
        data = path.read_bytes()
    except OSError:
        return []
    if data[:4] == b"ttcf":
        if len(data) < 12:
            return []
        count = struct.unpack_from(">I", data, 8)[0]
        starts = []
        for i in range(min(count, 64)):
            at = 12 + i * 4
            if at + 4 > len(data):
                break
            starts.append(struct.unpack_from(">I", data, at)[0])
    else:
        starts = [0]
    return [names for names in (_names_at(data, s) for s in starts) if names[0]]


@lru_cache(maxsize=1)
def installed() -> dict[str, dict[bool, Path]]:
    """family → {False: regular file, True: bold file}. Italics are skipped."""
    found: dict[str, dict[bool, Path]] = {}
    for folder in _font_dirs():
        for path in sorted(folder.iterdir()):
            if path.suffix.lower() not in _SUFFIXES or not path.is_file():
                continue
            for family, style in _fonts_in(path):
                low = style.lower()
                if "italic" in low or "oblique" in low:
                    continue
                bold = "bold" in low
                if not bold and low not in ("", "regular", "book", "roman",
                                            "normal", "medium"):
                    continue
                found.setdefault(family, {}).setdefault(bold, path)
    return found


def families() -> list[str]:
    """Every family the office may choose from, the usual ones first."""
    have = installed()
    liked = [name for name in ("Times New Roman", "Arial", "Calibri",
                               "Courier New", "Verdana", "Tahoma", "Georgia",
                               "Cambria", "Segoe UI") if name in have]
    return liked + sorted(name for name in have if name not in liked)


def font_file(family: str, bold: bool = False) -> tuple[Path, bool]:
    """The file to print ``family`` with, and whether bold must be FAKED.

    A family whose bold Windows never installed (many single-weight faces)
    is still printed bold — by stroking the regular outline, the way the
    чек and the МИГ card already do it.
    """
    faces = installed().get(family or "")
    if faces is None:
        for fallback in (DEFAULT_FAMILY, "Arial", "Calibri"):
            faces = installed().get(fallback)
            if faces is not None:
                break
    if faces is None:                          # no Windows fonts at all
        return _font_file("OfisSerifBold" if bold else "OfisSerif"), False
    if bold and True in faces:
        return faces[True], False
    if not bold and False in faces:
        return faces[False], False
    # one weight only: print it, and stroke it when bold was asked for
    only = faces.get(False) or faces[True]
    return only, bold and True not in faces


def font_id(family: str, bold: bool = False) -> str:
    """A short, stable PDF font name for this face."""
    tag = "".join(c for c in (family or DEFAULT_FAMILY).lower()
                  if c.isalnum()) or "font"
    return f"of_{tag}_{'b' if bold else 'r'}"[:32]
