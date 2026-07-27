"""Person/background segmentation with U²-Net (ONNX) — offline and free.

This is the engine behind rembg and HivisionIDPhotos, used directly through
onnxruntime so the app stays a single EXE with no extra service and no heavy
dependency chain. Face geometry stays with the bundled YuNet detector.

Models (downloaded once into AppData ``models/``, never shipped in git):

* ``u2net_human_seg.onnx`` (~168 MB) — trained on people; the quality pick.
* ``u2netp.onnx`` (~4.6 MB) — the light variant; downloads in seconds, used
  until the big one has arrived.

First run: the small model is fetched synchronously (seconds) so the feature
works immediately, and the big one is fetched in a background thread for every
run after that. No model / no network → callers fall back to the flood-fill
whitening that shipped before, so nothing ever breaks offline.
"""

from __future__ import annotations

import threading
import urllib.request
from pathlib import Path

from src.common.logging import get_logger
from src.config import paths

log = get_logger(__name__)

_BASE = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/"
# (filename, minimum sane size in bytes) — best first
MODELS: tuple[tuple[str, int], ...] = (
    ("u2net_human_seg.onnx", 100_000_000),
    ("u2netp.onnx", 3_000_000),
)

_sessions: dict[str, object] = {}
_download_lock = threading.Lock()
_bg_download_started = False


def _model_file(name: str) -> Path:
    return paths.models_dir() / name


def _download(name: str, min_size: int) -> bool:
    url = _BASE + name
    target = _model_file(name)
    tmp = target.with_suffix(".part")
    try:
        log.info("Downloading %s …", name)
        with urllib.request.urlopen(url, timeout=600) as resp, open(tmp, "wb") as f:
            while chunk := resp.read(1 << 20):
                f.write(chunk)
        if tmp.stat().st_size < min_size:
            tmp.unlink(missing_ok=True)
            return False
        tmp.replace(target)
        log.info("Model %s ready (%.1f MB)", name, target.stat().st_size / 1e6)
        return True
    except Exception as exc:  # noqa: BLE001 - offline is a normal condition
        log.info("Model %s not downloaded: %s", name, exc)
        tmp.unlink(missing_ok=True)
        return False


def _upgrade_in_background() -> None:
    """Fetch the big model once, quietly, so later runs use it."""
    global _bg_download_started
    if _bg_download_started:
        return
    _bg_download_started = True
    name, min_size = MODELS[0]

    def worker() -> None:
        with _download_lock:
            if not _model_file(name).exists():
                _download(name, min_size)

    threading.Thread(target=worker, daemon=True, name="ofis-model-dl").start()


def model_path(download: bool = True) -> Path | None:
    """Best available model file, downloading on first use when allowed."""
    import os

    override = os.environ.get("OFIS_BG_MODEL", "")
    if override:
        p = Path(override)
        return p if p.exists() else None

    for name, min_size in MODELS:
        p = _model_file(name)
        if p.exists() and p.stat().st_size >= min_size:
            return p
    if not download:
        return None
    # nothing on disk: grab the small one now, the big one in the background
    small, small_min = MODELS[1]
    with _download_lock:
        p = _model_file(small)
        if not p.exists() and not _download(small, small_min):
            return None
    _upgrade_in_background()
    return _model_file(small)


def _session(path: Path):
    import onnxruntime as ort

    key = str(path)
    if key not in _sessions:
        _sessions[key] = ort.InferenceSession(
            key, providers=["CPUExecutionProvider"])
    return _sessions[key]


def segment(rgb, download: bool = True):
    """RGB array → person mask (uint8, same H×W, 255 = person), or None when
    onnxruntime / the model is unavailable (caller falls back)."""
    try:
        import numpy as np
        import onnxruntime  # noqa: F401 - probe only
        from PIL import Image
    except ImportError:
        return None
    path = model_path(download)
    if path is None:
        return None
    try:
        sess = _session(path)
        h, w = rgb.shape[:2]
        inp = Image.fromarray(rgb).resize((320, 320), Image.LANCZOS)
        x = np.asarray(inp).astype(np.float32) / 255.0
        x = (x - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]
        x = x.transpose(2, 0, 1)[None].astype(np.float32)
        out = sess.run(None, {sess.get_inputs()[0].name: x})[0][0][0]
        out = (out - out.min()) / (out.max() - out.min() + 1e-8)
        mask = Image.fromarray((out * 255).astype(np.uint8)).resize(
            (w, h), Image.LANCZOS)
        return np.asarray(mask)
    except Exception as exc:  # noqa: BLE001 - a broken file must not crash
        log.warning("Segmentation failed (%s) — falling back", exc)
        try:  # a truncated download keeps failing; remove it so it re-fetches
            if path.stat().st_size < dict(MODELS).get(path.name, 0):
                path.unlink(missing_ok=True)
        except OSError:
            pass
        return None
