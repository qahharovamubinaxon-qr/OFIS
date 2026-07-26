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

    def list(self) -> list[RegistrationAddress]:
        return self._repo.list_active()

    def get(self, address_id: UUID) -> RegistrationAddress | None:
        return self._repo.get(address_id)

    def count(self) -> int:
        return self._repo.count()

    def archive(self, address_id: UUID) -> None:
        """Remove from the picker (soft delete — nothing on disk is lost)."""
        self._repo.archive(address_id)
        log.info("Registration address archived: %s", address_id)

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
