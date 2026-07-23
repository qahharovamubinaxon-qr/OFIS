"""Offline provider used by tests and as a safe default when no key is set.

It performs no real OCR (it cannot read the image); it returns whatever canned
fields it was given. Real reading is Gemini's job; the true offline path for
operators is the manual-fill table, not this provider.
"""

from __future__ import annotations

from src.ai.base import AiRawResult, IAiProvider
from src.domain.enums import DocType


class FakeProvider(IAiProvider):
    name = "fake"

    def __init__(self, canned: dict[DocType, dict[str, str]] | None = None) -> None:
        self._canned = canned or {}

    def is_configured(self) -> bool:
        return True

    def extract(self, image: bytes, doc_type: DocType, prompt: str) -> AiRawResult:
        return AiRawResult(
            document_type=doc_type, fields=dict(self._canned.get(doc_type, {})), provider=self.name
        )
