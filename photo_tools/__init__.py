"""photo_tools — OFIS 24/7 «РАСМ-ФОТО» bo'limi uchun rasm/hujjat qayta ishlash yadrosi.

Public API:
    person_photo.make_person_photo(...)   -> PersonPhotoResult (photo, sheet)
    person_photo.save_sheet_pdf(...)
    docscan.scan_document(...)            -> list[ScannedPage]
    docscan.layout_a4(...)                -> PDF + preview PNG
"""
from .person_photo import (
    PersonPhotoResult,
    make_person_photo,
    make_sheet,
    save_sheet_pdf,
    BACKGROUNDS,
    PHOTO_SIZES,
)
from .docscan import (
    ScannedPage,
    scan_document,
    layout_a4,
    DOC_PRESETS,
    COLOR_MODES,
)
from .models import ensure_models, models_status

__all__ = [
    "PersonPhotoResult", "make_person_photo", "make_sheet", "save_sheet_pdf",
    "BACKGROUNDS", "PHOTO_SIZES",
    "ScannedPage", "scan_document", "layout_a4", "DOC_PRESETS", "COLOR_MODES",
    "ensure_models", "models_status",
]
__version__ = "1.0.0"
