"""Free-form Gemini calls (text and/or images in → text out).

The OCR path (:mod:`src.ai.gemini_provider`) returns *structured fields* for a
known document type. Modules that need open-ended reasoning — rewrite this
document for a new worker, translate this certificate — need raw text back
instead. Both share the same API key from Settings.

No third-party dependency: raw REST over urllib, same as the rest of the app.
"""

from __future__ import annotations

import base64
import json
import time
import urllib.request

from src.common.errors import OfisError
from src.common.logging import get_logger

log = get_logger(__name__)

# Free-tier friendly first; the newest model is tried last as a quality bump
# when the key has quota for it.
_MODELS = ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest")

_RETRY_WAIT_S = 20


def _endpoint(model: str, key: str) -> str:
    return ("https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={key}")


def ask(
    key: str,
    prompt: str,
    images: list[bytes] | None = None,
    *,
    timeout: int = 180,
    json_out: bool = False,
) -> str:
    """Send ``prompt`` (+ optional images) and return the model's text.

    ``json_out`` asks the model for JSON and strips any ``` fencing, so callers
    can ``json.loads`` the result directly.
    """
    key = (key or "").strip()
    if not key:
        raise OfisError("AI kaliti yo'q — Sozlamalarga Gemini kalitini kiriting.")

    parts: list[dict] = [{"text": prompt}]
    for img in (images or [])[:15]:
        parts.append({"inline_data": {
            "mime_type": "image/jpeg",
            "data": base64.b64encode(img).decode(),
        }})

    payload: dict = {"contents": [{"parts": parts}]}
    if json_out:
        payload["generationConfig"] = {"response_mime_type": "application/json"}
    body = json.dumps(payload).encode()

    last = ""
    for model in _MODELS:
        for attempt in (1, 2):
            req = urllib.request.Request(
                _endpoint(model, key), data=body,
                headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    data = json.loads(resp.read().decode())
                text = "\n".join(
                    p.get("text", "")
                    for p in data["candidates"][0]["content"]["parts"]
                ).strip()
                if text:
                    return _unfence(text) if json_out else text
                last = "bo'sh javob"
            except Exception as exc:  # noqa: BLE001 - try the next model
                last = str(exc)[:160]
                if "429" in last and attempt == 1:
                    log.info("Rate limited on %s — waiting %ss", model, _RETRY_WAIT_S)
                    time.sleep(_RETRY_WAIT_S)
                    continue
            break
    raise OfisError(f"AI javob bermadi: {last}")


def _unfence(text: str) -> str:
    """Strip ```json … ``` fencing some models add around JSON."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()
