# -*- coding: utf-8 -*-
"""ModernButton 悬停/禁用状态自测（event_generate 注入，不依赖真实鼠标）。"""
import tkinter as tk

import qr_reader as q


def main():
    q.enable_dpi_awareness()
    root = tk.Tk()
    root.geometry("760x560+9999+9999")  # 屏幕外：可见（Enter 需要可映射窗口）但不打扰用户
    app = q.App(root)
    root.update()

    btn = app.btn_snip
    normal = btn.itemcget(btn._rect, "fill")

    btn.event_generate("<Enter>", x=10, y=10)
    root.update()
    hover = btn.itemcget(btn._rect, "fill")
    # tooltip 的 Toplevel 挂在按钮(canvas)下，递归查找整棵组件树
    def all_children(w):
        out = []
        for c in w.winfo_children():
            out.append(c)
            out.extend(all_children(c))
        return out
    tls = [w for w in all_children(root)
           if isinstance(w, tk.Toplevel) and w.winfo_ismapped()]
    print("normal fill:", normal)
    print("hover  fill:", hover)
    print("hover changed:", normal != hover)
    print("tooltip popped:", len(tls) > 0)

    btn.event_generate("<Leave>", x=10, y=300)
    root.update()
    back = btn.itemcget(btn._rect, "fill")
    print("leave restore ok:", back == normal)

    # 禁用态兼容 configure(state=...)
    app.btn_copy.configure(state="disabled")
    root.update()
    dis = app.btn_copy.itemcget(app.btn_copy._rect, "fill")
    print("disabled fill:", dis)
    app.btn_copy.configure(state="normal")
    root.update()
    print("re-enable fill:", app.btn_copy.itemcget(app.btn_copy._rect, "fill"))

    ok = (normal != hover and back == normal and dis == "#ececee"
          and len(tls) > 0)
    print("RESULT:", "PASS" if ok else "FAIL")
    root.destroy()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
