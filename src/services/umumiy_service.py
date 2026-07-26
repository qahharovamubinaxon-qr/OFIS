"""УМУМИЙ — reuse ANY of the office's own documents for a new worker.

The operator drops one of the office's existing documents (договор, справка,
заявление — any text PDF that already carries a previous worker's details) plus
the new worker's passport / миграционная карта photos and a date. The program:

1. reads every text line out of the PDF (with position, font size);
2. asks the AI which fragments are the *previous worker's* personal data and
   what each should become for the new worker (ФИО in the right grammatical
   case, паспорт, дата рождения, гражданство, даты …);
3. deletes those fragments with real redactions and retypes the new values in
   the same place, size and weight.

Company data (ИНН, ОГРН, адрес фирмы, директор) is explicitly protected — the
prompt forbids touching anything that is not the worker's own data, and a
guard drops replacements that would rewrite a protected pattern.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import fitz

from src.ai.text_client import ask
from src.common.errors import OfisError
from src.common.logging import get_logger
from src.config import paths
from src.domain.documents import Passport, Patent
from src.pdf.engine import _font_file
from src.pdf.formatters import _date_dmy

log = get_logger(__name__)

_MAX_LINES = 400  # documents are contracts, not books — keeps the prompt sane

_PROMPT = """Ты — юрист миграционного отдела. Ниже пронумерованные строки \
документа организации, в котором указаны данные ПРЕДЫДУЩЕГО работника. \
Нужно подготовить тот же документ для НОВОГО работника.

ДАННЫЕ НОВОГО РАБОТНИКА:
{worker}

ДАТА ДОКУМЕНТА: {form_date}

СТРОКИ ДОКУМЕНТА:
{lines}

Верни JSON-массив замен. Каждый элемент:
{{"line": <номер строки>, "old": "<точный фрагмент из этой строки>", \
"new": "<чем заменить>"}}

