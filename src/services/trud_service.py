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
from src.domain.firm_details import FirmDetails
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
    #: what the finished PDF could not be shown to contain (or still contained)
    notes: tuple[str, ...] = ()


class TrudFirmService:
    """Firm CRUD: each firm imports its two templates under templates/trud_<code>/."""

    def __init__(self, repo: TrudFirmRepository) -> None:
        self._repo = repo

    def list(self) -> list[TrudFirm]:
        return self._repo.list_active()

    def archive(self, firm_id: UUID) -> None:
        self._repo.archive(firm_id)
        log.info("Trud firm archived: %s", firm_id)

    def study_uved(self, firm: TrudFirm, ai) -> "object":
        """Learn where this firm's blank wants each worker value, and keep it.

        Every firm's Госуслуги blank differs — a different employer block, a
        different page count, some rows already filled — so one shared mapping
        cannot serve them all. Returns the study so the caller can tell the
        operator what was found.
        """
        from src.services import uved_layout

        if firm.uved_template_path.suffix.lower() != ".pdf":
            raise ValidationError("Only a PDF уведомление can be studied",
                                  context={"path": str(firm.uved_template_path)})
        result = uved_layout.study(firm.uved_template_path, ai)
        if result.ok:
            uved_layout.save(result, firm.uved_template_path,
                             firm.uved_template_path.parent)
        return result

    def study_trud(self, firm: TrudFirm, ai) -> "object":
        """Learn where this firm's contract leaves room for the worker.

        Only for a PDF contract — a .docx one is filled by text, which needs no
        study and is exact.
        """
        from src.services import trud_layout

        if firm.trud_template_path.suffix.lower() != ".pdf":
            raise ValidationError("Only a PDF трудовой договор can be studied",
                                  context={"path": str(firm.trud_template_path)})
        result = trud_layout.study(firm.trud_template_path, ai)
        if result.ok:
            trud_layout.save(result, firm.trud_template_path,
                             firm.trud_template_path.parent)
        return result

    def create_manual(self, details: FirmDetails, code: str, *,
                      today: date | None = None) -> TrudFirm:
        """Register a firm from its requisites — the program writes its templates.

        For a firm that never handed over a Word file. Both documents come out
        carrying the same Госуслуги labels an uploaded template would, so every
        worker after this is filled by the ordinary path.
        """
        from src.pdf.formatters import _date_long_g
        from src.services import firm_builder

        code = code.strip().lower()
        if not code:
            raise ValidationError("Фирма коди керак")
        if self._repo.by_internal_code(code):
            raise ValidationError("Internal code already exists", context={"code": code})

        dest = paths.user_templates_dir() / f"trud_{code}"
        dest.mkdir(parents=True, exist_ok=True)
        stamp = _copy_stamp(details.stamp_path, dest)
        details = details.model_copy(update={"stamp_path": stamp})
        header = _date_long_g(today or date.today()).removesuffix(" г.")
        trud, uved = firm_builder.build(details, dest, header_date=header)

        firm = TrudFirm(name=details.name, internal_code=code,
                        trud_template_path=trud, uved_template_path=uved,
                        details=details)
        self._repo.upsert(firm)
        log.info("Trud firm built from requisites: %s (%s)", details.name, code)
        return firm

    def create(self, name: str, code: str, trud_source: Path, uved_source: Path,
               hod_source: Path | None = None) -> TrudFirm:
        if self._repo.by_internal_code(code):
            raise ValidationError("Internal code already exists", context={"code": code})
        dest = paths.user_templates_dir() / f"trud_{code.lower()}"
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
        pdf_notes: list[str] = []
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
                worker=self._docx_values(passport, patent, form_date=form_date,
                                         profession=prof),
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
            report = self._editor.fill(
                firm.trud_template_path, trud_path,
                date_text=_date_dmy(form_date),
                worker_block=self._worker_block(passport),
                profession=prof,
            )
            # The editor reads its own output back; whatever it could not
            # confirm is carried to the operator rather than being logged away.
            pdf_notes = report.problems()

        if firm.uved_template_path.suffix.lower() == ".docx":
            from src.services.docx_editor import TrudDocxEditor, docx_to_pdf

            docx_uv = _unique(folder / f"{stem}_УВЕДОМЛЕНИЕ.docx")
            TrudDocxEditor().fill_uvedomlenie(
                firm.uved_template_path, docx_uv,
                self._docx_values(passport, patent, form_date=form_date,
                                  profession=prof, contract=False))
            uved_path = docx_to_pdf(docx_uv) or docx_uv
        else:
            uved_path = _unique(folder / f"{stem}_УВЕДОМЛЕНИЕ.pdf")
            from src.services import uved_layout

            # this firm's own blank, studied when it was added; the bundled
            # mapping is only a fallback for firms added before that existed
            own = uved_layout.mapping_for(firm.uved_template_path)
            mapping = FieldMapping.load(own or _UVED_MAPPING)
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
                          surname=passport.surname, hod_path=hod_path,
                          notes=tuple(pdf_notes))

    @staticmethod
    def _docx_values(passport: Passport, patent: Patent | None, *,
                     form_date: date, profession: str,
                     contract: bool = True) -> dict[str, str]:
        """What the Госуслуги labels inside a Word template should now read.

        The same labels appear in both documents, so one table serves the
        уведомление and the трудовой/ГПХ договор alike. ``address`` is the
        worker's own home address, which the office types into Word by hand —
        it is cleared so the previous worker's address cannot travel into the
        next worker's contract.
        """
        uv = TrudService._uved_values(passport, patent,
                                      form_date=form_date, profession=profession)
        values = {
            "surname": uv.get("uved.surname", ""),
            "name": uv.get("uved.name", ""),
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
            "profession": profession,
            "contract_date": uv.get("uved.contract_date", ""),
            "work_address": patent_region(patent),
        }
        values = {k: v for k, v in values.items() if v}
        if contract:
            values["address"] = ""
        return values

    @staticmethod
    def _trud_values(passport: Passport, patent: Patent | None, *,
                     form_date: date, profession: str) -> dict[str, str]:
        """What goes into each gap the contract leaves for the worker."""
        from src.pdf.formatters import _MONTHS_GEN

        fio = _title(" ".join(x for x in (passport.surname, passport.name,
                                          passport.patronymic or "") if x))
        initials = "".join(
            w[0].upper() + "." for w in
            f"{passport.name} {passport.patronymic or ''}".split()[:2])
        values = {
            "trud.worker_fio": fio,
            "trud.position": profession,
            "trud.req_fio": fio,
            "trud.req_doc": "паспорт иностранного гражданина",
            "trud.req_passport": f"{passport.series or ''} {passport.number}".strip(),
            "trud.req_passport_issued": " ".join(x for x in (
                _date_dmy(passport.issue_date) if passport.issue_date else "",
                passport.issued_by or "") if x),
            "trud.req_patent": " ".join(x for x in (
                (patent.series if patent else "") or "",
                (patent.number if patent else "") or "") if x),
            "trud.req_patent_issued": " ".join(x for x in (
                _date_dmy(patent.issue_date) if patent and patent.issue_date else "",
                (patent.issued_by if patent else "") or "") if x),
            "trud.sign_fio": f"{_title(passport.surname)} {initials}".strip(),
        }
        for part, text in (("day", f"{form_date.day:02d}"),
                           ("month", _MONTHS_GEN[form_date.month - 1]),
                           ("year", f"{form_date.year:04d}")):
            values[f"trud.contract_date_{part}"] = text
            values[f"trud.sign_date_{part}"] = text
        return values

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


def _copy_stamp(source: Path | None, dest: Path) -> Path | None:
    """Keep the печать beside the templates it is stamped onto.

    The operator picks it off their desktop; the file has to survive that
    folder being tidied up.
    """
    if source is None:
        return None
    if not source.exists():
        raise ValidationError("Печать файли топилмади", context={"path": str(source)})
    kept = dest / f"stamp{source.suffix.lower()}"
    if source.resolve() != kept.resolve():
        shutil.copyfile(source, kept)
    return kept


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in " _-" else "_" for c in name).strip() or "firm"


def _unique(candidate: Path) -> Path:
    base, i = candidate, 1
    while candidate.exists():
        candidate = base.with_name(f"{base.stem}_{i:03d}{base.suffix}")
        i += 1
    return candidate
