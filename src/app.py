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
from src.database.repositories.generated_repo import GeneratedRepository
from src.database.repositories.insurance_template_repo import (
    InsuranceTemplateRepository,
)
from src.database.repositories.profession_repo import ProfessionRepository
from src.database.repositories.registration_address_repo import RegistrationAddressRepository
from src.database.repositories.settings_repo import SettingsRepository
from src.database.repositories.trud_firm_repo import TrudFirmRepository
from src.domain.company import Company
from src.domain.enums import EmployerType
from src.domain.registration_address import RegistrationAddress
from src.services.company_service import CompanyService
from src.services.generation_service import GenerationService
from src.services.profession_service import ProfessionService
from src.services.registration_address_service import RegistrationAddressService
from src.services.registration_service import RegistrationService
from src.services.svera_service import SveraService
from src.services.trud_service import TrudFirmService, TrudService

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

    generated_repo = GeneratedRepository(db)
    container.register_instance(GeneratedRepository, generated_repo)

    container.register_instance(GenerationService, GenerationService(settings, generated_repo))

    container.register_instance(InsuranceTemplateRepository,
                               InsuranceTemplateRepository(db))

    reg_addr_repo = RegistrationAddressRepository(db)
    container.register_instance(RegistrationAddressRepository, reg_addr_repo)
    reg_addr_service = RegistrationAddressService(reg_addr_repo)
    container.register_instance(RegistrationAddressService, reg_addr_service)
    container.register_instance(RegistrationService, RegistrationService())

    profession_repo = ProfessionRepository(db)
    container.register_instance(ProfessionRepository, profession_repo)
    profession_service = ProfessionService(profession_repo)
    container.register_instance(ProfessionService, profession_service)
    container.register_instance(SveraService, SveraService(settings))

    trud_firm_repo = TrudFirmRepository(db)
    container.register_instance(TrudFirmRepository, trud_firm_repo)
    container.register_instance(TrudFirmService, TrudFirmService(trud_firm_repo))
    container.register_instance(TrudService, TrudService())

    # AI / OCR — a chain of three, tried in this order, each keyed from settings
    # (or its own env var). Mistral does document OCR, so it reads small print
    # and the machine-readable zone best; Groq answers fastest; Gemini stays as
    # the backstop the office has been using all along. A provider with no key
    # is skipped, and the service degrades to «use manual fill» only when none
    # of the three has one.
    from src.ai.gemini_provider import GeminiProvider
    from src.ai.groq_provider import GroqProvider
    from src.ai.manager import AiManager
    from src.ai.mistral_provider import MistralProvider
    from src.ocr.service import OcrService

    def _key_getter(name: str):
        return lambda: str(settings.get(f"ai.{name}_key", "") or "")

    ai_manager = AiManager([
        MistralProvider(key_getter=_key_getter("mistral")),
        GroqProvider(key_getter=_key_getter("groq")),
        GeminiProvider(key_getter=_key_getter("gemini")),
    ])
    container.register_instance(AiManager, ai_manager)
    container.register_instance(OcrService, OcrService(ai_manager))

    _seed_stroyinvest(TrudFirmService(trud_firm_repo))
    _seed_default_company(company_service)
    _seed_default_address(reg_addr_service)
    _seed_default_hostel(reg_addr_service)
    profession_service.seed_defaults()

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


def _seed_stroyinvest(firms: TrudFirmService) -> None:
    """Bundle-seed ООО «СТРОЙИНВЕСТ» with its 3 templates. Idempotent."""
    if firms._repo.by_internal_code("stroyinvest"):
        return
    src = paths.templates_dir() / "trud_seed_stroyinvest"
    trud, uved, hod = src / "trudovoy.docx", src / "uvedomlenie.pdf", src / "hodataystvo.docx"
    if not (trud.exists() and uved.exists()):
        return
    try:
        firms.create('ООО "СТРОЙИНВЕСТ"', "stroyinvest", trud, uved,
                     hod if hod.exists() else None)
        log.info("Seeded trud firm СТРОЙИНВЕСТ")
    except OfisError as exc:
        log.warning("Stroyinvest seed skipped: %s", exc.message)


