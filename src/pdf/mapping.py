"""Field-mapping models — the external, versioned description of where each
value goes on a template. Loaded from ``templates/<name>/mapping.vN.json``.

No coordinate ever lives in Python; the engine consumes only validated
:class:`FieldMapping` objects. See ARCHITECTURE.md §8.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.common.errors import MappingInvalidError

FieldType = Literal["grid", "text", "mark", "image"]
Align = Literal["left", "center", "right"]
Overflow = Literal["trim", "shrink", "wrap", "error"]


class Field_(BaseModel):
    model_config = ConfigDict(extra="allow")  # tolerate _calibrated etc.

    id: str
    type: FieldType
    page: int = Field(ge=1)
    required: bool = False

    # grid / text / mark share a subset of these
    x0: float | None = None  # grid: center-x of first cell
    y: float | None = None  # grid/text/mark baseline / anchor y
    x: float | None = None  # text/mark anchor x
    pitch: float | None = None  # grid: cell-to-cell spacing
    max_cells: int | None = None  # grid

    width: float | None = None  # text wrap / image box
    height: float | None = None  # image box

    font: str = "Arial"
    size: float = 11.0
    align: Align = "center"
    glyph: str = "V"  # mark

    transform: str | None = None  # uppercase / lowercase / title
    formatter: str | None = None  # date_dd / date_mm / date_yyyy / ...
    validator: str | None = None
    overflow: Overflow = "shrink"
    visible_if: str | None = None


class FieldMapping(BaseModel):
    model_config = ConfigDict(extra="allow")

    template: str
    template_version: str
    mapping_version: str
    page_size: tuple[float, float]
    fields: list[Field_]

    def calibrated_fields(self) -> list[Field_]:
        """Only fields whose coordinates are real (``_calibrated`` is not False)."""
        out: list[Field_] = []
        for f in self.fields:
            extra = f.model_extra or {}
            if extra.get("_calibrated") is False:
                continue
            out.append(f)
        return out

    @staticmethod
    def load(path: Path) -> "FieldMapping":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return FieldMapping.model_validate(data)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise MappingInvalidError(
                f"Could not load mapping {path.name}", context={"error": str(exc)}
            ) from exc
