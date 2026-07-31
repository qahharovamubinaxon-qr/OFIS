"""A free public https address for the Mini App, via Cloudflare Quick Tunnel.

Telegram opens a Mini App button only over **https**. The Mini App server
inside this program speaks plain http on the office LAN, so on its own it can
be reached from the phone's browser but never from inside Telegram.

``cloudflared tunnel --url http://localhost:<port>`` closes that gap: Cloudflare
hands out a ``https://….trycloudflare.com`` address and forwards it to this
computer. It is free, needs no account, no card and no domain — the one cost is
that the address is **new every time the tunnel starts**, which is why this
service writes it into settings itself. The operator never copies a URL.

The tunnel is an outward-facing door, so it is off unless switched on, and it
only ever forwards to the Mini App port — which refuses every request that does
not carry the operator's password or a signed Telegram ``initData``.

No third-party dependency: ``cloudflared`` is a single executable, and this is
a subprocess whose output is read for the address.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Callable

from src.common.logging import get_logger

log = get_logger(__name__)

KEY_TUNNEL = "tg.tunnel_enabled"

#: Where Windows installers put it when it is not on PATH.
_LIKELY = (
    r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
    r"C:\Program Files\cloudflared\cloudflared.exe",
)

_URL = re.compile(r"https://[a-z0-9][a-z0-9.-]*\.trycloudflare\.com")

#: How long to wait for the address before giving up on this attempt.
_WAIT_SECONDS = 40.0


def cloudflared() -> str:
    """Full path to ``cloudflared``, or ``""`` when it is not installed."""
    found = shutil.which("cloudflared")
    if found:
        return found
    from pathlib import Path

    for candidate in _LIKELY:
        if Path(candidate).exists():
            return candidate
    return ""


class TunnelService:
    """Owns the ``cloudflared`` process. ``start()`` is a no-op when off."""

    def __init__(self, settings) -> None:
        self._settings = settings
        self._proc: subprocess.Popen | None = None
        self._url = ""
        self._found = threading.Event()

    # -- state ---------------------------------------------------------
    def enabled(self) -> bool:
        return str(self._settings.get(KEY_TUNNEL, "0")) in ("1", "true", "True")

    def url(self) -> str:
        """The public address, or ``""`` until the tunnel has announced one."""
        return self._url

    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    # -- lifecycle -----------------------------------------------------
    def start(self, port: int, on_url: Callable[[str], None] | None = None) -> bool:
        """Open the tunnel. Returns whether the process was launched.

        The address arrives asynchronously — cloudflared has to reach
        Cloudflare first — so ``on_url`` is called from the reader thread once
        it is known, rather than making the window wait for it.
        """
        if not self.enabled() or self.running():
            return False
        exe = cloudflared()
        if not exe:
            log.info("Tunnel not started — cloudflared is not installed")
            return False

        self._url = ""
        self._found.clear()
        # no console window: this runs behind a desktop app, not in a terminal
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self._proc = subprocess.Popen(
                [exe, "tunnel", "--no-autoupdate", "--url",
                 f"http://localhost:{port}"],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace",
                # NOT the program's own folder. A child inherits the parent's
                # working directory, and Windows will not let anybody delete a
                # directory that is some process's current one — so a
                # cloudflared left behind after a hard kill made the next
                # `update.bat` fail with «dist\\OFIS занят другим процессом».
                cwd=tempfile.gettempdir(),
                creationflags=flags)
        except OSError as exc:
            log.warning("Tunnel failed to start: %s", exc)
            self._proc = None
            return False

        threading.Thread(target=self._read, args=(on_url,), daemon=True,
                         name="ofis-tunnel").start()
        return True

    def wait(self, timeout: float = _WAIT_SECONDS) -> str:
        """Block until the address is known (or the wait runs out)."""
        self._found.wait(timeout)
        return self._url

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        self._url = ""
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    # -- internals -----------------------------------------------------
    def _read(self, on_url: Callable[[str], None] | None) -> None:
        """Watch cloudflared's log for the address it was given."""
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        for line in proc.stderr:
            if self._url:
                continue                      # keep draining so it never blocks
            match = _URL.search(line)
            if not match:
                continue
            self._url = match.group(0)
            log.info("Tunnel open at %s", self._url)
            if on_url is not None:
                try:
                    on_url(self._url)
                except Exception as exc:      # noqa: BLE001
                    log.warning("tunnel callback failed: %s", exc)
            # set LAST: whoever is waiting is waiting for the address to be
            # saved, not merely parsed. The other way round the settings table
            # still held the previous run's address when they looked.
            self._found.set()
