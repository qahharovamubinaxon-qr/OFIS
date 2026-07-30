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
