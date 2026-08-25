"""Groq vision, over Groq's OpenAI-compatible endpoint.

Second in the chain: it looks at the photograph directly and answers in about a
second, which is what makes it worth having between the careful document-OCR
pass and the last-resort one.

Two things had to be true before it ever answered at all, and neither was:

*A model that exists.* One name was hard-wired — ``llama-4-scout`` — and Groq
has since stopped offering it to new keys, which answer 404. So the list below,
tried in order, with the winner remembered for the rest of the session. Which
models a key may call differs from key to key, so no single name is safe.

*A User-Agent.* Groq sits behind Cloudflare, and Cloudflare refuses urllib's
own «Python-urllib/3.12» with «error code: 1010» before the request ever
reaches Groq — see :mod:`src.ai.http`. Between the two, the office had a valid
gsk_ key in Settings and every single document still fell through to Gemini.
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

#: Tried in order; the first that answers is kept for the rest of the session.
#: All of these read a picture. A key that has none of them simply cannot serve
#: as a document reader, and the chain moves on to the next provider.
MODELS: tuple[str, ...] = (
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
    "qwen/qwen3.6-27b",
)
#: The default, kept under its old name for callers that pin one.
MODEL = MODELS[0]
ENV_KEY = "GROQ_API_KEY"


class GroqProvider(IAiProvider):
    name = "groq"

    def __init__(self, api_key: str | None = None,
                 key_getter: Callable[[], str] | None = None,
                 model: str | None = None, chat_url: str = CHAT_URL) -> None:
        self._static = api_key
        self._key_getter = key_getter
        #: A pinned name, or None to work down :data:`MODELS`.
        self._model = model
        self._chat_url = chat_url
        #: The one that answered — reused, so 404s are paid for once.
        self._chosen: str | None = None

    def _key(self) -> str:
        if self._key_getter:
            live = (self._key_getter() or "").strip()
            if live:
                return live
        return (self._static or "").strip() or os.environ.get(ENV_KEY, "").strip()

    def is_configured(self) -> bool:
        return bool(self._key())

    def _candidates(self) -> list[str]:
        """Which names to try, best first. A proven one short-circuits."""
        if self._model:
            return [self._model]
        if self._chosen:
            return [self._chosen, *[m for m in MODELS if m != self._chosen]]
        return list(MODELS)

    def extract(self, image: bytes, doc_type: DocType, prompt: str) -> AiRawResult:
        key = self._key()
        if not key:
            raise AiAuthError("Groq калити киритилмаган")
        last: AiError | None = None
        for model in self._candidates():
            try:
                answer = post_json(self._chat_url, {
                    "model": model,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [{"role": "user", "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url",
                         "image_url": {"url": _data_uri(image)}},
                    ]}],
                }, api_key=key, provider=self.name)
            except AiError as exc:
                # 404 means this key may not call that model — the next name
                # usually can, and waiting changes nothing.
                if not _missing(exc):
                    raise
                log.warning("Groq model %s unavailable for this key", model)
                last = exc
                continue
            fields = _parse(_content(answer, self.name))
            self._chosen = model
            log.info("Groq OK (%s)", model)
            return AiRawResult(document_type=doc_type, fields=fields,
                               provider=self.name)
        raise last or AiError("groq: биронта модел жавоб бермади")

    def check(self) -> str:
        """A tiny live call, for the «Tekshirish» button in Settings."""
        key = self._key()
        if not key:
            raise AiAuthError("Groq калити киритилмаган")
        last: AiError | None = None
        for model in self._candidates():
            try:
                answer = post_json(self._chat_url, {
                    "model": model,
                    "max_tokens": 4,
                    "messages": [{"role": "user", "content": "ping"}],
                }, api_key=key, provider=self.name, timeout=20.0)
            except AiError as exc:
                if not _missing(exc):
                    raise
                last = exc
                continue
            _content(answer, self.name)
            self._chosen = model
            return f"Groq ишлаяпти ({model})"
        raise last or AiError("groq: биронта модел жавоб бермади")


def _missing(exc: AiError) -> bool:
    """Is this «that model is not for you», rather than a real failure?"""
    said = str(getattr(exc, "message", "") or exc)
    return "404" in said or "does not exist" in said.lower()


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
