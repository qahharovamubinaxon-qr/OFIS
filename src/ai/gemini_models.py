"""Which Gemini models to ask for, in what order, and when to give up on one.

Google retires models under the office's feet. A key opened this month cannot
call ``gemini-2.0-flash`` at all, and ``gemini-2.5-flash`` answers new accounts
with «no longer available to new users» — both were hard-wired as the first two
choices in two different places, so a section that never reached past them
simply stopped working while passport reading, which had its own longer list,
carried on. The office saw «AI ишламаяпти» and reasonably blamed its key.

Two rules come out of that, and they live here so there is one list to keep:

*Ask for what exists.* An alias Google maintains (``…-latest``) ages better
than a version number, but an alias is also what everyone else is pointed at,
so it is the first to answer 503 when the service is busy. The list therefore
carries both, and enough of a tail that a key with an unusual allowance still
finds something.

*Never wait on a model that is gone.* 404 means gone and 503 means busy;
neither is worth a two-minute timeout, and the next model in the list usually
answers in seconds. Only a genuine timeout or a network fault costs the wait.
"""

from __future__ import annotations

import json
import urllib.error

#: For a paragraph of prose or a composed document. Ordered by what actually
#: answered when this was last checked against a fresh key, newest first —
#: quality matters here more than the second or two it costs.
TEXT_MODELS: tuple[str, ...] = (
    "gemini-3.5-flash",
    "gemini-flash-latest",
    "gemini-2.5-flash",
    "gemini-flash-lite-latest",
    "gemini-2.5-flash-lite",
)

#: For reading a document: the lite models are as accurate at pulling a name
#: off a passport and answer in a third of the time.
READ_MODELS: tuple[str, ...] = (
    "gemini-flash-lite-latest",
    "gemini-2.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-flash-latest",
)

ENDPOINT = ("https://generativelanguage.googleapis.com/v1beta/models/"
            "{model}:generateContent?key={key}")

#: The service's own way of saying «this one is no good, try another»:
#: 404 the model is gone, 503 it is overloaded, 400 the request does not suit
#: it. None of the three gets better by waiting.
MOVE_ON = (400, 403, 404, 503)


def endpoint(model: str, key: str) -> str:
    return ENDPOINT.format(model=model, key=key)


def why(exc: BaseException) -> str:
    """The service's own words for the log — short, and never the key.

    A raw ``HTTPError`` prints as «HTTP Error 404: Not Found», which does not
    say which model or why; Google puts the useful sentence in the body.
    """
    if isinstance(exc, urllib.error.HTTPError):
        try:
            said = (json.loads(exc.read().decode("utf-8", "replace") or "{}")
                    .get("error") or {}).get("message", "")
        except Exception:                       # noqa: BLE001 - best effort
            said = exc.reason or ""
        return f"{exc.code} {said}"[:160]
    return f"{exc.__class__.__name__}: {exc}"[:160]


def move_on(exc: BaseException) -> bool:
    """Is this model worth abandoning for the next one straight away?"""
    return (isinstance(exc, urllib.error.HTTPError)
            and exc.code in MOVE_ON)
