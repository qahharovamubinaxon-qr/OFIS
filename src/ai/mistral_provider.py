"""Mistral: the document-OCR endpoint, then a small model to structure it.

``mistral-ocr`` is built for documents rather than for pictures in general — it
reads a passport's small print, and the machine-readable zone in particular,
more reliably than a chat model looking at the same photograph. It returns the
page as text, so a second, cheap call turns that text into the JSON the caller
asked for.

The raw text it produced is carried back on the result, so a reader that
wants the whole page rather than the named fields needs no second OCR pass.
"""

from __future__ import annotations

import base64
import json
import os
from collections.abc import Callable

from src.ai.base import AiRawResult, IAiProvider
from src.ai.http import post_json
from src.common.errors import AiAuthError, AiError, AiInvalidJsonError
from src.common.logging import get_logger
from src.domain.enums import DocType

log = get_logger(__name__)

OCR_URL = "https://api.mistral.ai/v1/ocr"
CHAT_URL = "https://api.mistral.ai/v1/chat/completions"
OCR_MODEL = "mistral-ocr-latest"
TEXT_MODEL = "mistral-small-latest"
ENV_KEY = "MISTRAL_API_KEY"


class MistralProvider(IAiProvider):
    name = "mistral"

    def __init__(self, api_key: str | None = None,
                 key_getter: Callable[[], str] | None = None,
                 ocr_model: str = OCR_MODEL, text_model: str = TEXT_MODEL,
                 ocr_url: str = OCR_URL, chat_url: str = CHAT_URL) -> None:
        self._static = api_key
        self._key_getter = key_getter
        self._ocr_model = ocr_model
        self._text_model = text_model
        self._ocr_url = ocr_url
        self._chat_url = chat_url

    def _key(self) -> str:
        if self._key_getter:
            live = (self._key_getter() or "").strip()
            if live:
                return live
        return (self._static or "").strip() or os.environ.get(ENV_KEY, "").strip()

    def is_configured(self) -> bool:
        return bool(self._key())

    # ------------------------------------------------------------------
    def read_text(self, image: bytes) -> str:
        """The document as text — used on its own for the MRZ check."""
        key = self._key()
        if not key:
            raise AiAuthError("Mistral калити киритилмаган")
        data = post_json(self._ocr_url, {
            "model": self._ocr_model,
            "document": {"type": "image_url",
                         "image_url": _data_uri(image)},
            "include_image_base64": False,
        }, api_key=key, provider=self.name)
        pages = data.get("pages") or []
        text = "\n".join(str(p.get("markdown") or "") for p in pages).strip()
        if not text:
            raise AiError("Mistral OCR: ҳужжатдан матн чиқмади")
        return text

    def extract(self, image: bytes, doc_type: DocType, prompt: str) -> AiRawResult:
        key = self._key()
        if not key:
            raise AiAuthError("Mistral калити киритилмаган")
        text = self.read_text(image)
        answer = post_json(self._chat_url, {
            "model": self._text_model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content":
                    "Ниже — текст документа, распознанный OCR. Верни только "
                    "JSON по заданной схеме.\n\n" + text[:12000]},
            ],
        }, api_key=key, provider=self.name)
        fields = _parse(_content(answer, self.name))
        log.info("Mistral OK (%s + %s)", self._ocr_model, self._text_model)
        return AiRawResult(document_type=doc_type, fields=fields,
                           provider=self.name, text=text)

    def check(self) -> str:
        """A tiny live call, for the «Tekshirish» button in Settings."""
        key = self._key()
        if not key:
            raise AiAuthError("Mistral калити киритилмаган")
        answer = post_json(self._chat_url, {
            "model": self._text_model,
            "max_tokens": 4,
            "messages": [{"role": "user", "content": "ping"}],
        }, api_key=key, provider=self.name, timeout=20.0)
        _content(answer, self.name)
        return f"Mistral ишлаяпти ({self._text_model})"


def _data_uri(image: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(image).decode("ascii")


def _content(answer: dict, provider: str) -> str:
    try:
        return str(answer["choices"][0]["message"]["content"] or "")
    except (KeyError, IndexError, TypeError) as exc:
        raise AiError(f"{provider}: жавоб кутилгандек эмас") from exc


def _parse(text: str) -> dict[str, str]:
    cleaned = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise AiInvalidJsonError("Mistral JSON қайтармади",
                                 context={"raw": cleaned[:200]}) from exc
    if not isinstance(data, dict):
        raise AiInvalidJsonError("Mistral JSON объекти қайтармади")
    return {k: "" if v is None else str(v) for k, v in data.items()
            if k != "document_type"}
