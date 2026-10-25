# -*- coding: utf-8 -*-
"""启动新包迷你窗（液态玻璃），截一张渲染证据（含圆角卡 + 柔和阴影 + 桌面背景）。

多屏安全截图法：
  进程设 Per-Monitor DPI aware(V2) 后，`GetWindowRect` 直接返回**物理像素**屏幕坐标；
  抓图用 GDI `BitBlt(GetDC(0))` —— 该 DC 覆盖整个**虚拟桌面**（多屏），坐标 = 虚拟桌面
  左上起的物理像素，与上面同系，因此能抓到副屏上的窗口。
  （PIL ImageGrab.grab(bbox=) 只覆盖主屏，副屏区会得全黑；单屏 ×SCALE 法在副屏会算到
   副屏外、同样全黑。）
用法：`python _shot_glass.py <light|dark|""> [tag]`
"""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes
from PIL import Image

# 尽早声明 Per-Monitor DPI aware，使后续坐标获取走物理像素
_DPI_OK = False
try:
    if ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0:  # S_OK
        _DPI_OK = True
except Exception:
    _DPI_OK = False

SCALE = 1.0 if _DPI_OK else 1.25   # aware=物理坐标直接可用；否则按单屏 125% 换算
PAD = 40                           # 截图外扩（物理像素），纳入圆角外柔和阴影与桌面
EXE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "dist3", "DeepSeekBalanceViewer.exe")

_user32 = ctypes.windll.user32
_gdi32 = ctypes.windll.gdi32
_IsWindowVisible = _user32.IsWindowVisible
_GetClassNameW = _user32.GetClassNameW
_GetWindowRect = _user32.GetWindowRect

# 关键：给这些 API 设 argtypes/restype，让 64 位句柄走 c_void_p。
# 不设的话 ctypes 默认按 32 位 c_int 传句柄，句柄值 >2^31 时抛
# "argument 1: OverflowError: int too long to convert"（偶发，取决于本次句柄值）。
_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
_user32.EnumWindows.argtypes = [_WNDENUMPROC, wintypes.LPARAM]
_user32.EnumWindows.restype = wintypes.BOOL
_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.IsWindowVisible.restype = wintypes.BOOL
_user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.GetClassNameW.restype = ctypes.c_int
_user32.GetWindowRect.argtypes = [wintypes.HWND,
                                  ctypes.POINTER(wintypes.RECT)]
_user32.GetWindowRect.restype = wintypes.BOOL


class _BIH(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


class _BMI(ctypes.Structure):
    _fields_ = [("bmiHeader", _BIH), ("bmiColors", wintypes.DWORD * 3)]


def _grab_virtual_desktop(box):
    """GDI BitBlt 抓取**虚拟桌面**任意物理区域（支持副屏）。box 为物理像素。"""
    x, y, x2, y2 = box
    w, h = x2 - x, y2 - y
    if w <= 0 or h <= 0:
        return None
    _user32.GetDC.argtypes = [wintypes.HWND]
    _user32.GetDC.restype = wintypes.HDC
    _user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    _gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    _gdi32.CreateCompatibleDC.restype = wintypes.HDC
    _gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int,
                                              ctypes.c_int]
    _gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    _gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    _gdi32.SelectObject.restype = wintypes.HGDIOBJ
    _gdi32.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int,
                              ctypes.c_int, ctypes.c_int, wintypes.HDC,
                              ctypes.c_int, ctypes.c_int, wintypes.DWORD]
    _gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT,
                                 wintypes.UINT, wintypes.LPVOID,
                                 ctypes.POINTER(_BMI), wintypes.UINT]
    _gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    _gdi32.DeleteObject.restype = wintypes.BOOL
    _gdi32.DeleteDC.argtypes = [wintypes.HDC]
    _gdi32.DeleteDC.restype = wintypes.BOOL
    hdc = _user32.GetDC(0)
    if not hdc:
        return None
    try:
        mdc = _gdi32.CreateCompatibleDC(hdc)
        bmp = _gdi32.CreateCompatibleBitmap(hdc, w, h)
        _gdi32.SelectObject(mdc, bmp)
        _gdi32.BitBlt(mdc, 0, 0, w, h, hdc, x, y, 0x00CC0020)  # SRCCOPY
        bi = _BMI()
        bi.bmiHeader.biSize = ctypes.sizeof(_BIH)
        bi.bmiHeader.biWidth = w
        bi.bmiHeader.biHeight = -h          # top-down 行序
        bi.bmiHeader.biPlanes = 1
        bi.bmiHeader.biBitCount = 32
        bi.bmiHeader.biCompression = 0      # BI_RGB
        buf = ctypes.create_string_buffer(w * h * 4)
        _gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
        img = Image.frombuffer("RGBX", (w, h), buf, "raw", "BGRX", 0, 1)
        _gdi32.DeleteObject(bmp)
        _gdi32.DeleteDC(mdc)
        return img
    finally:
        _user32.ReleaseDC(0, hdc)


