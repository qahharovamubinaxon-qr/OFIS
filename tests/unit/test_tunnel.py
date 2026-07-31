"""The free public address for the Mini App.

Nothing here launches ``cloudflared`` — the process is faked, so the tests are
about the parts that decide whether to open a door and what to do with the
address that comes back.
"""

from __future__ import annotations

import tempfile

import pytest
from src.config import paths
from src.services.tunnel_service import KEY_TUNNEL, TunnelService

#: What cloudflared actually prints when a quick tunnel comes up.
BANNER = """\
2026-07-31T09:00:00Z INF Requesting new quick Tunnel on trycloudflare.com...
2026-07-31T09:00:02Z INF +----------------------------------------------+
2026-07-31T09:00:02Z INF |  Your quick Tunnel has been created!          |
2026-07-31T09:00:02Z INF |  https://plain-oven-shell-motor.trycloudflare.com |
2026-07-31T09:00:02Z INF +----------------------------------------------+
2026-07-31T09:00:03Z INF Registered tunnel connection connIndex=0
"""


class _FakeProc:
    """Stands in for the cloudflared process: some log, then it is done."""

    def __init__(self, text: str = BANNER) -> None:
        self.stderr = iter(text.splitlines(keepends=True))
        self.terminated = False

    def poll(self):
        return None

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0


@pytest.fixture()
def settings(monkeypatch):
    sandbox = tempfile.mkdtemp()
    monkeypatch.setenv("XDG_DATA_HOME", sandbox)
    monkeypatch.setenv("LOCALAPPDATA", sandbox)
    paths.data_dir.cache_clear()
    from src.app import build_container
    from src.config.settings_service import SettingsService

    yield build_container().resolve(SettingsService)
    paths.data_dir.cache_clear()


def test_the_address_is_read_out_of_the_log(settings) -> None:
    seen: list[str] = []
    service = TunnelService(settings)
    service._proc = _FakeProc()
    service._read(seen.append)

    assert service.url() == "https://plain-oven-shell-motor.trycloudflare.com"
    assert seen == [service.url()], "the address never reached the caller"


def test_a_log_with_no_address_leaves_it_empty(settings) -> None:
    service = TunnelService(settings)
    service._proc = _FakeProc("INF failed to connect\nINF retrying\n")
    service._read(None)
    assert service.url() == ""


def test_a_broken_callback_does_not_kill_the_reader(settings) -> None:
    """The address still has to be remembered even if saving it blows up."""
    def explode(_url: str) -> None:
        raise RuntimeError("settings table locked")

    service = TunnelService(settings)
    service._proc = _FakeProc()
    service._read(explode)
    assert service.url().endswith(".trycloudflare.com")


def test_the_door_stays_shut_unless_it_is_switched_on(settings, monkeypatch) -> None:
    """A public tunnel is opt-in — never a side effect of starting the app."""
    launched: list[list[str]] = []
    monkeypatch.setattr("src.services.tunnel_service.cloudflared", lambda: "cf.exe")
    monkeypatch.setattr("subprocess.Popen",
                        lambda cmd, **kw: launched.append(cmd) or _FakeProc())

    service = TunnelService(settings)
    assert not service.enabled()
    assert service.start(8770) is False
    assert not launched

    settings.set(KEY_TUNNEL, "1")
    assert service.enabled()
    assert service.start(8770) is True
    assert launched and "--url" in launched[0]
    assert "http://localhost:8770" in launched[0]


def test_nothing_is_launched_when_cloudflared_is_missing(settings, monkeypatch) -> None:
    monkeypatch.setattr("src.services.tunnel_service.cloudflared", lambda: "")
    settings.set(KEY_TUNNEL, "1")

    service = TunnelService(settings)
    assert service.start(8770) is False
    assert service.url() == ""


def test_stop_closes_the_process_and_forgets_the_address(settings) -> None:
    """cloudflared is a subprocess, not a daemon thread — it must be told."""
    service = TunnelService(settings)
    proc = _FakeProc()
    service._proc = proc
    service._url = "https://x.trycloudflare.com"

    service.stop()

    assert proc.terminated, "the tunnel would have outlived the program"
    assert service.url() == ""
    assert not service.running()


def test_waiting_for_the_address_means_waiting_for_it_to_be_saved(settings) -> None:
    """``wait()`` must not return before the caller's callback has finished.

    It used to set the event first, so a caller that waited and then read the
    setting got the previous run's address — or nothing at all on the very
    first start.
    """
    order: list[str] = []
    service = TunnelService(settings)
    service._proc = _FakeProc()

    def save(url: str) -> None:
        assert not service._found.is_set(), "wait() was released too early"
        order.append("saved")

    service._read(save)
    assert order == ["saved"]
    assert service._found.is_set()
    assert service.wait(0) == service.url()
