"""Telegram bot conversation flow, driven through a fake transport.

No network: ``_api``/``_send``/``_send_file``/``_download`` are replaced, so
every test exercises the real state machine and only stubs the wire.
"""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import pytest

from src.config import paths

CHAT = 7


@pytest.fixture()
def bot(monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", tempfile.mkdtemp())
    paths.data_dir.cache_clear()
    from src.app import build_container
    from src.config.settings_service import SettingsService
    from src.controllers.telegram_bot import KEY_PASSWORD, KEY_TOKEN, TelegramBot

    container = build_container()
    settings = container.resolve(SettingsService)
    settings.set(KEY_TOKEN, "TEST:TOKEN")
    settings.set(KEY_PASSWORD, "sirli")

    b = TelegramBot(container)
    b._settings = settings
    b.sent = []
    b.files = []
    monkeypatch.setattr(b, "_send",
                        lambda chat_id, text, keyboard=None: b.sent.append((text, keyboard)))
    monkeypatch.setattr(b, "_send_file",
                        lambda chat_id, path, caption="": b.files.append(Path(path)))
    monkeypatch.setattr(b, "_download", lambda file_id: b"fake-image-bytes")
    monkeypatch.setattr(b, "_api", lambda method, payload: {"ok": True, "result": []})
    yield b
    paths.data_dir.cache_clear()


def _text(bot, text: str, chat_id: int = CHAT) -> None:
    bot._handle({"update_id": 1, "message": {"chat": {"id": chat_id}, "text": text}})


def _photo(bot, chat_id: int = CHAT) -> None:
    bot._handle({"update_id": 1, "message": {
        "chat": {"id": chat_id}, "photo": [{"file_id": "s"}, {"file_id": "b"}]}})


def _pick(bot, index: int, chat_id: int = CHAT) -> None:
    bot._handle({"update_id": 1, "callback_query": {
        "id": "cq1", "message": {"chat": {"id": chat_id}},
        "data": f"pick:{index}"}})


def _last(bot) -> str:
    return bot.sent[-1][0]


def _all(bot) -> str:
    return "\n".join(t for t, _ in bot.sent)


def _login(bot) -> None:
    _text(bot, "/start sirli")


@pytest.fixture()
def ready(bot, monkeypatch):
    """Logged in with the AI marked available."""
    _login(bot)
    monkeypatch.setattr(bot.ctl()["ocr"], "available", lambda: True)
    bot.sent.clear()
    return bot


# ---------------------------------------------------------------- auth


def test_auth_flow(bot) -> None:
    _text(bot, "/start noto'g'ri")
    assert "хато" in _last(bot).lower()
    _login(bot)
    assert "уланди" in _all(bot).lower()
    assert CHAT in bot._allowed()


def test_unauthorized_blocked(bot) -> None:
    _text(bot, "salom", chat_id=99)
    assert "/start" in _last(bot)


# ---------------------------------------------------------------- menu


def test_menu_lists_every_module(ready) -> None:
    from src.controllers.telegram_bot import _MODULES

    _text(ready, "☰ Бўлимлар")
    buttons = {b for row in ready.sent[-1][1]["keyboard"] for b in row}
    for module in _MODULES:
        assert module.button in buttons, f"{module.key} missing from the menu"
    assert len(_MODULES) >= 9, "the bot must cover the whole program"


# ------------------------------------------------------- registration flow


def test_registration_asks_for_the_date_then_runs(ready, monkeypatch) -> None:
    seen = {}

    def fake_generate(target, passport, patent, back, *, registration_expiry):
        seen["expiry"] = registration_expiry
        out = paths.output_dir() / "reg.pdf"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"%PDF-1.4\n")

        class R:
            pdf_path = out

        return R()

    monkeypatch.setattr(ready.ctl()["reg"], "generate_from_images", fake_generate)

    _text(ready, "🏠 Регистрация")
    _pick(ready, 0)
    _photo(ready)
    _text(ready, "✅ Тайёрла")
    assert "ТУГАШ" in _last(ready), "the date question was never asked"

    _text(ready, "15.10.2026")
    assert seen["expiry"] == date(2026, 10, 15)
    assert ready.files, "no PDF was sent back"
    assert "Тайёр" in _all(ready)


def test_bad_date_is_rejected_and_re_asked(ready) -> None:
    _text(ready, "🏠 Регистрация")
    _pick(ready, 0)
    _photo(ready)
    _text(ready, "✅ Тайёрла")
    _text(ready, "ertaga")
    assert "формати" in _last(ready)


def test_run_without_a_pick_says_what_is_missing(ready) -> None:
    """Pressing Тайёрла before choosing an address must not bounce back to
    «select a section» — that dead-ended the operator."""
    _text(ready, "🏠 Регистрация")
    _text(ready, "✅ Тайёрла")
    assert "рўйхатдан танланг" in _last(ready).lower()


def test_photos_are_refused_until_a_module_is_chosen(ready) -> None:
    _photo(ready)
    assert "бўлимни танланг" in _last(ready).lower()


