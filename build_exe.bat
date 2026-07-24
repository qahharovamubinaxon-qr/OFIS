@echo off
REM OFIS — build a standalone EXE (run once; then use the Desktop shortcut).
cd /d "%~dp0"
echo === Installing build tools ===
pip install -r requirements.txt
pip install pyinstaller
echo === Building OFIS.exe (2-5 minutes) ===
pyinstaller build\ofis.spec --noconfirm --clean
echo.
echo ============================================================
echo  Tayyor!  EXE:  dist\OFIS\OFIS.exe
echo  Uni ish stoliga chiqarish uchun: dist\OFIS papkasiga kiring,
echo  OFIS.exe ustida o'ng tugma -> "Send to" -> "Desktop (create shortcut)".
echo ============================================================
pause
