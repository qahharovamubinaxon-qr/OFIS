"""Model og'irliklarini (GFPGAN, rembg) boshqarish — bir marta yuklab olinadi, keyin oflayn ishlaydi."""
from __future__ import annotations

import os
import sys
import types
import urllib.request
from pathlib import Path

MODELS_DIR = Path(os.environ.get("PHOTO_TOOLS_MODELS", Path.home() / ".ofis" / "models"))
GFPGAN_URL = "https://github.com/TencentARC/GFPGAN/releases/download/v1.3.4/GFPGANv1.4.pth"
GFPGAN_PATH = MODELS_DIR / "GFPGANv1.4.pth"


def _install_basicsr_shim() -> None:
    """basicsr eski torchvision API'ga (functional_tensor) tayanadi — yangi torchvision'da yo'q.
    Import qilishdan OLDIN chaqirilishi shart."""
    if "torchvision.transforms.functional_tensor" in sys.modules:
        return
    try:
        import torchvision.transforms.functional as F
    except ImportError:
        return
    shim = types.ModuleType("torchvision.transforms.functional_tensor")
    shim.rgb_to_grayscale = F.rgb_to_grayscale
    sys.modules["torchvision.transforms.functional_tensor"] = shim


def _download(url: str, dst: Path, progress=None) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".part")

    def hook(count, block, total):
        if progress and total > 0:
            progress(min(1.0, count * block / total))

    urllib.request.urlretrieve(url, tmp, hook)
    tmp.replace(dst)


def ensure_models(progress=None) -> dict:
    """GFPGAN og'irligini yuklab oladi (agar yo'q bo'lsa). rembg va facexlib o'z modellarini
    birinchi ishlatishda o'zi yuklab oladi (~/.u2net, gfpgan/weights)."""
    status = models_status()
    if not status["gfpgan"]:
        _download(GFPGAN_URL, GFPGAN_PATH, progress)
    # facexlib og'irliklarini ham MODELS_DIR ichiga yig'amiz
    os.environ.setdefault("FACEXLIB_HOME", str(MODELS_DIR))
    return models_status()


def models_status() -> dict:
    """UI'da ko'rsatish uchun: qaysi imkoniyatlar mavjud."""
    def has(mod: str) -> bool:
        try:
            __import__(mod)
            return True
        except Exception:
            return False

    return {
        "gfpgan": GFPGAN_PATH.exists() and has("torch"),
        "rembg": has("rembg"),
        "torch": has("torch"),
        "models_dir": str(MODELS_DIR),
    }
