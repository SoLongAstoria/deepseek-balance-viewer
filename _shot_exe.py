# -*- coding: utf-8 -*-
"""跨进程截图：启动打包好的 exe，用 PrintWindow 抓它自己的窗口内容。

为什么要单独验：用户日常双击的是 dist/*.exe——它是**打包那一刻的源码快照**，
源码截图正确不代表 exe 里正确（uikit / PIL / 字体没打进去就白改了）。

⚠ 本沙箱 BitBlt(GetDC(0)) 抓不到 Tk 窗口，只能 PrintWindow。
⚠ acrylic backdrop 属 DWM 合成层，PrintWindow 抓不到 → 图里窗底是掩膜色，
  真实玻璃效果只能真机肉眼确认。
"""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes

ctypes.windll.shcore.SetProcessDpiAwareness(2)
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
user32.PrintWindow.restype = wintypes.BOOL
user32.GetWindowDC.argtypes = [wintypes.HWND]
user32.GetWindowDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.GetParent.argtypes = [wintypes.HWND]
user32.GetParent.restype = wintypes.HWND
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER),
                ("bmiColors", wintypes.DWORD * 3)]


gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT,
                            wintypes.UINT, ctypes.c_void_p,
                            ctypes.POINTER(BITMAPINFO), wintypes.UINT]
gdi32.GetDIBits.restype = ctypes.c_int

ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def find_window(keyword):
    """枚举顶层窗口，按标题关键字找目标（返回 hwnd, title）。"""
    hits = []

    def cb(hwnd, _lp):
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 2)
        user32.GetWindowTextW(hwnd, buf, n + 2)
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if keyword in buf.value and cls.value.startswith("Tk"):
            hits.append((int(hwnd), buf.value, cls.value))
        return True

    user32.EnumWindows(ENUMPROC(cb), 0)
    return hits[0] if hits else None


def grab(hwnd, path):
    from PIL import Image
    hwnd = int(user32.GetParent(wintypes.HWND(hwnd)) or hwnd)
    r = wintypes.RECT()
    user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    if w <= 0 or h <= 0:
        raise RuntimeError("窗口尺寸无效")
    hdc = user32.GetWindowDC(wintypes.HWND(hwnd))
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    old = gdi32.SelectObject(mdc, bmp)
    user32.PrintWindow(wintypes.HWND(hwnd), mdc, 2)
    bi = BITMAPINFO()
    bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.bmiHeader.biWidth = w
    bi.bmiHeader.biHeight = -h
    bi.bmiHeader.biPlanes = 1
    bi.bmiHeader.biBitCount = 32
    bi.bmiHeader.biCompression = 0
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
    img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1)
    img.convert("RGB").save(path)
    gdi32.SelectObject(mdc, old)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(wintypes.HWND(hwnd), hdc)
    return w, h


def main():
    exe = sys.argv[1] if len(sys.argv) > 1 else "dist/DeepSeekBalanceViewer.exe"
    out = sys.argv[2] if len(sys.argv) > 2 else "_exe_shot.png"
    exe = os.path.abspath(exe)
    print("launch:", exe)
    # 隔离配置：让 exe 用临时 config，绝不读写用户真实 Key
    import tempfile
    env = dict(os.environ)
    env["DSBV_CONFIG"] = os.path.join(
        tempfile.mkdtemp(prefix="dsbv_exe_"), "config.ini")
    p = subprocess.Popen([exe], env=env)
    try:
        hit = None
        for _ in range(40):
            time.sleep(0.5)
            hit = find_window("DeepSeek")
            if hit:
                break
        if not hit:
            print("FAIL: 找不到 exe 窗口（可能启动崩溃）")
            return 1
        hwnd, title, cls = hit
        print(f"window: hwnd={hwnd} class={cls} title={title!r}")
        time.sleep(2.0)
        w, h = grab(hwnd, out)
        print(f"OK: {out}  {w}x{h}")
        return 0
    finally:
        try:
            p.terminate()
        except Exception:
            pass
        time.sleep(0.6)
        subprocess.run(["taskkill", "/F", "/IM",
                        os.path.basename(exe)], capture_output=True)


if __name__ == "__main__":
    sys.exit(main())
