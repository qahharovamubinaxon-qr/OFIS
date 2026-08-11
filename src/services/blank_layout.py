"""Where a section keeps what the office arranged on one blank.

Every section that prints onto an uploaded blank can let the office drag its
values into place (:mod:`src.ui.widgets.layout_editor`). What comes back is kept
here — one small JSON per blank, in AppData:

    <AppData>/OFIS/templates/layouts/<section>/<blank>.json

In AppData and not beside the blank itself, because some sections keep their
blanks inside the program folder (ЧЕК does), and anything written there is lost
the next time the EXE is rebuilt — which is exactly what the office must not
have happen to an afternoon of lining values up.

Nothing here knows what a section's values mean. It stores what it is given and
hands it back; each section decides what to do with it.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from src.common.logging import get_logger
from src.config import paths

log = get_logger(__name__)


def _folder(section: str) -> Path:
    folder = paths.user_templates_dir() / "layouts" / section
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in " _-" else "_" for c in name).strip() or "blank"


def layout_file(section: str, template: Path | str) -> Path:
    return _folder(section) / f"{_safe(Path(template).stem)}.json"


def load(section: str, template: Path | str | None) -> dict:
    """What the office arranged on this blank — empty when it never has."""
    if template is None:
        return {}
    path = layout_file(section, template)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        log.warning("%s: %s жойлашуви ўқилмади", section, path.name)
        return {}
    return data if isinstance(data, dict) else {}


def save(section: str, template: Path | str, layout: dict) -> Path:
    path = layout_file(section, template)
    path.write_text(json.dumps(layout, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    log.info("%s: %s жойлашуви сақланди", section, path.name)
    return path


def reset(section: str, template: Path | str) -> None:
    layout_file(section, template).unlink(missing_ok=True)
    for kind in MARKS:
        clear_mark(section, template, kind)


# ------------------------------------------------- the signature and stamp
#: Pictures a blank carries rather than values it prints. Uploaded once per
#: blank and kept beside its layout, so a section that has them does not ask
#: for the same signature with every worker.
MARKS = ("signature", "stamp")
_PICTURES = (".png", ".jpg", ".jpeg")


def mark_file(section: str, template: Path | str, kind: str) -> Path | None:
    """Where this blank's signature or stamp is, if the office uploaded one."""
    if kind not in MARKS:
        return None
    stem = _safe(Path(template).stem)
    for suffix in _PICTURES:
        found = _folder(section) / f"{stem}.{kind}{suffix}"
        if found.exists():
            return found
    return None


def set_mark(section: str, template: Path | str, kind: str,
             source: Path | str) -> Path:
    """Keep a picture with THIS blank — one office's signature, not another's."""
    if kind not in MARKS:
        raise ValueError(f"unknown mark: {kind}")
    source = Path(source)
    if source.suffix.lower() not in _PICTURES:
        raise ValueError("PNG ёки JPG бўлиши керак")
    clear_mark(section, template, kind)
    target = (_folder(section)
              / f"{_safe(Path(template).stem)}.{kind}{source.suffix.lower()}")
    shutil.copyfile(source, target)
    log.info("%s: %s — %s юкланди", section, Path(template).stem, kind)
    return target


def clear_mark(section: str, template: Path | str, kind: str) -> None:
    found = mark_file(section, template, kind)
    if found is not None:
        found.unlink(missing_ok=True)


def marks(section: str, template: Path | str | None) -> dict[str, Path]:
    """Every picture this blank carries, by kind."""
    if template is None:
        return {}
    return {kind: found for kind in MARKS
            if (found := mark_file(section, template, kind)) is not None}
