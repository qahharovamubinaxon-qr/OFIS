"""Coordinates the Трудовой-Уведомления use-case for the UI."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from uuid import UUID

from src.common.errors import ValidationError
from src.common.logging import get_logger
from src.domain.firm_details import FirmDetails
from src.domain.trud_firm import TrudFirm
from src.ocr.service import OcrService
from src.services.trud_service import TrudFirmService, TrudResult, TrudService

log = get_logger(__name__)


class TrudController:
    def __init__(self, firms: TrudFirmService, ocr: OcrService, trud: TrudService) -> None:
        self._firms = firms
        self._ocr = ocr
        self._trud = trud

    def firms(self) -> list[TrudFirm]:
        return self._firms.list()

    def add_firm(self, name: str, code: str, trud_tpl: Path, uved_tpl: Path,
                 hod_tpl: Path | None = None) -> TrudFirm:
        return self._firms.create(name, code, trud_tpl, uved_tpl, hod_tpl)

    def add_firm_manual(self, details: FirmDetails, code: str) -> TrudFirm:
        """Register a firm from typed requisites — the program writes its pair."""
        return self._firms.create_manual(details, code)

    def study_uved(self, firm: TrudFirm):
        """Read the firm's blank and learn where each worker value goes."""
        return self._firms.study_uved(firm, self._ocr.ai)

    def study_trud(self, firm: TrudFirm):
        """…and the same for a PDF трудовой договор."""
        return self._firms.study_trud(firm, self._ocr.ai)

    def study_templates(self, firm: TrudFirm) -> dict[str, object]:
        """Study whatever of this firm's two templates can be studied.

        A .docx contract needs none — it is filled by text — so its absence
        from the result is not a failure.
        """
        out: dict[str, object] = {}
        for name, study in (("uved", self.study_uved), ("trud", self.study_trud)):
            try:
                out[name] = study(firm)
            except ValidationError:
                out[name] = None          # a .docx template: nothing to study
        return out

    def archive_firm(self, firm_id: UUID) -> None:
        self._firms.archive(firm_id)

    def ai_available(self) -> bool:
        return self._ocr.available()

    def read_documents(
        self,
        passport_image: bytes,
        patent_image: bytes | None,
        patent_back_image: bytes | None = None,
    ):
        """The worker and the patent, for the operator to check before the
        трудовой and the уведомление are printed. Returns ``(passport, patent)``.

        The договор prints the worker's whole identity — name, birth, passport —
        and it used to be read inside the print step, so a misread went onto a
        filed contract unseen. Now it is read here, shown, and printed from the
        boxes."""
        return self._ocr.read_documents(
            passport_image, patent_image, patent_back_image
        )

    def generate(
        self,
        firm: TrudFirm,
        passport,
        patent,
        *,
        form_date: date,
        profession: str | None,
    ) -> TrudResult:
        """The pair, from what is IN THE BOXES — not from what was read.
        The patent is kept as read (its issue date sets the contract's end)."""
        return self._trud.generate(
            passport, patent, firm, form_date=form_date, profession=profession
        )

    def generate_from_images(
        self,
        firm: TrudFirm,
        passport_image: bytes,
        patent_image: bytes | None,
        patent_back_image: bytes | None = None,
        *,
        form_date: date,
        profession: str | None,
    ) -> TrudResult:
        """Read and print in one go — kept for the bot, which has no screen."""
        passport, patent = self.read_documents(
            passport_image, patent_image, patent_back_image
        )
        return self.generate(
            firm, passport, patent, form_date=form_date, profession=profession
        )

    @staticmethod
    def read_image(path: Path) -> bytes:
        return path.read_bytes()
