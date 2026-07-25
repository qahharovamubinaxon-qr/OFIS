"""ДОВЕРЕННОСТЬ: draft notarial documents for the office's notary partner.

The operator drops the parties' passport photos, picks a date and a document
type (or just describes it — the AI infers the type), and writes who → whom →
for what. Gemini composes the full Russian text per Moscow notarial practice,
addressed for certification by the office's notary; the draft is saved as BOTH
.docx and .pdf. The notary reviews, signs and stamps the print-out.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.common.errors import OfisError
from src.common.logging import get_logger
from src.config import paths
from src.domain.documents import Passport
from src.pdf.engine import _font_file
from src.pdf.formatters import _date_dmy

log = get_logger(__name__)

NOTARY_FIO = "Друганова Маргарита Владимировна"
NOTARY_CITY = "город Москва"

DOVER_TYPES = [
    "Авто (тавсифдан аниқлайди)",
    "Генеральная доверенность",
    "Доверенность на автомобиль",
    "Доверенность на ведение дел и представительство",
    "Доверенность на получение документов",
    "Доверенность на получение денежных средств",
    "Доверенность на распоряжение недвижимостью",
    "Доверенность на регистрационные действия",
    "Согласие на выезд ребёнка за границу",
    "Согласие на сопровождение ребёнка",
    "Согласие супруга на сделку",
    "Заявление (свободная форма)",
]

_SYSTEM = (
    "Ты — помощник московского нотариуса. Составь ПОЛНЫЙ текст нотариального "
    "документа (доверенность / согласие / заявление) по стандартам нотариальной "
    "практики города Москвы и законодательства РФ (ГК РФ, Основы законодательства "
    "о нотариате). Пиши строго официальным русским языком. Структура: заголовок "
    "(вид документа), место и дата прописью, полные данные доверителя (ФИО, дата "
    "рождения, гражданство, паспорт: серия, номер, кем и когда выдан), полные "
    "данные представителя, подробные полномочия по смыслу задания, срок действия "
    "(если уместен — один год, если не указан иной), право/запрет передоверия, "
    "отметка о разъяснении статей закона, строка для подписи доверителя, затем "
    "удостоверительная надпись нотариуса: «{city}. <дата прописью>. Настоящая "
    "доверенность удостоверена мной, {notary}, нотариусом города Москвы…» с "
    "местами для реестрового номера и тарифа (оставь «№ ________»). Верни ТОЛЬКО "
    "текст документа, без пояснений и без markdown."
).format(city=NOTARY_CITY, notary=NOTARY_FIO)


@dataclass(frozen=True)
class DoverResult:
    docx_path: Path
    pdf_path: Path


def _passport_block(label: str, p: Passport | None) -> str:
    if p is None:
        return f"{label}: не указан"
    parts = [f"{label}: {p.surname} {p.name} {p.patronymic or ''}".strip()]
    if p.birth_date:
        parts.append(f"дата рождения {_date_dmy(p.birth_date)}")
    if p.nationality:
        parts.append(f"гражданство {p.nationality}")
    num = f"{p.series or ''}{p.number}".strip()
    parts.append(f"паспорт {num}")
    if p.issue_date:
        parts.append(f"выдан {_date_dmy(p.issue_date)}")
    if p.issued_by:
        parts.append(f"кем выдан: {p.issued_by}")
    return ", ".join(parts)


class DoverService:
    def __init__(self, key_getter) -> None:
        self._key_getter = key_getter

    def generate(
        self,
        principal: Passport,
        agent: Passport | None,
        *,
        doc_type: str,
        description: str,
        form_date: date,
        output_dir: Path | None = None,
    ) -> DoverResult:
        text = self._compose(principal, agent, doc_type=doc_type,
                             description=description, form_date=form_date)
        folder = output_dir if output_dir is not None else paths.output_dir() / "dover"
        folder.mkdir(parents=True, exist_ok=True)
        stem = "".join(c if c.isalnum() or c in "_- " else "_"
                       for c in f"{principal.surname}_{principal.name}".upper()) or "DOVER"
        base = folder / f"{stem}_ДОВЕРЕННОСТЬ"
        i = 1
        while base.with_suffix(".pdf").exists():
            base = folder / f"{stem}_ДОВЕРЕННОСТЬ_{i:03d}"
            i += 1
        docx_path = self._to_docx(text, base.with_suffix(".docx"))
        pdf_path = self._to_pdf(text, base.with_suffix(".pdf"))
        log.info("Dover draft for %s (%s)", principal.surname, doc_type)
        return DoverResult(docx_path=docx_path, pdf_path=pdf_path)

    # ------------------------------------------------------------------
    def _compose(self, principal, agent, *, doc_type, description, form_date) -> str:
        key = (self._key_getter() or "").strip()
        if not key:
            raise OfisError("AI kaliti yo'q — Sozlamalarga Gemini kalitini kiriting.")
        chosen = "" if doc_type.startswith("Авто") else f"Вид документа: {doc_type}. "
        user = (
            f"{chosen}Дата составления: {_date_dmy(form_date)}. "
            f"{_passport_block('Доверитель', principal)}. "
            f"{_passport_block('Представитель (поверенный)', agent)}. "
            f"Задание от оператора (кто, кому, для чего): {description or 'не указано'}"
        )
        body = json.dumps({
            "contents": [{"parts": [{"text": _SYSTEM + "\n\n" + user}]}],
        }).encode()
        last = ""
        for model in ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest"):
            url = ("https://generativelanguage.googleapis.com/v1beta/models/"
                   f"{model}:generateContent?key={key}")
            req = urllib.request.Request(url, data=body,
                                         headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=90) as resp:
                    payload = json.loads(resp.read().decode())
                parts = payload["candidates"][0]["content"]["parts"]
                text = "\n".join(p.get("text", "") for p in parts).strip()
                if text:
                    return text
            except Exception as exc:  # noqa: BLE001 - try next model
                last = str(exc)[:150]
        raise OfisError(f"AI javob bermadi: {last}")

    @staticmethod
    def _to_docx(text: str, out: Path) -> Path:
        import docx
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Pt

        doc = docx.Document()
        style = doc.styles["Normal"]
        style.font.name = "Times New Roman"
        style.font.size = Pt(12)
        for i, line in enumerate(text.split("\n")):
            p = doc.add_paragraph(line.strip())
            p.alignment = (WD_ALIGN_PARAGRAPH.CENTER if i < 2 and line.strip()
                           else WD_ALIGN_PARAGRAPH.JUSTIFY)
        doc.save(str(out))
        return out

    @staticmethod
    def _to_pdf(text: str, out: Path) -> Path:
        import fitz

        doc = fitz.open()
        font_path = str(_font_file("OfisSerif"))
        rect = fitz.Rect(60, 60, 535, 780)
        remaining = text.strip()
        while remaining:
            chunk = remaining
            while True:
                page = doc.new_page(width=595, height=842)
                page.insert_font(fontname="dover", fontfile=font_path)
                spill = page.insert_textbox(rect, chunk, fontname="dover",
                                            fontsize=12, lineheight=1.35, align=3)
                if spill >= 0 or len(chunk) <= 200:
                    break
                doc.delete_page(doc.page_count - 1)
                cut = chunk.rfind("\n", 0, int(len(chunk) * 0.85))
                chunk = chunk[:cut if cut > 0 else int(len(chunk) * 0.85)]
            remaining = remaining[len(chunk):].strip()
        out.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(out), garbage=4, deflate=True)
        doc.close()
        return out
