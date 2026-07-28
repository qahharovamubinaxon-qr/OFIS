"""СТРАХОВКА МАШИНАГА — ОСАГО for the workers who drive the firm's cars.

The office holds agency status with several insurers through several of its own
companies, so each insurer's policy template is registered once and every car
after that is filled into a copy of it (the same idea as a Трудовой firm).

One run takes a photograph of the car's СТС (front and back) and of up to four
drivers' licences, the day cover starts, and the one choice that decides who the
policy actually covers — «неограниченного количества лиц» or the named list.

Cover runs for one year to the day before: cover from 10.07.2026 ends 09.07.2027.

What the program refuses to make up
-----------------------------------
* **the policy серия/номер.** РСА allocates those through the insurer; the
  operator records the block the agency was given (Settings) and the program
  hands them out in order, refusing to go past the end — the same rule the ДМС
  module already follows. A number nobody allocated is a policy that covers no
  one.
* **the electronic signature.** The previous policy's certificate, МЧД and
  доверенность are erased and never re-created; they belong to the insurer's
  signing system.
* **КБМ and the premium.** Those come from the РСА database and the insurer's
  own calculation.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from uuid import UUID

from src.common.errors import ValidationError
from src.common.logging import get_logger
from src.config import paths
from src.database.repositories.insurance_template_repo import (
    InsuranceTemplateRepository,
)
from src.domain.insurance_template import InsuranceTemplate
from src.domain.vehicle import DriverLicence, Sts
from src.services import insurance_docx

log = get_logger(__name__)

MAX_DRIVERS = 4

KEY_SERIES = "osago.series"
KEY_FROM, KEY_TO, KEY_NEXT = "osago.number_from", "osago.number_to", "osago.number_next"

#: The templates the office already works with, seeded on first run.
BUNDLED: tuple[tuple[str, str, str], ...] = (
    ("ingosstrah", "Ингосстрах", "СПАО «Ингосстрах»"),
    ("reso", "РЕСО-Гарантия", "САО «РЕСО-Гарантия»"),
    ("soglasie", "Согласие", "СК «Согласие»"),
    ("osago_a", "ОСАГО (электронный полис)", ""),
)


def cover_until(start: date) -> date:
    """A year of cover ends the day before the anniversary."""
    try:
        anniversary = start.replace(year=start.year + 1)
    except ValueError:
        # cover taken out on 29 February runs to 28 February
        anniversary = date(start.year + 1, 3, 1)
    return anniversary - timedelta(days=1)


def _bundled_dir() -> Path:
    return paths.templates_dir() / "strahovka"


@dataclass(frozen=True)
class InsuranceResult:
    docx_path: Path
    pdf_path: Path | None
    plate: str
    drivers: int
    notes: list[str]


class InsuranceTemplateService:
    """Register an insurer's policy template; add more the same way."""

    def __init__(self, repo: InsuranceTemplateRepository) -> None:
        self._repo = repo

    def list(self) -> list[InsuranceTemplate]:
        return self._repo.list_active()

    def seed_bundled(self) -> int:
        """Put the templates shipped with the program into the picker once."""
        added = 0
        for code, name, insurer in BUNDLED:
            source = _bundled_dir() / code / "polis.docx"
            if not source.exists() or self._repo.by_internal_code(code):
                continue
            self._repo.upsert(InsuranceTemplate(
                name=name, internal_code=code, insurer=insurer,
                template_path=source))
            added += 1
        if added:
            log.info("Seeded %d ОСАГО templates", added)
        return added

    def create(self, name: str, code: str, source: Path, *,
               insurer: str = "", firm: str = "") -> InsuranceTemplate:
        code = code.strip().lower()
        if not name.strip() or not code:
            raise ValidationError("Ном ва код керак")
        if source.suffix.lower() != ".docx":
            raise ValidationError("Шаблон Word (.docx) бўлиши керак",
                                  context={"path": str(source)})
        if not source.exists():
            raise ValidationError("Шаблон файли топилмади",
                                  context={"path": str(source)})
        if self._repo.by_internal_code(code):
            raise ValidationError("Бундай код аллақачон бор", context={"code": code})
        dest = paths.user_templates_dir() / f"strahovka_{code}" / "polis.docx"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        template = InsuranceTemplate(name=name.strip(), internal_code=code,
                                     insurer=insurer.strip(), firm=firm.strip(),
                                     template_path=dest)
        self._repo.upsert(template)
        log.info("ОСАГО template added: %s (%s)", name, code)
        return template

    def archive(self, template_id: UUID) -> None:
        self._repo.archive(template_id)


