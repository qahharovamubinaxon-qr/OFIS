"""Generate the registration PDF: passport + patent + expiry → fill the chosen
address's template → save named by the worker's surname.

Every address shares ONE field mapping (all registration templates have
identical box coordinates; only the printed address/host differ), so a new
address needs only its own ``template.pdf`` — never a code or mapping change.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.common.logging import get_logger
from src.config import paths
from src.domain.documents import Passport, Patent
from src.domain.registration_address import RegistrationAddress
from src.pdf.engine import fill
from src.pdf.mapping import FieldMapping
from src.services.registration_values import build_registration_values

log = get_logger(__name__)

_MAPPING_PATH = paths.templates_dir() / "registration" / "mapping.v1.json"


@dataclass(frozen=True)
class RegistrationResult:
    pdf_path: Path
    surname: str


class RegistrationService:
    def next_output_dir(self, address: RegistrationAddress) -> Path:
        return paths.output_dir() / "registration" / _safe(address.label)

    def generate(
        self,
        passport: Passport,
        patent: Patent | None,
        address: RegistrationAddress,
        *,
        registration_expiry: date,
        output_dir: Path | None = None,
    ) -> RegistrationResult:
        values = build_registration_values(
            passport, patent, registration_expiry=registration_expiry
        )
        mapping = FieldMapping.load(_MAPPING_PATH)
        out_path = self._unique_output_path(address, passport, output_dir)
        fill(address.template_path, mapping, values, out_path)
        log.info("Generated registration %s for %s", out_path.name, address.label)
        return RegistrationResult(pdf_path=out_path, surname=passport.surname)

    def _unique_output_path(
        self, address: RegistrationAddress, passport: Passport, base: Path | None
    ) -> Path:
        folder = base if base is not None else self.next_output_dir(address)
        folder.mkdir(parents=True, exist_ok=True)
        stem = _safe(f"{passport.surname}_{passport.name}".upper()) or "REG"
        candidate = folder / f"{stem}.pdf"
        i = 1
        while candidate.exists():
            candidate = folder / f"{stem}_{i:03d}.pdf"
            i += 1
        return candidate


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in " _-" else "_" for c in name).strip() or "reg"