def test_empty_list_does_not_leave_a_half_entered_module(ready, monkeypatch) -> None:
    monkeypatch.setattr(ready.ctl()["trud"], "firms", list)
    _text(ready, "📑 Трудовой")
    assert "бўш" in _last(ready)
    _photo(ready)  # not swallowed into a module with no target
    assert "бўлимни танланг" in _last(ready).lower()


def test_patent_flow_labels_the_photos(ready) -> None:
    _text(ready, "🛂 Патент PDF")
    _pick(ready, 0)
    _photo(ready)
    assert "1/3" in _last(ready)
    _photo(ready)
    assert "2/3" in _last(ready)


def test_missing_ai_key_is_reported_when_entering(bot) -> None:
    _login(bot)
    _text(bot, "🛂 Патент PDF")
    assert "ai калити йўқ" in _last(bot).lower()


# ------------------------------------------------------------ hostel flow


def test_hostel_asks_for_both_dates(ready, monkeypatch) -> None:
    seen = {}

    def fake_generate(target, passport, patent, back, *,
                      registration_expiry, registration_start):
        seen["start"] = registration_start
        seen["expiry"] = registration_expiry
        out = paths.output_dir() / "hostel.pdf"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"%PDF-1.4\n")

        class R:
            pdf_path = out

        return R()

    monkeypatch.setattr(ready.ctl()["hostel"], "generate_from_images", fake_generate)

    _text(ready, "🛏️ ХОСТЕЛ")
    _pick(ready, 0)
    _photo(ready)
    _text(ready, "✅ Тайёрла")
    assert "БОШЛАНИШ" in _last(ready)
    _text(ready, "27.07.2026")
    assert "ТУГАШ" in _last(ready)
    _text(ready, "25.10.2026")
    assert seen == {"start": date(2026, 7, 27), "expiry": date(2026, 10, 25)}


# ------------------------------------------------------- no-target modules


def test_jpg_to_pdf_needs_neither_ai_nor_a_target(bot) -> None:
    _login(bot)          # deliberately no AI key
    _text(bot, "🖼️ JPG→PDF")
    assert "расмларни" in _last(bot).lower()


def test_summa_module_answers_in_words(bot) -> None:
    _login(bot)
    _text(bot, "🔢 СУММА-ДАТА")
    _text(bot, "27500,50")
    assert "Двадцать семь тысяч пятьсот" in _all(bot)
    assert not bot.files


def test_summa_module_handles_a_date(bot) -> None:
    _login(bot)
    _text(bot, "🔢 СУММА-ДАТА")
    _text(bot, "25.07.2026")
    assert "июля" in _all(bot)


# ---------------------------------------------------------------- misc


def test_cancel_resets(ready) -> None:
    _text(ready, "🏠 Регистрация")
    _text(ready, "❌ Бекор")
    assert ready._state[CHAT]["mode"] is None
    _photo(ready)
    assert "бўлимни танланг" in _last(ready).lower()


def test_module_failure_is_reported_not_crashed(ready, monkeypatch) -> None:
    def boom(*a, **k):
        raise RuntimeError("gemini down")

    monkeypatch.setattr(ready.ctl()["reg"], "generate_from_images", boom)
    _text(ready, "🏠 Регистрация")
    _pick(ready, 0)
    _photo(ready)
    _text(ready, "✅ Тайёрла")
    _text(ready, "15.10.2026")
    assert "Хато" in _all(ready)
    assert ready._state[CHAT]["mode"] is None


def test_patent_now_asks_for_the_date(ready, monkeypatch) -> None:
    """Every producing module asks the date — patent used to skip it."""
    seen = {}

    def fake_generate(target, passport, patent, back, *, form_date, profession):
        seen["form_date"] = form_date

        class R:
            pdf_path = paths.output_dir() / "p.pdf"
            reg_number = "123"
        R.pdf_path.parent.mkdir(parents=True, exist_ok=True)
        R.pdf_path.write_bytes(b"%PDF-1.4\n")
        return R()

    monkeypatch.setattr(ready.ctl()["process"], "generate_from_images", fake_generate)
    _text(ready, "🛂 Патент PDF")
    _pick(ready, 0)
    _photo(ready)
    _text(ready, "✅ Тайёрла")
    assert "сана" in _last(ready).lower()  # asked, did not run yet
    _text(ready, "26.07.2026")
    assert seen["form_date"] == date(2026, 7, 26)


def test_tapping_run_at_a_date_uses_today(ready, monkeypatch) -> None:
    seen = {}

    def fake_generate(target, passport, patent, back, *, form_date, profession):
        seen["form_date"] = form_date

        class R:
            pdf_path = paths.output_dir() / "p2.pdf"
            reg_number = "1"
        R.pdf_path.parent.mkdir(parents=True, exist_ok=True)
        R.pdf_path.write_bytes(b"%PDF-1.4\n")
        return R()

    monkeypatch.setattr(ready.ctl()["process"], "generate_from_images", fake_generate)
    _text(ready, "🛂 Патент PDF")
    _pick(ready, 0)
    _photo(ready)
    _text(ready, "✅ Тайёрла")   # opens the date question
    _text(ready, "✅ Тайёрла")   # accept the suggested (today)
    assert seen["form_date"] == date.today()
