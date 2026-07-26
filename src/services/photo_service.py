"""РАСМ-ФОТО: turn a casual worker photo into a document-standard 3×4.

Pipeline (all offline):
1. EXIF-orient and decode.
2. Detect the face with YuNet (bundled ONNX model, works on any OpenCV ≥4.8).
   Its eye landmarks give the head tilt — the image is rotated straight.
3. Crop a 3:4 portrait around the face with document proportions (head ≈ 60%
   of frame, air above the hair).
4. GrabCut the person from the background and repaint the background pure
   white.
5. Output 600×800 PNG.

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

OUT_W, OUT_H = 600, 800  # 3:4


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
    Image.fromarray(rgb).save(buf, format="PNG")
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

    def process(self, data: bytes) -> PhotoResult:
        import cv2

        # 1) AI studio edit when a Gemini key is available — professional
        #    quality; the local pipeline stays as offline fallback.
        studio = self._ai_studio(data)
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
            return PhotoResult(png=_encode_png(self._center_crop(cv2, rgb)), face_found=False)

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
        crop = self._whiten_backdrop(cv2, crop)
        crop = cv2.resize(crop, (OUT_W, OUT_H), interpolation=cv2.INTER_AREA)
        note = "Lokal usul" + (f" (AI: {self._last_error})" if getattr(self, "_last_error", "") else "")
        return PhotoResult(png=_encode_png(crop), face_found=True, note=note)

    # ------------------------------------------------------------------
    @staticmethod
    def _document_crop(cv2, rgb, x, y, w, h, aspect: float = 0.75):
        """Window around the face at ``aspect`` (w/h): head ≈60% of the height,
        with air above the hair — the document-photo proportions."""
        H, W = rgb.shape[:2]
        crop_h = h * 2.4
        crop_w = crop_h * aspect
        top = y - 0.5 * h
        left = x + w / 2 - crop_w / 2
        pad = int(max(0.0, -left, -top, left + crop_w - W, top + crop_h - H)) + 1
        if pad > 1:
            # pad with white, not by replicating the edge — replication smears
            # the border pixels into visible streaks on a document photo
            rgb = cv2.copyMakeBorder(rgb, pad, pad, pad, pad,
                                     cv2.BORDER_CONSTANT, value=(255, 255, 255))
            left += pad
            top += pad
        x0, y0 = int(max(0, left)), int(max(0, top))
        return rgb[y0:y0 + int(crop_h), x0:x0 + int(crop_w)]

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
    def _center_crop(cv2, rgb, aspect: float = 0.75, out=None):
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

    Runs the offline pipeline only (no AI): YuNet face detection → eye-line
    straightening → document crop → GrabCut background whitening. Returns PNG
    bytes, or None when the image cannot be read.
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
    crop = svc._whiten_backdrop(cv2, crop)
    crop = cv2.resize(crop, size, interpolation=cv2.INTER_AREA)
    return _encode_png(crop)
