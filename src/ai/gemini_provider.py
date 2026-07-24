"""Google Gemini vision provider.

Reads the API key from settings (encrypted at rest) or the GEMINI_API_KEY env
var. The google-generativeai package is imported lazily so the app runs — and
tests pass — without it installed or without a key. Ready to go live the moment
a key is entered in Settings.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable

from src.ai.base import AiRawResult, IAiProvider
from src.common.errors import AiAuthError, AiError, AiInvalidJsonError
from src.common.logging import get_logger
from src.domain.enums import DocType

log = get_logger(__name__)

_MODEL = "gemini-2.0-flash"
# Tried in order until one responds — shields against a single model being
# deprecated or its free quota being saturated for a given key.
_MODEL_FALLBACKS = ("gemini-2.0-flash", "gemini-2.5-flash", "gemini-flash-latest")


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
        models = [self._model, *[m for m in _MODEL_FALLBACKS if m != self._model]]
        last_exc: Exception | None = None
        for model_name in models:
            try:
                model = genai.GenerativeModel(model_name)
                resp = model.generate_content(
                    [prompt, {"mime_type": "image/jpeg", "data": image}]
                )
                text = (resp.text or "").strip()
                return _parse(text, doc_type, self.name)
            except Exception as exc:  # noqa: BLE001 - provider boundary → typed error
                log.warning("Gemini model %s failed: %s", model_name, exc)
                last_exc = exc
        raise AiError(f"Gemini request failed: {last_exc}") from last_exc


def _parse(text: str, doc_type: DocType, provider: str) -> AiRawResult:
    # Strip ```json fences a model sometimes adds despite instructions.
    cleaned = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise AiInvalidJsonError("Model did not return valid JSON", context={"raw": text[:200]}) from exc
    fields = {k: str(v) for k, v in data.items() if k != "document_type"}
    return AiRawResult(document_type=doc_type, fields=fields, provider=provider)
