@echo off
chcp 65001 >nul
echo ========================================
echo RUNNING BOT
echo ========================================
echo.

REM Tim file bot
if exist bot_fixed_clean.py (
    echo [OK] Found bot_fixed_clean.py
    echo.
    python bot_fixed_clean.py
) else if exist bot.py (
    echo [OK] Found bot.py
    echo.
    python bot.py
) else (
    echo [X] Khong tim thay file bot!
    echo Can co file bot_fixed_clean.py hoac bot.py
    pause
    exit /b 1
)

pause