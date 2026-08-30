"""Run ONLY the Telegram bot — no window, no desktop UI.

The bot normally lives as a daemon thread inside the desktop app, so it
answers only while OFIS is open on the screen. This entry point runs the very
same bot on its own: it builds the same object graph the desktop app builds,
starts the bot (and the Mini App the «WhatsApp'га юбор» button needs), and
then keeps the process alive doing nothing but letting the bot's threads work.

It shares the office's own data, because it resolves everything through the
same paths the desktop app uses — the same AppData database (companies,
addresses, the ДМС number block), the same settings (the bot token and the AI
keys), and the same uploaded blanks. So a document the bot makes here is
numbered and stamped exactly as one made from the desktop program.

Leave it running — a startup shortcut, a scheduled task, or simply a minimised
console — and the bot answers around the clock without the desktop program
open. It is also the shape the bot takes on a small always-on machine or a
cloud server: the same file, run the same way.

    py -3.12 -m src.bot_main
"""

from __future__ import annotations

import contextlib
import signal
import threading

from src.common.logging import configure_logging, get_logger

log = get_logger(__name__)


def run() -> int:
    """Start the bot and block until interrupted. Returns a process exit code."""
    configure_logging()
    from src.app import build_container
    from src.config.settings_service import SettingsService
    from src.controllers.telegram_bot import KEY_WEBAPP, TelegramBot
    from src.controllers.telegram_webapp import WebAppServer
    from src.services.tunnel_service import TunnelService

    log.info("OFIS bot (headless) — старт")
    container = build_container()
    settings = container.resolve(SettingsService)

    bot = TelegramBot(container)
    if not bot.start():
        # start() logs the reason (no token). Without one there is nothing to
        # run, and a process that stays up doing nothing only misleads.
        log.error("Telegram токени йўқ — Sozlamalar → Telegram бўлимига "
                  "киритинг. Бот ишга тушмади.")
        return 1

    # The Mini App and its public address — what «WhatsApp'га юбор» needs.
    # Both are best-effort: the bot still answers text and files without them.
    webapp = WebAppServer(container)
    tunnel = TunnelService(settings)
    try:
        url = webapp.start()
        bot.webapp = webapp
        if url:
            tunnel.start(webapp.port(),
                         lambda public: settings.set(KEY_WEBAPP, public))
            log.info("Mini App очиқ: %s", url)
    except Exception as exc:  # noqa: BLE001 - never let the extras stop the bot
        log.error("Mini App/tunnel ишламади (бот барибир ишлайди): %s", exc)

    # Tell the desktop app (if it is opened later) that the token is taken, so
    # it does not start a second bot and collide on Telegram's 409.
    from src.common import bot_lock
    bot_lock.acquire()

    log.info("Бот ишлаяпти. Тўхтатиш: Ctrl+C.")

    # Block here until a stop is asked for. The bot and the Mini App live on
    # their own threads/process; this main thread only heartbeats the lock and
    # waits.
    done = threading.Event()

    def _shutdown(*_args) -> None:
        log.info("Тўхтатилаяпти…")
        done.set()

    signal.signal(signal.SIGINT, _shutdown)
    with contextlib.suppress(ValueError, AttributeError):
        signal.signal(signal.SIGTERM, _shutdown)  # SIGTERM is absent on Windows

    try:
        while not done.wait(bot_lock.HEARTBEAT_S):
            bot_lock.touch()
    finally:
        try:
            bot.stop()
            tunnel.stop()
        finally:
            bot_lock.release()
    log.info("Бот тўхтади.")
    return 0


def main() -> int:
    try:
        return run()
    except KeyboardInterrupt:
        return 0
    except Exception:  # noqa: BLE001 - a crash must be logged, not silent
        log.exception("Бот кутилмаганда тўхтади")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
