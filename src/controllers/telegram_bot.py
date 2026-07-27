"""Telegram bot — drive the whole of OFIS from the phone.

Workers send their passport/patent photos to the operator over WhatsApp or
Telegram; the operator forwards them to this bot and gets the finished PDFs
back in the chat, while the office computer does the actual work. Runs as a
daemon thread inside the desktop app (long polling — no server, no public IP
needed). Access is protected by a password: the operator sends
``/start <parol>`` once per chat; authorized chat ids persist in settings.

Every module is one entry in :data:`_MODULES` — button label, what has to be
picked first, how many photos, which extra questions to ask, and how to run it.
Adding a module to the bot means adding a row there, nothing else.

No third-party dependency — raw Bot API over urllib.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from src.common.errors import OfisError
from src.common.logging import get_logger

log = get_logger(__name__)

KEY_TOKEN = "tg.bot_token"
KEY_PASSWORD = "tg.password"
KEY_ALLOWED = "tg.allowed_chats"
KEY_WEBAPP = "tg.webapp_url"

_BTN_RUN = "✅ Тайёрла"
_BTN_CANCEL = "❌ Бекор"
_BTN_MENU = "☰ Бўлимлар"

# ---------------------------------------------------------------- questions


@dataclass(frozen=True)
class Ask:
    """One extra question asked after the photos, before the work starts."""

    field: str
    prompt: str
    kind: str = "date"            # date | text
    default_days: int | None = None  # date default = today + N days


def _parse_date(text: str) -> date | None:
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------- modules


@dataclass(frozen=True)
class Module:
    key: str
    button: str
    run: Callable[["TelegramBot", int, dict], list[Path]]
    targets: Callable[[dict], list] | None = None
    target_prompt: str = "Танланг:"
    photo_prompt: str = "Расмларни юборинг."
    photo_labels: tuple[str, ...] = ()
    min_photos: int = 1
    asks: tuple[Ask, ...] = ()
    text_only: bool = False       # no photos — answers questions instead
    needs_ai: bool = True


def _photos(state: dict) -> tuple[bytes, bytes | None, bytes | None]:
    ph = state["photos"]
    return ph[0], (ph[1] if len(ph) > 1 else None), (ph[2] if len(ph) > 2 else None)


def _run_patent(bot: "TelegramBot", chat_id: int, state: dict) -> list[Path]:
    passport, patent, back = _photos(state)
    r = bot.ctl()["process"].generate_from_images(
        state["target"], passport, patent, back,
        form_date=state["answers"].get("form_date") or date.today(), profession=None)
    bot.note(chat_id, f"№ {r.reg_number}")
    return [r.pdf_path]


def _run_reg(bot: "TelegramBot", chat_id: int, state: dict) -> list[Path]:
    passport, patent, back = _photos(state)
    r = bot.ctl()["reg"].generate_from_images(
        state["target"], passport, patent, back,
        registration_expiry=state["answers"]["expiry"])
    return [r.pdf_path]


def _run_hostel(bot: "TelegramBot", chat_id: int, state: dict) -> list[Path]:
    passport, patent, back = _photos(state)
    r = bot.ctl()["hostel"].generate_from_images(
        state["target"], passport, patent, back,
        registration_expiry=state["answers"]["expiry"],
        registration_start=state["answers"]["start"])
    return [r.pdf_path]


def _run_trud(bot: "TelegramBot", chat_id: int, state: dict) -> list[Path]:
    passport, patent, back = _photos(state)
    r = bot.ctl()["trud"].generate_from_images(
        state["target"], passport, patent, back,
        form_date=date.today(), profession=None)
    return [p for p in (r.trud_path, r.uved_path, getattr(r, "hod_path", None)) if p]


def _run_svera(bot: "TelegramBot", chat_id: int, state: dict) -> list[Path]:
    from src.config import paths

    passport = state["photos"][0]
    if len(state["photos"]) < 2:
        raise OfisError("Ишчининг расмини ҳам юборинг (2-расм).")
    portrait = paths.output_dir() / "svera" / f"tg_{uuid.uuid4().hex[:8]}.jpg"
    portrait.parent.mkdir(parents=True, exist_ok=True)
    portrait.write_bytes(state["photos"][1])
    r = bot.ctl()["svera"].generate_from_images(
        state["target"], passport, portrait,
        issue_date=state["answers"].get("issue_date") or date.today())
    bot.note(chat_id, f"Удостоверение № {r.udo_number} · ПО{r.po_number}")
    return [r.pdf_path]


def _run_perevod(bot: "TelegramBot", chat_id: int, state: dict) -> list[Path]:
    r = bot.ctl()["perevod"].translate(state["photos"], doc_type="auto")
    return [p for p in (r.pdf_path, getattr(r, "docx_path", None)) if p]


def _run_photo34(bot: "TelegramBot", chat_id: int, state: dict) -> list[Path]:
    from src.config import paths

    result = bot.ctl()["photo"].process(state["photos"][0])
    out = paths.output_dir() / "photo" / f"tg_3x4_{uuid.uuid4().hex[:8]}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(result.png)
    if result.note:
        bot.note(chat_id, result.note)
    return [out]


def _run_jpg2pdf(bot: "TelegramBot", chat_id: int, state: dict) -> list[Path]:
    from src.config import paths
    from src.services.jpg2pdf_service import build_pdf

    out = paths.output_dir() / "jpg2pdf" / f"tg_{uuid.uuid4().hex[:8]}.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(build_pdf(state["photos"]))
    return [out]


def _run_summa(bot: "TelegramBot", chat_id: int, state: dict) -> list[Path]:
    from src.utils.rus_words import amount_to_words, date_to_words, format_amount, parse_amount

    raw = str(state["answers"].get("value", "")).strip()
    as_date = _parse_date(raw)
    if as_date is not None:
        bot.note(chat_id, date_to_words(as_date))
        return []
    try:
        rubles, kopecks = parse_amount(raw)
    except ValueError:
        bot.note(chat_id, "Тушунмадим. Сана (25.07.2026) ёки сумма (27500,50) ёзинг.")
        return []
    bot.note(chat_id, f"{format_amount(rubles, kopecks)}\n"
                      f"{amount_to_words(rubles, kopecks)}")
    return []


_TRIO = ("Паспорт", "Патент (олд)", "Патент (орқа)")
_TRIO_PROMPT = ("Расмларни ТАРТИБ билан юборинг:\n"
                "1️⃣ Паспорт\n2️⃣ Патент (олд)\n3️⃣ Патент (орқа)\n"
                f"Кейин «{_BTN_RUN}» босинг.")

_MODULES: tuple[Module, ...] = (
    Module("patent", "🛂 Патент PDF", _run_patent,
           targets=lambda c: c["process"].companies(),
           target_prompt="Фирмани танланг:",
           photo_prompt=_TRIO_PROMPT, photo_labels=_TRIO),
    Module("reg", "🏠 Регистрация", _run_reg,
           targets=lambda c: c["reg"].addresses(),
           target_prompt="Манзилни танланг:",
           photo_prompt=_TRIO_PROMPT, photo_labels=_TRIO,
           asks=(Ask("expiry", "Рўйхатдан ўтиш ТУГАШ санаси (КК.ОО.ЙЙЙЙ):",
                     default_days=90),)),
    Module("hostel", "🛏️ ХОСТЕЛ", _run_hostel,
           targets=lambda c: c["hostel"].addresses(),
           target_prompt="Хостелни танланг:",
           photo_prompt=_TRIO_PROMPT, photo_labels=_TRIO,
           asks=(Ask("start", "Яшаш БОШЛАНИШ санаси (КК.ОО.ЙЙЙЙ):", default_days=0),
                 Ask("expiry", "Яшаш ТУГАШ санаси (КК.ОО.ЙЙЙЙ):", default_days=90))),
    Module("trud", "📑 Трудовой", _run_trud,
           targets=lambda c: c["trud"].firms(),
           target_prompt="Фирмани танланг:",
           photo_prompt=_TRIO_PROMPT, photo_labels=_TRIO),
    Module("svera", "🎓 СФЕРА", _run_svera,
           targets=lambda c: c["svera"].professions(),
           target_prompt="Касбни танланг:",
           photo_prompt=("Иккита расм юборинг:\n1️⃣ Паспорт\n2️⃣ Ишчининг расми\n"
                         f"Кейин «{_BTN_RUN}» босинг."),
           photo_labels=("Паспорт", "Ишчи расми"), min_photos=2,
           asks=(Ask("issue_date", "Бериш санаси (КК.ОО.ЙЙЙЙ):", default_days=0),)),
    Module("perevod", "🌐 ПЕРЕВОД", _run_perevod,
           photo_prompt=("Таржима қилинадиган ҳужжат расмларини юборинг "
                         f"(хоҳлаганча), кейин «{_BTN_RUN}» босинг.")),
    Module("photo", "📷 Расм 3×4", _run_photo34,
           photo_prompt="Ишчи расмини юборинг — 3×4 тайёрлаб бераман.",
           photo_labels=("Расм",), needs_ai=False),
    Module("jpg2pdf", "🖼️ JPG→PDF", _run_jpg2pdf,
           photo_prompt=("Расмларни тартиб билан юборинг, кейин "
                         f"«{_BTN_RUN}» босинг."), needs_ai=False),
    Module("summa", "🔢 СУММА-ДАТА", _run_summa, text_only=True, needs_ai=False,
           asks=(Ask("value", "Сана (25.07.2026) ёки сумма (27500,50) ёзинг:",
                     kind="text"),)),
)

_BY_BUTTON = {m.button: m for m in _MODULES}
_BY_KEY = {m.key: m for m in _MODULES}


def _main_keyboard() -> dict:
    rows, row = [], []
    for m in _MODULES:
        row.append(m.button)
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([_BTN_CANCEL])
    return {"keyboard": rows, "resize_keyboard": True}


_MAIN_KB = _main_keyboard()
_RUN_KB = {"keyboard": [[_BTN_RUN], [_BTN_MENU, _BTN_CANCEL]], "resize_keyboard": True}


def _fresh() -> dict:
    return {"mode": None, "step": None, "photos": [], "answers": {},
            "targets": None, "target": None, "ask_index": 0}


def _label(item) -> str:
    for attr in ("name", "label", "title"):
        value = getattr(item, attr, None)
        if value:
            return str(value)
    return str(item)


# ---------------------------------------------------------------- the bot


class TelegramBot:
    """One instance per app. ``start()`` is a no-op without a token."""

    def __init__(self, container) -> None:
        self._container = container
        self._settings = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._state: dict[int, dict] = {}
        self._controllers = None

    # -- lifecycle -----------------------------------------------------
    def start(self) -> bool:
        from src.config.settings_service import SettingsService

        self._settings = self._container.resolve(SettingsService)
        if not self._token():
            log.info("Telegram bot: no token — not started")
            return False
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="ofis-telegram")
        self._thread.start()
        log.info("Telegram bot started")
        return True

    def stop(self) -> None:
        self._stop.set()

    def _token(self) -> str:
        return str(self._settings.get(KEY_TOKEN, "") or "").strip()

    def _password(self) -> str:
        return str(self._settings.get(KEY_PASSWORD, "") or "").strip()

    def _webapp_url(self) -> str:
        return str(self._settings.get(KEY_WEBAPP, "") or "").strip()

    def _allowed(self) -> set[int]:
        raw = str(self._settings.get(KEY_ALLOWED, "") or "")
        return {int(x) for x in raw.split(",") if x.strip().lstrip("-").isdigit()}

    def _remember_chat(self, chat_id: int) -> None:
        allowed = self._allowed()
        allowed.add(chat_id)
        self._settings.set(KEY_ALLOWED, ",".join(str(x) for x in sorted(allowed)))

    # -- controllers (built lazily, Qt-free) ---------------------------
    def ctl(self):
        if self._controllers is not None:
            return self._controllers
        from src.controllers.hostel_controller import HostelController
        from src.controllers.process_controller import ProcessController
        from src.controllers.registration_controller import RegistrationController
        from src.controllers.svera_controller import SveraController
        from src.controllers.trud_controller import TrudController
        from src.ocr.service import OcrService
        from src.services.company_service import CompanyService
        from src.services.generation_service import GenerationService
        from src.services.hostel_service import HostelService
        from src.services.perevod_service import PerevodService
        from src.services.photo_service import PhotoService
        from src.services.profession_service import ProfessionService
        from src.services.registration_address_service import RegistrationAddressService
        from src.services.registration_service import RegistrationService
        from src.services.svera_service import SveraService
        from src.services.trud_service import TrudFirmService, TrudService

        c = self._container
        ocr = c.resolve(OcrService)
        key = lambda: str(self._settings.get("ai.gemini_key", "") or "")  # noqa: E731
        self._controllers = {
            "process": ProcessController(
                c.resolve(CompanyService), ocr, c.resolve(GenerationService)),
            "reg": RegistrationController(
                c.resolve(RegistrationAddressService), ocr,
                c.resolve(RegistrationService)),
            # HostelService is stateless and not container-registered (the
            # desktop view builds it the same way).
            "hostel": HostelController(
                c.resolve(RegistrationAddressService), ocr, HostelService()),
            "trud": TrudController(
                c.resolve(TrudFirmService), ocr, c.resolve(TrudService)),
            "svera": SveraController(
                c.resolve(ProfessionService), ocr, c.resolve(SveraService)),
            "perevod": PerevodService(key_getter=key),
            "photo": PhotoService(key_getter=key),
            "ocr": ocr,
        }
        return self._controllers

    # -- transport (overridden in tests) -------------------------------
    def _api(self, method: str, payload: dict) -> dict:
        url = f"https://api.telegram.org/bot{self._token()}/{method}"
        body = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=65) as resp:
            return json.loads(resp.read().decode())

    def _send(self, chat_id: int, text: str, keyboard: dict | None = None) -> None:
        payload = {"chat_id": chat_id, "text": text}
        if keyboard:
            payload["reply_markup"] = keyboard
        try:
            self._api("sendMessage", payload)
        except Exception as exc:  # noqa: BLE001
            log.warning("tg send failed: %s", exc)

    def note(self, chat_id: int, text: str) -> None:
        """Public: a module tells the operator something mid-run."""
        self._send(chat_id, text)

    def _send_file(self, chat_id: int, path: Path, caption: str = "") -> None:
        boundary = uuid.uuid4().hex
        data = path.read_bytes()
        mime = "application/pdf" if path.suffix.lower() == ".pdf" else \
            "application/octet-stream"
        parts = []
        for name, value in (("chat_id", str(chat_id)), ("caption", caption)):
            parts.append(
                f"--{boundary}\r\nContent-Disposition: form-data; "
                f'name="{name}"\r\n\r\n{value}\r\n'.encode())
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; "
            f'filename="{path.name}"\r\nContent-Type: {mime}\r\n\r\n'.encode())
        body = b"".join(parts) + data + f"\r\n--{boundary}--\r\n".encode()
        url = f"https://api.telegram.org/bot{self._token()}/sendDocument"
        req = urllib.request.Request(url, data=body, headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}"})
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                resp.read()
        except Exception as exc:  # noqa: BLE001
            log.warning("tg sendDocument failed: %s", exc)
            self._send(chat_id, f"Файл юборилмади: {str(exc)[:120]}")

    def _download(self, file_id: str) -> bytes | None:
        try:
            info = self._api("getFile", {"file_id": file_id})
            fp = info["result"]["file_path"]
            url = f"https://api.telegram.org/file/bot{self._token()}/{fp}"
            with urllib.request.urlopen(url, timeout=120) as resp:
                return resp.read()
        except Exception as exc:  # noqa: BLE001
            log.warning("tg download failed: %s", exc)
            return None

    # -- main loop -----------------------------------------------------
    def _loop(self) -> None:
        offset = 0
        while not self._stop.is_set():
            try:
                updates = self._api("getUpdates",
                                    {"timeout": 50, "offset": offset})
            except Exception as exc:  # noqa: BLE001
                log.warning("tg poll failed: %s", exc)
                time.sleep(5)
                continue
            for upd in updates.get("result", []):
                offset = max(offset, upd["update_id"] + 1)
                try:
                    self._handle(upd)
                except Exception as exc:  # noqa: BLE001 - keep the loop alive
                    log.error("tg handler error: %s", exc)

    # -- update handling -----------------------------------------------
    def _handle(self, upd: dict) -> None:
        if "callback_query" in upd:
            cq = upd["callback_query"]
            chat_id = cq["message"]["chat"]["id"]
            if chat_id in self._allowed():
                self._on_pick(chat_id, cq.get("data", ""))
            try:
                self._api("answerCallbackQuery", {"callback_query_id": cq["id"]})
            except Exception:  # noqa: BLE001
                pass
            return

        msg = upd.get("message") or {}
        chat_id = (msg.get("chat") or {}).get("id")
        if chat_id is None:
            return
        text = (msg.get("text") or "").strip()

        # -- auth ------------------------------------------------------
        if text.startswith("/start"):
            parol = text.split(maxsplit=1)[1].strip() if " " in text else ""
            if self._password() and parol == self._password():
                self._remember_chat(chat_id)
                self._menu(chat_id, "OFIS уланди ✅")
            elif chat_id in self._allowed():
                self._menu(chat_id, "Аллақачон уланган ✅")
            else:
                self._send(chat_id,
                           "Парол хато. Юборинг: /start ПАРОЛ\n"
                           "(паролни OFIS Sozlamalar'дан оласиз)")
            return
        if chat_id not in self._allowed():
            self._send(chat_id, "Аввал уланинг: /start ПАРОЛ")
            return

        state = self._state.setdefault(chat_id, _fresh())

        if text in (_BTN_CANCEL, "/cancel"):
            self._state[chat_id] = _fresh()
            self._menu(chat_id, "Бекор қилинди.")
            return
        if text in (_BTN_MENU, "/menu", "/help"):
            self._state[chat_id] = _fresh()
            self._menu(chat_id)
            return

        # -- module selection -----------------------------------------
        if text in _BY_BUTTON:
            self._enter(chat_id, _BY_BUTTON[text])
            return

        # -- an answer to a pending question --------------------------
        if state.get("step") == "ask" and text:
            self._on_answer(chat_id, state, text)
            return

        if text == _BTN_RUN:
            self._on_run(chat_id, state)
            return

        # -- photos ---------------------------------------------------
        file_id = None
        if msg.get("photo"):
            file_id = msg["photo"][-1]["file_id"]
        elif (msg.get("document") or {}).get("mime_type", "").startswith("image/"):
            file_id = msg["document"]["file_id"]
        if file_id:
            self._on_photo(chat_id, state, file_id)
            return

        if text:
            self._menu(chat_id, "Тушунмадим.")

    # -- steps ---------------------------------------------------------
    def _menu(self, chat_id: int, prefix: str = "") -> None:
        head = f"{prefix}\n\n" if prefix else ""
        kb = dict(_MAIN_KB)
        url = self._webapp_url()
        if url:
            self._send(chat_id, head + "Бўлимни танланг:", kb)
            self._send(chat_id, "Ёки тўлиқ ойнада очинг:", {
                "inline_keyboard": [[{"text": "🌐 OFIS Mini App",
                                      "web_app": {"url": url}}]]})
            return
        self._send(chat_id, head + "Бўлимни танланг:", kb)

    def _enter(self, chat_id: int, module: Module) -> None:
        self._state[chat_id] = _fresh()
        state = self._state[chat_id]
        if module.needs_ai and not self.ctl()["ocr"].available():
            self._menu(chat_id, "AI калити йўқ — компютерда Sozlamalar'га киритинг.")
            return

        if module.targets is not None:
            try:
                items = list(module.targets(self.ctl()))
            except Exception as exc:  # noqa: BLE001
                self._menu(chat_id, f"Рўйхат олинмади: {str(exc)[:120]}")
                return
            if not items:
                # Nothing to pick — stay out of the module entirely, otherwise
                # photos get accepted and «Тайёрла» dead-ends on a null target.
                self._menu(chat_id, "Рўйхат бўш — аввал компютерда қўшинг.")
                return
            state.update({"mode": module.key, "step": "pick", "targets": items})
            self._send(chat_id, module.target_prompt, {"inline_keyboard": [
                [{"text": _label(t), "callback_data": f"pick:{i}"}]
                for i, t in enumerate(items[:30])]})
            return

        state["mode"] = module.key
        if module.text_only:
            state["step"] = "ask"
            self._send(chat_id, module.asks[0].prompt, _RUN_KB)
            return
        state["step"] = "collect"
        self._send(chat_id, module.photo_prompt, _RUN_KB)

    def _on_pick(self, chat_id: int, data: str) -> None:
        state = self._state.setdefault(chat_id, _fresh())
        module = _BY_KEY.get(state.get("mode") or "")
        if module is None or not data.startswith("pick:") or not state.get("targets"):
            self._menu(chat_id, "Бўлим танланмаган.")
            return
        try:
            idx = int(data.split(":", 1)[1])
        except ValueError:
            return
        targets = state["targets"]
        if not 0 <= idx < len(targets):
            return
        state["target"] = targets[idx]
        state["step"] = "collect"
        self._send(chat_id, f"«{_label(targets[idx])}» танланди.\n{module.photo_prompt}",
                   _RUN_KB)

    def _on_photo(self, chat_id: int, state: dict, file_id: str) -> None:
        module = _BY_KEY.get(state.get("mode") or "")
        if module is None or state.get("step") != "collect":
            self._menu(chat_id, "Аввал бўлимни танланг.")
            return
        data = self._download(file_id)
        if not data:
            self._send(chat_id, "Расмни юклаб бўлмади — қайта юборинг.")
            return
        state["photos"].append(data)
        n = len(state["photos"])
        labels = module.photo_labels
        label = labels[n - 1] if n <= len(labels) else f"{n}-расм"
        total = f"/{len(labels)}" if labels else ""
        self._send(chat_id, f"✔ {label} қабул қилинди ({n}{total}). "
                            f"Тайёр бўлса «{_BTN_RUN}» босинг.")

    def _on_answer(self, chat_id: int, state: dict, text: str) -> None:
        module = _BY_KEY.get(state.get("mode") or "")
        if module is None:
            self._menu(chat_id)
            return
        ask = module.asks[state["ask_index"]]
        if ask.kind == "date":
            parsed = _parse_date(text)
            if parsed is None:
                self._send(chat_id, "Сана формати: КК.ОО.ЙЙЙЙ (масалан 15.10.2026)")
                return
            state["answers"][ask.field] = parsed
        else:
            state["answers"][ask.field] = text
        state["ask_index"] += 1
        self._ask_or_run(chat_id, state, module)

    def _ask_or_run(self, chat_id: int, state: dict, module: Module) -> None:
        if state["ask_index"] < len(module.asks):
            ask = module.asks[state["ask_index"]]
            state["step"] = "ask"
            hint = ""
            if ask.kind == "date" and ask.default_days is not None:
                suggested = date.today() + timedelta(days=ask.default_days)
                hint = f"\n(масалан {suggested.strftime('%d.%m.%Y')})"
            self._send(chat_id, ask.prompt + hint, _RUN_KB)
            return
        self._execute(chat_id, state, module)

    def _on_run(self, chat_id: int, state: dict) -> None:
        module = _BY_KEY.get(state.get("mode") or "")
        if module is None:
            self._menu(chat_id, "Аввал бўлимни танланг.")
            return
        if module.targets is not None and state.get("target") is None:
            self._send(chat_id, f"«{module.button}» учун рўйхатдан танланг.")
            return
        if not module.text_only and len(state["photos"]) < module.min_photos:
            self._send(chat_id, f"Камида {module.min_photos} та расм юборинг "
                                f"(ҳозир {len(state['photos'])} та).")
            return
        self._ask_or_run(chat_id, state, module)

    def _execute(self, chat_id: int, state: dict, module: Module) -> None:
        state["step"] = "busy"
        if not module.text_only:
            self._send(chat_id, "⏳ Тайёрланяпти… (1-2 дақиқа)")
        try:
            outputs = module.run(self, chat_id, state)
        except OfisError as exc:
            self._menu(chat_id, f"❌ {exc.message}")
        except Exception as exc:  # noqa: BLE001 - surface, never crash the poller
            log.exception("tg module %s failed", module.key)
            self._menu(chat_id, f"❌ Хато: {str(exc)[:150]}")
        else:
            for path in outputs:
                self._send_file(chat_id, Path(path))
            self._menu(chat_id, "✅ Тайёр!")
        self._state[chat_id] = _fresh()
