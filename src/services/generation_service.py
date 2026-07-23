"""Generate the final PDF: data → build_values → fill the company's template →
save named by the worker's surname → advance the registration counter.

Every company shares ONE field mapping (all templates have identical box
coordinates per the МВД form; only the company graphics differ), so a new
company needs only its own ``template.pdf`` — never a code or mapping change.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.common.logging import get_logger
from src.config import paths
from src.config.settings_service import SettingsService
from src.domain.company import Company
from src.domain.employee import Employee
from src.pdf.engine import fill
from src.pdf.mapping import FieldMapping
from src.services.field_extractor import build_values

log = get_logger(__name__)

# The shared МВД form (one mapping for every company template).
_FORM_DIR = paths.templates_dir() / "mvd_prilozhenie_7"
_MAPPING_PATH = _FORM_DIR / "mapping.v1.json"

_REG_COUNTER_KEY = "doc.reg_counter"
_REG_START_DEFAULT = 345


@dataclass(frozen=True)
class GenerationResult:
    pdf_path: Path
    reg_number: int
    surname: str


class GenerationService:
    def __init__(self, settings: SettingsService) -> None:
        self._settings = settings

    def next_reg_number(self) -> int:
        """Peek the number the next generated PDF will carry (does not consume)."""
        return int(self._settings.get(_REG_COUNTER_KEY, _REG_START_DEFAULT))  # type: ignore[arg-type]

    def _advance_reg_number(self) -> int:
        current = self.next_reg_number()
        self._settings.set(_REG_COUNTER_KEY, current + 1)
        return current

    def generate(
        self,
        employee: Employee,
        company: Company,
        *,
        form_date: date,
        profession: str | None = None,
    ) -> GenerationResult:
        reg_number = self._advance_reg_number()
        values = build_values(
            employee, company, form_date=form_date, reg_number=reg_number, profession=profession
        )
        mapping = FieldMapping.load(_MAPPING_PATH)
        out_path = self._unique_output_path(company, employee)
        fill(company.template_path, mapping, values, out_path)
        log.info("Generated %s (reg %s) for %s", out_path.name, reg_number, company.name)
        return GenerationResult(pdf_path=out_path, reg_number=reg_number, surname=employee.passport.surname)

    def _unique_output_path(self, company: Company, employee: Employee) -> Path:
        folder = paths.output_dir() / _safe(company.name)
        folder.mkdir(parents=True, exist_ok=True)
        stem = employee.output_basename()
        candidate = folder / f"{stem}.pdf"
        i = 1
        while candidate.exists():
            candidate = folder / f"{stem}_{i:03d}.pdf"
            i += 1
        return candidate


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in " _-" else "_" for c in name).strip() or "company"
