"""Coordinates «шаблонни ўзи тушунадиган режим» for the UI.

Upload a form → study it → the operator confirms the map → it is remembered by
the file's contents, so the same document is never studied twice → uploading a
worker's documents fills it.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.common.logging import get_logger
from src.config import paths
from src.database.repositories.template_profile_repo import TemplateProfileRepository
from src.ocr.service import OcrService
from src.services import template_fill, template_study
from src.services.template_study import Study

log = get_logger(__name__)


@dataclass(frozen=True)
class SavedTemplate:
    """A template the operator already studied and confirmed on the computer.

    The remote front ends can only pick from these — studying a new form needs
    the confirmation table, which is a desktop job.
    """

    name: str
    kind: str
    path: Path


class TemplateController:
    def __init__(self, profiles: TemplateProfileRepository, ocr: OcrService) -> None:
        self._profiles = profiles
        self._ocr = ocr

    # ------------------------------------------------------------- studying
    def study(self, source: Path) -> tuple[Study, bool]:
        """The map for this file, and whether it came from an earlier session."""
        remembered = self._profiles.for_file(source)
        if remembered is not None:
            log.info("Template %s already studied — reusing its map", source.name)
            return remembered, True
        return template_study.study(source), False

    def remember(self, name: str, source: Path, study: Study) -> Path:
        """Keep the template and the confirmed map together, under the app data."""
        dest = paths.user_templates_dir() / "own" / source.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != dest.resolve():
            shutil.copyfile(source, dest)
        self._profiles.save(name or source.stem, dest, study)
        return dest

    def forget(self, source: Path) -> None:
        self._profiles.forget(source)

    def saved(self) -> list[tuple[str, str, Path]]:
        return self._profiles.list()

    def saved_templates(self) -> list[SavedTemplate]:
        """The same list, named — for the bot and the Mini App pickers."""
        return [SavedTemplate(name, kind, path)
                for name, kind, path in self._profiles.list()
                if path.exists()]

    # -------------------------------------------------------------- filling
    def ai_available(self) -> bool:
        return self._ocr.available()

    def fill_from_images(self, study: Study, template: Path, out: Path,
                         passport_image: bytes, patent_image: bytes | None = None,
                         *, form_date: date | None = None,
                         profession: str = "") -> template_fill.FillResult:
        passport, patent = self._ocr.read_documents(passport_image, patent_image)
        values = template_fill.values_for(passport, patent, form_date=form_date,
                                          profession=profession)
        result = template_fill.fill(study, template, out, values)
        if passport.mrz_warning:
            result.problems.append(passport.mrz_warning)
        return result

    @staticmethod
    def fields() -> list[tuple[str, str]]:
        """Every value the office can put on a document — for the picker."""
        return [(key, label) for key, label, _a in template_study.FIELDS]

    @staticmethod
    def read_image(path: Path) -> bytes:
        return path.read_bytes()
