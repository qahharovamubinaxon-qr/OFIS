"""Hand a finished document to the worker over WhatsApp, in one tap.

WhatsApp has no open API: nothing may be sent on somebody's behalf without
Meta's Business platform, a dedicated number and a verified account. What every
WhatsApp *does* answer to is a ``wa.me`` link — it opens the chat with that one
person, with the message already written. The operator taps send.

So the office's flow becomes: make the document → type the worker's number →
WhatsApp opens with the text and a download link ready. No attaching, no
searching for the file, no account to register.

The link itself is served by the Mini App server (:mod:`telegram_webapp`), which
is already reachable from outside through the tunnel. It carries a one-use
random token and **expires**, because what is behind it is a migrant's own
paperwork and must not stay on the internet after the day's work.
"""

from __future__ import annotations

import urllib.parse

#: Country codes the office actually dials, longest first so «998» is tried
#: before «9».
_KNOWN = ("998", "992", "996", "7")

#: How long a shared link stays alive. A working day and a night: long enough
#: for a worker to open it after his shift, short enough that a link found later
#: is already dead.
LINK_HOURS = 24


def normalize_phone(raw: str) -> str:
    """Digits only, in the international form ``wa.me`` wants.

    The office writes numbers every way there is: ``+7 903 123-45-67``,
    ``8(903)1234567``, ``903 123 45 67``. Russian numbers are dialled locally
    with a leading 8, which is NOT part of the number — sent as-is, WhatsApp
    opens a chat with nobody.

    Returns ``""`` when what was typed cannot be a phone number, so the caller
    can say so instead of opening an empty chat.
    """
    digits = "".join(c for c in (raw or "") if c.isdigit())
    if not digits:
        return ""
    # a Russian mobile typed the local way: 8 903… → 7 903…
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if any(digits.startswith(code) for code in _KNOWN) and 9 <= len(digits) <= 15:
        return digits
    # a bare mobile with no country code — 9 digits in UZ, 10 in RU
    if len(digits) == 9:
        return "998" + digits
    if len(digits) == 10:
        return "7" + digits
    return digits if 9 <= len(digits) <= 15 else ""


def message(name: str, links: list[str], office: str = "") -> str:
    """What the worker reads. Short — it is read on a phone, in a queue."""
    lines = []
    who = " ".join((name or "").split())
    lines.append(f"Здравствуйте, {who}!" if who else "Здравствуйте!")
    lines.append("Ваши документы готовы:")
    lines.extend(links)
    if office:
        lines.append(office)
    lines.append(f"Ссылка действует {LINK_HOURS} часа.")
    return "\n".join(lines)


def wa_link(phone: str, text: str) -> str:
    """``https://wa.me/<number>?text=…`` — opens that chat, message written.

    Returns ``""`` for a number that cannot be dialled, rather than a link that
    opens WhatsApp on nothing.
    """
    number = normalize_phone(phone)
    if not number:
        return ""
    return f"https://wa.me/{number}?text={urllib.parse.quote(text or '')}"
