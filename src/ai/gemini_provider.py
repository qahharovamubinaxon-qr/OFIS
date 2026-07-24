"""Google Gemini vision provider.

Reads the API key from settings (encrypted at rest) or the GEMINI_API_KEY env
var. The google-generativeai package is imported lazily so the app runs — and
tests pass — without it installed or without a key. Ready to go live the moment
a key is entered in Settings.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable

from src.ai.base import AiRawResult, IAiProvider
from src.common.errors import AiAuthError, AiError, AiInvalidJsonError
from src.common.logging import get_logger
from src.domain.enums import DocType

log = get_logger(__name__)

_MODEL = "auto"  # discover models from the key and prefer free-tier-friendly ones

# Ordered preference when the key exposes several models. The *-lite / flash
# models carry a free tier; -pro does not (that is why gemini-2.0-flash returned
# "limit: 0" for a free key). Discovery (list_models) runs first; this list is
# the fallback and the ranking key.
_PREFERRED = (
    "gemini-2.5-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash",
    "gemini-flash-latest",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
)
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
        try:
            import google.generativeai as genai  # lazy: optional dependency
        except ImportError as exc:  # pragma: no cover - env-dependent
            raise AiError("google-generativeai is not installed") from exc

        genai.configure(api_key=api_key)
        last_exc: Exception | None = None
        for model_name in self._models(genai):
            for attempt in range(3):  # retry rate-limits before giving up on a model
                try:
                    model = genai.GenerativeModel(model_name)
                    resp = model.generate_content(
                        [prompt, {"mime_type": "image/jpeg", "data": image}]
                    )
                    log.info("Gemini OK via %s", model_name)
                    return _parse((resp.text or "").strip(), doc_type, self.name)
                except Exception as exc:  # noqa: BLE001 - provider boundary → typed error
                    last_exc = exc
                    text = str(exc)
                    if _is_rate_limit(text) and attempt < 2:
                        delay = min(_retry_after(text), 30.0)
                        log.warning("Gemini %s rate-limited; retry in %.0fs", model_name, delay)
                        time.sleep(delay)
                        continue
                    log.warning("Gemini model %s failed: %s", model_name, text[:120])
                    break  # non-retryable (or out of retries) → try next model
        raise AiError(_friendly(last_exc)) from last_exc

    def _models(self, genai) -> list[str]:
        """Candidate models, best free-tier-friendly first. If the operator
        pinned one (self._model != 'auto') try it first."""
        discovered: list[str] = []
        try:
            for m in genai.list_models():
                methods = getattr(m, "supported_generation_methods", []) or []
                if "generateContent" not in methods:
                    continue
                short = m.name.split("/")[-1]
                if any(x in short for x in _EXCLUDE):
                    continue
                discovered.append(short)
        except Exception as exc:  # noqa: BLE001 - discovery is best-effort
            log.warning("Gemini list_models failed: %s", str(exc)[:120])
        candidates = discovered or list(_PREFERRED)
        candidates = sorted(dict.fromkeys(candidates), key=_rank)
        if self._model and self._model != "auto":
            candidates = [self._model, *[c for c in candidates if c != self._model]]
        return candidates


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
    if "429" in text or "quota" in low or "rate" in low:
        return ("Gemini limiti tugadi yoki bepul tarifda bu model yo'q. Bir "
                "daqiqadan keyin urinib ko'ring, yoki «Qo'lda to'ldirish» dan "
                "foydalaning. (Free tier limit / quota.)")
    if "api key" in low or "permission" in low or "401" in text or "403" in text:
        return "Gemini kaliti noto'g'ri yoki ruxsat yo'q. Sozlamalarda kalitni tekshiring."
    if "not found" in low or "404" in text:
        return "Gemini modeli topilmadi. Dasturni yangilang yoki keyinroq urinib ko'ring."
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
