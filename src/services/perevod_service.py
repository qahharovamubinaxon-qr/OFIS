"""ПЕРЕВОД — notarial translation of personal documents into Russian.

The office's notary offers translation services: a client's passport, driving
licence, birth/marriage certificate, diploma or аттестат is translated into
Russian, printed, stapled behind a copy of the original and certified by the
notary.

Flow: drop the document photos (front/back) → the AI recognises WHICH document
it is, reads every field and returns a structured translation → the program
renders it in the standard Russian notarial-translation layout (header naming
the source language, the document body as «поле: значение», then the
translator's attestation line the notary signs under).

``templates/perevod/forms.v1.json`` holds the canonical field order per
document type (CIS passports, driving licences, certificates …) so output stays
consistent no matter how the AI phrases things.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.ai.text_client import ask
from src.common.errors import OfisError
from src.common.logging import get_logger
from src.config import paths
from src.pdf.engine import _font_file

log = get_logger(__name__)

DOC_TYPES = [
    ("auto", "Авто (программа ўзи аниқлайди)"),
    ("passport", "Паспорт"),
    ("driver_license", "Ҳайдовчилик гувоҳномаси"),
    ("birth_certificate", "Туғилганлик ҳақида гувоҳнома"),
    ("marriage_certificate", "Никоҳ гувоҳномаси"),
    ("diploma", "Диплом"),
    ("attestat", "Аттестат"),
    ("migration_card", "Миграционная карта"),
    ("other", "Бошқа ҳужжат"),
]

_PROMPT = """Ты — присяжный переводчик, готовишь НОТАРИАЛЬНЫЙ перевод документа \
на русский язык.

На фотографиях один документ (может быть несколько сторон одного документа).
{hint}

ЗАДАЧА:
1. Определи вид документа и язык оригинала.
2. Прочитай ВСЕ поля документа, включая печати, штампы и надписи.
3. Переведи на русский язык по стандартам нотариального перевода:
   - имена собственные — транслитерация по правилам русского языка
     (например: Shahboz Isakov → Шахбоз Исаков);
   - даты — в формате ДД.ММ.ГГГГ;
   - названия органов и учреждений — полный официальный перевод;
   - если поле нечитаемо — значение "неразборчиво";
   - если поля нет в документе — не включай его вовсе.

Верни СТРОГО JSON:
{{
 "doc_type": "<passport|driver_license|birth_certificate|marriage_certificate|\
diploma|attestat|migration_card|other>",
 "source_language": "<язык оригинала в родительном падеже, напр. узбекского>",
 "title": "<название документа по-русски заглавными, напр. ПАСПОРТ>",
 "issuing_country": "<государство, выдавшее документ>",
 "fields": [{{"label": "<поле по-русски>", "value": "<перевод значения>"}}],
 "stamps": ["<перевод текста печатей и штампов, если есть>"],
 "notes": ["<примечания переводчика, если нужны>"],
 "crops": [{{"x0": <число>, "y0": <число>, "x1": <число>, "y1": <число>}}]
}}

