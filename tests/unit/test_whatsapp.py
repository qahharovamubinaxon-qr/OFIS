"""Handing a finished document to the worker over WhatsApp.

Nothing is ever sent on anybody's behalf: WhatsApp has no open API, and the
office has no Meta Business account. What is built here is a ``wa.me`` link —
WhatsApp opens on that one number with the message already written, and the
operator presses send.
"""

from __future__ import annotations

import tempfile
import urllib.parse

import pytest
from src.config import paths
from src.services.whatsapp_service import LINK_HOURS, message, normalize_phone, wa_link


@pytest.mark.parametrize(("typed", "expected"), [
    ("+998 90 123 45 67", "998901234567"),
    ("998901234567", "998901234567"),
    ("90 123 45 67", "998901234567"),      # bare UZ mobile
    ("+7 903 123-45-67", "79031234567"),
    ("8 (903) 123 45 67", "79031234567"),  # dialled the local Russian way
    ("9031234567", "79031234567"),         # bare RU mobile
    ("+992 90 123 45 67", "992901234567"),
])
def test_numbers_are_written_the_way_whatsapp_wants(typed, expected) -> None:
    """The office writes a number every way there is; wa.me accepts one."""
    assert normalize_phone(typed) == expected


@pytest.mark.parametrize("junk", ["", "   ", "телефон", "12", "+", "1234"])
def test_what_cannot_be_a_number_is_refused(junk) -> None:
    """Better to say «рақам нотўғри» than open WhatsApp on nobody."""
    assert normalize_phone(junk) == ""
    assert wa_link(junk, "salom") == ""


def test_the_link_opens_that_chat_with_the_message_ready() -> None:
    link = wa_link("+998 90 123 45 67", "Салом\nҳужжат")
    assert link.startswith("https://wa.me/998901234567?text=")
    text = urllib.parse.unquote(link.partition("text=")[2])
    assert text == "Салом\nҳужжат"


def test_the_message_names_the_worker_and_says_when_it_dies() -> None:
    text = message("ИСАКОВ ШАХБОЗ", ["https://x/1", "https://x/2"])
    assert "ИСАКОВ ШАХБОЗ" in text
    assert "https://x/1" in text and "https://x/2" in text
    assert str(LINK_HOURS) in text, "the worker is not told the link expires"

    # no name read off the passport is not a reason to write «Здравствуйте, !»
    assert "Здравствуйте!" in message("", ["https://x/1"])


# --------------------------------------------------- the link the office gets


@pytest.fixture()
def server(monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", tempfile.mkdtemp())
    monkeypatch.setenv("LOCALAPPDATA", tempfile.mkdtemp())
    paths.data_dir.cache_clear()
    from src.app import build_container
    from src.config.settings_service import SettingsService
    from src.controllers.telegram_webapp import WebAppServer

    container = build_container()
    s = WebAppServer(container)
    s._settings = container.resolve(SettingsService)
    yield s
    paths.data_dir.cache_clear()


def test_the_shared_link_uses_the_public_address_when_there_is_one(server,
                                                                  tmp_path) -> None:
    """A LAN address is no use to a worker who is not in the office."""
    ready = tmp_path / "ISAKOV.pdf"
    ready.write_bytes(b"%PDF-1.4\n")

    server._settings.set("tg.webapp_url", "https://qora-oq.trycloudflare.com/")
    link = server.publish(ready)
    assert link.startswith("https://qora-oq.trycloudflare.com/api/file?t=")

    token = link.partition("t=")[2]
    assert server.result_path(token) == ready

    # with no tunnel it at least works indoors
    server._settings.set("tg.webapp_url", "")
    assert server.publish(ready).startswith("http://")


def test_a_shared_link_stops_working(server, tmp_path) -> None:
    """What is behind it is a migrant's own paperwork, not a public file."""
    ready = tmp_path / "ISAKOV.pdf"
    ready.write_bytes(b"%PDF-1.4\n")

    token = server.publish(ready, hours=-1).partition("t=")[2]   # already past
    assert server.result_path(token) is None, "an expired link still opened"


def test_the_whole_link_for_the_documents_just_made(server, tmp_path) -> None:
    ready = tmp_path / "ISAKOV.pdf"
    ready.write_bytes(b"%PDF-1.4\n")
    server._settings.set("tg.webapp_url", "https://x.trycloudflare.com")
    token = server.publish(ready).partition("t=")[2]

    link = server.whatsapp_link("+998901234567", "ИСАКОВ ШАХБОЗ", [token])
    assert link.startswith("https://wa.me/998901234567?text=")
    text = urllib.parse.unquote(link.partition("text=")[2])
    assert "ИСАКОВ ШАХБОЗ" in text
    assert "https://x.trycloudflare.com/api/file?t=" in text

    assert server.whatsapp_link("yo'q", "X", [token]) == ""   # bad number
    assert server.whatsapp_link("+998901234567", "X", []) == ""  # nothing made
