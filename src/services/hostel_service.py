"""ХОСТЕЛ — arrival-notification (Уведомление о прибытии) for a hostel host.

Same МВД form as Registration, but the принимающая сторона is a hostel/hotel
(гостиничные услуги): its отрывная часть carries the organisation name + ИНН.
Two paths, mirroring Registration:

* the operator uploads a ready hostel template (address + host already printed)
  → the program fills only the worker + dates;
* or fills the fields → the program prints the address (page 1) and the host
  block / organisation / ИНН (page 2) onto the bundled blank to make that
  hostel's template.

The worker-fill and address-builder coordinate maps live in
``templates/hostel/{mapping,address_mapping}.v1.json`` (calibrated to the blank).
This module NEVER reproduces the МВД electronic-signature block or a registration
number — those are applied by МВД/Госуслуги after a real submission.
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


def _hostel_dir() -> Path:
    return paths.templates_dir() / "hostel"


def _blank() -> Path:
    return paths.templates_dir() / "hostel_blank" / "blank.pdf"


@dataclass(frozen=True)
class HostelResult:
    pdf_path: Path
    surname: str


class HostelTemplateBuilder:
    """Print a hostel's fixed data (address + host + org + ИНН) onto the blank."""

    def available(self) -> bool:
        return _blank().exists() and (_hostel_dir() / "address_mapping.v1.json").exists()

    def build(self, out: Path, address: RegistrationAddress) -> Path:
        mapping = FieldMapping.load(_hostel_dir() / "address_mapping.v1.json")
        values = {
            "host.addr.subject": address.oblast or "",
            "host.addr.locality": address.raion or "",
            "host.addr.settlement": address.gorod or "",
            "host.addr.street": address.ulitsa or "",
            "host.addr.dom": f"ДОМ {address.dom}" if address.dom else "",
            "host.addr.korpus": f"КОРПУС {address.korpus}" if address.korpus else "",
            "host.addr.litera": (f"ЛИТЕРА {address.stroenie}" if address.stroenie else ""),
            "host.addr.komnata": (f"КОМ. {address.komnata}" if address.komnata else ""),
            "host.surname": _part(address.host_fio, 0),
            "host.name": _part(address.host_fio, 1),
            "host.patronymic": _part(address.host_fio, 2, tail=True),
            "host.org": address.organization_name or "",
            "host.inn": address.inn or "",
        }
        out.parent.mkdir(parents=True, exist_ok=True)
        fill(_blank(), mapping, values, out)
        log.info("Built hostel template for %s", address.label)
        return out


class HostelService:
    def next_output_dir(self, address: RegistrationAddress) -> Path:
        return paths.output_dir() / "hostel" / _safe(address.label)

    def generate(
        self,
        passport: Passport,
        patent: Patent | None,
        address: RegistrationAddress,
        *,
        registration_expiry: date,
        output_dir: Path | None = None,
    ) -> HostelResult:
        values = build_registration_values(
            passport, patent, registration_expiry=registration_expiry
        )
        mapping = FieldMapping.load(_hostel_dir() / "mapping.v1.json")
        out_path = self._unique_output_path(address, passport, output_dir)
        fill(address.template_path, mapping, values, out_path)
        log.info("Generated hostel %s for %s", out_path.name, address.label)
        return HostelResult(pdf_path=out_path, surname=passport.surname)

    def _unique_output_path(
        self, address: RegistrationAddress, passport: Passport, base: Path | None
    ) -> Path:
        folder = base if base is not None else self.next_output_dir(address)
        folder.mkdir(parents=True, exist_ok=True)
        stem = _safe(f"{passport.surname}_{passport.name}".upper()) or "HOSTEL"
        candidate = folder / f"{stem}.pdf"
        i = 1
        while candidate.exists():
            candidate = folder / f"{stem}_{i:03d}.pdf"
            i += 1
        return candidate


def _part(fio: str | None, idx: int, *, tail: bool = False) -> str:
    parts = (fio or "").split()
    if idx >= len(parts):
        return ""
    return " ".join(parts[idx:]) if tail else parts[idx]


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in " _-" else "_" for c in name).strip() or "hostel"
