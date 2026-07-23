# PyInstaller spec — build a windowed OFIS.exe bundling resources + templates.
#   pyinstaller build/ofis.spec
# Output: dist/OFIS/OFIS.exe  (data lives in %LOCALAPPDATA%/OFIS at runtime)

from pathlib import Path

from PyInstaller.building.api import COLLECT, EXE, PYZ
from PyInstaller.building.build_main import Analysis

ROOT = Path(SPECPATH).parent  # noqa: F821 - SPECPATH injected by PyInstaller

a = Analysis(
    [str(ROOT / "src" / "app.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "resources"), "resources"),
        (str(ROOT / "templates"), "templates"),
    ],
    hiddenimports=["google.generativeai"],
    hookspath=[],
    excludes=["cv2", "numpy.tests"],  # OpenCV is calibration-only, not runtime
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name="OFIS",
    console=False,  # windowed — no terminal
    icon=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="OFIS")
