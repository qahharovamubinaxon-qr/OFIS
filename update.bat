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
  REM  Bu nusxada kod YOZILMAYDI - u faqat olinadi va yig'iladi. Shuning
  REM  uchun "pull" bo'lmasa, to'g'ri javob: GitHub'dagiga tenglashtirish.
  REM  Ko'p uchragan hol: yarim qolgan konflikt - "Pulling is not possible
  REM  because you have unmerged files".
  echo.
  echo   Ogohlantirish: oddiy yo'l bilan olinmadi - GitHub'dagiga
  echo   tenglashtiriladi. Siz qo'shgan YANGI fayllar o'chmaydi.
  echo.
  git merge --abort >nul 2>&1
  git rebase --abort >nul 2>&1
  git fetch origin main
  if errorlevel 1 (
    echo.
    echo ============================================================
    echo   XATO: GitHub'ga ulanilmadi. Internetni tekshirib
    echo   qaytadan urinib ko'ring.
    echo ============================================================
    pause
    exit /b 1
  )
  git reset --hard origin/main
  if errorlevel 1 (
    echo.
    echo ============================================================
    echo   XATO: kod tortib olinmadi. Ekrandagini menga ko'rsating.
    echo ============================================================
    pause
    exit /b 1
  )
  echo   Tenglashtirildi.
)

echo.
echo ============================================================
echo   2/2  EXE qayta yig'ilmoqda (2-5 daqiqa)
echo ============================================================
call "%~dp0build_exe.bat"
exit /b %errorlevel%
