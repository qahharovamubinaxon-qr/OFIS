"""OpenRouter — the door that stays open when one company shuts a model.

The office asked for it after a day in which Gemini answered 404 because
Google had withdrawn a model and Groq answered nothing because its tier
carries one reasoning model and 8000 tokens a minute. What matters here is
that a withdrawn model costs the office nothing, that the free models really
are free, and that whatever shape an answer arrives in, the values come out.
"""

from __future__ import annotations

import pytest
from src.ai import openrouter_provider as mod
from src.ai.openrouter_provider import MODELS, OpenRouterProvider, _parse
from src.common.errors import AiAuthError, AiError, AiInvalidJsonError
from src.domain.enums import DocType

KEY = "sk-or-test-not-a-real-key"
IMAGE = b"\xff\xd8fake-jpeg"


def _said(text: str) -> dict:
    return {"choices": [{"message": {"content": text}}]}


class _Service:
    """A stand-in: say what each model does, read back what was asked."""

    def __init__(self) -> None:
        self.tried: list[str] = []
        self.plan: dict[str, object] = {}
        self.sent: dict = {}
        self.headers: dict = {}

    def post_json(self, url, payload, *, api_key, provider, timeout=None,
                  extra_headers=None):
        self.tried.append(payload["model"])
        self.sent = payload
        self.headers = extra_headers or {}
        answer = self.plan.get(payload["model"])
        if isinstance(answer, BaseException):
            raise answer
        if answer is None:
            raise AiError(f"{provider}: 404 No endpoints found for that model")
        return _said(str(answer))


@pytest.fixture
def service(monkeypatch):
    fake = _Service()
    monkeypatch.setattr(mod, "post_json", fake.post_json)
    return fake


def _read(provider: OpenRouterProvider) -> dict[str, str]:
    return provider.extract(IMAGE, DocType.PASSPORT, "read this").fields


# --------------------------------------------------------- the model list
def test_every_listed_model_is_free() -> None:
    """A model without «:free» can start charging without warning."""
    priced = [m for m in MODELS if not m.endswith(":free") and m != "openrouter/free"]
    assert not priced, f"бепул эмас: {priced}"


def test_the_music_model_is_not_in_the_list() -> None:
    """Google's Lyria accepts a picture and is no use for a passport."""
    assert not any("lyria" in m for m in MODELS)
    assert not any("safety" in m for m in MODELS)


def test_the_router_is_the_last_resort_not_the_first() -> None:
    assert MODELS[-1] == "openrouter/free"
    assert len(MODELS) >= 3, "битта модел етарли эмас"


# ------------------------------------------------- a model that is not there
def test_a_withdrawn_model_is_abandoned_for_the_next(service) -> None:
    service.plan[MODELS[-1]] = '{"surname": "Исоев"}'
    assert _read(OpenRouterProvider(api_key=KEY))["surname"] == "Исоев"
    assert service.tried == list(MODELS), "ҳаммаси навбат билан синалмади"


def test_the_model_that_answered_is_remembered(service) -> None:
    """A 404 is paid for once, not on every document the office reads."""
    service.plan[MODELS[-1]] = '{"surname": "Исоев"}'
    provider = OpenRouterProvider(api_key=KEY)
    _read(provider)
    service.tried.clear()
    _read(provider)
    assert service.tried == [MODELS[-1]], "яна бошидан синалибди"


def test_a_real_failure_is_not_mistaken_for_a_missing_model(service) -> None:
    service.plan[MODELS[0]] = AiError("openrouter: 500 upstream is down")
    with pytest.raises(AiError, match="500"):
        _read(OpenRouterProvider(api_key=KEY))
    assert service.tried == [MODELS[0]], "500 да кейингисига ўтмаслиги керак"


def test_a_pinned_model_is_the_only_one_tried(service) -> None:
    service.plan["google/gemma-4-31b-it:free"] = '{"surname": "Исоев"}'
    provider = OpenRouterProvider(api_key=KEY, model="google/gemma-4-31b-it:free")
    _read(provider)
    assert service.tried == ["google/gemma-4-31b-it:free"]


