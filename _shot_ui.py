# -*- coding: utf-8 -*-
"""用 PrintWindow 抓取 Tk 窗口自身的绘制内容，输出 PNG 供肉眼比对设计稿。

⚠ 本沙箱 `BitBlt(GetDC(0))` 抓不到 Tk 窗口（只出壁纸），只有
`PrintWindow(hwnd, dc, PW_RENDERFULLCONTENT=2)` 能拿到窗口自绘内容。
⚠ 它会跳过 acrylic backdrop（DWM 层），所以截图里窗口底是纯黑/掩膜色，
  这不代表屏幕实际效果——玻璃只能靠真机看。
"""
import ctypes
import os
import sys
from ctypes import wintypes

ctypes.windll.shcore.SetProcessDpiAwareness(2)
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowDC.argtypes = [wintypes.HWND]
user32.GetWindowDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
user32.PrintWindow.restype = wintypes.BOOL
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


def toplevel_hwnd(hwnd):
    parent = user32.GetParent(wintypes.HWND(hwnd))
    return int(parent) if parent else int(hwnd)


def grab(hwnd, path):
    from PIL import Image
    hwnd = toplevel_hwnd(hwnd)
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
    bi.bmiHeader.biHeight = -h            # 负数 = 自上而下
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
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    # ⚠ 配置隔离：截图脚本绝不能读写用户真实 config.ini。
    # 之前直接跑真实 App，输入框 <FocusOut> 触发自动保存，把用户 API Key
    # 覆盖成空值（2026-10-25 真丢过）。用临时配置后彻底隔离。
    import tempfile
    _td = tempfile.mkdtemp(prefix="dsbv_shot_")
    os.environ["DSBV_CONFIG"] = os.path.join(_td, "config.ini")
    # ⚠ 历史也要隔离：截图脚本同样会走 save_snapshot()，样例余额一旦写进
    # 用户真实 history.json，就会被算成"消耗"（2026-10-25 踩过）。
    os.environ["DSBV_HISTORY"] = os.path.join(_td, "history.json")
    import ui

    global SUF
    # ⚠ 这里**故意不做任何 monkeypatch**：走 App 的真实启动路径。
    # 之前用 --nog 把 apply_window_glass 打成失效，结果实底截图很漂亮、
    # 真机却因为 acrylic 把整窗文字糊掉而"完全看不清"——
    # 验证必须覆盖用户真正会跑的那条路径。
    #   python _shot_ui.py           → 默认（实底，清晰）
    #   python _shot_ui.py --glass   → 强制开启真玻璃，用于对比取证
    WITH_GLASS = "--glass" in sys.argv
    SUF = "_ui_glass" if WITH_GLASS else "_ui_real"
    if WITH_GLASS:
        # 直接打桩开关判定，比改 DEFAULTS 可靠（config.ini 里可能已落盘 false）
        ui.App._glass_enabled = lambda self: True
        print("[mode] 强制开启真 acrylic（预期：_audit_contrast 判 FAIL，) "
              "仅作「为什么默认关闭」的反面取证")
    else:
        print("[mode] 真实默认路径（实底）")

    # 注入 7 天假历史（不写盘），用于验证走势图与消耗统计的真实渲染
    import time as _t
    import history as histmod
    from datetime import datetime as _dt
    base, now = 40.0, _t.time()
    fake_hist = []
    for i in range(48):
        ts = now - (48 - i) * 4 * 3600
        fake_hist.append({
            "ts": ts, "time": _dt.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S"),
            "balance": round(base - i * 0.62, 2), "currency": "CNY"})
    fake_hist[-1]["balance"] = 12.34
    histmod.load_history = lambda: list(fake_hist)
    histmod.save_snapshot = lambda b, c: (fake_hist.append(
        {"ts": now, "time": _dt.now().strftime("%Y-%m-%d %H:%M:%S"),
         "balance": b, "currency": c}), fake_hist)[-1]

    app = ui.App()
    app.update()
    fake = {"is_available": True, "infos": [{
        "currency": "CNY", "total_balance": 12.34,
        "granted_balance": 5.00, "topped_up_balance": 7.34}]}
    app._fill_price()
    app._fill_from_balance(fake)
    app._data["net_down"] = "499 KB/s"
    app._data["net_up"] = "12 KB/s"
    app.refresh_view()
    app.update()
    app.lift()
    app.update()

    print(f"[state] config glass = {app.config_obj.get('ui', 'glass', 'false')!r}"
          f"  window_glass_on = {app.view.glass_on}")
    for t in ("light", "dark"):
        if app.theme != t:
            app._toggle_theme()
        for _ in range(8):
            app.update()
        fn = f"{SUF}_{t}.png"
        w, h = grab(app.winfo_id(), fn)
        print(f"{t:5s} -> {fn}  {w}x{h}  theme={app.theme}"
              f"  glass={app.view.glass_on}")

    # 迷你卡：单独截图（无边框 Toplevel，PrintWindow 同样适用）
    try:
        # 迷你卡：强制显示全部项 + 关闭缓动，确保拍到最终布局
        for _k in app.mini_show_vars:
            app.mini_show_vars[_k].set(True)
        app._open_mini()
        app.update()
        for _ in range(4):
            app.update()
        app._mini_autosize(animate=False)
        for _ in range(10):
            app.update()
        mn = app.mini
        if mn is not None:
            fn = f"{SUF}_mini.png"
            w, h = grab(mn.winfo_id(), fn)
            print(f"mini  -> {fn}  {w}x{h}  glass={app._glass_on}")
            # 迷你卡的真机 1:1 效果图（PIL 位图，不经过 PrintWindow）
            pf = f"{SUF}_mini_preview.png"
            if app.mini_view.export(pf):
                print(f"mini  -> {pf}  (真机 1:1 位图)  theme={app.theme}")
    except Exception as e:
        print("mini shot failed:", e)

    app.tray_mgr.stop()
    app.destroy()

    # 截图后立刻做对比度审计：把「看不清」变成硬门禁，
    # 不再依赖"我看截图觉得还行"这种主观判断。
    import _audit_contrast
    rc = 0
    for t in ("light", "dark"):
        fn = f"{SUF}_{t}.png"
        if os.path.exists(fn):
            rc |= _audit_contrast.audit(fn, t)
    return rc


if __name__ == "__main__":
    sys.exit(main())
