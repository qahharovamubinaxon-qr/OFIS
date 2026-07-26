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
from src.pdf.formatters import _date_dmy

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
 "notes": ["<примечания переводчика, если нужны>"]
}}
Только JSON, без пояснений и без markdown."""

_ATTEST = (
    "Перевод с {lang} языка на русский язык выполнен переводчиком."
)


@dataclass(frozen=True)
class PerevodResult:
    pdf_path: Path
    docx_path: Path
    doc_type: str
    title: str


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
    def __init__(self, key_getter) -> None:
        self._key_getter = key_getter

    def translate(
        self,
        images: list[bytes],
        *,
        doc_type: str = "auto",
        form_date: date | None = None,
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

        folder = output_dir if output_dir is not None else paths.output_dir() / "perevod"
        folder.mkdir(parents=True, exist_ok=True)
        stem = self._stem(fields, title)
        base = folder / stem
        i = 1
        while base.with_suffix(".pdf").exists():
            base = folder / f"{stem}_{i:03d}"
            i += 1

        pdf = self._to_pdf(base.with_suffix(".pdf"), title=title, lang=lang,
                           country=country, fields=fields, stamps=stamps,
                           notes=notes, form_date=form_date or date.today())
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
                form_date: date) -> Path:
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

        y += 26
        room(60)
        page.draw_line((X0, y), (X1, y), color=(0, 0, 0), width=0.7)
        y += 14
        for row in wrapped(_ATTEST.format(lang=lang), serif, SIZE, X0, width):
            room(SIZE * LEAD)
            tw.append((X0, y + SIZE), row, font=serif, fontsize=SIZE)
            y += SIZE * LEAD
        y += 6
        tw.append((X0, y + SIZE), f"Дата перевода: {_date_dmy(form_date)}",
                  font=serif, fontsize=SIZE)
        y += SIZE * LEAD * 2
        tw.append((X0, y + SIZE), "Переводчик: ______________________",
                  font=serif, fontsize=SIZE)

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

        d.add_paragraph()
        d.add_paragraph("_" * 70)
        d.add_paragraph(_ATTEST.format(lang=lang))
        d.add_paragraph()
        d.add_paragraph("Переводчик: ______________________")
        d.save(str(out))
        return out
