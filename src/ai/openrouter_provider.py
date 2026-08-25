"""OpenRouter — one key, a whole shelf of free models behind it.

The office asked for this by name, and the reason is the day it had just had:
Gemini answered 404 because Google had withdrawn a model, and Groq answered
nothing at all because its key's tier carries a single reasoning model and a
budget of 8000 tokens a minute. Every other provider in the chain is one
company, and when that company changes something the office stops working.

OpenRouter is not a model — it is a door onto many, through one key and one
OpenAI-shaped call. When a model is withdrawn the next name answers, and the
office never learns it happened.

Only genuinely free, genuinely image-reading models are listed. Left out on
purpose: Google's Lyria (a MUSIC model — it accepts a picture but is no use
for a passport), NVIDIA's content-safety classifier (it judges text, it does
not read documents), and anything without a ``:free`` suffix, which may start
charging or disappear without notice.
"""

from __future__ import annotations

import base64
import json
import os
import re
from collections.abc import Callable

from src.ai.base import AiRawResult, IAiProvider
from src.ai.http import post_json
from src.common.errors import AiAuthError, AiError, AiInvalidJsonError
from src.common.logging import get_logger
from src.domain.enums import DocType

log = get_logger(__name__)

CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
ENV_KEY = "OPENROUTER_API_KEY"

#: Tried in order; the first that answers is kept for the rest of the session.
#: Ordered by how well each suits reading a photographed document: a model
#: that follows an instruction to return JSON, with room for a large picture,
#: beats a longer context that only reasons in prose.
MODELS: tuple[str, ...] = (
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "minimax/minimax-m3:free",
    "dots-studio/dots-3-note-preview:free",
    # OpenRouter's own router — it picks among whatever is free at the moment,
    # which makes it the right last resort rather than the first choice.
    "openrouter/free",
)
MODEL = MODELS[0]

#: OpenRouter asks callers to identify themselves; it is how a key's usage is
#: attributed, and how the free tiers stay open.
_HEADERS = {
    "HTTP-Referer": "https://github.com/qahharovamubinaxon-qr/OFIS",
    "X-Title": "OFIS",
}

#: Reasoning models narrate before they answer. The narration is not part of
#: the answer and must never reach the JSON parser.
_THINK = re.compile(r"<think>.*?</think>", re.S)


class OpenRouterProvider(IAiProvider):
    name = "openrouter"

    def __init__(self, api_key: str | None = None,
                 key_getter: Callable[[], str] | None = None,
                 model: str | None = None, chat_url: str = CHAT_URL) -> None:
        self._static = api_key
        self._key_getter = key_getter
        #: A pinned name, or None to work down :data:`MODELS`.
        self._model = model
        self._chat_url = chat_url
        #: The one that answered — reused, so a 404 is paid for once.
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
            raise AiAuthError("OpenRouter калити киритилмаган")
        last: AiError | None = None
        for model in self._candidates():
            try:
                answer = post_json(self._chat_url, {
                    "model": model,
                    "temperature": 0,
                    "messages": [{"role": "user", "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url",
                         "image_url": {"url": _data_uri(image)}},
                    ]}],
                }, api_key=key, provider=self.name, extra_headers=_HEADERS)
            except AiError as exc:
                # «that model is not for you, or is no longer here» — the next
                # name usually is, and waiting changes nothing.
                if not _missing(exc):
                    raise
                log.warning("OpenRouter model %s unavailable", model)
                last = exc
                continue
            fields = _parse(_content(answer, self.name))
            self._chosen = model
            log.info("OpenRouter OK (%s)", model)
            return AiRawResult(document_type=doc_type, fields=fields,
                               provider=self.name)
        raise last or AiError("openrouter: биронта модел жавоб бермади")

    def check(self) -> str:
        """A tiny live call, for the «Tekshirish» button in Settings."""
        key = self._key()
        if not key:
            raise AiAuthError("OpenRouter калити киритилмаган")
        last: AiError | None = None
        for model in self._candidates():
            try:
                answer = post_json(self._chat_url, {
                    "model": model,
                    "max_tokens": 4,
                    "messages": [{"role": "user", "content": "ping"}],
                }, api_key=key, provider=self.name, timeout=25.0,
                    extra_headers=_HEADERS)
            except AiError as exc:
                if not _missing(exc):
                    raise
                last = exc
                continue
            _content(answer, self.name)
            self._chosen = model
            return f"OpenRouter ишлаяпти ({model})"
        raise last or AiError("openrouter: биронта модел жавоб бермади")


def _data_uri(image: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(image).decode("ascii")


def _missing(exc: AiError) -> bool:
    """Is this «that model is not here», rather than a real failure?"""
    said = str(getattr(exc, "message", "") or exc).lower()
    return ("404" in said or "not a valid model" in said
            or "no endpoints" in said or "no allowed providers" in said)


def _content(answer: dict, provider: str) -> str:
    try:
        return str(answer["choices"][0]["message"]["content"] or "")
    except (KeyError, IndexError, TypeError) as exc:
        raise AiError(f"{provider}: жавоб кутилгандек эмас") from exc


def _parse(text: str) -> dict[str, str]:
    """The JSON out of an answer, however the model chose to dress it."""
    cleaned = _THINK.sub("", text).strip()
    cleaned = (cleaned.removeprefix("```json").removeprefix("```")
               .removesuffix("```").strip())
    if not cleaned.startswith("{"):
        # some models put a sentence in front of the object
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start >= 0 and end > start:
            cleaned = cleaned[start:end + 1]
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise AiInvalidJsonError("OpenRouter JSON қайтармади",
                                 context={"raw": cleaned[:200]}) from exc
    if not isinstance(data, dict):
        raise AiInvalidJsonError("OpenRouter JSON объекти қайтармади")
    return {k: "" if v is None else str(v) for k, v in data.items()
            if k != "document_type"}