# ---------------------------------------------------- what comes back
@pytest.mark.parametrize("answer", [
    '{"surname": "Исоев", "name": "Аслидин"}',
    '```json\n{"surname": "Исоев", "name": "Аслидин"}\n```',
    '```\n{"surname": "Исоев", "name": "Аслидин"}\n```',
    '<think>The passport says Исоев.</think>\n{"surname": "Исоев", "name": "Аслидин"}',
    'Here is the JSON:\n{"surname": "Исоев", "name": "Аслидин"}\nHope that helps.',
])
def test_the_values_come_out_however_the_model_dressed_them(answer) -> None:
    """Free models are a mixed bunch: some reason aloud, some chat, some fence."""
    assert _parse(answer) == {"surname": "Исоев", "name": "Аслидин"}


def test_a_reasoning_model_narration_never_reaches_the_parser() -> None:
    narrated = ('<think>{"surname": "WRONG"}</think>'
                '{"surname": "Исоев"}')
    assert _parse(narrated) == {"surname": "Исоев"}


def test_prose_with_no_json_at_all_is_refused_not_guessed() -> None:
    with pytest.raises(AiInvalidJsonError):
        _parse("Кечирасиз, расмни ўқий олмадим.")


def test_a_list_is_not_a_document(service) -> None:
    service.plan[MODELS[0]] = '["Исоев", "Аслидин"]'
    with pytest.raises(AiInvalidJsonError):
        _read(OpenRouterProvider(api_key=KEY))


def test_nulls_become_empty_not_the_word_none() -> None:
    assert _parse('{"patronymic": null}') == {"patronymic": ""}


# ------------------------------------------------------------- the call
def test_the_picture_travels_with_the_prompt(service) -> None:
    service.plan[MODELS[0]] = "{}"
    _read(OpenRouterProvider(api_key=KEY))
    parts = service.sent["messages"][0]["content"]
    assert parts[0]["text"] == "read this"
    assert parts[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert service.sent["temperature"] == 0, "ўқишда тасодиф керак эмас"


def test_it_says_who_is_calling(service) -> None:
    """OpenRouter attributes usage by these, and the free tiers depend on it."""
    service.plan[MODELS[0]] = "{}"
    _read(OpenRouterProvider(api_key=KEY))
    assert service.headers.get("X-Title") == "OFIS"
    assert "HTTP-Referer" in service.headers


# -------------------------------------------------------------- the key
def test_no_key_is_said_plainly_without_calling_anyone(service) -> None:
    with pytest.raises(AiAuthError):
        _read(OpenRouterProvider(api_key=""))
    assert service.tried == []


def test_a_key_in_settings_beats_one_in_the_environment(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "from-env")
    assert OpenRouterProvider()._key() == "from-env"
    assert OpenRouterProvider(key_getter=lambda: "from-settings")._key() \
        == "from-settings"


def test_it_is_not_configured_without_a_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert not OpenRouterProvider().is_configured()
    assert OpenRouterProvider(api_key=KEY).is_configured()


# ------------------------------------------------------- «Tekshirish»
def test_the_settings_button_names_the_model_that_answered(service) -> None:
    service.plan[MODELS[-1]] = "ok"
    said = OpenRouterProvider(api_key=KEY).check()
    assert MODELS[-1] in said


# ------------------------------------------------------- in the chain
def test_it_is_wired_in_last_so_gemini_keeps_the_job() -> None:
    """Gemini answers a passport in under a second; OpenRouter is the door
    that stays open when Google withdraws a model."""
    import pathlib

    import src.app as app_module

    text = pathlib.Path(app_module.__file__).read_text(encoding="utf-8")
    order = [text.index(f"{name}(key_getter") for name in
             ("MistralProvider", "GroqProvider", "GeminiProvider",
              "OpenRouterProvider")]
    assert order == sorted(order), "OpenRouter охирида туриши керак"


def test_settings_offers_a_box_for_it() -> None:
    from src.ui.views.settings_view import AI_PROVIDERS

    assert "openrouter" in {p for p, _, _ in AI_PROVIDERS}
