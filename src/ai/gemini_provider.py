"""Google Gemini vision provider.

Reads the API key from settings (encrypted at rest) or the GEMINI_API_KEY env
var. The google-generativeai package is imported lazily so the app runs — and
tests pass — without it installed or without a key. Ready to go live the moment
a key is entered in Settings.
"""

from __future__ import annotations

import json
import os

from src.ai.base import AiRawResult, IAiProvider
from src.common.errors import AiAuthError, AiError, AiInvalidJsonError
from src.common.logging import get_logger
from src.domain.enums import DocType

log = get_logger(__name__)

_MODEL = "gemini-2.0-flash"


class GeminiProvider(IAiProvider):
    name = "gemini"

    def __init__(self, api_key: str | None = None, model: str = _MODEL) -> None:
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self._model = model

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def extract(self, image: bytes, doc_type: DocType, prompt: str) -> AiRawResult:
        if not self._api_key:
            raise AiAuthError("Gemini API key is not set")
        try:
            import google.generativeai as genai  # lazy: optional dependency
        except ImportError as exc:  # pragma: no cover - env-dependent
            raise AiError("google-generativeai is not installed") from exc

        try:
            genai.configure(api_key=self._api_key)
            model = genai.GenerativeModel(self._model)
            resp = model.generate_content(
                [prompt, {"mime_type": "image/jpeg", "data": image}]
            )
            text = (resp.text or "").strip()
        except Exception as exc:  # noqa: BLE001 - provider boundary → typed error
            raise AiError(f"Gemini request failed: {exc}") from exc

        return _parse(text, doc_type, self.name)


def _parse(text: str, doc_type: DocType, provider: str) -> AiRawResult:
    # Strip ```json fences a model sometimes adds despite instructions.
    cleaned = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise AiInvalidJsonError("Model did not return valid JSON", context={"raw": text[:200]}) from exc
    fields = {k: str(v) for k, v in data.items() if k != "document_type"}
    return AiRawResult(document_type=doc_type, fields=fields, provider=provider)
