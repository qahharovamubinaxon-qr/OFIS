"""МВД ТРУДАВОЙ — reading the worker's documents and printing the packet.

Three photographs stand behind one packet: the passport, and the patent's two
sides. The passport names the worker; the patent supplies its own series,
number, issue date and the орган that granted it — everything the ten pages
ask about the worker.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from src.common.logging import get_logger
from src.domain.documents import Passport, Patent
from src.ocr.service import OcrService
from src.pdf.mvd_trud_renderer import MvdTrudData, plus_one_year
from src.services.mvd_trud_service import MvdTrudResult, MvdTrudService

log = get_logger(__name__)


class MvdTrudController:
    def __init__(self, ocr: OcrService, service: MvdTrudService) -> None:
        self._ocr = ocr
        self._service = service

    def ai_available(self) -> bool:
        return self._ocr.available()

    # ------------------------------------------------------------- store
    def templates(self, region: str = "moscow") -> list[Path]:
        return self._service.templates(region)

    def all_templates(self) -> list[Path]:
        """Both regions' blanks in one list — the bot's pick list."""
        return self._service.templates("moscow") + self._service.templates("oblast")

    @staticmethod
    def region_of(template) -> str:
        from src.services.mvd_trud_service import region_of

        return region_of(template)

    def add_template(self, name: str, source: Path,
                     region: str = "moscow") -> Path:
        return self._service.add_template(name, source, region)

    def remove_template(self, template: Path) -> None:
        self._service.remove_template(template)

    def layout(self, template: Path | None) -> dict:
        return self._service.layout(template)

    def save_layout(self, template: Path, layout: dict):
        return self._service.save_layout(template, layout)

    def reset_layout(self, template: Path) -> None:
        self._service.reset_layout(template)

    # ------------------------------------------------------------ reading
    def read_documents(self, passport_image: bytes, patent_front: bytes,
                       patent_back: bytes | None) -> tuple[Passport, Patent]:
        """Passport + patent, merged the way the office wants them.

        Through :meth:`OcrService.read_documents`, so the ФИО comes off the
        PATENT — it prints the name in Russian, ready for the packet — while
        the passport keeps supplying its own series, number, dates and орган.
        """
        passport, patent = self._ocr.read_documents(
            passport_image, patent_front, patent_back)
        return passport, patent or Patent(number="", profession="")

    @staticmethod
    def parse_date(text: str) -> date | None:
        text = (text or "").strip()
        for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None

    # ----------------------------------------------------------- printing
    def generate(self, *, template: Path | None, passport: Passport,
                 patent: Patent, profession: str, deal_date: date,
                 uved_no: str = "", spravka_no: str = "",
                 work_address: str = "") -> MvdTrudResult:
        """One packet from what the documents said and the operator picked."""
        data = MvdTrudData(
            surname=passport.surname or patent.holder_surname or "",
            name=passport.name or patent.holder_name or "",
            patronymic=passport.patronymic or patent.holder_patronymic or "",
            citizenship=(passport.nationality or patent.holder_citizenship
                         or ""),
            birth_date=passport.birth_date,
            pass_series=passport.series or "",
            pass_number=passport.number or "",
            pass_issued=passport.issue_date,
            pass_issued_by=passport.issued_by or "",
            pat_series=patent.series or "",
            pat_number=patent.number or "",
            pat_issued=patent.issue_date,
            pat_issued_by=patent.issued_by or "",
            profession=profession,
            deal_date=deal_date,
            # the patent's own end date when the back said it; a year from
            # issue otherwise — that is how long a patent runs
            pat_until=patent.valid_to or plus_one_year(patent.issue_date),
            uved_no=uved_no, spravka_no=spravka_no,
            work_address=work_address)
        return self._service.generate(data, template)

    # the область's place-of-work address is the firm's own and constant —
    # typed once, kept in settings, offered back on the next run
    def work_address(self) -> str:
        return self._service.work_address()

    def remember_work_address(self, value: str) -> None:
        self._service.remember_work_address(value)

    @staticmethod
    def read_image(path: Path) -> bytes:
        return Path(path).read_bytes()
