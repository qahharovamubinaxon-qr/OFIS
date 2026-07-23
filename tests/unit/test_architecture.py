"""Import-lint: enforce the Clean Architecture dependency rule (ARCHITECTURE.md §2).

Dependencies may only point downward:
    ui → controllers → services → {ocr, ai, pdf, database} → common/config/domain

The check scans source files for forbidden ``import``s. It fails the build the
moment someone makes, e.g., a service import a UI widget or the PDF engine reach
into OCR.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"

# layer -> packages it must NOT import from
FORBIDDEN: dict[str, tuple[str, ...]] = {
    "domain": ("src.ui", "src.controllers", "src.services", "src.database",
               "src.ocr", "src.ai", "src.pdf"),
    "services": ("src.ui", "src.controllers"),
    "ocr": ("src.ui", "src.controllers", "src.pdf", "src.database"),
    "pdf": ("src.ui", "src.controllers", "src.ocr", "src.ai", "src.database"),
    "database": ("src.ui", "src.controllers", "src.ocr", "src.ai", "src.pdf"),
    "common": ("src.ui", "src.controllers", "src.services", "src.database",
               "src.ocr", "src.ai", "src.pdf"),
}

_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+(src\.[a-zA-Z0-9_.]+)", re.MULTILINE)


def test_dependency_rule_is_respected() -> None:
    violations: list[str] = []
    for layer, banned in FORBIDDEN.items():
        layer_dir = SRC / layer
        if not layer_dir.exists():
            continue
        for py in layer_dir.rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            for imported in _IMPORT_RE.findall(text):
                if any(imported == b or imported.startswith(b + ".") for b in banned):
                    violations.append(f"{py.relative_to(SRC.parent)} imports {imported}")
    assert not violations, "Architecture dependency rule violated:\n" + "\n".join(violations)
