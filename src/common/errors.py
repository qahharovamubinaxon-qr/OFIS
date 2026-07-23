"""Typed exception hierarchy.

Every layer raises one of these so the presentation layer can map an error
*type* to a friendly, localized message without ever parsing text or leaking a
stack trace. Rule (see ARCHITECTURE.md §9): no bare ``except``, no silent
``pass``. Recoverable failures should prefer :class:`src.common.result.Result`;
exceptional ones raise a subclass of :class:`OfisError`.
"""

from __future__ import annotations


class OfisError(Exception):
    """Base class for every error the application raises deliberately.

    ``code`` is a stable, machine-readable identifier used to look up a
    localized user message; ``context`` carries structured detail for the log
    (never shown to the user).
    """

    code: str = "ofis.error"

    def __init__(self, message: str, *, context: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.context: dict[str, object] = context or {}


# --- user / input -----------------------------------------------------------
class UserError(OfisError):
    code = "user.error"


class MissingDocumentError(UserError):
    code = "user.missing_document"


class InvalidFileTypeError(UserError):
    code = "user.invalid_file_type"


class EmptyFileError(UserError):
    code = "user.empty_file"


# --- validation -------------------------------------------------------------
class ValidationError(OfisError):
    code = "validation.error"


class RequiredFieldMissingError(ValidationError):
    code = "validation.required_field_missing"


# --- ocr --------------------------------------------------------------------
class OcrError(OfisError):
    code = "ocr.error"


class UnreadableImageError(OcrError):
    code = "ocr.unreadable_image"


class LowConfidenceError(OcrError):
    code = "ocr.low_confidence"


class OcrTimeoutError(OcrError):
    code = "ocr.timeout"


# --- ai provider ------------------------------------------------------------
class AiError(OfisError):
    code = "ai.error"


class AiAuthError(AiError):
    code = "ai.auth_failed"


class AiQuotaError(AiError):
    code = "ai.quota_exceeded"


class AiRateLimitError(AiError):
    code = "ai.rate_limited"


class AiInvalidJsonError(AiError):
    code = "ai.invalid_json"


class AiUnavailableError(AiError):
    code = "ai.unavailable"


# --- pdf --------------------------------------------------------------------
class PdfError(OfisError):
    code = "pdf.error"


class TemplateMissingError(PdfError):
    code = "pdf.template_missing"


class TemplateCorruptedError(PdfError):
    code = "pdf.template_corrupted"


class FontMissingError(PdfError):
    code = "pdf.font_missing"


class MappingInvalidError(PdfError):
    code = "pdf.mapping_invalid"


class PdfWriteError(PdfError):
    code = "pdf.write_failed"


# --- database ---------------------------------------------------------------
class DatabaseError(OfisError):
    code = "db.error"


class DatabaseLockedError(DatabaseError):
    code = "db.locked"


class MigrationError(DatabaseError):
    code = "db.migration_failed"


# --- infrastructure ---------------------------------------------------------
class InfraError(OfisError):
    code = "infra.error"


class DiskFullError(InfraError):
    code = "infra.disk_full"


class PermissionDeniedError(InfraError):
    code = "infra.permission_denied"


class NetworkError(InfraError):
    code = "infra.network"


class ConfigError(InfraError):
    code = "infra.config"
