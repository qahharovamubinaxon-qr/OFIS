"""РАСМ-ФОТО хизмати — `photo_tools` ядроси устидаги юпқа адаптер.

Расм/ҳужжат ишлаш мантиғи `photo_tools` пакетида (лойиҳа илдизида, вендор
нусха). Бу ерда фақат уланиш: юкланган байтларни quvурга бериш, PIL
натижаларни PNG байтга айлантириш, ва reportlab фаол PDF'ни вақтинчалик
файлдан ўқиб байт қилиб қайтариш. Ҳеч қандай расм мантиғи бу ерда
такрорланмайди — брифдаги талаб шу.

Оғир AI (torch/GFPGAN) ихтиёрий: йўқ бўлса `photo_tools` ўзи оддий
ўткирлашга тушиб, хатосиз ишлайверади.
"""

from __future__ import annotations

import io
import tempfile
from dataclasses import dataclass
from pathlib import Path

from src.common.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class PersonPhotoOutput:
    #: якуний битта ҳужжат расми (RGBA — фон «шаффоф» бўлса)
    photo_png: bytes
    #: 3×2 (ёки танланган) варақ — олдиндан кўриш ва сақлаш учун
    sheet_png: bytes
    #: чоп этишга тайёр варақ PDF (аниқ мм ўлчамда)
    pdf: bytes
    face_found: bool
    face_enhanced: bool


@dataclass(frozen=True)
class DocScanOutput:
    #: барча саҳифалар A4 марказида — битта PDF
    pdf: bytes
    #: 1-варақнинг расми — олдиндан кўриш учун
    preview_png: bytes
    #: ҳар текисланган саҳифа алоҳида PNG (керак бўлса алоҳида сақлаш учун)
    page_pngs: list[bytes]


def _to_image(data: bytes):
    """Юкланган байтлар → PIL Image (quvур PIL/ndarray/йўл қабул қилади)."""
    from PIL import Image

    return Image.open(io.BytesIO(data))


def _png(image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, "PNG")
    return buf.getvalue()


class PhotoLabService:
    """РАСМ-ФОТО экрани фақат шу хизмат орқали `photo_tools`га уланади."""

    # ------------------------------------------------------------- odam
    def person(self, data: bytes, *, size: str = "35x45",
               background: str = "white", enhance_face: bool = True,
               face_weight: float = 0.5, corner_cut: bool = True,
               border: bool = True, cols: int = 3, rows: int = 2,
               progress=None) -> PersonPhotoOutput:
        from photo_tools import make_person_photo, save_sheet_pdf

        res = make_person_photo(
            _to_image(data), size=size, background=background,
            enhance_face=enhance_face, face_weight=face_weight,
            make_grid=True, cols=cols, rows=rows, corner_cut=corner_cut,
            border=border, progress=progress)
        photo_png = _png(res.photo)
        sheet_png = _png(res.sheet) if res.sheet is not None else photo_png
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "sheet.pdf"
            save_sheet_pdf(res.sheet_pdf_items, out)
            pdf = out.read_bytes()
        return PersonPhotoOutput(
            photo_png=photo_png, sheet_png=sheet_png, pdf=pdf,
            face_found=res.face_found, face_enhanced=res.face_enhanced)

    # --------------------------------------------------------- hujjat
    def document(self, items: list[tuple[bytes, str]], *,
                 preset: str = "auto", color: str = "color",
                 progress=None) -> DocScanOutput:
        """items — (байт, ёрлиқ) жуфтлари: «old», «orqa». Ёрлиқ ихтиёрий."""
        from photo_tools import layout_a4, scan_document

        pages = []
        for data, label in items:
            pages += scan_document(_to_image(data), preset=preset,
                                   color=color, label=label, progress=progress)
        if not pages:
            raise ValueError("Ҳужжат топилмади — тўq фонга қўйиб, тўлиқ "
                             "кадрга олинг.")
        page_pngs = [_png(p.image) for p in pages]
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "doc.pdf"
            prev_path = Path(tmp) / "preview.png"
            layout_a4(pages, pdf_path, preview_png=prev_path)
            pdf = pdf_path.read_bytes()
            preview = prev_path.read_bytes()
        return DocScanOutput(pdf=pdf, preview_png=preview, page_pngs=page_pngs)

    # --------------------------------------------------------- models
    def models_status(self) -> dict:
        from photo_tools import models_status

        return models_status()

    def ensure_models(self, progress=None) -> dict:
        from photo_tools import ensure_models

        return ensure_models(progress=progress)
