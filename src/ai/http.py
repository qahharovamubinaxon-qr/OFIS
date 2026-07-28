"""A small JSON-over-HTTPS helper for the providers that have no SDK.

Deliberately stdlib-only: the desktop build is a PyInstaller EXE and every extra
package is another thing that can fail to bundle. Errors are mapped onto the
application's own AiError family so the manager can tell «wrong key» from «rate
limited» from «the service is down» and decide whether to try the next provider.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from src.common.errors import AiAuthError, AiError, AiRateLimitError

DEFAULT_TIMEOUT = 60.0


def post_json(url: str, payload: dict, *, api_key: str, provider: str,
              timeout: float = DEFAULT_TIMEOUT,
              extra_headers: dict[str, str] | None = None) -> dict:
    """POST ``payload`` as JSON and return the parsed response.

    The key travels in the Authorization header and is never logged, never
    written to disk and never put into an exception message.
    """
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
        **(extra_headers or {}),
    }
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = _detail(exc)
        if exc.code in (401, 403):
            raise AiAuthError(f"{provider}: калит нотўғри ёки рухсат йўқ",
                              context={"status": exc.code}) from exc
        if exc.code == 429:
            raise AiRateLimitError(f"{provider}: лимит тугади, кейинроқ уриниб кўринг",
                                   context={"status": exc.code}) from exc
        raise AiError(f"{provider}: {exc.code} {detail}",
                      context={"status": exc.code}) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AiError(f"{provider}: тармоққа уланиб бўлмади ({exc.__class__.__name__})") from exc
    except json.JSONDecodeError as exc:
        raise AiError(f"{provider}: жавоб JSON эмас") from exc


def _detail(exc: urllib.error.HTTPError) -> str:
    """The service's own words, trimmed — it usually says what is wrong."""
    try:
        raw = exc.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 - the body is best-effort
        return exc.reason or ""
    try:
        data = json.loads(raw)
        message = (data.get("error") or {})
        if isinstance(message, dict):
            return str(message.get("message") or "")[:200]
        return str(message)[:200]
    except json.JSONDecodeError:
        return raw[:200]
