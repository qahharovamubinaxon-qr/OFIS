"""Company use-cases: create/update/list, and template management.

A company's PDF template + its field mapping live under ``templates/<code>/``;
adding a company copies its blank template there so nothing in code changes.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from uuid import UUID

from src.common.errors import ValidationError
from src.common.logging import get_logger
from src.config import paths
from src.database.repositories.company_repo import CompanyRepository
from src.domain.company import Company

log = get_logger(__name__)


class CompanyService:
    def __init__(self, repo: CompanyRepository) -> None:
        self._repo = repo

    def list(self) -> list[Company]:
        return self._repo.list_active()

    def get(self, company_id: UUID) -> Company | None:
        return self._repo.get(company_id)

    def count(self) -> int:
        return self._repo.count()

    def create(self, company: Company, template_source: Path | None = None) -> Company:
        if self._repo.by_internal_code(company.internal_code):
            raise ValidationError(
                "Internal code already exists", context={"code": company.internal_code}
            )
        if template_source is not None:
            company = company.model_copy(update={"template_path": self._import_template(company, template_source)})
        if not company.template_path.exists():
            raise ValidationError("Template file not found", context={"path": str(company.template_path)})
        self._repo.upsert(company)
        log.info("Company created: %s (%s)", company.name, company.internal_code)
        return company

    def update(self, company: Company) -> Company:
        self._repo.upsert(company)
        return company

    def _import_template(self, company: Company, source: Path) -> Path:
        """Copy a company's blank template into templates/<code>/template.pdf."""
        dest_dir = paths.templates_dir() / company.internal_code.lower()
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / "template.pdf"
        shutil.copyfile(source, dest)
        return dest
