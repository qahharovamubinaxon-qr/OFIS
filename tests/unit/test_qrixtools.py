"""qrixtools.com — the office's own code-gated short link.

The domain is pinned here on purpose: the office corrected it once
already («qrix.tools» was wrong, it is qrixtools.com), and a wrong domain
would fail silently on every certificate.
"""

from __future__ import annotations

import io
import json
import urllib.error

import pytest
from src.common.errors import OfisError
from src.services import qrixtools


def test_the_domain_is_the_office_s_own() -> None:
    assert qrixtools.DOMAIN == "qrixtools.com"
    assert qrixtools.CREATE_URL.startswith("https://qrixtools.com/")
    assert "qrix.tools" not in qrixtools.BASE_URL


def test_the_key_is_asked_for_before_anything_is_sent() -> None:
    with pytest.raises(OfisError, match="QRIXTOOLS"):
        qrixtools.create_link("https://i.ibb.co/x.jpg", "3255", key="")


def test_nothing_is_sent_without_a_link_or_a_code() -> None:
    with pytest.raises(OfisError, match="Ҳавола"):
        qrixtools.create_link("", "3255", key="k")
    with pytest.raises(OfisError, match="код"):
        qrixtools.create_link("https://i.ibb.co/x.jpg", "", key="k")


class _Answer(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_a_short_link_comes_back_and_the_key_travels_as_a_bearer(monkeypatch
                                                                 ) -> None:
    seen = {}

    def fake_open(request, timeout=0):
        seen["url"] = request.full_url
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = json.loads(request.data.decode("utf-8"))
        return _Answer(json.dumps({"id": "kXy7Qa",
                                   "short_url": "https://qrixtools.com/s/kXy7Qa"}
                                  ).encode("utf-8"))

    monkeypatch.setattr(qrixtools.urllib.request, "urlopen", fake_open)
    made = qrixtools.create_link("https://i.ibb.co/x.jpg", "3255",
                                 "ЭРГАШЕВ — 4", key="secret")
    assert made.url == "https://qrixtools.com/s/kXy7Qa"
    assert made.id == "kXy7Qa"
    assert seen["url"] == qrixtools.CREATE_URL
    assert seen["auth"] == "Bearer secret"
    assert seen["body"]["target_url"] == "https://i.ibb.co/x.jpg"
    assert seen["body"]["code"] == "3255"


def test_a_bad_key_says_so_in_words_the_office_can_act_on(monkeypatch) -> None:
    def refuse(request, timeout=0):
        raise urllib.error.HTTPError(
            qrixtools.CREATE_URL, 401, "Unauthorized", {},
            io.BytesIO(b'{"error":"bad key"}'))

    monkeypatch.setattr(qrixtools.urllib.request, "urlopen", refuse)
    with pytest.raises(OfisError, match="калити нотўғри"):
        qrixtools.create_link("https://i.ibb.co/x.jpg", "3255", key="wrong")


def test_a_site_that_does_not_answer_does_not_crash_the_run(monkeypatch
                                                            ) -> None:
    def silence(request, timeout=0):
        raise urllib.error.URLError("no route")

    monkeypatch.setattr(qrixtools.urllib.request, "urlopen", silence)
    with pytest.raises(OfisError, match="жавоб бермади"):
        qrixtools.create_link("https://i.ibb.co/x.jpg", "3255", key="k")


def test_an_answer_without_a_link_is_refused(monkeypatch) -> None:
    monkeypatch.setattr(
        qrixtools.urllib.request, "urlopen",
        lambda r, timeout=0: _Answer(json.dumps({"id": "x"}).encode()))
    with pytest.raises(OfisError, match="қисқа ҳавола"):
        qrixtools.create_link("https://i.ibb.co/x.jpg", "3255", key="k")


def test_the_qr_is_drawn_here_and_not_fetched() -> None:
    """No picture crosses the wire — the code is made on the machine."""
    png = qrixtools.qr_png("https://qrixtools.com/s/kXy7Qa")
    assert png.startswith(b"\x89PNG")
    assert len(png) > 200
