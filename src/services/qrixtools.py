"""qrixtools.com — a short link that asks for a four-digit code first.

The office sends four certificates home about one worker. Each carries a
four-digit code printed at its foot and a QR beside it. Scanning the QR
opens the office's OWN site, which asks for that code and only then shows
the certificate — so a certificate that travels on its own is of no use to
anyone who does not also hold the paper.

This module talks to that site and nothing else. It sends a link and a
code, and gets a short link back; the QR itself is drawn here on the
machine, so no picture crosses the wire and the code works offline once
the link exists.

The key lives in Settings under :data:`SETTING_KEY` and is never written
into a file, a log or a document.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from src.common.errors import OfisError
from src.common.logging import get_logger

log = get_logger(__name__)

#: The office's own site. It is qrixtools.com — NOT «qrix.tools».
DOMAIN = "qrixtools.com"
BASE_URL = f"https://{DOMAIN}/api/v1"
CREATE_URL = f"{BASE_URL}/links"

#: Where the office keeps its key. Shown in Sozlamalar as «QRIXTOOLS».
SETTING_KEY = "ai.qrixtools_key"
SETTING_LABEL = "QRIXTOOLS"

#: A link is asked for four times in a row, so nothing may hang for long.
TIMEOUT = 15
#: A QR holding more than this reads badly on a phone camera.
LINK_LIMIT = 60


@dataclass(frozen=True)
class ShortLink:
    """What the site gives back: the link the QR will carry."""

    id: str
    url: str


def create_link(target_url: str, code: str, title: str = "", *,
                key: str = "") -> ShortLink:
    """Ask the site for a short link that opens ``target_url`` after ``code``.

    Raises :class:`OfisError` with something the operator can act on — a
    missing key, a site that did not answer, an answer that made no sense.
    """
    if not (key or "").strip():
        raise OfisError(
            f"{SETTING_LABEL} калити йўқ — Созламалар бўлимига киритинг.")
    if not (target_url or "").strip():
        raise OfisError("Ҳавола бўш — справка юкланмаган.")
    if not (code or "").strip():
        raise OfisError("4 хонали код йўқ.")

    body = json.dumps({"target_url": target_url, "code": code,
                       "title": title}).encode("utf-8")
    request = urllib.request.Request(
        CREATE_URL, data=body, method="POST",
        headers={"Authorization": f"Bearer {key.strip()}",
                 "Content-Type": "application/json",
                 "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:
            payload = json.loads(answer.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise OfisError(_complaint(exc)) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise OfisError(f"{DOMAIN} жавоб бермади — интернетни текширинг.") \
            from exc
    except (ValueError, UnicodeDecodeError) as exc:
        raise OfisError(f"{DOMAIN} тушунарсиз жавоб қайтарди.") from exc

    url = str(payload.get("short_url") or "").strip()
    if not url.startswith("http"):
        raise OfisError(f"{DOMAIN} қисқа ҳавола қайтармади.")
    if len(url) > LINK_LIMIT:
        log.info("qrixtools: ҳавола узун (%d белги) — QR майдалашиши мумкин",
                 len(url))
    return ShortLink(id=str(payload.get("id") or ""), url=url)


def _complaint(exc: urllib.error.HTTPError) -> str:
    """The site's own words when it has any, otherwise the plain code."""
    said = ""
    try:
        said = str(json.loads(exc.read().decode("utf-8")).get("error") or "")
    except Exception:                              # noqa: BLE001
        said = ""
    if exc.code in (401, 403):
        return f"{SETTING_LABEL} калити нотўғри — Созламалардан текширинг."
    return f"{DOMAIN}: {said or f'хато {exc.code}'}"


def qr_png(link: str, size: int = 12) -> bytes:
    """The QR itself, drawn here — no picture crosses the wire."""
    import io

    import qrcode

    code = qrcode.QRCode(box_size=size, border=2,
                         error_correction=qrcode.constants.ERROR_CORRECT_M)
    code.add_data(link)
    code.make(fit=True)
    buffer = io.BytesIO()
    code.make_image(fill_color="black", back_color="white").save(buffer, "PNG")
    return buffer.getvalue()
