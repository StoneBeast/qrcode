@echo off
rem 一键构建：首次运行会自动创建虚拟环境并安装依赖（全部在本目录，不占用 C 盘）
setlocal
cd /d %~dp0
set PIP_CACHE_DIR=%~dp0.pipcache
set TMP=%~dp0.tmp
set TEMP=%~dp0.tmp
if not exist "%TMP%" mkdir "%TMP%"
set PYTHON=%~dp0.venv\Scripts\python.exe
set BASE_PY=D:\huggingFace\pythons\cpython-3.12.14-windows-x86_64-none\python.exe

if not exist "%PYTHON%" (
    echo [1/4] 创建虚拟环境 .venv ...
    "%BASE_PY%" -m venv .venv || goto :err
)
echo [2/4] 安装依赖 ...
"%PYTHON%" -m pip install -q --no-warn-script-location zxing-cpp pillow tkinterdnd2 pyinstaller || goto :err
echo [3/4] 生成图标 ...
"%PYTHON%" make_icon.py || goto :err
echo [4/4] 打包 exe ...
"%PYTHON%" -m PyInstaller --noconfirm --clean --onefile --windowed --icon app.ico --name QReader qr_reader.py || goto :err
echo.
echo 构建完成: dist\QReader.exe
exit /b 0

:err
echo 构建失败，请检查上方错误信息。
exit /b 1
