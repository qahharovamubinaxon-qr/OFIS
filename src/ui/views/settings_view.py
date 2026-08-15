"""Settings screen — AI keys, theme, language, output folder.

Three provider keys (Mistral · Groq · Gemini) are stored via SettingsService,
the same settings table the Gemini key has always used. Entering one takes
effect on the next read — no restart — and «Tekshirish» proves it with a tiny
live request. Keys are shown masked and are never logged or written to a file.
Theme applies live; a language change asks for a restart.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.common.errors import OfisError
from src.config import constants, paths
from src.config.settings_service import SettingsService
from src.services.backup_service import BackupService
from src.ui.widgets.card import Card

#: provider key · field label · placeholder. Order = the order they are tried.
AI_PROVIDERS: tuple[tuple[str, str, str], ...] = (
    ("mistral", "Mistral API kalit:", "hujjat-OCR — eng aniq"),
    ("groq", "Groq API kalit:", "gsk_… — eng tez"),
    ("gemini", "Gemini API kalit:", "AIza… — zaxira"),
)


def _probe(provider: str, key: str) -> str:
    """One tiny live request, to say whether a key actually works.

    The key is passed in and used once; it is never logged and never written
    anywhere but the settings table the operator typed it into.
    """
    if provider == "mistral":
        from src.ai.mistral_provider import MistralProvider

        return MistralProvider(api_key=key).check()
    if provider == "groq":
        from src.ai.groq_provider import GroqProvider

        return GroqProvider(api_key=key).check()
    from src.ai.gemini_provider import GeminiProvider

    return GeminiProvider(api_key=key).check()


def _right(*widgets: QWidget) -> QHBoxLayout:
    """Push the controls to the right edge of their card, in order."""
    row = QHBoxLayout()
    row.addStretch(1)
    for widget in widgets:
        row.addWidget(widget)
    return row


def _open_folder(folder) -> None:
    import subprocess
    import sys

    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", str(folder)])  # noqa: S603,S607
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])  # noqa: S603,S607
        else:
            subprocess.Popen(["xdg-open", str(folder)])  # noqa: S603,S607
    except OSError:
        pass


class SettingsView(QWidget):
    def __init__(
        self,
        settings: SettingsService,
        on_theme_change=None,
        backup: BackupService | None = None,
    ) -> None:
        super().__init__()
        self._settings = settings
        self._on_theme_change = on_theme_change
        self._backup = backup or BackupService()

        page = QVBoxLayout(self)
        page.setContentsMargins(28, 24, 28, 16)
        page.setSpacing(14)

        title = QLabel("Sozlamalar / Настройки")
        title.setObjectName("viewTitle")
        page.addWidget(title)

        # Sub-navigation: sections on the left, one page of cards each — the
        # settings no longer read as one long scroll.
        body = QHBoxLayout()
        body.setSpacing(18)
        page.addLayout(body, stretch=1)

        self._sections = QListWidget()
        self._sections.setObjectName("settingsNav")
        self._sections.setFixedWidth(200)
        self._sections.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._sections.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._sections.setTextElideMode(Qt.TextElideMode.ElideRight)
        body.addWidget(self._sections)

        self._pages = QStackedWidget()
        body.addWidget(self._pages, stretch=1)
        self._sections.currentRowChanged.connect(self._pages.setCurrentIndex)

        # -- AI ---------------------------------------------------------
        root = self._section("🤖", "Sun'iy intellekt")
        ai = Card("🤖", "Sun'iy intellekt",
                  "Hujjatlarni o'qish uchun uchta provayder. Yuqoridagisi "
                  "birinchi ishlaydi; xato bersa yoki kaliti bo'lmasa "
                  "keyingisiga o'tiladi.")
        self._keys: dict[str, QLineEdit] = {}
        self._key_states: dict[str, QLabel] = {}
        for provider, label, hint in AI_PROVIDERS:
            ai.add(self._key_row(provider, label, hint))
            self._key_states[provider] = ai.note("")
        # kept under its old name: the rest of the view already refers to it
        self._key = self._keys["gemini"]
        self._ai_state = ai.note("")
        ai.note("Kalitlar: console.mistral.ai · console.groq.com · "
                "aistudio.google.com/apikey")
        root.addWidget(ai)
        root.addStretch(1)

        # -- appearance --------------------------------------------------
        root = self._section("🎨", "Ko'rinish")
        look = Card("🎨", "Ko'rinish", "Mavzu darhol, til qayta ishga tushirgach.")
        look_form = look.form()
        self._theme = QComboBox()
        self._theme.addItems(constants.SUPPORTED_THEMES)
        self._theme.setCurrentText(self._settings.theme)
        self._theme.currentTextChanged.connect(self._save_theme)
        look_form.addRow("Mavzu / Theme:", self._theme)
        self._lang = QComboBox()
        self._lang.addItems(constants.SUPPORTED_LANGUAGES)
        self._lang.setCurrentText(self._settings.language)
        self._lang.currentTextChanged.connect(self._save_lang)
        look_form.addRow("Til / Язык:", self._lang)
        root.addWidget(look)

        # -- disk ---------------------------------------------------------
        # Twice now the finished documents have filled the office machine's
        # C: drive and stopped the program. They are swept after a day — but
        # a thing that deletes by itself must be visible and switchable, so
        # it is here rather than buried.
        from src.services.housekeeping import (
            DEFAULT_KEEP_DAYS,
            KEY_KEEP_DAYS,
            sweep_output,
        )

        disk = Card("🧹", "Диск тозалаш",
                    "Тайёрланган ҳужжатлар шунча кундан сўнг ўзи ўчади. "
                    "Юклаган БЛАНКАЛАРИНГИЗГА тегмайди — улар бошқа папкада.")
        dk = disk.form()
        self._keep_days = QSpinBox()
        self._keep_days.setRange(0, 365)
        self._keep_days.setSuffix(" кун")
        self._keep_days.setSpecialValueText("ўчирилмасин (0)")
        self._keep_days.setValue(int(
            self._settings.get(KEY_KEEP_DAYS, DEFAULT_KEEP_DAYS)
            or DEFAULT_KEEP_DAYS))
        self._keep_days.setToolTip(
            "Нечи кун сақлансин. 0 — ҳеч қачон ўчирилмасин.")
        dk.addRow("Ҳужжатлар сақланиши:", self._keep_days)
        save_dk = QPushButton("Saqlash")
        save_dk.setObjectName("primaryButton")
        save_dk.clicked.connect(self._save_keep_days)
        now_dk = QPushButton("🧹 Ҳозир тозалаш")
        now_dk.clicked.connect(lambda: self._sweep_now(sweep_output))
        disk.add(_right(save_dk, now_dk))
        self._disk_state = disk.note("")
        self._show_disk()
        root.addWidget(disk)
        root.addStretch(1)

        # -- доверенность counters ---------------------------------------
        root = self._section("📜", "Рақамлар")
        from src.services.dover_service import (
            DEFAULT_REESTR_NEXT,
            DEFAULT_SERIES_NEXT,
            DEFAULT_SERIES_PREFIX,
            DEFAULT_TARIF,
            KEY_REESTR_NEXT,
            KEY_SERIES_NEXT,
            KEY_SERIES_PREFIX,
            KEY_TARIF,
        )

        dover = Card("📜", "Доверенность · Согласие",
                     "Бланк серияси ва реестр рақами ҳар ҳужжатда автомат +1 бўлади.")
        dv = dover.form()
        self._dv_prefix = QLineEdit(str(
            self._settings.get(KEY_SERIES_PREFIX, DEFAULT_SERIES_PREFIX)
            or DEFAULT_SERIES_PREFIX))
        self._dv_series = QLineEdit(str(
            self._settings.get(KEY_SERIES_NEXT, DEFAULT_SERIES_NEXT) or DEFAULT_SERIES_NEXT))
        self._dv_reestr = QLineEdit(str(
            self._settings.get(KEY_REESTR_NEXT, DEFAULT_REESTR_NEXT) or DEFAULT_REESTR_NEXT))
        self._dv_tarif = QLineEdit(str(
            self._settings.get(KEY_TARIF, DEFAULT_TARIF) or DEFAULT_TARIF))
        dv.addRow("Бланк серияси (префикс):", self._dv_prefix)
        dv.addRow("Кейинги бланк рақами:", self._dv_series)
        dv.addRow("Кейинги реестр №:", self._dv_reestr)
        dv.addRow("Тариф (руб.):", self._dv_tarif)
        save_dv = QPushButton("Saqlash")
        save_dv.setObjectName("primaryButton")
        save_dv.clicked.connect(self._save_dover)
        dover.add(_right(save_dv))
        root.addWidget(dover)
        root.addStretch(1)

        # -- telegram bot -------------------------------------------------
        root = self._section("📱", "Telegram bot")
        from src.controllers.telegram_bot import KEY_PASSWORD, KEY_TOKEN

        tg_card = Card("📱", "Telegram bot",
                       "Telefondan PDF tayyorlash — kompyuter va OFIS ochiq turishi kerak.")
        tg = tg_card.form()
        self._tg_token = QLineEdit(str(self._settings.get(KEY_TOKEN, "") or ""))
        self._tg_token.setEchoMode(QLineEdit.EchoMode.Password)
        self._tg_token.setPlaceholderText("123456789:AA… (@BotFather'дан)")
        self._tg_parol = QLineEdit(str(self._settings.get(KEY_PASSWORD, "") or ""))
        self._tg_parol.setPlaceholderText("масалан: ofis2026")
        tg.addRow("Бот токени:", self._tg_token)
        tg.addRow("Парол:", self._tg_parol)
        save_tg = QPushButton("Saqlash")
        save_tg.setObjectName("primaryButton")
        save_tg.clicked.connect(self._save_telegram)
        tg_card.add(_right(save_tg))
        self._tg_state = tg_card.note("")
        tg_card.note(
            "@BotFather → /newbot → tokenni shu yerga kiriting. Telefondan botga: "
            "/start PAROL. Token kiritilgach dasturni qayta oching."
        )
        root.addWidget(tg_card)

        # -- mini app -------------------------------------------------------
        from src.controllers.telegram_bot import KEY_WEBAPP
        from src.controllers.telegram_webapp import DEFAULT_PORT, KEY_ENABLED, KEY_PORT

        port_now = self._settings.get(KEY_PORT, DEFAULT_PORT)
        wa = Card("🌐", "Mini App",
                  "Butun dastur telefon ekranida — bir xil bo'limlar, bir xil PDF.")
        wf = wa.form()
        self._wa_on = QCheckBox("Yoqilsin (dastur ochiq turganda)")
        self._wa_on.setChecked(
            str(self._settings.get(KEY_ENABLED, "0")) in ("1", "true", "True"))
        self._wa_port = QLineEdit(str(port_now))
        self._wa_url = QLineEdit(str(self._settings.get(KEY_WEBAPP, "") or ""))
        self._wa_url.setPlaceholderText("https://…  (Telegram Mini App uchun)")

        from src.services.tunnel_service import KEY_TUNNEL, cloudflared

        self._wa_tunnel = QCheckBox(
            "Telegram ichida «Mini App» tugmasi chiqsin (bepul)")
        self._wa_tunnel.setChecked(
            str(self._settings.get(KEY_TUNNEL, "0")) in ("1", "true", "True"))
        self._wa_tunnel.setEnabled(bool(cloudflared()))
        # the address is issued fresh on every start, so it is filled in by the
        # program; typing over it would only be overwritten
        self._wa_tunnel.toggled.connect(
            lambda on: self._wa_url.setEnabled(not on))
        self._wa_url.setEnabled(not self._wa_tunnel.isChecked())

        wf.addRow("", self._wa_on)
        wf.addRow("Port:", self._wa_port)
        wf.addRow("", self._wa_tunnel)
        wf.addRow("Public https URL:", self._wa_url)
        save_wa = QPushButton("Saqlash")
        save_wa.setObjectName("primaryButton")
        save_wa.clicked.connect(self._save_webapp)
        wa.add(_right(save_wa))
        self._wa_state = wa.note("")
        wa.note(
            "Telefon va kompyuter bitta Wi-Fi'da bo'lsa — yuqoridagi manzilni "
            "telefon brauzerida oching. Hech narsa kerak emas.\n\n"
            "Telegram ichida tugma chiqishi uchun Telegram https manzil talab "
            "qiladi. Yuqoridagi katakcha yoqilsa, dastur uni Cloudflare orqali "
            "o'zi oladi — bepul, ro'yxatdan o'tish va karta kerak emas. "
            + ("" if cloudflared() else
               "Buning uchun cloudflared o'rnatilgan bo'lishi kerak — hozir "
               "topilmadi, shuning uchun katakcha o'chirilgan.")
        )
        root.addWidget(wa)
        root.addStretch(1)

        # -- КРКОД РЕГ: imgbb ----------------------------------------------
        from src.services.imgbb import KEY_IMGBB

        qr_card = Card("🔳", "КРКОД РЕГ — imgbb",
                       "Подтверждение расми шу аккаунтга юкланади; QR ўша "
                       "ҳаволага ишора қилади.")
        qf = qr_card.form()
        self._imgbb_key = QLineEdit(str(self._settings.get(KEY_IMGBB, "") or ""))
        self._imgbb_key.setPlaceholderText("api.imgbb.com дан олинган калит")
        self._imgbb_key.setEchoMode(QLineEdit.EchoMode.Password)
        qf.addRow("API калит:", self._imgbb_key)
        save_qr = QPushButton("Saqlash")
        save_qr.setObjectName("primaryButton")
        save_qr.clicked.connect(self._save_imgbb)
        qr_card.add(_right(save_qr))
        root.addWidget(qr_card)
        root.addStretch(1)

        # -- УЗБ СПРАВКАЛАР: qrixtools -------------------------------------
        from src.services import qrixtools

        gate_card = Card("🔐", f"{qrixtools.SETTING_LABEL} — кодли ҳавола",
                         "УЗБ справканинг QR'и шу сайт орқали ўтади: сайт "
                         "аввал пастдаги 4 хонали кодни сўрайди, кейин "
                         "справкани кўрсатади. Калит қоғозга ҳам, логга ҳам "
                         "ёзилмайди.")
        gf = gate_card.form()
        self._qrix_key = QLineEdit(
            str(self._settings.get(qrixtools.SETTING_KEY, "") or ""))
        self._qrix_key.setPlaceholderText(
            f"{qrixtools.DOMAIN} дан олинган калит")
        self._qrix_key.setEchoMode(QLineEdit.EchoMode.Password)
        gf.addRow("API калит:", self._qrix_key)
        save_gate = QPushButton("Saqlash")
        save_gate.setObjectName("primaryButton")
        save_gate.clicked.connect(self._save_qrixtools)
        gate_card.add(_right(save_gate))
        root.addWidget(gate_card)
        root.addStretch(1)

        # -- перевод certification names ----------------------------------
        from src.controllers.ofis_modules import (
            PEREVOD_CITY_KEY,
            PEREVOD_NOTARY_KEY,
            PEREVOD_TRANSLATOR_KEY,
        )

        root = self._section("🌐", "ПЕРЕВОД")
        pv = Card("🌐", "Notarial tasdiq varag'i (3-sahifa)",
                  "Перевод PDF'ining 3-sahifasidagi ismlar. Muhr, imzo va reyestr "
                  "raqamini dastur QO'YMAYDI — ularni notarius o'zi qo'l bilan "
                  "qo'yadi va muhrlaydi.")
        pf = pv.form()
        self._pv_notary = QLineEdit(str(self._settings.get(PEREVOD_NOTARY_KEY, "") or ""))
        self._pv_notary.setPlaceholderText("масалан: Акимов Глеб Борисович")
        self._pv_translator = QLineEdit(
            str(self._settings.get(PEREVOD_TRANSLATOR_KEY, "") or ""))
        self._pv_translator.setPlaceholderText("масалан: Варавва Мария Васильевна")
        self._pv_city = QLineEdit(
            str(self._settings.get(PEREVOD_CITY_KEY, "город Москва") or "город Москва"))
        pf.addRow("Нотариус (Ф.И.О.):", self._pv_notary)
        pf.addRow("Таржимон (Ф.И.О.):", self._pv_translator)
        pf.addRow("Шаҳар:", self._pv_city)
        save_pv = QPushButton("Saqlash")
        save_pv.setObjectName("primaryButton")
        save_pv.clicked.connect(self._save_perevod)
        pv.add(_right(save_pv))
        pv.note("Bo'sh qoldirsangiz — 3-sahifada ismlar o'rniga chiziq chiqadi, "
                "notarius qo'lda to'ldiradi.")
        root.addWidget(pv)
        root.addStretch(1)

        # -- ДМС policy numbers -------------------------------------------
        from src.services.dms_service import (
            DEFAULT_REGION,
            KEY_FROM,
            KEY_NEXT,
            KEY_REGION,
            KEY_TO,
        )

        root = self._section("🏥", "ДМС")
        dm = Card("🏥", "Polis raqamlari",
                  "RESO agentligingizga ajratgan raqamlar oralig'i. Dastur faqat "
                  "shu oraliqdagi raqamlarni ishlatadi va tugaganda to'xtaydi — "
                  "o'zi raqam o'ylab topmaydi.")
        df = dm.form()
        self._dms_from = QLineEdit(str(self._settings.get(KEY_FROM, "") or ""))
        self._dms_from.setPlaceholderText("50682676085")
        self._dms_to = QLineEdit(str(self._settings.get(KEY_TO, "") or ""))
        self._dms_to.setPlaceholderText("50682676999")
        self._dms_next = QLineEdit(str(self._settings.get(KEY_NEXT, "") or ""))
        self._dms_next.setPlaceholderText("keyingi ishlatiladigan raqam")
        self._dms_region = QLineEdit(
            str(self._settings.get(KEY_REGION, DEFAULT_REGION) or DEFAULT_REGION))
        df.addRow("Раqamlar: dan", self._dms_from)
        df.addRow("… gacha", self._dms_to)
        df.addRow("Keyingi raqam:", self._dms_next)
        df.addRow("Patent hududi:", self._dms_region)
        save_dm = QPushButton("Saqlash")
        save_dm.setObjectName("primaryButton")
        save_dm.clicked.connect(self._save_dms)
        dm.add(_right(save_dm))
        self._dms_state = dm.note("")
        dm.note("Raqamlar tugaganda RESO'dan yangi oraliq oling va shu yerga "
                "kiriting.")
        root.addWidget(dm)

        # -- the blank itself ---------------------------------------------
        bl = Card("📄", "Polis blankasi",
                  "Toza blankangiz bo'lsa shu yerga yuklang — dastur o'shanga "
                  "bosadi. Fayl AppData'da saqlanadi, EXE qayta yig'ilganda "
                  "yoki «git pull» qilganda o'chmaydi.")
        bl_row = QHBoxLayout()
        pick_bl = QPushButton("📄  Blanka yuklash (PDF)")
        pick_bl.clicked.connect(self._import_dms_blank)
        open_bl = QPushButton("📂  Papkani ochish")
        open_bl.clicked.connect(self._open_dms_blank_folder)
        reset_bl = QPushButton("↩  Dasturnikiga qaytarish")
        reset_bl.clicked.connect(self._reset_dms_blank)
        for b in (pick_bl, open_bl, reset_bl):
            bl_row.addWidget(b)
        bl_row.addStretch(1)
        bl.add(bl_row)
        self._dms_blank_state = bl.note("")
        root.addWidget(bl)
        root.addStretch(1)

        # -- ИНН sheet ------------------------------------------------------
        root = self._section("🔢", "ИНН")
        inn = Card("🔢", "ИНН varag'i",
                   "Ishchining ИНН raqami saqlanadigan varaq. Yangi dizayn "
                   "qilsangiz shu yerga yuklang — AppData'da saqlanadi, EXE "
                   "qayta yig'ilganda o'chmaydi.")
        inn_row = QHBoxLayout()
        pick_inn = QPushButton("📄  Blanka yuklash (PDF)")
        pick_inn.clicked.connect(self._import_inn_blank)
        open_inn = QPushButton("📂  Papkani ochish")
        open_inn.clicked.connect(self._open_inn_blank_folder)
        reset_inn = QPushButton("↩  Dasturnikiga qaytarish")
        reset_inn.clicked.connect(self._reset_inn_blank)
        for b in (pick_inn, open_inn, reset_inn):
            inn_row.addWidget(b)
        inn_row.addStretch(1)
        inn.add(inn_row)
        self._inn_blank_state = inn.note("")
        root.addWidget(inn)
        root.addStretch(1)

        # -- БЕЙДЖИК blanks (one per region) --------------------------------
        root = self._section("🪪", "БЕЙДЖИК")
        bj = Card("🪪", "Beydjik blankalari",
                  "Har region uchun alohida blanka: 77 — Москва, "
                  "50 — Московская область. Yangi dizayn qilsangiz shu yerga "
                  "yuklang — AppData'da saqlanadi, EXE qayta yig'ilganda "
                  "o'chmaydi.")
        self._bj_blank_states = {}
        from src.services.beydjik_service import REGIONS as _BJ_REGIONS

        for code, spec in _BJ_REGIONS.items():
            row = QHBoxLayout()
            row.addWidget(QLabel(spec["label"]))
            pick = QPushButton("📄  Blanka yuklash")
            pick.clicked.connect(lambda _=False, c=code: self._import_bj_blank(c))
            openb = QPushButton("📂  Papka")
            openb.clicked.connect(lambda _=False, c=code: self._open_bj_folder(c))
            reset = QPushButton("↩  Dasturnikiga")
            reset.clicked.connect(lambda _=False, c=code: self._reset_bj_blank(c))
            for w in (pick, openb, reset):
                row.addWidget(w)
            row.addStretch(1)
            bj.add(row)
            self._bj_blank_states[code] = bj.note("")
        root.addWidget(bj)

        pr = Card("🔢", "Beydjik «ПР» raqami",
                  "Har beydjikda bittaga oshadi. Yangi seriyani shu yerdan "
                  "boshlang.")
        pr_row = QHBoxLayout()
        pr_row.addWidget(QLabel("Keyingi ПР:"))
        self._bj_pr = QLineEdit()
        self._bj_pr.setFixedWidth(140)
        pr_row.addWidget(self._bj_pr)
        pr_row.addSpacing(16)
        pr_row.addWidget(QLabel("Firma (kem vydano):"))
        self._bj_firm = QLineEdit()
        pr_row.addWidget(self._bj_firm)
        save_bj = QPushButton("💾  Saqlash")
        save_bj.clicked.connect(self._save_beydjik)
        pr_row.addWidget(save_bj)
        pr.add(pr_row)
        self._bj_state = pr.note("")
        root.addWidget(pr)

        qr = Card("🔳", "Beydjik QR-kodi",
                  "Beydjikning orqasidagi QR-kod ichida nima yozilishi. "
                  "Jingalak qavs ichidagilar har beydjikning o'z ma'lumoti "
                  "bilan almashadi.")
        self._bj_qr = QLineEdit()
        qr.add(self._bj_qr)
        save_qr = QHBoxLayout()
        save_qr_btn = QPushButton("💾  Saqlash")
        save_qr_btn.clicked.connect(self._save_beydjik_qr)
        reset_qr_btn = QPushButton("↩  Standart matn")
        reset_qr_btn.clicked.connect(self._reset_beydjik_qr)
        save_qr.addWidget(save_qr_btn)
        save_qr.addWidget(reset_qr_btn)
        save_qr.addStretch(1)
        qr.add(save_qr)
        from src.services.beydjik_service import QR_FIELDS as _BJ_QR_FIELDS

        qr.note("Mavjud maydonlar:  "
                + "  ".join("{" + f + "}" for f in _BJ_QR_FIELDS))
        self._bj_qr_state = qr.note("")
        root.addWidget(qr)
        root.addStretch(1)

        # -- backup / restore ---------------------------------------------
        root = self._section("💾", "Zaxira")
        bk = Card("💾", "Zaxira nusxa",
                  "Butun baza (firmalar, manzillar, hisoblagichlar, arxiv) + shablonlar.")
        bk_row = QHBoxLayout()
        make_bk = QPushButton("💾  Zaxira yaratish (ZIP)")
        make_bk.clicked.connect(self._create_backup)
        restore_bk = QPushButton("📥  Zaxiradan tiklash")
        restore_bk.clicked.connect(self._restore_backup)
        bk_row.addWidget(make_bk)
        bk_row.addWidget(restore_bk)
        bk_row.addStretch(1)
        bk.add(bk_row)
        self._bk_state = bk.note("")
        bk.note("Yangi kompyuterga o'tishda yoki har oy bir marta zaxira oling.")
        root.addWidget(bk)
        root.addStretch(1)

        # -- folders --------------------------------------------------------
        root = self._section("📁", "Papkalar")
        folders = Card("📁", "Papkalar", "Hujjatlar va ma'lumotlar qayerda turadi.")
        for label, folder in (("Chiqish papkasi", paths.output_dir()),
                              ("Ma'lumotlar", paths.data_dir()),
                              ("Zaxiralar", paths.backups_dir())):
            row = QHBoxLayout()
            text = QLabel(f"{label}:  {folder}")
            text.setObjectName("cardNote")
            text.setWordWrap(True)
            open_btn = QPushButton("Ochish")
            open_btn.clicked.connect(lambda _=False, f=folder: _open_folder(f))
            row.addWidget(text, stretch=1)
            row.addWidget(open_btn)
            folders.add(row)
        root.addWidget(folders)
        root.addStretch(1)

        self._sections.setCurrentRow(0)
        self._refresh_states()

    # ------------------------------------------------------------------
    def _section(self, icon: str, title: str) -> QVBoxLayout:
        """Register a settings section and return the layout for its cards."""
        item = QListWidgetItem(f"{icon}   {title}")
        self._sections.addItem(item)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 0, 10, 0)
        layout.setSpacing(16)
        scroll.setWidget(holder)
        self._pages.addWidget(scroll)
        return layout

    def refresh(self) -> None:
        self._refresh_states()

    def _refresh_states(self) -> None:
        """Show at a glance what is configured and what is not."""
        from src.controllers.telegram_bot import KEY_TOKEN

        ready = [provider.capitalize() for provider, _l, _h in AI_PROVIDERS
                 if str(self._settings.get(f"ai.{provider}_key", "") or "").strip()]
        self._ai_state.setText(
            "✅  Zanjir: " + " → ".join(ready) if ready
            else "⚠️  Birorta kalit yo'q — AI bo'limlari ishlamaydi.")

        has_token = bool(str(self._settings.get(KEY_TOKEN, "") or "").strip())
        self._tg_state.setText("✅  Token kiritilgan — bot ishga tushadi." if has_token
                               else "⚠️  Token yo'q — bot o'chirilgan.")

        from src.controllers.telegram_bot import KEY_PASSWORD
        from src.controllers.telegram_webapp import DEFAULT_PORT, KEY_ENABLED, KEY_PORT, lan_ip

        if str(self._settings.get(KEY_ENABLED, "0")) not in ("1", "true", "True"):
            self._wa_state.setText("⚠️  O'chirilgan.")
        elif not str(self._settings.get(KEY_PASSWORD, "") or "").strip():
            self._wa_state.setText("⚠️  Parol yo'q — Mini App ishga tushmaydi.")
        else:
            # the address is written out in full, password and all: it has to
            # be typed on the phone, and «?k=PAROL» left the operator guessing
            # which parol and where it goes.
            port = str(self._settings.get(KEY_PORT, DEFAULT_PORT))
            if not (port.isdigit() and 1 <= int(port) <= 65535):
                port = str(DEFAULT_PORT)
            parol = str(self._settings.get(KEY_PASSWORD, "") or "").strip()
            lines = ["✅  Telefon brauzerida oching (bir xil Wi-Fi):",
                     f"http://{lan_ip()}:{port}/?k={parol}"]

            from src.controllers.telegram_bot import KEY_WEBAPP
            from src.services.tunnel_service import KEY_TUNNEL

            if str(self._settings.get(KEY_TUNNEL, "0")) in ("1", "true", "True"):
                public = str(self._settings.get(KEY_WEBAPP, "") or "").strip()
                lines.append("")
                lines.append(f"🌐  Telegram tugmasi:  {public}" if public else
                             "🌐  Telegram manzili olinmoqda… (bir daqiqagacha)")
            self._wa_state.setText("\n".join(lines))

        from src.services.dms_service import DmsService

        dms = DmsService(self._settings)
        nxt, left = dms.peek_number(), dms.remaining()
        self._dms_state.setText(
            f"✅  Keyingi raqam: {nxt}  ·  qoldi: {left} ta" if nxt
            else "⚠️  Raqamlar oralig'i kiritilmagan — ДМС ishlamaydi.")

        from src.services.dms_service import blank_source

        blank, own = blank_source()
        self._dms_blank_state.setText(
            f"✅  Sizning blankangiz:  {blank}" if own
            else f"ℹ️  Dasturning blankasi ishlatilyapti.\n     Yuklash joyi:  {blank}")

        from src.services.inn_service import blank_source as inn_blank_source
        from src.services.inn_service import user_blank_path as inn_blank_target

        inn_blank, inn_own = inn_blank_source()
        self._inn_blank_state.setText(
            f"✅  Sizning varag'ingiz:  {inn_blank}" if inn_own
            else "ℹ️  Dasturning varag'i ishlatilyapti.\n"
                 f"     Yuklash joyi:  {inn_blank_target()}")

        from src.services.beydjik_service import (
            KEY_FIRM as BJ_KEY_FIRM,
        )
        from src.services.beydjik_service import (
            KEY_PR_NEXT as BJ_KEY_PR,
        )
        from src.services.beydjik_service import (
            blank_source as bj_blank_source,
        )
        from src.services.beydjik_service import (
            user_blank_path as bj_blank_target,
        )

        for code, note in getattr(self, "_bj_blank_states", {}).items():
            bj_blank, bj_own = bj_blank_source(code)
            note.setText(
                f"✅  Sizning blankangiz:  {bj_blank}" if bj_own
                else "ℹ️  Dasturning blankasi ishlatilyapti.\n"
                     f"     Yuklash joyi:  {bj_blank_target(code)}")
        if hasattr(self, "_bj_qr"):
            from src.services.beydjik_service import DEFAULT_QR_TEMPLATE
            from src.services.beydjik_service import KEY_QR as BJ_KEY_QR

            stored = str(self._settings.get(BJ_KEY_QR, "") or "").strip()
            if not self._bj_qr.text().strip():
                self._bj_qr.setText(stored or DEFAULT_QR_TEMPLATE)
            self._bj_qr_state.setText(
                "✅  Sizning matningiz" if stored
                else "ℹ️  Dasturning standart matni ishlatilyapti.")

        if hasattr(self, "_bj_pr"):
            nxt = str(self._settings.get(BJ_KEY_PR, "") or "")
            if not self._bj_pr.text().strip():
                self._bj_pr.setText(nxt)
            if not self._bj_firm.text().strip():
                self._bj_firm.setText(str(self._settings.get(BJ_KEY_FIRM, "") or ""))
            self._bj_state.setText(
                f"✅  Keyingi ПР: {nxt}" if nxt
                else "⚠️  «ПР» raqami kiritilmagan — 1 dan boshlanadi.")

        backups = sorted(paths.backups_dir().glob("OFIS_backup_*.zip"))
        if backups:
            newest = backups[-1]
            stamp = newest.stem.replace("OFIS_backup_", "").replace("_", " ")
            self._bk_state.setText(f"Oxirgi zaxira:  {stamp}  ({len(backups)} ta)")
        else:
            self._bk_state.setText("⚠️  Hali zaxira olinmagan.")

    # ------------------------------------------------------------ AI keys
    def _key_row(self, provider: str, label: str, hint: str):
        """One provider's key: hidden field, «Saqlash», «Tekshirish»."""
        row = QHBoxLayout()
        field = QLineEdit(str(self._settings.get(f"ai.{provider}_key", "") or ""))
        field.setEchoMode(QLineEdit.EchoMode.Password)
        field.setPlaceholderText(hint)
        self._keys[provider] = field

        save = QPushButton("Saqlash")
        save.setObjectName("primaryButton")
        save.clicked.connect(lambda _=False, p=provider: self._save_ai_key(p))
        check = QPushButton("Tekshirish")
        check.clicked.connect(lambda _=False, p=provider: self._check_ai_key(p))

        row.addWidget(QLabel(label))
        row.addWidget(field, stretch=1)
        row.addWidget(save)
        row.addWidget(check)
        return row

    def _save_ai_key(self, provider: str) -> None:
        """Stored exactly like the Gemini key always was — same settings table."""
        self._settings.set(f"ai.{provider}_key", self._keys[provider].text().strip())
        self._refresh_states()
        QMessageBox.information(self, "OK", f"{provider.capitalize()} kaliti saqlandi.")

    def _check_ai_key(self, provider: str) -> None:
        """Send a tiny live request and say plainly whether it worked."""
        key = self._keys[provider].text().strip()
        state = self._key_states[provider]
        if not key:
            state.setText("⚠️  Kalit kiritilmagan.")
            return
        state.setText("⏳  Tekshirilyapti…")
        QApplication.processEvents()
        try:
            message = _probe(provider, key)
        except OfisError as exc:
            state.setText("❌  " + exc.message)
            return
        except Exception as exc:  # noqa: BLE001 - surface whatever went wrong
            state.setText("❌  " + str(exc)[:160])
            return
        state.setText("✅  " + message)

    def _save_key(self) -> None:
        """Kept for callers that still know only about the Gemini field."""
        self._save_ai_key("gemini")

    # -- disk -----------------------------------------------------------
    def _folder_size(self) -> tuple[int, int]:
        """How much the finished documents are taking up, right now."""
        from src.config import paths

        files = [f for f in paths.output_dir().rglob("*") if f.is_file()]
        return len(files), sum(f.stat().st_size for f in files)

    def _show_disk(self) -> None:
        try:
            count, size = self._folder_size()
        except OSError:
            self._disk_state.setText("")
            return
        self._disk_state.setText(
            f"Ҳозир: {count} та ҳужжат · {size / 1_073_741_824:.2f} GB")

    def _save_keep_days(self) -> None:
        from src.services.housekeeping import KEY_KEEP_DAYS

        days = self._keep_days.value()
        self._settings.set(KEY_KEEP_DAYS, days)
        QMessageBox.information(
            self, "OK", "Тайёрланган ҳужжатлар " + (
                "ҳеч қачон ўчирилмайди." if not days else
                f"{days} кундан сўнг ўзи ўчади.\n"
                "Юклаган бланкаларингизга тегилмайди."))

    def _sweep_now(self, sweep) -> None:
        days = self._keep_days.value()
        if not days:
            QMessageBox.information(
                self, "Diqqat", "0 турибди — ҳеч нима ўчирилмайди. "
                "Аввал неча кун сақланишини белгиланг.")
            return
        made = sweep(days)
        self._show_disk()
        QMessageBox.information(
            self, "Тозаланди",
            f"{made.removed} та ҳужжат ўчди, {made.freed_mb:.0f} MB бўшади.\n"
            f"{made.kept} та ҳужжат ҳали {days} кунлик эмас — қолдирилди."
            + (f"\n{made.locked} таси очиқ турибди — ўчмади."
               if made.locked else ""))

    def _save_theme(self, theme: str) -> None:
        self._settings.set("theme", theme)
        if self._on_theme_change:
            self._on_theme_change(theme)

    def _save_lang(self, lang: str) -> None:
        self._settings.set("language", lang)
        QMessageBox.information(self, "OK", "Til saqlandi. Qayta ishga tushiring / Restart to apply.")

    def _save_dover(self) -> None:
        from src.services.dover_service import (
            KEY_REESTR_NEXT,
            KEY_SERIES_NEXT,
            KEY_SERIES_PREFIX,
            KEY_TARIF,
        )

        try:
            series = int(self._dv_series.text().strip())
            reestr = int(self._dv_reestr.text().strip())
        except ValueError:
            QMessageBox.warning(self, "Xato", "Бланк рақами ва реестр № — фақат рақам.")
            return
        self._settings.set(KEY_SERIES_PREFIX, self._dv_prefix.text().strip() or "77 АВ")
        self._settings.set(KEY_SERIES_NEXT, series)
        self._settings.set(KEY_REESTR_NEXT, reestr)
        self._settings.set(KEY_TARIF, self._dv_tarif.text().strip() or "1500")
        QMessageBox.information(self, "OK", "Доверенность рақамлари сақланди.")

    def _save_telegram(self) -> None:
        from src.controllers.telegram_bot import KEY_PASSWORD, KEY_TOKEN

        self._settings.set(KEY_TOKEN, self._tg_token.text().strip())
        self._settings.set(KEY_PASSWORD, self._tg_parol.text().strip())
        self._refresh_states()
        QMessageBox.information(
            self, "OK",
            "Telegram sozlamalari saqlandi.\nDasturni yopib qayta oching — "
            "bot shunda ishga tushadi.")

    def _import_dms_blank(self) -> None:
        from src.services.dms_service import import_blank

        path, _ = QFileDialog.getOpenFileName(
            self, "Polis blankasi (PDF)", str(paths.desktop_dir()), "PDF (*.pdf)")
        if not path:
            return
        try:
            saved = import_blank(Path(path))
        except OfisError as exc:
            QMessageBox.warning(self, "Xato", exc.message)
            return
        self._refresh_states()
        QMessageBox.information(
            self, "OK", f"Blanka yuklandi:\n{saved}\n\nEndi ДМС shu blankaga bosadi.")

    def _open_dms_blank_folder(self) -> None:
        from src.services.dms_service import user_blank_path

        folder = user_blank_path().parent
        folder.mkdir(parents=True, exist_ok=True)
        _open_folder(folder)

    def _reset_dms_blank(self) -> None:
        from src.services.dms_service import user_blank_path

        own = user_blank_path()
        if not own.exists():
            QMessageBox.information(self, "OK", "Allaqachon dasturnikini ishlatyapti.")
            return
        if QMessageBox.question(
                self, "Qaytarish",
                "Yuklangan blanka o'chirilsinmi? Dastur o'zinikiga qaytadi."
        ) != QMessageBox.StandardButton.Yes:
            return
        own.unlink()
        self._refresh_states()
        QMessageBox.information(self, "OK", "Dasturning blankasi ishlatiladi.")

    def _import_inn_blank(self) -> None:
        from src.services.inn_service import import_blank

        path, _ = QFileDialog.getOpenFileName(
            self, "ИНН varag'i (PDF)", str(paths.desktop_dir()), "PDF (*.pdf)")
        if not path:
            return
        try:
            saved = import_blank(Path(path))
        except OfisError as exc:
            QMessageBox.warning(self, "Xato", exc.message)
            return
        self._refresh_states()
        QMessageBox.information(self, "OK", f"Varaq yuklandi:\n{saved}")

    def _open_inn_blank_folder(self) -> None:
        from src.services.inn_service import user_blank_path

        folder = user_blank_path().parent
        folder.mkdir(parents=True, exist_ok=True)
        _open_folder(folder)

    def _reset_inn_blank(self) -> None:
        from src.services.inn_service import user_blank_path

        own = user_blank_path()
        if not own.exists():
            QMessageBox.information(self, "OK", "Allaqachon dasturnikini ishlatyapti.")
            return
        if QMessageBox.question(
                self, "Qaytarish", "Yuklangan varaq o'chirilsinmi?"
        ) != QMessageBox.StandardButton.Yes:
            return
        own.unlink()
        self._refresh_states()
        QMessageBox.information(self, "OK", "Dasturning varag'i ishlatiladi.")

    def _import_bj_blank(self, region: str) -> None:
        from src.services.beydjik_service import import_blank

        path, _ = QFileDialog.getOpenFileName(
            self, f"Beydjik blankasi — {region} (PDF)",
            str(paths.desktop_dir()), "PDF (*.pdf)")
        if not path:
            return
        try:
            saved = import_blank(region, Path(path))
        except OfisError as exc:
            QMessageBox.warning(self, "Xato", exc.message)
            return
        self._refresh_states()
        QMessageBox.information(self, "OK", f"Blanka yuklandi:\n{saved}")

    def _open_bj_folder(self, region: str) -> None:
        from src.services.beydjik_service import user_blank_path

        folder = user_blank_path(region).parent
        folder.mkdir(parents=True, exist_ok=True)
        _open_folder(folder)

    def _reset_bj_blank(self, region: str) -> None:
        from src.services.beydjik_service import user_blank_path

        own = user_blank_path(region)
        if not own.exists():
            QMessageBox.information(self, "OK", "Allaqachon dasturnikini ishlatyapti.")
            return
        if QMessageBox.question(
                self, "Qaytarish", f"{region} blankasi o'chirilsinmi?"
        ) != QMessageBox.StandardButton.Yes:
            return
        own.unlink()
        self._refresh_states()
        QMessageBox.information(self, "OK", "Dasturning blankasi ishlatiladi.")

    def _save_beydjik(self) -> None:
        from src.services.beydjik_service import KEY_FIRM, KEY_PR_NEXT

        digits = "".join(c for c in self._bj_pr.text() if c.isdigit())
        if digits:
            self._settings.set(KEY_PR_NEXT, int(digits))
        self._settings.set(KEY_FIRM, self._bj_firm.text().strip())
        self._refresh_states()
        QMessageBox.information(self, "OK", "Beydjik sozlamalari saqlandi.")

    def _save_beydjik_qr(self) -> None:
        from src.services.beydjik_service import KEY_QR

        self._settings.set(KEY_QR, self._bj_qr.text().strip())
        self._refresh_states()
        QMessageBox.information(self, "OK", "QR-kod matni saqlandi.")

    def _reset_beydjik_qr(self) -> None:
        from src.services.beydjik_service import DEFAULT_QR_TEMPLATE, KEY_QR

        self._settings.set(KEY_QR, "")
        self._bj_qr.setText(DEFAULT_QR_TEMPLATE)
        self._refresh_states()

    def _save_dms(self) -> None:
        from src.services.dms_service import (
            DEFAULT_REGION,
            KEY_FROM,
            KEY_NEXT,
            KEY_REGION,
            KEY_TO,
        )

        def digits(widget) -> str:
            return "".join(c for c in widget.text() if c.isdigit())

        low, high, nxt = digits(self._dms_from), digits(self._dms_to), digits(self._dms_next)
        if low and high and int(high) < int(low):
            QMessageBox.warning(self, "Xato", "«gacha» raqami «dan» dan kichik.")
            return
        self._settings.set(KEY_FROM, low)
        self._settings.set(KEY_TO, high)
        self._settings.set(KEY_NEXT, nxt or low)
        self._settings.set(KEY_REGION,
                           self._dms_region.text().strip() or DEFAULT_REGION)
        self._refresh_states()
        QMessageBox.information(self, "OK", "ДМС sozlamalari saqlandi.")

    def _save_perevod(self) -> None:
        from src.controllers.ofis_modules import (
            PEREVOD_CITY_KEY,
            PEREVOD_NOTARY_KEY,
            PEREVOD_TRANSLATOR_KEY,
        )

        self._settings.set(PEREVOD_NOTARY_KEY, self._pv_notary.text().strip())
        self._settings.set(PEREVOD_TRANSLATOR_KEY, self._pv_translator.text().strip())
        self._settings.set(PEREVOD_CITY_KEY,
                           self._pv_city.text().strip() or "город Москва")
        QMessageBox.information(self, "OK", "ПЕРЕВОД sozlamalari saqlandi.")

    def _save_imgbb(self) -> None:
        from src.services.imgbb import KEY_IMGBB

        self._settings.set(KEY_IMGBB, self._imgbb_key.text().strip())
        QMessageBox.information(self, "OK", "imgbb калити сақланди.")

    def _save_qrixtools(self) -> None:
        from src.services import qrixtools

        self._settings.set(qrixtools.SETTING_KEY, self._qrix_key.text().strip())
        QMessageBox.information(
            self, "OK", f"{qrixtools.SETTING_LABEL} калити сақланди.")

    def _save_webapp(self) -> None:
        from src.controllers.telegram_bot import KEY_WEBAPP
        from src.controllers.telegram_webapp import DEFAULT_PORT, KEY_ENABLED, KEY_PORT

        # 0 is a number too, and the socket takes it as «any free port» — the
        # address on this screen then points at a port nothing listens on.
        port = self._wa_port.text().strip()
        ok = port.isdigit() and 1 <= int(port) <= 65535
        self._settings.set(KEY_PORT, port if ok else str(DEFAULT_PORT))
        if not ok:
            self._wa_port.setText(str(DEFAULT_PORT))
        self._settings.set(KEY_ENABLED, "1" if self._wa_on.isChecked() else "0")

        from src.services.tunnel_service import KEY_TUNNEL

        tunnel_on = self._wa_tunnel.isChecked()
        self._settings.set(KEY_TUNNEL, "1" if tunnel_on else "0")
        if tunnel_on:
            # the tunnel writes the address itself on every start; saving the
            # box's stale contents over it would break the button
            self._refresh_states()
            QMessageBox.information(
                self, "OK",
                "Mini App sozlamalari saqlandi.\nDasturni yopib qayta oching — "
                "manzil o'zi olinadi va Telegram'da tugma chiqadi.")
            return

        # Telegram opens a Mini App button only over https. An http address
        # here is silently dropped by Telegram, so it is refused right away
        # instead of leaving a button that never opens.
        url = self._wa_url.text().strip()
        if url and not url.lower().startswith("https://"):
            QMessageBox.warning(
                self, "Mini App",
                "Telegram «Mini App» tugmasi faqat https manzil bilan ishlaydi.\n"
                "Bu maydon bo'shatildi — telefon brauzerida quyidagi "
                "http manzildan foydalaning.")
            url = ""
            self._wa_url.setText("")
        self._settings.set(KEY_WEBAPP, url)
        self._refresh_states()
        QMessageBox.information(
            self, "OK",
            "Mini App sozlamalari saqlandi.\nDasturni yopib qayta oching.")

    # -- backup / restore ----------------------------------------------
    def _create_backup(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Zaxira qayerga saqlansin?", str(paths.desktop_dir())
        )
        if not folder:
            return
        try:
            target = self._backup.create_backup(Path(folder))
        except OfisError as exc:
            QMessageBox.warning(self, "Xato", exc.message)
            return
        self._refresh_states()
        QMessageBox.information(self, "Tayyor", f"Zaxira nusxa yaratildi:\n{target}")

    def _restore_backup(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Zaxira ZIP faylini tanlang", str(paths.desktop_dir()),
            "OFIS backup (*.zip)",
        )
        if not path:
            return
        confirm = QMessageBox.question(
            self, "Tasdiqlash",
            "Joriy ma'lumotlar zaxiradagi bilan ALMASHTIRILADI.\n"
            "(Hozirgi baza avval backups/ papkasiga saqlab qo'yiladi.)\n\nDavom etamizmi?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            BackupService.stage_restore(Path(path))
        except OfisError as exc:
            QMessageBox.warning(self, "Xato", exc.message)
            return
        QMessageBox.information(
            self, "Tayyor",
            "Zaxira qabul qilindi.\nDasturni YOPIB QAYTA OCHING — "
            "ma'lumotlar shunda tiklanadi.",
        )
