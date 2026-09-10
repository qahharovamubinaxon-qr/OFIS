"""Hujjat skaneri: telefon surati → hujjatni topish → perspektivadan to'g'rilash →
skaner ko'rinishi (tekis yoritish, oq qog'oz, keskin matn) → A4 markaziga standart o'lchamda.

Foydalanish:
    pages = scan_document("pasport.jpg", preset="passport_spread", color="color")
    pages += scan_document("karta_orqa.jpg", preset="id_card")
    layout_a4(pages, "natija.pdf", preview_png="natija_preview.png")
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

import cv2
import numpy as np
from PIL import Image, ImageFilter, ImageOps

DPI = 600
MM = DPI / 25.4

# preset → (eni_mm, bo'yi_mm) yoki None (avto: aniqlangan nisbat saqlanadi)
DOC_PRESETS = {
    "id_card": (85.6, 54.0),          # ID-1: patent, ID-karta, haydovchilik guvohnomasi, bank kartasi
    "passport_page": (125.0, 88.0),   # bitta pasport sahifasi
    "passport_spread": (125.0, None), # ochiq pasport (2 sahifa) — buklanishdan bo'linadi
    "a4": (210.0, 297.0),
    "a5": (148.0, 210.0),
    "auto": None,                     # nisbat saqlanadi, eni A4 ga sig'adigan qilib
}
COLOR_MODES = ("color", "gray", "bw")

ImageLike = Union[str, Path, Image.Image, np.ndarray]


@dataclass
class ScannedPage:
    image: Image.Image                # 600 dpi, RGB
    width_mm: float
    height_mm: float
    label: str = ""


# ----------------------------------------------------------------------------- yordamchi

def _load_bgr(img: ImageLike) -> np.ndarray:
    if isinstance(img, np.ndarray):
        return img
    p = img if isinstance(img, Image.Image) else Image.open(img)
    p = ImageOps.exif_transpose(p).convert("RGB")
    return cv2.cvtColor(np.asarray(p), cv2.COLOR_RGB2BGR)


def _order_quad(pts) -> np.ndarray:
    pts = np.asarray(pts, np.float32).reshape(-1, 2)
    s = pts.sum(1); d = np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]], np.float32)


def find_document(img: np.ndarray, min_area_frac: float = 0.12) -> Optional[np.ndarray]:
    """Qorong'i fondagi yorug' hujjatning 4 burchagini topadi (tl, tr, br, bl).
    Ikki usul: yorqinlik bo'yicha (Otsu) va chekkalar bo'yicha (Canny) — kattarog'i olinadi."""
    h, w = img.shape[:2]
    scale = 800 / max(h, w)
    small = cv2.resize(img, None, fx=scale, fy=scale)
    v = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2HSV)[..., 2], (7, 7), 0)
    _, th = cv2.threshold(v, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))

    edges = cv2.Canny(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), 40, 120)
    edges = cv2.dilate(edges, np.ones((5, 5), np.uint8))

    # Avval yorqinlik bo'yicha (qog'oz/karta — plyonka emas), topilmasa chekkalar bo'yicha
    for mask in (th, edges):
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cnts = [c for c in cnts if cv2.contourArea(c) >= min_area_frac * th.size]
        if not cnts:
            continue
        hull = cv2.convexHull(max(cnts, key=cv2.contourArea))
        peri = cv2.arcLength(hull, True)
        quad = None
        for eps in (0.02, 0.03, 0.05, 0.08):
            approx = cv2.approxPolyDP(hull, eps * peri, True)
            if len(approx) == 4:
                quad = approx; break
        if quad is None:
            quad = cv2.boxPoints(cv2.minAreaRect(hull))
        return _order_quad(np.asarray(quad, np.float32) / scale)
    return None


def _quad_size(q: np.ndarray) -> tuple[float, float]:
    w = (np.linalg.norm(q[1] - q[0]) + np.linalg.norm(q[2] - q[3])) / 2
    h = (np.linalg.norm(q[3] - q[0]) + np.linalg.norm(q[2] - q[1])) / 2
    return float(w), float(h)


