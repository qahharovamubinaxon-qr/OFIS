"""Groq vision — Llama 4 Scout, over Groq's OpenAI-compatible endpoint.

Second in the chain: it looks at the photograph directly and answers in about a
second, which is what makes it worth having between the careful document-OCR
pass and the last-resort one.
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

CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
ENV_KEY = "GROQ_API_KEY"


class GroqProvider(IAiProvider):
    name = "groq"

    def __init__(self, api_key: str | None = None,
                 key_getter: Callable[[], str] | None = None,
                 model: str = MODEL, chat_url: str = CHAT_URL) -> None:
        self._static = api_key
        self._key_getter = key_getter
        self._model = model
        self._chat_url = chat_url

    def _key(self) -> str:
        if self._key_getter:
            live = (self._key_getter() or "").strip()
            if live:
                return live
        return (self._static or "").strip() or os.environ.get(ENV_KEY, "").strip()

    def is_configured(self) -> bool:
        return bool(self._key())

    def extract(self, image: bytes, doc_type: DocType, prompt: str) -> AiRawResult:
        key = self._key()
        if not key:
            raise AiAuthError("Groq калити киритилмаган")
        answer = post_json(self._chat_url, {
            "model": self._model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url",
                 "image_url": {"url": _data_uri(image)}},
            ]}],
        }, api_key=key, provider=self.name)
        fields = _parse(_content(answer, self.name))
        log.info("Groq OK (%s)", self._model)
        return AiRawResult(document_type=doc_type, fields=fields, provider=self.name)

    def check(self) -> str:
        """A tiny live call, for the «Tekshirish» button in Settings."""
        key = self._key()
        if not key:
            raise AiAuthError("Groq калити киритилмаган")
        answer = post_json(self._chat_url, {
            "model": self._model,
            "max_tokens": 4,
            "messages": [{"role": "user", "content": "ping"}],
        }, api_key=key, provider=self.name, timeout=20.0)
        _content(answer, self.name)
        return f"Groq ишлаяпти ({self._model})"


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
        raise AiInvalidJsonError("Groq JSON қайтармади",
                                 context={"raw": cleaned[:200]}) from exc
    if not isinstance(data, dict):
        raise AiInvalidJsonError("Groq JSON объекти қайтармади")
    return {k: "" if v is None else str(v) for k, v in data.items()
            if k != "document_type"}
