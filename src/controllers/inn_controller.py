"""Coordinates the ИНН use-case: a passport or patent photo → the record sheet."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from src.common.logging import get_logger
from src.ocr.service import OcrService
from src.services.inn_service import InnResult, InnService

log = get_logger(__name__)


class InnController:
    def __init__(self, ocr: OcrService, inn: InnService) -> None:
        self._ocr = ocr
        self._inn = inn

    def ai_available(self) -> bool:
        return self._ocr.available()

    def read_inn(self, image: bytes) -> str:
        """The worker's ИНН as the патент prints it, or "" if it is not on it.

        Read as soon as the photograph is dropped, so the box is already filled
        by the time the operator looks at it. Whatever comes back is only a
        suggestion — the box stays editable, and an empty one simply means the
        number is typed by hand, as it always was.
        """
        return self._ocr.read_inn(image)

    def read_all(self, image: bytes):
        """The worker AND the ИНН, from one photograph, for the operator to
        check before printing.

        The sheet prints the worker's ФИО, sex, birth date and citizenship,
        and until now they were read INSIDE the print step — so a misread name
        went onto a filed sheet unseen. Now the passport is read here, shown in
        editable boxes, and the sheet is printed from what is in them. Returns
        ``(passport, inn_digits)``.
        """
        return self._ocr.read_passport(image), self._ocr.read_inn(image)

    def generate(self, passport, *, inn: str, form_date: date) -> InnResult:
        """The sheet, from what is IN THE BOXES — not from what was read."""
        return self._inn.generate(passport, inn=inn, form_date=form_date)

    def generate_from_image(
        self,
        image: bytes,
        *,
        inn: str,
        form_date: date,
    ) -> InnResult:
        """Read and print in one go — kept for the bot, which has no screen.
        The upload may be a passport or a patent — both print the worker's
        ФИО, date of birth and citizenship, which is all the sheet needs."""
        return self.generate(self._ocr.read_passport(image),
                             inn=inn, form_date=form_date)

    @staticmethod
    def read_image(path: Path) -> bytes:
        return path.read_bytes()
