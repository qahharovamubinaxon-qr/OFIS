"""Telegram bot conversation flow, driven through a fake transport.

No network: ``_api``/``_send``/``_send_file``/``_download`` are replaced, so
every test exercises the real state machine and only stubs the wire.
"""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import pytest

from src.config import paths

CHAT = 7


@pytest.fixture()
def bot(monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", tempfile.mkdtemp())
    paths.data_dir.cache_clear()
    from src.app import build_container
    from src.config.settings_service import SettingsService
    from src.controllers.telegram_bot import KEY_PASSWORD, KEY_TOKEN, TelegramBot

    container = build_container()
    settings = container.resolve(SettingsService)
    settings.set(KEY_TOKEN, "TEST:TOKEN")
    settings.set(KEY_PASSWORD, "sirli")

    b = TelegramBot(container)
    b._settings = settings
    b.sent = []
    b.files = []
    monkeypatch.setattr(b, "_send",
                        lambda chat_id, text, keyboard=None: b.sent.append((text, keyboard)))
    monkeypatch.setattr(b, "_send_file",
                        lambda chat_id, path, caption="": b.files.append(Path(path)))
    monkeypatch.setattr(b, "_download", lambda file_id: b"fake-image-bytes")
    monkeypatch.setattr(b, "_api", lambda method, payload: {"ok": True, "result": []})
    yield b
    paths.data_dir.cache_clear()


def _text(bot, text: str, chat_id: int = CHAT) -> None:
    bot._handle({"update_id": 1, "message": {"chat": {"id": chat_id}, "text": text}})


def _photo(bot, chat_id: int = CHAT) -> None:
    bot._handle({"update_id": 1, "message": {
        "chat": {"id": chat_id}, "photo": [{"file_id": "s"}, {"file_id": "b"}]}})


def _pick(bot, index: int, chat_id: int = CHAT) -> None:
    bot._handle({"update_id": 1, "callback_query": {
        "id": "cq1", "message": {"chat": {"id": chat_id}},
        "data": f"pick:{index}"}})


def _last(bot) -> str:
    return bot.sent[-1][0]


def _all(bot) -> str:
    return "\n".join(t for t, _ in bot.sent)


def _login(bot) -> None:
    _text(bot, "/start sirli")


@pytest.fixture()
def ready(bot, monkeypatch):
    """Logged in with the AI marked available."""
    _login(bot)
    monkeypatch.setattr(bot.ctl()["ocr"], "available", lambda: True)
    bot.sent.clear()
    return bot


# ---------------------------------------------------------------- auth


def test_auth_flow(bot) -> None:
    _text(bot, "/start noto'g'ri")
    assert "хато" in _last(bot).lower()
    _login(bot)
    assert "уланди" in _all(bot).lower()
    assert CHAT in bot._allowed()


def test_unauthorized_blocked(bot) -> None:
    _text(bot, "salom", chat_id=99)
    assert "/start" in _last(bot)


# ---------------------------------------------------------------- menu


def test_menu_lists_every_module(ready) -> None:
    from src.controllers.telegram_bot import _MODULES

    _text(ready, "☰ Бўлимлар")
    buttons = {b for row in ready.sent[-1][1]["keyboard"] for b in row}
    for module in _MODULES:
        assert module.button in buttons, f"{module.key} missing from the menu"
    assert len(_MODULES) >= 9, "the bot must cover the whole program"


#: Every desktop side-bar entry that does work, and the module that mirrors it
#: on the phone. A new section on the computer that never reaches the bot is
#: exactly the bug this table exists to catch.
_DESKTOP_TO_MODULE = {
    "nav.process": "patent",
    "nav.registration": "reg",
    "nav.hostel": "hostel",
    "nav.trud": "trud",
    "nav.dms": "dms",
    "nav.strahovka": "insurance",
    "nav.inn": "inn",
    "nav.beydjik": "beydjik",
    "nav.patent": "patent_card",
    "nav.razreshenie": "razreshenie",
    "nav.svera": "svera",
    "nav.sertifikat": "sertifikat",
    "nav.dover": "dover",
    "nav.perevod": "perevod",
    "nav.umumiy": "umumiy",
    "nav.template": "shablon",
    "nav.photo": "photo",
    "nav.jpg2pdf": "jpg2pdf",
    "nav.jpg2pdf": "jpg2pdf",
    "nav.summa": "summa",
}

#: Sections that hold data or settings rather than doing work.
_HOUSEKEEPING = {"nav.dashboard", "nav.companies", "nav.archive", "nav.search",
                 "nav.settings"}

#: ЧЕК stays on the computer. Its renderer makes up the payment's own proof —
#: a random 6-digit код авторизации and a random company id on a bank-receipt
#: background — and I will not build the machinery that mails those out.
_NOT_ON_THE_PHONE = {"nav.chek",
                     # ППУ needs the office's own blank uploaded first
                     "nav.ppu",
                     # СНИЛС likewise
                     "nav.snils"}


def test_every_desktop_section_is_also_on_the_phone() -> None:
    from src.controllers.ofis_modules import BY_KEY
    from src.ui.main_window import _NAV

    for _group, key, title, *_rest in _NAV:
        if key in _HOUSEKEEPING or key in _NOT_ON_THE_PHONE:
            continue
        assert key in _DESKTOP_TO_MODULE, (
            f"«{title}» ({key}) компютерда бор, телефонда йўқ — "
            "ofis_modules.MODULES га қўшинг")
        assert _DESKTOP_TO_MODULE[key] in BY_KEY, (
            f"{_DESKTOP_TO_MODULE[key]} модули йўқолиб қолди")


# ------------------------------------------------------- registration flow


def test_registration_asks_for_the_date_then_runs(ready, monkeypatch) -> None:
    seen = {}

    def fake_generate(target, passport, patent, back, *, registration_expiry):
        seen["expiry"] = registration_expiry
        out = paths.output_dir() / "reg.pdf"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"%PDF-1.4\n")

        class R:
            pdf_path = out

        return R()

    monkeypatch.setattr(ready.ctl()["reg"], "generate_from_images", fake_generate)

    _text(ready, "🏠 Регистрация")
    _pick(ready, 0)
    _photo(ready)
    _text(ready, "✅ Тайёрла")
    assert "ТУГАШ" in _last(ready), "the date question was never asked"

    _text(ready, "15.10.2026")
    assert seen["expiry"] == date(2026, 10, 15)
    assert ready.files, "no PDF was sent back"
    assert "Тайёр" in _all(ready)


