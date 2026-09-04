"""The provider chain: Mistral OCR → Groq vision → Gemini.

Three services read the same passport, so what matters is not that any one of
them answers but that a *wrong* answer never reaches a document: an answer that
says nothing, or carries a date nobody can read, is refused and the next
provider gets its turn.
"""

from __future__ import annotations

import base64
import json
import pathlib
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from src.ai.base import AiRawResult, IAiProvider
from src.ai.groq_provider import GroqProvider
from src.ai.manager import AiManager
from src.ai.mistral_provider import MistralProvider
from src.ai.schemas import validate
from src.common.errors import (
    AiAuthError,
    AiError,
    AiInvalidJsonError,
    AiRateLimitError,
    AiUnavailableError,
)
from src.domain.enums import DocType

PASSPORT = {
    "surname": "НАЗАРОВ", "name": "МУРОДУЛЛО", "patronymic": "ХАИТАЛИЕВИЧ",
    "nationality": "УЗБЕКИСТАН", "birth_date": "2004-02-22", "gender": "male",
    "series": "FB", "number": "1234567", "issue_date": "2023-02-16",
    "expiry_date": "2033-02-15",
}
MRZ = ("P<UZBNAZAROV<<MURODULLO<<<<<<<<<<<<<<<<<<<<<<\n"
       "FB1234567<7UZB0402224M3302156<<<<<<<<<<<<<<02")


class _Fake(IAiProvider):
    def __init__(self, name: str, *, key: bool = True, raises=None,
                 fields: dict | None = None, text: str = "") -> None:
        self.name = name
        self._key, self._raises = key, raises
        self._fields, self._text = fields or {}, text
        self.calls = 0

    def is_configured(self) -> bool:
        return self._key

    def extract(self, image, doc_type, prompt):
        self.calls += 1
        if self._raises:
            raise self._raises
        return AiRawResult(document_type=doc_type, fields=self._fields,
                           provider=self.name, text=self._text)


# ------------------------------------------------------------- the schema


def test_an_answer_that_says_nothing_is_refused() -> None:
    with pytest.raises(AiInvalidJsonError):
        validate({"surname": "", "number": "", "name": "Муродулло"},
                 DocType.PASSPORT)


def test_a_date_nobody_can_read_is_refused() -> None:
    with pytest.raises(AiInvalidJsonError):
        validate({**PASSPORT, "birth_date": "22 февраля 2004"}, DocType.PASSPORT)


@pytest.mark.parametrize("junk", ["N/A", "none", "—", "не указано", None])
def test_a_models_way_of_saying_nothing_becomes_nothing(junk) -> None:
    out = validate({**PASSPORT, "patronymic": junk}, DocType.PASSPORT)
    assert out["patronymic"] == ""


def test_every_document_the_office_reads_has_a_schema() -> None:
    for doc_type, fields in (
        (DocType.PASSPORT, PASSPORT),
        (DocType.PATENT, {"number": "2600017664", "issue_date": "2026-04-14"}),
        (DocType.STS, {"vin": "XWB4A1CD9A2123456", "plate": "А123ВС750"}),
        (DocType.DRIVER_LICENCE, {"number": "1234567", "surname": "НАЗАРОВ"}),
    ):
        assert validate(fields, doc_type)


def test_a_caller_with_its_own_keys_is_left_alone() -> None:
    """The template studies invent their own field names — nothing to check."""
    out = validate({"worker_fio": "0.31", "position": "0.44"}, DocType.UNKNOWN)
    assert out == {"worker_fio": "0.31", "position": "0.44"}


# -------------------------------------------------------------- the chain


def test_a_provider_with_no_key_is_skipped_not_failed() -> None:
    first, second = _Fake("mistral", key=False), _Fake("groq", fields=PASSPORT)
    result = AiManager([first, second]).extract(b"x", DocType.PASSPORT, "p")
    assert first.calls == 0
    assert result.provider == "groq"


