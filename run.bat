@echo off
rem 开发模式运行（无需打包）
cd /d %~dp0
if not exist .venv\Scripts\pythonw.exe (
    echo 未找到 .venv，请先运行 build.bat
    pause
    exit /b 1
)
start "" .venv\Scripts\pythonw.exe qr_reader.py %*
