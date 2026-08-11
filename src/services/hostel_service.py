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

from src.common.errors import ValidationError
from src.common.logging import get_logger
from src.config import paths
from src.domain.documents import Passport, Patent
from src.domain.registration_address import RegistrationAddress
from src.pdf import boxes
from src.pdf.engine import fill
from src.pdf.mapping import FieldMapping, with_layout
from src.services.registration_values import build_registration_values

log = get_logger(__name__)

#: What this section is called in the arranged-layout store.
SECTION = "hostel"

#: The stay-start date, printed inside the «Отметка о подтверждении» box.
STAY_FROM = "reg.stay_from"


def _hostel_dir() -> Path:
    return paths.templates_dir() / "hostel"


def _blank() -> Path:
    return paths.templates_dir() / "hostel_blank" / "blank.pdf"


@dataclass(frozen=True)
class HostelResult:
    pdf_path: Path
    surname: str


@dataclass(frozen=True)
class StaySpot:
    """Everything needed to let the operator point at where the date goes.

    The box on the МВД form is large and every hostel's stamp sits somewhere
    else inside it, so the spot is marked once per hostel against a picture of
    that hostel's own page.
    """

    page: int
    image: boxes.PageImage
    x: float                 # the centre of the printed date, in points
    y: float                 # its baseline
    default_x: float
    default_y: float
    box: tuple[float, float, float, float] | None
    sample: str
    size: float              # the printed size in points, so the preview is honest
    bold: bool

    @property
    def is_default(self) -> bool:
        return (abs(self.x - self.default_x) < 0.05
                and abs(self.y - self.default_y) < 0.05)


def stay_from_default() -> tuple[int, float, float]:
    """Where the form itself puts the date: page, centre-x, baseline-y."""
    mapping = FieldMapping.load(_hostel_dir() / "mapping.v1.json")
    field = next((f for f in mapping.fields if f.id == STAY_FROM), None)
    if field is None or field.x is None or field.y is None:
        raise ValidationError("Бланкада бошланиш санаси майдони йўқ",
                              context={"field": STAY_FROM})
    return field.page, field.x + (field.width or 0.0) / 2, field.y


def _with_stay_from(mapping: FieldMapping,
                    address: RegistrationAddress) -> FieldMapping:
    """Move the date to where this hostel asked for it, if it asked."""
    if address.stay_from_x is None or address.stay_from_y is None:
        return mapping
    fields = []
    for field in mapping.fields:
        if field.id == STAY_FROM:
            field = field.model_copy(update={
                "x": address.stay_from_x - (field.width or 0.0) / 2,
                "y": address.stay_from_y,
            })
        fields.append(field)
    return mapping.model_copy(update={"fields": fields})


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

    def stay_from_spot(self, address: RegistrationAddress | None = None, *,
                       template: Path | None = None,
                       current: tuple[float, float] | None = None,
                       sample: date | None = None) -> StaySpot:
        """Render the page the start date is printed on, ready to be marked.

        Falls back to the bundled blank — a hostel being added has no template
        of its own yet, and the box is in the same place on both. ``current``
        is a spot chosen but not yet saved, so re-opening the picker does not
        throw away what the operator just marked.
        """
        from src.pdf.formatters import apply_formatter

        page, dx, dy = stay_from_default()
        source = template or (address.template_path if address else None)
        if source is None or not Path(source).exists():
            source = _blank()
        if not source.exists():
            raise ValidationError("Хостел бланкаси топилмади",
                                  context={"path": str(source)})

        if current is not None:
            x, y = current
        else:
            x = address.stay_from_x if address and address.stay_from_x is not None else dx
            y = address.stay_from_y if address and address.stay_from_y is not None else dy
        mapping = FieldMapping.load(_hostel_dir() / "mapping.v1.json")
        field = next(f for f in mapping.fields if f.id == STAY_FROM)
        return StaySpot(
            page=page, image=boxes.render(source, page), x=x, y=y,
            default_x=dx, default_y=dy,
            box=boxes.enclosing_box(source, page, (dx, dy)),
            sample=apply_formatter((sample or date.today()).isoformat(),
                                   field.formatter),
            size=field.size, bold="Bold" in field.font,
        )

    def generate(
        self,
        passport: Passport,
        patent: Patent | None,
        address: RegistrationAddress,
        *,
        registration_expiry: date,
        registration_start: date | None = None,
        output_dir: Path | None = None,
    ) -> HostelResult:
        values = build_registration_values(
            passport, patent, registration_expiry=registration_expiry
        )
        # Start of the stay, printed inside the «Отметка о подтверждении» box.
        # Only the date — the registration number and the electronic-signature
        # certificate are applied by МВД/Госуслуги after a real submission.
        values[STAY_FROM] = (registration_start or date.today()).isoformat()
        from src.pdf.mapping import own_values, with_marks
        from src.services import blank_layout

        layout = blank_layout.load(SECTION, address.template_path)
        # whatever the office typed onto THIS blank in «📐 Созлаш»
        values.update(own_values(layout))
        mapping = _with_stay_from(
            with_layout(FieldMapping.load(_hostel_dir() / "mapping.v1.json"),
                        layout),
            address)
        # …and the signature or stamp it placed there, kept with the blank
        mapping, pictures = with_marks(
            mapping, layout, blank_layout.marks(SECTION, address.template_path))
        values.update(pictures)
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