def test_bad_date_is_rejected_and_re_asked(ready) -> None:
    _text(ready, "🏠 Регистрация")
    _pick(ready, 0)
    _photo(ready)
    _text(ready, "✅ Тайёрла")
    _text(ready, "ertaga")
    assert "формати" in _last(ready)


def test_run_without_a_pick_says_what_is_missing(ready) -> None:
    """Pressing Тайёрла before choosing an address must not bounce back to
    «select a section» — that dead-ended the operator."""
    _text(ready, "🏠 Регистрация")
    _text(ready, "✅ Тайёрла")
    assert "рўйхатдан танланг" in _last(ready).lower()


def test_photos_are_refused_until_a_module_is_chosen(ready) -> None:
    _photo(ready)
    assert "бўлимни танланг" in _last(ready).lower()


def test_empty_list_does_not_leave_a_half_entered_module(ready, monkeypatch) -> None:
    monkeypatch.setattr(ready.ctl()["trud"], "firms", list)
    _text(ready, "📑 Трудовой")
    assert "бўш" in _last(ready)
    _photo(ready)  # not swallowed into a module with no target
    assert "бўлимни танланг" in _last(ready).lower()


def test_patent_flow_labels_the_photos(ready) -> None:
    _text(ready, "🛂 Патент PDF")
    _pick(ready, 0)
    _photo(ready)
    assert "1/3" in _last(ready)
    _photo(ready)
    assert "2/3" in _last(ready)


def test_missing_ai_key_is_reported_when_entering(bot) -> None:
    _login(bot)
    _text(bot, "🛂 Патент PDF")
    assert "ai калити йўқ" in _last(bot).lower()


# ------------------------------------------------------------ hostel flow


def test_hostel_asks_for_both_dates(ready, monkeypatch) -> None:
    seen = {}

    def fake_generate(target, passport, patent, back, *,
                      registration_expiry, registration_start):
        seen["start"] = registration_start
        seen["expiry"] = registration_expiry
        out = paths.output_dir() / "hostel.pdf"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"%PDF-1.4\n")

        class R:
            pdf_path = out

        return R()

    monkeypatch.setattr(ready.ctl()["hostel"], "generate_from_images", fake_generate)

    _text(ready, "🛏️ ХОСТЕЛ")
    _pick(ready, 0)
    _photo(ready)
    _text(ready, "✅ Тайёрла")
    assert "БОШЛАНИШ" in _last(ready)
    _text(ready, "27.07.2026")
    assert "ТУГАШ" in _last(ready)
    _text(ready, "25.10.2026")
    assert seen == {"start": date(2026, 7, 27), "expiry": date(2026, 10, 25)}


