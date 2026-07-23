"""AI provider manager: pick the configured provider, fall back on failure.

Order: primary (Gemini) → secondary (future). Keeps the OCR service free of any
provider specifics. If nothing is configured it raises AiUnavailableError, which
the UI turns into "AI unavailable — use manual fill".
"""

from __future__ import annotations

from src.ai.base import AiRawResult, IAiProvider
from src.common.errors import AiError, AiUnavailableError
from src.common.logging import get_logger
from src.domain.enums import DocType

log = get_logger(__name__)


class AiManager:
    def __init__(self, providers: list[IAiProvider]) -> None:
        self._providers = providers

    def available(self) -> bool:
        return any(p.is_configured() for p in self._providers)

    def extract(self, image: bytes, doc_type: DocType, prompt: str) -> AiRawResult:
        last: AiError | None = None
        tried = False
        for provider in self._providers:
            if not provider.is_configured():
                continue
            tried = True
            try:
                return provider.extract(image, doc_type, prompt)
            except AiError as exc:
                log.warning("Provider %s failed: %s", provider.name, exc.message)
                last = exc
        if last is not None:
            raise last
        if not tried:
            raise AiUnavailableError("No AI provider is configured")
        raise AiUnavailableError("All AI providers failed")
