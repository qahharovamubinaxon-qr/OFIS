"""АЛЬЯНСКОТ 2400 — the firm's three blanks, and three PDFs out of them.

The office uploads three empty blanks by fixed name — the two-page
удостоверение (``udo``) and two справки (``spr1``, ``spr2``) — arranges each
one (:mod:`src.pdf.alliance_renderer`), and one press prints the worker onto
all three. Each comes out as its own PDF named after the worker, with the
blank's kind on the end so the three never collide:

    АШУРОВ_ДИЛМУРОД_УДОСТОВЕРЕНИЕ.pdf
    АШУРОВ_ДИЛМУРОД_СПРАВКА_1.pdf
    АШУРОВ_ДИЛМУРОД_СПРАВКА_2.pdf

The uploaded blanks live in AppData and are never deleted by an EXE rebuild.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import fitz

from src.common.errors import ValidationError
from src.common.logging import get_logger
from src.config import paths
from src.pdf.alliance_renderer import AllianceData, output_name, render
from src.services import blank_layout

log = get_logger(__name__)

SECTION = "alliance"
#: The three fixed blanks, in printing order.
SLOTS: tuple[str, ...] = ("udo", "spr1", "spr2")
#: What each blank's kind is called on the end of the saved file name.
SLOT_LABELS: dict[str, str] = {
    "udo": "УДОСТОВЕРЕНИЕ", "spr1": "СПРАВКА_1", "spr2": "СПРАВКА_2"}
BLANK_SUFFIXES = {".pdf"}


@dataclass(frozen=True)
class AllianceResult:
    slot: str
    pdf: bytes
    saved: Path
    surname: str


def templates_dir() -> Path:
    folder = paths.user_templates_dir() / "alliance"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _check_slot(slot: str) -> None:
    if slot not in SLOTS:
        raise ValidationError(f"Номаълум бланка: {slot}")


class AllianceService:
    def __init__(self, settings=None) -> None:
        self._settings = settings

    # ------------------------------------------------------------ blanks
    def blank(self, slot: str) -> Path | None:
        _check_slot(slot)
        found = templates_dir() / f"{slot}.pdf"
        return found if found.exists() else None

    def set_blank(self, slot: str, source: Path) -> Path:
        _check_slot(slot)
        source = Path(source)
        if source.suffix.lower() not in BLANK_SUFFIXES or not source.exists():
            raise ValidationError("Бланка PDF бўлиши керак")
        dest = templates_dir() / f"{slot}.pdf"
        shutil.copyfile(source, dest)
        log.info("АЛЬЯНСКОТ бланкаси юкланди: %s", slot)
        return dest

    def pages(self, slot: str) -> int:
        found = self.blank(slot)
        if found is None:
            return 0
        with fitz.open(str(found)) as doc:
            return doc.page_count

    # ------------------------------------------------------------ layout
    def layout(self, slot: str) -> dict:
        found = self.blank(slot)
        return blank_layout.load(SECTION, found) if found else {}

    def save_layout(self, slot: str, layout: dict) -> None:
        found = self.blank(slot)
        if found is not None:
            blank_layout.save(SECTION, found, layout)

    # ---------------------------------------------------------- printing
    def generate(self, data: AllianceData,
                 out_dir: Path | None = None) -> list[AllianceResult]:
        if not (data.surname or "").strip():
            raise ValidationError("Фамилия керак — ҳужжатларни ўқитинг")
        for slot in SLOTS:
            if self.blank(slot) is None:
                raise ValidationError(
                    f"«{SLOT_LABELS[slot]}» бланкаси юкланмаган — учаласини "
                    "ҳам юкланг.")

        folder = Path(out_dir) if out_dir is not None \
            else paths.output_dir() / "alliance"
        folder.mkdir(parents=True, exist_ok=True)
        base = output_name(data)[:-4]           # strip «.pdf»

        results: list[AllianceResult] = []
        for slot in SLOTS:
            blank = self.blank(slot)
            assert blank is not None            # guarded above
            pdf = render(data, blank, self.layout(slot))
            target = _unique(folder / f"{base}_{SLOT_LABELS[slot]}.pdf")
            target.write_bytes(pdf)
            log.info("АЛЬЯНСКОТ: %s — %s", slot, target.name)
            results.append(AllianceResult(
                slot=slot, pdf=pdf, saved=target,
                surname=(data.surname or "").strip()))
        return results


def _unique(target: Path) -> Path:
    counter = 2
    stem = target.stem
    while target.exists():
        target = target.with_name(f"{stem} ({counter}){target.suffix}")
        counter += 1
    return target
