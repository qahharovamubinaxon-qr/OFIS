"""Трудовой-Уведомления: one RUN → two PDFs for one worker.

* трудовой договор — the firm's text template with the worker block, contract
  date and profession re-written (:class:`~src.pdf.trud_editor.TrudDocEditor`);
* уведомление о заключении трудового договора — the firm's госуслуги blank
  filled per ``templates/trud/uved_mapping.v1.json``.

Business rules: names/citizenship from the patent (Russian), the rest from the
passport; values are Title-case («Мирзамуродов», «Узбекистан», «Мужской»);
patent region derived from the patent's issuing organ.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from uuid import UUID

from src.common.errors import ValidationError
from src.common.logging import get_logger
from src.config import paths
from src.database.repositories.trud_firm_repo import TrudFirmRepository
from src.domain.documents import Passport, Patent
from src.domain.enums import Gender
from src.domain.trud_firm import TrudFirm
from src.pdf.engine import fill
from src.pdf.formatters import _date_dmy
from src.pdf.mapping import FieldMapping
from src.pdf.trud_editor import TrudDocEditor
from src.utils.geo import birth_country

log = get_logger(__name__)

_UVED_MAPPING = paths.templates_dir() / "trud" / "uved_mapping.v1.json"

DEFAULT_TRUD_PROFESSION = "ПОДСОБНЫЙ РАБОЧИЙ"


def _title(s: str | None) -> str:
    return (s or "").strip().title()


def _sentence(s: str | None) -> str:
    s = (s or "").strip()
    return s[:1].upper() + s[1:].lower() if s else ""


def patent_region(patent: Patent | None) -> str:
    issued = ((patent.issued_by if patent else "") or "").upper()
    if "МОСКОВСК" in issued and "ОБЛАСТ" in issued:
        return "Московская область"
    return "Москва"


@dataclass(frozen=True)
class TrudResult:
    trud_path: Path
    uved_path: Path
    surname: str
    hod_path: Path | None = None


class TrudFirmService:
    """Firm CRUD: each firm imports its two templates under templates/trud_<code>/."""

    def __init__(self, repo: TrudFirmRepository) -> None:
        self._repo = repo

    def list(self) -> list[TrudFirm]:
        return self._repo.list_active()

    def archive(self, firm_id: UUID) -> None:
        self._repo.archive(firm_id)
        log.info("Trud firm archived: %s", firm_id)

    def create(self, name: str, code: str, trud_source: Path, uved_source: Path,
               hod_source: Path | None = None) -> TrudFirm:
        if self._repo.by_internal_code(code):
            raise ValidationError("Internal code already exists", context={"code": code})
        dest = paths.templates_dir() / f"trud_{code.lower()}"
        dest.mkdir(parents=True, exist_ok=True)
        trud = dest / f"trudovoy{trud_source.suffix.lower()}"
        uved = dest / f"uvedomlenie{uved_source.suffix.lower()}"
        shutil.copyfile(trud_source, trud)
        shutil.copyfile(uved_source, uved)
        hod = None
        if hod_source is not None:
            hod = dest / f"hodataystvo{hod_source.suffix.lower()}"
            shutil.copyfile(hod_source, hod)
        firm = TrudFirm(name=name, internal_code=code,
                        trud_template_path=trud, uved_template_path=uved,
                        hod_template_path=hod)
        self._repo.upsert(firm)
        log.info("Trud firm created: %s (%s)", name, code)
        return firm


class TrudService:
    def __init__(self) -> None:
        self._editor = TrudDocEditor()

    def generate(
        self,
        passport: Passport,
        patent: Patent | None,
        firm: TrudFirm,
        *,
        form_date: date,
        profession: str | None = None,
        output_dir: Path | None = None,
    ) -> TrudResult:
        prof = _sentence(profession or DEFAULT_TRUD_PROFESSION)
        folder = output_dir if output_dir is not None else (
            paths.output_dir() / "trud" / _safe(firm.name)
        )
        folder.mkdir(parents=True, exist_ok=True)
        stem = _safe(f"{passport.surname}_{passport.name}".upper()) or "WORKER"

        if firm.trud_template_path.suffix.lower() == ".docx":
            from src.services.docx_editor import TrudDocxEditor, docx_to_pdf
            from src.services.field_extractor import plus_one_year

            fio_u = " ".join(x for x in (passport.surname, passport.name,
                                         passport.patronymic or "") if x).upper()
            initials = "".join(w[0] + "." for w in
                               f"{passport.name} {passport.patronymic or ''}".split()[:2])
            docx_path = _unique(folder / f"{stem}_ТРУДОВОЙ.docx")
            TrudDocxEditor().fill_trudovoy(
                firm.trud_template_path, docx_path,
                form_date=form_date, fio_upper=fio_u,
                citizenship_upper=(passport.nationality or "").upper(),
                sign_abbr=f"{passport.surname.upper()} {initials}",
                contract_end=(plus_one_year(patent.issue_date)
                              if patent and patent.issue_date else None),
                profession=prof,
                fio_title=_title(fio_u),
                birth_date=passport.birth_date,
                passport_number=f"{passport.series or ''}{passport.number}".strip(),
                passport_issue=passport.issue_date,
            )
            trud_path = docx_to_pdf(docx_path) or docx_path
        else:
            trud_path = _unique(folder / f"{stem}_ТРУДОВОЙ.pdf")
            self._editor.fill(
                firm.trud_template_path, trud_path,
                date_text=_date_dmy(form_date),
                worker_block=self._worker_block(passport),
                profession=prof,
            )

        if firm.uved_template_path.suffix.lower() == ".docx":
            from src.services.docx_editor import TrudDocxEditor, docx_to_pdf

            uv = self._uved_values(passport, patent, form_date=form_date, profession=prof)
            docx_uv = _unique(folder / f"{stem}_УВЕДОМЛЕНИЕ.docx")
            TrudDocxEditor().fill_uvedomlenie(firm.uved_template_path, docx_uv, {
                "surname": uv.get("uved.surname", ""), "name": uv.get("uved.name", ""),
                "patronymic": uv.get("uved.patronymic", ""),
                "birth_date": uv.get("uved.birth_date", ""),
                "gender": uv.get("uved.gender", ""),
                "citizenship": uv.get("uved.citizenship", ""),
                "birth_place": uv.get("uved.birth_place", ""),
                "pass_series": uv.get("uved.passport.series", ""),
                "pass_number": uv.get("uved.passport.number", ""),
                "pass_issue_date": uv.get("uved.passport.issue_date", ""),
                "pass_issued_by": uv.get("uved.passport.issued_by", ""),
                "pat_series": uv.get("uved.patent.series", ""),
                "pat_number": uv.get("uved.patent.number", ""),
                "region": uv.get("uved.patent.region", ""),
                "blank_series": uv.get("uved.patent.blank_series", ""),
                "blank_number": uv.get("uved.patent.blank_number", ""),
                "profession": prof, "contract_date": uv.get("uved.contract_date", ""),
            })
            uved_path = docx_to_pdf(docx_uv) or docx_uv
        else:
            uved_path = _unique(folder / f"{stem}_УВЕДОМЛЕНИЕ.pdf")
            mapping = FieldMapping.load(_UVED_MAPPING)
            fill(firm.uved_template_path, mapping, self._uved_values(
                passport, patent, form_date=form_date, profession=prof,
            ), uved_path)

        hod_path = None
        if firm.hod_template_path and firm.hod_template_path.exists():
            from src.services.docx_editor import HodDocxEditor, docx_to_pdf

            issue = (f"выдан {_date_dmy(passport.issue_date)}"
                     if passport.issue_date else "выдан ________")
            passport_line = (f"{passport.series or ''}{passport.number}".strip()
                             + f", {issue} {(passport.issued_by or '').upper()}").strip()
            hod_docx = _unique(folder / f"{stem}_ХОДАТАЙСТВО.docx")
            HodDocxEditor().fill(
                firm.hod_template_path, hod_docx,
                fio_title=_title(" ".join(x for x in (passport.surname, passport.name,
                                                      passport.patronymic or "") if x)),
                citizenship_upper=(passport.nationality or "").upper(),
                pat_series=(patent.series if patent else "") or "",
                pat_number=(patent.number if patent else "") or "",
                passport_line=passport_line, form_date=form_date,
            )
            hod_path = docx_to_pdf(hod_docx) or hod_docx

        log.info("Generated трудовой+уведомление for %s (%s)", passport.surname, firm.name)
        return TrudResult(trud_path=trud_path, uved_path=uved_path,
                          surname=passport.surname, hod_path=hod_path)

    @staticmethod
    def _worker_block(p: Passport) -> str:
        fio = " ".join(x for x in (_title(p.surname), _title(p.name), _title(p.patronymic)) if x)
        parts = [f"Работник: {fio},"]
        if p.birth_date:
            parts.append(f"Дата рождения {_date_dmy(p.birth_date)}")
        if p.nationality:
            parts.append(f"Гражданство {_title(p.nationality)}")
        number = f"{p.series or ''}{p.number}".strip()
        parts.append(f"Иностранный паспорт Номер {number}")
        if p.issue_date:
            parts.append(f"Дата выдачи {_date_dmy(p.issue_date)}")
        if p.issued_by:
            parts.append(f"Кем выдан {p.issued_by.upper()}")
        return " ".join(parts)

    @staticmethod
    def _uved_values(
        passport: Passport, patent: Patent | None, *, form_date: date, profession: str
    ) -> dict[str, str]:
        citizenship = _title(passport.nationality)
        values = {
            "uved.surname": _title(passport.surname),
            "uved.name": _title(passport.name),
            "uved.patronymic": _title(passport.patronymic),
            "uved.birth_date": _date_dmy(passport.birth_date) if passport.birth_date else "",
            "uved.gender": ("Мужской" if passport.gender == Gender.MALE
                            else "Женский" if passport.gender == Gender.FEMALE else ""),
            "uved.citizenship": citizenship,
            "uved.birth_place": birth_country(passport.birth_place, passport.nationality)
                                or citizenship,
            "uved.passport.series": (passport.series or "").upper(),
            "uved.passport.number": passport.number,
            "uved.passport.issue_date": _date_dmy(passport.issue_date) if passport.issue_date else "",
            "uved.passport.issued_by": (passport.issued_by or "").upper(),
            "uved.profession": profession,
            "uved.contract_date": _date_dmy(form_date),
        }
        if patent is not None:
            values.update({
                "uved.patent.series": patent.series or "",
                "uved.patent.number": patent.number,
                "uved.patent.region": patent_region(patent),
                "uved.patent.blank_series": (patent.blank_series or "").upper(),
                "uved.patent.blank_number": patent.blank_number or "",
            })
        return {k: v for k, v in values.items() if v}


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in " _-" else "_" for c in name).strip() or "firm"


def _unique(candidate: Path) -> Path:
    base, i = candidate, 1
    while candidate.exists():
        candidate = base.with_name(f"{base.stem}_{i:03d}{base.suffix}")
        i += 1
    return candidate
