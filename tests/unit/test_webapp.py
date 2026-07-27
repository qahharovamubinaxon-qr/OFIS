"""Mini App — auth, module catalogue and running a module without a browser."""

from __future__ import annotations

import hashlib
import hmac
import tempfile
import urllib.parse
from datetime import date
from pathlib import Path

import pytest

from src.config import paths

TOKEN = "123456:AA-test-token"
PAROL = "ofis2026"


@pytest.fixture()
def server(monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", tempfile.mkdtemp())
    paths.data_dir.cache_clear()
    from src.app import build_container
    from src.config.settings_service import SettingsService
    from src.controllers.telegram_bot import KEY_PASSWORD, KEY_TOKEN
    from src.controllers.telegram_webapp import WebAppServer

    container = build_container()
    settings = container.resolve(SettingsService)
    settings.set(KEY_TOKEN, TOKEN)
    settings.set(KEY_PASSWORD, PAROL)

    s = WebAppServer(container)
    s._settings = settings
    yield s
    paths.data_dir.cache_clear()


def _signed_init_data(token: str, payload: str = "auth_date=1&user=%7B%7D") -> str:
    pairs = urllib.parse.parse_qsl(payload, keep_blank_values=True)
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return f"{payload}&hash={digest}"


# ---------------------------------------------------------------- auth


def test_password_grants_access(server) -> None:
    assert server.authorized(PAROL, "")
    assert not server.authorized("boshqa", "")
    assert not server.authorized("", "")


def test_telegram_init_data_is_verified(server) -> None:
    assert server.authorized("", _signed_init_data(TOKEN))
    assert not server.authorized("", _signed_init_data("wrong:token"))
    assert not server.authorized("", "auth_date=1&hash=deadbeef")


# ------------------------------------------------------------- catalogue


def test_catalogue_matches_the_bot(server) -> None:
    from src.controllers.ofis_modules import MODULES

    payload = server.modules_payload()
    assert [m["key"] for m in payload] == [m.key for m in MODULES]
    by_key = {m["key"]: m for m in payload}
    assert by_key["hostel"]["needsTarget"] is True
    assert [a["field"] for a in by_key["hostel"]["asks"]] == ["start", "expiry"]
    assert by_key["summa"]["textOnly"] is True
    # modules that need no AI are usable even without a Gemini key
    assert by_key["jpg2pdf"]["ready"] is True


def test_hostel_run_passes_both_dates(server, monkeypatch) -> None:
    seen = {}

    def fake_generate(target, passport, patent, back, *,
                      registration_expiry, registration_start):
        seen["start"] = registration_start
        seen["expiry"] = registration_expiry
        out = paths.output_dir() / "wa_hostel.pdf"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"%PDF-1.4\n")

        class R:
            pdf_path = out

        return R()

    monkeypatch.setattr(server.ctl()["ocr"], "available", lambda: True)
    monkeypatch.setattr(server.ctl()["hostel"], "generate_from_images", fake_generate)

    result = server.run_module("hostel", 0, [b"img"], {
        "start": "27.07.2026", "expiry": "25.10.2026"})
    assert result["ok"] and result["files"]
    assert seen == {"start": date(2026, 7, 27), "expiry": date(2026, 10, 25)}

    # the produced file is reachable by its download token, and only by it
    token = result["files"][0]["token"]
    assert server.result_path(token) == paths.output_dir() / "wa_hostel.pdf"
    assert server.result_path("nonsense") is None


def test_missing_target_is_refused(server, monkeypatch) -> None:
    from src.common.errors import OfisError

    monkeypatch.setattr(server.ctl()["ocr"], "available", lambda: True)
    with pytest.raises(OfisError):
        server.run_module("reg", None, [b"img"], {"expiry": "25.10.2026"})


def test_module_without_ai_key_is_refused(server, monkeypatch) -> None:
    from src.common.errors import OfisError

    monkeypatch.setattr(server.ctl()["ocr"], "available", lambda: False)
    with pytest.raises(OfisError):
        server.run_module("reg", 0, [b"img"], {"expiry": "25.10.2026"})


def test_summa_module_returns_words_and_no_file(server) -> None:
    result = server.run_module("summa", None, [], {"value": "27500,50"})
    assert result["files"] == []
    assert "Двадцать семь тысяч пятьсот" in "\n".join(result["notes"])


def test_page_is_self_contained_html(server) -> None:
    from src.controllers.telegram_webapp import PAGE

    assert PAGE.lstrip().startswith("<!doctype html>")
    assert "telegram-web-app.js" in PAGE
    assert "/api/run" in PAGE


def test_http_server_serves_the_page_and_guards_the_api(server, monkeypatch) -> None:
    """End-to-end over a real socket: the page is public, the API is not."""
    import json
    import urllib.error
    import urllib.request

    from src.controllers.telegram_webapp import KEY_ENABLED, KEY_PORT

    server._settings.set(KEY_ENABLED, "1")
    server._settings.set(KEY_PORT, "0")  # let the OS pick a free port
    assert server.start() is not None
    try:
        port = server._httpd.server_address[1]
        base = f"http://127.0.0.1:{port}"

        with urllib.request.urlopen(f"{base}/", timeout=10) as resp:
            assert b"<!doctype html>" in resp.read()[:40].lower()

        with pytest.raises(urllib.error.HTTPError) as bad:
            urllib.request.urlopen(f"{base}/api/modules?k=wrong", timeout=10)
        assert bad.value.code == 403

        with urllib.request.urlopen(
                f"{base}/api/modules?k={PAROL}", timeout=10) as resp:
            modules = json.loads(resp.read().decode())
        assert [m["key"] for m in modules][:2] == ["patent", "reg"]
    finally:
        server.stop()
