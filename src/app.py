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
from src.database.repositories.company_repo import CompanyRepository
from src.database.repositories.settings_repo import SettingsRepository
from src.domain.company import Company
from src.domain.enums import EmployerType
from src.services.company_service import CompanyService
from src.services.generation_service import GenerationService

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

    company_repo = CompanyRepository(db)
    container.register_instance(CompanyRepository, company_repo)

    company_service = CompanyService(company_repo)
    container.register_instance(CompanyService, company_service)

    container.register_instance(GenerationService, GenerationService(settings))

    # AI / OCR — Gemini keyed from settings (or GEMINI_API_KEY env); the OCR
    # service degrades to "use manual fill" when no key is present.
    from src.ai.gemini_provider import GeminiProvider
    from src.ai.manager import AiManager
    from src.ocr.service import OcrService

    gemini = GeminiProvider(api_key=str(settings.get("ai.gemini_key", "") or ""))
    ai_manager = AiManager([gemini])
    container.register_instance(AiManager, ai_manager)
    container.register_instance(OcrService, OcrService(ai_manager))

    _seed_default_company(company_service)

    return container


def _seed_default_company(companies: CompanyService) -> None:
    """First-run seed: the ИП ГОРДИЕНКО company whose blank МВД form ships in
    templates/. Idempotent — skipped once any company exists."""
    if companies.count() > 0:
        return
    template = paths.templates_dir() / "mvd_prilozhenie_7" / "template.pdf"
    if not template.exists():
        return
    try:
        companies.create(
            Company(
                name="ИП ГОРДИЕНКО АЛЕКСЕЙ АНАТОЛЬЕВИЧ",
                internal_code="GORDIENKO",
                employer_type=EmployerType.IP,
                okved="46.21.19",
                ogrn="315080100000587",
                inn="080100230802",
                address_index="111677",
                address_text="МОСКВА УЛ. ВЕРТОЛЁТЧИКОВ Д4 К2",
                director_fio="ГОРДИЕНКО АЛЕКСЕЙ АНАТОЛЬЕВИЧ",
                template_path=template,
            )
        )
        log.info("Seeded default company ГОРДИЕНКО")
    except OfisError as exc:
        log.warning("Seed skipped: %s", exc.message)


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
    window = MainWindow(container, translator)
    window.show()

    log.info("UI ready (theme=%s, language=%s)", settings.theme, settings.language)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
