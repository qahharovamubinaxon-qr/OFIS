"""ТРУДАВОЙ/УВЕДОМЛЕНИЕ — print onto the firms' own filled samples.

Every firm's ТД and УВ was mapped 1:1 off its sample: each slot knows where
the old worker's value sits (the ``clear`` rectangle) and where the new one
starts. Rendering paints the old value white and writes the new one at the
same spot, in the same size and face — so the finished document is the
firm's own paper with only the worker changed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import fitz

from src.common.errors import OfisError
from src.pdf.engine import _font_file, _fontname

TEXT_OPACITY = 1.0

_FACES = {(False, False): "OfisSansRegular", (False, True): "OfisSans",
          (True, False): "OfisSerif", (True, True): "OfisSerifBold"}


@dataclass
class Trud8Data:
    surname: str = ""
    name: str = ""
    patronymic: str = ""
    gender: str = ""                  # "male" | "female"
    citizenship: str = ""
    birth_date: date | None = None
    pass_series: str = ""
    pass_number: str = ""
    pass_issued: date | None = None
    pass_issued_by: str = ""
    pat_series: str = ""
    pat_number: str = ""
    pat_blank_series: str = ""
    pat_blank_number: str = ""
    pat_issued: date | None = None
    profession: str = ""
    deal_date: date | None = None
    layout: dict = field(default_factory=dict)

    def fio(self) -> str:
        parts = [p.strip() for p in (self.surname, self.name, self.patronymic)
                 if (p or "").strip()]
        return _title(" ".join(parts))


def _title(text: str) -> str:
    return " ".join(w.capitalize() for w in (text or "").split())


def _dots(value: date | None) -> str:
    return f"{value:%d.%m.%Y}" if value else ""


def values(data: Trud8Data) -> dict[str, str]:
    """Every mapped key's finished text — the samples' own manner."""
    return {
        "surname": _title(data.surname),
        "name": _title(data.name),
        "patronymic": _title(data.patronymic),
        "fio": data.fio(),
        "gender": "Женский" if data.gender == "female" else "Мужской",
        "citizenship": _title(data.citizenship),
        "birth_place": _title(data.citizenship),
        "birth_date": _dots(data.birth_date),
        "pass_series": (data.pass_series or "").upper(),
        "pass_number": (data.pass_number or "").upper(),
        "pass_issued": _dots(data.pass_issued),
        "pass_issued_by": (data.pass_issued_by or "").upper(),
        "pat_series": (data.pat_series or "").upper(),
        "pat_number": (data.pat_number or "").upper(),
        "pat_blank_series": (data.pat_blank_series or "").upper(),
        "pat_blank_number": (data.pat_blank_number or "").upper(),
        "pat_issued": _dots(data.pat_issued),
        "profession": (data.profession or "").strip().capitalize(),
        "deal_date": _dots(data.deal_date),
    }


def render(data: Trud8Data, template: Path, slots: list[dict],
           layout: dict | None = None) -> bytes:
    """One document: the firm's sample with the worker replaced."""
    if not Path(template).exists():
        raise OfisError("Фирманинг бланкаси топилмади — бўлимда юкланг.")
    texts = values(data)
    moved = ((layout or {}).get("fields") or {})
    with fitz.open(str(template)) as doc:
        # the old worker is REDACTED — removed from the text layer, not
        # merely painted over, so nothing of the sample's person survives
        # in a copy-paste or a search
        touched = set()
        for slot in slots:
            page = doc[slot["page"] - 1]
            pw, ph = page.rect.width, page.rect.height
            x0, y0, x1, y1 = slot["clear"]
            page.add_redact_annot(
                fitz.Rect(x0 * pw, y0 * ph, x1 * pw, y1 * ph), fill=(1, 1, 1))
            touched.add(slot["page"] - 1)
        for index in touched:
            doc[index].apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
        for index, slot in enumerate(slots):
            text = texts.get(slot["key"]) or ""
            if not text:
                continue
            page = doc[slot["page"] - 1]
            pw, ph = page.rect.width, page.rect.height
            x, baseline, size = slot["x"], slot["baseline"], slot["size"]
            override = moved.get(f"{slot['key']}#{index}")
            if override and len(override) == 3:
                x, baseline, size = (float(v) for v in override)
            family = _FACES[(bool(slot.get("serif")), bool(slot.get("bold")))]
            page.insert_text((x * pw, baseline * ph), text,
                             fontsize=size * ph,
                             fontfile=str(_font_file(family)),
                             fontname=_fontname(family), color=(0, 0, 0),
                             fill_opacity=TEXT_OPACITY)
        return doc.tobytes()


def output_stem(data: Trud8Data) -> str:
    parts = [p.strip().upper() for p in (data.surname, data.name)
             if (p or "").strip()]
    stem = "_".join(parts) or "TRUD"
    return "".join(c for c in stem if c.isalnum() or c in "_-") or "TRUD"
