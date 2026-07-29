@echo off
REM ============================================================
REM  OFIS — yangilash: kodni tortib olib, EXE ni qayta yig'adi.
REM
REM  Ikki qadam bir joyda. «git pull» yolg'iz o'zi YETARLI EMAS:
REM  ish stolidagi yorliq dist\OFIS\OFIS.exe ga boradi, u esa
REM  yig'ilgan paytdagi kodni ichida olib yuradi. Yangi kod EXE ga
REM  faqat qayta yig'ilganda tushadi.
REM ============================================================
cd /d "%~dp0"
chcp 65001 >nul

echo.
echo ============================================================
echo  1/2  Yangi kod olinmoqda (git pull)
echo ============================================================
git --version >nul 2>&1
if errorlevel 1 (
  echo.
  echo  XATO: git topilmadi.
  echo  https://git-scm.com/download/win dan o'rnating va qaytadan urinib ko'ring.
  pause
  exit /b 1
)

git pull --ff-only
if errorlevel 1 (
  echo.
  echo ============================================================
  echo  XATO: kod tortib olinmadi.
  echo.
  echo  Ko'p uchraydigan sabab: bu kompyuterda o'zgartirilgan fayl bor
  echo  (masalan yangi shablon yuklagansiz) va u yangisi bilan
  echo  to'qnashyapti. Hech narsa o'chirilmadi — hammasi joyida.
  echo.
  echo  Nima yozayotganini menga ko'rsating, birga hal qilamiz.
  echo ============================================================
  pause
  exit /b 1
)

echo.
echo ============================================================
echo  2/2  EXE qayta yig'ilmoqda (2-5 daqiqa)
echo ============================================================
call "%~dp0build_exe.bat"
exit /b %errorlevel%
