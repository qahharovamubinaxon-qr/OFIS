"""ПАТЕНТ — the same card as БЕЙДЖИК, on the blanks the office keeps for it.

The office asked for this section to be one-to-one with БЕЙДЖИК: the same
fields, the same numbering, the same QR, the same firm history, the same two
regions (77 Москва and 50 Московская область). Only two things differ, and both
are about what the card is *for*:

* **the blank.** A badge is printed, folded and laminated, so its blank is one
  small page with the back upside down under the front. A patent card is used
  on a screen, so its blanks are two full pages the right way up — and the
  finished card is one PDF, front on page 1, back on page 2, saved onto the
  desktop under the worker's surname.
* **the photograph** is laid on at nine parts in ten rather than flat, as the
  office asked.

So nothing here re-implements the badge. :class:`PatentService` *is* a
:class:`~src.services.beydjik_service.BeydjikService`; every value is drawn by
the badge's own code onto a badge-sized overlay, and that overlay is then
stamped onto the patent blanks. Whatever the office changes about the badge —
a field, a size, the QR record — this section follows it, which is exactly what
«бирга бир» has to mean if it is to stay true a year from now.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import fitz

from src.common.errors import OfisError
from src.common.logging import get_logger
from src.config import paths
from src.domain.documents import Passport
from src.pdf.engine import _font_file
from src.services import beydjik_service as badge

log = get_logger(__name__)

#: The card's place on the blank pages — the same on all four the office gave.
CARD = (367.20, 286.56, 1223.28, 889.92)
#: The badge page, and the line the front and the back meet on.
BADGE_PAGE = (262.80, 370.08)
BADGE_SPLIT = 185.04

#: The blanks' own windows, measured on them rather than scaled from the badge:
#: the office redrew both a little when it made these pages.
PHOTO_BOX = (451.08, 461.52, 728.64, 830.88)
QR_BOX = (942.84, 563.40, 1185.84, 807.48)

#: «100 эмас 90» — the card shows through the picture a tenth of the way.
PHOTO_OPACITY = 0.90

SIDES = ("front", "back")


@dataclass(frozen=True)
class PatentResult:
    pdf_path: Path
    pr_number: str
    surname: str
    region: str


def bundled_blank(region: str, side: str) -> Path:
    return paths.templates_dir() / "patent" / region / f"{side}.pdf"


def user_blank_path(region: str, side: str) -> Path:
    """Where the office drops its own design. In AppData, so an update never
    overwrites it."""
    return paths.user_templates_dir() / "patent" / region / f"{side}.pdf"


def blank_source(region: str, side: str) -> tuple[Path, bool]:
    """(the file to print on, True when it is the office's own upload)."""
    own = user_blank_path(region, side)
    if own.exists():
        return own, True
    return bundled_blank(region, side), False


def import_blank(region: str, side: str, source: Path) -> Path:
    """Adopt ``source`` as this region's front or back, after a size check."""
    if region not in badge.REGIONS or side not in SIDES:
        raise OfisError("Регион ёки томон нотўғри.")
    try:
        doc = fitz.open(source)
    except Exception as exc:                      # noqa: BLE001
        raise OfisError("PDF ochilmadi — boshqa fayl tanlang.") from exc
    try:
        if len(doc) < 1:
            raise OfisError("PDF bo'sh.")
        rect = doc[0].rect
        if not (rect.width > rect.height):
            raise OfisError(
                "Бланка кўндаланг (landscape) бўлиши керак — картанинг бир "
                "томони.")
    finally:
        doc.close()
    dest = user_blank_path(region, side)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)
    log.info("Патент бланкаси юкланди: %s / %s", region, side)
    return dest


