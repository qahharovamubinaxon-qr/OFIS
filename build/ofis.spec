# PyInstaller spec — build a windowed, standalone OFIS.exe (no terminal).
#   pyinstaller build/ofis.spec
# Output: dist/OFIS/OFIS.exe   (app data lives in %LOCALAPPDATA%/OFIS)
#
# Analysis / PYZ / EXE / COLLECT are injected by PyInstaller when it execs this
# spec — they are not imported. SPECPATH is the folder containing this file.

from pathlib import Path

ROOT = Path(SPECPATH).parent  # noqa: F821 - SPECPATH injected by PyInstaller

a = Analysis(  # noqa: F821
    [str(ROOT / "src" / "app.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "resources"), "resources"),
        (str(ROOT / "templates"), "templates"),
        # DB migrations must ship so schema upgrades apply on a built EXE.
        (str(ROOT / "src" / "database" / "migrations"), "migrations"),
    ],
    hiddenimports=["google.generativeai", "PIL", "PIL.Image", "PIL.ImageOps"],
    hookspath=[],
    excludes=["cv2", "matplotlib", "tkinter"],  # OpenCV is calibration-only
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
    icon=None,
)
coll = COLLECT(  # noqa: F821
    exe, a.binaries, a.datas, name="OFIS"
)
