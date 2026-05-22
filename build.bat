@echo off
chcp 65001 >nul
echo ========================================
echo  Anki Apkg 清理工具 — 打包 exe
echo ========================================
echo.

:: 检查 PyInstaller
where pyinstaller >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [1/2] 正在安装 PyInstaller...
    pip install pyinstaller
    if %ERRORLEVEL% NEQ 0 (
        echo ❌ 安装失败，请确保 pip 可用
        pause
        exit /b 1
    )
) else (
    echo [1/2] PyInstaller 已安装
)

:: 检查 libzstd.dll
if not exist libzstd.dll (
    echo ⚠️  未找到 libzstd.dll，尝试从 Logseq 复制...
    for /f "delims=" %%i in ('dir /s /b "%LOCALAPPDATA%\Logseq\app-*\resources\app\node_modules\dugite\git\mingw64\bin\libzstd.dll" 2^>nul') do (
        copy "%%i" libzstd.dll >nul
        echo ✅ 已复制 libzstd.dll
        goto :found
    )
    echo ❌ 未找到 libzstd.dll，请手动放到当前目录
    pause
    exit /b 1
)
:found

echo [2/2] 正在打包 exe...
pyinstaller --onefile --windowed --name "AnkiApkgCleaner" --add-data "libzstd.dll;." anki_cleaner.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ✅ 打包成功！
    echo 输出: dist\AnkiApkgCleaner.exe
    echo.
    echo 用户只需要这一个 exe 文件即可运行
) else (
    echo ❌ 打包失败
)

pause
