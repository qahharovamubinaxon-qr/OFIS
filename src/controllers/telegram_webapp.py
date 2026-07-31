"""OFIS Mini App — the whole program as a phone page.

A small stdlib HTTP server runs inside the desktop app and serves a one-page
web UI plus a JSON API driven by the same :data:`MODULES` table as the Telegram
bot. Two ways to reach it:

* **Same Wi-Fi** — open ``http://<computer-ip>:8770/?k=<parol>`` in the phone
  browser. Works immediately, nothing to install.
* **Telegram Mini App** — needs a public **https** address, so the operator
  points a tunnel (Cloudflare Tunnel, ngrok…) at this port and saves the
  resulting URL as ``tg.webapp_url``. The bot then shows an «OFIS Mini App»
  button that opens this same page inside Telegram, and requests are
  authenticated with Telegram's ``initData`` signature.

Every request must carry either the operator password (``?k=`` / ``X-Ofis-Key``)
or a valid Telegram ``initData``; nothing is served otherwise.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import mimetypes
import socket
import threading
import urllib.parse
import uuid
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from src.common.errors import OfisError
from src.common.logging import get_logger
from src.controllers.ofis_modules import (
    BY_KEY,
    MODULES,
    RunContext,
    build_controllers,
    label_of,
    new_state,
    parse_date,
)

log = get_logger(__name__)

KEY_ENABLED = "tg.webapp_enabled"
KEY_PORT = "tg.webapp_port"
DEFAULT_PORT = 8770


def lan_ip() -> str:
    """Best-effort LAN address of this computer (for the phone URL)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # no packet is sent — just picks the route
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def check_init_data(init_data: str, bot_token: str) -> bool:
    """Validate Telegram's ``initData`` signature (Mini App auth)."""
    if not init_data or not bot_token:
        return False
    pairs = urllib.parse.parse_qsl(init_data, keep_blank_values=True)
    received = dict(pairs).get("hash", "")
    if not received:
        return False
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs) if k != "hash")
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, received)


