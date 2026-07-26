"""Telegram bot — drive OFIS from the phone.

Workers send their passport/patent photos to the operator over WhatsApp or
Telegram; the operator forwards them to this bot and gets the finished PDFs
back in the chat, while the office computer does the actual work. Runs as a
daemon thread inside the desktop app (long polling — no server, no public IP
needed). Access is protected by a password: the operator sends
``/start <parol>`` once per chat; authorized chat ids persist in settings.

No third-party dependency — raw Bot API over urllib.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
import uuid
from datetime import date, datetime
from pathlib import Path

from src.common.errors import OfisError
from src.common.logging import get_logger

log = get_logger(__name__)

KEY_TOKEN = "tg.bot_token"
KEY_PASSWORD = "tg.password"
KEY_ALLOWED = "tg.allowed_chats"

_BTN_PATENT = "🛂 Патент PDF"
_BTN_REG = "🏠 Регистрация"
_BTN_TRUD = "📑 Трудовой"
_BTN_PHOTO = "📷 Расм 3×4"
_BTN_RUN = "✅ Тайёрла"
_BTN_CANCEL = "❌ Бекор"

_MAIN_KB = {
    "keyboard": [[_BTN_PATENT, _BTN_REG], [_BTN_TRUD, _BTN_PHOTO], [_BTN_CANCEL]],
    "resize_keyboard": True,
}
_RUN_KB = {
    "keyboard": [[_BTN_RUN], [_BTN_CANCEL]],
    "resize_keyboard": True,
}


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

    def _allowed(self) -> set[int]:
        raw = str(self._settings.get(KEY_ALLOWED, "") or "")
        return {int(x) for x in raw.split(",") if x.strip().lstrip("-").isdigit()}

    def _remember_chat(self, chat_id: int) -> None:
        allowed = self._allowed()
        allowed.add(chat_id)
        self._settings.set(KEY_ALLOWED, ",".join(str(x) for x in sorted(allowed)))

    # -- controllers (built lazily, Qt-free) ---------------------------
    def _ensure(self):
        if self._controllers is not None:
            return self._controllers
        from src.controllers.process_controller import ProcessController
        from src.controllers.registration_controller import RegistrationController
        from src.controllers.trud_controller import TrudController
        from src.ocr.service import OcrService
        from src.services.company_service import CompanyService
        from src.services.generation_service import GenerationService
        from src.services.photo_service import PhotoService
        from src.services.registration_address_service import RegistrationAddressService
        from src.services.registration_service import RegistrationService
        from src.services.trud_service import TrudFirmService, TrudService

        c = self._container
        ocr = c.resolve(OcrService)
        self._controllers = {
            "process": ProcessController(
                c.resolve(CompanyService), ocr, c.resolve(GenerationService)),
            "reg": RegistrationController(
                c.resolve(RegistrationAddressService), ocr,
                c.resolve(RegistrationService)),
            "trud": TrudController(
                c.resolve(TrudFirmService), ocr, c.resolve(TrudService)),
            "photo": PhotoService(key_getter=lambda: str(
                self._settings.get("ai.gemini_key", "") or "")),
        }
        return self._controllers

    # -- transport -----------------------------------------------------
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
        # inline keyboard choice (firma / manzil / firm pick)
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
                self._send(chat_id, "OFIS уланди ✅ Бўлимни танланг:", _MAIN_KB)
            elif chat_id in self._allowed():
                self._send(chat_id, "Аллақачон уланган ✅", _MAIN_KB)
            else:
                self._send(chat_id,
                           "Парол хато. Юборинг: /start ПАРОЛ\n"
                           "(паролни OFIS Sozlamalar'дан оласиз)")
            return
        if chat_id not in self._allowed():
            self._send(chat_id, "Аввал уланинг: /start ПАРОЛ")
            return

        state = self._state.setdefault(chat_id, {"mode": None, "photos": []})

        if text == _BTN_CANCEL:
            self._state[chat_id] = {"mode": None, "photos": []}
            self._send(chat_id, "Бекор қилинди. Бўлимни танланг:", _MAIN_KB)
            return

        # -- mode selection -------------------------------------------
        if text in (_BTN_PATENT, _BTN_REG, _BTN_TRUD, _BTN_PHOTO):
            self._enter_mode(chat_id, text)
            return

        # -- expiry date for registration -----------------------------
        if state.get("await_expiry") and text:
            try:
                expiry = datetime.strptime(text, "%d.%m.%Y").date()
            except ValueError:
                self._send(chat_id, "Сана формати: КК.ОО.ЙЙЙЙ (масалан 15.10.2026)")
                return
            state["expiry"] = expiry
            state["await_expiry"] = False
            self._run_registration(chat_id, state)
            return

        # -- run --------------------------------------------------------
        if text == _BTN_RUN:
            self._on_run(chat_id, state)
            return

        # -- photos -----------------------------------------------------
        file_id = None
        if msg.get("photo"):
            file_id = msg["photo"][-1]["file_id"]
        elif (msg.get("document") or {}).get("mime_type", "").startswith("image/"):
            file_id = msg["document"]["file_id"]
        if file_id:
            self._on_photo(chat_id, state, file_id)
            return

        if text:
            self._send(chat_id, "Бўлимни танланг:", _MAIN_KB)

    # -- flows ---------------------------------------------------------
    def _enter_mode(self, chat_id: int, btn: str) -> None:
        ctl = self._ensure()
        self._state[chat_id] = {"mode": None, "photos": []}
        state = self._state[chat_id]
        if btn == _BTN_PHOTO:
            state["mode"] = "photo"
            self._send(chat_id, "Ишчи расмини юборинг — 3×4 тайёрлаб бераман.",
                       _RUN_KB)
            return
        if btn == _BTN_PATENT:
            items = ctl["process"].companies()
            state.update({"mode": "patent", "targets": items})
            title = "Фирмани танланг:"
        elif btn == _BTN_REG:
            items = ctl["reg"].addresses()
            state.update({"mode": "reg", "targets": items})
            title = "Манзилни танланг:"
        else:
            items = ctl["trud"].firms()
            state.update({"mode": "trud", "targets": items})
            title = "Фирмани танланг:"
        if not items:
            self._send(chat_id, "Рўйхат бўш — аввал компютерда қўшинг.", _MAIN_KB)
            return
        kb = {"inline_keyboard": [
            [{"text": getattr(t, "name", None) or getattr(t, "label", "?"),
              "callback_data": f"pick:{i}"}]
            for i, t in enumerate(items[:20])
        ]}
        self._send(chat_id, title, kb)

    def _on_pick(self, chat_id: int, data: str) -> None:
        state = self._state.setdefault(chat_id, {"mode": None, "photos": []})
        if not data.startswith("pick:") or not state.get("targets"):
            return
        idx = int(data.split(":")[1])
        targets = state["targets"]
        if not 0 <= idx < len(targets):
            return
        state["target"] = targets[idx]
        name = getattr(targets[idx], "name", None) or getattr(targets[idx], "label", "?")
        self._send(
            chat_id,
            f"«{name}» танланди.\nЭнди расмларни ТАРТИБ билан юборинг:\n"
            "1️⃣ Паспорт\n2️⃣ Патент (олд)\n3️⃣ Патент (орқа)\n"
            f"Кейин «{_BTN_RUN}» тугмасини босинг.",
            _RUN_KB,
        )

    def _on_photo(self, chat_id: int, state: dict, file_id: str) -> None:
        if state.get("mode") is None:
            self._send(chat_id, "Аввал бўлимни танланг:", _MAIN_KB)
            return
        data = self._download(file_id)
        if not data:
            self._send(chat_id, "Расмни юклаб бўлмади — қайта юборинг.")
            return
        if state["mode"] == "photo":
            self._run_photo(chat_id, data)
            return
        state["photos"].append(data)
        names = ["Паспорт", "Патент (олд)", "Патент (орқа)"]
        n = len(state["photos"])
        label = names[n - 1] if n <= 3 else f"{n}-расм"
        self._send(chat_id, f"✔ {label} қабул қилинди ({n}/3). "
                            f"Тайёр бўлса «{_BTN_RUN}» босинг.")

    def _on_run(self, chat_id: int, state: dict) -> None:
        mode = state.get("mode")
        if mode not in ("patent", "reg", "trud") or state.get("target") is None:
            self._send(chat_id, "Аввал бўлим ва фирма/манзилни танланг.", _MAIN_KB)
            return
        if not state["photos"]:
            self._send(chat_id, "Камида паспорт расмини юборинг.")
            return
        ctl = self._ensure()
        if not ctl["process"].ai_available():
            self._send(chat_id, "AI калити йўқ — компютерда Sozlamalar'га киритинг.")
            return
        if mode == "reg":
            state["await_expiry"] = True
            self._send(chat_id,
                       "Рўйхатга олиш ТУГАШ санасини ёзинг (КК.ОО.ЙЙЙЙ):")
            return
        self._send(chat_id, "⏳ Тайёрланяпти… (1-2 дақиқа)")
        photos = state["photos"]
        passport = photos[0]
        patent = photos[1] if len(photos) > 1 else None
        back = photos[2] if len(photos) > 2 else None
        try:
            if mode == "patent":
                r = ctl["process"].generate_from_images(
                    state["target"], passport, patent, back,
                    form_date=date.today(), profession=None)
                self._send_file(chat_id, r.pdf_path, f"№ {r.reg_number}")
            else:
                r = ctl["trud"].generate_from_images(
                    state["target"], passport, patent, back,
                    form_date=date.today(), profession=None)
                for p in (r.trud_path, r.uved_path, getattr(r, "hod_path", None)):
                    if p:
                        self._send_file(chat_id, p)
        except OfisError as exc:
            self._send(chat_id, f"❌ {exc.message}", _MAIN_KB)
        except Exception as exc:  # noqa: BLE001
            self._send(chat_id, f"❌ Хато: {str(exc)[:150]}", _MAIN_KB)
        else:
            self._send(chat_id, "✅ Тайёр!", _MAIN_KB)
        self._state[chat_id] = {"mode": None, "photos": []}

    def _run_registration(self, chat_id: int, state: dict) -> None:
        ctl = self._ensure()
        self._send(chat_id, "⏳ Тайёрланяпти… (1-2 дақиқа)")
        photos = state["photos"]
        passport = photos[0]
        patent = photos[1] if len(photos) > 1 else None
        back = photos[2] if len(photos) > 2 else None
        try:
            r = ctl["reg"].generate_from_images(
                state["target"], passport, patent, back,
                registration_expiry=state["expiry"])
            self._send_file(chat_id, r.pdf_path)
        except OfisError as exc:
            self._send(chat_id, f"❌ {exc.message}", _MAIN_KB)
        except Exception as exc:  # noqa: BLE001
            self._send(chat_id, f"❌ Хато: {str(exc)[:150]}", _MAIN_KB)
        else:
            self._send(chat_id, "✅ Тайёр!", _MAIN_KB)
        self._state[chat_id] = {"mode": None, "photos": []}

    def _run_photo(self, chat_id: int, data: bytes) -> None:
        ctl = self._ensure()
        self._send(chat_id, "⏳ 3×4 тайёрланяпти…")
        try:
            result = ctl["photo"].process(data)
            from src.config import paths

            out = paths.output_dir() / "photo" / "tg_3x4.png"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(result.png)
            self._send_file(chat_id, out, "3×4 " + (result.note or ""))
            self._send(chat_id, "✅ Тайёр!", _MAIN_KB)
        except Exception as exc:  # noqa: BLE001
            self._send(chat_id, f"❌ Хато: {str(exc)[:150]}", _MAIN_KB)
        self._state[chat_id] = {"mode": None, "photos": []}
