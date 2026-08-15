"""Composing prose and documents through Gemini — and surviving Google.

Google retires models under the office's feet. A key opened this month cannot
call ``gemini-2.0-flash`` at all and ``gemini-2.5-flash`` answers new accounts
with «no longer available to new users»; the busy alias answers 503. Those were
the first three models the ДОВЕРЕННОСТЬ section asked for, in its own private
copy of the list, so the section died while passport reading — which had a
longer list of its own — carried on. The office saw «AI ишламаяпти» and
reasonably suspected its key.

What is checked here is that a dead model costs the office nothing: the next
one is tried at once, no timeout is spent, and the failure that is finally
reported says which model said what.
"""

from __future__ import annotations

import io
import json
import urllib.error

import pytest
from src.ai import gemini_models, text_client
from src.common.errors import OfisError

KEY = "test-key-not-a-real-one"


class _Answer:
    """What urlopen gives back: a JSON body in a context manager."""

    def __init__(self, text: str) -> None:
        self._body = json.dumps(
            {"candidates": [{"content": {"parts": [{"text": text}]}}]}).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_) -> bool:
        return False


def _http(code: int, message: str) -> urllib.error.HTTPError:
    body = io.BytesIO(json.dumps({"error": {"message": message}}).encode())
    return urllib.error.HTTPError("https://x", code, message, {}, body)


class _Gemini:
    """A stand-in for the service: say what each model does, read back what
    was asked. ``serve`` replaces the whole handler for the odd test that
    needs to watch the request itself."""

    def __init__(self) -> None:
        self.tried: list[str] = []
        self.plan: dict[str, object] = {}
        self.sent: dict = {}
        self._handler = None

    def serve(self, handler) -> None:
        self._handler = handler

    def urlopen(self, request, timeout=None):    # noqa: ANN001 - stdlib shape
        model = request.full_url.split("/models/")[1].split(":")[0]
        self.tried.append(model)
        self.sent = json.loads(request.data.decode())
        if self._handler is not None:
            return self._handler(model)
        answer = self.plan.get(model, _http(404, "no longer available"))
        if isinstance(answer, BaseException):
            raise answer
        return _Answer(str(answer))


@pytest.fixture
def gemini(monkeypatch):
    fake = _Gemini()
    monkeypatch.setattr(text_client.urllib.request, "urlopen", fake.urlopen)
    monkeypatch.setattr(text_client.time, "sleep", lambda _s: None)
    return fake


# ------------------------------------------------------ the models it asks for
def test_it_asks_for_a_model_that_still_exists() -> None:
    """The two that broke the office must not be first in the queue again."""
    first = gemini_models.TEXT_MODELS[0]
    assert first not in ("gemini-2.0-flash", "gemini-2.5-flash")
    assert len(gemini_models.TEXT_MODELS) >= 3, "битта модел етарли эмас"


def test_every_list_is_the_same_list() -> None:
    """Three private copies of it is exactly how this went wrong."""
    from src.services import dover_service

    assert not hasattr(dover_service, "_MODELS")
    source = (dover_service.__file__)
    with open(source, encoding="utf-8") as handle:
        body = handle.read()
    assert "gemini-2.0-flash" not in body, "яна ўз рўйхати пайдо бўлибди"
    assert "generativelanguage.googleapis.com" not in body


# ------------------------------------------------------- a retired model
def test_a_retired_model_is_abandoned_for_the_next_one(gemini) -> None:
    gemini.plan[gemini_models.TEXT_MODELS[-1]] = "ДОВЕРЕННОСТЬ"
    assert text_client.ask(KEY, "compose") == "ДОВЕРЕННОСТЬ"
    assert gemini.tried == list(gemini_models.TEXT_MODELS), \
        "ҳамма моделлар навбат билан синалиши керак"


def test_a_dead_model_is_never_waited_on_twice(gemini) -> None:
    """404 is settled — retrying it is how six minutes went missing."""
    gemini.plan[gemini_models.TEXT_MODELS[-1]] = "ok"
    text_client.ask(KEY, "compose")
    assert len(gemini.tried) == len(set(gemini.tried)), \
        "ўлган модел иккинчи марта сўралибди"


def test_an_overloaded_model_is_stepped_over(gemini) -> None:
    """503 «high demand» — the very answer the office's blank got."""
    for model in gemini_models.TEXT_MODELS[:-1]:
        gemini.plan[model] = _http(503, "This model is currently experiencing "
                                        "high demand")
    gemini.plan[gemini_models.TEXT_MODELS[-1]] = "ДОВЕРЕННОСТЬ"
    assert text_client.ask(KEY, "compose") == "ДОВЕРЕННОСТЬ"


def test_the_first_model_that_answers_wins(gemini) -> None:
    gemini.plan[gemini_models.TEXT_MODELS[0]] = "биринчиси"
    gemini.plan[gemini_models.TEXT_MODELS[1]] = "иккинчиси"
    assert text_client.ask(KEY, "compose") == "биринчиси"
    assert gemini.tried == [gemini_models.TEXT_MODELS[0]], "кераксиз сўров"


# --------------------------------------------------------- what it reports
def test_the_failure_says_which_model_said_what(gemini) -> None:
    """«AI javob bermadi: The read operation timed out» named neither."""
    with pytest.raises(OfisError) as raised:
        text_client.ask(KEY, "compose")
    said = str(raised.value)
    assert gemini_models.TEXT_MODELS[-1] in said
    assert "no longer available" in said


def test_a_rate_limit_is_waited_out_once(gemini) -> None:
    """429 is the one refusal worth waiting on — the quota comes back."""
    wanted = gemini_models.TEXT_MODELS[0]
    hit = {"n": 0}

    def handler(model):
        if model != wanted:
            raise _http(404, "no longer available")
        hit["n"] += 1
        if hit["n"] == 1:
            raise _http(429, "rate limited")
        return _Answer("кечикиб келди")

    gemini.serve(handler)
    assert text_client.ask(KEY, "compose") == "кечикиб келди"
    assert gemini.tried == [wanted, wanted], "429 дан кейин қайта урилмади"


def test_no_key_is_said_plainly_without_asking_google(gemini) -> None:
    with pytest.raises(OfisError, match="kalit"):
        text_client.ask("   ", "compose")
    assert gemini.tried == []


# ------------------------------------------------------------- the key
def test_the_key_never_reaches_the_message(gemini) -> None:
    """A key in an error message ends up pasted into a chat by the office."""
    secret = "AQ.SUPER-SECRET-VALUE"
    with pytest.raises(OfisError) as raised:
        text_client.ask(secret, "compose")
    assert secret not in str(raised.value)


def test_images_travel_with_the_prompt(gemini) -> None:
    """Доверенность composes off photographed documents, not typed fields."""
    gemini.plan[gemini_models.TEXT_MODELS[0]] = "ok"
    text_client.ask(KEY, "compose", [b"\xff\xd8fake-jpeg", b"\xff\xd8another"])
    parts = gemini.sent["contents"][0]["parts"]
    assert parts[0]["text"] == "compose"
    assert sum("inline_data" in p for p in parts) == 2
