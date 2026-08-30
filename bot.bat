@echo off
REM ============================================================
REM  OFIS - fonda bot: OFIS oynasini ochmasdan, faqat Telegram
REM  bot ishlaydi. Kompyuter yoqiq tursa - bot javob beradi.
REM
REM  Ishlatish: shu faylni ikki marta bosing. Ochilgan qora
REM  oynani YOPMANG - yopilsa bot to'xtaydi.
REM  To'xtatish: oynani yoping yoki Ctrl+C bosing.
REM
REM  DIQQAT: bu fayl CRLF bilan saqlanishi shart (.gitattributes
REM  buni ta'minlaydi) - cmd.exe Unix qator oxirlarini tushunmaydi.
REM ============================================================
cd /d "%~dp0"
title OFIS bot (fonda) - YOPMANG

echo.
echo ============================================================
echo   OFIS Telegram bot fonda ishga tushmoqda...
echo   Bu oynani YOPMANG - yopilsa bot to'xtaydi.
echo ============================================================
echo.

where py >nul 2>&1
if errorlevel 1 (
  python -m src.bot_main
) else (
  py -3.12 -m src.bot_main
)

echo.
echo   Bot to'xtadi. Oynani yopsangiz bo'ladi.
pause
