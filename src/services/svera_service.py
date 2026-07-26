"""Generate the СФЕРА 2-page PDF (Удостоверение + Протокол) for one student.

Reads names from a passport (OCR), places the student photo, fills the chosen
profession + date, and advances the three counters (удостоверение №, ПО number
shared by both pages, 13-digit protocol reg number). Saved by surname.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.common.logging import get_logger
from src.config import paths
from src.config.settings_service import SettingsService
from src.domain.documents import Passport
from src.domain.profession import Profession
from src.pdf.engine import fill
from src.pdf.mapping import FieldMapping
from src.services.svera_values import build_svera_values

log = get_logger(__name__)

_MAPPING_PATH = paths.templates_dir() / "svera" / "mapping.v1.json"
_TEMPLATE_PATH = paths.templates_dir() / "svera" / "template.pdf"
# The centre's round stamp (transparent PNG) — printed over the photo on the
# left card and over the qualification block on the right one.
_STAMP_PATH = paths.templates_dir() / "svera" / "stamp.png"

_UDO_KEY, _UDO_START = "svera.udo_counter", 100
_PO_KEY, _PO_START = "svera.po_counter", 1548
_REG13_KEY, _REG13_START = "svera.reg13_counter", 1800359856150


@dataclass(frozen=True)
class SveraResult:
    pdf_path: Path
    udo_number: int
    po_number: int


class SveraService:
    def __init__(self, settings: SettingsService) -> None:
        self._settings = settings

    def _peek(self, key: str, default: int) -> int:
        return int(self._settings.get(key, default))  # type: ignore[arg-type]

    def next_po_number(self) -> int:
        return self._peek(_PO_KEY, _PO_START)

    def generate(
        self,
        passport: Passport,
        profession: Profession,
        *,
        issue_date: date,
        photo_path: Path | None,
        output_dir: Path | None = None,
    ) -> SveraResult:
        udo = self._peek(_UDO_KEY, _UDO_START)
        po = self._peek(_PO_KEY, _PO_START)
        reg13 = self._peek(_REG13_KEY, _REG13_START)

        stamp = _STAMP_PATH if _STAMP_PATH.exists() else None
        values = build_svera_values(
            passport.surname, passport.name, passport.patronymic, profession,
            issue_date=issue_date,
            photo_path=str(photo_path) if photo_path else None,
            po_number=po, udo_number=udo, reg13=reg13,
            stamp_path=str(stamp) if stamp else None,
        )
        mapping = FieldMapping.load(_MAPPING_PATH)
        out_path = self._unique_output_path(passport, output_dir)
        fill(_TEMPLATE_PATH, mapping, values, out_path)
        # Page 2 (the certificate) is typeset in full — its blank is empty, so
        # the labels, rules and stamps are drawn rather than mapped.
        self._draw_certificate(out_path, values, photo_path, stamp)

        self._settings.set(_UDO_KEY, udo + 1)
        self._settings.set(_PO_KEY, po + 1)
        self._settings.set(_REG13_KEY, reg13 + 1)
        log.info("Generated СФЕРА %s (ПО%s) for %s", out_path.name, po, passport.surname)
        return SveraResult(pdf_path=out_path, udo_number=udo, po_number=po)

    @staticmethod
    def _draw_certificate(pdf: Path, values: dict, photo: Path | None,
                          stamp: Path | None) -> None:
        import fitz

        from src.pdf.svera_udo import UdoData, render_udostoverenie

        doc = fitz.open(str(pdf))
        try:
            render_udostoverenie(doc[1], UdoData(
                number=str(values["svera.udo_number"]),
                fio_dative=str(values["svera.fio_udo_left"]).split("\n"),
                profession=str(values["svera.prof_udo_left"]),
                qualification=str(values["svera.qual_udo_right"]),
                issue_date=str(values["svera.date_udo"]),
                basis=str(values["svera.osnovanie"]),
                photo_path=photo,
                stamp_path=stamp,
            ))
            doc.saveIncr()
        finally:
            doc.close()

    def _unique_output_path(self, passport: Passport, base: Path | None) -> Path:
        folder = base if base is not None else paths.output_dir() / "svera"
        folder.mkdir(parents=True, exist_ok=True)
        stem = _safe(f"{passport.surname}_{passport.name}".upper()) or "SVERA"
        candidate = folder / f"{stem}.pdf"
        i = 1
        while candidate.exists():
            candidate = folder / f"{stem}_{i:03d}.pdf"
            i += 1
        return candidate


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in " _-" else "_" for c in name).strip() or "svera"
