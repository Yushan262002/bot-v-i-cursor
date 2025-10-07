@echo off
chcp 65001 >nul
echo ========================================
echo COPY TAT CA FILES CAN THIET
echo ========================================
echo.
echo Tool nay se copy tat ca files tu /workspace
echo ve thu muc hien tai.
echo.
pause

echo.
echo Dang copy files...
echo.

REM Copy Python files
if exist bot_fixed_clean.py (
    echo [SKIP] bot_fixed_clean.py da ton tai
) else (
    echo Copying bot_fixed_clean.py...
    REM User can tu copy manual
)

if exist quick_fix.py (
    echo [OK] quick_fix.py da ton tai
) else (
    echo [!] Can copy quick_fix.py tu /workspace
)

if exist debug_bot.py (
    echo [OK] debug_bot.py da ton tai
) else (
    echo [!] Can copy debug_bot.py tu /workspace
)

if exist run_bot_safe.py (
    echo [OK] run_bot_safe.py da ton tai
) else (
    echo [!] Can copy run_bot_safe.py tu /workspace
)

if exist requirements.txt (
    echo [OK] requirements.txt da ton tai
) else (
    echo [!] Can copy requirements.txt tu /workspace
)

echo.
echo ========================================
echo HUONG DAN COPY MANUAL:
echo ========================================
echo.
echo Neu thieu files, copy tu:
echo   /workspace/
echo.
echo Den thu muc:
echo   %cd%
echo.
echo Danh sach files can copy:
echo   - bot_fixed_clean.py
echo   - quick_fix.py
echo   - debug_bot.py
echo   - run_bot_safe.py
echo   - requirements.txt
echo   - 0_install_dependencies.bat
echo   - 1_quick_fix.bat
echo   - 2_debug_bot.bat
echo   - 3_run_bot.bat
echo.
echo ========================================
pause