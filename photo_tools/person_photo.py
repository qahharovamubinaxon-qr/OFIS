"""Odam rasmi: fonni olib tashlash → yuzni tiklash → 3×4 / 3.5×4.5 kesish → varaq (3×2) → PDF/PNG.

Foydalanish:
    res = make_person_photo("foto.jpg", size="35x45", background="white", enhance_face=True)
    res.photo.save("rasm.png")            # bitta rasm (RGBA agar background="transparent")
    save_sheet_pdf(res.sheet_pdf_items, "rasm_6ta.pdf")
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from .models import GFPGAN_PATH, _install_basicsr_shim

DPI = 600
MM = DPI / 25.4

PHOTO_SIZES = {          # nom → (eni_mm, bo'yi_mm)
    "30x40": (30.0, 40.0),
    "35x45": (35.0, 45.0),
    "40x50": (40.0, 50.0),
    "50x50": (50.0, 50.0),
}

BACKGROUNDS = {          # nom → RGB yoki None (shaffof)
    "white": (255, 255, 255),
    "lightgray": (235, 235, 235),
    "blue": (172, 205, 240),
    "studio": "studio",          # yumshoq gradient
    "transparent": None,
}

ImageLike = Union[str, Path, Image.Image, np.ndarray]


# ----------------------------------------------------------------------------- yordamchi

def _load(img: ImageLike) -> Image.Image:
    if isinstance(img, Image.Image):
        p = img
    elif isinstance(img, np.ndarray):
        p = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    else:
        p = Image.open(img)
    p = ImageOps.exif_transpose(p)
    return p.convert("RGB")


_face_cascade = None


def _detect_face(rgb: np.ndarray) -> Optional[tuple[int, int, int, int]]:
    """Eng katta yuzni qaytaradi (x, y, w, h) yoki None."""
    global _face_cascade
    if _face_cascade is None:
        _face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.equalizeHist(gray)
    faces = _face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(max(30, gray.shape[0] // 12),) * 2)
    if len(faces) == 0:
        return None
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    return int(x), int(y), int(w), int(h)


def _crop_for_document(p: Image.Image, ratio: float, face_h_frac=0.45, face_cy_frac=0.45) -> Image.Image:
    """Yuz bo'yicha hujjat standartiga mos kesish. ratio = eni/bo'yi.
    Yuz (Haar box) balandligi rasm balandligining ~50% (bosh ~72%), yuz markazi tepadan 46%."""
    rgb = np.asarray(p)
    H0, W0 = rgb.shape[:2]
    face = _detect_face(rgb)
    if face is None:
        # yuz topilmadi — markazdan maksimal kesish
        if W0 / H0 > ratio:
            h = H0; w = int(h * ratio)
        else:
            w = W0; h = int(w / ratio)
        x0, y0 = (W0 - w) // 2, (H0 - h) // 2
        return p.crop((x0, y0, x0 + w, y0 + h))

    x, y, w, h = face
    cx, cy = x + w / 2, y + h / 2
    crop_h = h / face_h_frac
    crop_w = crop_h * ratio
    x0, y0 = cx - crop_w / 2, cy - face_cy_frac * crop_h
    box = (int(round(x0)), int(round(y0)), int(round(x0 + crop_w)), int(round(y0 + crop_h)))
    # rasm chegarasidan chiqsa — oq bilan to'ldirib kengaytiramiz (keyin fon baribir almashadi)
    pad_l, pad_t = max(0, -box[0]), max(0, -box[1])
    pad_r, pad_b = max(0, box[2] - W0), max(0, box[3] - H0)
    if any((pad_l, pad_t, pad_r, pad_b)):
        edge = tuple(int(v) for v in np.median(rgb[0], axis=0))  # tepadagi qator rangi (odatda fon)
        p = ImageOps.expand(p, (pad_l, pad_t, pad_r, pad_b), fill=edge)
        box = (box[0] + pad_l, box[1] + pad_t, box[2] + pad_l, box[3] + pad_t)
    return p.crop(box)


# ----------------------------------------------------------------------------- AI bosqichlari

_rembg_session = None


def remove_background(p: Image.Image) -> Image.Image:
    """rembg (u2net_human_seg) + alpha matting → RGBA."""
    global _rembg_session
    from rembg import new_session, remove
    if _rembg_session is None:
        _rembg_session = new_session("u2net_human_seg")
    return remove(
        p, session=_rembg_session, alpha_matting=True,
        alpha_matting_foreground_threshold=240, alpha_matting_background_threshold=15,
        alpha_matting_erode_size=8,
    ).convert("RGBA")


_gfpgan = None


def enhance_face(p: Image.Image, weight: float = 0.5) -> Image.Image:
    """GFPGAN v1.4 bilan yuzni tiklash. weight 0..1 (0.3–0.5 hujjat uchun tavsiya).
    Model/torch bo'lmasa — yumshoq keskinlashtirish bilan qaytadi (xatosiz)."""
    global _gfpgan
    if not GFPGAN_PATH.exists():
        return p.filter(ImageFilter.UnsharpMask(radius=1.5, percent=90, threshold=3))
    try:
        if _gfpgan is None:
            _install_basicsr_shim()
            from gfpgan import GFPGANer
            # facexlib og'irliklarini joriy papkaga emas, MODELS_DIR ga yuklashi uchun
            import os
            cwd = os.getcwd()
            os.chdir(GFPGAN_PATH.parent)
            try:
                _gfpgan = GFPGANer(model_path=str(GFPGAN_PATH), upscale=1, arch="clean",
                                   channel_multiplier=2, bg_upsampler=None)
            finally:
                os.chdir(cwd)
        bgr = cv2.cvtColor(np.asarray(p.convert("RGB")), cv2.COLOR_RGB2BGR)
        _, _, out = _gfpgan.enhance(bgr, has_aligned=False, only_center_face=True,
                                    paste_back=True, weight=weight)
        return Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))
    except Exception:
        return p.filter(ImageFilter.UnsharpMask(radius=1.5, percent=90, threshold=3))