@pytest.mark.parametrize("failure", [
    AiRateLimitError("429"), AiAuthError("401"), AiError("service down"),
    TimeoutError("timed out"),
])
def test_a_failure_moves_on_to_the_next_provider(failure) -> None:
    result = AiManager([_Fake("mistral", raises=failure),
                        _Fake("groq", fields=PASSPORT)]).extract(
        b"x", DocType.PASSPORT, "p")
    assert result.provider == "groq"


def test_a_confident_but_empty_answer_does_not_win() -> None:
    """A provider that answers nonsense must not beat one that answers."""
    result = AiManager([_Fake("mistral", fields={"surname": "", "number": ""}),
                        _Fake("groq", fields=PASSPORT)]).extract(
        b"x", DocType.PASSPORT, "p")
    assert result.provider == "groq"
    assert result.fields["surname"] == "НАЗАРОВ"


def test_when_all_three_fail_the_last_reason_is_raised() -> None:
    with pytest.raises(AiError) as exc:
        AiManager([_Fake("a", raises=AiError("first")),
                   _Fake("b", raises=AiError("second"))]).extract(
            b"x", DocType.PASSPORT, "p")
    assert "second" in exc.value.message


def test_with_no_keys_at_all_the_ui_is_told_to_use_manual_fill() -> None:
    with pytest.raises(AiUnavailableError):
        AiManager([_Fake("a", key=False)]).extract(b"x", DocType.PASSPORT, "p")


def test_the_page_text_survives_for_the_mrz_check() -> None:
    result = AiManager([_Fake("mistral", fields=PASSPORT, text=MRZ)]).extract(
        b"x", DocType.PASSPORT, "p")
    assert "P<UZB" in result.text


def test_the_chain_reports_which_providers_are_ready() -> None:
    manager = AiManager([_Fake("mistral"), _Fake("groq", key=False),
                         _Fake("gemini")])
    assert manager.configured() == ["mistral", "gemini"]
    assert manager.available()


# ------------------------------------------------------- over real HTTP


class _Handler(BaseHTTPRequestHandler):
    seen: list = []
    fields: dict = {}

    def log_message(self, *_a):  # keep the test output clean
        pass

    def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler's name
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Handler.seen.append((self.path, self.headers.get("Authorization"), body))
        if self.path.endswith("/unauthorised"):
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"Invalid API Key"}}')
            return
        if self.path.endswith("/ocr"):
            payload = {"pages": [{"markdown": "ПАСПОРТ\n" + MRZ}]}
        else:
            payload = {"choices": [{"message":
                                    {"content": json.dumps(_Handler.fields)}}]}
        raw = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


@pytest.fixture()
def service(monkeypatch):
    """A stand-in for the real endpoints — same JSON, same status codes."""
    monkeypatch.setenv("NO_PROXY", "*")
    monkeypatch.setenv("no_proxy", "*")
    _Handler.seen, _Handler.fields = [], dict(PASSPORT)
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_groq_sends_the_image_and_the_key_the_way_the_api_wants(service) -> None:
    provider = GroqProvider(api_key="gsk_test", chat_url=f"{service}/chat")
    result = provider.extract(b"\xff\xd8JPEG", DocType.PASSPORT, "read this")

    _path, auth, body = _Handler.seen[-1]
    assert auth == "Bearer gsk_test"
    assert body["model"].startswith("meta-llama/llama-4-scout")
    parts = body["messages"][0]["content"]
    assert parts[0]["text"] == "read this"
    uri = parts[1]["image_url"]["url"]
    assert base64.b64decode(uri.split(",", 1)[1]) == b"\xff\xd8JPEG"
    assert result.fields["surname"] == "НАЗАРОВ"


def test_mistral_reads_the_document_then_structures_it(service) -> None:
    provider = MistralProvider(api_key="k", ocr_url=f"{service}/ocr",
                               chat_url=f"{service}/chat")
    result = provider.extract(b"\xff\xd8JPEG", DocType.PASSPORT, "read this")

    assert [path for path, _a, _b in _Handler.seen] == ["/ocr", "/chat"]
    assert _Handler.seen[0][2]["model"] == "mistral-ocr-latest"
    assert "P<UZB" in result.text, "the OCR text must survive for the MRZ check"


