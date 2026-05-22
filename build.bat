@echo off
chcp 65001 >nul
title Build AnkiApkgCleaner
echo ========================================
echo  Build AnkiApkgCleaner
echo ========================================
echo.

:: 1. Install dependencies
echo [1/3] Installing dependencies...
pip install pyinstaller zstandard -q
if %ERRORLEVEL% NEQ 0 (
    echo ❌ pip install failed
    pause
    exit /b 1
)
echo     ✅ pyinstaller + zstandard

:: 2. Build exe
echo [2/3] Building exe...
set ICON=assets\AnkiHTMLCleaner.ico
if not exist "%ICON%" if exist "AnkiHTMLCleaner.ico" set ICON=AnkiHTMLCleaner.ico

pyinstaller --onefile --windowed --icon "%ICON%" --name "AnkiApkgCleaner" anki_cleaner.py
if %ERRORLEVEL% NEQ 0 (
    echo ❌ Build failed
    pause
    exit /b 1
)
echo     ✅ AnkiApkgCleaner.exe

:: 3. Cleanup
echo [3/3] Cleaning build cache...
rmdir /s /q build >nul 2>&1
del /f /q AnkiApkgCleaner.spec >nul 2>&1
echo     ✅ Done

echo.
echo ========================================
echo  Output: dist\AnkiApkgCleaner.exe
echo ========================================
pause