def _clean_edges(p: Image.Image) -> Image.Image:
    """Telefon suratidagi shovqinni yo'qotib, yengil keskinlashtirish (kiyim/soch uchun)."""
    bgr = cv2.cvtColor(np.asarray(p.convert("RGB")), cv2.COLOR_RGB2BGR)
    bgr = cv2.fastNlMeansDenoisingColored(bgr, None, 3, 3, 7, 21)
    out = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    return out.filter(ImageFilter.UnsharpMask(radius=1.2, percent=70, threshold=3))


def _make_background(size: tuple[int, int], background: str) -> Image.Image:
    W, H = size
    spec = BACKGROUNDS[background]
    if spec is None:
        return Image.new("RGBA", size, (0, 0, 0, 0))
    if spec == "studio":
        y = np.linspace(0, 1, H)[:, None]
        x = np.linspace(-1, 1, W)[None, :]
        base = 246 - 22 * y - 10 * (x ** 2)           # tepada ochroq, pastda va chetlarda salgina to'qroq
        arr = np.repeat(np.clip(base, 0, 255)[..., None], 3, axis=2).astype(np.uint8)
        return Image.fromarray(arr).convert("RGBA")
    return Image.new("RGBA", size, spec + (255,))


def compose(rgba: Image.Image, background: str) -> Image.Image:
    bg = _make_background(rgba.size, background)
    bg.alpha_composite(rgba)
    return bg if BACKGROUNDS[background] is None else bg.convert("RGB")


# ----------------------------------------------------------------------------- varaq

def _corner_cut(p: Image.Image, cut_w_frac=0.47, cut_h_frac=0.29) -> Image.Image:
    """Pastki chap burchakni diagonal kesish (hujjat obrazetsi kabi). Ramka to'liq qoladi."""
    p = p.convert("RGB").copy()
    W, H = p.size
    d = ImageDraw.Draw(p)
    d.polygon([(0, H - int(H * cut_h_frac)), (int(W * cut_w_frac), H), (0, H)], fill=(255, 255, 255))
    return p


def _with_border(p: Image.Image, color=(60, 60, 60), width=3) -> Image.Image:
    p = p.convert("RGB").copy()
    ImageDraw.Draw(p).rectangle([0, 0, p.width - 1, p.height - 1], outline=color, width=width)
    return p


@dataclass
class PersonPhotoResult:
    photo: Image.Image                     # yakuniy bitta rasm (RGB yoki RGBA)
    size_mm: tuple[float, float]
    sheet: Optional[Image.Image] = None    # 3×2 varaq (RGB, 600 dpi) — UI preview uchun
    sheet_pdf_items: list = field(default_factory=list)   # save_sheet_pdf uchun
    face_found: bool = True
    face_enhanced: bool = False