# ------------------------------------------------------- no-target modules


def test_jpg_to_pdf_needs_neither_ai_nor_a_target(bot) -> None:
    _login(bot)          # deliberately no AI key
    _text(bot, "🖼️ JPG→PDF")
    assert "расмларни" in _last(bot).lower()


def test_summa_module_answers_in_words(bot) -> None:
    _login(bot)
    _text(bot, "🔢 СУММА-ДАТА")
    _text(bot, "27500,50")
    assert "Двадцать семь тысяч пятьсот" in _all(bot)
    assert not bot.files


def test_summa_module_handles_a_date(bot) -> None:
    _login(bot)
    _text(bot, "🔢 СУММА-ДАТА")
    _text(bot, "25.07.2026")
    assert "июля" in _all(bot)


# ---------------------------------------------------------------- misc


def test_cancel_resets(ready) -> None:
    _text(ready, "🏠 Регистрация")
    _text(ready, "❌ Бекор")
    assert ready._state[CHAT]["mode"] is None
    _photo(ready)
    assert "бўлимни танланг" in _last(ready).lower()


def test_module_failure_is_reported_not_crashed(ready, monkeypatch) -> None:
    def boom(*a, **k):
        raise RuntimeError("gemini down")

    monkeypatch.setattr(ready.ctl()["reg"], "generate_from_images", boom)
    _text(ready, "🏠 Регистрация")
    _pick(ready, 0)
    _photo(ready)
    _text(ready, "✅ Тайёрла")
    _text(ready, "15.10.2026")
    assert "Хато" in _all(ready)
    assert ready._state[CHAT]["mode"] is None


def test_patent_now_asks_for_the_date(ready, monkeypatch) -> None:
    """Every producing module asks the date — patent used to skip it."""
    seen = {}

    def fake_generate(target, passport, patent, back, *, form_date, profession):
        seen["form_date"] = form_date

        class R:
            pdf_path = paths.output_dir() / "p.pdf"
            reg_number = "123"
        R.pdf_path.parent.mkdir(parents=True, exist_ok=True)
        R.pdf_path.write_bytes(b"%PDF-1.4\n")
        return R()

    monkeypatch.setattr(ready.ctl()["process"], "generate_from_images", fake_generate)
    _text(ready, "🛂 Патент PDF")
    _pick(ready, 0)
    _photo(ready)
    _text(ready, "✅ Тайёрла")
    assert "сана" in _last(ready).lower()  # asked, did not run yet
    _text(ready, "26.07.2026")
    assert seen["form_date"] == date(2026, 7, 26)


def test_tapping_run_at_a_date_uses_today(ready, monkeypatch) -> None:
    seen = {}

    def fake_generate(target, passport, patent, back, *, form_date, profession):
        seen["form_date"] = form_date

        class R:
            pdf_path = paths.output_dir() / "p2.pdf"
            reg_number = "1"
        R.pdf_path.parent.mkdir(parents=True, exist_ok=True)
        R.pdf_path.write_bytes(b"%PDF-1.4\n")
        return R()

    monkeypatch.setattr(ready.ctl()["process"], "generate_from_images", fake_generate)
    _text(ready, "🛂 Патент PDF")
    _pick(ready, 0)
    _photo(ready)
    _text(ready, "✅ Тайёрла")   # opens the date question
    _text(ready, "✅ Тайёрла")   # accept the suggested (today)
    assert seen["form_date"] == date.today()


# ----------------------------------------------------- umumiy / dover


def _pdf(bot, chat_id: int = CHAT) -> None:
    bot._handle({"update_id": 1, "message": {
        "chat": {"id": chat_id},
        "document": {"file_id": "d1", "mime_type": "application/pdf",
                     "file_name": "dogovor.pdf"}}})


