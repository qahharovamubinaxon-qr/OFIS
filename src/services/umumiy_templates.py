"""УМУМИЙ template store — save any office document once, reuse it forever.

The operator adds a document that already carries some previous worker's
details. The program studies it ONCE with the AI, blanks every fragment that
belonged to that worker, and remembers each blank as a field: which value goes
there, at what coordinates, in which font, size, weight and casing.

    templates/umumiy/<slug>/
        template.pdf      the document with the worker's data removed
        fields.v1.json    {key, page, rect, size, bold, font, align, case}
        meta.json         {name, created, source, scanned}

Filling a saved template needs no AI at all: for a new worker the program walks
the field list and types each value into its rectangle. That makes it instant,
free and repeatable — the same template always produces the same layout.

Both kinds of PDF work:

* **text PDF** — fragments are located through the text layer, exactly;
* **scanned PDF** (no text layer) — pages are rendered and the AI returns the
  boxes, so «matn topilmadi» is no longer a dead end.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import fitz

from src.ai.russian import RUSSIAN_RULES
from src.ai.text_client import ask
from src.common.errors import OfisError
from src.common.logging import get_logger
from src.config import paths
from src.domain.documents import Passport, Patent
from src.pdf.engine import _font_file
from src.services.umumiy_fields import (
    FIELD_KEYS,
    FIELD_LABELS,
    apply_case,
    detect_case,
    field_value,
)

log = get_logger(__name__)

FIELDS_VERSION = 1
_MAX_LINES = 400
_SCAN_DPI = 150

_KEY_LIST = "\n".join(f"- {k}: {v}" for k, v in FIELD_LABELS.items())

_TEXT_PROMPT = RUSSIAN_RULES + """Ты — юрист миграционного отдела. Ниже пронумерованные строки \
документа организации, в котором записаны данные КОНКРЕТНОГО работника. \
Мы делаем из этого документа МНОГОРАЗОВЫЙ ШАБЛОН: данные работника надо \
стереть и запомнить, что именно стояло на каждом месте.

СТРОКИ ДОКУМЕНТА:
{lines}

Верни JSON-массив. Каждый элемент — одно место, где стоят данные работника:
{{"line": <номер строки>, "text": "<точный фрагмент из этой строки>", \
"field": "<ключ поля>"}}

ДОПУСТИМЫЕ КЛЮЧИ ПОЛЕЙ:
{keys}

ПРАВИЛА:
- "text" должен быть ТОЧНОЙ подстрокой указанной строки, посимвольно.
- Отмечай ТОЛЬКО данные самого работника: ФИО (в любом падеже, в том числе \
сокращения «ИВАНОВ И.И.»), гражданство, дату рождения, паспорт (серия, номер, \
кем и когда выдан, срок), патент, профессию, дату документа.
- НИКОГДА не отмечай данные организации: название фирмы, её ИНН, ОГРН, КПП, \
юридический адрес, ФИО директора, банковские реквизиты, номера статей закона, \
суммы.
- Каждый фрагмент — отдельный элемент. Если ФИО написано целиком одной строкой, \
используй ключ fio_full; если только фамилия — surname.
- Если данных работника нет — верни [].
Только JSON, без пояснений."""

_SCAN_PROMPT = """Ты — юрист миграционного отдела. На изображениях страницы \
документа организации с данными КОНКРЕТНОГО работника. Мы делаем из него \
МНОГОРАЗОВЫЙ ШАБЛОН.

Найди КАЖДОЕ место, где написаны данные работника, и верни JSON-массив:
{{"page": <номер страницы с 0>, "text": "<что там написано>", \
"field": "<ключ поля>", "box": {{"x0": <число>, "y0": <число>, "x1": <число>, \
"y1": <число>}}}}

"box" — прямоугольник вокруг ЭТОГО текста в долях размера страницы: \
0.0 — левый/верхний край, 1.0 — правый/нижний. Прямоугольник должен плотно \
охватывать только сам текст.

ДОПУСТИМЫЕ КЛЮЧИ ПОЛЕЙ:
{keys}

