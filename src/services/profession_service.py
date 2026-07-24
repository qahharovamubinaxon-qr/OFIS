"""Profession use-cases for the СФЕРА module: list, add, first-run seed."""

from __future__ import annotations

from src.common.logging import get_logger
from src.database.repositories.profession_repo import ProfessionRepository
from src.domain.profession import Profession

log = get_logger(__name__)

# The five professions the training centre currently certifies (from the samples).
_SEED = [
    ("Арматурщик", None),
    ("Электрогазосварщик", "аргонодуговая"),
    ("Бетонщик", None),
    ("Монтажник по монтажу стальных и железобетонных конструкций", None),
    ("Монтажник технологических трубопроводов", None),
]


class ProfessionService:
    def __init__(self, repo: ProfessionRepository) -> None:
        self._repo = repo

    def list(self) -> list[Profession]:
        return self._repo.list_active()

    def count(self) -> int:
        return self._repo.count()

    def add(self, name: str, note: str | None = None, grade: int = 5) -> Profession:
        p = Profession(name=name, note=note or None, grade=grade)
        self._repo.add(p, sort_order=self._repo.count())
        log.info("Profession added: %s", name)
        return p

    def seed_defaults(self) -> None:
        if self._repo.count() > 0:
            return
        for i, (name, note) in enumerate(_SEED):
            self._repo.add(Profession(name=name, note=note), sort_order=i)
        log.info("Seeded %d default professions", len(_SEED))
