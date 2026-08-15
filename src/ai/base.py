"""Provider-agnostic AI vision contract.

The OCR pipeline knows only this interface, so Gemini → OpenAI → Claude → local
is a config/registration change, never a code change (ARCHITECTURE.md §7). Every
provider returns strict JSON matching the per-document schema; the manager
validates it.
"""

from __future__ import annotations

import hashlib
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
    #: The page as the provider read it, when it does document OCR; empty for a
    #: provider that only answers questions about a picture. Readers that want
    #: the whole page rather than the named fields work off this.
    text: str = ""


class IAiProvider(ABC):
    name: str = "provider"

    @abstractmethod
    def is_configured(self) -> bool:
        """True when the provider has what it needs (e.g. an API key)."""

    @abstractmethod
    def extract(self, image: bytes, doc_type: DocType, prompt: str) -> AiRawResult:
        """Read one document image and return structured fields. Raises AiError."""

    def key_id(self) -> str:
        """A short fingerprint of the key in force, or ``""`` if unknowable.

        The manager needs to tell «the same key that was refused a minute ago»
        from «the office has just pasted a new one». It cannot hold the key
        itself — a key must not travel further than the provider that uses it —
        so it holds this instead: it changes when the key changes and says
        nothing about the key otherwise.
        """
        getter = getattr(self, "_key", None)
        if not callable(getter):
            return ""
        try:
            key = (getter() or "").strip()
        except Exception:                    # noqa: BLE001 - a key is never fatal
            return ""
        return hashlib.sha256(key.encode()).hexdigest()[:16] if key else ""