def _find_tk_windows():
    """所有可见 TkTopLevel 窗口 [(hwnd, (l, t, r, b))]。迷你卡 + 投影层都在内。"""
    out = []

    def cb(hwnd, _):
        if not _IsWindowVisible(hwnd):
            return True
        cls = ctypes.create_unicode_buffer(64)
        _GetClassNameW(hwnd, cls, 64)
        if cls.value != "TkTopLevel":
            return True
        r = wintypes.RECT()
        _GetWindowRect(hwnd, ctypes.byref(r))
        out.append((hwnd, (r.left, r.top, r.right, r.bottom)))
        return True

    CMP = _WNDENUMPROC
    _user32.EnumWindows(CMP(cb), 0)
    return out


def _pick_card(wins):
    """迷你卡 = 面积最小的可见 TkTopLevel（投影层比它大一圈且偏右下）。"""
    if not wins:
        return None

    def area(w):
        l, t, r, b = w[1]
        return (r - l) * (b - t)
    return min(wins, key=lambda w: (area(w), w[1][0] + w[1][1]))


def _set_theme(theme):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import config as cfg
    c = cfg.Config()
    c.set("ui", "mini_theme", theme)   # "" = 跟随系统；light / dark = 固定
    c.save()


def _capture(tag):
    card = None
    for _ in range(48):
        card = _pick_card(_find_tk_windows())
        if card:
            break
        time.sleep(0.25)
    if not card:
        print(f"[{tag}] 未找到迷你窗")
        return
    # 等尺寸稳定：autosize 缓动 + 内容渲染完成前会停在 230x150 初始态，
    # 连续多次尺寸一致才认为稳定（避免截到动画中间态）
    last, stable, cur = None, 0, card
    for _ in range(40):
        cur = _pick_card(_find_tk_windows()) or cur
        l, t, r, b = cur[1]
        size = (r - l, b - t)
        stable = stable + 1 if size == last else 0
        last = size
        if stable >= 4:
            break
        time.sleep(0.2)
    hwnd, (l, t, r, b) = cur
    time.sleep(1.0)   # 等 acrylic backdrop 合成/淡入完成再截
    box = (max(0, int(l * SCALE) - PAD), max(0, int(t * SCALE) - PAD),
           int(r * SCALE) + PAD, int(b * SCALE) + PAD)
    img = _grab_virtual_desktop(box)
    if img is None:
        print(f"[{tag}] 抓图失败")
        return
    img = img.convert("RGB")   # RGBX 不能直接存 PNG
    out = f"glass_{tag}_proof.png"
    img.save(out)
    print(f"[{tag}] DPI_OK={_DPI_OK} 卡 {r-l}x{b-t} @({l},{t}) -> {out} {img.size}")


if __name__ == "__main__":
    theme = sys.argv[1] if len(sys.argv) > 1 else ""
    tag = sys.argv[2] if len(sys.argv) > 2 else (theme or "auto")
    _set_theme(theme)
    p = subprocess.Popen([EXE, "--mini"])
    time.sleep(2.2)
    try:
        _capture(tag)
    finally:
        p.terminate()
        try:
            p.wait(timeout=3)
        except Exception:
            p.kill()
