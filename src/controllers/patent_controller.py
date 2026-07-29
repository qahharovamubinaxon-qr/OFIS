"""ПАТЕНТ use-case — the badge's own controller, pointed at the patent blanks.

It *is* :class:`~src.controllers.beydjik_controller.BeydjikController`: the
section was asked to be one-to-one with БЕЙДЖИК, and the only difference the
screen has to know about is that a patent blank comes in two halves, so the
front and the back are uploaded separately.
"""

from __future__ import annotations

from pathlib import Path

from src.common.logging import get_logger
from src.controllers.beydjik_controller import BeydjikController
from src.services import patent_service

log = get_logger(__name__)


class PatentController(BeydjikController):
    def import_blank(self, region: str, side: str, source: Path) -> Path:
        """Adopt the office's own front or back for this region."""
        return patent_service.import_blank(region, side, Path(source))

    @staticmethod
    def blank_state(region: str) -> str:
        """What the section is printing on, for the operator to see."""
        own = [side for side in patent_service.SIDES
               if patent_service.user_blank_path(region, side).exists()]
        if len(own) == len(patent_service.SIDES):
            return "ўз шаблонингиз"
        if own:
            return f"ўз шаблонингиз ({', '.join(own)}), қолгани дастурники"
        return "дастурдаги шаблон"