ПРАВИЛА:
- Заменяй ТОЛЬКО персональные данные работника: ФИО (в том числе в родительном/\
дательном падеже и сокращения вида «ИВАНОВ И.И.»), дату рождения, гражданство, \
серию и номер паспорта, кем и когда выдан, номер патента/миграционной карты, \
адрес проживания работника, ИНН работника.
- Дату документа заменяй на указанную выше дату документа.
- НИКОГДА не трогай данные организации: название фирмы, её ИНН, ОГРН, КПП, \
юридический адрес, ФИО директора, банковские реквизиты, номера статей закона, \
суммы, названия должностей (если должность не указана как данные работника).
- "old" должен быть ТОЧНОЙ подстрокой указанной строки, посимвольно.
- Сохраняй падеж и регистр: если в документе «РАХИМОВА БАДРИДДИНА», новое \
значение тоже в родительном падеже и теми же заглавными буквами.
- Если заменять нечего — верни пустой массив [].
Только JSON, без пояснений."""


@dataclass(frozen=True)
class UmumiyResult:
    pdf_path: Path
    replacements: int
    surname: str


def _worker_block(passport: Passport, patent: Patent | None,
                  form_date: date) -> str:
    parts = [
        f"Фамилия: {passport.surname}",
        f"Имя: {passport.name}",
        f"Отчество: {passport.patronymic or '-'}",
        f"Гражданство: {passport.nationality or '-'}",
        f"Дата рождения: {_date_dmy(passport.birth_date) if passport.birth_date else '-'}",
        f"Паспорт серия/номер: {(passport.series or '')}{passport.number}",
        f"Паспорт выдан: {_date_dmy(passport.issue_date) if passport.issue_date else '-'}",
        f"Кем выдан: {passport.issued_by or '-'}",
        f"Срок действия паспорта: "
        f"{_date_dmy(passport.expiry_date) if passport.expiry_date else '-'}",
    ]
    if patent is not None:
        parts += [
            f"Патент серия/номер: {(patent.series or '')}{patent.number}",
            f"Патент выдан: {_date_dmy(patent.issue_date) if patent.issue_date else '-'}",
            f"Профессия по патенту: {patent.profession or '-'}",
        ]
    parts.append(f"Дата документа: {_date_dmy(form_date)}")
    return "\n".join(parts)


# Fragments that must never be rewritten even if the model suggests it.
_PROTECTED = re.compile(
    r"\b(ИНН|ОГРН|ОГРНИП|КПП|БИК|р/с|к/с|расчет|корресп)\b", re.IGNORECASE)


def _page_lines(doc: fitz.Document) -> list[dict]:
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
                out.append({
                    "page": pno,
                    "text": text,
                    "size": spans[0]["size"],
                    "bold": bool(spans[0].get("flags", 0) & 2 ** 4),
                })
                if len(out) >= _MAX_LINES:
                    return out
    return out


class UmumiyService:
    """Rewrite any office document for a new worker."""

    def __init__(self, key_getter) -> None:
        self._key_getter = key_getter

    def generate(
        self,
        source_pdf: Path,
        passport: Passport,
        patent: Patent | None,
        *,
        form_date: date,
        output_dir: Path | None = None,
    ) -> UmumiyResult:
        doc = fitz.open(source_pdf)
        lines = _page_lines(doc)
        if not lines:
            doc.close()
            raise OfisError(
                "Hujjatda matn topilmadi — u skan (rasm) bo'lishi mumkin. "
                "Matnli PDF yuklang.")

        numbered = "\n".join(f"{i}: {ln['text']}" for i, ln in enumerate(lines))
        prompt = _PROMPT.format(
            worker=_worker_block(passport, patent, form_date),
            form_date=_date_dmy(form_date),
            lines=numbered,
        )
        raw = ask(self._key_getter(), prompt, json_out=True)
        try:
            edits = json.loads(raw)
        except json.JSONDecodeError as exc:
            doc.close()
            raise OfisError("AI javobini o'qib bo'lmadi — qayta urinib ko'ring.") from exc
        if not isinstance(edits, list):
            edits = []

        applied = self._apply(doc, lines, edits)
        out_path = self._unique_output_path(source_pdf, passport, output_dir)
        doc.save(str(out_path), garbage=4, deflate=True)
        doc.close()
        log.info("Umumiy: %s → %s (%d replacements)",
                 source_pdf.name, out_path.name, applied)
        return UmumiyResult(pdf_path=out_path, replacements=applied,
                            surname=passport.surname)

    # ------------------------------------------------------------------
    def _apply(self, doc: fitz.Document, lines: list[dict],
               edits: list[dict]) -> int:
        """Redact every accepted old fragment, then retype the new value."""
        pending: dict[int, list[tuple[fitz.Rect, str, float, bool]]] = {}
        for edit in edits:
            if not isinstance(edit, dict):
                continue
            old = str(edit.get("old", "")).strip()
            new = str(edit.get("new", "")).strip()
            idx = edit.get("line")
            if not old or not isinstance(idx, int) or not 0 <= idx < len(lines):
                continue
            if old == new or _PROTECTED.search(old):
                continue
            info = lines[idx]
            if old not in info["text"]:
                continue
            page = doc[info["page"]]
            hits = page.search_for(old)
            if not hits:
                continue
            rect = hits[0]
            pending.setdefault(info["page"], []).append(
                (rect, new, info["size"], info["bold"]))

        applied = 0
        for pno, items in pending.items():
            page = doc[pno]
            for rect, _new, _size, _bold in items:
                page.add_redact_annot(rect)
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
            page.insert_font(fontname="umumiy_r",
                             fontfile=str(_font_file("OfisSerif")))
            page.insert_font(fontname="umumiy_b",
                             fontfile=str(_font_file("OfisSerifBold")))
            for rect, new, size, bold in items:
                if not new:
                    applied += 1  # deletion is a valid edit
                    continue
                font = fitz.Font(fontfile=str(
                    _font_file("OfisSerifBold" if bold else "OfisSerif")))
                fitted = size
                while fitted > 5 and font.text_length(new, fontsize=fitted) > rect.width:
                    fitted -= 0.25
                page.insert_text(
                    (rect.x0, rect.y1 - size * 0.22), new,
                    fontname="umumiy_b" if bold else "umumiy_r",
                    fontsize=fitted,
                )
                applied += 1
        return applied

    @staticmethod
    def _unique_output_path(source: Path, passport: Passport,
                            base: Path | None) -> Path:
        folder = base if base is not None else paths.output_dir() / "umumiy"
        folder.mkdir(parents=True, exist_ok=True)
        stem = "".join(c if c.isalnum() or c in " _-" else "_"
                       for c in f"{passport.surname}_{source.stem}").strip()
        candidate = folder / f"{stem or 'UMUMIY'}.pdf"
        i = 1
        while candidate.exists():
            candidate = folder / f"{stem}_{i:03d}.pdf"
            i += 1
        return candidate
