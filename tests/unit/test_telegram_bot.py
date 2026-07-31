"""Telegram bot conversation flow, driven through a fake transport.

No network: ``_api``/``_send``/``_send_file``/``_download`` are replaced, so
every test exercises the real state machine and only stubs the wire.
"""

from __future__ import annotations

import tempfile
from datetime import date, datetime
from pathlib import Path

import pytest

from src.config import paths

CHAT = 7


@pytest.fixture()
def bot(monkeypatch):
    # both roots: paths.data_dir() reads LOCALAPPDATA on Windows and
    # XDG_DATA_HOME elsewhere. With only one of them set these tests read the
    # real machine's AppData — the settings, the uploaded blanks, the address
    # book — and then pass or fail depending on what happens to be on it.
    sandbox = tempfile.mkdtemp()
    monkeypatch.setenv("XDG_DATA_HOME", sandbox)
    monkeypatch.setenv("LOCALAPPDATA", sandbox)
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
    "nav.chek": "chek",
    "nav.beydjik": "beydjik",
    "nav.patent": "patent_card",
    "nav.razreshenie": "razreshenie",
    "nav.ppu": "ppu",
    "nav.snils": "snils",
    "nav.svera": "svera",
    "nav.sertifikat": "sertifikat",
    "nav.dover": "dover",
    "nav.perevod": "perevod",
    "nav.mig": "mig",
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

#: Nothing is left off any more.
_NOT_ON_THE_PHONE: set[str] = set()


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


# ---------------------------------------------------------------- ЧЕК flow


def _chek_ready(ready, monkeypatch, *, company="357852345266REGD"):
    ctl = ready.ctl()["chek"]
    ctl.set_company_id(company)
    monkeypatch.setattr(ctl, "read_patent_fields", lambda image: {
        "fam": "СЕЙТИМОВ", "ism": "АЗИЗ", "otch": "",
        "inn": "772365215425"})
    return ctl


def _chek_answers(ready, *, avtoriz="357852") -> None:
    _text(ready, "15000,50")
    _text(ready, "1234")
    _text(ready, avtoriz)
    _text(ready, "27.07.2026")
    _text(ready, "14:30:05")


def test_chek_flow_passes_the_typed_authorisation_code_through(
        ready, monkeypatch) -> None:
    seen = {}

    def fake_generate(**kwargs):
        seen.update(kwargs)
        return b"%PDF-1.4\n", "Документ-2026-07-27-14-30-05.pdf"

    ctl = _chek_ready(ready, monkeypatch)
    monkeypatch.setattr(ctl, "generate", fake_generate)

    _text(ready, "🧾 ЧЕК")
    _photo(ready)
    _text(ready, "✅ Тайёрла")
    assert "Сумма" in _last(ready)
    _chek_answers(ready)

    assert seen["avtoriz"] == "357852", "the operator's code never arrived"
    assert (seen["rub"], seen["kop"]) == (15000, 50)
    assert seen["card4"] == "1234"
    assert seen["when"] == datetime(2026, 7, 27, 14, 30, 5)
    assert seen["fam"] == "СЕЙТИМОВ"
    assert ready.files


def test_chek_says_the_company_id_is_missing_before_asking_anything(
        ready, monkeypatch) -> None:
    """The refusal comes on the way IN, not after five answered questions.

    It used to be raised inside the runner, so the operator was asked the sum,
    the card, the authorisation code, the day and the hour — and only then told
    the company id was missing, in one line that immediately scrolled away
    behind the section menu. On the phone that reads as «ЧЕК asks for the
    documents and never sends the PDF».
    """
    _chek_ready(ready, monkeypatch, company="")

    _text(ready, "🧾 ЧЕК")

    assert "компания коди" in _last(ready).lower()
    # «сумма» alone is no proof — СУММА-ДАТА is a section in the printed menu.
    assert "сумма (₽)" not in _all(ready).lower(), "a question was still asked"
    _photo(ready)
    assert not ready.files, "a receipt printed with no company id"


