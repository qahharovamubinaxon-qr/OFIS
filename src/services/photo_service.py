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
        import urllib.request

        img_b64 = base64.b64encode(data).decode()
        body = json.dumps({
            "contents": [{"parts": [
                {"text": _STUDIO_PROMPT},
                {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}},
            ]}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
        }).encode()
        for model in ("gemini-2.5-flash-image", "gemini-2.5-flash-image-preview",
                      "gemini-2.0-flash-preview-image-generation"):
            url = ("https://generativelanguage.googleapis.com/v1beta/models/"
                   f"{model}:generateContent?key={key.strip()}")
            req = urllib.request.Request(
                url, data=body, headers={"Content-Type": "application/json"}
            )
            try:
                with urllib.request.urlopen(req, timeout=90) as resp:
                    payload = json.loads(resp.read().decode())
                for cand in payload.get("candidates", []):
                    for part in cand.get("content", {}).get("parts", []):
                        inline = part.get("inlineData") or part.get("inline_data")
                        if inline and inline.get("data"):
                            log.info("Studio photo via %s", model)
                            return base64.b64decode(inline["data"])
            except Exception as exc:  # noqa: BLE001 - try next model
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
                return PhotoResult(png=_encode_png(crop), face_found=True)
            crop = cv2.resize(crop, (OUT_W, OUT_H), interpolation=cv2.INTER_AREA)
            return PhotoResult(png=_encode_png(crop), face_found=True)

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
        crop = self._whiten_background(cv2, crop)
        crop = cv2.resize(crop, (OUT_W, OUT_H), interpolation=cv2.INTER_AREA)
        return PhotoResult(png=_encode_png(crop), face_found=True)

    # ------------------------------------------------------------------
    @staticmethod
    def _document_crop(cv2, rgb, x, y, w, h):
        """3:4 window around the face: head ≈60% of height, air above hair."""
        H, W = rgb.shape[:2]
        crop_h = h * 2.4
        crop_w = crop_h * 0.75
        top = y - 0.5 * h
        left = x + w / 2 - crop_w / 2
        pad = int(max(0.0, -left, -top, left + crop_w - W, top + crop_h - H)) + 1
        if pad > 1:
            rgb = cv2.copyMakeBorder(rgb, pad, pad, pad, pad, cv2.BORDER_REPLICATE)
            left += pad
            top += pad
        x0, y0 = int(max(0, left)), int(max(0, top))
        return rgb[y0:y0 + int(crop_h), x0:x0 + int(crop_w)]

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
    def _center_crop(cv2, rgb):
        h, w = rgb.shape[:2]
        target = 3 / 4
        if w / h > target:
            new_w = int(h * target)
            x0 = (w - new_w) // 2
            crop = rgb[:, x0:x0 + new_w]
        else:
            new_h = int(w / target)
            y0 = max(0, (h - new_h) // 4)  # bias toward the top (face usually there)
            crop = rgb[y0:y0 + new_h, :]
        return cv2.resize(crop, (OUT_W, OUT_H), interpolation=cv2.INTER_AREA)
