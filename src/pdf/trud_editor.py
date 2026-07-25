"""Edit a трудовой договор text-PDF: swap the old worker's data for the new.

The firm's template is a real text PDF whose page 1 carries the previous
worker's block. Four spots are re-written (found by pattern, never by fixed
coordinates, so any firm's template works):

* the standalone contract date (``dd.mm.yyyy`` line near the top);
* the «Работник: …» paragraph (name, birth date, citizenship, passport);
* «…в должности: X» and «…обязанности: X» — the profession after the colon.

Old text is removed with redactions (really deleted, not covered), then the new
text is typeset in the same spot at the template's own font size.
"""

from __future__ import annotations

import re
from pathlib import Path

import fitz

from src.common.errors import TemplateMissingError
from src.pdf.engine import _font_file  # reuse the family resolution

_DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")


def _page_lines(page: fitz.Page) -> list[dict]:
    """Flatten to lines: text, bbox, size of first span, origin."""
    out = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            text = "".join(s["text"] for s in spans)
            if not text.strip():
                continue
            out.append({
                "text": text,
                "bbox": fitz.Rect(line["bbox"]),
                "size": spans[0]["size"],
                "origin": spans[0]["origin"],
            })
    return out


class TrudDocEditor:
    def __init__(self) -> None:
        self._font_path = _font_file("OfisSansRegular")
        self._bold_path = _font_file("OfisSans")

    def fill(
        self,
        template_path: Path,
        output_path: Path,
        *,
        date_text: str,  # 23.07.2026
        worker_block: str,  # Работник: … Кем выдан …
        profession: str,  # Подсобный рабочий
    ) -> Path:
        if not template_path.exists():
            raise TemplateMissingError(
                "Трудовой template missing", context={"path": str(template_path)}
            )
        doc = fitz.open(str(template_path))
        try:
            page = doc[0]
            lines = _page_lines(page)

            targets: list[tuple[fitz.Rect, str, float, tuple[float, float], bool]] = []
            worker_rect: fitz.Rect | None = None
            worker_size = 11.0
            worker_origin: tuple[float, float] | None = None
            in_worker = False
            for ln in lines:
                stripped = ln["text"].strip()
                if _DATE_RE.match(stripped) and ln["bbox"].y0 < 200:
                    targets.append((ln["bbox"], date_text, ln["size"], ln["origin"], False))
                    continue
                if stripped.startswith("Работник:"):
                    in_worker = True
                    worker_rect = fitz.Rect(ln["bbox"])
                    worker_size = ln["size"]
                    worker_origin = ln["origin"]
                    continue
                if in_worker:
                    # The worker paragraph continues until a blank-ish gap or a
                    # numbered section starts.
                    if stripped.startswith(("1.", "ПРЕДМЕТ")) or ln["bbox"].y0 - worker_rect.y1 > ln["size"] * 1.6:
                        in_worker = False
                    else:
                        worker_rect |= ln["bbox"]
                        continue
                m = re.search(r"(должности:|обязанности:)\s*(.+)$", stripped)
                if m and m.group(2).strip():
                    targets.append((ln["bbox"],
                                    ln["text"][: ln["text"].index(m.group(1)) + len(m.group(1))]
                                    + " " + profession,
                                    ln["size"], ln["origin"], False))

            for rect, *_ in targets:
                page.add_redact_annot(rect)
            if worker_rect is not None:
                page.add_redact_annot(worker_rect)
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

            page.insert_font(fontname="trud_r", fontfile=str(self._font_path))
            page.insert_font(fontname="trud_b", fontfile=str(self._bold_path))
            for rect, text, size, origin, _bold in targets:
                page.insert_text((origin[0], origin[1]), text, fontname="trud_r", fontsize=size)
            if worker_rect is not None and worker_origin is not None:
                self._write_worker_block(page, worker_rect, worker_origin, worker_block, worker_size)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            doc.save(str(output_path), garbage=4, deflate=True)
        finally:
            doc.close()
        return output_path

    def _write_worker_block(
        self, page: fitz.Page, rect: fitz.Rect, origin: tuple[float, float],
        text: str, size: float,
    ) -> None:
        """Word-wrap the new «Работник: …» paragraph into the old block's area
        (the label itself is typeset bold, like the template's other labels)."""
        font = fitz.Font(fontfile=str(self._font_path))
        max_w = rect.x1 - origin[0] + 10
        words = text.split()
        lines: list[str] = []
        cur = ""
        for w in words:
            cand = f"{cur} {w}".strip()
            if cur and font.text_length(cand, fontsize=size) > max_w:
                lines.append(cur)
                cur = w
            else:
                cur = cand
        if cur:
            lines.append(cur)
        y = origin[1]
        lh = size * 1.35
        for i, line in enumerate(lines):
            x = origin[0]
            if i == 0 and line.startswith("Работник:"):
                page.insert_text((x, y), "Работник:", fontname="trud_b", fontsize=size)
                label_w = fitz.Font(fontfile=str(self._bold_path)).text_length(
                    "Работник:", fontsize=size
                )
                page.insert_text((x + label_w + 3, y), line[len("Работник:"):].strip(),
                                 fontname="trud_r", fontsize=size)
            else:
                page.insert_text((x, y), line, fontname="trud_r", fontsize=size)
            y += lh
