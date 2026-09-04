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

And one rule keeps a settled failure from being paid for over and over: a key
the service says is *invalid* is not offered to it again. That is different
from a timeout or a rate limit, which are bad moments and keep their turn. The
office's «groq» slot held a key both Groq and x.ai refused, and it cost a round
trip on every passport read all day. It is remembered against the KEY, so
pasting a new one into Sozlamalar gives it a fresh chance at once.
"""

from __future__ import annotations

import time

from src.ai.base import AiRawResult, IAiProvider
from src.ai.schemas import validate
from src.common.errors import (
    AiAuthError,
    AiError,
    AiQuotaError,
    AiRateLimitError,
    AiUnavailableError,
)
from src.common.logging import get_logger
from src.domain.enums import DocType

log = get_logger(__name__)

#: How long a rate-limited / out-of-quota provider is set aside before it gets
#: a fresh turn. A limited key keeps its turn (unlike a refused one) but not on
#: the VERY NEXT document — re-trying a spent Mistral and Groq on every passport
#: cost the office ~11 seconds a read while the free tiers were used up. It is
#: still tried as a last resort when nothing fresher can answer.
_COOLDOWN_S = 300.0


class AiManager:
    def __init__(self, providers: list[IAiProvider]) -> None:
        self._providers = providers
        #: (provider, key fingerprint) pairs the service has told us are not
        #: valid. A refused key is not a bad moment — it is a settled fact, and
        #: asking again costs a network round-trip on every document the office
        #: reads. The office's «groq» slot held a key both Groq and x.ai
        #: refused, and it was re-offered to them on every single passport.
        #:
        #: Keyed on the KEY, not the provider, so pasting a new one into
        #: Sozlamalar takes effect at once with nothing to restart or clear.
        self._refused: set[tuple[str, str]] = set()
        #: provider name → monotonic time its rate-limit cooldown ends. Unlike
        #: a refused key this is a passing state, so it is kept by NAME (a new
        #: key does not clear it — the limit is on the account, not the string)
        #: and it expires on its own.
        self._cooldown: dict[str, float] = {}

    @property
    def providers(self) -> list[IAiProvider]:
        return list(self._providers)

    def available(self) -> bool:
        return any(p.is_configured() for p in self._providers)

    def configured(self) -> list[str]:
        """Names of the providers that have a key, in the order they are tried."""
        return [p.name for p in self._providers if p.is_configured()]

    def usable(self) -> list[str]:
        """Those that have a key the service has not already refused."""
        return [p.name for p in self._providers
                if p.is_configured() and not self._is_refused(p)]

    def _is_refused(self, provider: IAiProvider) -> bool:
        fingerprint = provider.key_id()
        return bool(fingerprint) and (provider.name, fingerprint) in self._refused

    def _on_cooldown(self, provider: IAiProvider) -> bool:
        until = self._cooldown.get(provider.name)
        return until is not None and time.monotonic() < until

    def _refuse(self, provider: IAiProvider) -> None:
        # Only when the key can be fingerprinted: without one there is no way
        # to notice the office replacing it, and skipping for ever would be
        # worse than the round-trip this saves.
        fingerprint = provider.key_id()
        if fingerprint:
            self._refused.add((provider.name, fingerprint))
            log.warning("Provider %s: калит рад этилди — бу калит билан "
                        "бошқа сўралмайди (Созламалардан алмаштиринг)",
                        provider.name)

    def extract(self, image: bytes, doc_type: DocType, prompt: str) -> AiRawResult:
        configured = [p for p in self._providers if p.is_configured()]
        live = [p for p in configured if not self._is_refused(p)]
        # a spent provider keeps its turn, but at the BACK of the queue — a
        # fresh one answers first, and it is reached only if nothing else can
        fresh = [p for p in live if not self._on_cooldown(p)]
        cooled = [p for p in live if self._on_cooldown(p)]
        order = fresh + cooled

        last: AiError | None = None
        for provider in order:
            started = time.monotonic()
            try:
                result = provider.extract(image, doc_type, prompt)
                fields = validate(result.fields, doc_type)
            except AiAuthError as exc:
                self._refuse(provider)
                last = exc
                continue
            except (AiRateLimitError, AiQuotaError) as exc:
                self._cooldown[provider.name] = time.monotonic() + _COOLDOWN_S
                log.warning("Provider %s лимитда — %.0f сония четда: %s",
                            provider.name, _COOLDOWN_S, exc.message)
                last = exc
                continue
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
        refused = [p.name for p in configured if self._is_refused(p)]
        if refused:
            # Everything with a key has one the service has already refused —
            # saying «not configured» would send the office looking for an
            # empty box when what it needs is a new key in a full one.
            raise AiUnavailableError(
                "AI калити рад этилди: " + ", ".join(refused) +
                ". Созламалардан янги калит киритинг.")
        if not configured:
            raise AiUnavailableError("Бирорта AI провайдер созланмаган")
        raise AiUnavailableError("Ҳамма AI провайдерлар жавоб бермади")
