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

:: ── 2. 安装 zstd 支持（新版 apkg 需要） ──
echo [2/4] 检查 zstd 支持...

python -c "import zstandard" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo     正在安装 zstandard...
    pip install zstandard
    if %ERRORLEVEL% NEQ 0 (
        echo ⚠️  zstandard 安装失败，仅支持旧版 apkg
    ) else (
        echo     zstandard ✅
    )
) else (
    echo     zstandard ✅
)

:: ── 3. 准备 UPX（压缩 exe 体积） ──
echo [3/4] 准备 UPX 压缩工具...

set UPX_DIR=upx-4.2.4-win64
if not exist "%UPX_DIR%" (
    where upx >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        echo     UPX 已在 PATH ✅
        set "UPX_DIR="
    ) else (
        echo     正在下载 UPX...
        powershell -Command "Invoke-WebRequest -Uri 'https://github.com/upx/upx/releases/download/v4.2.4/upx-4.2.4-win64.zip' -OutFile 'upx.zip'" >nul 2>&1
        if exist upx.zip (
            powershell -Command "Expand-Archive -Path 'upx.zip' -DestinationPath '.'" >nul 2>&1
            del upx.zip >nul 2>&1
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
if defined UPX_DIR set EXTRA=--upx-dir "%UPX_DIR%"

pyinstaller --onefile --windowed %EXTRA% --name "AnkiApkgCleaner" anki_cleaner.py

if %ERRORLEVEL% EQU 0 (
    for %%i in (dist\AnkiApkgCleaner.exe) do set FILESIZE=%%~zi
    echo.
    echo ========================================
    echo  ✅ 打包成功！
    echo     输出: dist\AnkiApkgCleaner.exe
    for %%i in (dist\AnkiApkgCleaner.exe) do echo     大小: %%~zi 字节
    echo ========================================
    echo.
    echo 用户只需要这一个 exe 文件即可运行
) else (
    echo.
    echo ❌ 打包失败
    echo.
    echo 试试手动运行:
    echo   pyinstaller --onefile --windowed --name "AnkiApkgCleaner" anki_cleaner.py
)

pause