def test_umumiy_takes_a_pdf_then_photos(ready, monkeypatch) -> None:
    seen = {}

    def fake_generate(source, passport, patent, *, form_date, output_dir=None):
        seen["source"] = Path(source)
        seen["form_date"] = form_date

        class R:
            pdf_path = paths.output_dir() / "umumiy_out.pdf"
            replacements = 7
            surname = "ИСАКОВ"
        R.pdf_path.parent.mkdir(parents=True, exist_ok=True)
        R.pdf_path.write_bytes(b"%PDF-1.4\n")
        return R()

    monkeypatch.setattr(ready.ctl()["umumiy"], "generate", fake_generate)
    monkeypatch.setattr(ready.ctl()["ocr"], "read_documents",
                        lambda *a, **k: (object(), None))

    _text(ready, "♻️ УМУМИЙ")
    _pdf(ready)
    assert "PDF қабул қилинди" in _last(ready)
    _photo(ready)
    _text(ready, "✅ Тайёрла")
    assert "сана" in _last(ready).lower()
    _text(ready, "26.07.2026")
    assert seen["form_date"] == date(2026, 7, 26)
    assert seen["source"].read_bytes() == b"fake-image-bytes"
    assert ready.files, "no PDF was sent back"


def test_umumiy_run_without_a_pdf_says_so(ready) -> None:
    _text(ready, "♻️ УМУМИЙ")
    _photo(ready)
    _text(ready, "✅ Тайёрла")
    assert "pdf" in _last(ready).lower()


def test_dover_asks_type_description_and_date(ready, monkeypatch) -> None:
    from src.services.dover_service import DOVER_TYPES

    seen = {}

    def fake_generate(images, *, doc_type, description, form_date, output_dir=None):
        seen.update(doc_type=doc_type, description=description, form_date=form_date)

        class R:
            pdf_path = paths.output_dir() / "dover.pdf"
            docx_path = paths.output_dir() / "dover.docx"
            series = "77 AB 1234567"
            reestr = 12854
        for p in (R.pdf_path, R.docx_path):
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"x")
        return R()

    monkeypatch.setattr(ready.ctl()["dover"], "generate_from_images", fake_generate)

    _text(ready, "📜 Доверенность")
    _photo(ready)
    _text(ready, "✅ Тайёрла")
    assert "тури" in _last(ready).lower()
    _text(ready, "2")                       # pick by number
    _text(ready, "Ака укасига машина учун")
    _text(ready, "26.07.2026")
    assert seen["doc_type"] == DOVER_TYPES[1]
    assert seen["description"] == "Ака укасига машина учун"
    assert seen["form_date"] == date(2026, 7, 26)
    assert len(ready.files) == 2            # PDF + Word


def test_modules_that_reject_pdf_say_so(ready) -> None:
    _text(ready, "🏠 Регистрация")
    _pick(ready, 0)
    _pdf(ready)
    assert "pdf қабул қилмайди" in _last(ready).lower()


def test_dms_flow_asks_everything_then_runs(ready, monkeypatch) -> None:
    seen = {}

    def fake_generate(image, *, start_date, phone, address, region):
        seen.update(start_date=start_date, phone=phone, address=address,
                    region=region)
        out = paths.output_dir() / "dms.pdf"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"%PDF-1.4\n")

        class R:
            pdf_path = out
            policy_number = "50682676085"
            start_date = date(2026, 7, 27)
            end_date = date(2027, 7, 26)

        return R()

    monkeypatch.setattr(ready.ctl()["dms"], "generate_from_images", fake_generate)

    _text(ready, "🏥 ДМС")
    _photo(ready)
    _text(ready, "✅ Тайёрла")
    assert "БОШЛАНИШ" in _last(ready)
    _text(ready, "27.07.2026")
    _text(ready, "+79683941008")
    _text(ready, "Москва, Вяземская 1к1")
    _text(ready, "Москва")
    assert seen["start_date"] == date(2026, 7, 27)
    assert seen["phone"] == "+79683941008"
    assert seen["address"] == "Москва, Вяземская 1к1"
    assert "50682676085" in _all(ready)
    assert ready.files


def test_inn_flow_asks_the_number_and_date(ready, monkeypatch) -> None:
    seen = {}

    def fake_generate(image, *, inn, form_date):
        seen.update(inn=inn, form_date=form_date)
        out = paths.output_dir() / "inn.pdf"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"%PDF-1.4\n")

        class R:
            pdf_path = out
            inn = "770912345678"
            surname = "ИСАКОВ"

        return R()

    monkeypatch.setattr(ready.ctl()["inn"], "generate_from_image", fake_generate)

    _text(ready, "🔢 ИНН")
    _photo(ready)
    _text(ready, "✅ Тайёрла")
    assert "ИНН рақами" in _last(ready)
    _text(ready, "770912345678")
    _text(ready, "27.07.2026")
    assert seen == {"inn": "770912345678", "form_date": date(2026, 7, 27)}
    assert "770912345678" in _all(ready)
    assert ready.files


# --------------------------------------------------------- СТРАХОВКА flow


