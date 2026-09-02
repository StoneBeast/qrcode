# QReader —— Windows 二维码识别工具

小体积、绿色便携的二维码 / 条形码识别软件。截图框选即扫，结果自动复制。

![体积](https://img.shields.io/badge/单文件体积-19MB-green) ![依赖](https://img.shields.io/badge/运行依赖-零-blue)

## 功能

| 功能 | 说明 | 默认快捷键 |
|---|---|---|
| 📷 框选识别 | 像 QQ/微信截图一样框选屏幕任意区域，支持多显示器、高分屏 | `Ctrl+Alt+Q` |
| 🖥 全屏识别 | 截取整个屏幕自动寻找所有二维码 / 条形码 | `Ctrl+Alt+W` |
| 📂 打开图片 | 选择本地图片文件识别 | `Ctrl+Alt+O` |
| 📋 粘贴识别 | 直接粘贴剪贴板里的图片（配合 `Win+Shift+S` 截图非常好用） | `Ctrl+Alt+V` |
| ⚙ 设置 | 自定义以上全局快捷键 | — |
| 拖拽识别 | 把图片文件拖进窗口即可识别 | — |
| 历史记录 | 自动保存最近 100 条，双击回看、右键复制/删除，随软件绿色保存 | — |
| 智能解析 | 自动识别网址（可一键打开）、WiFi 信息（解析出 SSID/密码） | — |

**全局快捷键**：点击「设置」可自行修改，改完即时生效；无论焦点在哪个程序上都能触发（如播放器全屏、游戏中）。默认值刻意避开系统级 `Ctrl+V` 之类的组合，防止抢键；若所选组合被其他软件占用，状态栏会提示。识别成功后默认**自动复制到剪贴板**（可用工具栏复选框关闭）；预览图上用红框标出二维码位置；支持 QRCode / DataMatrix / PDF417 / EAN / Code128 等全部常见码制。

## 使用

按下面「打包」一节生成 `dist\QReader.exe`（约 19MB，单文件），双击即可运行，无需 Python 环境。

推荐工作流：`Win+Shift+S` 截屏 → 切到 QReader 按 `Ctrl+V`，或直接点「框选识别」。

**开发模式运行**：先按「打包」一节创建好虚拟环境并安装依赖，然后运行 `run.bat`。

命令行也支持直接传图片：`QReader.exe 图片路径`，启动即识别。

## 目录结构

```
qrcode/
├── qr_reader.py      # 主程序（单文件源码，含全部逻辑）
├── make_icon.py      # 生成应用图标 app.ico
├── make_test_qr.py   # 生成 test_data/ 测试二维码
├── test_decode.py    # 解码自测脚本
├── run.bat           # 开发模式运行
├── app.ico           # 应用图标
└── test_data/        # 测试二维码图片
```

## 打包

运行依赖只有 3 个第三方库：`zxing-cpp`（扫码核心）、`Pillow`（图片解码/截屏）、`tkinterdnd2`（窗口拖拽支持）。GUI 用系统自带 tkinter，刻意不引入 OpenCV / Qt，体积才压得下来。

以 Windows + Python 3.10+ 为例：

```bat
:: 1. 创建虚拟环境并安装依赖（含打包工具 PyInstaller）
python -m venv .venv
.venv\Scripts\python -m pip install zxing-cpp pillow tkinterdnd2 pyinstaller

:: 2. 打包单文件 exe
.venv\Scripts\python -m PyInstaller --noconfirm --clean --onefile --windowed --icon app.ico --name QReader qr_reader.py
```

构建完成后得到 `dist\QReader.exe`，单文件、免安装、可直接分发。图标 `app.ico` 已随仓库提供，如需重新生成可运行 `make_icon.py`。

## 自测

```bat
.venv\Scripts\python make_test_qr.py   &REM 生成测试图
.venv\Scripts\python test_decode.py    &REM 解码断言（含中文/网址/WiFi/小图）
```

## 常见问题

- **框选时屏幕上出现浮动提示窗口残留？** 框选是全屏冻结截图，按 `Esc` 或右键即可取消。
- **识别不准？** 尽量框得稍大一圈（保留二维码周围的留白）；程序对小图会自动放大、对反色二维码自动兼容。
- **数据写在哪？** 仅在软件同目录写 `history.json`（历史记录）与 `error.log`（异常时），删除即重置，不写注册表。