def _seed_default_address(addresses: RegistrationAddressService) -> None:
    """First-run seed: the sample registration template that ships in
    templates/registration/ (Г МОСКВА 5-Я ПАРКОВАЯ 55, host ПОПОВ). Idempotent."""
    if addresses.count() > 0:
        return
    template = paths.templates_dir() / "registration" / "template.pdf"
    if not template.exists():
        return
    try:
        addresses.create(
            RegistrationAddress(
                label="5-Я ПАРКОВАЯ 55-55",
                internal_code="parkovaya55",
                address_text="Г МОСКВА, 5-Я ПАРКОВАЯ, ДОМ 55, КОРПУС 1, КВ. 55",
                host_fio="ПОПОВ ВЛАДИМИР ГЕННАДЬЕВИЧ",
                template_path=template,
            )
        )
        log.info("Seeded default registration address ПАРКОВАЯ")
    except OfisError as exc:
        log.warning("Registration seed skipped: %s", exc.message)


def _seed_default_hostel(addresses: RegistrationAddressService) -> None:
    """First-run seed: the partner hostel on ЛУЖСКАЯ (ИП ДЯГИЛЕВА), built from
    the bundled hostel blank. Idempotent."""
    if addresses._repo.by_internal_code("luzhskaya10"):
        return
    if not (paths.templates_dir() / "hostel_blank" / "blank.pdf").exists():
        return
    try:
        addresses.create_hostel(
            RegistrationAddress(
                label="ХОСТЕЛ ЛУЖСКАЯ 10",
                internal_code="luzhskaya10",
                address_text="САНКТ-ПЕТЕРБУРГ Г, ЛУЖСКАЯ УЛ, ДОМ 10, КОРПУС 1, ЛИТЕРА В",
                host_fio="ДЯГИЛЕВА ЮЛИЯ ГЕННАДЬЕВНА",
                kind="hostel",
                oblast="САНКТ-ПЕТЕРБУРГ Г",
                ulitsa="ЛУЖСКАЯ УЛ",
                dom="10", korpus="1", stroenie="В",
                organization_name="ИНДИВИДУАЛЬНЫЙ ПРЕДПРИНИМАТЕЛЬ ДЯГИЛЕВ",
                inn="780401098145",
                template_path=paths.templates_dir() / "hostel_blank" / "blank.pdf",
            ),
            None,
        )
        log.info("Seeded hostel ЛУЖСКАЯ 10")
    except OfisError as exc:
        log.warning("Hostel seed skipped: %s", exc.message)


def main() -> int:
    configure_logging()
    log.info("Starting OFIS")

    # A staged backup restore must land before the DB is opened.
    from src.services.backup_service import BackupService

    try:
        if BackupService.apply_pending_restore():
            log.info("Pending backup restore applied")
    except Exception as exc:  # noqa: BLE001 - a bad ZIP must not brick startup
        log.error("Pending restore failed: %s", exc)

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
    icon_file = paths.resources_dir() / "icons" / "ofis_256.png"
    if icon_file.exists():
        from PySide6.QtGui import QIcon

        app.setWindowIcon(QIcon(str(icon_file)))
    apply_theme(app, settings.theme)

    translator = Translator(settings.language)
    window = MainWindow(container, translator)
    window.show()

    # Telegram bot (phone remote-control) — silent no-op without a token.
    from src.controllers.telegram_bot import TelegramBot

    bot = TelegramBot(container)
    try:
        bot.start()
    except Exception as exc:  # noqa: BLE001 - bot must never block the UI
        log.error("Telegram bot failed to start: %s", exc)
    window._telegram_bot = bot  # keep alive for the app's lifetime

    # Mini App — the same modules as a phone page; off unless switched on.
    from src.controllers.telegram_webapp import WebAppServer

    webapp = WebAppServer(container)
    try:
        url = webapp.start()
        if url:
            log.info("Mini App reachable at %s", url)
    except Exception as exc:  # noqa: BLE001 - must never block the UI
        log.error("Mini App failed to start: %s", exc)
    window._webapp = webapp

    # Warm up the background-removal model: first install downloads it here,
    # in the background, so the first photo never waits for the network.
    import threading as _threading

    from src.services import bg_segment

    _threading.Thread(target=lambda: bg_segment.model_path(download=True),
                      daemon=True, name="ofis-model-warmup").start()

    log.info("UI ready (theme=%s, language=%s)", settings.theme, settings.language)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
