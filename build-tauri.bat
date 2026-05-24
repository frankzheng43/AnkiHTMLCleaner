@echo off
chcp 65001 >nul
title Build AnkiHTMLCleaner (Tauri)
echo ========================================
echo  Build AnkiHTMLCleaner — Tauri
echo ========================================
echo.

:: 1. 安装 Rust
echo [1/5] 检查 Rust...
rustc --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo     正在安装 Rust...
    winget install Rustlang.Rustup 2>nul || (
        echo ❌ 请手动安装: https://rustup.rs
        pause
        exit /b 1
    )
)
echo     ✅ Rust

:: 2. 安装 Node.js
echo [2/5] 检查 Node.js...
node --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo     正在安装 Node.js...
    winget install OpenJS.NodeJS.LTS 2>nul || (
        echo ⚠️  请手动安装: https://nodejs.org
        pause
        exit /b 1
    )
)
echo     ✅ Node.js

:: 3. 安装 Tauri CLI
echo [3/5] 安装 Tauri CLI...
cargo install tauri-cli --version "^2"
echo     ✅ tauri-cli

:: 4. 编译
echo [4/5] 编译...
cd src-tauri
cargo build --release
cd ..
echo     ✅ 编译完成

:: 5. 复制 exe
echo [5/5] 复制输出...
mkdir dist 2>nul
copy src-tauri\target\release\anki-html-cleaner.exe dist\AnkiHTMLCleaner.exe
echo     ✅ dist\AnkiHTMLCleaner.exe

echo.
echo ========================================
echo  ✅ 全部完成！
echo     输出: dist\AnkiHTMLCleaner.exe
echo ========================================
pause