class WebAppServer:
    """Owns the HTTP thread. ``start()`` is a no-op unless enabled."""

    def __init__(self, container) -> None:
        self._container = container
        self._settings = None
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._controllers = None
        self._results: dict[str, Path] = {}

    # -- lifecycle -----------------------------------------------------
    def start(self) -> str | None:
        from src.config.settings_service import SettingsService

        self._settings = self._container.resolve(SettingsService)
        if not self._enabled():
            return None
        if not self._password():
            log.warning("Mini App not started — no password set")
            return None
        port = self.port()
        try:
            self._httpd = ThreadingHTTPServer(("0.0.0.0", port), self._make_handler())
        except OSError as exc:
            log.warning("Mini App port %s busy: %s", port, exc)
            return None
        self._thread = threading.Thread(target=self._httpd.serve_forever,
                                        daemon=True, name="ofis-webapp")
        self._thread.start()
        url = f"http://{lan_ip()}:{port}/?k={urllib.parse.quote(self._password())}"
        log.info("Mini App on %s", url)
        return url

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd = None

    def port(self) -> int:
        """The configured port, or the default when it is not a usable one.

        ``0`` is refused on purpose. It is a number, so it used to be saved and
        handed straight to the socket — and the OS then picks a RANDOM free
        port. The address printed on the Settings screen (``…:0/?k=…``) was
        never the one actually listening, so the phone could not reach it and
        the Mini App simply «did not work».
        """
        try:
            port = int(self._settings.get(KEY_PORT, DEFAULT_PORT))
        except (TypeError, ValueError):
            return DEFAULT_PORT
        return port if 1 <= port <= 65535 else DEFAULT_PORT

    def _enabled(self) -> bool:
        return str(self._settings.get(KEY_ENABLED, "0")) in ("1", "true", "True")

    def _password(self) -> str:
        from src.controllers.telegram_bot import KEY_PASSWORD

        return str(self._settings.get(KEY_PASSWORD, "") or "").strip()

    def _bot_token(self) -> str:
        from src.controllers.telegram_bot import KEY_TOKEN

        return str(self._settings.get(KEY_TOKEN, "") or "").strip()

    def ctl(self) -> dict:
        if self._controllers is None:
            self._controllers = build_controllers(
                self._container,
                lambda: str(self._settings.get("ai.gemini_key", "") or ""))
        return self._controllers

    # -- authorisation --------------------------------------------------
    def authorized(self, key: str, init_data: str) -> bool:
        password = self._password()
        if password and hmac.compare_digest(key or "", password):
            return True
        return check_init_data(init_data, self._bot_token())

    # -- API ------------------------------------------------------------
    def modules_payload(self) -> list[dict]:
        ctl = self.ctl()
        ai = ctl["ocr"].available()
        out = []
        for m in MODULES:
            targets: list[dict] = []
            if m.targets is not None:
                try:
                    targets = [{"i": i, "label": label_of(t)}
                               for i, t in enumerate(m.targets(ctl))]
                except Exception as exc:  # noqa: BLE001
                    log.warning("targets for %s failed: %s", m.key, exc)
            out.append({
                "key": m.key, "icon": m.icon, "title": m.title,
                "hint": m.photo_prompt, "targetPrompt": m.target_prompt,
                "needsTarget": m.targets is not None, "targets": targets,
                "textOnly": m.text_only, "minPhotos": m.min_photos,
                "photoLabels": list(m.photo_labels), "wantsPdf": m.wants_pdf,
                "ready": (ai or not m.needs_ai) and not self._blocked(m, ctl),
                "blocked": self._blocked(m, ctl),
                "asks": [{"field": a.field, "prompt": a.prompt, "kind": a.kind,
                          "options": a.options()}
                         for a in m.asks],
            })
        return out

    @staticmethod
    def _blocked(module, ctl) -> str:
        """Why the section cannot run yet — before anything is uploaded.

        ЧЕК needs its company id typed on the computer once; without this the
        operator fills the whole card in and the refusal only arrives at the
        end.
        """
        if module.ready is None:
            return ""
        try:
            return module.ready(ctl) or ""
        except Exception as exc:  # noqa: BLE001
            return f"Тайёр эмас: {str(exc)[:120]}"

    def run_module(self, key: str, target_index: int | None,
                   images: list[bytes], answers: dict[str, str],
                   pdfs: list[bytes] | None = None) -> dict:
        module = BY_KEY.get(key)
        if module is None:
            raise OfisError("Бўлим топилмади.")
        ctl = self.ctl()
        if module.needs_ai and not ctl["ocr"].available():
            raise OfisError("AI калити йўқ — Sozlamalar'га киритинг.")
        blocked = self._blocked(module, ctl)
        if blocked:
            raise OfisError(blocked)

        state = new_state()
        state["mode"] = key
        state["photos"] = images
        state["pdfs"] = pdfs or []
        if module.targets is not None:
            items = list(module.targets(ctl))
            if target_index is None or not 0 <= target_index < len(items):
                raise OfisError("Рўйхатдан танланг.")
            state["target"] = items[target_index]
        if module.wants_pdf and len(state["pdfs"]) < module.wants_pdf:
            raise OfisError(f"{module.wants_pdf} та PDF ҳужжат юкланг.")
        if not module.text_only and len(images) < module.min_photos:
            raise OfisError(f"Камида {module.min_photos} та расм юкланг.")

        for ask in module.asks:
            raw = (answers.get(ask.field) or "").strip()
            if ask.kind == "date":
                parsed = parse_date(raw) if raw else date.today()
                if parsed is None:
                    raise OfisError(f"Сана нотўғри: {ask.prompt}")
                state["answers"][ask.field] = parsed
            elif ask.kind == "choice":
                options = ask.options()
                state["answers"][ask.field] = (
                    raw if raw in options else (options[0] if options else raw))
            else:
                state["answers"][ask.field] = raw

        notes: list[str] = []
        outputs = module.run(RunContext(ctl=ctl, note=notes.append), state)
        files = []
        for path in outputs:
            token = uuid.uuid4().hex
            self._results[token] = Path(path)
            files.append({"name": Path(path).name, "token": token})
        return {"ok": True, "notes": notes, "files": files}

    def result_path(self, token: str) -> Path | None:
        return self._results.get(token)

    # -- handler --------------------------------------------------------
    def _make_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt, *args):  # keep the console clean
                log.debug("webapp %s", fmt % args)

            # -- helpers
            def _auth(self, query: dict) -> bool:
                key = (query.get("k", [""])[0]
                       or self.headers.get("X-Ofis-Key", ""))
                return server.authorized(key, self.headers.get("X-Telegram-Init", ""))

            def _json(self, payload: dict | list, status: int = 200) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _deny(self) -> None:
                self._json({"ok": False, "error": "Парол хато"}, 403)

            # -- routes
            def do_GET(self) -> None:  # noqa: N802 - stdlib naming
                parsed = urllib.parse.urlparse(self.path)
                query = urllib.parse.parse_qs(parsed.query)
                if parsed.path in ("/", "/index.html"):
                    self._page()
                    return
                if not self._auth(query):
                    self._deny()
                    return
                if parsed.path == "/api/modules":
                    self._json(server.modules_payload())
                    return
                if parsed.path == "/api/file":
                    self._file(query.get("t", [""])[0])
                    return
                self._json({"ok": False, "error": "not found"}, 404)

            def do_POST(self) -> None:  # noqa: N802 - stdlib naming
                parsed = urllib.parse.urlparse(self.path)
                query = urllib.parse.parse_qs(parsed.query)
                if not self._auth(query):
                    self._deny()
                    return
                if parsed.path != "/api/run":
                    self._json({"ok": False, "error": "not found"}, 404)
                    return
                length = int(self.headers.get("Content-Length", "0") or 0)
                raw = self.rfile.read(length) if length else b"{}"
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self._json({"ok": False, "error": "bad request"}, 400)
                    return
                import base64

                def decode(items) -> list[bytes]:
                    out = []
                    for item in items or []:
                        head, _, data = str(item).partition(",")
                        try:
                            out.append(base64.b64decode(data or head))
                        except (ValueError, TypeError):
                            continue
                    return out

                try:
                    result = server.run_module(
                        payload.get("module", ""),
                        payload.get("target"),
                        decode(payload.get("images")),
                        payload.get("answers") or {},
                        decode(payload.get("pdfs")),
                    )
                except OfisError as exc:
                    self._json({"ok": False, "error": exc.message})
                except Exception as exc:  # noqa: BLE001
                    log.exception("webapp run failed")
                    self._json({"ok": False, "error": str(exc)[:200]})
                else:
                    self._json(result)

            def _file(self, token: str) -> None:
                path = server.result_path(token)
                if path is None or not path.exists():
                    self._json({"ok": False, "error": "not found"}, 404)
                    return
                data = path.read_bytes()
                mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Disposition",
                                 f'attachment; filename="{path.name}"')
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _page(self) -> None:
                body = PAGE.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler


