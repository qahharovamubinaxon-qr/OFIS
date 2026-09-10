# PyInstaller spec — build a windowed, standalone OFIS.exe (no terminal).
#   pyinstaller build/ofis.spec
# Output: dist/OFIS/OFIS.exe   (app data lives in %LOCALAPPDATA%/OFIS)
#
# Analysis / PYZ / EXE / COLLECT are injected by PyInstaller when it execs this
# spec — they are not imported. SPECPATH is the folder containing this file.

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files  # noqa: F821

ROOT = Path(SPECPATH).parent  # noqa: F821 - SPECPATH injected by PyInstaller

# РАСМ-ФОТО «photo_tools» ядроси лойиҳа илдизидаги вендор пакет — lazy import
# қилингани учун PyInstaller ўзи топмайди, шунга қўлда киритилади.
_datas = [
    (str(ROOT / "resources"), "resources"),
    (str(ROOT / "templates"), "templates"),
    # DB migrations must ship so schema upgrades apply on a built EXE.
    (str(ROOT / "src" / "database" / "migrations"), "migrations"),
]
_binaries = []
_hidden = ["PIL", "PIL.Image", "PIL.ImageOps", "qrcode",
           "photo_tools", "photo_tools.person_photo", "photo_tools.docscan",
           "photo_tools.models", "photo_tools.cli"]

# basicsr (GFPGAN боғламаси) эски torchvision.transforms.functional_tensor ни
# импорт қилади — у torchvision ≥0.17 да олиб ташланган. PyInstaller Analysis
# basicsr ни импорт қила олиши (ва GFPGAN ни EXE га қўшиши) учун ўша модулни
# бир қаторлик қилиб тиклаб қўямиз. Runtime да ҳам photo_tools shim қўяди, бу
# эса build пайтидаги импорт учун. Torch йўқ енгил йиғишда — ўтказиб юборилади.
try:
    import os as _os

    import torchvision as _tv

    _ft = _os.path.join(_os.path.dirname(_tv.__file__), "transforms",
                        "functional_tensor.py")
    if not _os.path.exists(_ft):
        with open(_ft, "w", encoding="utf-8") as _f:
            _f.write("from torchvision.transforms.functional "
                     "import rgb_to_grayscale  # noqa: F401\n")
except Exception:  # noqa: BLE001 - torch йўқ енгил йиғиш
    pass

# rembg (фон олиш) ва GFPGAN стек (AI юз тиклаш) — маълумот файллари ва
# яширин импортлари билан. Йўқ бўлса (енгил йиғиш) — ўтказиб юборилади.
for _pkg in ("rembg", "gfpgan", "facexlib", "basicsr"):
    try:
        _d, _b, _h = collect_all(_pkg)
        _datas += _d
        _binaries += _b
        _hidden += _h
    except Exception:  # noqa: BLE001 - пакет йўқ бўлса йиғиш тўхтамасин
        pass

# cv2 нинг Haar каскади (haarcascade_frontalface_default.xml) — photo_tools
# юз топишда ишлатади; PyInstaller уни ўзи қўшмайди.
try:
    _datas += collect_data_files("cv2")
except Exception:  # noqa: BLE001
    pass

a = Analysis(  # noqa: F821
    [str(ROOT / "src" / "app.py")],
    pathex=[str(ROOT)],
    binaries=_binaries,
    datas=_datas,
    hiddenimports=_hidden,
    hookspath=[],
    excludes=["matplotlib", "tkinter"],  # cv2 IS bundled — РАСМ-ФОТО needs it
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OFIS",
    console=False,  # windowed — no terminal window
    icon=str(ROOT / "resources" / "icons" / "ofis.ico"),
    version=str(ROOT / "build" / "version_info.txt"),
)
coll = COLLECT(  # noqa: F821
    exe, a.binaries, a.datas, name="OFIS"
)
