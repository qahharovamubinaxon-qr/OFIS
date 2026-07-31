@echo off
REM OFIS — build a standalone EXE (run once; then use the Desktop shortcut).
cd /d "%~dp0"

echo === Ishlab turgan OFIS yopilmoqda ===
REM PyInstaller cannot replace dist\OFIS while the old EXE is running, so the
REM build used to die halfway through COLLECT leaving the previous EXE in place.
taskkill /F /IM OFIS.exe >nul 2>&1
if not errorlevel 1 (
  echo   OFIS.exe yopildi.
  REM let Windows release the DLL handles before we delete the folder
  ping -n 3 127.0.0.1 >nul
)
REM cloudflared is OFIS's own Mini App tunnel. Killed hard, OFIS never gets to
REM stop it, and it keeps dist\OFIS as its working directory - Windows then
REM refuses to delete that folder and the build dies at COLLECT with
REM "занят другим процессом". A tunnel with no OFIS behind it is dead weight.
taskkill /F /IM cloudflared.exe >nul 2>&1
if not errorlevel 1 (
  echo   cloudflared yopildi ^(OFIS tunneli^).
  ping -n 2 127.0.0.1 >nul
)

echo === Installing build tools ===
pip install -r requirements.txt
pip install pyinstaller

echo === Building OFIS.exe (2-5 minutes) ===
pyinstaller build\ofis.spec --noconfirm --clean
if errorlevel 1 goto :failed
if not exist "dist\OFIS\OFIS.exe" goto :failed

echo === Portable ZIP ===
if exist "dist\OFIS_portable_1.0.0.zip" del /F /Q "dist\OFIS_portable_1.0.0.zip"
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
exit /b 0

:failed
echo.
echo ============================================================
echo  XATO: EXE yig'ilmadi — eski dist\OFIS o'zgarmay qoldi!
echo.
echo  Sabab: dist\OFIS papkasidagi fayllar band.
echo    - OFIS oynasi hali ochiq (Task Manager -^> OFIS.exe -^> End task);
echo    - yoki dist\OFIS papkasi Explorer'da ochiq turibdi;
echo    - yoki antivirus faylni tekshirayotgan bo'lishi mumkin.
echo.
echo  Hammasini yopib, build_exe.bat ni qaytadan ishga tushiring.
echo ============================================================
pause
exit /b 1