def test_a_rejected_key_is_named_as_such_not_as_a_crash(service) -> None:
    with pytest.raises(AiAuthError):
        GroqProvider(api_key="x", chat_url=f"{service}/unauthorised").check()


def test_the_key_is_never_put_into_an_error_message(service) -> None:
    secret = "gsk_do_not_leak_me"
    with pytest.raises(AiError) as exc:
        GroqProvider(api_key=secret, chat_url=f"{service}/unauthorised").check()
    assert secret not in str(exc.value)
    assert secret not in str(exc.value.context)


def test_the_chain_falls_through_a_dead_service_to_a_live_one(service) -> None:
    chain = AiManager([
        MistralProvider(api_key="k", ocr_url=f"{service}/unauthorised",
                        chat_url=f"{service}/chat"),
        GroqProvider(api_key="k", chat_url=f"{service}/chat"),
    ])
    assert chain.extract(b"\xff\xd8J", DocType.PASSPORT, "p").provider == "groq"


def test_the_check_button_says_which_model_answered(service) -> None:
    assert "Groq" in GroqProvider(api_key="k", chat_url=f"{service}/chat").check()
    assert "Mistral" in MistralProvider(
        api_key="k", chat_url=f"{service}/chat").check()


# ---------------------------------------------------------------- wiring


def test_the_app_wires_all_three_in_order() -> None:
    from src.ai.gemini_provider import GeminiProvider

    for name, cls in (("mistral", MistralProvider), ("groq", GroqProvider),
                      ("gemini", GeminiProvider)):
        assert hasattr(cls, "check"), f"{name} needs a check() for Settings"

    import src.app as app_module

    text = pathlib.Path(app_module.__file__).read_text(encoding="utf-8")
    order = [text.index(f"{cls.__name__}(key_getter")
             for cls in (MistralProvider, GroqProvider, GeminiProvider)]
    assert order == sorted(order), "Mistral → Groq → Gemini is the intended order"


