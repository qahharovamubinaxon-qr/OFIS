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

from src.ai.gemini_models import TEXT_MODELS, endpoint, move_on, why
from src.common.errors import OfisError
from src.common.logging import get_logger

log = get_logger(__name__)

_RETRY_WAIT_S = 20


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
    for model in TEXT_MODELS:
        for attempt in (1, 2):
            req = urllib.request.Request(
                endpoint(model, key), data=body,
                headers={"Content-Type": "application/json"})
            started = time.monotonic()
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    data = json.loads(resp.read().decode())
                text = "\n".join(
                    p.get("text", "")
                    for p in data["candidates"][0]["content"]["parts"]
                ).strip()
                if text:
                    log.info("Gemini OK via %s in %.1fs (%d belgi, %d расм)",
                             model, time.monotonic() - started, len(text),
                             len(images or []))
                    return _unfence(text) if json_out else text
                last = f"{model}: бўш жавоб"
            except Exception as exc:  # noqa: BLE001 - try the next model
                said = why(exc)
                last = f"{model}: {said}"
                # A retired or overloaded model never improves by being waited
                # on — and waiting on it is precisely how the office lost six
                # minutes to a section whose first two models no longer exist.
                if move_on(exc):
                    log.warning("Gemini %s skipped (%.1fs): %s",
                                model, time.monotonic() - started, said)
                    break
                if "429" in said and attempt == 1:
                    log.info("Rate limited on %s — waiting %ss", model, _RETRY_WAIT_S)
                    time.sleep(_RETRY_WAIT_S)
                    continue
                log.warning("Gemini %s failed (%.1fs): %s",
                            model, time.monotonic() - started, said)
            break
    log.error("Gemini: ҳамма моделлар рад этди — охиргиси: %s", last)
    raise OfisError(f"AI javob bermadi: {last}")


def _unfence(text: str) -> str:
    """Strip ```json … ``` fencing some models add around JSON."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()
