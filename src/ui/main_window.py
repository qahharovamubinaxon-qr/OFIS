"""The application shell: sidebar navigation + stacked content + status bar.

Phase 1 wires the real chrome (navigation, theming, i18n, status bar) with every
screen shown as a themed placeholder. Each subsequent phase swaps one placeholder
for its real view without touching this shell — the navigation contract stays put.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
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
from src.services.trud_service import TrudFirmService, TrudService
from src.ui.i18n import Translator
from src.ui.views.archive_view import ArchiveView
from src.ui.views.companies_view import CompaniesView
from src.ui.views.dashboard_view import DashboardView
from src.ui.views.photo_view import PhotoView
from src.ui.views.process_view import ProcessView
from src.ui.views.registration_view import RegistrationView
from src.ui.views.settings_view import SettingsView
from src.ui.views.svera_view import SveraView
from src.ui.views.trud_view import TrudView

# (section header | None, key, default title, subtitle, icon)
_NAV = [
    (None, "nav.dashboard", "Dashboard", "Today's activity, totals and alerts", "📊"),
    ("МИГРАЦИЯ", "nav.process", "Process Employee",
     "Upload documents → OCR → verify → PDF", "🛂"),
    (None, "nav.registration", "Registration", "Уведомление о прибытии → PDF", "🏠"),
    (None, "nav.hostel", "ХОСТЕЛ", "Хостел уведомление о прибытии → PDF", "🛏️"),
    (None, "nav.trud", "Трудовой-Уведомления", "Договор + Уведомление → 2 PDF", "📑"),
    (None, "nav.dms", "ДМС", "Полис «ДМС-Трудовой» → PDF", "🏥"),
    (None, "nav.strahovka", "СТРАХОВКА МАШИНАГА",
     "ОСАГО полиси — машина + ҳайдовчилар → Word/PDF", "🚗"),
    (None, "nav.inn", "ИНН", "Ишчининг ИНН рақами варағи → PDF", "🔢"),
    (None, "nav.beydjik", "БЕЙДЖИК", "Ишчининг бейджиги (77 / 50) → PDF", "🪪"),
    (None, "nav.patent", "ПАТЕНТ",
     "Патент картаси (77 / 50) — олд + орқа → PDF", "🩷"),
    (None, "nav.chek", "ЧЕК", "Премия чеки — патент + сумма → PDF", "🧾"),
    (None, "nav.razreshenie", "РАЗРЕШЕНИЯ",
     "Ишчининг рухсатнома картаси — олд + орқа → PDF", "🟩"),
    (None, "nav.ppu", "ППУ",
     "Регистрациядан ППУ жуфтлиги — олд + орқа → расм", "🧾"),
    (None, "nav.snils", "СНИЛС",
     "Ишчининг СНИЛС номери варағи → PDF", "🔖"),
    (None, "nav.svera", "СФЕРА", "Удостоверение + Протокол обучения → PDF", "🎓"),
    (None, "nav.sertifikat", "СЕРТИФИКАТ",
     "Рус тили сертификати (УЦ «СФЕРА») → PDF", "📜"),
    ("НОТАРИУС", "nav.dover", "Доверенность", "Нотариал ҳужжат Word + PDF", "📜"),
    (None, "nav.perevod", "ПЕРЕВОД", "Нотариал таржима — рус тилига", "🌐"),
    ("ҲУЖЖАТ", "nav.umumiy", "УМУМИЙ", "Ҳужжатни янги ишчига мослаш", "♻️"),
    (None, "nav.template", "ЎЗ ШАБЛОНИМ",
     "Ўз PDF/Word шаблонингизни программа ўзи тушунади", "🧩"),
    (None, "nav.photo", "РАСМ-ФОТО", "Документ учун 3×4 расм тайёрлаш", "📷"),
    (None, "nav.jpg2pdf", "JPG→PDF", "Расмлардан PDF йиғиш", "🖼️"),
    (None, "nav.summa", "СУММА-ДАТА", "Сумма ва санани пропись қилиш", "🔢"),
    ("БАЗА", "nav.companies", "Companies", "Templates, logos and company data", "🏢"),
    (None, "nav.archive", "Archive",
     "Every generated package, by year and company", "🗂️"),
    (None, "nav.search", "Search",
     "Find an employee by passport, patent or name", "🔍"),
    (None, "nav.settings", "Settings",
     "Language, theme, AI providers, folders", "⚙️"),
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

        # Section headers are non-selectable list rows, so the nav reads as
        # grouped sections while the stack still maps 1:1 to real entries.
        self._row_to_page: dict[int, int] = {}
        #: which section owns each row, so the open one can colour the window
        self._row_to_key: dict[int, str] = {}
        self._theme = str(getattr(self._settings, "theme", constants.DEFAULT_THEME))
        self._nav_key = "nav.dashboard"
        for section, key, title, subtitle, icon in _NAV:
            if section:
                self._nav_list.addItem(self._section_item(section))
            item = QListWidgetItem(f"{icon}   {self._tr.tr(key, title)}")
            self._nav_list.addItem(item)
            self._row_to_page[self._nav_list.count() - 1] = self._stack.count()
            self._row_to_key[self._nav_list.count() - 1] = key
            self._stack.addWidget(self._make_view(key, title, subtitle))

        self._nav_list.currentRowChanged.connect(self._on_nav)
        self._select_page(1)  # open on Process Employee

        self._build_status_bar()

        refresh_shortcut = QShortcut(QKeySequence("F5"), self)
        refresh_shortcut.activated.connect(self.reset_current_view)
        QShortcut(QKeySequence("Ctrl+R"), self).activated.connect(
            self.reset_current_view)

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
        if key == "nav.hostel":
            from src.controllers.hostel_controller import HostelController
            from src.services.hostel_service import HostelService
            from src.ui.views.hostel_view import HostelView

            return HostelView(HostelController(
                self._container.resolve(RegistrationAddressService),
                self._container.resolve(OcrService),
                HostelService(),
            ))
        if key == "nav.chek":
            from src.controllers.chek_controller import ChekController
            from src.ui.views.chek_view import ChekView

            return ChekView(ChekController(self._container.resolve(OcrService)))
        if key == "nav.svera":
            from src.controllers.svera_controller import SveraController

            svera_controller = SveraController(
                self._container.resolve(ProfessionService),
                self._container.resolve(OcrService),
                self._container.resolve(SveraService),
            )
            return SveraView(svera_controller)
        if key == "nav.trud":
            from src.controllers.trud_controller import TrudController

            trud_controller = TrudController(
                self._container.resolve(TrudFirmService),
                self._container.resolve(OcrService),
                self._container.resolve(TrudService),
            )
            return TrudView(trud_controller)
        if key == "nav.inn":
            from src.controllers.inn_controller import InnController
            from src.services.inn_service import InnService
            from src.ui.views.inn_view import InnView

            return InnView(InnController(
                self._container.resolve(OcrService), InnService()))
        if key == "nav.beydjik":
            from src.controllers.beydjik_controller import BeydjikController
            from src.services.beydjik_service import BeydjikService
            from src.ui.views.beydjik_view import BeydjikView

            return BeydjikView(BeydjikController(
                self._container.resolve(OcrService),
                BeydjikService(self._settings),
            ))
        if key == "nav.patent":
            from src.controllers.patent_controller import PatentController
            from src.services.patent_service import PatentService
            from src.ui.views.patent_view import PatentView

            return PatentView(PatentController(
                self._container.resolve(OcrService),
                PatentService(self._settings),
            ))
        if key == "nav.razreshenie":
            from src.controllers.razreshenie_controller import (
                RazreshenieController,
            )
            from src.services.razreshenie_service import RazreshenieService
            from src.ui.views.razreshenie_view import RazreshenieView

            return RazreshenieView(RazreshenieController(
                self._container.resolve(OcrService),
                RazreshenieService(self._settings),
            ))
        if key == "nav.snils":
            from src.controllers.snils_controller import SnilsController
            from src.services.snils_service import SnilsService
            from src.ui.views.snils_view import SnilsView

            return SnilsView(SnilsController(
                self._container.resolve(OcrService),
                SnilsService(self._settings),
            ))
        if key == "nav.ppu":
            from src.controllers.ppu_controller import PpuController
            from src.services.ppu_service import PpuService
            from src.ui.views.ppu_view import PpuView

            return PpuView(PpuController(
                self._container.resolve(OcrService),
                PpuService(self._settings),
            ))
        if key == "nav.sertifikat":
            from src.controllers.sertifikat_controller import (
                SertifikatController,
            )
            from src.services.sertifikat_service import SertifikatService
            from src.ui.views.sertifikat_view import SertifikatView

            return SertifikatView(SertifikatController(
                self._container.resolve(OcrService),
                SertifikatService(self._settings),
            ))
        if key == "nav.strahovka":
            from src.controllers.insurance_controller import InsuranceController
            from src.database.repositories.insurance_template_repo import (
                InsuranceTemplateRepository,
            )
            from src.services.insurance_service import (
                InsuranceService,
                InsuranceTemplateService,
            )
            from src.ui.views.insurance_view import InsuranceView

            return InsuranceView(InsuranceController(
                InsuranceTemplateService(
                    self._container.resolve(InsuranceTemplateRepository)),
                self._container.resolve(OcrService),
                InsuranceService(self._settings),
            ))
        if key == "nav.template":
            from src.controllers.template_controller import TemplateController
            from src.database.repositories.template_profile_repo import (
                TemplateProfileRepository,
            )
            from src.ui.views.template_view import TemplateView

            return TemplateView(TemplateController(
                self._container.resolve(TemplateProfileRepository),
                self._container.resolve(OcrService),
            ))
        if key == "nav.dms":
            from src.controllers.dms_controller import DmsController
            from src.services.dms_service import DmsService
            from src.ui.views.dms_view import DmsView

            return DmsView(DmsController(
                self._container.resolve(OcrService),
                DmsService(self._settings),
            ))
        if key == "nav.photo":
            from src.services.photo_service import PhotoService

            return PhotoView(PhotoService(
                key_getter=lambda: str(self._settings.get("ai.gemini_key", "") or "")
            ))
        if key == "nav.dover":
            from src.services.dover_service import DoverService
            from src.ui.views.dover_view import DoverView

            return DoverView(
                self._container.resolve(OcrService),
                DoverService(
                    key_getter=lambda: str(self._settings.get("ai.gemini_key", "") or ""),
                    settings=self._settings,
                ),
            )
        if key == "nav.umumiy":
            from src.services.umumiy_service import UmumiyService
            from src.services.umumiy_templates import UmumiyTemplateService
            from src.ui.views.umumiy_view import UmumiyView

            gemini = lambda: str(self._settings.get("ai.gemini_key", "") or "")  # noqa: E731
            return UmumiyView(
                self._container.resolve(OcrService),
                UmumiyService(key_getter=gemini),
                UmumiyTemplateService(key_getter=gemini),
            )
        if key == "nav.perevod":
            from src.controllers.ofis_modules import _perevod_cert
            from src.services.perevod_service import PerevodService
            from src.ui.views.perevod_view import PerevodView

            return PerevodView(PerevodService(
                key_getter=lambda: str(self._settings.get("ai.gemini_key", "") or ""),
                cert_getter=_perevod_cert(self._container)))
        if key == "nav.jpg2pdf":
            from src.ui.views.jpg2pdf_view import Jpg2PdfView

            return Jpg2PdfView()
        if key == "nav.summa":
            from src.ui.views.summa_view import SummaView

            return SummaView()
        if key == "nav.companies":
            return CompaniesView(self._container.resolve(CompanyService))
        if key == "nav.archive":
            return ArchiveView(self._container.resolve(GeneratedRepository), "Arxiv / Архив")
        if key == "nav.search":
            return ArchiveView(self._container.resolve(GeneratedRepository), "Qidiruv / Поиск")
        if key == "nav.settings":
            from src.database.connection import Database
            from src.services.backup_service import BackupService

            db = self._container.resolve(Database)
            return SettingsView(
                self._settings,
                on_theme_change=self._apply_theme,
                backup=BackupService(db.connection),
            )
        return QWidget()

    @staticmethod
    def _section_item(text: str) -> QListWidgetItem:
        """A small, muted, non-selectable group heading inside the nav list."""
        from PySide6.QtGui import QFont

        item = QListWidgetItem(text)
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        font = QFont()
        font.setPointSize(8)
        font.setBold(True)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)
        item.setFont(font)
        # the colour is the theme's to choose — a heading has to stay muted on
        # paper and on ink alike, and a value fixed here would suit only one
        item.setSizeHint(QSize(0, 32))
        return item

    def _select_page(self, page_index: int) -> None:
        """Focus the nav row that owns ``page_index`` in the stack."""
        for row, page in self._row_to_page.items():
            if page == page_index:
                self._nav_list.setCurrentRow(row)
                return

    def _on_nav(self, row: int) -> None:
        page = self._row_to_page.get(row)
        if page is None:  # a section header — ignore
            return
        self._stack.setCurrentIndex(page)
        # the screen takes the colour of the paper it prints on
        self._nav_key = self._row_to_key.get(row, self._nav_key)
        self._repaint()
        view = self._stack.currentWidget()
        refresh = getattr(view, "refresh", None)
        if callable(refresh):
            refresh()

    def _apply_theme(self, theme: str) -> None:
        """Switch light/dark without losing which section's colour is showing."""
        self._theme = theme
        self._repaint()

    def _repaint(self) -> None:
        from PySide6.QtWidgets import QApplication

        from src.ui.theme import INKS, apply_theme, stock_for

        app = QApplication.instance()
        if app is not None:
            apply_theme(app, self._theme, self._nav_key)  # type: ignore[arg-type]
        brand = getattr(self, "_brand", None)
        if brand is not None:
            ink, muted = INKS.get(self._theme, INKS["dark"])
            brand.set_palette(stock_for(self._nav_key, self._theme).base,
                              ink, muted)

    def _build_sidebar(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("sidebar")
        panel.setFixedWidth(248)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        from src.ui.widgets.brand_mark import BrandMark

        self._brand = BrandMark()
        self._brand.setToolTip(constants.APP_NAME)
        layout.addWidget(self._brand)

        self._nav_list.setObjectName("navList")
        self._nav_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._nav_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._nav_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        layout.addWidget(self._nav_list, stretch=1)

        refresh = QPushButton("🔄  Обновить")
        refresh.setObjectName("refreshButton")
        refresh.setToolTip("Майдонларни тозалаш — янги ҳужжат юклаш учун (F5)")
        refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh.clicked.connect(self.reset_current_view)
        wrap = QVBoxLayout()
        wrap.setContentsMargins(12, 6, 12, 4)
        wrap.addWidget(refresh)
        layout.addLayout(wrap)

        version = QLabel(f"v{constants.APP_VERSION} · {constants.ORG_NAME}")
        version.setObjectName("sidebarVersion")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)
        return panel

    def reset_current_view(self) -> None:
        """Clear the open screen's uploads so a new document can be loaded."""
        from src.ui.widgets.reset import reset_view

        view = self._stack.currentWidget()
        if view is not None and reset_view(view):
            self.statusBar().showMessage("Майдонлар тозаланди / Очищено", 2500)

    def _build_status_bar(self) -> None:
        bar = QStatusBar()
        bar.setSizeGripEnabled(False)
        self.setStatusBar(bar)
        provider = self._settings.get_str("ai.primary_provider").capitalize()
        ready = QLabel(f"  ●  {self._tr.tr('status.ready', 'Ready')}")
        ready.setObjectName("statusReady")
        bar.addWidget(ready)
        chip = QLabel(f"AI · {provider}")
        chip.setObjectName("statusChip")
        bar.addPermanentWidget(chip)
        bar.addPermanentWidget(QLabel(f"v{constants.APP_VERSION}  "))
