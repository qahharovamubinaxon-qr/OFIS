"""РАСМ-ФОТО: turn a casual worker photo into a document-standard 3×4.

Pipeline (all offline and free):
1. EXIF-orient and decode.
2. Detect the face with YuNet (bundled ONNX model, works on any OpenCV ≥4.8).
   Its eye landmarks give the head tilt — the image is rotated straight.
3. Crop a 3:4 portrait around the face with document proportions (head ≈ 65%
   of frame, 12–18% air above the head).
4. Separate the person from the background with U²-Net
   (:mod:`src.services.bg_segment`) and repaint the background in the chosen
   colour (white / light grey / blue). No model yet → edge flood-fill
   whitening, so the feature never depends on a download.
5. Output 413×531 px (3×4 cm at 300 DPI) PNG.

If no face is found the photo is centre-cropped to 3:4 without background
cleanup, so the operator always gets a usable result.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass

from src.common.logging import get_logger
from src.config import paths

log = get_logger(__name__)

OUT_W, OUT_H = 413, 531  # 3×4 cm at 300 DPI
OUT_DPI = 300

# document backdrop colours the operator can pick from
BG_COLORS: dict[str, tuple[int, int, int]] = {
    "white": (255, 255, 255),
    "gray": (235, 235, 235),
    "blue": (99, 140, 190),
    # «studio» is not a flat colour — see _studio_backdrop. The entry is here
    # so the rest of the pipeline can treat it like any other choice, and so a
    # caller that cannot build the gradient still gets a sensible grey.
    "studio": (222, 222, 222),
}

#: The seamless light-grey sweep a portrait studio actually has behind the
#: sitter: brightest just behind the head, falling off gently to the corners.
#:
#: This is a **backdrop**, not a filter. It is painted only where the person is
#: not — the face, the hair and the clothes come through the segmentation mask
#: untouched, pixel for pixel. That distinction is the whole point: the photo
#: goes on a патент, a бейджик and a разрешение, where an inspector holds the
#: card up against the worker's own face, so nothing about the person may be
#: redrawn, softened or invented. Only what is behind them changes.
STUDIO_HI = 240          # behind the head
STUDIO_LO = 196          # into the corners
STUDIO_CENTRE = (0.50, 0.30)   # (x, y) of the bright spot, as a share of frame
STUDIO_FALLOFF = 1.25    # >1 keeps the middle open and darkens late
#: A soft contact shadow cast onto the backdrop, which is what separates the
#: shoulders from the sweep in a real studio frame.
STUDIO_SHADOW = 0.16
STUDIO_SHADOW_OFFSET = (0.020, 0.014)   # (x, y), as a share of frame


@dataclass(frozen=True)
class PhotoResult:
    png: bytes
    face_found: bool
    note: str = ""


def _load_rgb(data: bytes):
    """bytes → RGB numpy array, EXIF rotation applied."""
    import numpy as np
    from PIL import Image, ImageOps

    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img).convert("RGB")
    if max(img.size) > 2000:  # keep detection + grabcut fast
        img.thumbnail((2000, 2000))
    return np.asarray(img)


def _encode_png(rgb) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format="PNG", dpi=(OUT_DPI, OUT_DPI))
    return buf.getvalue()


_STUDIO_PROMPT = (
    "Сделай студийное профессиональное фото на документы в формате 3:4. "
    "Фон чисто белый. Человек одет в чёрную футболку. Человек смотрит прямо "
    "в камеру, голова ровно, плечи ровные. Освещение мягкое студийное. "
    "Лицо человека не менять — сохранить полное сходство."
)


class PhotoService:
    def __init__(self, key_getter=None) -> None:
        self._key_getter = key_getter

    # -- AI studio edit (Gemini image model); falls back to local pipeline --
    def _ai_studio(self, data: bytes) -> bytes | None:
        key = (self._key_getter() if self._key_getter else "") or ""
        if not key.strip():
            return None
        import base64
        import json
        import urllib.error
        import urllib.request

        img_b64 = base64.b64encode(data).decode()
        body = json.dumps({
            "contents": [{"parts": [
                {"text": _STUDIO_PROMPT},
                {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}},
            ]}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
        }).encode()
        models = ["gemini-3-pro-image-preview", "gemini-2.5-flash-image",
                  "gemini-2.5-flash-image-preview",
                  "gemini-2.0-flash-preview-image-generation"]
        # discover any image-capable model this key actually has
        try:
            with urllib.request.urlopen(
                "https://generativelanguage.googleapis.com/v1beta/models?key="
                + key.strip(), timeout=20
            ) as resp:
                listing = json.loads(resp.read().decode())
            for m in listing.get("models", []):
                name = m.get("name", "").split("/")[-1]
                if "image" in name and "generateContent" in m.get(
                    "supportedGenerationMethods", []
                ) and name not in models:
                    models.append(name)
        except Exception:  # noqa: BLE001
            pass
        self._last_error = ""
        for model in models:
            url = ("https://generativelanguage.googleapis.com/v1beta/models/"
                   f"{model}:generateContent?key={key.strip()}")
            req = urllib.request.Request(
                url, data=body, headers={"Content-Type": "application/json"}
            )
            try:
                import time
                try:
                    with urllib.request.urlopen(req, timeout=90) as resp:
                        payload = json.loads(resp.read().decode())
                except urllib.error.HTTPError as he:
                    if he.code == 429:  # free-tier rate limit — wait and retry
                        time.sleep(35)
                        with urllib.request.urlopen(
                            urllib.request.Request(url, data=body,
                                headers={"Content-Type": "application/json"}),
                            timeout=90,
                        ) as resp:
                            payload = json.loads(resp.read().decode())
                    else:
                        raise
                for cand in payload.get("candidates", []):
                    for part in cand.get("content", {}).get("parts", []):
                        inline = part.get("inlineData") or part.get("inline_data")
                        if inline and inline.get("data"):
                            log.info("Studio photo via %s", model)
                            return base64.b64decode(inline["data"])
            except Exception as exc:  # noqa: BLE001 - try next model
                self._last_error = str(exc)[:120]
                log.info("Studio model %s unavailable: %s", model, exc)
        return None

    def _detector(self, cv2, w: int, h: int):
        model = paths.resources_dir() / "models" / "face_detection_yunet.onnx"
        if not model.exists():
            return None
        try:
            det = cv2.FaceDetectorYN.create(str(model), "", (w, h), 0.6, 0.3, 5000)
            det.setInputSize((w, h))
            return det
        except cv2.error:
            log.warning("YuNet unavailable — falling back to centre crop")
            return None

    def _detect_face(self, cv2, rgb):
        """Largest face → (x, y, w, h, right_eye, left_eye) or None."""
        import numpy as np

        det = self._detector(cv2, rgb.shape[1], rgb.shape[0])
        if det is None:
            return None
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        _, faces = det.detect(bgr)
        if faces is None or len(faces) == 0:
            return None
        f = max(faces, key=lambda r: r[2] * r[3])
        x, y, w, h = (float(v) for v in f[:4])
        right_eye = (float(f[4]), float(f[5]))
        left_eye = (float(f[6]), float(f[7]))
        return x, y, w, h, right_eye, left_eye

    def process(self, data: bytes, bg: str = "white") -> PhotoResult:
        import cv2

        # 1) AI studio edit when a Gemini key is available — professional
        #    quality; the local pipeline stays as offline fallback.
        studio = self._ai_studio(data) if bg == "white" else None
        if studio is not None:
            rgb = _load_rgb(studio)
            found = self._detect_face(cv2, rgb)
            if found is not None:
                x, y, w, h, *_ = found
                crop = self._document_crop(cv2, rgb, x, y, w, h)
            else:
                crop = self._center_crop(cv2, rgb)
                return PhotoResult(png=_encode_png(crop), face_found=True, note="AI studio")
            crop = cv2.resize(crop, (OUT_W, OUT_H), interpolation=cv2.INTER_AREA)
            return PhotoResult(png=_encode_png(crop), face_found=True, note="AI studio")

        rgb = _load_rgb(data)
        found = self._detect_face(cv2, rgb)
        if found is None:
            log.info("Photo: no face found — centre crop only")
            return PhotoResult(
                png=_encode_png(self._center_crop(cv2, rgb)), face_found=False,
                note="Yuz topilmadi — rasm markazdan kesildi, fon o'zgartirilmadi.")

        x, y, w, h, right_eye, left_eye = found
        # -- straighten via the eye line ---------------------------------
        dx = left_eye[0] - right_eye[0]
        dy = left_eye[1] - right_eye[1]
        if abs(dx) > 5:
            angle = math.degrees(math.atan2(dy, dx))
            if 2.0 < abs(angle) < 25.0:
                center = (x + w / 2, y + h / 2)
                mat = cv2.getRotationMatrix2D(center, angle, 1.0)
                rgb = cv2.warpAffine(rgb, mat, (rgb.shape[1], rgb.shape[0]),
                                     flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
                redetected = self._detect_face(cv2, rgb)
                if redetected is not None:
                    x, y, w, h, *_ = redetected

        crop = self._document_crop(cv2, rgb, x, y, w, h)
        low_res = crop.shape[1] < OUT_W * 0.8  # upscaling would soften the result
        crop, method = self._apply_background(cv2, crop, bg)
        crop = cv2.resize(
            crop, (OUT_W, OUT_H),
            interpolation=cv2.INTER_LANCZOS4 if low_res else cv2.INTER_AREA)
        note = {"u2net": "U²-Net (lokal)", "flood": "Lokal usul"}.get(method, "Lokal usul")
        if low_res:
            note += " · rasm kichik — sifat pastroq bo'lishi mumkin"
        if getattr(self, "_last_error", ""):
            note += f" (AI: {self._last_error})"
        return PhotoResult(png=_encode_png(crop), face_found=True, note=note)

    # ------------------------------------------------------------------
    @staticmethod
    def _document_crop(cv2, rgb, x, y, w, h, aspect: float = OUT_W / OUT_H):
        """Window around the face at ``aspect`` (w/h), taken entirely from real
        pixels.

        The window is sized for document proportions (head ≈65% of the height,
        a little air above the hair), then shrunk and slid until it lies wholly
        inside the photo. Nothing is padded, so the portrait fills the frame
        evenly whatever shape the original was — a source narrower than the
        target simply yields a shorter window instead of white side bars.
        """
        H, W = float(rgb.shape[0]), float(rgb.shape[1])

        crop_h = h * 2.3
        crop_w = crop_h * aspect
        scale = min(1.0, W / crop_w, H / crop_h)   # keep the aspect exact
        crop_w, crop_h = crop_w * scale, crop_h * scale

        left = x + w / 2 - crop_w / 2              # centred on the face
        top = y - 0.42 * h                         # air above the hair
        left = max(0.0, min(left, W - crop_w))     # slide fully inside
        top = max(0.0, min(top, H - crop_h))

        x0, y0 = int(round(left)), int(round(top))
        x1 = min(rgb.shape[1], x0 + int(round(crop_w)))
        y1 = min(rgb.shape[0], y0 + int(round(crop_h)))
        return rgb[y0:y1, x0:x1]

    @staticmethod
    def _studio_backdrop(np, h: int, w: int):
        """The grey sweep, as a float32 H×W×3 image.

        An ellipse rather than a circle, so a 3:4 frame falls off at the same
        rate sideways as it does top to bottom and the sweep does not read as a
        vignette bolted onto a portrait.
        """
        cx, cy = STUDIO_CENTRE
        ys = (np.arange(h, dtype=np.float32)[:, None] / max(h - 1, 1) - cy) / 0.85
        xs = (np.arange(w, dtype=np.float32)[None, :] / max(w - 1, 1) - cx) / 0.72
        distance = np.clip(np.sqrt(xs * xs + ys * ys), 0.0, 1.0)
        level = STUDIO_HI - (STUDIO_HI - STUDIO_LO) * distance ** STUDIO_FALLOFF
        return np.repeat(level[..., None], 3, axis=2)

    @staticmethod
    def _cast_shadow(cv2, np, backdrop, alpha, h: int, w: int):
        """Darken the sweep where the sitter would shade it — background only."""
        blur = max(3, int(min(h, w) * 0.09) | 1)
        shadow = cv2.GaussianBlur(alpha[..., 0], (blur, blur), 0)
        dx = int(round(w * STUDIO_SHADOW_OFFSET[0]))
        dy = int(round(h * STUDIO_SHADOW_OFFSET[1]))
        shadow = np.roll(np.roll(shadow, dy, axis=0), dx, axis=1)
        if dy:
            shadow[:dy, :] = 0
        if dx:
            shadow[:, :dx] = 0
        return backdrop * (1.0 - STUDIO_SHADOW * shadow[..., None])

    @staticmethod
    def _apply_background(cv2, crop, bg: str = "white") -> tuple:
        """Repaint the backdrop in ``BG_COLORS[bg]``. U²-Net segmentation when
        the model is available; otherwise the flood-fill whitening.

        Returns ``(image, method)`` — method is "u2net", "flood" or "none".
        """
        import numpy as np

        from src.services.bg_segment import segment

        colour = BG_COLORS.get(bg, BG_COLORS["white"])
        h, w = crop.shape[:2]
        if h < 40 or w < 40:
            return crop, "none"

        mask = segment(crop)
        if mask is not None:
            share = float((mask > 128).mean())
            # sanity: the person must exist, not swallow the whole frame, and
            # the mask must actually cover the face area (centre-upper block)
            face_zone = mask[int(h * 0.25):int(h * 0.55), int(w * 0.35):int(w * 0.65)]
            if 0.15 < share < 0.97 and float(face_zone.mean()) > 128:
                person = cv2.morphologyEx(
                    mask, cv2.MORPH_CLOSE,
                    cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
                person = cv2.GaussianBlur(person, (5, 5), 0)
                alpha = person.astype(np.float32)[..., None] / 255.0
                if bg == "studio":
                    backdrop = PhotoService._studio_backdrop(np, h, w)
                    backdrop = PhotoService._cast_shadow(
                        cv2, np, backdrop, alpha, h, w)
                else:
                    backdrop = np.full_like(crop, 0, dtype=np.float32)
                    backdrop[..., 0], backdrop[..., 1], backdrop[..., 2] = colour
                out = crop.astype(np.float32) * alpha + backdrop * (1 - alpha)
                return out.astype("uint8"), "u2net"
            log.info("U²-Net mask rejected (share %.2f) — flood fill", share)

        if bg == "white":
            return PhotoService._whiten_backdrop(cv2, crop), "flood"
        # the flood fill can only whiten; tint its white afterwards
        whitened = PhotoService._whiten_backdrop(cv2, crop)
        white_zone = (whitened.astype(np.int16).min(axis=2) > 247)
        if bg == "studio":
            # no mask to cast a shadow from, so the sweep goes on alone — it is
            # still a studio backdrop, just without the contact shadow
            swept = whitened.copy()
            swept[white_zone] = PhotoService._studio_backdrop(
                np, h, w)[white_zone].astype("uint8")
            return swept, "flood"
        if colour != (255, 255, 255):
            tinted = whitened.copy()
            tinted[white_zone] = colour
            return tinted, "flood"
        return whitened, "flood"

    @staticmethod
    def _whiten_backdrop(cv2, crop):
        """Whiten ONLY the backdrop, leaving the person and their clothes intact.

        The backdrop is found by flooding inward from the top and the upper
        side edges with a colour tolerance: the fill spreads across the even
        studio background but stops at the hair, face and shoulders, so a dark
        jacket is never mistaken for background the way a blind GrabCut
        rectangle would. If the fill leaks over most of the frame (busy or
        dark background) the photo is returned untouched.
        """
        import numpy as np

        h, w = crop.shape[:2]
        if h < 40 or w < 40:
            return crop
        bgr = cv2.cvtColor(crop, cv2.COLOR_RGB2BGR)
        smooth = cv2.GaussianBlur(bgr, (5, 5), 0)

        mask = np.zeros((h + 2, w + 2), np.uint8)
        tol = (26, 26, 26)
        flags = 4 | cv2.FLOODFILL_MASK_ONLY | (255 << 8)
        step = max(3, w // 48)
        seeds = [(x, 0) for x in range(0, w, step)]
        seeds += [(x, 1) for x in range(0, w, step * 2)]
        # sides, upper two-thirds only — the shoulders own the lower band
        for y in range(0, int(h * 0.62), step):
            seeds += [(0, y), (w - 1, y)]
        for sx, sy in seeds:
            if mask[sy + 1, sx + 1] == 0:
                try:
                    cv2.floodFill(smooth, mask, (sx, sy), 255, tol, tol, flags)
                except cv2.error:
                    return crop

        back = mask[1:-1, 1:-1]
        share = float((back > 0).sum()) / (h * w)
        if share < 0.03 or share > 0.85:
            return crop  # nothing found, or the fill leaked into the person

        # close over thin strips the fill could not cross (a slightly different
        # shade of the same backdrop), then soften the silhouette edge
        back = cv2.morphologyEx(back, cv2.MORPH_CLOSE,
                                cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
        back = cv2.morphologyEx(back, cv2.MORPH_OPEN,
                                cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
        back = cv2.GaussianBlur(back, (7, 7), 0)
        alpha = back.astype(np.float32)[..., None] / 255.0
        white = np.full_like(crop, 255, dtype=np.float32)
        out = crop.astype(np.float32) * (1 - alpha) + white * alpha
        return out.astype("uint8")

    @staticmethod
    def _whiten_background(cv2, crop):
        """GrabCut the person, repaint the background white."""
        import numpy as np

        h, w = crop.shape[:2]
        if h < 40 or w < 40:
            return crop
        mask = np.full((h, w), cv2.GC_PR_BGD, dtype=np.uint8)
        # person: centre column from the hair line down
        cv2.rectangle(mask, (int(w * 0.18), int(h * 0.10)), (int(w * 0.82), h - 1),
                      int(cv2.GC_PR_FGD), -1)
        # face area is definitely person
        cv2.rectangle(mask, (int(w * 0.32), int(h * 0.18)), (int(w * 0.68), int(h * 0.52)),
                      int(cv2.GC_FGD), -1)
        # top corners are definitely background
        cv2.rectangle(mask, (0, 0), (int(w * 0.14), int(h * 0.16)), int(cv2.GC_BGD), -1)
        cv2.rectangle(mask, (int(w * 0.86), 0), (w - 1, int(h * 0.16)), int(cv2.GC_BGD), -1)
        bgr = cv2.cvtColor(crop, cv2.COLOR_RGB2BGR)
        try:
            bgd = np.zeros((1, 65), np.float64)
            fgd = np.zeros((1, 65), np.float64)
            cv2.grabCut(bgr, mask, None, bgd, fgd, 5, cv2.GC_INIT_WITH_MASK)
        except cv2.error:
            return crop
        person = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype("uint8")
        person = cv2.morphologyEx(person, cv2.MORPH_CLOSE,
                                  cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
        person = cv2.GaussianBlur(person, (5, 5), 0)
        alpha = person.astype(np.float32)[..., None] / 255.0
        white = np.full_like(crop, 255)
        out = (crop.astype(np.float32) * alpha + white.astype(np.float32) * (1 - alpha))
        return out.astype("uint8")

    @staticmethod
    def _center_crop(cv2, rgb, aspect: float = OUT_W / OUT_H, out=None):
        h, w = rgb.shape[:2]
        target = aspect
        if w / h > target:
            new_w = int(h * target)
            x0 = (w - new_w) // 2
            crop = rgb[:, x0:x0 + new_w]
        else:
            new_h = int(w / target)
            y0 = max(0, (h - new_h) // 4)  # bias toward the top (face usually there)
            crop = rgb[y0:y0 + new_h, :]
        return cv2.resize(crop, out or (OUT_W, OUT_H), interpolation=cv2.INTER_AREA)


def prepare_portrait(data: bytes, aspect: float = 0.75, height: int = 800) -> bytes | None:
    """Head-and-shoulders crop at ``aspect`` (width/height) on a white
    background, ready to drop into a document frame edge to edge.

    Runs the offline pipeline only (no cloud AI): YuNet face detection →
    eye-line straightening → document crop → U²-Net background removal (flood
    fill when the model is absent). Returns PNG bytes, or None when the image
    cannot be read.
    """
    try:
        import cv2
    except ImportError:  # pragma: no cover - cv2 ships with the app
        return None
    try:
        rgb = _load_rgb(data)
    except Exception:  # noqa: BLE001 - unreadable upload
        return None

    size = (max(60, int(height * aspect)), height)
    svc = PhotoService()
    found = svc._detect_face(cv2, rgb)
    if found is None:
        log.info("Portrait: no face found — centre crop to the frame")
        return _encode_png(svc._center_crop(cv2, rgb, aspect, size))

    x, y, w, h, right_eye, left_eye = found
    dx, dy = left_eye[0] - right_eye[0], left_eye[1] - right_eye[1]
    if abs(dx) > 5:
        angle = math.degrees(math.atan2(dy, dx))
        if 2.0 < abs(angle) < 25.0:
            mat = cv2.getRotationMatrix2D((x + w / 2, y + h / 2), angle, 1.0)
            rgb = cv2.warpAffine(rgb, mat, (rgb.shape[1], rgb.shape[0]),
                                 flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            again = svc._detect_face(cv2, rgb)
            if again is not None:
                x, y, w, h, *_ = again

    crop = svc._document_crop(cv2, rgb, x, y, w, h, aspect)
    crop, _method = svc._apply_background(cv2, crop, "white")
    crop = cv2.resize(crop, size, interpolation=cv2.INTER_AREA)
    return _encode_png(crop)