def test_chek_really_produces_the_pdf(ready, monkeypatch) -> None:
    """End to end with the real renderer — the section the operator reported.

    Everything above stubs ``generate``; this one does not, so a break anywhere
    between the answers and the finished file is caught here.
    """
    _chek_ready(ready, monkeypatch)
    _text(ready, "🧾 ЧЕК")
    _photo(ready)
    _text(ready, "✅ Тайёрла")
    _chek_answers(ready)

    assert len(ready.files) == 1, _all(ready)[-400:]
    assert ready.files[0].suffix.lower() == ".pdf"
    assert ready.files[0].read_bytes()[:5] == b"%PDF-"


def test_chek_refuses_a_missing_authorisation_code(ready, monkeypatch) -> None:
    """The whole point of the section reaching the phone: the code is copied
    off the bank's confirmation, never generated."""
    _chek_ready(ready, monkeypatch)
    _text(ready, "🧾 ЧЕК")
    _photo(ready)
    _text(ready, "✅ Тайёрла")
    _chek_answers(ready, avtoriz="✅ Тайёрла")   # left blank
    assert "код авторизации" in _all(ready).lower()
    assert not ready.files, "a receipt printed with an empty код авторизации"


def test_the_receipt_never_invents_its_own_proof() -> None:
    """No randomness anywhere in the receipt path — the authorisation code and
    the company id both come from outside the program."""
    from pathlib import Path as _P

    for name in ("src/pdf/chek_renderer.py", "src/controllers/chek_controller.py"):
        source = _P(name).read_text(encoding="utf-8")
        for generator in ("import random", "random.", "randint", "getrandbits",
                          "uuid4", "secrets."):
            assert generator not in source, f"{name} still makes something up"


# ------------------------------- ТРУД ППУ, the blanks, and a new address
# The office asked for these three on the phone: the ПЕРЕВОД sheets, ТРУД ППУ,
# and adding an address without going to the computer.


def _blank_pdf(path: Path, width: float = 842.0, height: float = 474.0) -> Path:
    import fitz

    doc = fitz.open()
    doc.new_page(width=width, height=height)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))
    return path


def _pdf_doc(bot, chat_id: int = CHAT) -> None:
    bot._handle({"update_id": 1, "message": {
        "chat": {"id": chat_id},
        "document": {"file_id": "d9", "mime_type": "application/pdf",
                     "file_name": "blank.pdf"}}})


def test_trud_ppu_runs_on_the_phone(ready, monkeypatch, tmp_path) -> None:
    desktop = tmp_path / "desktop"
    desktop.mkdir()
    monkeypatch.setattr("src.services.ppu_service.paths.desktop_dir",
                        lambda: desktop)
    monkeypatch.setattr("src.services.trud_ppu_service.paths.desktop_dir",
                        lambda: desktop)
    ready.ctl()["ppu"].add_template(
        "ОФИС", _blank_pdf(tmp_path / "f.pdf"), _blank_pdf(tmp_path / "b.pdf"))
    trud = ready.ctl()["trud_ppu"]
    trud.add_template("ОФИС", _blank_pdf(tmp_path / "p2.pdf", 1600.0, 900.0),
                      _blank_pdf(tmp_path / "p3.pdf", 899.0, 1599.0))
    monkeypatch.setattr(trud, "read_contract", lambda pdf: {
        "contract_date": "20.09.2024", "firm": "ООО “ЭКСПЕРТ”",
        "surname": "МУРТАЗОЕВ", "name": "АББОСХОН",
        "patronymic": "АБДУЛОХОНОВИЧ", "birth_date": "03.03.1990",
        "gender": "Мужской", "citizenship": "УЗБЕКИСТАН",
        "document": "FA 7822242"})
    monkeypatch.setattr(trud, "read_uved", lambda pdf: {
        "uved_number": "4785796716",
        "uved_fio": "Муртазоев Аббосхон Абдулохонович"})
    monkeypatch.setattr(trud, "read_patent", lambda front, back=None: {
        "patent_series": "77", "patent_number": "2400328451",
        "patent_issue": "18.07.2024"})

    _text(ready, "🧷 ТРУД ППУ")
    _pick(ready, 0)
    _text(ready, "✅ Тайёрла")
    assert "2 та pdf" in _last(ready).lower(), "it must not start without them"

    _pdf(ready)
    assert "1/2" in _last(ready) and "яна 1" in _last(ready).lower()
    _pdf(ready)
    assert "2/2" in _last(ready)
    _photo(ready)                       # патент олд
    _photo(ready)                       # патент орқа
    _text(ready, "✅ Тайёрла")

    assert "2400328451" in _all(ready) and "ЭКСПЕРТ" in _all(ready)
    assert len(ready.files) == 3, "ТРУД ППУ is three sheets"
    assert all(f.suffix == ".png" and f.parent == desktop for f in ready.files)


