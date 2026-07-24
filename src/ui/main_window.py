"""The application shell: sidebar navigation + stacked content + status bar.

Phase 1 wires the real chrome (navigation, theming, i18n, status bar) with every
screen shown as a themed placeholder. Each subsequent phase swaps one placeholder
for its real view without touching this shell — the navigation contract stays put.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from src.common.di import Container
from src.config import constants
from src.config.settings_service import SettingsService
from src.controllers.process_controller import ProcessController
from src.database.repositories.generated_repo import GeneratedRepository
from src.ocr.service import OcrService
from src.services.company_service import CompanyService
from src.services.generation_service import GenerationService
from src.services.profession_service import ProfessionService
from src.services.registration_address_service import RegistrationAddressService
from src.services.registration_service import RegistrationService
from src.services.svera_service import SveraService
from src.ui.i18n import Translator
from src.ui.views.archive_view import ArchiveView
from src.ui.views.companies_view import CompaniesView
from src.ui.views.dashboard_view import DashboardView
from src.ui.views.process_view import ProcessView
from src.ui.views.registration_view import RegistrationView
from src.ui.views.settings_view import SettingsView
from src.ui.views.svera_view import SveraView

_NAV = [
    ("nav.dashboard", "Dashboard", "Today's activity, totals and alerts"),
    ("nav.process", "Process Employee", "Upload documents → OCR → verify → PDF"),
    ("nav.registration", "Registration", "Уведомление о прибытии → PDF"),
    ("nav.svera", "СФЕРА", "Удостоверение + Протокол обучения → PDF"),
    ("nav.companies", "Companies", "Templates, logos and company data"),
    ("nav.archive", "Archive", "Every generated package, by year and company"),
    ("nav.search", "Search", "Find an employee by passport, patent or name"),
    ("nav.settings", "Settings", "Language, theme, AI providers, folders"),
]


class MainWindow(QMainWindow):
    def __init__(self, container: Container, translator: Translator) -> None:
        super().__init__()
        self._container = container
        self._settings = container.resolve(SettingsService)
        self._tr = translator

        self.setWindowTitle(constants.APP_NAME)
        self.resize(1180, 760)
        self.setMinimumSize(960, 640)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._nav_list = QListWidget()
        self._stack = QStackedWidget()

        root.addWidget(self._build_sidebar())
        root.addWidget(self._stack, stretch=1)
        self.setCentralWidget(central)

        for key, title, subtitle in _NAV:
            self._nav_list.addItem(self._tr.tr(key, title))
            self._stack.addWidget(self._make_view(key, title, subtitle))

        self._nav_list.currentRowChanged.connect(self._on_nav)
        self._nav_list.setCurrentRow(1)  # open on Process Employee

        self._build_status_bar()

    def _make_view(self, key: str, title: str, subtitle: str) -> QWidget:
        if key == "nav.dashboard":
            return DashboardView(
                self._container.resolve(GeneratedRepository),
                self._container.resolve(CompanyService),
                self._container.resolve(GenerationService),
            )
        if key == "nav.process":
            controller = ProcessController(
                self._container.resolve(CompanyService),
                self._container.resolve(OcrService),
                self._container.resolve(GenerationService),
            )
            return ProcessView(controller, self._tr)
        if key == "nav.registration":
            from src.controllers.registration_controller import RegistrationController

            reg_addresses = self._container.resolve(RegistrationAddressService)
            reg_controller = RegistrationController(
                reg_addresses,
                self._container.resolve(OcrService),
                self._container.resolve(RegistrationService),
            )
            return RegistrationView(reg_controller, reg_addresses)
        if key == "nav.svera":
            from src.controllers.svera_controller import SveraController

            svera_controller = SveraController(
                self._container.resolve(ProfessionService),
                self._container.resolve(OcrService),
                self._container.resolve(SveraService),
            )
            return SveraView(svera_controller)
        if key == "nav.companies":
            return CompaniesView(self._container.resolve(CompanyService))
        if key == "nav.archive":
            return ArchiveView(self._container.resolve(GeneratedRepository), "Arxiv / Архив")
        if key == "nav.search":
            return ArchiveView(self._container.resolve(GeneratedRepository), "Qidiruv / Поиск")
        if key == "nav.settings":
            return SettingsView(self._settings, on_theme_change=self._apply_theme)
        return QWidget()

    def _on_nav(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        view = self._stack.currentWidget()
        refresh = getattr(view, "refresh", None)
        if callable(refresh):
            refresh()

    def _apply_theme(self, theme: str) -> None:
        from PySide6.QtWidgets import QApplication

        from src.ui.theme import apply_theme

        app = QApplication.instance()
        if app is not None:
            apply_theme(app, theme)  # type: ignore[arg-type]

    def _build_sidebar(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("sidebar")
        panel.setFixedWidth(232)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        brand = QLabel(constants.APP_SHORT)
        brand.setObjectName("brand")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(brand)

        self._nav_list.setObjectName("navList")
        self._nav_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(self._nav_list, stretch=1)
        return panel

    def _build_status_bar(self) -> None:
        bar = QStatusBar()
        self.setStatusBar(bar)
        provider = self._settings.get_str("ai.primary_provider").capitalize()
        bar.addWidget(QLabel(f"  {self._tr.tr('status.ready', 'Ready')}"))
        bar.addPermanentWidget(QLabel(f"AI: {provider}"))
        bar.addPermanentWidget(QLabel(f"v{constants.APP_VERSION}  "))
