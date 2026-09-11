@echo off
REM OFIS — build a standalone EXE (run once; then use the Desktop shortcut).
cd /d "%~dp0"

REM OFIS ni ANIQ Python 3.12 bilan yig'amiz. torch/rembg/gfpgan ning yangi
REM Python 3.14 uchun wheel'lari hali yo'q - agar PATH dagi "python"/"pip"
REM 3.14 bo'lsa, "pip install" jimgina yiqiladi va EXE kutubxonasiz chiqadi
REM (aynan shu bo'lgan edi: "No module named rembg"). "py -3.12" launcher
REM aniq 3.12 ni tanlaydi.
set "PY=py -3.12"
%PY% --version >nul 2>&1
if errorlevel 1 (
  echo XATO: Python 3.12 topilmadi.
  echo   https://www.python.org/downloads/ dan Python 3.12 ni o'rnating.
  pause
  exit /b 1
)

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

echo === Installing build tools (Python 3.12) ===
%PY% -m pip install -r requirements.txt
if errorlevel 1 goto :depsfail
%PY% -m pip install pyinstaller

echo === cv2 ni faqat headless (4.x) qoldirish ===
REM gfpgan/basicsr/facexlib to'liq "opencv-python" ni tortadi. U PySide6 ning
REM Qt si bilan urishadi, va OpenCV 5.0 da Haar (CascadeClassifier) olib
REM tashlangan - photo_tools yuz topishda uni ishlatadi. Shu sabab to'liq
REM nusxa o'chirilib, faqat headless 4.x qoldiriladi.
%PY% -m pip uninstall -y opencv-python opencv-contrib-python >nul 2>&1
%PY% -m pip install --force-reinstall "opencv-python-headless>=4.9,<5"

echo === Building OFIS.exe (torch bilan katta: 10-20 daqiqa) ===
%PY% -m PyInstaller build\ofis.spec --noconfirm --clean
if errorlevel 1 goto :failed
if not exist "dist\OFIS\OFIS.exe" goto :failed

echo === Portable ZIP ===
rem Compress-Archive reads the whole folder into memory and dies on ours
rem ("System.OutOfMemoryException"), so the .NET packer is used instead:
rem it streams straight to the file. The EXE is already built by now, so a
rem ZIP that fails is a warning, never a failed build.
if exist "dist\OFIS_portable_1.0.0.zip" del /F /Q "dist\OFIS_portable_1.0.0.zip"
powershell -NoProfile -Command "try { Add-Type -AssemblyName System.IO.Compression.FileSystem; [System.IO.Compression.ZipFile]::CreateFromDirectory((Resolve-Path 'dist\OFIS').Path, (Join-Path (Resolve-Path 'dist').Path 'OFIS_portable_1.0.0.zip'), [System.IO.Compression.CompressionLevel]::Optimal, $true) } catch { Write-Host ('ZIP tayyorlanmadi (EXE tayyor): ' + $_.Exception.Message) }"

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

:depsfail
echo.
echo ============================================================
echo  XATO: kutubxonalar o'rnatilmadi (pip install -r requirements.txt).
echo  Ko'p uchraydi: Python 3.12 yo'q, yoki internet uzilgan
echo  (torch/rembg katta - yuzlab MB). Internetni tekshirib qaytadan uring.
echo ============================================================
pause
exit /b 1

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
