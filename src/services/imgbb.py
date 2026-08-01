"""Upload one picture to imgbb.com and hand back its DIRECT link.

The owner keeps an imgbb account; its API key is typed once in Sozlamalar.
Only the **direct** ``https://i.ibb.co/…`` address is accepted — the viewer
pages imgbb also returns are of no use to a QR code, which must open the bare
picture on any phone.

Plain urllib: the API takes a form-encoded POST with the key and the image as
base64 — no third-party dependency.
"""

from __future__ import annotations

import base64
import json
import urllib.parse
import urllib.request

from src.common.errors import OfisError
from src.common.logging import get_logger

log = get_logger(__name__)

KEY_IMGBB = "qrreg.imgbb_key"

_ENDPOINT = "https://api.imgbb.com/1/upload"


def upload(png: bytes, api_key: str, name: str = "") -> str:
    """Send the picture, return the direct ``i.ibb.co`` link.

    Raises :class:`OfisError` with a sentence the operator can act on — a QR
    pointing at nothing must never be printed.
    """
    api_key = (api_key or "").strip()
    if not api_key:
        raise OfisError("imgbb API калити йўқ — Sozlamalar'да «КРКОД РЕГ» "
                        "қисмига калитни киритинг (api.imgbb.com дан олинади).")

    payload = {"key": api_key,
               "image": base64.b64encode(png).decode("ascii")}
    if name:
        payload["name"] = name
    body = urllib.parse.urlencode(payload).encode("ascii")
    request = urllib.request.Request(_ENDPOINT, data=body, headers={
        "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(request, timeout=90) as resp:
            answer = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:                      # noqa: BLE001
        raise OfisError(f"imgbb'га юкланмади: {str(exc)[:120]}") from exc

    if not answer.get("success"):
        raise OfisError("imgbb рад этди — API калитини текширинг.")

    data = answer.get("data") or {}
    # data["image"]["url"] and data["url"] both carry the direct link; the
    # viewer page lives in data["url_viewer"] and must never be taken
    direct = ((data.get("image") or {}).get("url") or data.get("url") or "")
    if not direct.startswith("https://i.ibb.co/"):
        raise OfisError("imgbb тўғри (прямой) ҳавола қайтармади — "
                        f"келгани: {direct[:60]}")
    log.info("imgbb: %s", direct)
    return direct
