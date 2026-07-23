"""Application-wide constants. No business/tunable values here — those live in
settings. Only things that are truly fixed for a given build.
"""

from __future__ import annotations

APP_NAME = "HR Document Automation System Pro"
APP_SHORT = "OFIS"
APP_VERSION = "0.1.0"
ORG_NAME = "OFIS"

SUPPORTED_LANGUAGES = ("ru", "uz", "en")
DEFAULT_LANGUAGE = "ru"

SUPPORTED_THEMES = ("dark", "light")
DEFAULT_THEME = "dark"

# Input formats the OCR pipeline accepts (see OCR_ENGINE.md).
SUPPORTED_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".tiff")
SUPPORTED_PDF_EXTS = (".pdf",)

DEFAULT_CONFIDENCE_THRESHOLD = 0.90
DEFAULT_OCR_TIMEOUT_S = 60
DEFAULT_AI_RETRIES = 3

A4_WIDTH_PT = 595.3
A4_HEIGHT_PT = 842.4