Поле "crops" — по одному элементу на КАЖДУЮ присланную фотографию, в том же \
порядке. Это границы самого документа на фото (без стола, кровати, пальцев и \
прочего фона) в долях от размера изображения: 0.0 — левый/верхний край, 1.0 — \
правый/нижний. Если документ занимает всё фото, верни 0,0,1,1.
Только JSON, без пояснений и без markdown."""

@dataclass(frozen=True)
class PerevodResult:
    pdf_path: Path
    docx_path: Path
    doc_type: str
    title: str


def _scan_page(doc, image: bytes, crop: dict | None = None) -> bool:
    """Add a page holding the original document as a clean B/W «scan».

    ``crop`` are the document's bounds within the photo in 0..1 fractions (the
    AI returns them alongside the translation — it can see where the document
    is far more reliably than edge detection can on a patterned surface). The
    photo is trimmed to those bounds, its lighting evened out and lifted to
    paper-white / ink-black, then centred on A4.

    Returns False (adding nothing) if the bytes are not a readable image.
    """
    import fitz
    import numpy as np

    try:
        import cv2
    except ImportError:  # pragma: no cover - cv2 ships with the app
        cv2 = None

    data = image
    if cv2 is not None:
        arr = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
        if arr is None:
            return False
        arr = _apply_crop(arr, crop)
        data = _scan_look(cv2, arr) or data

    page = doc.new_page(width=595, height=842)
    margin = 38.0
    area = fitz.Rect(margin, margin, 595 - margin, 842 - margin)
    try:
        page.insert_image(area, stream=data, keep_proportion=True)
    except Exception:  # noqa: BLE001 - unreadable photo must not kill the run
        doc.delete_page(doc.page_count - 1)
        log.warning("Perevod: skipped an unreadable document photo")
        return False
    return True


def _apply_crop(arr, crop: dict | None):
    """Trim to the AI-reported document bounds, with a small safety margin."""
    if not isinstance(crop, dict):
        return arr
    try:
        x0 = float(crop["x0"]); y0 = float(crop["y0"])
        x1 = float(crop["x1"]); y1 = float(crop["y1"])
    except (KeyError, TypeError, ValueError):
        return arr
    if not (0.0 <= x0 < x1 <= 1.0 and 0.0 <= y0 < y1 <= 1.0):
        return arr
    if (x1 - x0) * (y1 - y0) < 0.05:  # implausibly small — ignore
        return arr
    h, w = arr.shape[:2]
    pad = 0.012
    px0 = max(0, int((x0 - pad) * w)); py0 = max(0, int((y0 - pad) * h))
    px1 = min(w, int((x1 + pad) * w)); py1 = min(h, int((y1 + pad) * h))
    if px1 - px0 < 40 or py1 - py0 < 40:
        return arr
    return arr[py0:py1, px0:px1]


def _scan_look(cv2, arr) -> bytes | None:
    """Flatten phone lighting and lift the page to crisp black-on-white."""
    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    # divide out the illumination field, then stretch what is left
    blur = cv2.GaussianBlur(gray, (0, 0), sigmaX=max(gray.shape) / 30.0)
    flat = cv2.divide(gray, blur, scale=255)
    flat = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(flat)
    # clip the paper to white and the ink to black without going fully binary,
    # so photos, stamps and guilloche stay readable
    lo, hi = 120.0, 225.0
    stretched = cv2.convertScaleAbs(flat, alpha=255.0 / (hi - lo),
                                    beta=-lo * 255.0 / (hi - lo))
    ok, buf = cv2.imencode(".png", stretched)
    return buf.tobytes() if ok else None


def _forms() -> dict:
    path = paths.templates_dir() / "perevod" / "forms.v1.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _order_fields(doc_type: str, fields: list[dict]) -> list[dict]:
    """Sort the AI's fields into the canonical order for this document type;
    anything unknown keeps its original position at the end."""
    template = _forms().get(doc_type) or {}
    wanted = [w.lower() for w in template.get("fields", [])]
    if not wanted:
        return fields

    def rank(f: dict) -> int:
        label = str(f.get("label", "")).strip().lower()
        for i, w in enumerate(wanted):
            if label == w or label.startswith(w) or w.startswith(label):
                return i
        return len(wanted) + 1

    return sorted(fields, key=rank)


class PerevodService:
    def __init__(self, key_getter, cert_getter=None) -> None:
        self._key_getter = key_getter
        # returns {"notary": str, "translator": str, "city": str} for the
        # certification page (page 3); names are printed, never signed/stamped.
        self._cert_getter = cert_getter

    def translate(
        self,
        images: list[bytes],
        *,
        doc_type: str = "auto",
        form_date: date | None = None,  # kept for API compatibility; unused
        output_dir: Path | None = None,
    ) -> PerevodResult:
        if not images:
            raise OfisError("Hujjat rasmini yuklang.")
        hint = ""
        if doc_type != "auto":
            label = dict(DOC_TYPES).get(doc_type, doc_type)
            hint = f"Оператор указал вид документа: {label} ({doc_type}).\n"

        from src.ocr.preprocess import prepare_image

        prepared = [prepare_image(i) for i in images[:10]]
        raw = ask(self._key_getter(), _PROMPT.format(hint=hint),
                  prepared, json_out=True)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OfisError("AI javobini o'qib bo'lmadi — qayta urinib ko'ring.") from exc

        kind = str(data.get("doc_type") or (doc_type if doc_type != "auto" else "other"))
        title = str(data.get("title") or _forms().get(kind, {}).get("title") or "ДОКУМЕНТ")
        lang = str(data.get("source_language") or "иностранного")
        country = str(data.get("issuing_country") or "")
        fields = _order_fields(kind, [f for f in data.get("fields", [])
                                      if isinstance(f, dict) and f.get("label")])
        stamps = [str(s) for s in data.get("stamps", []) if str(s).strip()]
        notes = [str(n) for n in data.get("notes", []) if str(n).strip()]
        crops = data.get("crops") if isinstance(data.get("crops"), list) else []

        folder = output_dir if output_dir is not None else paths.output_dir() / "perevod"
        folder.mkdir(parents=True, exist_ok=True)
        stem = self._stem(fields, title)
        base = folder / stem
        i = 1
        while base.with_suffix(".pdf").exists():
            base = folder / f"{stem}_{i:03d}"
            i += 1

        cert = (self._cert_getter() if self._cert_getter else None) or {}
        pdf = self._to_pdf(base.with_suffix(".pdf"), title=title, lang=lang,
                           country=country, fields=fields, stamps=stamps,
                           notes=notes, cert=cert, scans=list(zip(
                               images[:10],
                               list(crops) + [None] * len(images),
                               strict=False)))
        docx = self._to_docx(base.with_suffix(".docx"), title=title, lang=lang,
                             country=country, fields=fields, stamps=stamps,
                             notes=notes)
        log.info("Perevod: %s (%s) → %s", title, kind, pdf.name)
        return PerevodResult(pdf_path=pdf, docx_path=docx, doc_type=kind, title=title)

    # ------------------------------------------------------------------
    @staticmethod
    def _stem(fields: list[dict], title: str) -> str:
        surname = ""
        for f in fields:
            label = str(f.get("label", "")).lower()
            if "фамилия" in label:
                surname = str(f.get("value", "")).split()[0] if f.get("value") else ""
                break
        raw = f"{surname}_{title}".strip("_") or "PEREVOD"
        return "".join(c if c.isalnum() or c in " _-" else "_" for c in raw).strip()

    def _to_pdf(self, out: Path, *, title: str, lang: str, country: str,
                fields: list[dict], stamps: list[str], notes: list[str],
                scans: list[tuple[bytes, dict | None]],
                cert: dict | None = None) -> Path:
        import fitz

        serif = fitz.Font(fontfile=str(_font_file("OfisSerif")))
        bold = fitz.Font(fontfile=str(_font_file("OfisSerifBold")))
        X0, X1 = 70.0, 525.0
        width = X1 - X0
        LABEL_W = 200.0
        SIZE, LEAD = 11.0, 1.5
        TOP, BOTTOM = 70.0, 780.0

        doc = fitz.open()
        page = None
        tw = None
        y = 0.0

        def new_page() -> None:
            nonlocal page, tw, y
            if page is not None and tw is not None:
                tw.write_text(page)
            page = doc.new_page(width=595, height=842)
            tw = fitz.TextWriter(page.rect)
            y = TOP

        def room(need: float) -> None:
            if page is None or y + need > BOTTOM:
                new_page()

        def center(text: str, font, size: float) -> None:
            nonlocal y
            room(size * LEAD)
            w = font.text_length(text, fontsize=size)
            tw.append((X0 + (width - w) / 2, y + size), text, font=font, fontsize=size)
            y += size * LEAD

        def wrapped(text: str, font, size: float, x: float, avail: float) -> list[str]:
            rows, cur = [], ""
            for word in text.split():
                cand = (cur + " " + word).strip()
                if cur and font.text_length(cand, fontsize=size) > avail:
                    rows.append(cur)
                    cur = word
                else:
                    cur = cand
            if cur:
                rows.append(cur)
            return rows

        # page(s) 1..n — the original document as a clean scan
        for shot, crop in scans:
            _scan_page(doc, shot, crop)

        new_page()
        center(f"ПЕРЕВОД С {lang.upper()} ЯЗЫКА НА РУССКИЙ ЯЗЫК", bold, 12.0)
        y += 8
        if country:
            center(country.upper(), serif, 11.0)
        center(title.upper(), bold, 13.0)
        y += 12

        for f in fields:
            label = str(f.get("label", "")).strip()
            value = str(f.get("value", "")).strip()
            if not label:
                continue
            rows = wrapped(value, serif, SIZE, X0 + LABEL_W, width - LABEL_W) or [""]
            for i, row in enumerate(rows):
                room(SIZE * LEAD)
                if i == 0:
                    tw.append((X0, y + SIZE), f"{label}:", font=serif, fontsize=SIZE)
                tw.append((X0 + LABEL_W, y + SIZE), row, font=bold, fontsize=SIZE)
                y += SIZE * LEAD

        if stamps:
            y += 10
            center("Печати и штампы:", bold, SIZE)
            for s in stamps:
                for row in wrapped(s, serif, SIZE, X0, width):
                    room(SIZE * LEAD)
                    tw.append((X0, y + SIZE), row, font=serif, fontsize=SIZE)
                    y += SIZE * LEAD

        if notes:
            y += 10
            for n in notes:
                for row in wrapped(f"Примечание переводчика: {n}", serif, 10.0, X0, width):
                    room(10.0 * LEAD)
                    tw.append((X0, y + 10.0), row, font=serif, fontsize=10.0)
                    y += 10.0 * LEAD

        # page 3 — the notarial certification, as a BLANK the notary completes.
        # The program prints only the standard wording (and the office's usual
        # notary/translator names, if configured). The registry number, the
        # date, the fee, the sheet count, both signatures and the round seal are
        # left empty — the notary fills and stamps them in person, exactly like
        # the Госуслуги block on the hostel form. It never prints a seal, a
        # signature or a registry number, so it is a draft to be certified, not
        # a finished notarial act.
        def left(text: str, font, size: float, dx: float = 0.0) -> None:
            nonlocal y
            room(size * LEAD)
            tw.append((X0 + dx, y + size), text, font=font, fontsize=size)
            y += size * LEAD

        def rule(x0: float, x1: float, dy: float = -3.0) -> None:
            page.draw_line((x0, y + dy), (x1, y + dy), color=(0, 0, 0), width=0.6)

        cert = cert or {}
        notary = str(cert.get("notary") or "").strip()
        translator = str(cert.get("translator") or "").strip()
        city = str(cert.get("city") or "город Москва").strip()
        # header form (nominative) vs. the genitive used after «нотариус …»
        city_head = city[:1].upper() + city[1:] if city else city
        city_gen = ("города Москвы" if city.lower() in ("город москва", "москва")
                    else city)
        blank = "_" * 34

        new_page()
        left(f"Перевод данного текста выполнен переводчиком {translator or blank}",
             serif, SIZE)
        y += 30  # room for the translator's own signature (left blank)

        y += 14
        center("Российская Федерация", bold, SIZE)
        center(city_head, bold, SIZE)
        center("«____» ________________ 20____ года", serif, SIZE)
        y += 16

        who = notary or blank
        body = [
            f"Я, {who}, нотариус {city_gen}, свидетельствую подлинность подписи",
            f"переводчика {translator or blank}.",
            "Подпись сделана в моём присутствии.",
            "Личность подписавшего документ установлена.",
        ]
        for para in body:
            for row in wrapped(para, serif, SIZE, X0, width):
                left(row, serif, SIZE)
        y += 16
        left("Зарегистрировано в реестре: № ___________________________", serif, SIZE)
        y += 8
        left("Уплачено за совершение нотариального действия: ________ руб. ____ коп.",
             serif, SIZE)
        y += 40

        # notary signature line (left blank) with the name printed to its right
        room(SIZE * LEAD)
        rule(X0, X0 + 150, dy=SIZE - 2)
        tw.append((X0 + 165, y + SIZE), notary or "", font=serif, fontsize=SIZE)
        y += SIZE * LEAD
        left("(подпись нотариуса)", serif, 8.0, dx=35)
        y += 24
        left("Всего прошнуровано, пронумеровано и", serif, SIZE)
        left("скреплено печатью ______ листа(ов)", serif, SIZE)
        left("Нотариус: ______________________", serif, SIZE)

        if page is not None and tw is not None:
            tw.write_text(page)
        out.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(out), garbage=4, deflate=True)
        doc.close()
        return out

    @staticmethod
    def _to_docx(out: Path, *, title: str, lang: str, country: str,
                 fields: list[dict], stamps: list[str], notes: list[str]) -> Path:
        import docx
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Pt

        d = docx.Document()
        style = d.styles["Normal"]
        style.font.name = "Times New Roman"
        style.font.size = Pt(11)

        head = d.add_paragraph()
        run = head.add_run(f"ПЕРЕВОД С {lang.upper()} ЯЗЫКА НА РУССКИЙ ЯЗЫК")
        run.bold = True
        run.font.size = Pt(12)
        head.alignment = WD_ALIGN_PARAGRAPH.CENTER

        if country:
            p = d.add_paragraph(country.upper())
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        t = d.add_paragraph()
        tr = t.add_run(title.upper())
        tr.bold = True
        tr.font.size = Pt(13)
        t.alignment = WD_ALIGN_PARAGRAPH.CENTER
        d.add_paragraph()

        for f in fields:
            label = str(f.get("label", "")).strip()
            if not label:
                continue
            p = d.add_paragraph()
            p.add_run(f"{label}: ")
            p.add_run(str(f.get("value", "")).strip()).bold = True

        if stamps:
            d.add_paragraph()
            d.add_paragraph("Печати и штампы:").runs[0].bold = True
            for s in stamps:
                d.add_paragraph(s)
        for n in notes:
            d.add_paragraph(f"Примечание переводчика: {n}")
        d.save(str(out))
        return out
