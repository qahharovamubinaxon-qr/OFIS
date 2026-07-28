"""Taking a value off a PDF and putting another in its place — and proving it.

Three things kept going wrong when the previous worker was swapped for the next
one: a value was not written at all, a value landed somewhere it did not belong,
and the old value was still there underneath. Each was patched where it showed.
This module fixes the cause instead:

**Erasing.** The old value's rectangles are found with ``search_for`` and
removed with a redaction, which deletes the text from the content stream. A
white rectangle only hides it — copy the PDF's text and the old worker is still
in there, which for a passport number is a real leak, not a cosmetic one.

**Writing.** The new value is typeset inside that same rectangle, shrinking the
font until it fits. If even the smallest readable size will not fit, the value
is written anyway and the caller is *told* — silently trimming a passport
number is the worst of the three options.

**Proving.** Nothing is trusted. After the file is saved it is opened again and
read back: every new value must be findable, and none of the old ones may
remain. A failure names the field, so the operator learns which one to look at
instead of discovering it at the ministry counter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import fitz

from src.common.errors import OfisError
from src.common.logging import get_logger
from src.pdf.engine import _font_file

log = get_logger(__name__)

MIN_SIZE = 5.0          # below this nobody can read it anyway
SHRINK_STEP = 0.25
PAD = 1.0               # a hair of room inside the old rectangle


class FillNotVerified(OfisError):
    """Raised when the finished PDF does not say what it was told to say."""

    code = "pdf.not_verified"


@dataclass
class Report:
    """What was written, what would not fit, and what refused to go away."""

    written: dict[str, str] = field(default_factory=dict)
    erased: list[str] = field(default_factory=list)
    overflow: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    left_over: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.missing or self.left_over)

    def problems(self) -> list[str]:
        out = [f"«{name}» ёзилмади" for name in self.missing]
        out += [f"эски қиймат «{value}» ўчмади" for value in self.left_over]
        out += [f"«{name}» жойга сиғмади — текширинг" for name in self.overflow]
        return out


# ------------------------------------------------------------------ erasing


def find(page: fitz.Page, value: str) -> list[fitz.Rect]:
    """Every rectangle on the page holding ``value``.

    Tried as printed first, then with the spacing collapsed — a PDF often puts
    «FB 1234567» where the data said «FB1234567».
    """
    value = (value or "").strip()
    if len(value) < 2:
        return []
    rects = list(page.search_for(value))
    if not rects and " " in value:
        rects = list(page.search_for(value.replace(" ", "")))
    if not rects and " " not in value:
        rects = list(page.search_for(" ".join(value)))
    return rects


def erase(page: fitz.Page, values: list[str], report: Report | None = None) -> int:
    """Really remove each value from the page — not paint over it."""
    count = 0
    for value in values:
        for rect in find(page, value):
            page.add_redact_annot(rect)
            count += 1
        if report is not None and find(page, value):
            report.erased.append(value)
    if count:
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
    return count


# ------------------------------------------------------------------ writing


def fit_size(font: fitz.Font, text: str, width: float, size: float) -> float:
    """The largest size at or below ``size`` that still fits ``width``."""
    if width <= 0:
        return size
    while size > MIN_SIZE and font.text_length(text, fontsize=size) > width:
        size -= SHRINK_STEP
    return size


def write(page: fitz.Page, rect: fitz.Rect, text: str, *, fontname: str,
          font: fitz.Font, size: float, name: str = "",
          report: Report | None = None) -> float:
    """Typeset ``text`` inside ``rect``, shrinking to fit. Returns the size used.

    A value that will not fit even at the smallest readable size is written in
    full and recorded as an overflow — the operator is told rather than handed
    a quietly truncated document.
    """
    text = (text or "").strip()
    if not text:
        return size
    width = rect.width - 2 * PAD
    used = fit_size(font, text, width, size)
    if font.text_length(text, fontsize=used) > width and report is not None:
        report.overflow.append(name or text[:24])
        log.warning("Value does not fit its box: %s", name or text[:40])
    baseline = rect.y1 - max(1.0, (rect.height - used) / 2)
    page.insert_text((rect.x0 + PAD, baseline), text,
                     fontname=fontname, fontsize=used)
    if report is not None and name:
        report.written[name] = text
    return used


def install_font(page: fitz.Page, family: str = "OfisSansRegular",
                 alias: str = "ofis") -> tuple[str, fitz.Font]:
    """Embed the app's Cyrillic face and hand back its name and metrics."""
    path = _font_file(family)
    page.insert_font(fontname=alias, fontfile=str(path))
    return alias, fitz.Font(fontfile=str(path))


# ------------------------------------------------------------------ proving


def read_text(pdf: Path) -> str:
    """Everything the finished document actually says."""
    doc = fitz.open(str(pdf))
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def _present(haystack: str, needle: str) -> bool:
    """Is the value in the page text, however the PDF spaced it out?"""
    needle = (needle or "").strip()
    if not needle:
        return True
    if needle in haystack:
        return True
    squashed = "".join(haystack.split())
    return "".join(needle.split()) in squashed


def verify(pdf: Path, *, must_contain: dict[str, str],
           must_not_contain: list[str] | None = None,
           written: str = "", report: Report | None = None) -> Report:
    """Read the finished PDF back and check it says what it was told to.

    ``must_contain`` is field name → value, so a failure can name the field.
    Keep those short — a whole paragraph would pin the line wrapping too.
    ``must_not_contain`` is the previous worker's values: none may survive.
    ``written`` is everything that was written this time; anything appearing in
    it cannot be a leftover, however it also appeared before.
    """
    report = report or Report()
    text = read_text(pdf)
    for name, value in must_contain.items():
        if value and not _present(text, value):
            report.missing.append(name)

    # A value the two workers share is not a leftover: both may be «Узбекистан»,
    # and reporting that as the old worker surviving would be a false alarm.
    written = " ".join([*must_contain.values(), written])
    for old in must_not_contain or []:
        if not old or len(old.strip()) <= 2:
            continue
        if _present(written, old):
            continue
        if _present(text, old):
            report.left_over.append(old)
    if report.ok:
        log.info("Verified %s: %d values present, nothing of the old left",
                 pdf.name, len(must_contain))
    else:
        log.warning("Verification failed for %s: %s", pdf.name,
                    "; ".join(report.problems()))
    return report


def verify_or_raise(pdf: Path, *, must_contain: dict[str, str],
                    must_not_contain: list[str] | None = None) -> Report:
    """The same check, but a failure stops the run instead of shipping."""
    report = verify(pdf, must_contain=must_contain,
                    must_not_contain=must_not_contain)
    if not report.ok:
        raise FillNotVerified("PDF текширувдан ўтмади: " + "; ".join(report.problems()),
                              context={"file": str(pdf),
                                       "missing": report.missing,
                                       "left_over": report.left_over})
    return report
