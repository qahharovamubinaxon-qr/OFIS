@echo off
REM ============================================================
REM  OFIS - yangilash: kodni tortib olib, EXE ni qayta yig'adi.
REM
REM  Ikki qadam bir joyda. "git pull" yolg'iz o'zi YETARLI EMAS:
REM  ish stolidagi yorliq dist\OFIS\OFIS.exe ga boradi, u esa
REM  yig'ilgan paytdagi kodni ichida olib yuradi. Yangi kod EXE ga
REM  faqat qayta yig'ilganda tushadi.
REM
REM  DIQQAT: bu fayl CRLF bilan saqlanishi shart. cmd.exe Unix
REM  qator oxirlarini tushunmaydi - har satrning boshi yeyiladi.
REM  .gitattributes buni ta'minlab turadi.
REM ============================================================
cd /d "%~dp0"

echo.
echo ============================================================
echo   1/2  Yangi kod olinmoqda (git pull)
echo ============================================================
where git >nul 2>&1
if errorlevel 1 (
  echo.
  echo   XATO: git topilmadi.
  echo   https://git-scm.com/download/win dan o'rnating.
  pause
  exit /b 1
)

git pull --ff-only
if errorlevel 1 (
  echo.
  echo ============================================================
  echo   XATO: kod tortib olinmadi.
  echo.
  echo   Ko'p uchraydigan sabab: bu kompyuterda o'zgartirilgan fayl
  echo   bor ^(masalan yangi shablon yuklagansiz^) va u yangisi bilan
  echo   to'qnashyapti. Hech narsa o'chirilmadi - hammasi joyida.
  echo.
  echo   Ekrandagini menga ko'rsating, birga hal qilamiz.
  echo ============================================================
  pause
  exit /b 1
)

echo.
echo ============================================================
echo   2/2  EXE qayta yig'ilmoqda (2-5 daqiqa)
echo ============================================================
call "%~dp0build_exe.bat"
exit /b %errorlevel%
