"""УЗБ СПРАВКАЛАР — the office's blanks, its firms' seals and its numbering.

Four certificates go home to the agency about one worker: how he behaves,
what he is paid, how his family is housed and schooled, and that he really
works here. The office keeps three things between runs:

* a BLANK per certificate — its own scanned sheet, uploaded once;
* a SEAL per firm, kept by NAME, because a worker is placed with one of
  several firms and every one of his four certificates carries that firm's
  seal and no other;
* whatever it dragged in «📐 Созлаш».

Nothing here reads a document or draws a page — this is where the office's
own things are kept, and only that.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from src.common.errors import ValidationError
from src.common.logging import get_logger
from src.config import paths

log = get_logger(__name__)

SECTION = "uzbspravka"
#: The four certificates, by the numbers the office calls them.
SHEETS = (1, 2, 3, 4)
SHEET_NAMES = {
    1: "Ишчининг хулқ-атвори",
    2: "Ишчининг маоши",
    3: "Оила ҳолати — яшаш жойи ва болалар мактаби",
    4: "Ҳақиқатан ишлаётгани ҳақида",
}
_PICTURES = (".png", ".jpg", ".jpeg")
_SHEET_KINDS = (".pdf", *_PICTURES)


def folder() -> Path:
    made = paths.user_templates_dir() / SECTION
    made.mkdir(parents=True, exist_ok=True)
    return made


def seals_dir() -> Path:
    made = folder() / "seals"
    made.mkdir(parents=True, exist_ok=True)
    return made


def _safe(name: str) -> str:
    """A firm's name, as a file may carry it."""
    cleaned = "".join(c for c in (name or "").strip()
                      if c.isalnum() or c in " _-.«»\"'").strip()
    if not cleaned:
        raise ValidationError("Фирма номини ёзинг")
    return cleaned


# ---------------------------------------------------------------- blanks
def blank_of(sheet: int) -> Path | None:
    for suffix in _SHEET_KINDS:
        found = folder() / f"sheet{sheet}{suffix}"
        if found.exists():
            return found
    return None


def blanks() -> dict[int, Path]:
    return {s: found for s in SHEETS if (found := blank_of(s)) is not None}


def set_blank(sheet: int, source: Path) -> Path:
    if sheet not in SHEETS:
        raise ValidationError("Справка 1 дан 4 гача бўлиши керак")
    source = Path(source)
    if source.suffix.lower() not in _SHEET_KINDS:
        raise ValidationError("Бланка PDF ёки расм бўлиши керак")
    if not source.exists():
        raise ValidationError("Бланка файли топилмади")
    clear_blank(sheet)
    target = folder() / f"sheet{sheet}{source.suffix.lower()}"
    shutil.copyfile(source, target)
    log.info("УЗБ СПРАВКА: %d-справка бланкаси юкланди", sheet)
    return target


def clear_blank(sheet: int) -> None:
    found = blank_of(sheet)
    if found is not None:
        found.unlink(missing_ok=True)


# ------------------------------------------------------- the firms' seals
def seals() -> dict[str, Path]:
    """Every firm's seal the office has uploaded, by the name it gave it."""
    found: dict[str, Path] = {}
    for path in sorted(seals_dir().iterdir()):
        if path.is_file() and path.suffix.lower() in _PICTURES:
            found[path.stem] = path
    return found


def seal_of(firm: str) -> Path | None:
    return seals().get(_safe(firm)) if (firm or "").strip() else None


def add_seal(firm: str, source: Path) -> Path:
    """One firm, one seal. Uploading again replaces it."""
    source = Path(source)
    if source.suffix.lower() not in _PICTURES:
        raise ValidationError("Печать расм бўлиши керак (шаффоф PNG яхши)")
    if not source.exists():
        raise ValidationError("Печать файли топилмади")
    name = _safe(firm)
    remove_seal(name)
    target = seals_dir() / f"{name}{source.suffix.lower()}"
    shutil.copyfile(source, target)
    log.info("УЗБ СПРАВКА: «%s» печати юкланди", name)
    return target


def remove_seal(firm: str) -> None:
    found = seals().get(_safe(firm))
    if found is not None:
        found.unlink(missing_ok=True)


# ------------------------------------------------------------ the layout
def load_layout() -> dict:
    from src.services import blank_layout

    return blank_layout.load(SECTION, SECTION)


def save_layout(layout: dict) -> None:
    from src.services import blank_layout

    blank_layout.save(SECTION, SECTION, layout)
