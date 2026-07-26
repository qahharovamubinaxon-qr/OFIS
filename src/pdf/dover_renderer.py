"""Render a notarial draft onto the office's scanned notarial blank.

Layout rules (mirror the approved образец):
- the document title (СОГЛАСИЕ / ДОВЕРЕННОСТЬ / …), «Город Москва.» and the
  date-in-words line are CENTERED;
- body paragraphs are justified;
- the blank's series number at the top is redrawn per document (the bundled
  page1 scan is pre-cleaned of its printed number);
- page 1 uses the blank with the ornament header, later pages the plain
  continuation blank.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.config import paths
from src.pdf.engine import _font_file

# safe text area inside the guilloche frame (A4 points)
_X0, _X1 = 75.0, 520.0
_PAGE1_TOP, _PAGE_TOP, _BOTTOM = 150.0, 70.0, 795.0
_SERIES_Y = 110.0
_SERIES_COLOR = (0.64, 0.30, 0.26)
_BODY_SIZE = 12.0
_TITLE_SIZE = 14.0
_LEADING = 1.42

_CENTER, _JUSTIFY, _TITLE, _NOTARY = "center", "justify", "title", "notary"

# красная строка — first-line indent of a body paragraph (≈1 cm)
PARA_INDENT = 28.0

_ENUM_RE = re.compile(r"^(\d+[\.)]\s|[-–—•]\s)")
_TERMINAL = (".", ":", ";", "!", "?", "_")


def blank_dir() -> Path:
    return paths.templates_dir() / "dover_blank"


def _is_special(stripped: str, *, first: bool, prev_city: bool) -> bool:
    low = stripped.lower()
    if first or low.startswith(("город москва", "нотариус:", "подпись",
                                "зарегистрировано", "уплачено")):
        return True
    return prev_city and not any(c.isdigit() for c in stripped) and (
        "года" in low or "тысячи" in low
    )


def _reflow(lines: list[str]) -> list[str]:
    """Merge hard-wrapped body lines back into full paragraphs.

    AI (and pasted samples) often break one sentence across several short
    lines; printed to the blank that leaves one-word lines. A body line is
    glued to the previous paragraph unless the paragraph already ends a
    sentence (terminal punctuation), a blank line intervenes, an enumeration
    item starts, or either line is a special (title/city/date/…) line."""
    out: list[str] = []
    seen_first = False
    prev_city = False
    prev_special = True
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            out.append("")
            prev_special = True
            prev_city = False
            continue
        special = _is_special(stripped, first=not seen_first, prev_city=prev_city)
        seen_first = True
        prev_city = stripped.lower().startswith("город москва")
        if special or prev_special or _ENUM_RE.match(stripped) or not out:
            out.append(stripped)
        else:
            prev = out[-1]
            if prev and not prev.endswith(_TERMINAL):
                out[-1] = prev + " " + stripped
            else:
                out.append(stripped)
        prev_special = special
    return out


def _classify(lines: list[str]) -> list[tuple[str, str]]:
    """Tag each logical (reflowed) line with its layout role."""
    out: list[tuple[str, str]] = []
    seen_title = False
    prev_city = False
    for line in _reflow(lines):
        stripped = line.strip()
        if not stripped:
            out.append((_JUSTIFY, ""))
            prev_city = False
            continue
        low = stripped.lower()
        if not seen_title:
            seen_title = True
            out.append((_TITLE, stripped))
            continue
        if low.startswith("город москва"):
            out.append((_CENTER, stripped))
            prev_city = True
            continue
        is_date_words = prev_city and not any(c.isdigit() for c in stripped) and (
            "года" in low or "тысячи" in low
        )
        prev_city = False
        if is_date_words:
            out.append((_CENTER, stripped))
            continue
        if low.startswith("нотариус:"):
            out.append((_NOTARY, stripped))
            continue
        out.append((_JUSTIFY, stripped))
    return out


def render_dover_pdf(text: str, out: Path, *, series: str | None) -> Path:
    import fitz

    serif = fitz.Font(fontfile=str(_font_file("OfisSerif")))
    bold = fitz.Font(fontfile=str(_font_file("OfisSerifBold")))
    width = _X1 - _X0

    bg1, bg2 = blank_dir() / "page1.jpg", blank_dir() / "page2.jpg"
    have_blank = bg1.exists()

    doc = fitz.open()
    page = None
    tw = None
    y = 0.0

    def new_page() -> None:
        nonlocal page, tw, y
        if page is not None and tw is not None:
            tw.write_text(page)
        page = doc.new_page(width=595, height=842)
        first = doc.page_count == 1
        if have_blank:
            bg = bg1 if first else (bg2 if bg2.exists() else bg1)
            page.insert_image(page.rect, filename=str(bg))
        tw = fitz.TextWriter(page.rect, color=(0, 0, 0))
        if first and series and have_blank:
            stw = fitz.TextWriter(page.rect, color=_SERIES_COLOR)
            s_width = bold.text_length(series, fontsize=13.5)
            stw.append((297.5 - s_width / 2, _SERIES_Y), series, font=bold, fontsize=13.5)
            stw.write_text(page)
        y = _PAGE1_TOP if first else _PAGE_TOP

    def ensure_room(needed: float) -> None:
        if page is None or y + needed > _BOTTOM:
            new_page()

    def wrap(words: list[str], font, size: float,
             first_indent: float = 0.0) -> list[list[str]]:
        rows: list[list[str]] = []
        cur: list[str] = []
        cur_w = 0.0
        space = font.text_length(" ", fontsize=size)
        for w in words:
            ww = font.text_length(w, fontsize=size)
            avail = width - (first_indent if not rows else 0.0)
            if cur and cur_w + space + ww > avail:
                rows.append(cur)
                cur, cur_w = [w], ww
            else:
                cur_w += (space if cur else 0) + ww
                cur.append(w)
        if cur:
            rows.append(cur)
        return rows

    step = _BODY_SIZE * _LEADING
    for role, content in _classify(text.strip().splitlines()):
        if not content:
            y += step * 0.55
            continue
        if role == _TITLE:
            ensure_room(_TITLE_SIZE * _LEADING + 6)
            w = bold.text_length(content, fontsize=_TITLE_SIZE)
            tw.append((_X0 + (width - w) / 2, y + _TITLE_SIZE), content,
                      font=bold, fontsize=_TITLE_SIZE)
            y += _TITLE_SIZE * _LEADING + 4
            continue
        if role == _CENTER:
            ensure_room(step)
            w = serif.text_length(content, fontsize=_BODY_SIZE)
            tw.append((_X0 + (width - w) / 2, y + _BODY_SIZE), content,
                      font=serif, fontsize=_BODY_SIZE)
            y += step
            continue
        if role == _NOTARY:
            ensure_room(step * 2)
            y += step * 0.6
            name = content.split(":", 1)[1].strip()
            tw.append((_X0, y + _BODY_SIZE), "Нотариус:", font=serif, fontsize=_BODY_SIZE)
            if name:
                nw = serif.text_length(name, fontsize=_BODY_SIZE)
                tw.append((_X1 - nw, y + _BODY_SIZE), name, font=serif, fontsize=_BODY_SIZE)
            y += step
            continue
        # justified paragraph with красная строка on its first line
        indent = 0.0 if content.lower().startswith(("подпись", "зарегистрировано",
                                                    "уплачено")) else PARA_INDENT
        words = content.split()
        rows = wrap(words, serif, _BODY_SIZE, first_indent=indent)
        for i, row in enumerate(rows):
            ensure_room(step)
            x_start = _X0 + (indent if i == 0 else 0.0)
            row_width = _X1 - x_start
            last = i == len(rows) - 1
            if last or len(row) == 1:
                tw.append((x_start, y + _BODY_SIZE), " ".join(row),
                          font=serif, fontsize=_BODY_SIZE)
            else:
                total = sum(serif.text_length(w, fontsize=_BODY_SIZE) for w in row)
                gap = (row_width - total) / (len(row) - 1)
                x = x_start
                for w in row:
                    tw.append((x, y + _BODY_SIZE), w, font=serif, fontsize=_BODY_SIZE)
                    x += serif.text_length(w, fontsize=_BODY_SIZE) + gap
            y += step

    if page is not None and tw is not None:
        tw.write_text(page)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out), garbage=4, deflate=True)
    doc.close()
    return out


_DROP_RE = re.compile(
    r"зарегистрировано в реестре|по тарифу|^\s*нотариус\b|реестров\w* номер",
    re.IGNORECASE,
)


def finalize_notarial_text(ai_text: str, *, reestr: int, tarif: str,
                           notary_short: str) -> str:
    """Strip whatever реестр/тариф/нотариус lines the AI produced and append
    the office's fixed block with the real numbers."""
    lines = [ln for ln in ai_text.splitlines() if not _DROP_RE.search(ln)]
    while lines and not lines[-1].strip():
        lines.pop()
    lines += [
        f"Зарегистрировано в реестре: № {reestr}",
        f"Уплачено по тарифу: {tarif} руб.",
        "",
        f"Нотариус: {notary_short}",
    ]
    return "\n".join(lines)