def test_each_provider_reads_its_key_from_settings_and_env(monkeypatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert not GroqProvider().is_configured()
    monkeypatch.setenv("GROQ_API_KEY", "from-env")
    assert GroqProvider().is_configured()
    # a live getter (Settings) wins, so entering a key takes effect at once
    assert GroqProvider(key_getter=lambda: "from-settings")._key() == "from-settings"


# ------------------------------------------------- a key the service refused
class _Keyed(IAiProvider):
    """A provider whose key can change, as one in Settings does."""

    def __init__(self, name: str, key: str, *, raises=None) -> None:
        self.name = name
        self.key = key
        self._raises = raises
        self.calls = 0

    def _key(self) -> str:                   # what key_id() fingerprints
        return self.key

    def is_configured(self) -> bool:
        return bool(self.key)

    def extract(self, image, doc_type, prompt):
        self.calls += 1
        if self._raises:
            raise self._raises
        return AiRawResult(document_type=doc_type, provider=self.name,
                           fields={"surname": "Исоев", "name": "Аслидин"})


def _read(manager) -> None:
    manager.extract(b"img", DocType.PASSPORT, "prompt")


def test_a_refused_key_is_not_offered_again(monkeypatch) -> None:
    """The office's «groq» slot held a key both services refused, and it was
    re-offered to them on every single passport."""
    dead = _Keyed("groq", "xai-dead", raises=AiAuthError("калит нотўғри"))
    good = _Keyed("gemini", "AQ.good")
    manager = AiManager([dead, good])

    for _ in range(5):
        _read(manager)
    assert dead.calls == 1, "рад этилган калит қайта сўралибди"
    assert good.calls == 5


def test_pasting_a_new_key_gives_it_a_fresh_chance() -> None:
    """Nothing to restart and nothing to clear — it is keyed on the KEY."""
    provider = _Keyed("groq", "xai-dead", raises=AiAuthError("калит нотўғри"))
    manager = AiManager([provider, _Keyed("gemini", "AQ.good")])
    _read(manager)
    _read(manager)
    assert provider.calls == 1

    provider.key = "gsk_the-right-one-this-time"
    provider._raises = None
    _read(manager)
    assert provider.calls == 2, "янги калит синалмади"


def test_only_the_refused_provider_is_skipped() -> None:
    dead = _Keyed("groq", "xai-dead", raises=AiAuthError("калит нотўғри"))
    slow = _Keyed("mistral", "m-key", raises=AiError("timeout"))
    good = _Keyed("gemini", "AQ.good")
    manager = AiManager([dead, slow, good])
    for _ in range(3):
        _read(manager)
    assert dead.calls == 1
    # a timeout is a bad moment, not a settled fact — it keeps its turn
    assert slow.calls == 3
    assert good.calls == 3


def test_usable_lists_only_the_keys_still_worth_trying() -> None:
    dead = _Keyed("groq", "xai-dead", raises=AiAuthError("калит нотўғри"))
    manager = AiManager([dead, _Keyed("gemini", "AQ.good")])
    assert manager.usable() == ["groq", "gemini"]
    _read(manager)
    assert manager.usable() == ["gemini"]
    assert manager.configured() == ["groq", "gemini"], "калит ҳали ҳам бор"


def test_when_every_key_is_refused_the_office_is_told_to_replace_one() -> None:
    """«Бирорта провайдер созланмаган» would send it hunting an empty box."""
    manager = AiManager([_Keyed("groq", "xai-dead",
                                raises=AiAuthError("калит нотўғри"))])
    with pytest.raises(AiAuthError):
        _read(manager)                       # first time: the real refusal
    with pytest.raises(AiUnavailableError, match="рад этилди"):
        _read(manager)                       # after: says what to do


def test_a_provider_that_cannot_be_fingerprinted_is_unaffected() -> None:
    """_Fake has no key getter — it must behave exactly as it always did."""
    dead = _Fake("groq", raises=AiAuthError("калит нотўғри"))
    manager = AiManager([dead, _Keyed("gemini", "AQ.good")])
    for _ in range(3):
        _read(manager)
    assert dead.calls == 3


def test_the_key_itself_never_leaves_the_provider() -> None:
    provider = _Keyed("groq", "xai-SECRET-VALUE")
    assert "SECRET" not in provider.key_id()
    assert provider.key_id() == _Keyed("groq", "xai-SECRET-VALUE").key_id()
    assert provider.key_id() != _Keyed("groq", "xai-other").key_id()


# ------------------------------------------------ the rate-limit cooldown
def test_a_rate_limited_provider_is_skipped_next_read() -> None:
    """Re-trying a spent free tier on every passport cost the office ~11s a
    read. Once it says «лимит тугади» it stands aside for a while."""
    limited = _Fake("mistral", raises=AiRateLimitError("mistral: лимит тугади"))
    good = _Fake("gemini", fields=PASSPORT)
    manager = AiManager([limited, good])

    manager.extract(b"img", DocType.PASSPORT, "p")     # both tried, gemini wins
    assert limited.calls == 1
    assert good.calls == 1

    manager.extract(b"img", DocType.PASSPORT, "p")     # mistral now on cooldown
    assert limited.calls == 1                          # not retried
    assert good.calls == 2


def test_a_cooled_provider_is_still_the_last_resort() -> None:
    """Cooldown must never turn into «no providers» — a spent one still gets a
    turn when nothing fresher can answer."""
    only = _Fake("mistral", raises=AiRateLimitError("лимит"))
    manager = AiManager([only])
    with pytest.raises(AiRateLimitError):
        manager.extract(b"img", DocType.PASSPORT, "p")     # cools it
    assert only.calls == 1

    only._raises = None
    only._fields = PASSPORT
    result = manager.extract(b"img", DocType.PASSPORT, "p")
    assert result.provider == "mistral"                    # tried again, answered
    assert only.calls == 2