PAGE = """<!doctype html>
<html lang="uz"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>OFIS</title>
<script async src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
:root{--bg:#0f1115;--card:#171a21;--line:#262b36;--fg:#eef1f6;--dim:#9aa4b8;
      --accent:#2f81f7;--ok:#2ea043;--err:#f85149;--r:14px}
@media (prefers-color-scheme:light){:root{--bg:#f4f6fa;--card:#fff;--line:#e3e8f0;
      --fg:#11151c;--dim:#5b6577}}
*{box-sizing:border-box}
body{margin:0;font:16px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
     background:var(--bg);color:var(--fg);padding:16px 14px 40px}
h1{font-size:20px;margin:0 0 4px}
.sub{color:var(--dim);font-size:13px;margin-bottom:16px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:var(--r);
      padding:14px;cursor:pointer;transition:transform .12s,border-color .12s}
.tile:active{transform:scale(.97)}
.tile.off{opacity:.45}
.tile .ic{font-size:26px}
.tile .nm{margin-top:6px;font-weight:600;font-size:14px}
.tile .st{color:var(--dim);font-size:11px;margin-top:2px}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--r);
      padding:16px;margin-top:12px}
label{display:block;font-size:13px;color:var(--dim);margin:12px 0 6px}
select,input,button{width:100%;padding:12px;border-radius:10px;border:1px solid var(--line);
      background:var(--bg);color:var(--fg);font-size:16px;font-family:inherit}
button{background:var(--accent);border:0;color:#fff;font-weight:600;margin-top:16px;cursor:pointer}
button.ghost{background:transparent;border:1px solid var(--line);color:var(--fg);font-weight:500}
button:disabled{opacity:.5}
.hint{white-space:pre-line;color:var(--dim);font-size:13px;margin-top:4px}
.thumbs{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.thumbs img{width:64px;height:64px;object-fit:cover;border-radius:8px;border:1px solid var(--line)}
.msg{margin-top:14px;padding:12px;border-radius:10px;white-space:pre-line;font-size:14px}
.msg.ok{background:rgba(46,160,67,.14);border:1px solid var(--ok)}
.msg.err{background:rgba(248,81,73,.14);border:1px solid var(--err)}
.files a{display:block;margin-top:8px;color:var(--accent);font-weight:600;text-decoration:none}
.spin{display:inline-block;width:14px;height:14px;border:2px solid #fff6;border-top-color:#fff;
      border-radius:50%;animation:sp .8s linear infinite;vertical-align:-2px;margin-right:8px}
@keyframes sp{to{transform:rotate(360deg)}}
</style></head><body>
<h1>OFIS</h1>
<div class="sub" id="sub">Юкланмоқда…</div>
<div id="home" class="grid"></div>
<div id="form" style="display:none"></div>
<script>
const tg = window.Telegram && window.Telegram.WebApp;
if (tg) { tg.ready(); tg.expand(); }
const KEY = new URLSearchParams(location.search).get('k') || '';

// Telegram's own SDK is loaded async and is NOT depended on. Loaded the
// blocking way it sat in front of every line below it, so whenever
// telegram.org was slow or blocked the page stopped at «Юкланмоқда…» and
// stayed there — which is what the operator saw inside the bot.
//
// The signature the server checks does not need the SDK at all: Telegram puts
// it in the address it opens the Mini App with, as #tgWebAppData=…
function initData(){
  const live = window.Telegram && window.Telegram.WebApp;
  if (live && live.initData) return live.initData;
  try{ return new URLSearchParams(location.hash.slice(1)).get('tgWebAppData') || ''; }
  catch(e){ return ''; }
}
// built per request, because the SDK may arrive after the first one
const head = () => ({'Content-Type':'application/json','X-Ofis-Key':KEY,
                     'X-Telegram-Init': initData()});
let MODULES = [], picked = null, images = [], pdfs = [];

const el = (id) => document.getElementById(id);

async function load(){
  // never sit on «Юкланмоқда…» with nothing said: a request that hangs must
  // end in a sentence the operator can act on
  const stop = new AbortController();
  const timer = setTimeout(() => stop.abort(), 20000);
  try{
    const r = await fetch('/api/modules?k='+encodeURIComponent(KEY),
                          {headers:head(), signal:stop.signal});
    if(r.status === 403){
      el('sub').textContent = initData()
        ? 'Telegram имзоси тан олинмади — Sozlamalar’даги бот токени ното‘г‘ри.'
        : 'Парол хато — ҳаволани қайта олинг.';
      return;
    }
    if(!r.ok){ el('sub').textContent = 'Компьютер жавоб берди: '+r.status; return; }
    MODULES = await r.json();
    el('sub').textContent = 'Бўлимни танланг';
    home();
  }catch(e){
    el('sub').textContent = (e && e.name === 'AbortError')
      ? 'Компьютер жавоб бермади. OFIS очиқми? Кейин қайта уриниб кўринг.'
      : 'Компьютерга уланмади: '+e;
  }finally{ clearTimeout(timer); }
}

function home(){
  picked = null; images = []; pdfs = [];
  el('form').style.display='none'; el('home').style.display='grid';
  el('sub').textContent = 'Бўлимни танланг';
  el('home').innerHTML = MODULES.map((m,i)=>`
    <div class="tile ${m.ready?'':'off'}" onclick="open_(${i})">
      <div class="ic">${m.icon}</div><div class="nm">${m.title}</div>
      <div class="st">${m.ready?(m.needsTarget?m.targets.length+' та':'тайёр'):(m.blocked||'AI калити йўқ')}</div>
    </div>`).join('');
}

function open_(i){
  const m = MODULES[i];
  if(!m.ready){ alert(m.blocked || "AI калити йўқ — Sozlamalar'га киритинг."); return; }
  picked = m; images = []; pdfs = [];
  el('home').style.display='none'; el('form').style.display='block';
  el('sub').textContent = m.icon+' '+m.title;
  const targets = m.needsTarget ? `<label>${m.targetPrompt}</label>
      <select id="target">${m.targets.map(t=>`<option value="${t.i}">${t.label}</option>`).join('')}</select>` : '';
  const asks = m.asks.map(a=>{
    if(a.kind === 'choice'){
      return `<label>${a.prompt}</label><select id="ask_${a.field}">` +
        (a.options||[]).map(o=>`<option value="${o}">${o}</option>`).join('') + '</select>';
    }
    if(a.kind === 'date'){
      return `<label>${a.prompt}</label>
        <input id="ask_${a.field}" placeholder="${today()}" value="${today()}">`;
    }
    return `<label>${a.prompt}</label><input id="ask_${a.field}" placeholder="…">`;
  }).join('');
  const pdfBox = m.wantsPdf ? `<label>📄 Ҳужжат (PDF)</label>
      <input type="file" id="pdfs" accept="application/pdf" multiple onchange="addPdfs(this)">
      <div class="hint" id="pdfnames"></div>` : '';
  const upload = m.textOnly ? '' : `<label>${m.hint}</label>
      <input type="file" id="files" accept="image/*" multiple onchange="addFiles(this)">
      <div class="thumbs" id="thumbs"></div>`;
  el('form').innerHTML = `<div class="card">${targets}${pdfBox}${upload}${asks}
      <button id="go" onclick="run()">✅ Тайёрла</button>
      <button class="ghost" onclick="home()">← Орқага</button>
      <div id="out"></div></div>`;
}

function today(){
  const d = new Date();
  return String(d.getDate()).padStart(2,'0')+'.'+String(d.getMonth()+1).padStart(2,'0')+'.'+d.getFullYear();
}

function addFiles(input){
  for(const f of input.files){
    const rd = new FileReader();
    rd.onload = () => { images.push(rd.result); draw(); };
    rd.readAsDataURL(f);
  }
  input.value='';
}
function draw(){
  el('thumbs').innerHTML = images.map((src,i)=>
    `<img src="${src}" onclick="images.splice(${i},1);draw()">`).join('');
}

function addPdfs(input){
  for(const f of input.files){
    const rd = new FileReader();
    const name = f.name;
    rd.onload = () => { pdfs.push(rd.result); drawPdfs(name); };
    rd.readAsDataURL(f);
  }
  input.value='';
}
function drawPdfs(last){
  el('pdfnames').textContent = pdfs.length ? `📄 ${pdfs.length} ta PDF (${last})` : '';
}

async function run(){
  const btn = el('go'); btn.disabled = true;
  btn.innerHTML = '<span class="spin"></span>Тайёрланяпти…';
  const answers = {};
  picked.asks.forEach(a => answers[a.field] = (el('ask_'+a.field)||{}).value || '');
  const body = {module: picked.key, images, pdfs,
                target: picked.needsTarget ? Number(el('target').value) : null,
                answers};
  try{
    const r = await fetch('/api/run?k='+encodeURIComponent(KEY),
                          {method:'POST', headers:head(), body:JSON.stringify(body)});
    const j = await r.json();
    if(!j.ok){ show('err', j.error || 'Хато'); }
    else {
      const links = (j.files||[]).map(f=>
        `<a href="/api/file?t=${f.token}&k=${encodeURIComponent(KEY)}">⬇ ${f.name}</a>`).join('');
      show('ok', (j.notes||[]).join('\\n') || '✅ Тайёр!', links);
    }
  }catch(e){ show('err', String(e)); }
  btn.disabled = false; btn.textContent = '✅ Тайёрла';
}

function show(kind, text, links){
  el('out').innerHTML = `<div class="msg ${kind}">${text}</div>
                         <div class="files">${links||''}</div>`;
}
load();
</script></body></html>
"""
