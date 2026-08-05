@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title OFIS — компьютерни тозалаш

rem ============================================================
rem  Компьютерни кераксиз файллардан тозалайди.
rem
rem  ФАҚАТ ЎЗИ ҚАЙТА ЯРАЛАДИГАН нарсалар ўчирилади: вақтинчалик
rem  файллар, браузер кэши, Windows Update юкламалари, лог ва
rem  хато файллари, қурилиш папкаси.
rem
rem  ҲЕЧ ҚАЧОН тегилмайди:
rem    - AppData\Local\OFIS  ← фирмалар, адреслар, бланкалар,
rem                             созловлар, чиққан ҳужжатлар, архив
rem    - Ҳужжатлар, Иш столи, Юкланмалар, OneDrive
rem    - Корзина (уни ўзингиз бўшатасиз — ичида керакли нарса
rem      бўлиши мумкин)
rem    - dist\OFIS — ишлаётган программангиз
rem    - pagefile.sys — Windows нинг ўз файли
rem ============================================================

echo.
echo ============================================================
echo   OFIS — компьютерни тозалаш
echo ============================================================
echo.
echo  Ўчирилади (ҳаммаси ўзи қайта яралади):
echo    - Вақтинчалик файллар (Temp)
echo    - Windows Update юклаган эски файллар
echo    - Chrome / Edge кэши
echo    - Хато ҳисоботлари (crash dumps), эски логлар
echo    - Расм миниатюралари кэши
echo    - pip кэши ва OFIS қурилиш папкаси
echo.
echo  ТЕГИЛМАЙДИ: ҳужжатларингиз, иш столи, юкланмалар,
echo              OFIS маълумотлари, корзина, программанинг ўзи.
echo.

for /f %%a in ('powershell -NoProfile -Command "[math]::Round((Get-PSDrive C).Free/1GB,2)"') do set BEFORE=%%a
echo  Ҳозир бўш жой: %BEFORE% GB
echo.

choice /C YN /N /M "Тозалашни бошлайманми? (Y = ҳа, N = йўқ): "
if errorlevel 2 goto :cancelled

echo.
echo === 1/7  Вақтинчалик файллар ===
for /d %%d in ("%TEMP%\*") do rd /s /q "%%d" 2>nul
del /f /q "%TEMP%\*.*" 2>nul
for /d %%d in ("C:\Windows\Temp\*") do rd /s /q "%%d" 2>nul
del /f /q "C:\Windows\Temp\*.*" 2>nul

echo === 2/7  Windows Update юкламалари ===
net stop wuauserv >nul 2>&1
net stop bits >nul 2>&1
rd /s /q "C:\Windows\SoftwareDistribution\Download" 2>nul
md "C:\Windows\SoftwareDistribution\Download" 2>nul
net start wuauserv >nul 2>&1
net start bits >nul 2>&1

echo === 3/7  Браузер кэши ===
rd /s /q "%LOCALAPPDATA%\Google\Chrome\User Data\Default\Cache" 2>nul
rd /s /q "%LOCALAPPDATA%\Google\Chrome\User Data\Default\Code Cache" 2>nul
rd /s /q "%LOCALAPPDATA%\Microsoft\Edge\User Data\Default\Cache" 2>nul
rd /s /q "%LOCALAPPDATA%\Microsoft\Edge\User Data\Default\Code Cache" 2>nul

echo === 4/7  Хато ҳисоботлари ва логлар ===
rd /s /q "%LOCALAPPDATA%\CrashDumps" 2>nul
del /f /q "C:\Windows\Logs\CBS\*.log" 2>nul
del /f /q "C:\Windows\Logs\DISM\*.log" 2>nul
del /f /q /s "%LOCALAPPDATA%\Microsoft\Windows\WER\ReportArchive\*" 2>nul

echo === 5/7  Расм миниатюралари кэши ===
del /f /q "%LOCALAPPDATA%\Microsoft\Windows\Explorer\thumbcache_*.db" 2>nul
del /f /q "%LOCALAPPDATA%\Microsoft\Windows\Explorer\iconcache_*.db" 2>nul

echo === 6/7  pip кэши ===
python -m pip cache purge >nul 2>&1

echo === 7/7  OFIS қурилиш папкаси ===
rd /s /q "%~dp0build\ofis" 2>nul

for /f %%a in ('powershell -NoProfile -Command "[math]::Round((Get-PSDrive C).Free/1GB,2)"') do set AFTER=%%a

echo.
echo ============================================================
echo   Тозаланди.
echo     Аввал:  %BEFORE% GB бўш
echo     Ҳозир:  %AFTER% GB бўш
echo ============================================================
echo.
echo  Яна жой керак бўлса, ЎЗИНГИЗ қилинг:
echo    1) Корзинани бўшатинг (ичида керакли файл бўлиши мумкин)
echo    2) Юкланмалар (Downloads) папкасини кўриб чиқинг
echo    3) Пуск -^> "Очистка диска" -^> "Очистить системные файлы"
echo.
pause
goto :eof

:cancelled
echo.
echo  Бекор қилинди — ҳеч нарса ўчирилмади.
echo.
pause
