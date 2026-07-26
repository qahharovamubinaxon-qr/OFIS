"""Telegram bot state machine — auth, mode selection, photo intake (offline)."""

from __future__ import annotations

import tempfile

import pytest

from src.config import paths


@pytest.fixture()
def bot(monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", tempfile.mkdtemp())
    paths.data_dir.cache_clear()
    from src.app import build_container
    from src.controllers.telegram_bot import KEY_PASSWORD, KEY_TOKEN, TelegramBot
    from src.config.settings_service import SettingsService

    container = build_container()
    settings = container.resolve(SettingsService)
    settings.set(KEY_TOKEN, "TEST:TOKEN")
    settings.set(KEY_PASSWORD, "sirli")

    b = TelegramBot(container)
    b._settings = settings
    sent: list[tuple[int, str]] = []
    monkeypatch.setattr(b, "_send",
                        lambda chat_id, text, keyboard=None: sent.append((chat_id, text)))
    monkeypatch.setattr(b, "_download", lambda file_id: b"fake-image-bytes")
    b.sent = sent
    yield b
    paths.data_dir.cache_clear()


def _msg(chat_id: int, text: str = "", photo: bool = False) -> dict:
    m: dict = {"chat": {"id": chat_id}}
    if text:
        m["text"] = text
    if photo:
        m["photo"] = [{"file_id": "small"}, {"file_id": "big"}]
    return {"message": m}


def test_auth_flow(bot) -> None:
    bot._handle(_msg(7, "/start noto'g'ri"))
    assert "хато" in bot.sent[-1][1].lower()
    bot._handle(_msg(7, "/start sirli"))
    assert "уланди" in bot.sent[-1][1].lower()
    assert 7 in bot._allowed()


def test_unauthorized_blocked(bot) -> None:
    bot._handle(_msg(99, "salom"))
    assert "/start" in bot.sent[-1][1]


def test_patent_flow_collects_photos(bot) -> None:
    bot._handle(_msg(7, "/start sirli"))
    bot._handle(_msg(7, "🛂 Патент PDF"))          # company picker shown
    assert "танланг" in bot.sent[-1][1].lower()
    bot._on_pick(7, "pick:0")                      # ГОРДИЕНКО seeded
    assert "паспорт" in bot.sent[-1][1].lower()
    bot._handle(_msg(7, photo=True))
    assert "1/3" in bot.sent[-1][1]
    bot._handle(_msg(7, photo=True))
    assert "2/3" in bot.sent[-1][1]
    # run without AI key → clear error, state reset
    bot._handle(_msg(7, "✅ Тайёрла"))
    assert "ai калити йўқ" in bot.sent[-1][1].lower()


def test_cancel_resets(bot) -> None:
    bot._handle(_msg(7, "/start sirli"))
    bot._handle(_msg(7, "🛂 Патент PDF"))
    bot._handle(_msg(7, "❌ Бекор"))
    assert bot._state[7]["mode"] is None
