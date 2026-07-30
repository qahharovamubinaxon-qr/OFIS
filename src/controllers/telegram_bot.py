"""Telegram bot — drive the whole of OFIS from the phone.

Workers send their passport/patent photos to the operator over WhatsApp or
Telegram; the operator forwards them to this bot and gets the finished PDFs
back in the chat, while the office computer does the actual work. Runs as a
daemon thread inside the desktop app (long polling — no server, no public IP
needed). Access is protected by a password: the operator sends
``/start <parol>`` once per chat; authorized chat ids persist in settings.

The modules themselves live in :mod:`src.controllers.ofis_modules`, shared with
the Mini App, so both front ends always offer the same work.

No third-party dependency — raw Bot API over urllib.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.request
import uuid
from datetime import date, timedelta
from pathlib import Path

from src.common.errors import OfisError
from src.common.logging import get_logger
from src.controllers.ofis_modules import (
    BY_BUTTON as _BY_BUTTON,
)
from src.controllers.ofis_modules import (
    BY_KEY as _BY_KEY,
)
from src.controllers.ofis_modules import (
    MODULES as _MODULES,
)
from src.controllers.ofis_modules import (
    Module,
    RunContext,
    build_controllers,
)
from src.controllers.ofis_modules import (
    label_of as _label,
)
from src.controllers.ofis_modules import (
    new_state as _fresh,
)
from src.controllers.ofis_modules import (
    parse_date as _parse_date,
)

log = get_logger(__name__)

KEY_TOKEN = "tg.bot_token"
KEY_PASSWORD = "tg.password"
KEY_ALLOWED = "tg.allowed_chats"
KEY_WEBAPP = "tg.webapp_url"

_BTN_RUN = "✅ Тайёрла"
_BTN_CANCEL = "❌ Бекор"
_BTN_MENU = "☰ Бўлимлар"


#: Three to a row, not two.
#:
#: Telegram gives a reply keyboard only a slice of the screen and scrolls the
#: rest out of sight. At two a row the office's nineteen sections needed eleven
#: rows and the ones at the bottom — СФЕРА, ПЕРЕВОД, УМУМИЙ, СУММА-ДАТА — were
#: below the fold, which reads on the phone as «they are not there». Three a
#: row brings it to seven, and the labels are short enough to stay readable.
_PER_ROW = 3


def _main_keyboard() -> dict:
    rows, row = [], []
    for m in _MODULES:
        row.append(m.button)
        if len(row) == _PER_ROW:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([_BTN_CANCEL])
    return {"keyboard": rows, "resize_keyboard": True}


def _plain(text: str) -> str:
    """A button's name with the decoration off — «🩷 ПАТЕНТ» → «патент»."""
    kept = [c for c in (text or "").lower() if c.isalnum() or c.isspace()]
    return " ".join("".join(kept).split())


#: Every section by its bare name, so the operator can simply TYPE it.
#:
#: The keyboard can be collapsed, scrolled or hidden behind the phone's own
#: keyboard, and then there is no way in at all. Typing «сертификат» — or its
#: number from the list the menu prints — always works.
_BY_NAME: dict[str, Module] = {_plain(m.button): m for m in _MODULES}


def _module_for(text: str) -> Module | None:
    """The section the operator meant: a button, a typed name, or its number."""
    text = (text or "").strip()
    if text in _BY_BUTTON:
        return _BY_BUTTON[text]
    if text.isdigit():
        index = int(text) - 1
        if 0 <= index < len(_MODULES):
            return _MODULES[index]
        return None
    name = _plain(text)
    if not name:
        return None
    if name in _BY_NAME:
        return _BY_NAME[name]
    starts = [m for key, m in _BY_NAME.items() if key.startswith(name)]
    return starts[0] if len(starts) == 1 else None


def _menu_text() -> str:
    """The sections written out, numbered.

    The keyboard can be scrolled or collapsed; a message cannot. So the menu
    also SAYS what there is, and any of it can be reached by replying with the
    number or the name — nothing depends on a button being on screen.
    """
    lines = [f"{i}. {m.button}" for i, m in enumerate(_MODULES, 1)]
    return ("Бўлимни танланг — тугмани босинг, ёки рақамини/номини ёзинг:\n\n"
            + "\n".join(lines))