def make_sheet(photo: Image.Image, size_mm: tuple[float, float], cols=3, rows=2,
               gap_mm=3.0, margin_mm=5.0, corner_cut=True, border=True) -> tuple[Image.Image, list]:
    """Bir xil rasmdan cols×rows varaq. Qaytaradi: (PIL varaq, reportlab uchun elementlar)."""
    w_mm, h_mm = size_mm
    cell = photo.convert("RGB").resize((int(w_mm * MM), int(h_mm * MM)), Image.LANCZOS)
    if corner_cut:
        cell = _corner_cut(cell)
    if border:
        cell = _with_border(cell)
    SW = int((2 * margin_mm + cols * w_mm + (cols - 1) * gap_mm) * MM)
    SH = int((2 * margin_mm + rows * h_mm + (rows - 1) * gap_mm) * MM)
    sheet = Image.new("RGB", (SW, SH), (255, 255, 255))
    items = []
    for r in range(rows):
        for c in range(cols):
            x_mm = margin_mm + c * (w_mm + gap_mm)
            y_mm = margin_mm + r * (h_mm + gap_mm)
            sheet.paste(cell, (int(x_mm * MM), int(y_mm * MM)))
            items.append((cell, x_mm, y_mm, w_mm, h_mm))
    return sheet, {"items": items, "page_mm": (SW / MM, SH / MM)}


def save_sheet_pdf(sheet_pdf_items: dict, out_pdf: Union[str, Path], title="Rasm") -> Path:
    """Varaqni aniq mm o'lchamda PDF qilib saqlaydi (chop etganda 100% masshtab)."""
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    PW, PH = sheet_pdf_items["page_mm"]
    c = canvas.Canvas(str(out_pdf), pagesize=(PW * mm, PH * mm))
    c.setTitle(title)
    for cell, x, y, w, h in sheet_pdf_items["items"]:
        c.drawImage(ImageReader(cell), x * mm, (PH - y - h) * mm, w * mm, h * mm)
    c.showPage()
    c.save()
    return Path(out_pdf)


# ----------------------------------------------------------------------------- asosiy

def make_person_photo(
    src: ImageLike,
    size: str = "35x45",
    background: str = "white",
    enhance_face: bool = True,
    face_weight: float = 0.5,
    make_grid: bool = True,
    cols: int = 3,
    rows: int = 2,
    corner_cut: bool = True,
    border: bool = True,
    progress=None,
) -> PersonPhotoResult:
    """To'liq quvur: yuklash → yuz bo'yicha kesish → yuz tiklash → fon olib tashlash → fon → varaq.

    size:        PHOTO_SIZES kaliti ("30x40", "35x45", ...)
    background:  BACKGROUNDS kaliti ("white", "lightgray", "blue", "studio", "transparent")
    progress:    ixtiyoriy callback(str) — UI status uchun
    """
    say = progress or (lambda s: None)
    w_mm, h_mm = PHOTO_SIZES[size]
    ratio = w_mm / h_mm
    target = (int(w_mm * MM), int(h_mm * MM))

    say("Rasm yuklanmoqda…")
    p = _load(src)

    say("Yuz aniqlanmoqda va kesilmoqda…")
    face_found = _detect_face(np.asarray(p)) is not None
    crop = _crop_for_document(p, ratio)
    crop = crop.resize(target, Image.LANCZOS)
    crop = _clean_edges(crop)

    enhanced = False
    if enhance_face:
        say("Yuz tiklanmoqda (AI)…")
        before = crop
        crop = enhance_face_fn(crop, face_weight)
        enhanced = crop is not before

    say("Fon olib tashlanmoqda…")
    rgba = remove_background(crop)

    say("Fon qo'yilmoqda…")
    photo = compose(rgba, background)

    result = PersonPhotoResult(photo=photo, size_mm=(w_mm, h_mm),
                               face_found=face_found, face_enhanced=enhanced)
    if make_grid:
        say("Varaq yig'ilmoqda…")
        grid_src = compose(rgba, "white") if BACKGROUNDS[background] is None else photo
        result.sheet, result.sheet_pdf_items = make_sheet(
            grid_src, (w_mm, h_mm), cols, rows, corner_cut=corner_cut, border=border)
    say("Tayyor")
    return result


enhance_face_fn = enhance_face  # make_person_photo ichidagi parametr nomi bilan to'qnashmasligi uchun
