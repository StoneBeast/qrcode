# -*- coding: utf-8 -*-
"""
QReader —— Windows 二维码识别工具

小体积、免安装依赖的单窗口小工具：
  * 框选屏幕识别（类截图，支持多显示器）
  * 全屏识别 / 打开图片 / 粘贴剪贴板图片 / 拖拽图片进窗口
  * 结果自动复制、历史记录、WiFi / 网址智能解析
依赖：Pillow、zxing-cpp、tkinterdnd2（可选，用于拖拽）
"""
import os
import re
import sys
import json
import time
import ctypes
import traceback
import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, font as tkfont

from PIL import Image, ImageTk, ImageDraw, ImageGrab, ImageEnhance, ImageFont

try:
    import zxingcpp
except ImportError:
    print("缺少 zxing-cpp：请在 .venv 中执行 pip install zxing-cpp")
    raise

APP_NAME = "二维码识别工具"
APP_VERSION = "1.0.0"
FONT_FAMILY = "Microsoft YaHei UI"

# ---------------------------------------------------------------- 基础工具


def app_dir():
    """程序所在目录（打包后为 exe 目录），历史记录等可写数据放在这里，保持绿色便携。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def data_dir():
    """可写数据目录：优先 exe/脚本目录，只读环境下退回用户目录。"""
    for d in (app_dir(), os.path.join(os.path.expanduser("~"), ".qreader")):
        try:
            os.makedirs(d, exist_ok=True)
            probe = os.path.join(d, ".write_test")
            with open(probe, "w") as f:
                f.write("ok")
            os.remove(probe)
            return d
        except OSError:
            continue
    return os.getcwd()


HISTORY_FILE = os.path.join(data_dir(), "history.json")


def enable_dpi_awareness():
    """让窗口与截屏坐标使用物理像素，保证高分屏下框选位置精确。"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def virtual_screen():
    """虚拟屏幕（所有显示器拼合后的范围）：x, y, w, h"""
    g = ctypes.windll.user32.GetSystemMetrics
    return g(76), g(77), g(78), g(79)  # SM_XVIRTUALSCREEN....


def grab_screen():
    """抓取整个虚拟屏幕，返回 PIL 图像（像素 0,0 对应虚拟屏幕左上角）。"""
    vx, vy, vw, vh = virtual_screen()
    shot = ImageGrab.grab(all_screens=True)
    if shot.size != (vw, vh):
        shot = shot.resize((max(vw, 1), max(vh, 1)), Image.BILINEAR)
    return shot


# ---------------------------------------------------------------- 解码核心

URL_RE = re.compile(r"^(https?|ftp)://", re.I)
WIFI_RE = re.compile(
    r"^WIFI:(?:T:(?P<t>[^;]*);)?(?:S:(?P<s>[^;]*);)?(?:P:(?P<p>[^;]*);)?(?:H:(?P<h>[^;]*);?)?",
    re.I,
)

CONTENT_TYPE_NAMES = {
    "Text": "文本",
    "Binary": "二进制",
    "GS1": "GS1",
    "ISO15434": "ISO15434",
    "UnknownECI": "未知编码",
}


def _point_xy(p):
    try:
        return float(p.x), float(p.y)
    except AttributeError:
        try:
            return float(p[0]), float(p[1])
        except Exception:
            return None