def test_the_perevod_sheets_can_be_uploaded_from_the_phone(ready, tmp_path) -> None:
    """The three sheets used to be loadable only at the computer."""
    from src.services.perevod_service import blank_path, blanks

    assert not any(blanks()), "the sandbox should start with no blanks"

    _text(ready, "🌐➕ ПЕРЕВОД бланкаси")
    rows = ready.sent[-1][1]["inline_keyboard"]
    assert len(rows) == 3, "one row per sheet"
    assert "1 —" in rows[0][0]["text"] and "3 —" in rows[2][0]["text"]

    _pick(ready, 1)                     # 2-саҳифа
    _pdf_doc(ready)                     # a PDF blank, not a photograph
    assert "қабул қилинди" in _last(ready)
    _text(ready, "✅ Тайёрла")

    assert blank_path(2) is not None, "the sheet was not stored"
    assert blank_path(1) is None and blank_path(3) is None
    assert "2-бланка юкланди" in _all(ready)

    # a picture works just as well — the office's own sheets are JPEGs
    _text(ready, "🌐➕ ПЕРЕВОД бланкаси")
    _pick(ready, 0)
    _photo(ready)
    _text(ready, "✅ Тайёрла")
    assert blank_path(1) is not None


def test_perevod_offers_the_blank_button_next_to_the_work(ready) -> None:
    _text(ready, "🌐 ПЕРЕВОД")
    # ПЕРЕВОД has no list to pick from, so it goes straight to collecting —
    # the blanks are reached from their own button in the menu
    assert "ҳужжат расмларини" in _last(ready).lower()
    from src.controllers.ofis_modules import BY_KEY

    assert BY_KEY["perevod"].add_key == "perevod_blank"


def test_registration_offers_adding_an_address_and_then_lists_it(
        ready, monkeypatch) -> None:
    """«🏠 Регистрация» used to be a dead end when the address book was empty,
    and offered no way to add one. Now the pick list carries the button."""
    before = {a.label for a in ready.ctl()["reg_addr"].list()}
    monkeypatch.setattr(ready.ctl()["reg"], "addresses",
                        lambda: [a for a in ready.ctl()["reg_addr"].list()
                                 if a.label not in before])

    _text(ready, "🏠 Регистрация")
    rows = ready.sent[-1][1]["inline_keyboard"]
    assert rows[-1][0]["callback_data"] == "pick:add"
    assert "янги манзил" in rows[-1][0]["text"].lower()

    ready._handle({"update_id": 1, "callback_query": {
        "id": "cq", "message": {"chat": {"id": CHAT}}, "data": "pick:add"}})
    assert "номи" in _last(ready).lower()

    for answer in ("ПАРКОВАЯ 55", "Г МОСКВА", "✅ Тайёрла", "МОСКВА",
                   "5-Я ПАРКОВАЯ", "55", "✅ Тайёрла", "✅ Тайёрла", "6",
                   "ПОПОВ ВЛАДИМИР ГЕННАДЬЕВИЧ", "02/770-1234"):
        _text(ready, answer)

    assert "манзил қўшилди" in _all(ready).lower()
    added = [a for a in ready.ctl()["reg_addr"].list() if a.label not in before]
    assert [a.label for a in added] == ["ПАРКОВАЯ 55"]
    assert "5-Я ПАРКОВАЯ" in added[0].address_text
    assert added[0].template_path.exists(), "the template was not built"
    _text(ready, "🏠 Регистрация")
    assert "манзилни танланг" in _last(ready).lower()