class PatentService(badge.BeydjikService):
    """The badge, printed onto the patent blanks and saved as one PDF."""

    # the patent blanks print no region under «Территория действия патента»,
    # so unlike the badge there is nothing to hide before writing it
    def _rewrite_territory(self, page, font, territory: str) -> None:
        badge.BeydjikService._back_text(page, font, territory,
                                        *badge._TERRITORY_ORIGIN,
                                        size=badge._SIZE)

    # ------------------------------------------------------------------
    def generate(                                  # type: ignore[override]
        self,
        passport: Passport,
        *,
        region: str,
        personal_number: str,
        inn: str,
        issue_date: date,
        firm: str | None = None,
        dolzhnost: str = "",
        territory: str = "",
        photo_path: Path | None = None,
        output_dir: Path | None = None,
    ) -> PatentResult:
        if region not in badge.REGIONS:
            raise OfisError("Регион танланг: 77 (Москва) ёки 50 (область).")
        blanks = {}
        for side in SIDES:
            path, _own = blank_source(region, side)
            if not path.exists():
                raise OfisError(
                    f"Патент бланкаси топилмади ({side}). Бўлимдаги «Шаблон "
                    "юклаш» орқали олд ва орқа PDF ни юкланг.")
            blanks[side] = path
        if not personal_number.strip():
            raise OfisError("Шахсий номерни киритинг.")

        pr = self._take_pr()
        firm = (firm or self.firm()).strip()
        self.remember_firm(firm)
        territory = territory.strip() or badge.REGIONS[region]["territory"]

        overlay = self._values_overlay(
            passport, region=region, personal_number=personal_number.strip(),
            inn=inn.strip(), issue_date=issue_date, firm=firm, pr=pr,
            dolzhnost=dolzhnost.strip(), territory=territory)
        try:
            out = fitz.open()
            out.insert_pdf(fitz.open(str(blanks["front"])))
            out.insert_pdf(fitz.open(str(blanks["back"])))
            card = fitz.Rect(*CARD)
            out[0].show_pdf_page(
                card, overlay, 0,
                clip=fitz.Rect(0, 0, BADGE_PAGE[0], BADGE_SPLIT))
            out[1].show_pdf_page(
                card, overlay, 0, rotate=180,
                clip=fitz.Rect(0, BADGE_SPLIT, BADGE_PAGE[0], BADGE_PAGE[1]))
            self._place_photo_softly(out[0], photo_path)
            self._place_qr_here(out[1], self.qr_text(
                passport, region=region, personal_number=personal_number.strip(),
                inn=inn.strip(), issue_date=issue_date, firm=firm, pr=pr,
                dolzhnost=dolzhnost.strip(), territory=territory))
            target = self._output_path(passport, output_dir)
            out.save(str(target), garbage=4, deflate=True)
            out.close()
        finally:
            overlay.close()

        log.info("ПАТЕНТ %s %s for %s", region, pr, passport.surname)
        return PatentResult(pdf_path=target, pr_number=pr,
                            surname=passport.surname, region=region)

    # ------------------------------------------------------------------
    def _values_overlay(self, passport: Passport, *, region: str,
                        personal_number: str, inn: str, issue_date: date,
                        firm: str, pr: str, dolzhnost: str,
                        territory: str) -> fitz.Document:
        """The badge's own values, drawn on nothing but themselves.

        A PDF page paints no background of its own, so stamping this over the
        patent blank lays down the text and nothing else.
        """
        doc = fitz.open()
        page = doc.new_page(width=BADGE_PAGE[0], height=BADGE_PAGE[1])
        page.insert_font(fontname="bj", fontfile=str(_font_file(badge._FONT)))
        page.insert_font(fontname="bjb",
                         fontfile=str(_font_file(badge._FONT_BOLD)))
        page.insert_font(fontname="bjs", fontfile=str(_font_file(badge._SERIF)))
        font = fitz.Font(fontfile=str(_font_file(badge._FONT)))
        serif = fitz.Font(fontfile=str(_font_file(badge._SERIF)))
        self._fill_front(page, font, passport, region=region,
                         personal_number=personal_number, inn=inn,
                         dolzhnost=dolzhnost)
        self._fill_back(page, font, serif, firm=firm, issue_date=issue_date,
                        pr=pr, territory=territory)
        return doc

    @staticmethod
    def _place_qr_here(page, text: str) -> None:
        """The badge's own QR record, in this blank's own window.

        A card is never lost to the code: if it cannot be built, the blank's
        printed one simply stays.
        """
        if not text.strip():
            return
        from src.pdf.qr import draw_qr, modules

        try:
            side = modules(text).shape[0]
            per_module_mm = (QR_BOX[2] - QR_BOX[0]) / 72 * 25.4 / side
            if per_module_mm < badge._QR_MIN_MODULE_MM:
                log.warning(
                    "ПАТЕНТ QR is %d modules wide — %.2f mm each, may not scan",
                    side, per_module_mm)
            draw_qr(page, text, QR_BOX)
        except Exception as exc:                  # noqa: BLE001
            log.warning("ПАТЕНТ QR not drawn (%s) — keeping the blank's own", exc)

    @staticmethod
    def _place_photo_softly(page, photo_path: Path | None) -> None:
        """The worker's photograph, filling its window at nine parts in ten."""
        if photo_path is None or not Path(photo_path).exists():
            return
        raw = Path(photo_path).read_bytes()
        aspect = (PHOTO_BOX[2] - PHOTO_BOX[0]) / (PHOTO_BOX[3] - PHOTO_BOX[1])
        stream = None
        try:
            from src.services.photo_service import prepare_portrait

            stream = prepare_portrait(raw, aspect=aspect, height=900)
        except Exception as exc:                  # noqa: BLE001
            log.warning("Патент: расм мослаштирилмади (%s)", exc)
        try:
            from src.pdf.razreshenie_renderer import _cover_crop, _soften

            if stream is None:
                stream = _cover_crop(raw, aspect)
            stream = _soften(stream, PHOTO_OPACITY)
        except Exception as exc:                  # noqa: BLE001
            log.warning("Патент: расм тайёрланмади (%s) — ўз ҳолича", exc)
            stream = stream or raw
        try:
            page.insert_image(fitz.Rect(*PHOTO_BOX), stream=stream,
                              keep_proportion=False, overlay=True)
        except (RuntimeError, ValueError) as exc:
            log.warning("Патент: расм жойлашмади: %s", exc)

    @staticmethod
    def _output_path(passport: Passport, output_dir: Path | None) -> Path:
        """Onto the desktop, under the worker's surname, never over another."""
        folder = Path(output_dir) if output_dir else paths.desktop_dir()
        folder.mkdir(parents=True, exist_ok=True)
        stem = "".join(c for c in (passport.surname or "").strip()
                       if c.isalnum() or c in " _-").strip() or "Патент"
        target = folder / f"{stem}.pdf"
        counter = 2
        while target.exists():
            target = folder / f"{stem} ({counter}).pdf"
            counter += 1
        return target