def decode_image(img):
    """解码图片里的全部条码，返回 [{text, format, content_type, points}]。

    zxing 默认已尝试旋转 / 反色 / 缩小，这里额外处理：
    小图放大重试（截图里的小二维码）、大图缩小重试（整屏巨型二维码）。
    """
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    barcodes = zxingcpp.read_barcodes(img)
    if not barcodes:
        w, h = img.size
        m = max(w, h)
        try:
            if m < 400:
                f = max(2, 800 // m)
                barcodes = zxingcpp.read_barcodes(
                    img.resize((w * f, h * f), Image.LANCZOS))
            elif m > 2400:
                sc = 1600.0 / m
                barcodes = zxingcpp.read_barcodes(
                    img.resize((int(w * sc), int(h * sc)), Image.LANCZOS))
        except Exception:
            pass

    results = []
    for b in barcodes:
        pts = [xy for xy in (
            _point_xy(getattr(b.position, "top_left", None)),
            _point_xy(getattr(b.position, "top_right", None)),
            _point_xy(getattr(b.position, "bottom_right", None)),
            _point_xy(getattr(b.position, "bottom_left", None)),
        ) if xy]
        fmt = getattr(b.format, "name", str(b.format))
        fmt = fmt.split(".")[-1]
        ct = getattr(b, "content_type", None)
        ct_name = getattr(ct, "name", str(ct)) if ct is not None else ""
        results.append({
            "text": b.text,
            "format": fmt,
            "content_type": CONTENT_TYPE_NAMES.get(ct_name, ct_name or "文本"),
            "points": pts,
        })
    return results


def describe_result(r):
    """生成结果摘要行：格式 · 类型（网址/WiFi 附加解析）。"""
    text = r["text"]
    desc = f'{r["format"]} · {r["content_type"]}'
    if URL_RE.match(text):
        desc += " · 网址"
    else:
        m = WIFI_RE.match(text.strip())
        if m:
            parts = []
            if m.group("s"):
                parts.append(f'SSID: {m.group("s")}')
            if m.group("p"):
                parts.append(f'密码: {m.group("p")}')
            if parts:
                desc += " · WiFi（" + "，".join(parts) + "）"
    return desc


# ---------------------------------------------------------------- 框选浮层


class SnipOverlay:
    """全屏框选浮层（性能优化版）。

    卡顿根源：Tk 的 stipple（抖动填充）矩形是纯软件逐像素合成，拖拽时在
    全屏画布上每帧重绘必然掉帧。本实现改为：
      * 背景一次性用 PIL 预合成"压暗版截图"（C 速度，仅一次开销）
      * 拖拽时只更新少量持久画布元素：选区内的原始亮图（小图 crop 极快）、
        细边框、四角手柄、尺寸标签，全部用 itemconfigure/coords 原地更新
      * 选区面积超过阈值时不再逐帧抠亮图，只画边框，任何大小都不卡
      * 窗口先出现（黑色 + 十字光标），背景截图随后贴上，启动体感即时
    """

    DIM = 0.45            # 选区外的压暗程度
    BIG_AREA = 2_500_000  # 选区像素数超过此值时不逐帧抠亮图

    def __init__(self, master, shot, on_done, on_cancel):
        self.master = master
        self.on_done = on_done
        self.on_cancel = on_cancel
        self.start = None
        self.shot = shot  # 截屏必须发生在浮层可见之前，否则会抓到自己
        self.vx, self.vy, vw, vh = virtual_screen()

        # 背景先在 PIL 里合成好（压暗 + 烘焙提示文字），窗口首次绘制即为完整画面
        dim = ImageEnhance.Brightness(shot).enhance(self.DIM)
        self._bake_hint(dim, vw)
        self._bg_img = ImageTk.PhotoImage(dim, master=master)

        self.top = tk.Toplevel(master)
        self.top.overrideredirect(True)
        self.top.geometry(f"{vw}x{vh}+{self.vx}+{self.vy}")
        self.top.attributes("-topmost", True)
        self.top.configure(cursor="crosshair", bg="black")

        self.canvas = tk.Canvas(self.top, width=vw, height=vh,
                                highlightthickness=0, bg="black")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_image(0, 0, image=self._bg_img, anchor="nw")

        # 持久画布元素，拖拽时只改坐标/内容，不删建
        self._img_item = self.canvas.create_image(0, 0, anchor="nw", state="hidden")
        self._line_item = self.canvas.create_rectangle(
            0, 0, 0, 0, outline="#00e5ff", width=2, state="hidden")
        self._label_item = self.canvas.create_text(
            0, 0, anchor="sw", fill="#00e5ff", font=("Consolas", 10),
            state="hidden")
        hs = max(3, int(4 * self.master.winfo_fpixels("1i") / 96))
        self._hs = hs
        self._handles = [self.canvas.create_rectangle(
            0, 0, 0, 0, fill="#00e5ff", outline="", state="hidden")
            for _ in range(4)]

        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.top.bind("<Escape>", lambda e: self.close(on_cancel))
        self.canvas.bind("<ButtonPress-3>", lambda e: self.close(on_cancel))

        self.top.focus_force()
        self.top.grab_set()

    # ---------- 背景准备 ----------

    def _bake_hint(self, dim, vw):
        """把提示文字直接烘进压暗背景里（零画布元素开销）。"""
        try:
            s = self.master.winfo_fpixels("1i") / 96.0
            font = ImageFont.truetype("msyh.ttc", int(15 * s))
            d = ImageDraw.Draw(dim)
            text = "拖拽框选二维码区域，Esc 或右键取消"
            w = d.textlength(text, font=font)
            x, y = (vw - w) / 2, 20 * s
            d.text((x + 1, y + 1), text, font=font, fill=(0, 0, 0))
            d.text((x, y), text, font=font, fill=(240, 240, 240))
        except Exception:
            pass  # 字体缺失只是没有提示文字，不影响功能

    # ---------- 拖拽 ----------

    def _press(self, e):
        self.start = (e.x, e.y)
        for it in [self._img_item, self._line_item, self._label_item,
                   *self._handles]:
            self.canvas.itemconfigure(it, state="hidden")

    def _drag(self, e):
        if not self.start or self.shot is None:
            return
        lx, rx = sorted((self.start[0], e.x))
        ty, by = sorted((self.start[1], e.y))
        if rx - lx < 2 or by - ty < 2:
            return
        c = self.canvas
        # 选区内显示原始亮图（小区域 crop+转换每帧 <2ms；大区域跳过防卡顿）
        if (rx - lx) * (by - ty) <= self.BIG_AREA:
            self._crop_img = ImageTk.PhotoImage(
                self.shot.crop((lx, ty, rx, by)), master=self.top)
            c.itemconfigure(self._img_item, image=self._crop_img, state="normal")
            c.coords(self._img_item, lx, ty)
        else:
            c.itemconfigure(self._img_item, state="hidden")
        c.coords(self._line_item, lx, ty, rx - 1, by - 1)
        c.itemconfigure(self._line_item, state="normal")
        label_y = ty - 8 if ty > 30 else by + 8
        c.itemconfigure(self._label_item, state="normal",
                        text=f"{rx - lx} x {by - ty}")
        c.coords(self._label_item, lx + 4, label_y)
        for i, (hx, hy) in enumerate(((lx, ty), (rx, ty), (lx, by), (rx, by))):
            c.coords(self._handles[i], hx - self._hs, hy - self._hs,
                     hx + self._hs, hy + self._hs)
            c.itemconfigure(self._handles[i], state="normal")

    def _release(self, e):
        if not self.start:
            return
        x0, y0 = self.start
        self.start = None
        lx, rx = sorted((x0, e.x))
        ty, by = sorted((y0, e.y))
        if rx - lx >= 10 and by - ty >= 10:
            crop = self.shot.crop((lx, ty, rx, by))
            self.close()
            self.on_done(crop)

    def close(self, cb=None):
        try:
            self.top.grab_release()
        except Exception:
            pass
        try:
            self.top.destroy()
        except Exception:
            pass
        if cb:
            cb()


# ---------------------------------------------------------------- 主界面


class App:
    def __init__(self, root):
        self.root = root
        self.current_results = []
        self.history = self._load_history()

        self._setup_fonts()
        self.s = root.winfo_fpixels("1i") / 96.0  # DPI 缩放系数
        self._build_ui()
        self._bind_keys()
        self._render_history()

        root.title(f"{APP_NAME} QReader v{APP_VERSION}")
        icon = os.path.join(app_dir(), "app.ico")
        if os.path.exists(icon):
            try:
                root.iconphoto(True, ImageTk.PhotoImage(file=icon))
            except Exception:
                pass
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 拖拽支持（可选依赖 tkinterdnd2）
        self._has_dnd = False
        try:
            from tkinterdnd2 import DND_FILES
            root.drop_target_register(DND_FILES)
            root.bind("<<Drop>>", self._on_drop)
            self._has_dnd = True
        except Exception:
            pass
        self._update_dnd_hint()

    # ---------- UI ----------

    def _setup_fonts(self):
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
            try:
                tkfont.nametofont(name).configure(family=FONT_FAMILY, size=9)
            except tk.TclError:
                pass

    def _px(self, v):
        return int(v * self.s)

    def _build_ui(self):
        r = self.root
        pad = {"padx": self._px(8), "pady": self._px(6)}

        # ---- 工具栏
        bar = ttk.Frame(r)
        bar.pack(fill="x", **pad)

        style = ttk.Style(r)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass

        self.btn_snip = tk.Button(bar, text="📷 框选识别", command=self.start_snip,
                                  bg="#0a8f5b", fg="white", activebackground="#0aa96d",
                                  activeforeground="white", relief="flat",
                                  padx=self._px(12), pady=self._px(4),
                                  font=(FONT_FAMILY, 10, "bold"), cursor="hand2")
        self.btn_snip.pack(side="left")
        self._tip(self.btn_snip, "隐藏本窗口，框选屏幕任意区域识别 (Ctrl+1)")

        tk.Button(bar, text="🖥 全屏识别", command=self.scan_fullscreen,
                  relief="flat", padx=self._px(12), pady=self._px(4),
                  font=(FONT_FAMILY, 10), cursor="hand2").pack(side="left", padx=(self._px(8), 0))
        tk.Button(bar, text="📂 打开图片", command=self.open_file,
                  relief="flat", padx=self._px(12), pady=self._px(4),
                  font=(FONT_FAMILY, 10), cursor="hand2").pack(side="left", padx=(self._px(8), 0))
        tk.Button(bar, text="📋 粘贴", command=self.paste_clipboard,
                  relief="flat", padx=self._px(12), pady=self._px(4),
                  font=(FONT_FAMILY, 10), cursor="hand2").pack(side="left", padx=(self._px(8), 0))

        self.var_autocopy = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="自动复制", variable=self.var_autocopy).pack(side="right")
        self.var_topmost = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="窗口置顶", variable=self.var_topmost,
                        command=self._apply_topmost).pack(side="right", padx=(0, self._px(10)))

        # ---- 中部：预览 + 结果
        mid = ttk.Frame(r)
        mid.pack(fill="both", expand=True, **pad)
        mid.columnconfigure(1, weight=1)
        mid.rowconfigure(0, weight=1)

        prev_frame = ttk.LabelFrame(mid, text=" 图片预览 ")
        prev_frame.grid(row=0, column=0, sticky="nsw", padx=(0, self._px(8)))
        self.preview_size = (self._px(340), self._px(300))
        holder = tk.Frame(prev_frame, width=self.preview_size[0],
                          height=self.preview_size[1], bg="#e9ebee")
        holder.pack(padx=self._px(6), pady=self._px(6))
        holder.pack_propagate(False)
        self.preview = tk.Label(holder, text="框选 / 打开 / 粘贴图片\n或把图片拖进本窗口",
                                bg="#e9ebee", fg="#777", justify="center",
                                font=(FONT_FAMILY, 9))
        self.preview.pack(fill="both", expand=True)
        self.preview_img = None  # 防止 PhotoImage 被回收

        res_frame = ttk.LabelFrame(mid, text=" 识别结果 ")
        res_frame.grid(row=0, column=1, sticky="nsew")
        res_frame.rowconfigure(1, weight=1)
        res_frame.columnconfigure(0, weight=1)

        self.lbl_desc = ttk.Label(res_frame, text="（暂无结果）", foreground="#555")
        self.lbl_desc.grid(row=0, column=0, sticky="w", padx=self._px(8), pady=(self._px(4), 0))

        self.txt_result = tk.Text(res_frame, height=6, wrap="char", relief="flat",
                                  bg="#fafafa", font=(FONT_FAMILY, 10))
        self.txt_result.grid(row=1, column=0, sticky="nsew", padx=self._px(8), pady=self._px(4))
        self.txt_result.configure(state="disabled")

        res_btns = ttk.Frame(res_frame)
        res_btns.grid(row=2, column=0, sticky="ew", padx=self._px(8), pady=(0, self._px(6)))
        self.btn_copy = tk.Button(res_btns, text="复制结果", command=self.copy_result,
                                  relief="flat", bg="#2b7cff", fg="white",
                                  activebackground="#1e63d6", activeforeground="white",
                                  padx=self._px(10), cursor="hand2", state="disabled")
        self.btn_copy.pack(side="left")
        self.btn_url = tk.Button(res_btns, text="打开链接", command=self.open_url,
                                 relief="flat", bg="#5f6368", fg="white",
                                 activebackground="#3c4043", activeforeground="white",
                                 padx=self._px(10), cursor="hand2", state="disabled")
        self.btn_url.pack(side="left", padx=(self._px(8), 0))

        # ---- 历史
        his = ttk.LabelFrame(r, text=" 历史记录（双击查看，右键操作） ")
        his.pack(fill="x", **pad)
        hb = ttk.Frame(his)
        hb.pack(fill="x", padx=self._px(6), pady=(self._px(4), 0))
        tk.Button(hb, text="清空", relief="flat", fg="#c62828",
                  cursor="hand2", command=self.clear_history).pack(side="right")
        self.listbox = tk.Listbox(his, height=5, activestyle="dotbox",
                                  font=(FONT_FAMILY, 9))
        self.listbox.pack(fill="x", padx=self._px(6), pady=(0, self._px(6)))
        self.listbox.bind("<Double-Button-1>", self._on_history_dbl)
        self.listbox.bind("<Button-3>", self._on_history_menu)
        self.hist_menu = tk.Menu(self.listbox, tearoff=0)
        self.hist_menu.add_command(label="复制内容", command=self.copy_history_item)
        self.hist_menu.add_command(label="删除该条", command=self.delete_history_item)

        # ---- 状态栏
        self.status = ttk.Label(r, text="就绪", relief="sunken", anchor="w",
                                padding=(self._px(6), self._px(2)))
        self.status.pack(fill="x", side="bottom")

    def _tip(self, widget, text):
        """轻量 tooltip。"""
        tip = {"win": None}

        def enter(_):
            tip["win"] = tw = tk.Toplevel(widget)
            tw.wm_overrideredirect(True)
            x = widget.winfo_rootx() + 10
            y = widget.winfo_rooty() + widget.winfo_height() + 4
            tw.wm_geometry(f"+{x}+{y}")
            tk.Label(tw, text=text, bg="#333", fg="white", justify="left",
                     font=(FONT_FAMILY, 9), padx=6, pady=3).pack()

        def leave(_):
            if tip["win"]:
                tip["win"].destroy()
                tip["win"] = None

        widget.bind("<Enter>", enter)
        widget.bind("<Leave>", leave)

    def _bind_keys(self):
        r = self.root
        # 注意：Tk 里 <Control-1> 是 Ctrl+鼠标左键，数字键必须用 <Control-Key-N>
        r.bind("<Control-Key-1>", lambda e: self.start_snip())
        r.bind("<Control-Key-2>", lambda e: self.scan_fullscreen())
        r.bind("<Control-o>", lambda e: self.open_file())
        r.bind("<Control-v>", lambda e: self.paste_clipboard())
        r.bind("<Control-c>", lambda e: self.copy_result() if self.current_results else None)

    def _apply_topmost(self):
        self.root.attributes("-topmost", self.var_topmost.get())

    def _update_dnd_hint(self):
        if not self._has_dnd:
            self.status.configure(text="就绪（提示：安装 tkinterdnd2 可支持拖拽图片）")

    # ---------- 识别入口 ----------

    def start_snip(self):
        self.root.withdraw()
        self.root.after(120, self._do_snip)  # 等待主窗口完成隐藏

    def _do_snip(self):
        try:
            shot = grab_screen()  # 必须在浮层显示前截屏，否则会抓到浮层自己
        except Exception as e:
            self.root.deiconify()
            messagebox.showerror(APP_NAME, f"截屏失败：{e}")
            return
        SnipOverlay(self.root, shot,
                    on_done=lambda img: self._snip_done(img),
                    on_cancel=lambda: self._snip_cancel())

    def _snip_cancel(self):
        self._restore_main()

    def _snip_done(self, crop):
        self._restore_main()
        self.process_image(crop, source="屏幕框选")

    def _restore_main(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def scan_fullscreen(self):
        self.set_status("正在截取全屏…")
        self.root.update_idletasks()
        try:
            shot = grab_screen()
        except Exception as e:
            messagebox.showerror(APP_NAME, f"截屏失败：{e}")
            return
        self.process_image(shot, source="全屏")

    def open_file(self):
        path = filedialog.askopenfilename(
            title="选择图片",
            filetypes=[("图片文件", "*.png;*.jpg;*.jpeg;*.bmp;*.gif;*.webp;*.tif;*.tiff"),
                       ("所有文件", "*.*")])
        if path:
            self.load_file(path)

    def load_file(self, path):
        try:
            img = Image.open(path)
            img.load()
        except Exception as e:
            messagebox.showerror(APP_NAME, f"无法打开图片：\n{path}\n\n{e}")
            return
        self.process_image(img, source=os.path.basename(path))

    def paste_clipboard(self):
        try:
            data = ImageGrab.grabclipboard()
        except Exception as e:
            messagebox.showerror(APP_NAME, f"读取剪贴板失败：{e}")
            return
        if isinstance(data, Image.Image):
            self.process_image(data, source="剪贴板")
        elif isinstance(data, list) and data:
            self.load_file(data[0])
        else:
            self.set_status("剪贴板中没有图片（可用 Win+Shift+S 截图后再粘贴）")

    def _on_drop(self, event):
        try:
            paths = self.root.tk.splitlist(event.data)
        except Exception:
            return
        for p in paths:
            if os.path.isfile(p):
                self.load_file(p)
                break

    # ---------- 处理与展示 ----------

    def process_image(self, img, source=""):
        self.set_status(f"正在识别…（{source}）")
        self.root.update_idletasks()
        self.root.configure(cursor="watch")
        t0 = time.perf_counter()
        try:
            results = decode_image(img)
        except Exception as e:
            results = []
            self.set_status(f"识别出错：{e}")
        self.root.configure(cursor="")
        cost = (time.perf_counter() - t0) * 1000

        self.show_preview(img, results)
        if not results:
            self.current_results = []
            self._set_result_text("")
            self.lbl_desc.configure(text="（未识别到二维码 / 条形码）")
            self.btn_copy.configure(state="disabled")
            self.btn_url.configure(state="disabled")
            self.set_status(f"未识别到条码 · {source} · {cost:.0f} ms")
            return

        self.current_results = results
        lines, descs = [], []
        for i, r in enumerate(results, 1):
            prefix = f"[{i}] " if len(results) > 1 else ""
            lines.append(prefix + r["text"])
            descs.append(describe_result(r))
        self._set_result_text("\n".join(lines))
        self.lbl_desc.configure(text="；".join(descs[:3]) + ("…" if len(descs) > 3 else ""))

        # 逐条写入历史
        now = datetime.datetime.now().strftime("%m-%d %H:%M:%S")
        for r in results:
            self._add_history({"time": now, "text": r["text"], "format": r["format"]})

        self.btn_copy.configure(state="normal")
        self.btn_url.configure(state="normal" if URL_RE.match(results[0]["text"].strip()) else "disabled")

        if self.var_autocopy.get():
            self._copy_text(results[0]["text"])
            self.set_status(f"识别到 {len(results)} 个条码，已自动复制 · {cost:.0f} ms")
        else:
            self.set_status(f"识别到 {len(results)} 个条码 · {cost:.0f} ms")

    def show_preview(self, img, results):
        """按预览框等比缩放图片，并把识别位置画上红框。"""
        pw, ph = self.preview_size
        im = img.convert("RGB").copy()
        im.thumbnail((pw - self._px(8), ph - self._px(8)))
        if results and img.width:
            sc = im.width / img.width
            draw = ImageDraw.Draw(im)
            lw = max(2, int(self.s))
            for r in results:
                pts = [(x * sc, y * sc) for x, y in r["points"]]
                if len(pts) >= 2:
                    xs = [p[0] for p in pts]
                    ys = [p[1] for p in pts]
                    draw.rectangle([min(xs), min(ys), max(xs), max(ys)],
                                   outline="#ff3b30", width=lw)
        self.preview_img = ImageTk.PhotoImage(im, master=self.root)
        self.preview.configure(image=self.preview_img, text="", width=im.width, height=im.height)

    def _set_result_text(self, text):
        self.txt_result.configure(state="normal")
        self.txt_result.delete("1.0", "end")
        self.txt_result.insert("1.0", text)
        self.txt_result.configure(state="disabled")

    def set_status(self, text):
        self.status.configure(text=text)

    # ---------- 复制 / 链接 ----------

    def _copy_text(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def copy_result(self):
        if not self.current_results:
            return
        text = "\n".join(r["text"] for r in self.current_results)
        self._copy_text(text)
        self.set_status("已复制到剪贴板")

    def open_url(self):
        if not self.current_results:
            return
        url = self.current_results[0]["text"].strip()
        if URL_RE.match(url):
            os.startfile(url)  # noqa 仅接受 http/https/ftp 开头
        else:
            self.set_status("当前结果不是网址")

    # ---------- 历史 ----------

    def _load_history(self):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return [d for d in data if isinstance(d, dict) and "text" in d]
        except Exception:
            pass
        return []

    def _save_history(self):
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.history[-100:], f, ensure_ascii=False, indent=1)
        except Exception:
            pass

    def _add_history(self, item):
        self.history.append(item)
        if len(self.history) > 100:
            self.history = self.history[-100:]
        self._save_history()
        self._render_history()

    def _render_history(self):
        self.listbox.delete(0, "end")
        for item in reversed(self.history):  # 最新在最上
            text = item.get("text", "").replace("\n", " ")
            label = f'{item.get("time", "")} [{item.get("format", "?")}] {text[:46]}'
            self.listbox.insert("end", label)

    def _sel_history_item(self):
        sel = self.listbox.curselection()
        if not sel:
            return None
        idx = len(self.history) - 1 - sel[0]
        if 0 <= idx < len(self.history):
            return self.history[idx]
        return None

    def _on_history_dbl(self, _):
        item = self._sel_history_item()
        if not item:
            return
        text = item.get("text", "")
        fake = {"text": text, "format": item.get("format", "QRCode"),
                "content_type": "文本", "points": []}
        self.current_results = [fake]
        self._set_result_text(text)
        self.lbl_desc.configure(text=f'{item.get("format", "")} · 来自历史记录')
        self.btn_copy.configure(state="normal")
        self.btn_url.configure(state="normal" if URL_RE.match(text.strip()) else "disabled")
        self.set_status("已载入历史记录（仅查看，预览不可用）")

    def _on_history_menu(self, event):
        if self.listbox.nearest(event.y) < 0:
            return
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(self.listbox.nearest(event.y))
        self.hist_menu.tk_popup(event.x_root, event.y_root)

    def copy_history_item(self):
        item = self._sel_history_item()
        if item:
            self._copy_text(item.get("text", ""))
            self.set_status("已复制历史内容")

    def delete_history_item(self):
        item = self._sel_history_item()
        if item:
            self.history.remove(item)
            self._save_history()
            self._render_history()

    def clear_history(self):
        if self.history and messagebox.askyesno(APP_NAME, "确定清空全部历史记录？"):
            self.history = []
            self._save_history()
            self._render_history()

    def _on_close(self):
        self._save_history()
        self.root.destroy()


# ---------------------------------------------------------------- 入口


def main():
    enable_dpi_awareness()

    def excepthook(t, v, tb):
        try:
            with open(os.path.join(data_dir(), "error.log"), "a", encoding="utf-8") as f:
                f.write("".join(traceback.format_exception(t, v, tb)) + "\n")
        except Exception:
            pass
        traceback.print_exception(t, v, tb)

    sys.excepthook = excepthook

    try:
        from tkinterdnd2 import TkinterDnD
        root = TkinterDnD.Tk()
    except Exception:
        root = tk.Tk()

    app = App(root)

    # 命令行传入图片则启动即识别
    for arg in sys.argv[1:]:
        if os.path.isfile(arg):
            root.after(200, lambda p=arg: app.load_file(p))
            break

    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    w, h = int(760 * app.s), int(560 * app.s)
    root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 3}")
    root.minsize(int(640 * app.s), int(480 * app.s))
    root.mainloop()


if __name__ == "__main__":
    main()