_MAIN_KB = _main_keyboard()
_MENU_TEXT = _menu_text()
_RUN_KB = {"keyboard": [[_BTN_RUN], [_BTN_MENU, _BTN_CANCEL]], "resize_keyboard": True}


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
        if self._controllers is None:
            self._controllers = build_controllers(
                self._container,
                lambda: str(self._settings.get("ai.gemini_key", "") or ""))
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
        # A section BUTTON always switches, wherever the operator is — that is
        # how it has always worked. A typed name or a number only counts at the
        # menu: mid-flow they belong to the question being answered, and «3»
        # must not throw away three photographs already uploaded.
        busy = bool(state.get("step"))
        chosen = _BY_BUTTON.get(text) if busy else _module_for(text)
        if chosen is not None:
            self._enter(chat_id, chosen)
            return

        # -- an answer to a pending question --------------------------
        if state.get("step") == "ask" and text:
            self._on_answer(chat_id, state, text)
            return

        if text == _BTN_RUN:
            self._on_run(chat_id, state)
            return

        # -- photos / PDFs --------------------------------------------
        document = msg.get("document") or {}
        mime = document.get("mime_type", "")
        file_id = None
        if msg.get("photo"):
            file_id = msg["photo"][-1]["file_id"]
        elif mime.startswith("image/"):
            file_id = document["file_id"]
        elif mime == "application/pdf" or str(
                document.get("file_name", "")).lower().endswith(".pdf"):
            self._on_pdf(chat_id, state, document["file_id"])
            return
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
            # the Mini App offer goes FIRST and the sections last, so the list
            # is what the operator is left looking at. The other way round the
            # sections scroll up out of the way behind the offer, which reads
            # as «the sections are gone».
            self._send(chat_id, (head + "Тўлиқ ойнада очиш:").strip(), {
                "inline_keyboard": [[{"text": "🌐 OFIS Mini App",
                                      "web_app": {"url": url}}]]})
            self._send(chat_id, _MENU_TEXT, kb)
            return
        self._send(chat_id, head + _MENU_TEXT, kb)

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
            if not items and module.add_key is None:
                # Nothing to pick — stay out of the module entirely, otherwise
                # photos get accepted and «Тайёрла» dead-ends on a null target.
                self._menu(chat_id, "Рўйхат бўш — аввал компютерда қўшинг.")
                return
            rows = [[{"text": _label(t), "callback_data": f"pick:{i}"}]
                    for i, t in enumerate(items[:30])]
            if module.add_key is not None:
                # the operator can add a new one right here, on the phone,
                # rather than being sent to the computer for it
                rows.append([{"text": module.add_prompt,
                              "callback_data": "pick:add"}])
            state.update({"mode": module.key, "step": "pick", "targets": items})
            prompt = module.target_prompt if items else (
                "Рўйхат бўш — пастдаги тугма билан янгисини қўшинг:")
            self._send(chat_id, prompt, {"inline_keyboard": rows})
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
        if module is None or not data.startswith("pick:"):
            self._menu(chat_id, "Бўлим танланмаган.")
            return
        if data == "pick:add" and module.add_key:
            adder = _BY_KEY.get(module.add_key)
            if adder is not None:
                self._enter(chat_id, adder)
                return
        if not state.get("targets"):
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

    def _on_pdf(self, chat_id: int, state: dict, file_id: str) -> None:
        module = _BY_KEY.get(state.get("mode") or "")
        if module is None or state.get("step") != "collect":
            self._menu(chat_id, "Аввал бўлимни танланг.")
            return
        if not module.wants_pdf and not module.accepts_pdf:
            self._send(chat_id, f"«{module.button}» PDF қабул қилмайди — "
                                "расм юборинг.")
            return
        data = self._download(file_id)
        if not data:
            self._send(chat_id, "PDF юклаб бўлмади — қайта юборинг.")
            return
        state.setdefault("pdfs", []).append(data)
        got = len(state["pdfs"])
        if not module.wants_pdf:
            # a module that takes ONE file, PDF or picture — the blank sheets
            self._send(chat_id, f"✔ Файл қабул қилинди. «{_BTN_RUN}» босинг.")
            return
        left = module.wants_pdf - got
        # ТРУД ППУ wants two, in order — «send the photos now» after the first
        # of them would lose the уведомление
        self._send(chat_id, f"✔ PDF қабул қилинди ({got}/{module.wants_pdf}). "
                            + (f"Яна {left} та PDF юборинг." if left > 0
                               else "Энди расмларни юборинг."))

    def _on_answer(self, chat_id: int, state: dict, text: str) -> None:
        module = _BY_KEY.get(state.get("mode") or "")
        if module is None:
            self._menu(chat_id)
            return
        ask = module.asks[state["ask_index"]]
        if ask.kind == "date":
            # tapping «Тайёрла» at a date question means "use the suggested day"
            if text == _BTN_RUN and ask.default_days is not None:
                state["answers"][ask.field] = date.today() + timedelta(days=ask.default_days)
                state["ask_index"] += 1
                self._ask_or_run(chat_id, state, module)
                return
            parsed = _parse_date(text)
            if parsed is None:
                self._send(chat_id, "Сана формати: КК.ОО.ЙЙЙЙ (масалан 15.10.2026)")
                return
            state["answers"][ask.field] = parsed
        elif ask.kind == "choice":
            options = ask.options()
            choice = options[0] if options else ""
            if text.strip().isdigit():
                idx = int(text.strip()) - 1
                if not 0 <= idx < len(options):
                    self._send(chat_id, f"1 дан {len(options)} гача рақам ёзинг.")
                    return
                choice = options[idx]
            elif text != _BTN_RUN:  # tapping Тайёрла keeps «Авто»
                match = [o for o in options if text.lower() in o.lower()]
                choice = match[0] if match else options[0]
            state["answers"][ask.field] = choice
        else:
            state["answers"][ask.field] = "" if text == _BTN_RUN else text
        state["ask_index"] += 1
        self._ask_or_run(chat_id, state, module)

    def _ask_or_run(self, chat_id: int, state: dict, module: Module) -> None:
        if state["ask_index"] < len(module.asks):
            ask = module.asks[state["ask_index"]]
            state["step"] = "ask"
            hint = ""
            if ask.kind == "date" and ask.default_days is not None:
                suggested = date.today() + timedelta(days=ask.default_days)
                hint = (f"\n(масалан {suggested.strftime('%d.%m.%Y')} — ёки "
                        f"«{_BTN_RUN}» босинг, ўша сана қўйилади)")
            elif ask.kind == "choice":
                options = ask.options()
                hint = "\n" + "\n".join(f"{i}. {o}" for i, o in enumerate(options, 1))
                hint += f"\n(«{_BTN_RUN}» босилса — 1-вариант)"
            elif ask.kind == "text":
                hint = f"\n(керак бўлмаса «{_BTN_RUN}» босинг)"
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
        if module.wants_pdf and len(state.get("pdfs") or []) < module.wants_pdf:
            self._send(chat_id, f"Аввал {module.wants_pdf} та PDF ҳужжат юборинг.")
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
            outputs = module.run(
                RunContext(ctl=self.ctl(), note=lambda t: self.note(chat_id, t)),
                state)
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
