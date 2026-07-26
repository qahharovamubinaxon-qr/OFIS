@echo off
REM OFIS — build a standalone EXE (run once; then use the Desktop shortcut).
cd /d "%~dp0"
echo === Installing build tools ===
pip install -r requirements.txt
pip install pyinstaller
echo === Building OFIS.exe (2-5 minutes) ===
pyinstaller build\ofis.spec --noconfirm --clean
echo === Portable ZIP ===
powershell -NoProfile -Command "Compress-Archive -Path 'dist\OFIS' -DestinationPath 'dist\OFIS_portable_1.0.0.zip' -Force"
echo.
echo ============================================================
echo  Tayyor!
echo    EXE:       dist\OFIS\OFIS.exe
echo    Portable:  dist\OFIS_portable_1.0.0.zip  (boshqa kompyuterga olib o'tish uchun)
echo    Installer: Inno Setup 6 bo'lsa:  iscc build\installer.iss
echo  Ish stoliga chiqarish: OFIS.exe ustida o'ng tugma -^> "Send to" -^> Desktop.
echo ============================================================
pause