def warp(img: np.ndarray, quad: np.ndarray, width_mm: float, height_mm: float, inset: float = 0.0) -> np.ndarray:
    W, H = int(round(width_mm * MM)), int(round(height_mm * MM))
    dst = np.array([[0, 0], [W, 0], [W, H], [0, H]], np.float32)
    M = cv2.getPerspectiveTransform(quad, dst)
    out = cv2.warpPerspective(img, M, (W, H), flags=cv2.INTER_LANCZOS4)
    if inset:
        ix, iy = int(W * inset), int(H * inset)
        out = cv2.resize(out[iy:H - iy, ix:W - ix], (W, H), interpolation=cv2.INTER_LANCZOS4)
    return out


def enhance_scan(img: np.ndarray, color: str = "color", sharpen: float = 1.0) -> Image.Image:
    """Skaner ko'rinishi. color: color | gray | bw."""
    # 1) yoritishni tekislash (qorong'i burchaklar, soyalar)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)
    L = lab[..., 0]
    bg = cv2.GaussianBlur(L, (0, 0), max(img.shape[:2]) / 12)
    lab[..., 0] = np.clip(L / (bg + 1e-3) * np.percentile(bg, 90), 0, 255)
    f = cv2.cvtColor(lab.astype(np.uint8), cv2.COLOR_LAB2BGR).astype(np.float32)
    # 2) oq balans — qog'ozning eng yorug' 20% pikseli neytral bo'lsin
    lum = f.mean(2); m = lum > np.percentile(lum, 80)
    ref = f[m].mean(0); f = np.clip(f * (ref.max() / ref), 0, 255)
    # 3) kontrast: qog'oz → oq, siyoh → qora
    lo, hi = np.percentile(f, 1), np.percentile(f, 97)
    f = np.clip((f - lo) / (hi - lo) * 255, 0, 255).astype(np.uint8)
    # 4) shovqin + keskinlik
    f = cv2.fastNlMeansDenoisingColored(f, None, 3, 3, 7, 21)
    p = Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
    p = p.filter(ImageFilter.UnsharpMask(radius=1.4, percent=int(110 * sharpen), threshold=2))
    if color == "gray":
        p = p.convert("L").convert("RGB")
    elif color == "bw":
        g = np.asarray(p.convert("L"))
        bw = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 51, 12)
        p = Image.fromarray(bw).convert("RGB")
    return p


def _find_fold(img: np.ndarray, quad: np.ndarray) -> Optional[int]:
    """Ochiq pasportda ikki sahifa orasidagi buklanish (eng qorong'i gorizontal chiziq) y-koordinatasi."""
    mask = np.zeros(img.shape[:2], np.uint8)
    cv2.fillPoly(mask, [quad.astype(int)], 255)
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    rows = np.array([g[y][mask[y] > 0].mean() if (mask[y] > 0).sum() > 50 else 255 for y in range(img.shape[0])])
    y0, y1 = int(img.shape[0] * 0.3), int(img.shape[0] * 0.7)
    seg = cv2.GaussianBlur(rows[y0:y1].reshape(-1, 1).astype(np.float32), (1, 0), 3).ravel()
    fy = y0 + int(np.argmin(seg))
    # buklanish haqiqatan qorong'i bo'lsa (o'rtacha yorqinlikdan ancha past)
    return fy if seg.min() < np.median(seg) - 12 else None


def _x_at(p1, p2, y):
    return p1[0] + (p2[0] - p1[0]) * (y - p1[1]) / (p2[1] - p1[1] + 1e-6)


# ----------------------------------------------------------------------------- asosiy

