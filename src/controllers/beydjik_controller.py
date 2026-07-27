"""Coordinates the БЕЙДЖИК use-case: a passport photo → the worker's badge."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from src.common.logging import get_logger
from src.ocr.service import OcrService
from src.services.beydjik_service import BeydjikResult, BeydjikService

log = get_logger(__name__)


class BeydjikController:
    def __init__(self, ocr: OcrService, beydjik: BeydjikService) -> None:
        self._ocr = ocr
        self._beydjik = beydjik

    def ai_available(self) -> bool:
        return self._ocr.available()

    def regions(self) -> list[tuple[str, str]]:
        from src.services.beydjik_service import REGIONS

        return [(code, spec["label"]) for code, spec in REGIONS.items()]

    def next_pr(self) -> str:
        return self._beydjik.peek_pr()

    def set_next_pr(self, value: str | int) -> None:
        self._beydjik.set_pr(value)

    @staticmethod
    def territory(region: str) -> str:
        """The wording this region's badges normally carry, as a starting point."""
        from src.services.beydjik_service import REGIONS

        return str(REGIONS.get(region, {}).get("territory", ""))

    def firm(self) -> str:
        return self._beydjik.firm()

    def generate_from_image(
        self,
        passport_image: bytes,
        *,
        region: str,
        personal_number: str,
        inn: str,
        issue_date: date,
        firm: str | None = None,
        dolzhnost: str = "",
        territory: str = "",
        photo_path: Path | None = None,
    ) -> BeydjikResult:
        """ФИО, date of birth, citizenship and the passport number come off the
        passport; everything else the operator typed in."""
        passport = self._ocr.read_passport(passport_image)
        return self._beydjik.generate(
            passport, region=region, personal_number=personal_number, inn=inn,
            issue_date=issue_date, firm=firm, dolzhnost=dolzhnost,
            territory=territory, photo_path=photo_path)

    @staticmethod
    def read_image(path: Path) -> bytes:
        return path.read_bytes()
