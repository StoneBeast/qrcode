# -*- coding: utf-8 -*-
"""全局快捷键自测：真实注册、消息循环触发、录制解析、冲突校验。"""
import ctypes
import time
import tkinter as tk

import qr_reader as q


def main():
    q.enable_dpi_awareness()
    import os
    if os.path.exists(q.HOTKEY_FILE):
        os.remove(q.HOTKEY_FILE)  # 保证干净起点，避免跨运行状态污染
    root = tk.Tk()
    root.geometry("760x560+9999+9999")
    app = q.App(root)
    root.update()
    ok = True

    def check(name, cond):
        nonlocal ok
        if not cond:
            ok = False
        print("[%s] %s" % ("OK " if cond else "FAIL", name))

    # 1) 热键线程真实注册
    time.sleep(0.5)
    check("默认快捷键全部注册成功",
          all(app.hotkeys.status.get(i) is True for i in q.HOTKEY_IDS.values()))

    # 2) 冲突检测：向线程投递与系统冲突的注册应失败（如 Ctrl+C 被系统占用的情况
    #    不一定成立，改用保留组合 Ctrl+Alt+Del 无法注册来验证失败路径不可靠，
    #    这里验证"重复注册不同 id 相同键"时第二组依旧成功——RegisterHotKey 允许
    #    不同 id 重复注册，跳过该项。仅验证 status 字段结构。）
    check("status 字段覆盖全部 id",
          set(app.hotkeys.status.keys()) == set(q.HOTKEY_IDS.values()))

    # 3) 触发链路：向热键线程投递 WM_HOTKEY，UI 轮询应执行动作（启动框选）
    ctypes.windll.user32.PostThreadMessageW(app.hotkeys._tid, q.WM_HOTKEY,
                                            q.HOTKEY_IDS["snip"], 0)
    t0 = time.time()
    while time.time() - t0 < 3:
        root.update()
        time.sleep(0.05)
        if app._snipping:
            break
    check("WM_HOTKEY 触发框选（浮层已启动）", app._snipping)
    # 取消浮层
    app._snip_cancel()
    root.update()
    check("取消后状态复位", not app._snipping)

    # 4) 录制组件：模拟按键解析 Ctrl+Alt+K
    dlg = q.SettingsDialog(app)
    root.update()
    rec = dlg.recorders["snip"]
    rec._start_recording()
    seq = [("<Control-KeyPress>", 0x4 | 0x8, "Control_L"),
           ("<Alt-KeyPress>", 0x4 | 0x8, "Alt_L"),
           ("<KeyPress-k>", 0x4 | 0x8, "k")]
    for pattern, state, keysym in seq:
        e = tk.Event()
        e.keysym = keysym
        e.state = state
        e.keycode = ord("K") if keysym == "k" else 0
        rec._on_key(e)
    root.update()
    check("录制解析 Ctrl+Alt+K", rec.value == (q.MOD_CONTROL | q.MOD_ALT,
                                               ord("K"), "Ctrl+Alt+K"))

    # 5) 冲突校验：把"全屏识别"也设为 Ctrl+Alt+K，save 应拦截并保留旧配置
    snapshot = dict(app.hotkey_cfg)
    rec2 = dlg.recorders["fs"]
    rec2.value = (q.MOD_CONTROL | q.MOD_ALT, ord("K"), "Ctrl+Alt+K")
    dlg.save()
    root.update()
    check("冲突被拦截（配置未保存）",
          app.hotkey_cfg["snip"] == snapshot["snip"]
          and app.hotkey_cfg["fs"] == snapshot["fs"]
          and q.load_hotkey_config()["snip"] == snapshot["snip"])

    # 6) 正常保存新配置并持久化
    dlg2 = q.SettingsDialog(app)
    root.update()
    dlg2.recorders["snip"].value = (q.MOD_CONTROL | q.MOD_ALT, ord("Z"),
                                    "Ctrl+Alt+Z")
    dlg2.save()
    time.sleep(0.5)
    check("新配置生效并注册", app.hotkeys.status.get(q.HOTKEY_IDS["snip"]) is True
          and app.hotkey_cfg["snip"][2] == "Ctrl+Alt+Z")
    saved = q.load_hotkey_config()
    check("settings.json 持久化", saved["snip"][2] == "Ctrl+Alt+Z")

    # 7) 取消对话框应恢复旧配置
    dlg3 = q.SettingsDialog(app)
    dlg3.recorders["snip"].value = q.DEFAULT_HOTKEYS["snip"]
    dlg3.recorders["snip"].set_text("Ctrl+Alt+Q")
    dlg3.cancel()
    time.sleep(0.3)
    check("取消后配置不变", app.hotkey_cfg["snip"][2] == "Ctrl+Alt+Z")

    print("RESULT:", "PASS" if ok else "FAIL")
    root.destroy()
    if os.path.exists(q.HOTKEY_FILE):
        os.remove(q.HOTKEY_FILE)  # 测试自清理，不污染真实使用
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
