"""Bulk mode: one ZIP of per-worker folders → one PDF each, saved to Desktop.

The operator makes a folder per worker containing that worker's passport +
patent photos, zips them all together, and uploads the ZIP. This service
unpacks it, classifies each folder's images (passport / patent front / patent
back — by filename hint, then by order), reads them with the OCR service and
generates a PDF per worker into a single dated folder on the Desktop.
"""

from __future__ import annotations

import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from src.common.logging import get_logger
from src.config import paths
from src.domain.company import Company
from src.domain.employee import Employee
from src.ocr.service import OcrService
from src.services.generation_service import GenerationService

log = get_logger(__name__)

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}

_PASSPORT_KW = ("pasport", "passport", "паспорт", "pass", "psprt")
_BACK_KW = ("orqa", "orka", "orq", "back", "obr", "oborot", "оборот", "zad", "задн", "орка")
_PATENT_KW = ("patent", "патент", "pat", "old", "олд", "front")


@dataclass
class BatchItem:
    folder: str
    ok: bool
    surname: str = ""
    pdf: str = ""
    error: str = ""


@dataclass
class BatchSummary:
    output_dir: Path
    items: list[BatchItem] = field(default_factory=list)

    @property
    def ok_count(self) -> int:
        return sum(1 for i in self.items if i.ok)

    @property
    def total(self) -> int:
        return len(self.items)


def classify_images(paths_in: list[Path]) -> dict[str, Path | None]:
    """Assign a folder's images to passport / patent / patent_back slots.

    Filename hints win; leftovers fill empty slots in name order (so an unnamed
    pair becomes passport + patent, a trio adds the back).
    """
    slots: dict[str, Path | None] = {"passport": None, "patent": None, "patent_back": None}
    rest: list[Path] = []
    for p in sorted(paths_in, key=lambda x: x.name.lower()):
        n = p.stem.lower()
        if slots["passport"] is None and any(k in n for k in _PASSPORT_KW):
            slots["passport"] = p
        elif slots["patent_back"] is None and any(k in n for k in _BACK_KW):
            slots["patent_back"] = p
        elif slots["patent"] is None and any(k in n for k in _PATENT_KW):
            slots["patent"] = p
        else:
            rest.append(p)
    for slot in ("passport", "patent", "patent_back"):
        if slots[slot] is None and rest:
            slots[slot] = rest.pop(0)
    return slots


class BatchService:
    def __init__(self, ocr: OcrService, generation: GenerationService) -> None:
        self._ocr = ocr
        self._generation = generation

    def process_zip(
        self,
        zip_path: Path,
        company: Company,
        *,
        form_date: date,
        profession: str | None,
        on_progress=None,
    ) -> BatchSummary:
        out_dir = self._make_output_dir(company)
        summary = BatchSummary(output_dir=out_dir)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(root)

            folders = self._worker_folders(root)
            for idx, folder in enumerate(folders, start=1):
                name = folder.name
                if on_progress:
                    on_progress(idx, len(folders), name)
                try:
                    item = self._process_one(folder, company, out_dir, form_date, profession)
                except Exception as exc:  # noqa: BLE001 - one bad folder must not stop the batch
                    log.warning("Batch folder %s failed: %s", name, exc)
                    item = BatchItem(folder=name, ok=False, error=str(exc)[:160])
                summary.items.append(item)

        log.info("Batch done: %d/%d → %s", summary.ok_count, summary.total, out_dir)
        return summary

    # -- internals ---------------------------------------------------------
    def _process_one(
        self, folder: Path, company: Company, out_dir: Path, form_date: date, profession: str | None
    ) -> BatchItem:
        images = [p for p in folder.iterdir() if p.suffix.lower() in _IMAGE_EXTS]
        if not images:
            return BatchItem(folder=folder.name, ok=False, error="rasm topilmadi")
        slots = classify_images(images)
        if slots["passport"] is None:
            return BatchItem(folder=folder.name, ok=False, error="pasport rasmi topilmadi")

        passport = self._ocr.read_passport(slots["passport"].read_bytes())
        patent = None
        if slots["patent"] is not None:
            back = slots["patent_back"].read_bytes() if slots["patent_back"] else None
            patent = self._ocr.read_patent(slots["patent"].read_bytes(), back)

        employee = Employee(
            company_id=company.id, passport=passport, patent=patent,
            profession=profession or (patent.profession if patent else "ПОДСОБНЫЙ РАБОЧИЙ"),
            contract_date=form_date,
        )
        result = self._generation.generate(
            employee, company, form_date=form_date, profession=profession, output_dir=out_dir
        )
        return BatchItem(folder=folder.name, ok=True, surname=result.surname, pdf=result.pdf_path.name)

    @staticmethod
    def _worker_folders(root: Path) -> list[Path]:
        """Each immediate subfolder that contains images is one worker. If the
        ZIP has images at the top level (no subfolders), treat the root as one
        worker."""
        subdirs = [
            d for d in sorted(root.rglob("*"))
            if d.is_dir() and any(p.suffix.lower() in _IMAGE_EXTS for p in d.iterdir())
        ]
        if subdirs:
            return subdirs
        if any(p.suffix.lower() in _IMAGE_EXTS for p in root.iterdir()):
            return [root]
        return []

    @staticmethod
    def _make_output_dir(company: Company) -> Path:
        safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in company.name).strip()
        base = paths.desktop_dir() / f"OFIS — {safe}"
        out = base
        i = 1
        while out.exists():
            out = Path(f"{base} ({i})")
            i += 1
        out.mkdir(parents=True, exist_ok=True)
        return out
