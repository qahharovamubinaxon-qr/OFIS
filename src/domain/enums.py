"""Enumerations shared across the domain. Values mirror the МВД form choices."""

from __future__ import annotations

from enum import StrEnum


class DocType(StrEnum):
    PASSPORT = "passport"
    PATENT = "patent"
    REGISTRATION = "registration"
    MIGRATION_CARD = "migration_card"
    UNKNOWN = "unknown"


class Gender(StrEnum):
    MALE = "male"
    FEMALE = "female"


class ContractType(StrEnum):
    """§3.3 of the form: трудовой / гражданско-правовой договор."""

    LABOR = "labor"
    CIVIL = "civil"


class EmployerType(StrEnum):
    """§1 status checkboxes on the МВД form."""

    LEGAL_ENTITY = "legal_entity"  # юридическое лицо
    IP = "ip"  # индивидуальный предприниматель
    LAWYER = "lawyer"  # адвокат, учредивший адвокатский кабинет
    INDIVIDUAL = "individual"  # физическое лицо — гражданин РФ
    OTHER_LICENSED = "other_licensed"
    FOREIGN_REP = "foreign_representation"
    FOREIGN_BRANCH = "foreign_branch"
    NOTARY = "private_notary"


class CompanyStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"
    DELETED = "deleted"


class GeneratedStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"