class _FakeTemplate:
    name = "РЕСО-Гарантия"


def _fake_policy(seen):
    def generate(template, sts_front, sts_back, licences, *, start,
                 unlimited=None, policy_holder=""):
        seen.update(template=template, front=sts_front, back=sts_back,
                    licences=list(licences), start=start,
                    policy_holder=policy_holder)
        out = paths.output_dir() / "osago.docx"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"PK\x03\x04")

        class R:
            docx_path = out
            pdf_path = None
            plate = "Х420КС797"
            drivers = len(seen["licences"])
            notes = ["Полис серия/номерини страховая компания беради"]

        return R()

    return generate


def test_insurance_flow_splits_the_photos_and_asks_the_dates(ready, monkeypatch) -> None:
    seen = {}
    ctl = ready.ctl()["insurance"]
    monkeypatch.setattr(ctl, "templates", lambda: [_FakeTemplate()])
    monkeypatch.setattr(ctl, "generate_from_images", _fake_policy(seen))

    _text(ready, "🚗 СТРАХОВКА")
    _pick(ready, 0)
    for _ in range(4):          # СТС олд · СТС орқа · 2 та права
        _photo(ready)
    assert "Права 2" in _last(ready), "the photos are not labelled in order"

    _text(ready, "✅ Тайёрла")
    assert "БОШЛАНИШ" in _last(ready)
    _text(ready, "10.07.2026")
    assert "Страхователь" in _last(ready)
    _text(ready, "✅ Тайёрла")   # left blank — the СТС owner is used

    assert seen["start"] == date(2026, 7, 10)
    assert seen["back"] is not None
    assert len(seen["licences"]) == 2
    assert seen["policy_holder"] == ""
    assert "Х420КС797" in _all(ready)
    assert "лица, допущенные" in _all(ready)
    assert ready.files, "the policy was never sent back"


def test_insurance_without_licences_is_unlimited_cover(ready, monkeypatch) -> None:
    seen = {}
    ctl = ready.ctl()["insurance"]
    monkeypatch.setattr(ctl, "templates", lambda: [_FakeTemplate()])
    monkeypatch.setattr(ctl, "generate_from_images", _fake_policy(seen))

    _text(ready, "🚗 СТРАХОВКА")
    _pick(ready, 0)
    _photo(ready)
    _photo(ready)
    _text(ready, "✅ Тайёрла")
    _text(ready, "10.07.2026")
    _text(ready, "✅ Тайёрла")

    assert seen["licences"] == []
    assert "без ограничения" in _all(ready)


# ------------------------------------------------------ ЎЗ ШАБЛОНИМ flow


def test_shablon_flow_fills_a_template_saved_on_the_computer(
        ready, monkeypatch, tmp_path) -> None:
    from src.controllers.template_controller import SavedTemplate

    saved = tmp_path / "anketa.pdf"
    saved.write_bytes(b"%PDF-1.4\n")
    seen = {}

    def fake_fill(study, template, out, passport, patent=None, *,
                  form_date, profession):
        seen.update(template=template, patent=patent, form_date=form_date,
                    profession=profession)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"%PDF-1.4\n")

        class R:
            path = out
            written = {"surname": "ИСАКОВ"}
            problems = []

        return R()

    ctl = ready.ctl()["template"]
    monkeypatch.setattr(ctl, "saved_templates",
                        lambda: [SavedTemplate("Анкета", "pdf", saved)])
    monkeypatch.setattr(ctl, "study", lambda source: (object(), True))
    monkeypatch.setattr(ctl, "fill_from_images", fake_fill)

    _text(ready, "📐 ЎЗ ШАБЛОНИМ")
    _pick(ready, 0)
    _photo(ready)
    _text(ready, "✅ Тайёрла")
    assert "санаси" in _last(ready).lower()
    _text(ready, "27.07.2026")
    _text(ready, "Штукатур")

    assert seen["template"] == saved
    assert seen["patent"] is None
    assert seen["form_date"] == date(2026, 7, 27)
    assert seen["profession"] == "Штукатур"
    assert ready.files, "the filled form was never sent back"


def test_shablon_with_nothing_saved_says_so(ready, monkeypatch) -> None:
    monkeypatch.setattr(ready.ctl()["template"], "saved_templates", list)
    _text(ready, "📐 ЎЗ ШАБЛОНИМ")
    assert "бўш" in _last(ready)


# ---------------------------------------------------- ПАТЕНТ · РАЗРЕШЕНИЯ


