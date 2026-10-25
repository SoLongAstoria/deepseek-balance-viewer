# -*- coding: utf-8 -*-
"""截图验证：启动新打包 exe 的迷你窗，抓取含网速块的真实渲染。

要点（踩坑备忘）：
- 本渲染脚本**不调** SetProcessDpiAwareness，保持 DPI-unaware；
  应用本体是 DPI-aware 的，故坐标需按 SCALE 换算，否则抓偏/裁切。
- 只抓迷你窗所在的屏幕右上角一小块，避免抓到无关桌面内容。
"""
import ctypes
import os
import subprocess
import time
from ctypes import wintypes

from PIL import ImageGrab

SCALE = 1.25  # 本机 125% 缩放
HERE = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(HERE, "dist", "DeepSeekBalanceViewer.exe")

user32 = ctypes.windll.user32
logical_w = user32.GetSystemMetrics(0)
logical_h = user32.GetSystemMetrics(1)
print("logical screen: %dx%d  (physical approx %dx%d)"
      % (logical_w, logical_h, int(logical_w * SCALE), int(logical_h * SCALE)))

proc = subprocess.Popen([EXE, "--mini"])
print("launched pid", proc.pid)
time.sleep(6.0)  # 等余额拉取 + 网速第一次采样（1s 间隔）

found = []


def cb(hwnd, lparam):
    if not user32.IsWindowVisible(hwnd):
        return True
    cls = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls, 256)
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    if cls.value == "TkTopLevel":
        found.append((int(hwnd), r.left, r.top, r.right, r.bottom))
    return True


WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows(WNDENUMPROC(cb), 0)

print("TkTopLevel windows found:", len(found))
for h, l, t, rr, b in found:
    print("  hwnd=%d rect=(%d,%d)-(%d,%d) size=%dx%d" % (h, l, t, rr, b, rr - l, b - t))

if not found:
    print("NO_TK_WINDOW")
    proc.terminate()
    raise SystemExit(1)

# 取最靠右上、尺寸最小的那个（迷你窗）
h, l, t, rr, b = min(found, key=lambda x: (x[1] + x[2], (x[3] - x[1]) * (x[4] - x[2])))
w, ht = rr - l, b - t
print("picked mini: rect=(%d,%d) size=%dx%d" % (l, t, w, ht))

# 两套坐标解释各抓一张，肉眼挑正确的那张
for tag, f in (("phys", 1.0), ("logi", SCALE)):
    x1 = max(0, int((l - 40) * f))
    y1 = max(0, int((t - 30) * f))
    x2 = min(int(logical_w * SCALE), int((rr + 40) * f))
    y2 = min(int(logical_h * SCALE), int((b + 40) * f))
    img = ImageGrab.grab(bbox=(x1, y1, x2, y2))
    out = os.path.join(HERE, "_shot_mini_%s.png" % tag)
    img.save(out)
    print("saved %s bbox=(%d,%d,%d,%d) size=%s" % (out, x1, y1, x2, y2, img.size))

proc.terminate()
try:
    proc.wait(timeout=5)
except Exception:
    proc.kill()
print("SHOT_DONE")
