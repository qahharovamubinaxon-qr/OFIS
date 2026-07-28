"""Enumerations shared across the domain. Values mirror the МВД form choices."""

from __future__ import annotations

from enum import StrEnum


class DocType(StrEnum):
    PASSPORT = "passport"
    PATENT = "patent"
    REGISTRATION = "registration"
    MIGRATION_CARD = "migration_card"
    STS = "sts"  # свидетельство о регистрации ТС
    DRIVER_LICENCE = "driver_licence"  # водительское удостоверение
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


class LegalForm(StrEnum):
    """How a Трудовой firm signs: as a company or as the предприниматель."""

    OOO = "ooo"  # юридическое лицо — ОГРН, КПП, «в лице директора»
    IP = "ip"  # индивидуальный предприниматель — ОГРНИП, без КПП


class CompanyStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"
    DELETED = "deleted"


class GeneratedStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"
