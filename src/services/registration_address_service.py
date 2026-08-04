"""Registration-address use-cases: create/list, plus template import.

Each address's blank registration PDF is copied under
``templates/registration_<code>/`` so adding one never changes code — all
addresses share the one ``templates/registration/mapping.v1.json`` mapping.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from uuid import UUID

from src.common.errors import ValidationError
from src.common.logging import get_logger
from src.config import paths
from src.database.repositories.registration_address_repo import RegistrationAddressRepository
from src.domain.registration_address import RegistrationAddress

log = get_logger(__name__)


class RegistrationAddressService:
    def __init__(self, repo: RegistrationAddressRepository) -> None:
        self._repo = repo

    def list(self, kind: str | None = None) -> list[RegistrationAddress]:
        return self._repo.list_active(kind)

    def create_hostel(
        self,
        address: RegistrationAddress,
        template_source: Path | None = None,
    ) -> RegistrationAddress:
        """Register a hostel address (kind='hostel'). Its template is either an
        uploaded ready PDF or built from the bundled hostel blank with the
        address + host + organisation + ИНН printed on."""
        if self._repo.by_internal_code(address.internal_code):
            raise ValidationError(
                "Internal code already exists", context={"code": address.internal_code}
            )
        address = address.model_copy(update={"kind": "hostel"})
        if template_source is not None:
            dest = self._hostel_dest(address)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(template_source, dest)
            address = address.model_copy(update={"template_path": dest})
        else:
            from src.services.hostel_service import HostelTemplateBuilder

            dest = self._hostel_dest(address)
            built = HostelTemplateBuilder().build(dest, address)
            address = address.model_copy(update={"template_path": built})
        if not address.template_path.exists():
            raise ValidationError(
                "Template file not found", context={"path": str(address.template_path)}
            )
        self._repo.upsert(address)
        log.info("Hostel address created: %s (%s)", address.label, address.internal_code)
        return address

    def create_mvdreg(
        self,
        address: RegistrationAddress,
        template_source: Path | None = None,
    ) -> RegistrationAddress:
        """Register an МВД РЕГИСТРАЦИЯ address (kind='mvdreg').

        Same road as a hostel's: a ready template PDF, or the office's own
        МВД blank with the address + host + organisation printed on."""
        if self._repo.by_internal_code(address.internal_code):
            raise ValidationError(
                "Internal code already exists", context={"code": address.internal_code}
            )
        address = address.model_copy(update={"kind": "mvdreg"})
        dest = self._mvdreg_dest(address)
        if template_source is not None:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(template_source, dest)
            address = address.model_copy(update={"template_path": dest})
        else:
            from src.services.mvdreg_service import MvdRegTemplateBuilder

            built = MvdRegTemplateBuilder().build(dest, address)
            address = address.model_copy(update={"template_path": built})
        if not address.template_path.exists():
            raise ValidationError(
                "Template file not found", context={"path": str(address.template_path)}
            )
        self._repo.upsert(address)
        log.info("MvdReg address created: %s (%s)", address.label,
                 address.internal_code)
        return address

    @staticmethod
    def _mvdreg_dest(address: RegistrationAddress) -> Path:
        return (paths.user_templates_dir()
                / f"mvdreg_{address.internal_code.lower()}" / "template.pdf")

    def set_stay_from(self, address_id: UUID,
                      spot: tuple[float, float] | None) -> RegistrationAddress:
        """Remember where this hostel wants the stay-start date printed.

        ``None`` puts it back where the form itself puts it.
        """
        address = self._repo.get(address_id)
        if address is None:
            raise ValidationError("Хостел топилмади", context={"id": str(address_id)})
        x, y = spot if spot is not None else (None, None)
        address = address.model_copy(update={"stay_from_x": x, "stay_from_y": y})
        self._repo.upsert(address)
        log.info("Stay-from spot for %s: %s", address.label, spot or "default")
        return address

    @staticmethod
    def _hostel_dest(address: RegistrationAddress) -> Path:
        return (paths.user_templates_dir()
                / f"hostel_{address.internal_code.lower()}" / "template.pdf")

    def get(self, address_id: UUID) -> RegistrationAddress | None:
        return self._repo.get(address_id)

    def count(self) -> int:
        return self._repo.count()

    def archive(self, address_id: UUID) -> None:
        """Remove from the picker (soft delete — nothing on disk is lost)."""
        self._repo.archive(address_id)
        log.info("Registration address archived: %s", address_id)

    def list_archived(self, kind: str | None = None) -> list[RegistrationAddress]:
        """Addresses removed from the picker — still fully recoverable."""
        return self._repo.list_archived(kind)

    def restore(self, address_id: UUID) -> RegistrationAddress:
        """Bring a removed address back.

        If its template file is gone (an address created before templates moved
        to AppData — an EXE rebuild wiped the program folder), the blank is
        re-printed from the address data that the database still holds.
        """
        address = self._repo.get(address_id)
        if address is None:
            raise ValidationError("Address not found", context={"id": str(address_id)})
        self._repo.restore(address_id)
        if not address.template_path.exists():
            address = self._rebuild_template(address)
            self._repo.upsert(address)
        log.info("Registration address restored: %s", address.label)
        return address

    def _rebuild_template(self, address: RegistrationAddress) -> RegistrationAddress:
        """Re-print the blank for an address whose template file went missing."""
        if address.kind == "hostel":
            from src.services.hostel_service import HostelTemplateBuilder

            built = HostelTemplateBuilder().build(self._hostel_dest(address), address)
        else:
            from src.services.address_template_builder import AddressTemplateBuilder

            dest_dir = (paths.user_templates_dir()
                        / f"registration_{address.internal_code.lower()}")
            dest_dir.mkdir(parents=True, exist_ok=True)
            built = AddressTemplateBuilder().build(
                dest_dir / "template.pdf",
                oblast=address.oblast, raion=address.raion, gorod=address.gorod,
                ulitsa=address.ulitsa, dom=address.dom, korpus=address.korpus,
                stroenie=address.stroenie, kvartira=address.kvartira,
                host_fio=address.host_fio, regional_number=address.regional_number,
            )
        log.info("Template rebuilt for %s → %s", address.label, built)
        return address.model_copy(update={"template_path": built})

    def create(
        self,
        address: RegistrationAddress,
        template_source: Path | None = None,
        *,
        build_from_blank: bool = False,
    ) -> RegistrationAddress:
        """Register an address. Its template comes from either an uploaded
        ready-made PDF (``template_source``) or, when ``build_from_blank`` is
        set, is generated from the blank with the address data printed in."""
        if self._repo.by_internal_code(address.internal_code):
            raise ValidationError(
                "Internal code already exists", context={"code": address.internal_code}
            )
        if template_source is not None:
            address = address.model_copy(
                update={"template_path": self._import_template(address, template_source)}
            )
        elif build_from_blank:
            from src.services.address_template_builder import AddressTemplateBuilder

            dest_dir = paths.user_templates_dir() / f"registration_{address.internal_code.lower()}"
            dest_dir.mkdir(parents=True, exist_ok=True)
            built = AddressTemplateBuilder().build(
                dest_dir / "template.pdf",
                oblast=address.oblast, raion=address.raion, gorod=address.gorod,
                ulitsa=address.ulitsa, dom=address.dom, korpus=address.korpus,
                stroenie=address.stroenie, kvartira=address.kvartira,
                host_fio=address.host_fio, regional_number=address.regional_number,
            )
            address = address.model_copy(update={"template_path": built})
        if not address.template_path.exists():
            raise ValidationError(
                "Template file not found", context={"path": str(address.template_path)}
            )
        self._repo.upsert(address)
        log.info("Registration address created: %s (%s)", address.label, address.internal_code)
        return address

    def _import_template(self, address: RegistrationAddress, source: Path) -> Path:
        dest_dir = paths.user_templates_dir() / f"registration_{address.internal_code.lower()}"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / "template.pdf"
        shutil.copyfile(source, dest)
        return dest
