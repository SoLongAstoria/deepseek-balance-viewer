# -*- coding: utf-8 -*-
"""探针：验证迷你窗 region 真的把**四个角**都切掉了（SetWindowRgn 返回 True 不算数）。

真机问题是「四角有黑底」，成因是 w/h 是物理像素却被 set_round_region 又乘了
一次 DPI 缩放 → region 比窗口大 25% → 只剩左上角那个圆弧落在窗口内，
右上 / 左下 / 右下三个角全是直角，露出窗口底色（#1C1D22，看着就是黑角）。

跑法: build-venv/Scripts/python.exe _probe_region.py
"""
import os
import tempfile

os.environ.setdefault("DSBV_CONFIG",
                      os.path.join(tempfile.mkdtemp(), "probe.ini"))

# ⚠ 必须开启 DPI 感知，否则 GetDpiForWindow 恒返回 96（虚拟化），
# 复现不了真机 125% 缩放下「region 被二次缩放」的 bug。
try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

import tkinter as tk

import glass

W, H, R = 375, 145, 23          # 物理像素尺寸 + 圆角（= 18 * 1.25）


def corners_cut(win, s):
    """按逻辑像素取四个角的内侧点，返回每个角是否被 region 裁掉。"""
    lw, lh = W / s, H / s
    pts = {"TL": (1, 1), "TR": (lw - 2, 1),
           "BL": (1, lh - 2), "BR": (lw - 2, lh - 2)}
    return {k: glass.region_corner_cut(win, x, y) for k, (x, y) in pts.items()}


root = tk.Tk()
root.withdraw()
w = tk.Toplevel(root)
w.overrideredirect(True)
w.geometry(f"{W}x{H}+200+200")
w.update()

s = glass.dpi_scale(w)
print("dpi_scale      :", s)

bad = glass.set_round_region(w, W, H, R)          # 旧写法：物理像素当逻辑
old = corners_cut(w, s)
print("old(physical=False) ret=%-5s %s" % (bad, old))

ok = glass.set_round_region(w, W, H, R, physical=True)
new = corners_cut(w, s)
print("new(physical=True)  ret=%-5s %s" % (ok, new))
print("center_in      :", not glass.region_corner_cut(
    w, W / s / 2, H / s / 2))
w.destroy()
root.destroy()

assert ok, "SetWindowRgn 调用失败"
assert all(new.values()), f"region 未把四角全部切掉：{new}"
print("RESULT: PASS")
