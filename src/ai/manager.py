"""The provider chain: document OCR → fast vision → last resort.

Order (:mod:`src.app` wires it): **Mistral OCR** first, because it is built for
documents and reads small print and the machine-readable zone best; then **Groq
vision**, which answers in about a second; then **Gemini**, which the office has
been using all along and stays as the backstop.

Two rules keep a wrong answer from reaching a document:

* a provider with no key is skipped silently — it is not an error to have only
  one of the three;
* every answer must fit the one common schema (:mod:`src.ai.schemas`). An answer
  that says nothing, or carries a date nobody can read, is refused and the next
  provider gets its turn. Whichever provider finally answered is logged.
"""

from __future__ import annotations

import time

from src.ai.base import AiRawResult, IAiProvider
from src.ai.schemas import validate
from src.common.errors import AiError, AiUnavailableError
from src.common.logging import get_logger
from src.domain.enums import DocType

log = get_logger(__name__)


class AiManager:
    def __init__(self, providers: list[IAiProvider]) -> None:
        self._providers = providers

    @property
    def providers(self) -> list[IAiProvider]:
        return list(self._providers)

    def available(self) -> bool:
        return any(p.is_configured() for p in self._providers)

    def configured(self) -> list[str]:
        """Names of the providers that have a key, in the order they are tried."""
        return [p.name for p in self._providers if p.is_configured()]

    def extract(self, image: bytes, doc_type: DocType, prompt: str) -> AiRawResult:
        last: AiError | None = None
        tried = False
        for provider in self._providers:
            if not provider.is_configured():
                log.debug("Provider %s skipped: no key", provider.name)
                continue
            tried = True
            started = time.monotonic()
            try:
                result = provider.extract(image, doc_type, prompt)
                fields = validate(result.fields, doc_type)
            except AiError as exc:
                log.warning("Provider %s rejected (%s): %s", provider.name,
                            exc.__class__.__name__, exc.message)
                last = exc
                continue
            except Exception as exc:  # noqa: BLE001 - a provider must not crash the app
                log.warning("Provider %s failed: %s", provider.name, str(exc)[:160])
                last = AiError(f"{provider.name}: {str(exc)[:160]}")
                continue
            log.info("Read %s via %s in %.1fs", doc_type.value, provider.name,
                     time.monotonic() - started)
            return AiRawResult(document_type=result.document_type, fields=fields,
                               confidence=result.confidence,
                               provider=provider.name, text=result.text)
        if last is not None:
            raise last
        if not tried:
            raise AiUnavailableError("Бирорта AI провайдер созланмаган")
        raise AiUnavailableError("Ҳамма AI провайдерлар жавоб бермади")
