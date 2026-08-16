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

import base64
import json
import urllib.error
import urllib.request

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


# ---------------------------------------------------------------- the wire
# Plain HTTPS with the standard library, and no SDK. `google-generativeai`
# was the SDK this used to go through, and it cost more than it gave: Google
# ended support for it, and it pinned `protobuf < 6` — which quietly held the
# office's OTHER program, the one that talks to Firebase, below the version
# that program requires. One dependency fewer is also one less thing that can
# fail to bundle into the EXE.


def parts_of(prompt: str, images: list[bytes] | None = None) -> list[dict]:
    """A prompt, and any pictures with it, in the shape the service wants."""
    made: list[dict] = [{"text": prompt}]
    for picture in (images or [])[:15]:
        made.append({"inline_data": {
            "mime_type": "image/jpeg",
            "data": base64.b64encode(picture).decode(),
        }})
    return made


def generate(key: str, model: str, parts: list[dict], *,
             timeout: float = 180, json_out: bool = False) -> str:
    """One call to one model. The answer's text, or an exception to act on.

    Raises whatever urllib raises — the caller decides whether that model is
    worth abandoning (see :func:`move_on`) or waiting on.
    """
    payload: dict = {"contents": [{"parts": parts}]}
    if json_out:
        payload["generationConfig"] = {"response_mime_type": "application/json"}
    request = urllib.request.Request(
        endpoint(model, key), data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as answer:
        said = json.loads(answer.read().decode())
    return "\n".join(
        part.get("text", "")
        for part in said["candidates"][0]["content"]["parts"]).strip()


def offered(key: str, *, timeout: float = 40) -> list[str]:
    """Every model this key may actually call, newest listing first.

    Used only when every name we know has already failed — a key on an
    unusual allowance may still have something we have never heard of.
    """
    url = ("https://generativelanguage.googleapis.com/v1beta/models"
           f"?key={key}&pageSize=200")
    with urllib.request.urlopen(url, timeout=timeout) as answer:
        listing = json.loads(answer.read().decode()).get("models", [])
    return [m["name"].split("/")[-1] for m in listing
            if "generateContent" in m.get("supportedGenerationMethods", [])]