def test_a_new_address_needs_more_than_a_name(ready) -> None:
    before = ready.ctl()["reg_addr"].count()
    _text(ready, "🏠➕ Янги манзил")
    for _ in range(11):
        _text(ready, "✅ Тайёрла")
    assert "манзил бўш" in _all(ready).lower()
    assert ready.ctl()["reg_addr"].count() == before, "an empty address was saved"


# ---------------------------------------------------------- ППУ · СНИЛС


def test_ppu_takes_everything_off_the_registration(ready, monkeypatch, tmp_path) -> None:
    """Only the start date is typed; the Ф.И.О., passport, address and the end
    date all come off the регистрация the office already issued."""
    blank = tmp_path / "standart"
    blank.mkdir()
    seen = {}

    def fake_generate(**kwargs):
        seen.update(kwargs)

        class R:
            pages = [b"\x89PNG-front", b"\x89PNG-back"]
            saved: list = []
            pdf = b"%PDF-1.4\n"
            passport = "AA 1234567"
            valid_from = date(2026, 7, 27)
            valid_to = date(2026, 10, 25)

        return R()

    ctl = ready.ctl()["ppu"]
    monkeypatch.setattr(ctl, "templates", lambda: [blank])
    monkeypatch.setattr(ctl, "read_registration", lambda image: {
        "surname": "СЕЙТИМОВ", "name": "АЗИЗ", "patronymic": "",
        "birth_date": "01.02.1990", "gender": "муж", "citizenship": "Узбекистан",
        "document": "AA 1234567", "address": "Москва, Вяземская 1к1",
        "stay_from": "27.07.2026", "stay_to": "25.10.2026"})
    monkeypatch.setattr(ctl, "generate", fake_generate)

    _text(ready, "🧾 ППУ")
    _pick(ready, 0)
    _photo(ready)
    _photo(ready)
    _text(ready, "✅ Тайёрла")
    assert "БОШЛАНИШ" in _last(ready)
    _text(ready, "27.07.2026")
    _text(ready, "✅ Тайёрла")        # тугаш санаси — регистрациядан

    assert seen["template"] == blank
    assert seen["valid_from"] == date(2026, 7, 27)
    assert seen["valid_to"] == date(2026, 10, 25), "the end date was not read"
    assert seen["address"] == "Москва, Вяземская 1к1"
    assert seen["photo"], "the worker's photograph was dropped"
    assert len(ready.files) == 2, "both sides must come back"
    assert all(f.suffix == ".png" for f in ready.files)


def test_ppu_says_so_when_the_end_date_could_not_be_read(
        ready, monkeypatch, tmp_path) -> None:
    blank = tmp_path / "standart"
    blank.mkdir()

    class R:
        pages = [b"\x89PNG"]
        pdf = b"%PDF-1.4\n"
        passport = "AA 1234567"
        valid_from = date(2026, 7, 27)
        valid_to = None

    ctl = ready.ctl()["ppu"]
    monkeypatch.setattr(ctl, "templates", lambda: [blank])
    monkeypatch.setattr(ctl, "read_registration", lambda image: {
        "surname": "СЕЙТИМОВ", "name": "АЗИЗ", "document": "AA 1234567",
        "stay_from": "27.07.2026", "stay_to": ""})
    monkeypatch.setattr(ctl, "generate", lambda **k: R())

    _text(ready, "🧾 ППУ")
    _pick(ready, 0)
    _photo(ready)
    _photo(ready)
    _text(ready, "✅ Тайёрла")
    _text(ready, "27.07.2026")
    _text(ready, "✅ Тайёрла")
    assert "тугаш санаси" in _all(ready).lower()