def test_patent_card_is_the_badge_on_the_other_blank(ready, monkeypatch) -> None:
    """The desktop keeps ПАТЕНТ one-to-one with БЕЙДЖИК by inheritance; the bot
    must ask the same questions and reach the patent controller, not the badge."""
    from src.controllers.ofis_modules import BY_KEY

    assert BY_KEY["patent_card"].asks == BY_KEY["beydjik"].asks
    seen = {}

    def fake_generate(image, **kwargs):
        seen.update(kwargs)
        out = paths.output_dir() / "patent_card.pdf"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"%PDF-1.4\n")

        class R:
            pdf_path = out
            pr_number = "0001234"
            surname = "ТОШПУЛАТОВ"
            region = "77"

        return R()

    monkeypatch.setattr(ready.ctl()["patent"], "generate_from_image", fake_generate)
    monkeypatch.setattr(ready.ctl()["beydjik"], "generate_from_image",
                        lambda *a, **k: pytest.fail("the badge ran instead"))

    _text(ready, "🩷 ПАТЕНТ")
    _photo(ready)
    _photo(ready)
    _text(ready, "✅ Тайёрла")
    for answer in ("77", "770912345678", "770912345678", "ООО СФЕРА", "-", ""):
        _text(ready, answer if answer else "✅ Тайёрла")
    _text(ready, "27.07.2026")

    assert seen["region"] == "77"
    assert seen["issue_date"] == date(2026, 7, 27)
    assert seen["photo_path"] is not None, "the worker's photograph was dropped"
    assert "ТОШПУЛАТОВ" in _all(ready)
    assert ready.files


def test_razreshenie_flow_reuses_the_remembered_firm(ready, monkeypatch) -> None:
    from src.services.razreshenie_service import Firm

    seen = {}

    def fake_generate(**kwargs):
        seen.update(kwargs)

        class R:
            pdf = b"%PDF-1.4\n"
            filename = "Сейтимов.pdf"
            seria = "77"
            number = "1354594"
            back_number = "0035454"
            valid_from = date(2026, 7, 10)
            valid_to = date(2027, 7, 9)

        return R()

    ctl = ready.ctl()["razreshenie"]
    monkeypatch.setattr(ctl, "read_passport", lambda image: {
        "surname": "СЕЙТИМОВ", "name": "АЗИЗ", "patronymic": "",
        "birth_date": "01.02.1990", "citizenship": "Узбекистан",
        "document": "A2311191"})
    monkeypatch.setattr(ctl, "firm", lambda: Firm("ООО СФЕРА", "7723652154"))
    monkeypatch.setattr(ctl, "generate", fake_generate)

    _text(ready, "🟩 РАЗРЕШЕНИЯ")
    _photo(ready)
    _photo(ready)
    _text(ready, "✅ Тайёрла")
    assert "должность" in _last(ready).lower()
    _text(ready, "Штукатур")
    _text(ready, "10.07.2026")
    _text(ready, "772365215425")
    _text(ready, "✅ Тайёрла")      # фирма номи — бўш
    _text(ready, "✅ Тайёрла")      # фирма ИННси — бўш

    assert seen["activity"] == "Штукатур"
    assert seen["valid_from"] == date(2026, 7, 10)
    assert seen["inn"] == "772365215425"
    assert seen["birth_date"] == date(1990, 2, 1), "the date arrived as text"
    assert seen["firm_name"] == "ООО СФЕРА", "the remembered firm was not used"
    assert seen["firm_inn"] == "7723652154"
    assert seen["photo"], "the worker's photograph was dropped"
    assert "1354594" in _all(ready) and "0035454" in _all(ready)
    assert ready.files and ready.files[-1].name == "Сейтимов.pdf"


def test_razreshenie_keeps_an_earlier_card_of_the_same_surname(
        ready, monkeypatch) -> None:
    from src.controllers.ofis_modules import _free_path

    folder = paths.output_dir() / "razreshenie"
    first = _free_path(folder, "Сейтимов.pdf")
    first.write_bytes(b"%PDF-1.4\n")
    second = _free_path(folder, "Сейтимов.pdf")

    assert second.name == "Сейтимов (2).pdf"
    assert first.exists(), "the first card was overwritten"


def test_the_receipt_section_is_deliberately_not_on_the_phone() -> None:
    """ЧЕК makes up the payment's own proof — a random код авторизации on a
    bank-receipt background. It stays where it is; the bot does not mail it."""
    from src.controllers.ofis_modules import BY_KEY

    assert "chek" not in BY_KEY
