@echo off
rem 开发模式运行（无需打包）
cd /d %~dp0
if not exist .venv\Scripts\pythonw.exe (
    echo 未找到 .venv，请先创建虚拟环境并安装依赖（见 README「打包」一节）
    pause
    exit /b 1
)
start "" .venv\Scripts\pythonw.exe qr_reader.py %*
