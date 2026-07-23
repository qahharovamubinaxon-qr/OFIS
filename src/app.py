"""Composition root.

The one place that knows how everything is wired: it builds the DI container,
runs migrations, and shows the main window. Nothing else constructs its own
dependencies — they are injected. This keeps every other module testable in
isolation (ARCHITECTURE.md §9).
"""

from __future__ import annotations

import sys

from src.common.di import Container
from src.common.errors import OfisError
from src.common.logging import configure_logging, get_logger
from src.config import paths
from src.config.settings_service import SettingsService
from src.database.connection import Database
from src.database.repositories.settings_repo import SettingsRepository

log = get_logger(__name__)


def build_container() -> Container:
    """Wire the object graph. Pure of Qt so it can be exercised in unit tests."""
    container = Container()

    db = Database(paths.database_path())
    db.migrate()
    container.register_instance(Database, db)

    settings_repo = SettingsRepository(db)
    container.register_instance(SettingsRepository, settings_repo)

    settings = SettingsService(settings_repo)
    container.register_instance(SettingsService, settings)

    return container


def main() -> int:
    configure_logging()
    log.info("Starting OFIS")

    try:
        container = build_container()
    except OfisError as exc:
        log.critical("Startup failed: %s", exc.message, extra={"context": exc.context})
        return 1

    # Import Qt only inside main so headless tests can build the container
    # without a display.
    from PySide6.QtWidgets import QApplication

    from src.ui.i18n import Translator
    from src.ui.main_window import MainWindow
    from src.ui.theme import apply_theme

    settings = container.resolve(SettingsService)

    app = QApplication(sys.argv)
    app.setApplicationName("OFIS")
    apply_theme(app, settings.theme)

    translator = Translator(settings.language)
    window = MainWindow(settings, translator)
    window.show()

    log.info("UI ready (theme=%s, language=%s)", settings.theme, settings.language)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
