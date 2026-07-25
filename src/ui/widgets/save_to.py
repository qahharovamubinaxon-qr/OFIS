"""«Qayerga saqlash?» — after generation, offer a save location (обзор).

The generated files always stay in the app's output/ folder; this copies them
to wherever the operator picks and returns that folder (or None if skipped).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtWidgets import QFileDialog


def ask_save_dir(parent, files: list[Path]) -> Path | None:
    files = [f for f in files if f and Path(f).exists()]
    if not files:
        return None
    target = QFileDialog.getExistingDirectory(
        parent, "Qayerga saqlash? (Bekor qilsangiz — dastur papkasida qoladi)"
    )
    if not target:
        return None
    dest_dir = Path(target)
    for f in files:
        dest = dest_dir / Path(f).name
        i = 1
        while dest.exists():
            dest = dest_dir / f"{Path(f).stem}_{i:03d}{Path(f).suffix}"
            i += 1
        shutil.copyfile(f, dest)
    return dest_dir
