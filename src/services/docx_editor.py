"""Word (.docx) трудовой/уведомление templates: swap the old worker for the new.

Pattern-based like the PDF trud editor — no fixed positions, so any firm's docx
works: the «гражданин республики … именуемый» clause, contract dates, long
Russian dates, the signature «ФАМИЛИЯ И.О.» and the уведомление's label/value
paragraphs are found by text, old values removed, new ones written in place
(keeping each paragraph's original formatting via its first run).
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from src.pdf.formatters import _date_dmy, _date_long_g

_FIO_CLAUSE = re.compile(
    r"(гражданин(?:ка)?\s+республики\s+).+?(\s+именуем)", re.IGNORECASE | re.DOTALL
)
_DMY = re.compile(r"\d{2}\.\d{2}\.\d{4}")
_LONG_DATE = re.compile(r"^\d{1,2}\s+[а-яё]+(\s+\d{4}\s*г?\.?)?$", re.IGNORECASE)
_YEAR_ONLY = re.compile(r"^\d{4}\s*г\.?$")
_SIGN_ABBR = re.compile(r"^[А-ЯЁ]{2,}\s+[А-ЯЁ]\.\s*[А-ЯЁ]\.$")


def _set_text(paragraph, text: str) -> None:
    """Replace a paragraph's text, keeping the first run's formatting."""
    if paragraph.runs:
        paragraph.runs[0].text = text
        for run in paragraph.runs[1:]:
            run.text = ""
    else:
        paragraph.add_run(text)


def _iter_paragraphs(doc):
    yield from doc.paragraphs
    seen = set()
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                if id(cell._tc) in seen:
                    continue
                seen.add(id(cell._tc))
                yield from cell.paragraphs


class TrudDocxEditor:
    def fill_trudovoy(
        self,
        template: Path,
        out: Path,
        *,
        form_date: date,
        fio_upper: str,          # ШОДИЕВ БОКИ ЗОКИР УГЛИ
        citizenship_upper: str,  # УЗБЕКИСТАН
        sign_abbr: str,          # ШОДИЕВ Б.З.
        contract_end: date | None,
        profession: str,
    ) -> Path:
        import docx

        doc = docx.Document(str(template))
        long_date = _date_long_g(form_date)
        srok_done = False
        for p in _iter_paragraphs(doc):
            text = p.text
            stripped = text.strip()
            if not stripped:
                continue
            if _FIO_CLAUSE.search(text):
                new = _FIO_CLAUSE.sub(
                    lambda m: f"{m.group(1)}{citizenship_upper} {fio_upper}{m.group(2)}", text
                )
                _set_text(p, new)
                continue
            if "Срок договора" in text and _DMY.search(text) and not srok_done:
                dates = [_date_dmy(form_date)]
                if contract_end:
                    dates.append(_date_dmy(contract_end))
                it = iter(dates)
                _set_text(p, _DMY.sub(lambda m: next(it, m.group(0)), text))
                srok_done = True
                continue
            if "Срок договора" not in text and _DMY.fullmatch(stripped):
                _set_text(p, _date_dmy(form_date))
                continue
            if _LONG_DATE.match(stripped) and "г" in stripped and len(stripped) > 8:
                _set_text(p, long_date)
                continue
            if _LONG_DATE.match(stripped) and len(stripped) <= 12 and any(
                mon in stripped.lower() for mon in
                ("январ", "феврал", "март", "апрел", "мая", "июн", "июл",
                 "август", "сентябр", "октябр", "ноябр", "декабр")
            ):
                _set_text(p, f"{form_date.day:02d} {_date_long_g(form_date).split()[1]}")
                continue
            if _YEAR_ONLY.match(stripped):
                _set_text(p, f"{form_date.year} г.")
                continue
            if _SIGN_ABBR.match(stripped):
                _set_text(p, sign_abbr)
                continue
            m = re.search(r"(должности:|обязанности:)\s*(\S.*)$", stripped)
            if m:
                _set_text(p, stripped[: stripped.index(m.group(1)) + len(m.group(1))] + " " + profession)
        # A separate «Срок договора» row may keep bare dd.mm.yyyy cells; handled
        # above via the fullmatch branch (first = start, others already equal).
        out.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(out))
        return out

    def fill_uvedomlenie(self, template: Path, out: Path, values: dict[str, str]) -> Path:
        """``values`` keys: surname, name, patronymic, birth_date, gender,
        citizenship, birth_place, pass_series, pass_number, pass_issue_date,
        pass_issued_by, pat_series, pat_number, region, blank_series,
        blank_number, profession, contract_date."""
        import docx

        doc = docx.Document(str(template))
        paras = [p for p in _iter_paragraphs(doc)]
        section = "passport"
        pending: str | None = None

        def label_for(stripped: str) -> tuple[str, str] | None:
            nonlocal section
            if stripped.startswith("Сведения о разрешении"):
                section = "patent"
                return None
            table = [
                ("Фамилия (рус.)", "surname"), ("Имя (рус.)", "name"),
                ("Отчество (рус.)", "patronymic"), ("Дата рождения", "birth_date"),
                ("Пол", "gender"), ("Гражданство", "citizenship"),
                ("Место рождения", "birth_place"),
                ("Серия бланка", "blank_series"), ("Номер бланка", "blank_number"),
                ("Дата выдачи", "pass_issue_date"), ("Кем выдан", "pass_issued_by"),
                ("Регион", "region"),
                ("Дата заключения договора", "contract_date"),
                ("Профессия", "profession"),
                ("Серия", "pass_series" if section == "passport" else "pat_series"),
                ("Номер", "pass_number" if section == "passport" else "pat_number"),
            ]
            for label, key in table:
                if stripped.startswith(label):
                    return label, key
            return None

        for p in paras:
            stripped = p.text.strip()
            if not stripped:
                continue
            if pending is not None:
                if pending in values:
                    _set_text(p, values[pending])
                pending = None
                continue
            hit = label_for(stripped)
            if hit is None:
                continue
            label, key = hit
            rest = stripped[len(label):].strip()
            if key == "profession":
                # two-line label; the value is the next non-empty paragraph
                pending = key
                continue
            if rest:
                if key in values:
                    _set_text(p, f"{label} {values[key]}")
            else:
                pending = key
        out.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(out))
        return out


def docx_to_pdf(docx_path: Path) -> Path | None:
    """Convert via MS Word when available (Windows); else return None and the
    .docx itself is the deliverable."""
    pdf = docx_path.with_suffix(".pdf")
    try:
        from docx2pdf import convert  # type: ignore

        convert(str(docx_path), str(pdf))
        if pdf.exists():
            return pdf
    except Exception:  # noqa: BLE001 - no Word / not Windows
        pass
    # LibreOffice fallback (soffice on PATH)
    try:
        import subprocess

        subprocess.run(
            ["soffice", "--headless", "--convert-to", "pdf",
             "--outdir", str(docx_path.parent), str(docx_path)],
            capture_output=True, timeout=120, check=True,
        )
        if pdf.exists():
            return pdf
    except Exception:  # noqa: BLE001
        pass
    return None
