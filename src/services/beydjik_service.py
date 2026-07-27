"""БЕЙДЖИК — the office's own worker ID badge, printed and laminated.

ООО СФЕРА gives every worker a wearable badge. There are two region layouts —
77 Москва and 50 Московская область — the second of which also carries the
worker's должность. The operator picks the region, drops the worker's photo and
passport, and types the badge-specific fields (region code, personal number,
ИНН, issuing firm, date, and — for the область layout — the должность). The
worker's name, date of birth, citizenship and passport number come off the
passport, and the photo is cropped to the badge frame.

The badge is a single small page: the front sits upright at the top and the
back is printed rotated 180° at the bottom, so a printed sheet folds into a
two-sided card. Coordinates were measured off the office's own filled badge.

Blanks are per region and replaceable: the office can drop a nicer design into
AppData (``templates/beydjik/<region>.pdf``) and the module prints on that.
The badge serial (``ПР …``) counts up from a number the operator sets — it is
the company's own badge numbering, not a government-issued identifier.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import fitz

from src.common.errors import OfisError
from src.common.logging import get_logger
from src.config import paths
from src.domain.documents import Passport
from src.pdf.engine import _font_file
from src.pdf.formatters import _date_dmy

log = get_logger(__name__)

# region code → (label, bundled blank, does it carry должность?, territory line)
REGIONS: dict[str, dict] = {
    "77": {"label": "77 — Москва", "blank": "msk_blank.pdf",
           "dolzhnost": False, "territory": "г. Москва"},
    "50": {"label": "50 — Московская область", "blank": "obl_blank.pdf",
           "dolzhnost": True, "territory": "Московская область"},
}

KEY_PR_NEXT = "beydjik.pr_next"
KEY_FIRM = "beydjik.firm"
DEFAULT_FIRM = "ООО СФЕРА"

# ------------------------------------------------------------ geometry
# Every number below was measured off the office's own filled badge, by
# subtracting the blank from the filled copy at 600 dpi so only the typed
# values remained. The blank's labels are Arial Bold; the values the office
# typed are Arial Regular — 10pt in their Word original, which the badge's
# own page scale renders at 7pt here.
_FONT, _FONT_BOLD = "OfisArial", "OfisArialBold"
_SERIF = "OfisSerif"
_SIZE = 7.0                            # ФИО, даты, гражданство, документ…
_SERIA_SIZE = 8.2                      # the серия line runs a little larger
_DATE_SIZE = 8.8                       # «Дата выдачи» is set bold and larger
_PR_SIZE = 15.6                        # «ПР» is Times, matching its own label
_PR_TRACKING = 1.16                    # …and letterspaced, as on the sample

# --- front -------------------------------------------------------------
# the white photo window in the blank, 85.2 × 113.2 pt — very close to 3:4
PHOTO_BOX = (25.7, 53.8, 110.9, 166.9)
PHOTO_ASPECT = (PHOTO_BOX[2] - PHOTO_BOX[0]) / (PHOTO_BOX[3] - PHOTO_BOX[1])

_SERIA_BASE = 66.6
_SERIA_REGION_X = 157.0               # right after the «Серия» label
_SERIA_NUMBER_X = 185.5               # right after «№»

# the value column is not straight: the short labels (Фамилия/Имя/Отчество)
# let their values start earlier than the long ones.
_X_NAME = 166.8
_X_WIDE = 181.9                       # Дата рождения / Гражданство
_X_FULL = 119.4                       # документ and профессия sit on their own
_VALUE_MAX_X = 253.0                  # values shrink rather than leave the card

_ROW_SURNAME = 78.97
_ROW_NAME = 89.05
_ROW_PATRONYMIC = 99.13
_ROW_DOB = 109.21
_ROW_CITIZEN = 119.29
_ROW_DOC = 138.25                     # «паспорт № / ИНН», under its own label
_ROW_DOLZH = 167.93                   # профессия, under its 3-line label (обл)
_DOC_SIZE = 6.6                       # the документ line is set a touch smaller
# the blanks already print the separating «/» at x 157.7–159.3, so the two
# numbers are written on either side of it rather than with a slash of our own
_DOC_PASSPORT_MAX_X = 156.2
_DOC_INN_X = 160.5

# --- back (printed rotated 180°, so an origin is the value's RIGHT edge) --
_BACK_RIGHT = 250.7                   # the back's reading-left margin
# the firm name starts where the bold «Кем выдано» label ends, and any
# continuation returns to the full margin on the line below
_FIRM_FIRST_RIGHT = 196.1
_FIRM_BASE = 315.90
_FIRM_LINE = 10.1                     # a further line goes 10.1pt "higher"
_FIRM_LEFT = 20.0
_DATE_ORIGIN = (251.9, 246.85)
_PR_ORIGIN = (210.4, 210.90)

# «Территория действия патента». Both blanks the office supplied carry
# «Московская область» printed into the artwork, so the line is always cleared
# and rewritten — otherwise a Москва badge would name the wrong region.
_TERRITORY_ORIGIN = (250.7, 325.91)
_TERRITORY_BOX = (180.0, 323.4, 253.5, 333.4)
# a strip of the same guilloche, verified blank on both blanks, used to hide
# the printed line instead of a flat patch
_TERRITORY_DONOR_Y = 292.0


@dataclass(frozen=True)
class BeydjikResult:
    pdf_path: Path
    pr_number: str
    surname: str
    region: str


def _bundled_blank(region: str) -> Path:
    return paths.templates_dir() / "beydjik" / REGIONS[region]["blank"]


def user_blank_path(region: str) -> Path:
    """Where the office drops its own design for this region. In AppData, so a
    `git pull` or an EXE rebuild never overwrites it."""
    return paths.user_templates_dir() / "beydjik" / f"{region}.pdf"


def blank_source(region: str) -> tuple[Path, bool]:
    """(the file to print on, True when it is the office's own upload)."""
    own = user_blank_path(region)
    if own.exists():
        return own, True
    return _bundled_blank(region), False


def import_blank(region: str, source: Path) -> Path:
    """Adopt ``source`` as this region's badge blank, after a size check."""
    import shutil

    if region not in REGIONS:
        raise OfisError("Регион нотўғри.")
    try:
        doc = fitz.open(source)
    except Exception as exc:  # noqa: BLE001
        raise OfisError("PDF ochilmadi — boshqa fayl tanlang.") from exc
    try:
        if len(doc) < 1:
            raise OfisError("PDF bo'sh.")
        rect = doc[0].rect
        # the badge is a small card, not A4
        if not (200 < rect.width < 340 and 300 < rect.height < 460):
            raise OfisError(
                "Bu beydjik o'lchamida emas — badgening PDF blankasini yuklang "
                f"(hozirgi {rect.width:.0f}×{rect.height:.0f} pt).")
    finally:
        doc.close()
    target = user_blank_path(region)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    log.info("БЕЙДЖИК blank replaced for region %s from %s", region, source)
    return target


def _title(text: str) -> str:
    return " ".join(w[:1].upper() + w[1:].lower() for w in (text or "").split())


class BeydjikService:
    def __init__(self, settings) -> None:
        self._settings = settings

    # ------------------------------------------------------- numbering
    def peek_pr(self) -> str:
        try:
            return str(int(self._settings.get(KEY_PR_NEXT, 1) or 1))
        except (TypeError, ValueError):
            return "1"

    def _take_pr(self) -> str:
        current = self.peek_pr()
        self._settings.set(KEY_PR_NEXT, int(current) + 1)
        return current

    def firm(self) -> str:
        return str(self._settings.get(KEY_FIRM, DEFAULT_FIRM) or DEFAULT_FIRM)

    # -------------------------------------------------------- generate
    def generate(
        self,
        passport: Passport,
        *,
        region: str,
        personal_number: str,
        inn: str,
        issue_date: date,
        firm: str | None = None,
        dolzhnost: str = "",
        photo_path: Path | None = None,
        output_dir: Path | None = None,
    ) -> BeydjikResult:
        if region not in REGIONS:
            raise OfisError("Регион танланг: 77 (Москва) ёки 50 (область).")
        blank, _own = blank_source(region)
        if not blank.exists():
            raise OfisError(
                "Бейджик бланкаси топилмади. Sozlamalar → БЕЙДЖИК орқали "
                "бланка PDF сини юкланг.")
        if not personal_number.strip():
            raise OfisError("Шахсий номерни киритинг.")

        pr = self._take_pr()
        firm = (firm or self.firm()).strip()

        doc = fitz.open(blank)
        try:
            page = doc[0]
            page.insert_font(fontname="bj", fontfile=str(_font_file(_FONT)))
            page.insert_font(fontname="bjb", fontfile=str(_font_file(_FONT_BOLD)))
            page.insert_font(fontname="bjs", fontfile=str(_font_file(_SERIF)))
            font = fitz.Font(fontfile=str(_font_file(_FONT)))
            serif = fitz.Font(fontfile=str(_font_file(_SERIF)))
            self._fill_front(page, font, passport, region=region,
                             personal_number=personal_number.strip(),
                             inn=inn.strip(), dolzhnost=dolzhnost.strip())
            self._fill_back(page, font, serif, firm=firm, issue_date=issue_date,
                            pr=pr, territory=REGIONS[region]["territory"])
            self._place_photo(page, photo_path)
            out = self._output_path(passport, region, output_dir)
            doc.save(str(out), garbage=4, deflate=True)
        finally:
            doc.close()

        log.info("БЕЙДЖИК %s %s for %s", region, pr, passport.surname)
        return BeydjikResult(pdf_path=out, pr_number=pr,
                             surname=passport.surname, region=region)

    # ------------------------------------------------------------------
    def _fill_front(self, page, font, passport: Passport, *, region: str,
                    personal_number: str, inn: str, dolzhnost: str) -> None:
        self._text(page, font, region, _SERIA_REGION_X, _SERIA_BASE,
                   size=_SERIA_SIZE)
        self._text(page, font, personal_number, _SERIA_NUMBER_X, _SERIA_BASE,
                   size=_SERIA_SIZE, max_x=_VALUE_MAX_X)

        self._text(page, font, _title(passport.surname or ""),
                   _X_NAME, _ROW_SURNAME, max_x=_VALUE_MAX_X)
        self._text(page, font, _title(passport.name or ""),
                   _X_NAME, _ROW_NAME, max_x=_VALUE_MAX_X)
        self._text(page, font, _title(passport.patronymic or ""),
                   _X_NAME, _ROW_PATRONYMIC, max_x=_VALUE_MAX_X)
        if passport.birth_date:
            self._text(page, font, _date_dmy(passport.birth_date),
                       _X_WIDE, _ROW_DOB)
        self._text(page, font, _title(passport.nationality or ""),
                   _X_WIDE, _ROW_CITIZEN, max_x=_VALUE_MAX_X)

        # the «/» between them is already on the blank — writing another would
        # print a double slash
        passport_no = f"{passport.series or ''}{passport.number or ''}".strip()
        self._text(page, font, passport_no, _X_FULL, _ROW_DOC,
                   size=_DOC_SIZE, max_x=_DOC_PASSPORT_MAX_X)
        self._text(page, font, inn, _DOC_INN_X, _ROW_DOC,
                   size=_DOC_SIZE, max_x=_VALUE_MAX_X)

        if REGIONS[region]["dolzhnost"] and dolzhnost:
            self._text(page, font, dolzhnost, _X_FULL, _ROW_DOLZH,
                       max_x=_VALUE_MAX_X)

    def _fill_back(self, page, font, serif, *, firm: str, issue_date: date,
                   pr: str, territory: str) -> None:
        self._rewrite_territory(page, font, territory)
        self._fill_firm(page, font, firm)
        self._back_text(page, font, _date_dmy(issue_date), *_DATE_ORIGIN,
                        size=_DATE_SIZE, fontname="bjb")
        self._back_number(page, serif, pr, *_PR_ORIGIN)

    def _fill_firm(self, page, font, firm: str) -> None:
        """«Кем выдано …» — the issuing company, wrapped onto a second line.

        The back reads upside down, so line two is drawn *above* line one.
        """
        if not firm:
            return
        lines, current = [], ""
        for word in firm.split():
            right = _FIRM_FIRST_RIGHT if not lines else _BACK_RIGHT
            trial = f"{current} {word}".strip()
            if current and font.text_length(
                    trial, fontsize=_SIZE) > right - _FIRM_LEFT:
                lines.append(current)
                current = word
            else:
                current = trial
        if current:
            lines.append(current)
        for i, line in enumerate(lines[:3]):
            self._back_text(page, font, line,
                            _FIRM_FIRST_RIGHT if i == 0 else _BACK_RIGHT,
                            _FIRM_BASE - i * _FIRM_LINE, size=_SIZE)

    def _rewrite_territory(self, page, font, territory: str) -> None:
        """Clear the region printed on the blank and write the right one.

        The line is part of the artwork, so it is covered by cloning the
        badge's own guilloche from a blank strip of the same pattern — a flat
        rectangle would read as a patch.
        """
        self._clone_over(page, _TERRITORY_BOX, _TERRITORY_DONOR_Y)
        self._back_text(page, font, territory, *_TERRITORY_ORIGIN, size=_SIZE)

    @staticmethod
    def _clone_over(page, box: tuple[float, float, float, float],
                    donor_y: float) -> None:
        """Hide ``box`` under a copy of the badge's own background pattern,
        lifted from ``donor_y`` — a blank strip of the same artwork."""
        try:
            import io

            import numpy as np
            from PIL import Image
        except ImportError:  # pragma: no cover - both ship with the app
            page.draw_rect(fitz.Rect(*box), color=None, fill=(1, 1, 1))
            return

        x0, y0, x1, y1 = box
        height = y1 - y0
        # a strip of the same artwork known to carry no text
        donor = fitz.Rect(x0, donor_y, x1, donor_y + height)
        try:
            pm = page.get_pixmap(dpi=400, clip=donor)
            arr = np.frombuffer(pm.samples, dtype=np.uint8).reshape(
                pm.height, pm.width, pm.n)[:, :, :3]
            buf = io.BytesIO()
            Image.fromarray(arr).save(buf, format="PNG")
            page.insert_image(fitz.Rect(*box), stream=buf.getvalue(), overlay=True)
        except Exception:  # noqa: BLE001 - never let cosmetics break a badge
            page.draw_rect(fitz.Rect(*box), color=None, fill=(1, 1, 1))

    @staticmethod
    def _text(page, font, text: str, x: float, baseline: float, *,
              size: float = _SIZE, max_x: float | None = None) -> None:
        if not text:
            return
        if max_x is not None:
            avail = max_x - x
            while size > 5 and font.text_length(text, fontsize=size) > avail:
                size -= 0.25
        page.insert_text((x, baseline), text, fontname="bj", fontsize=size)

    @staticmethod
    def _back_text(page, font, text: str, right_x: float, top_y: float, *,
                   size: float, fontname: str = "bj") -> None:
        """Draw ``text`` rotated 180° (the badge back), with ``right_x`` its
        right edge — the point where reading begins on the flipped card."""
        if not text:
            return
        # never let a value run off the card's other edge
        while size > 5 and font.text_length(text, fontsize=size) > right_x - 15:
            size -= 0.25
        page.insert_text((right_x, top_y), text, fontname=fontname,
                         fontsize=size, rotate=180)

    @staticmethod
    def _back_number(page, serif, number: str, right_x: float,
                     top_y: float) -> None:
        """The «ПР …» serial — Times, like its own label, and letterspaced.

        Rotated text runs right to left in page coordinates, so the digits are
        laid down from ``right_x`` backwards, one at a time, to reproduce the
        tracking the office's badge uses.
        """
        if not number:
            return
        x = right_x
        for char in number:
            page.insert_text((x, top_y), char, fontname="bjs",
                             fontsize=_PR_SIZE, rotate=180)
            x -= serif.text_length(char, fontsize=_PR_SIZE) + _PR_TRACKING

    @staticmethod
    def _place_photo(page, photo_path: Path | None) -> None:
        """Fill the badge's photo window edge to edge.

        The upload is first cropped head-and-shoulders onto a white background
        at the window's own aspect, so nothing is stretched; if that pipeline
        cannot read the file the original is fitted instead.
        """
        if photo_path is None or not Path(photo_path).exists():
            return
        stream = None
        try:
            from src.services.photo_service import prepare_portrait

            stream = prepare_portrait(Path(photo_path).read_bytes(),
                                      aspect=PHOTO_ASPECT)
        except Exception as exc:  # noqa: BLE001 - fall back to the raw photo
            log.warning("Badge photo not fitted (%s) — using it as-is", exc)
        try:
            if stream:
                page.insert_image(fitz.Rect(*PHOTO_BOX), stream=stream,
                                  keep_proportion=False, overlay=True)
            else:
                page.insert_image(fitz.Rect(*PHOTO_BOX), filename=str(photo_path),
                                  keep_proportion=False, overlay=True)
        except (RuntimeError, ValueError):
            log.warning("Badge photo could not be placed: %s", photo_path)

    @staticmethod
    def _output_path(passport: Passport, region: str, base: Path | None) -> Path:
        folder = base if base is not None else paths.output_dir() / "beydjik"
        folder.mkdir(parents=True, exist_ok=True)
        stem = "".join(c if c.isalnum() or c in " _-" else "_"
                       for c in f"{passport.surname}_{region}".upper()).strip()
        candidate = folder / f"{stem or 'BEYDJIK'}.pdf"
        i = 1
        while candidate.exists():
            candidate = folder / f"{stem}_{i:03d}.pdf"
            i += 1
        return candidate