def test_ppu_with_no_blank_uploaded_says_so(ready, monkeypatch) -> None:
    monkeypatch.setattr(ready.ctl()["ppu"], "templates", list)
    _text(ready, "🧾 ППУ")
    assert "бўш" in _last(ready)


def test_snils_flow_keeps_the_last_number_when_left_blank(
        ready, monkeypatch, tmp_path) -> None:
    blank = tmp_path / "standart"
    blank.mkdir()
    seen = {}

    def fake_generate(**kwargs):
        seen.update(kwargs)

        class R:
            pdf = b"%PDF-1.4\n"
            filename = "Сейтимов СНИЛС.pdf"
            snils = "123-456-789 01"
            reg_date = date(2026, 7, 27)

        return R()

    ctl = ready.ctl()["snils"]
    monkeypatch.setattr(ctl, "templates", lambda: [blank])
    monkeypatch.setattr(ctl, "read_passport", lambda image: {
        "surname": "СЕЙТИМОВ", "name": "АЗИЗ", "patronymic": "",
        "birth_date": "01.02.1990", "birth_place": "Узбекистан",
        "gender": "муж"})
    monkeypatch.setattr(ctl, "generate", fake_generate)

    _text(ready, "🔖 СНИЛС")
    _pick(ready, 0)
    _photo(ready)
    _text(ready, "✅ Тайёрла")
    assert "сана" in _last(ready).lower()
    _text(ready, "27.07.2026")
    _text(ready, "✅ Тайёрла")        # рақам — охиргиси

    assert seen["reg_date"] == date(2026, 7, 27)
    assert seen["snils"] == "", "a blank answer must mean «the last number»"
    assert seen["birth_date"] == date(1990, 2, 1), "the date arrived as text"
    assert seen["template"] == blank
    assert "123-456-789 01" in _all(ready)
    assert ready.files and ready.files[-1].name == "Сейтимов СНИЛС.pdf"


# --------------------------------------------------------------------- МИГ


def test_mig_asks_for_the_code_and_passes_it_on(ready, monkeypatch) -> None:
    """The КОД is printed at the four corners of the issue date.

    The phone never asked for it, and the runner never passed it, so every card
    made from the bot came back with those four corners empty while the same
    card made on the computer had them.
    """
    from src.controllers.ofis_modules import BY_KEY

    prompts = [a.prompt for a in BY_KEY["mig"].asks]
    assert any("КОД" in p for p in prompts), f"the bot never asks: {prompts}"

    seen = {}
    ctl = ready.ctl()["mig"]
    monkeypatch.setattr(ctl, "templates", lambda: [Path("СФЕРА.pdf")])
    monkeypatch.setattr(ctl, "stamps", lambda: [])
    monkeypatch.setattr(ctl, "read_passport", lambda image: {
        "surname": "ИСАКОВ", "name": "ШАХБОЗ", "patronymic": "",
        "birth_date": "01.01.1990", "citizenship": "УЗБЕКИСТАН",
        "passport": "AA1234567", "gender": "male"})

    class _Made:
        saved = Path("card.pdf")

    monkeypatch.setattr(ctl, "generate",
                        lambda **kw: seen.update(kw) or _Made())
    monkeypatch.setattr(ready, "_send_file", lambda cid, p, caption="": None)

    _text(ready, "🪪 МИГ — ИШЧИ КАРТАСИ")
    _pick(ready, 0)
    _photo(ready)
    _text(ready, "✅ Тайёрла")
    for answer in ("46 26", "0367598", "✅ Тайёрла", "РАЗНОРАБОЧИЙ",
                   "01.08.2026", "01.11.2026", "15  03  26", "4821"):
        _text(ready, answer)

    assert seen.get("code") == "4821", f"the code never reached the card: {seen}"
    assert seen.get("issued") == "15  03  26"
    assert seen.get("series") == "46 26"
