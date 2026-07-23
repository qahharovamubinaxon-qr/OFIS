"""OCR result & confidence models — metadata kept separate from the domain data.

The review UI reads ``field_confidence`` to highlight anything below the
configured threshold; the archive stores ``raw_json`` (exact provider response)
and ``normalized_json`` (post-normalization) for full traceability.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from src.domain.enums import DocType


class FieldScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    confidence: float = Field(ge=0.0, le=1.0)


class OcrResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    document_type: DocType
    provider: str
    overall_confidence: float = Field(ge=0.0, le=1.0)
    field_confidence: dict[str, FieldScore] = Field(default_factory=dict)
    raw_json: dict[str, object] = Field(default_factory=dict)
    normalized_json: dict[str, object] = Field(default_factory=dict)
    processing_ms: int = 0
    created_at: datetime = Field(default_factory=datetime.now)

    def low_confidence_fields(self, threshold: float) -> list[str]:
        return [k for k, s in self.field_confidence.items() if s.confidence < threshold]
