"""Provider-agnostic AI vision contract.

The OCR pipeline knows only this interface, so Gemini → OpenAI → Claude → local
is a config/registration change, never a code change (ARCHITECTURE.md §7). Every
provider returns strict JSON matching the per-document schema; the manager
validates it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from src.domain.enums import DocType


@dataclass(frozen=True)
class AiRawResult:
    """A provider's raw structured answer for one document image."""

    document_type: DocType
    fields: dict[str, str]
    confidence: dict[str, float] = field(default_factory=dict)
    provider: str = ""


class IAiProvider(ABC):
    name: str = "provider"

    @abstractmethod
    def is_configured(self) -> bool:
        """True when the provider has what it needs (e.g. an API key)."""

    @abstractmethod
    def extract(self, image: bytes, doc_type: DocType, prompt: str) -> AiRawResult:
        """Read one document image and return structured fields. Raises AiError."""
