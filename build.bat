@echo off
chcp 65001 >nul
title Anki Apkg 清理工具 — 打包
echo ========================================
echo  Anki Apkg 清理工具 — 打包 exe
echo ========================================
echo.

:: ── 1. 检查环境 ──
echo [1/4] 检查环境...

where pyinstaller >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo     正在安装 PyInstaller...
    pip install pyinstaller
    if %ERRORLEVEL% NEQ 0 (
        echo ❌ pip install 失败，请确保网络可用
        pause
        exit /b 1
    )
)
echo     PyInstaller ✅

:: ── 2. 准备 libzstd.dll ──
echo [2/4] 准备 libzstd.dll...

if not exist libzstd.dll (
    for /f "delims=" %%i in ('dir /s /b "%LOCALAPPDATA%\Logseq\app-*\resources\app\node_modules\dugite\git\mingw64\bin\libzstd.dll" 2^>nul') do (
        copy "%%i" libzstd.dll >nul
        goto :dll_ok
    )
    echo ⚠️  未找到 libzstd.dll，正在从 GitHub 下载...
    powershell -Command "Invoke-WebRequest -Uri 'https://github.com/facebook/zstd/releases/download/v1.5.6/zstd-win64.zip' -OutFile 'zstd.zip'" >nul 2>&1
    if exist zstd.zip (
        powershell -Command "Expand-Archive -Path 'zstd.zip' -DestinationPath 'zstd_temp' -Force; Copy-Item 'zstd_temp\dll\libzstd.dll' -Destination '.'" >nul 2>&1
        rmdir /s /q zstd_temp 2>nul
        del zstd.zip 2>nul
    )
)
:dll_ok
if not exist libzstd.dll (
    echo ❌ libzstd.dll 获取失败，请手动放到当前目录
    pause
    exit /b 1
)
echo     libzstd.dll ✅

:: ── 3. 准备 UPX（压缩 exe 体积） ──
echo [3/4] 准备 UPX 压缩工具...

set UPX_DIR=upx-4.2.4-win64
set UPX_ZIP=%UPX_DIR%.zip
if not exist "%UPX_DIR%" (
    REM 先看看 PATH 里有没有
    where upx >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        echo     UPX 已在 PATH ✅
        set "UPX_DIR="
    ) else (
        echo     正在下载 UPX...
        powershell -Command "Invoke-WebRequest -Uri 'https://github.com/upx/upx/releases/download/v4.2.4/upx-4.2.4-win64.zip' -OutFile '%UPX_ZIP%'" >nul 2>&1
        if exist "%UPX_ZIP%" (
            powershell -Command "Expand-Archive -Path '%UPX_ZIP%' -DestinationPath '.'" >nul 2>&1
            del "%UPX_ZIP%"
            echo     UPX ✅
        ) else (
            echo     ⚠️  跳过 UPX（exe 会大一些）
            set "UPX_DIR="
        )
    )
) else (
    echo     UPX ✅
)

:: ── 4. 打包 ──
echo [4/4] 正在打包...

set EXTRA=
if defined UPX_DIR (
    set EXTRA=--upx-dir "%UPX_DIR%"
)

pyinstaller --onefile --windowed %EXTRA% --name "AnkiApkgCleaner" --add-data "libzstd.dll;." anki_cleaner.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo  ✅ 打包成功！
    echo     输出: %CD%\dist\AnkiApkgCleaner.exe
    echo     大小: 
    for %%i in (dist\AnkiApkgCleaner.exe) do echo     %%~zi 字节
    echo ========================================
    echo.
    echo 用户只需要这一个 exe 文件即可运行
) else (
    echo.
    echo ❌ 打包失败
    echo.
    echo 试试手动运行:
    echo   pyinstaller --onefile --windowed --name "AnkiApkgCleaner" --add-data "libzstd.dll;." anki_cleaner.py
)

pause