class InsuranceService:
    def __init__(self, settings=None) -> None:
        self._settings = settings

    # ------------------------------------------------------------- numbers
    def policy_number(self) -> str:
        """The next number from the block the agency was actually allocated.

        Empty when no block has been recorded — the policy then prints without
        one and the operator writes in the number the insurer issued. The
        program never makes one up.
        """
        if self._settings is None:
            return ""
        series = (self._settings.get(KEY_SERIES) or "").strip().upper()
        low = (self._settings.get(KEY_FROM) or "").strip()
        high = (self._settings.get(KEY_TO) or "").strip()
        if not (low.isdigit() and high.isdigit()):
            return ""
        nxt = (self._settings.get(KEY_NEXT) or "").strip()
        current = int(nxt) if nxt.isdigit() else int(low)
        if current > int(high):
            raise ValidationError(
                "Страховая компания берган номерлар тугади — Созламаларда "
                "янги оралиқни киритинг",
                context={"from": low, "to": high})
        self._settings.set(KEY_NEXT, str(current + 1))
        width = len(low)
        return f"{series} {current:0{width}d}".strip()

    # -------------------------------------------------------------- filling
    def generate(
        self,
        sts: Sts,
        drivers: list[DriverLicence],
        template: InsuranceTemplate,
        *,
        start: date,
        unlimited: bool,
        policy_holder: str = "",
        output_dir: Path | None = None,
    ) -> InsuranceResult:
        if not template.template_path.exists():
            raise ValidationError("Шаблон файли топилмади",
                                  context={"path": str(template.template_path)})
        named = [d for d in drivers if not d.is_empty()][:MAX_DRIVERS]
        if not unlimited and not named:
            raise ValidationError(
                "«Лица, допущенные к управлению» танланганда камида битта "
                "ҳайдовчи праваси керак")

        end = cover_until(start)
        holder = policy_holder.strip() or sts.owner_fio
        values = {k: v for k, v in {
            "vehicle": sts.vehicle,
            "vin": sts.vin,
            "plate": sts.plate,
            "sts": sts.document,
            "policy_holder": holder,
            "owner": sts.owner_fio or holder,
        }.items() if v}

        out = self._path(sts, template, output_dir)
        report = insurance_docx.fill(
            template.template_path, out, values=values,
            drivers=[(d.fio, d.licence) for d in named], unlimited=unlimited,
            start=_dmy(start), end=_dmy(end), signed=_dmy(start))

        notes = list(report.skipped)
        if report.cleared:
            notes.append("Шаблондаги электрон имзо ўз ҳолича қолдирилди — "
                         "уни страховая компания алмаштиради")
        notes.append("Полис серия/номерини страховая компания беради — "
                     "программа ўзи ўйлаб чиқармайди")
        notes.append("КБМ ва страховая премия РСА базасидан олинади")

        from src.services.docx_editor import docx_to_pdf

        log.info("ОСАГО for %s (%s): %d drivers, %s — %s",
                 sts.plate, template.name, report.drivers, _dmy(start), _dmy(end))
        return InsuranceResult(docx_path=out, pdf_path=docx_to_pdf(out),
                               plate=sts.plate, drivers=report.drivers, notes=notes)

    def _path(self, sts: Sts, template: InsuranceTemplate,
              base: Path | None) -> Path:
        folder = base if base is not None else (
            paths.output_dir() / "strahovka" / _safe(template.name))
        folder.mkdir(parents=True, exist_ok=True)
        stem = _safe(sts.plate.upper()) or "AUTO"
        candidate, i = folder / f"{stem}.docx", 1
        while candidate.exists():
            candidate = folder / f"{stem}_{i:03d}.docx"
            i += 1
        return candidate


def _dmy(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in " _-" else "_" for c in name).strip() or "auto"