def scan_document(src: ImageLike, preset: str = "auto", color: str = "color",
                  label: str = "", inset: float = 0.004, progress=None) -> list[ScannedPage]:
    """Bitta suratdan 1 (yoki passport_spread uchun 2) ta tekislangan sahifa qaytaradi."""
    say = progress or (lambda s: None)
    say("Hujjat qidirilmoqda…")
    img = _load_bgr(src)
    quad = find_document(img)
    if quad is None:
        raise ValueError("Hujjat topilmadi — hujjatni to'q fonga qo'yib, to'liq kadrga oling")

    qw, qh = _quad_size(quad)
    pages: list[ScannedPage] = []

    if preset == "passport_spread":
        fy = _find_fold(img, quad)
        if fy is None:
            preset = "passport_page"          # buklanish yo'q — bitta sahifa deb qaraymiz
        else:
            tl, tr, br, bl = quad
            fl = np.array([_x_at(tl, bl, fy), fy], np.float32)
            fr = np.array([_x_at(tr, br, fy), fy], np.float32)
            for i, q in enumerate((np.array([tl, tr, fr, fl], np.float32), np.array([fl, fr, br, bl], np.float32))):
                w, h = _quad_size(q)
                Wmm = DOC_PRESETS["passport_spread"][0]
                Hmm = round(Wmm * h / w, 1)
                say(f"Sahifa {i + 1} tekislanmoqda…")
                flat = warp(img, q, Wmm, Hmm, inset=0.003)
                pages.append(ScannedPage(enhance_scan(flat, color), Wmm, Hmm, f"{label} {i + 1}".strip()))
            return pages

    spec = DOC_PRESETS.get(preset)
    if spec is None:                          # auto — nisbat saqlanadi
        landscape = qw >= qh
        Wmm = 190.0 if landscape else 190.0 * qw / qh
        Hmm = Wmm * qh / qw
        if Hmm > 277: Hmm, Wmm = 277.0, 277.0 * qw / qh
    else:
        Wmm, Hmm = spec
        if Hmm is None: Hmm = Wmm * qh / qw
        if (qw < qh) != (Wmm < Hmm):          # avto-orientatsiya
            Wmm, Hmm = Hmm, Wmm
    say("Tekislanmoqda…")
    flat = warp(img, quad, Wmm, Hmm, inset)
    say("Sifat yaxshilanmoqda…")
    pages.append(ScannedPage(enhance_scan(flat, color), Wmm, Hmm, label))
    return pages


def layout_a4(pages: list[ScannedPage], out_pdf: Union[str, Path], gap_mm: float = 12.0,
              border: bool = True, preview_png: Optional[Union[str, Path]] = None,
              preview_dpi: int = 150) -> Path:
    """Sahifalarni A4 markaziga vertikal ustma-ust joylaydi (old tepada, orqa pastda).
    Sig'masa — yangi A4 varaq ochiladi. preview_png berilsa, 1-varaq rasmi ham saqlanadi."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    PW, PH = A4
    usable = PH / mm - 20
    c = canvas.Canvas(str(out_pdf), pagesize=A4)

    # varaqlarga bo'lish
    sheets, cur, cur_h = [], [], 0.0
    for pg in pages:
        need = pg.height_mm + (gap_mm if cur else 0)
        if cur and cur_h + need > usable:
            sheets.append(cur); cur, cur_h = [], 0.0; need = pg.height_mm
        cur.append(pg); cur_h += need
    if cur: sheets.append(cur)

    preview = None
    for si, sheet in enumerate(sheets):
        total = sum(p.height_mm for p in sheet) + gap_mm * (len(sheet) - 1)
        y = (PH / mm + total) / 2
        if si == 0 and preview_png:
            s = preview_dpi / 25.4
            preview = Image.new("RGB", (int(210 * s), int(297 * s)), "white")
        for pg in sheet:
            x = (PW / mm - pg.width_mm) / 2; y -= pg.height_mm
            c.drawImage(ImageReader(pg.image), x * mm, y * mm, pg.width_mm * mm, pg.height_mm * mm)
            if border:
                c.setLineWidth(0.3); c.setStrokeColorRGB(0.6, 0.6, 0.6)
                c.rect(x * mm, y * mm, pg.width_mm * mm, pg.height_mm * mm)
            if preview is not None:
                s = preview_dpi / 25.4
                im = pg.image.resize((int(pg.width_mm * s), int(pg.height_mm * s)), Image.LANCZOS)
                preview.paste(im, (int(x * s), int((297 - y - pg.height_mm) * s)))
            y -= gap_mm
        c.showPage()
    c.save()
    if preview is not None:
        preview.save(preview_png)
    return Path(out_pdf)


def save_png(page: ScannedPage, out_png: Union[str, Path], transparent: bool = False) -> Path:
    """Bitta tekislangan sahifani PNG qilib saqlash (600 dpi metadata bilan)."""
    im = page.image
    im.save(out_png, dpi=(DPI, DPI))
    return Path(out_png)
