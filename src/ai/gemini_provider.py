"""Google Gemini vision provider — the document reader.

Reads the API key from settings (encrypted at rest) or the GEMINI_API_KEY env
var, and goes live the moment a key is entered in Settings.

It speaks to Google over plain HTTPS, through :mod:`src.ai.gemini_models`.
It used to go through the `google-generativeai` SDK, which cost more than it
gave on both counts: Google has ended support for the package, and the package
pinned `protobuf < 6` — quietly holding the office's OTHER program, the one
that talks to Firebase, below the protobuf version that program requires. The
REST call is the same call the SDK was making.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable

from src.ai import gemini_models
from src.ai.base import AiRawResult, IAiProvider
from src.common.errors import AiAuthError, AiError, AiInvalidJsonError
from src.common.logging import get_logger
from src.domain.enums import DocType

log = get_logger(__name__)

_MODEL = "auto"  # discover models from the key and prefer free-tier-friendly ones

#: How long one model gets to read one document. A reading is a lookup, not a
#: composition — the lite models answer in three or four seconds.
_READ_TIMEOUT_S = 90

# Ordered preference when the key exposes several models, and the ranking key
# for whatever discovery turns up. The lite models read a passport as
# accurately as the big ones and answer in a third of the time.
#
# What is NOT here matters as much: `gemini-2.0-flash` is withdrawn and
# `gemini-2.5-flash` is refused to accounts opened recently — both answer 404,
# and a list whose head is 404 is how the ДОВЕРЕННОСТЬ section stopped working
# while this one carried on.
_PREFERRED = gemini_models.READ_MODELS
_EXCLUDE = ("embedding", "aqa", "imagen", "-tts", "-pro", "vision", "learnlm")


def _rank(name: str) -> tuple[int, str]:
    for i, pref in enumerate(_PREFERRED):
        if name == pref:
            return (i, name)
    if "flash-lite" in name:
        return (len(_PREFERRED), name)
    if "flash" in name:
        return (len(_PREFERRED) + 1, name)
    return (len(_PREFERRED) + 5, name)


class GeminiProvider(IAiProvider):
    name = "gemini"

    def __init__(
        self,
        api_key: str | None = None,
        key_getter: Callable[[], str] | None = None,
        model: str = _MODEL,
    ) -> None:
        # ``key_getter`` reads the key live (from Settings) so entering it takes
        # effect immediately, without restarting the app.
        self._static = api_key
        self._key_getter = key_getter
        self._model = model
        self._chosen: str | None = None  # first model that works, reused after
        self._discovered: list[str] | None = None  # list_models() cache

    def _key(self) -> str:
        if self._key_getter:
            live = (self._key_getter() or "").strip()
            if live:
                return live
        return (self._static or "").strip() or os.environ.get("GEMINI_API_KEY", "").strip()

    def is_configured(self) -> bool:
        return bool(self._key())

    def extract(self, image: bytes, doc_type: DocType, prompt: str) -> AiRawResult:
        api_key = self._key()
        if not api_key:
            raise AiAuthError("Gemini API key is not set")
        last_exc: Exception | None = None

        # Fast path: a model already proved itself this session — use it directly
        # (one retry on a transient rate-limit), never re-discovering.
        if self._chosen:
            try:
                return self._call(api_key, self._chosen, image, prompt, doc_type,
                                  retries=1)
            except Exception as exc:  # noqa: BLE001 - fall back to a full search
                last_exc = exc
                self._chosen = None

        # Try the known-good names first (no network call). Only if every one of
        # them fails do we spend a listing call to discover others.
        tried: set[str] = set()

        def _try(names: list[str]) -> AiRawResult | None:
            nonlocal last_exc
            for model_name in names:
                if model_name in tried:
                    continue
                tried.add(model_name)
                try:
                    result = self._call(api_key, model_name, image, prompt,
                                        doc_type, retries=1)
                    self._chosen = model_name  # remember the winner for next time
                    return result
                except Exception as exc:  # noqa: BLE001 - provider boundary
                    last_exc = exc
                    log.warning("Gemini model %s failed: %s", model_name,
                                gemini_models.why(exc))
            return None

        result = _try(self._candidates())
        if result is None:
            result = _try(self._discover(api_key))  # last resort — one API call
        if result is not None:
            return result
        raise AiError(_friendly(last_exc)) from last_exc

    def check(self) -> str:
        """A tiny live call, for the «Tekshirish» button in Settings."""
        api_key = self._key()
        if not api_key:
            raise AiAuthError("Gemini калити киритилмаган")
        last: Exception | None = None
        for model_name in self._candidates()[:3]:
            try:
                gemini_models.generate(api_key, model_name,
                                       [{"text": "ping"}], timeout=30)
                return f"Gemini ишлаяпти ({model_name})"
            except Exception as exc:  # noqa: BLE001 - try the next model
                last = exc
        raise AiError(_friendly(last))

    def _call(self, api_key: str, model_name: str, image: bytes, prompt: str,
              doc_type: DocType, *, retries: int) -> AiRawResult:
        for attempt in range(retries + 1):
            try:
                text = gemini_models.generate(
                    api_key, model_name,
                    gemini_models.parts_of(prompt, [image]), timeout=_READ_TIMEOUT_S)
                log.info("Gemini OK via %s", model_name)
                return _parse(text, doc_type, self.name)
            except Exception as exc:  # noqa: BLE001
                said = gemini_models.why(exc)
                # A model that is gone or overloaded never improves by being
                # waited on — the next name in the list usually answers at once.
                if gemini_models.move_on(exc):
                    raise
                if _is_rate_limit(said) and attempt < retries:
                    time.sleep(min(_retry_after(said), 8.0))
                    continue
                raise

    def _candidates(self) -> list[str]:
        """The fixed known-good list (no network call). Pinned model wins."""
        if self._model and self._model != "auto":
            return [self._model, *[c for c in _PREFERRED if c != self._model]]
        return list(_PREFERRED)

    def _discover(self, api_key: str) -> list[str]:
        """What the key may actually call, computed once and cached, used only
        when every known model already failed."""
        if self._discovered is None:
            discovered: list[str] = []
            try:
                discovered = [name for name in gemini_models.offered(api_key)
                              if not any(x in name for x in _EXCLUDE)]
            except Exception as exc:  # noqa: BLE001 - discovery is best-effort
                log.warning("Gemini listing failed: %s", gemini_models.why(exc))
            self._discovered = sorted(dict.fromkeys(discovered), key=_rank)
        return self._discovered


def _is_rate_limit(text: str) -> bool:
    low = text.lower()
    return "429" in text or "rate" in low or ("quota" in low and "limit: 0" not in low)


def _retry_after(text: str) -> float:
    """Seconds to wait, parsed from 'retry in 10.85s' when present, else 15s."""
    m = re.search(r"retry in ([0-9.]+)s", text, re.IGNORECASE)
    return float(m.group(1)) + 1.0 if m else 15.0


def _friendly(exc: Exception | None) -> str:
    """Short, actionable message instead of Google's multi-line quota dump."""
    text = str(exc or "")
    low = text.lower()
    # 404 FIRST. Google's «no longer available to new users» body ends
    # «…for the latest features and improved QUOTA limits», so the quota
    # test below matched it and the office was told its limit had run out
    # while the real answer was that the model had been withdrawn.
    if "not found" in low or "no longer available" in low or "404" in text:
        return ("Gemini modeli endi mavjud emas (Google o'chirgan). "
                "Dasturni yangilang — «Обновить» tugmasi.")
    if "429" in text or "quota" in low or "rate" in low:
        return ("Gemini limiti tugadi yoki bepul tarifda bu model yo'q. Bir "
                "daqiqadan keyin urinib ko'ring, yoki «Qo'lda to'ldirish» dan "
                "foydalaning. (Free tier limit / quota.)")
    if "api key" in low or "permission" in low or "401" in text or "403" in text:
        return "Gemini kaliti noto'g'ri yoki ruxsat yo'q. Sozlamalarda kalitni tekshiring."
    return f"Gemini xatosi: {text[:160]}"


def _parse(text: str, doc_type: DocType, provider: str) -> AiRawResult:
    # Strip ```json fences a model sometimes adds despite instructions.
    cleaned = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise AiInvalidJsonError("Model did not return valid JSON", context={"raw": text[:200]}) from exc
    fields = {k: str(v) for k, v in data.items() if k != "document_type"}
    return AiRawResult(document_type=doc_type, fields=fields, provider=provider)