ПРАВИЛА:
- Только данные работника. НИКОГДА: название фирмы, ИНН/ОГРН/КПП организации, \
её адрес, ФИО директора, банковские реквизиты, суммы, номера статей закона.
- Если данных работника нет — верни [].
Только JSON, без пояснений."""

# never blank a fragment that carries company requisites
_PROTECTED = re.compile(
    r"\b(ИНН|ОГРН|ОГРНИП|КПП|БИК|р/с|к/с|расчет|корресп)\b", re.IGNORECASE)


@dataclass(frozen=True)
class UmumiyTemplate:
    slug: str
    name: str
    pdf_path: Path
    fields: int
    scanned: bool
    created: str = ""

    @property
    def label(self) -> str:
        kind = " (скан)" if self.scanned else ""
        return f"{self.name} — {self.fields} майдон{kind}"


def _slugify(name: str) -> str:
    keep = "".join(c if c.isalnum() or c in " _-" else "_" for c in name).strip()
    return (keep.replace(" ", "_").lower() or "shablon")[:60]


def _root() -> Path:
    return paths.user_templates_dir() / "umumiy"


def _lines_of(doc: fitz.Document) -> list[dict]:
    out: list[dict] = []
    for pno, page in enumerate(doc):
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue
                text = "".join(s["text"] for s in spans)
                if not text.strip():
                    continue
                span = spans[0]
                out.append({
                    "page": pno,
                    "text": text,
                    "size": float(span.get("size", 11.0)),
                    "bold": bool(span.get("flags", 0) & 2 ** 4),
                })
                if len(out) >= _MAX_LINES:
                    return out
    return out


def has_text_layer(pdf: Path) -> bool:
    """True when the PDF carries a real text layer we can search."""
    doc = fitz.open(pdf)
    try:
        return bool(_lines_of(doc))
    finally:
        doc.close()


class UmumiyTemplateService:
    """Create, list, delete and fill saved УМУМИЙ templates."""

    def __init__(self, key_getter) -> None:
        self._key_getter = key_getter

    # ---------------------------------------------------------- listing
    def list(self) -> list[UmumiyTemplate]:
        out: list[UmumiyTemplate] = []
        root = _root()
        if not root.exists():
            return out
        for folder in sorted(root.iterdir()):
            tpl = self._load(folder)
            if tpl is not None:
                out.append(tpl)
        return out

    def get(self, slug: str) -> UmumiyTemplate | None:
        return self._load(_root() / slug)

    @staticmethod
    def _load(folder: Path) -> UmumiyTemplate | None:
        pdf, fields_file = folder / "template.pdf", folder / "fields.v1.json"
        meta_file = folder / "meta.json"
        if not (pdf.exists() and fields_file.exists()):
            return None
        try:
            fields = json.loads(fields_file.read_text(encoding="utf-8"))
            meta = (json.loads(meta_file.read_text(encoding="utf-8"))
                    if meta_file.exists() else {})
        except (OSError, json.JSONDecodeError):
            return None
        return UmumiyTemplate(
            slug=folder.name, name=str(meta.get("name") or folder.name),
            pdf_path=pdf, fields=len(fields.get("fields", [])),
            scanned=bool(meta.get("scanned")), created=str(meta.get("created") or ""))

    def delete(self, slug: str) -> None:
        folder = _root() / slug
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)
            log.info("Umumiy template removed: %s", slug)

    # ---------------------------------------------------------- creation
    def create(self, source_pdf: Path, name: str) -> UmumiyTemplate:
        """Study ``source_pdf`` once, blank the worker's data, save the map."""
        doc = fitz.open(source_pdf)
        try:
            lines = _lines_of(doc)
            if lines:
                found = self._study_text(lines)
                fields = self._fields_from_text(doc, lines, found)
                scanned = False
            else:
                # No text layer — read the pages as images instead of giving up.
                found = self._study_scan(doc)
                fields = self._fields_from_boxes(doc, found)
                scanned = True
            if not fields:
                raise OfisError(
                    "Hujjatda ishchi ma'lumotlari topilmadi. Boshqa hujjat "
                    "yuklang yoki ishchi ismi ko'rinadigan nusxasini bering.")

            for field in fields:  # blank every remembered spot
                doc[field["page"]].add_redact_annot(fitz.Rect(*field["rect"]))
            for page in doc:
                page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

            slug = self._free_slug(_slugify(name))
            folder = _root() / slug
            folder.mkdir(parents=True, exist_ok=True)
            doc.save(str(folder / "template.pdf"), garbage=4, deflate=True)
        finally:
            doc.close()

        (folder / "fields.v1.json").write_text(json.dumps(
            {"version": FIELDS_VERSION, "fields": fields},
            ensure_ascii=False, indent=2), encoding="utf-8")
        (folder / "meta.json").write_text(json.dumps({
            "name": name.strip() or slug,
            "created": datetime.now().isoformat(timespec="seconds"),
            "source": source_pdf.name,
            "scanned": scanned,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("Umumiy template saved: %s (%d fields, scanned=%s)",
                 slug, len(fields), scanned)
        tpl = self._load(folder)
        assert tpl is not None
        return tpl

    @staticmethod
    def _free_slug(base: str) -> str:
        root = _root()
        slug, i = base, 1
        while (root / slug).exists():
            slug = f"{base}_{i}"
            i += 1
        return slug

    def _study_text(self, lines: list[dict]) -> list[dict]:
        numbered = "\n".join(f"{i}: {ln['text']}" for i, ln in enumerate(lines))
        raw = ask(self._key_getter(),
                  _TEXT_PROMPT.format(lines=numbered, keys=_KEY_LIST),
                  json_out=True)
        return _as_list(raw)

    def _study_scan(self, doc: fitz.Document) -> list[dict]:
        images = [page.get_pixmap(dpi=_SCAN_DPI).tobytes("png")
                  for page in list(doc)[:6]]
        raw = ask(self._key_getter(), _SCAN_PROMPT.format(keys=_KEY_LIST),
                  images, json_out=True)
        return _as_list(raw)

    @staticmethod
    def _fields_from_text(doc: fitz.Document, lines: list[dict],
                          found: list[dict]) -> list[dict]:
        fields: list[dict] = []
        for item in found:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", "")).strip()
            key = str(item.get("field", "")).strip()
            idx = item.get("line")
            if (not text or key not in FIELD_KEYS
                    or not isinstance(idx, int) or not 0 <= idx < len(lines)):
                continue
            if _PROTECTED.search(text):
                continue
            info = lines[idx]
            if text not in info["text"]:
                continue
            hits = doc[info["page"]].search_for(text)
            if not hits:
                continue
            rect = hits[0]
            fields.append({
                "key": key, "page": info["page"],
                "rect": [rect.x0, rect.y0, rect.x1, rect.y1],
                "size": round(info["size"], 2), "bold": info["bold"],
                "case": detect_case(text), "sample": text,
            })
        return fields

    @staticmethod
    def _fields_from_boxes(doc: fitz.Document, found: list[dict]) -> list[dict]:
        fields: list[dict] = []
        for item in found:
            if not isinstance(item, dict):
                continue
            key = str(item.get("field", "")).strip()
            box = item.get("box")
            pno = item.get("page", 0)
            if key not in FIELD_KEYS or not isinstance(box, dict):
                continue
            if not isinstance(pno, int) or not 0 <= pno < len(doc):
                continue
            sample = str(item.get("text", ""))
            if _PROTECTED.search(sample):
                continue
            page = doc[pno]
            w, h = page.rect.width, page.rect.height
            try:
                x0, y0 = float(box["x0"]) * w, float(box["y0"]) * h
                x1, y1 = float(box["x1"]) * w, float(box["y1"]) * h
            except (KeyError, TypeError, ValueError):
                continue
            if x1 - x0 < 4 or y1 - y0 < 4:
                continue
            fields.append({
                "key": key, "page": pno, "rect": [x0, y0, x1, y1],
                # a scanned box has no font metrics — estimate from its height
                "size": round(max(6.0, min(20.0, (y1 - y0) * 0.72)), 2),
                "bold": False, "case": detect_case(sample), "sample": sample,
            })
        return fields

    # ------------------------------------------------------------- fill
    def fill(self, slug: str, passport: Passport, patent: Patent | None,
             *, form_date: date, output_dir: Path | None = None) -> Path:
        """Type this worker's values into a saved template. No AI involved."""
        folder = _root() / slug
        tpl = self._load(folder)
        if tpl is None:
            raise OfisError("Shablon topilmadi — ro'yxatdan qaytadan tanlang.")
        data = json.loads((folder / "fields.v1.json").read_text(encoding="utf-8"))

        doc = fitz.open(folder / "template.pdf")
        try:
            for page in doc:
                page.insert_font(fontname="um_r", fontfile=str(_font_file("OfisSerif")))
                page.insert_font(fontname="um_b",
                                 fontfile=str(_font_file("OfisSerifBold")))
            for field in data.get("fields", []):
                value = apply_case(
                    field_value(str(field.get("key")), passport, patent, form_date),
                    field.get("case"))
                if not value:
                    continue
                rect = fitz.Rect(*field["rect"])
                bold = bool(field.get("bold"))
                size = float(field.get("size", 11.0))
                font = fitz.Font(fontfile=str(
                    _font_file("OfisSerifBold" if bold else "OfisSerif")))
                while size > 5 and font.text_length(value, fontsize=size) > rect.width:
                    size -= 0.25
                doc[int(field["page"])].insert_text(
                    (rect.x0, rect.y1 - rect.height * 0.22), value,
                    fontname="um_b" if bold else "um_r", fontsize=size)
            out = self._output_path(tpl, passport, output_dir)
            doc.save(str(out), garbage=4, deflate=True)
        finally:
            doc.close()
        log.info("Umumiy template %s filled for %s", slug, passport.surname)
        return out

    @staticmethod
    def _output_path(tpl: UmumiyTemplate, passport: Passport,
                     base: Path | None) -> Path:
        folder = base if base is not None else paths.output_dir() / "umumiy"
        folder.mkdir(parents=True, exist_ok=True)
        stem = "".join(c if c.isalnum() or c in " _-" else "_"
                       for c in f"{passport.surname}_{tpl.name}").strip()
        candidate = folder / f"{stem or 'UMUMIY'}.pdf"
        i = 1
        while candidate.exists():
            candidate = folder / f"{stem}_{i:03d}.pdf"
            i += 1
        return candidate


def _as_list(raw: str) -> list[dict]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OfisError("AI javobini o'qib bo'lmadi — qayta urinib ko'ring.") from exc
    return parsed if isinstance(parsed, list) else []
