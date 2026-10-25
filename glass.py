# -*- coding: utf-8 -*-
"""桌面迷你窗「液态玻璃」视觉的 Windows 原生能力封装（零依赖，ctypes）。

真·液态玻璃配方（2026-10-25 对照 pywinstyles 源码逐行修正，Win11 26300 实测）：
  1. 窗口底色设为**纯黑** —— 黑色像素即「玻璃掩膜」；
  2. `DwmSetWindowAttribute(DWMWA_USE_IMMERSIVE_DARK_MODE=20, 1)`；
  3. `SetWindowCompositionAttribute(Attribute=30, AccentState=3,
     GradientColor=tint)` —— DWM 把掩膜区替换为「背后桌面实时模糊 + 染色」的
     backdrop（Attribute=30 是未公开 acrylic 通道；AccentState=4 在已发布
     Windows 上从未实装，API 返回成功但不渲染，勿用）；
  4. `DwmExtendFrameIntoClientArea(MARGINS(-1,-1,-1,-1))`
     —— 让整块客户区纳入 DWM 合成；
  5. `SetWindowRgn(CreateRoundRectRgn)` —— 圆角裁剪（按 DPI 换算物理像素）。

⚠ 三个关键坑（都踩过，别再改回去）：
  - **`winfo_id()` 不是顶级 HWND**：tkinter 的 Toplevel（尤其 overrideredirect）
    `winfo_id()` 返回子窗口句柄，DWM API 只收顶级窗口 → 必须先
    `GetParent` / `GetAncestor(GA_ROOT)` 解析，否则 `err=6 ERROR_INVALID_HANDLE`。
  - **顺序**：dark 属性 → accent → extend frame → region。region 变更会强制
    DWM 重新合成，是让 backdrop 渲染出来的可靠触发（SWP_FRAMECHANGED /
    RedrawWindow 均无效）；尺寸变化时 region 自然会重刷。
  - **不要用 `-transparentcolor` 色键**：本机 Tk 8.6 上一设色键，窗口所有内容
    （含文字、不透明底色）全部停止渲染——黑底掩膜路线无此问题，文字清晰可读。

非 Windows / API 失败时全部函数安全返回 False，调用方退回实底卡片即可。
"""

import ctypes
from ctypes import wintypes

try:
    _user32 = ctypes.windll.user32
    _gdi32 = ctypes.windll.gdi32
    _dwmapi = ctypes.windll.dwmapi
    _HAS_WIN = True
except Exception:
    _user32 = _gdi32 = _dwmapi = None
    _HAS_WIN = False

if _HAS_WIN:
    # WndProc 回退需用 64 位 LPARAM：鼠标坐标 lParam 在高 DPI / 跨屏下会超过
    # 2^31，不声明 argtypes 时 ctypes 默认按 c_int 转换 → OverflowError。
    _user32.DefWindowProcW.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    _user32.DefWindowProcW.restype = ctypes.c_longlong

# 真·acrylic 可用性（当前仅在 Windows 上验证）
HAS_ACRYLIC = _HAS_WIN

# WCA / DWMWA 常量（避免依赖 pywin32 的枚举）
# 注意：SetWindowCompositionAttribute 的 Attribute 有两个都在用的值——
#   19 = WCA_ACCENT_POLICY（文档属性，state=4 acrylic 在已发布 Windows 上从未实装）
#   30 = 未公开 acrylic 通道（pywinstyles 实测有效的路线）
# 本模块走 30 路线；AccentState 只用 3（ACCENT_ENABLE_BLURBEHIND），
# 4 会静默无效（API 返回成功但不渲染）——2026-10-25 用户真机截图抓到的坑。
_WCA_ACRYLIC_CHANNEL = 30
_ACCENT_ENABLE_BLURBEHIND = 3
_ACCENT_DISABLED = 0
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_WINDOW_CORNER_PREFERENCE = 33   # Win11 圆角偏好（系统级圆角，保留贴靠）
_DMWCP_ROUND = 2                       # DMWCP_ROUND：系统圆角
_GA_ROOT = 2                     # GetAncestor 的顶级窗口


class _ACCENTPOLICY(ctypes.Structure):
    _fields_ = [("AccentState", ctypes.c_int), ("AccentFlags", ctypes.c_uint),
                ("GradientColor", ctypes.c_uint), ("AnimationId", ctypes.c_int)]


class _WINCOMPATTRDATA(ctypes.Structure):
    _fields_ = [("Attribute", ctypes.c_int),
                ("Data", ctypes.POINTER(_ACCENTPOLICY)),
                ("SizeOfData", ctypes.c_size_t)]


class _MARGINS(ctypes.Structure):
    _fields_ = [("cxLeftWidth", ctypes.c_int), ("cxRightWidth", ctypes.c_int),
                ("cyTopHeight", ctypes.c_int), ("cyBottomHeight", ctypes.c_int)]


def _as_hwnd(widget_or_hwnd):
    """接受 tkinter 控件或整数 HWND，返回整数句柄（取不到返回 0）。"""
    if widget_or_hwnd is None:
        return 0
    try:
        return int(widget_or_hwnd)
    except (TypeError, ValueError):
        pass
    get_id = getattr(widget_or_hwnd, "winfo_id", None)
    if get_id is None:
        return 0
    try:
        return int(get_id())
    except Exception:
        return 0


def get_toplevel_hwnd(widget_or_hwnd):
    """把 tkinter 控件的 `winfo_id()` 解析成**顶级**窗口 HWND。

    tkinter 的 Toplevel（尤其 overrideredirect）`winfo_id()` 是子窗口句柄，
    DWM API 只认顶级窗口。解析失败时原样返回（可能就是个顶级句柄）。
    """
    hwnd = _as_hwnd(widget_or_hwnd)
    if not _HAS_WIN or not hwnd:
        return hwnd
    try:
        _user32.GetParent.argtypes = [wintypes.HWND]
        _user32.GetParent.restype = wintypes.HWND
        parent = _user32.GetParent(hwnd)
        if parent:
            return parent
        _user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
        _user32.GetAncestor.restype = wintypes.HWND
        root = _user32.GetAncestor(hwnd, _GA_ROOT)
        if root:
            return root
    except Exception:
        pass
    return hwnd


def _set_dark_mode(hwnd, enabled=True):
    """DWMWA_USE_IMMERSIVE_DARK_MODE（ acrylic 配方的组成部分）。"""
    try:
        _dwmapi.DwmSetWindowAttribute.argtypes = [
            wintypes.HWND, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD]
        v = ctypes.c_int(1 if enabled else 0)
        return _dwmapi.DwmSetWindowAttribute(
            hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(v), 4) == 0
    except Exception:
        return False


def apply_acrylic(hwnd, tint_abgr):
    """给窗口应用真·Acrylic（背后实时模糊 + 染色）。返回是否成功。

    hwnd:      tkinter 控件或整数 HWND（内部自动解析到顶级窗口）。
    tint_abgr: DWORD，字节序 A,B,G,R。pywinstyles 实测配方用 0x292929
               （ABGR：A=0x29≈16% 不透明深灰）；浅色主题用 0x40F0F0F0
               （A=0x40≈25% 不明白）。
    配方（与 pywinstyles "acrylic" 样式逐行一致，Win11 26300 实测）：
      Attribute=30（未公开 acrylic 通道）+ AccentState=3（BLURBEHIND）。
    ⚠ AccentState=4（ACRYLICBLURBEHIND）在已发布 Windows 上**从未实装**——
      API 返回成功但不渲染，窗口就是一张实底黑卡（2026-10-25 用户真机抓到）。
    注意：调用后需再应用一次窗口 region 才会触发 DWM 重新合成、渲染 backdrop。
    """
    if not _HAS_WIN:
        return False
    hwnd = get_toplevel_hwnd(hwnd)
    if not hwnd:
        return False
    try:
        accent = _ACCENTPOLICY()
        accent.AccentState = _ACCENT_ENABLE_BLURBEHIND
        accent.AccentFlags = 0
        accent.GradientColor = int(tint_abgr) & 0xFFFFFFFF
        accent.AnimationId = 0
        data = _WINCOMPATTRDATA(_WCA_ACRYLIC_CHANNEL, ctypes.pointer(accent),
                                ctypes.sizeof(accent))
        _user32.SetWindowCompositionAttribute.argtypes = [
            wintypes.HWND, ctypes.POINTER(_WINCOMPATTRDATA)]
        _user32.SetWindowCompositionAttribute.restype = ctypes.c_int
        return bool(_user32.SetWindowCompositionAttribute(
            hwnd, ctypes.byref(data)))
    except Exception:
        return False


def extend_frame_into_client_area(hwnd, margins=-1):
    """把整个客户区交给 DWM 合成（acrylic backdrop 稳定渲染的关键一步）。

    margins=-1 → MARGINS(-1,-1,-1,-1)（整窗纳入 sheet of glass）。
    返回 HRESULT == 0 (S_OK) 即成功。
    """
    if not _HAS_WIN:
        return False
    hwnd = get_toplevel_hwnd(hwnd)
    if not hwnd:
        return False
    try:
        m = _MARGINS(margins, margins, margins, margins)
        _dwmapi.DwmExtendFrameIntoClientArea.argtypes = [
            wintypes.HWND, ctypes.POINTER(_MARGINS)]
        _dwmapi.DwmExtendFrameIntoClientArea.restype = ctypes.c_int
        return _dwmapi.DwmExtendFrameIntoClientArea(
            hwnd, ctypes.byref(m)) == 0
    except Exception:
        return False


def apply_liquid_glass(widget_or_hwnd, tint_abgr, w, h, radius):
    """一键套用完整液态玻璃配方：dark 属性 → accent 染色 → extend frame → 圆角。

    - widget_or_hwnd: tkinter 控件（winfo_id 自动解析到顶级 HWND）或整数句柄
    - tint_abgr:      acrylic 染色（A,B,G,R 字节序 DWORD），见 apply_acrylic
    - w/h:            窗口逻辑像素尺寸（DIP），radius 为圆角半径（DIP）
    返回是否成功；失败时调用方应退回实底卡片。
    """
    if not _HAS_WIN:
        return False
    hwnd = get_toplevel_hwnd(widget_or_hwnd)
    if not hwnd:
        return False
    _set_dark_mode(hwnd, True)
    if not apply_acrylic(hwnd, tint_abgr):
        return False
    extend_frame_into_client_area(hwnd, -1)
    # region 必须最后：它的变更强制 DWM 重新合成，是 backdrop 渲染的可靠触发
    return set_round_region(hwnd, w, h, radius)


def clear_window_glass(widget_or_hwnd):
    """撤销 acrylic / extend frame，把窗口交回普通实底绘制。

    ⚠ 这不是"可选清理"，而是**可读性兜底路径**（2026-10-25 用户真机截图确认）：
    `AccentState=3(BLURBEHIND)` 会让 DWM 重新合成整块客户区，Tk 用 GDI 画的
    文字被一并模糊 —— 表现为"字全部发虚、看不出内容"，且**与配色无关**，
    调色救不回来。因此主窗默认走实色窗底，只有显式开启 [ui] glass 才套玻璃。
    """
    if not _HAS_WIN:
        return False
    hwnd = get_toplevel_hwnd(widget_or_hwnd)
    if not hwnd:
        return False
    ok = False
    try:
        accent = _ACCENTPOLICY()
        accent.AccentState = _ACCENT_DISABLED
        accent.AccentFlags = 0
        accent.GradientColor = 0
        accent.AnimationId = 0
        data = _WINCOMPATTRDATA(_WCA_ACRYLIC_CHANNEL, ctypes.pointer(accent),
                                ctypes.sizeof(accent))
        _user32.SetWindowCompositionAttribute.argtypes = [
            wintypes.HWND, ctypes.POINTER(_WINCOMPATTRDATA)]
        _user32.SetWindowCompositionAttribute.restype = ctypes.c_int
        ok = bool(_user32.SetWindowCompositionAttribute(
            hwnd, ctypes.byref(data)))
    except Exception:
        pass
    try:
        # extend(0)：收回客户区，DWM 不再把整窗当 sheet of glass 合成
        m = _MARGINS(0, 0, 0, 0)
        _dwmapi.DwmExtendFrameIntoClientArea.argtypes = [
            wintypes.HWND, ctypes.POINTER(_MARGINS)]
        _dwmapi.DwmExtendFrameIntoClientArea.restype = ctypes.c_int
        _dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(m))
    except Exception:
        pass
    return ok


def apply_layered_bitmap(widget_or_hwnd, img_rgba):
    """把 RGBA 位图以**逐像素 alpha** 贴到窗口（UpdateLayeredWindow）。

    这是「无边框卡片 + 柔和外扩阴影」的正解：
      - 阴影画在位图里（PIL 高斯模糊），窗口外区域 alpha=0 → 完全透明，
        不再需要单独的阴影窗，也不会出现"一圈均匀黑边"；
      - 位图必须预乘 alpha（premultiplied）且通道序为 BGRA。

    ⚠ 两个踩过的坑：
      - **Tk 的 `-alpha` 会让 `geometry()` 的位置设置失效**（尺寸能改、位置不行），
        所以阴影窗方案已废弃 —— 实测 `_sync_shadow(2135, 40)` 后阴影窗仍停在 +0+0，
        在屏幕左上角留一个透明黑框（2026-10-25 用户截图抓到）。
      - `CreateDIBSection` 必须用 **负数 biHeight**（top-down），否则图是上下颠倒的。
    """
    if not _HAS_WIN or img_rgba is None:
        return False
    hwnd = get_toplevel_hwnd(widget_or_hwnd)
    if not hwnd:
        return False
    try:
        from PIL import Image, ImageChops
    except Exception:
        return False
    W, H = img_rgba.size
    if W <= 0 or H <= 0:
        return False
    try:
        img = img_rgba.convert("RGBA")
        a = img.getchannel("A")
        r = ImageChops.multiply(img.getchannel("R"), a)
        g = ImageChops.multiply(img.getchannel("G"), a)
        b = ImageChops.multiply(img.getchannel("B"), a)
        # merge 成内存序 B,G,R,A（UpdateLayeredWindow 需要 BGRA）
        bgra = Image.merge("RGBA", (b, g, r, a))
        data = bgra.tobytes()

        class _BIH(ctypes.Structure):
            _fields_ = [("biSize", wintypes.DWORD),
                        ("biWidth", ctypes.c_long),
                        ("biHeight", ctypes.c_long),
                        ("biPlanes", wintypes.WORD),
                        ("biBitCount", wintypes.WORD),
                        ("biCompression", wintypes.DWORD),
                        ("biSizeImage", wintypes.DWORD),
                        ("biXPelsPerMeter", ctypes.c_long),
                        ("biYPelsPerMeter", ctypes.c_long),
                        ("biClrUsed", wintypes.DWORD),
                        ("biClrImportant", wintypes.DWORD)]

        class _BF(ctypes.Structure):
            _fields_ = [("BlendOp", ctypes.c_byte),
                        ("SourceConstantAlpha", ctypes.c_byte),
                        ("AlphaFormat", ctypes.c_byte),
                        ("BlendFlags", ctypes.c_byte)]

        bi = _BIH()
        bi.biSize = ctypes.sizeof(_BIH)
        bi.biWidth = W
        bi.biHeight = -H              # 负数 = top-down
        bi.biPlanes = 1
        bi.biBitCount = 32
        bi.biCompression = 0          # BI_RGB
        ppv = ctypes.c_void_p()
        hdc_screen = _user32.GetDC(None)
        hbm = _gdi32.CreateDIBSection(hdc_screen, ctypes.byref(bi), 0,
                                      ctypes.byref(ppv), None, 0)
        if not hbm or not ppv.value:
            _user32.ReleaseDC(None, hdc_screen)
            return False
        ctypes.memmove(ppv.value, data, len(data))
        dc_mem = _gdi32.CreateCompatibleDC(hdc_screen)
        _gdi32.SelectObject(dc_mem, hbm)

        _user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int,
                                           ctypes.c_long]
        _user32.SetWindowLongW.restype = ctypes.c_long
        _user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        _user32.GetWindowLongW.restype = ctypes.c_long
        _user32.UpdateLayeredWindow.argtypes = [
            wintypes.HWND, wintypes.HDC, ctypes.c_void_p, ctypes.c_void_p,
            wintypes.HDC, ctypes.c_void_p, wintypes.COLORREF,
            ctypes.c_void_p, wintypes.DWORD]
        _user32.UpdateLayeredWindow.restype = wintypes.BOOL

        GWL_EXSTYLE, WS_EX_LAYERED = -20, 0x00080000
        style = _user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if not (style & WS_EX_LAYERED):
            _user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED)

        sz = (ctypes.c_long * 2)(W, H)
        src = (ctypes.c_long * 2)(0, 0)
        blend = _BF(0, 255, 1, 0)     # AC_SRC_OVER / alpha=255 / AC_SRC_ALPHA
        ok = _user32.UpdateLayeredWindow(
            hwnd, hdc_screen, None, sz, dc_mem, src, 0,
            ctypes.byref(blend), 2)   # ULW_ALPHA

        _gdi32.DeleteDC(dc_mem)
        _gdi32.DeleteObject(hbm)
        _user32.ReleaseDC(None, hdc_screen)
        return bool(ok)
    except Exception:
        return False


def dpi_scale(hwnd):
    """返回窗口所在显示器的 DPI 缩放（1.0 = 96dpi）。多屏不同缩放也准确。"""
    if not _HAS_WIN or not hwnd:
        return 1.0
    hwnd = get_toplevel_hwnd(hwnd)
    try:
        _user32.GetDpiForWindow.argtypes = [wintypes.HWND]
        _user32.GetDpiForWindow.restype = wintypes.UINT
        dpi = _user32.GetDpiForWindow(hwnd)
        if dpi:
            return dpi / 96.0
    except Exception:
        pass
    return 1.0


def set_round_region(widget_or_hwnd, w, h, radius, physical=False):
    """把窗口裁剪成圆角矩形。返回是否成功。

    - 接受 tkinter 控件或整数 HWND（自动解析顶级窗口）
    - **默认 w/h/radius 是逻辑像素(DIP)**，内部按窗口 DPI 换算成物理像素；
      `physical=True` 时视为已经是物理像素，**不再乘 DPI 缩放**。
      ⚠ 2026-10-25 踩坑：位图尺寸是物理像素（w_css×S，S 已含 1.25 缩放），
      传给本函数又被乘了一次 1.25 → region 比窗口大 25%，被系统按窗口边界
      截成矩形 → 四角根本切不掉，真机上表现为「四角有黑底」。
    - 每次尺寸变化后调用，圆角随窗口大小保持
    - 非 Windows / 失败时静默返回 False，不影响任何功能
    """
    if not _HAS_WIN or w <= 0 or h <= 0:
        return False
    hwnd = get_toplevel_hwnd(widget_or_hwnd)
    if not hwnd:
        return False
    try:
        s = 1.0 if physical else dpi_scale(hwnd)
        pw, ph = int(round(w * s)), int(round(h * s))
        rr = int(round(radius * s))
        if rr > min(pw, ph) // 2:
            rr = min(pw, ph) // 2
        _gdi32.CreateRoundRectRgn.argtypes = [
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int]
        _gdi32.CreateRoundRectRgn.restype = wintypes.HRGN
        _user32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN,
                                         wintypes.BOOL]
        _user32.SetWindowRgn.restype = ctypes.c_int
        # ⚠ CreateRoundRectRgn 的后两个参数是**椭圆直径**（不是半径）：
        # 传 rr 只得到 rr/2 的圆角，比位图 mask 的圆角更方 → 卡片圆角外侧
        # 那一圈（位图里 alpha=0）会露窗口底色，看起来"四角黑角没切干净"。
        # 必须 ×2 才能与 PIL rounded_rectangle(radius=rr) 严格对齐。
        # +1 让右下角闭合，避免圆角外多出 1px 直角毛边
        rgn = _gdi32.CreateRoundRectRgn(0, 0, pw + 1, ph + 1, rr * 2, rr * 2)
        if not rgn:
            return False
        return bool(_user32.SetWindowRgn(hwnd, rgn, True))
    except Exception:
        return False


def region_corner_cut(widget_or_hwnd, x=1, y=1):
    """自检：窗口 region 在角上 (x,y) 处是否被裁掉（True = 圆角真的生效了）。

    SetWindowRgn 返回 True 只代表"调用成功"，**不代表 region 覆盖范围正确**
    （region 比窗口大时也被截成矩形、同样返回 True）。所以要用
    GetWindowRgn + PtInRegion 实测一个角点是否落在 region 之外。
    `x/y` 是**逻辑像素**，内部按 DPI 换算。
    """
    if not _HAS_WIN:
        return False
    hwnd = get_toplevel_hwnd(widget_or_hwnd)
    if not hwnd:
        return False
    try:
        s = dpi_scale(hwnd)
        _gdi32.CreateRectRgn.argtypes = [
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        _gdi32.CreateRectRgn.restype = wintypes.HRGN
        hrgn = _gdi32.CreateRectRgn(0, 0, 1, 1)
        if not hrgn:
            return False
        try:
            _user32.GetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN]
            _user32.GetWindowRgn.restype = ctypes.c_int
            if _user32.GetWindowRgn(hwnd, hrgn) == 0:   # 0 = ERROR，无 region
                return False
            _gdi32.PtInRegion.argtypes = [
                wintypes.HRGN, ctypes.c_int, ctypes.c_int]
            _gdi32.PtInRegion.restype = wintypes.BOOL
            inside = bool(_gdi32.PtInRegion(
                hrgn, int(round(x * s)), int(round(y * s))))
            return not inside
        finally:
            _gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
            _gdi32.DeleteObject.restype = wintypes.BOOL
            _gdi32.DeleteObject(hrgn)
    except Exception:
        return False


def set_round_corners(widget_or_hwnd, round_=True):
    """Win11 系统级圆角（DWMWA_WINDOW_CORNER_PREFERENCE=33, DMWCP_ROUND=2）。

    与 SetWindowRgn 裁剪的区别：系统圆角**保留窗口贴靠 / 缩放 / 阴影**，
    尺寸变化无需重算——适合主窗（可 resize 的标准窗）。
    迷你窗（overrideredirect）在 Win10 上无此属性，仍走 set_round_region。
    Win10 / 非 Windows 上静默返回 False。
    """
    if not _HAS_WIN:
        return False
    hwnd = get_toplevel_hwnd(widget_or_hwnd)
    if not hwnd:
        return False
    try:
        v = ctypes.c_int(_DMWCP_ROUND if round_ else 1)
        _dwmapi.DwmSetWindowAttribute.argtypes = [
            wintypes.HWND, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD]
        return _dwmapi.DwmSetWindowAttribute(
            hwnd, _DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(v), 4) == 0
    except Exception:
        return False


def apply_window_glass(widget_or_hwnd, tint_abgr, dark=True):
    """主程序窗口的玻璃化（对照效果图 .win 设计稿）。

    与迷你窗配方的区别：
    - **不用 SetWindowRgn**：主窗可 resize、要保留系统贴靠与阴影，
      圆角走 set_round_corners（Win11 系统圆角，尺寸变化零维护）；
    - dark 属性随主题：浅色主题必须关掉沉浸式暗色（否则原生标题栏
      文字白底白字看不见）；
    - tint 即设计稿的窗口底色叠加：dark rgba(16,20,30,.82) →
      ABGR 0xD1201410；light rgba(250,250,252,.86) → 0xDBFCFAFA。
      （GradientColor 的 alpha = 染色层不透明度，A 越大背后透出越少。）

    返回是否成功；失败时调用方用实色 win_bg 即可，不影响任何功能。
    """
    if not _HAS_WIN:
        return False
    hwnd = get_toplevel_hwnd(widget_or_hwnd)
    if not hwnd:
        return False
    _set_dark_mode(hwnd, dark)
    if not apply_acrylic(hwnd, tint_abgr):
        return False
    # extend(-1)：标题栏也纳入 DWM 合成，获得玻璃延伸（系统按钮仍可用）
    extend_frame_into_client_area(hwnd, -1)
    set_round_corners(hwnd, True)
    return True


def system_is_light():
    """读取 Windows 应用明暗主题（HKCU ...Themes\\Personalize\\AppsUseLightTheme）。

    读不到（旧系统 / 非 Windows / 注册表无该项）时默认返回浅色 True。
    """
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return bool(val)
    except Exception:
        return True


# ============================================================================
# 桌面迷你窗：纯 Win32 分层窗口
# ----------------------------------------------------------------------------
# 为什么不用 Tk 窗口承载逐像素 alpha 位图：Tk 的 overrideredirect 窗口在事后被
# 动态加上 WS_EX_LAYERED（apply_layered_bitmap 的旧做法）后，Tk 自己的窗口过程
# 与它管理的 WM_PAINT 绘制循环冲突，在真实 DWM 下会导致 Tcl/Tk 在 C 层崩溃
# （表现为"闪退"，Python try/except 抓不到）。改用纯 Win32 原生创建、自带
# WS_EX_LAYERED 的窗口承载位图，由 DWM 标准支持逐像素 alpha，与 Tk 无任何交叉，
# 彻底消除该冲突。Tk 仅负责业务逻辑与右键菜单（通过 after 切回主线程弹 Tk Menu）。
# ============================================================================
_kernel32 = ctypes.windll.kernel32 if _HAS_WIN else None

_WS_POPUP = 0x80000000
_WS_EX_LAYERED = 0x80000
_WS_EX_TOPMOST = 0x8
_WS_EX_TOOLWINDOW = 0x80
_WS_EX_NOACTIVATE = 0x08000000
_SWP_NOSIZE = 0x0001
_SWP_NOACTIVATE = 0x0010
_SWP_SHOWWINDOW = 0x0040
_SW_SHOWNA = 8
_CS_HREDRAW = 0x2
_CS_VREDRAW = 0x1
_CS_DBLCLKS = 0x8
_WM_LBUTTONDOWN = 0x0201
_WM_LBUTTONUP = 0x0202
_WM_MOUSEMOVE = 0x0200
_WM_LBUTTONDBLCLK = 0x0203
_WM_RBUTTONUP = 0x0205
_WM_DESTROY = 0x0002
_IDC_ARROW = 32512


class _BIH(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long), ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD)]


class _BLENDFUNC(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_byte), ("SourceConstantAlpha", ctypes.c_byte),
                ("AlphaFormat", ctypes.c_byte), ("BlendFlags", ctypes.c_byte)]


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("style", wintypes.DWORD),
        ("lpfnWndProc", ctypes.c_void_p), ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int), ("hInstance", ctypes.c_void_p),
        ("hIcon", ctypes.c_void_p), ("hCursor", ctypes.c_void_p),
        ("hbrBackground", ctypes.c_void_p), ("lpszMenuName", ctypes.c_void_p),
        ("lpszClassName", ctypes.c_void_p), ("hIconSm", ctypes.c_void_p)]


def _build_layered_bits(img_rgba):
    """RGBA -> UpdateLayeredWindow 需要的 BGRA 预乘字节流 (data, W, H)。"""
    from PIL import Image, ImageChops
    img = img_rgba.convert("RGBA")
    a = img.getchannel("A")
    r = ImageChops.multiply(img.getchannel("R"), a)
    g = ImageChops.multiply(img.getchannel("G"), a)
    b = ImageChops.multiply(img.getchannel("B"), a)
    bgra = Image.merge("RGBA", (b, g, r, a))
    return bgra.tobytes(), img.size[0], img.size[1]


def update_layered_window(hwnd, img_rgba, x=None, y=None):
    """把 RGBA 位图以逐像素 alpha 贴到**已 Layered**的窗口（纯 Win32 窗口）。

    调用方须保证 hwnd 创建时即带 WS_EX_LAYERED。x/y 给定则贴图同时定位。
    返回是否成功。
    """
    if not _HAS_WIN or not hwnd or img_rgba is None:
        return False
    try:
        from PIL import Image, ImageChops
    except Exception:
        return False
    data, W, H = _build_layered_bits(img_rgba)
    if W <= 0 or H <= 0:
        return False
    try:
        bi = _BIH()
        bi.biSize = ctypes.sizeof(_BIH)
        bi.biWidth = W
        bi.biHeight = -H              # 负数 = top-down
        bi.biPlanes = 1
        bi.biBitCount = 32
        bi.biCompression = 0
        ppv = ctypes.c_void_p()
        hdc_screen = _user32.GetDC(None)
        hbm = _gdi32.CreateDIBSection(hdc_screen, ctypes.byref(bi), 0,
                                      ctypes.byref(ppv), None, 0)
        if not hbm or not ppv.value:
            _user32.ReleaseDC(None, hdc_screen)
            return False
        ctypes.memmove(ppv.value, data, len(data))
        dc_mem = _gdi32.CreateCompatibleDC(hdc_screen)
        _gdi32.SelectObject(dc_mem, hbm)

        _user32.UpdateLayeredWindow.argtypes = [
            wintypes.HWND, wintypes.HDC, ctypes.c_void_p, ctypes.c_void_p,
            wintypes.HDC, ctypes.c_void_p, wintypes.COLORREF,
            ctypes.c_void_p, wintypes.DWORD]
        _user32.UpdateLayeredWindow.restype = wintypes.BOOL

        sz = (ctypes.c_long * 2)(W, H)
        src = (ctypes.c_long * 2)(0, 0)
        ppt = (ctypes.c_long * 2)(x, y) if (x is not None and y is not None) else None
        blend = _BLENDFUNC(0, 255, 1, 0)
        ok = _user32.UpdateLayeredWindow(
            hwnd, hdc_screen,
            ctypes.cast(ppt, ctypes.c_void_p) if ppt is not None else None,
            ctypes.cast(sz, ctypes.c_void_p), dc_mem,
            ctypes.cast(src, ctypes.c_void_p), 0,
            ctypes.byref(blend), 2)
        _gdi32.DeleteDC(dc_mem)
        _gdi32.DeleteObject(hbm)
        _user32.ReleaseDC(None, hdc_screen)
        return bool(ok)
    except Exception:
        return False


def apply_layered_bitmap(widget_or_hwnd, img_rgba):
    """（向后兼容）把位图贴到 Tk 控件/窗口——仅用于非迷你窗的遗留场景。

    ⚠ 给 Tk 窗口动态加 WS_EX_LAYERED 会与 Tk 自身绘制循环冲突（C 层崩溃），
    迷你窗已改用 MiniLayeredWindow（纯 Win32）规避，此函数仅保留兼容。
    """
    if not _HAS_WIN or img_rgba is None:
        return False
    hwnd = get_toplevel_hwnd(widget_or_hwnd)
    if not hwnd:
        return False
    try:
        GWL_EXSTYLE, WS_EX_LAYERED = -20, 0x00080000
        _user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int,
                                          ctypes.c_long]
        _user32.SetWindowLongW.restype = ctypes.c_long
        style = _user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if not (style & WS_EX_LAYERED):
            _user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED)
    except Exception:
        return False
    return update_layered_window(hwnd, img_rgba)


# ----------------------------------------------------------------------------
# MiniLayeredWindow：纯 Win32 分层窗口，承载迷你卡整张位图（卡片 + 阴影外扩）
# ----------------------------------------------------------------------------
_MINI_INSTANCES = {}
_MINI_ATOM = 0
_MINI_WNDPROC = None


def _mini_wndproc(hwnd, msg, wp, lp):
    inst = _MINI_INSTANCES.get(hwnd)
    if inst is not None:
        try:
            return inst._dispatch(msg, wp, lp)
        except Exception:
            return 0
    return _user32.DefWindowProcW(hwnd, msg, wp, lp)


class MiniLayeredWindow:
    """纯 Win32 分层窗口，显示迷你卡位图并处理鼠标交互。

    不与任何 Tk 窗口共享 HWND，因此不会触发 Tk 的 WS_EX_LAYERED 冲突。
    交互（拖拽 / 双击刷新 / 右键菜单）通过 WndProc 直接处理，菜单回调经
    Tk 主线程的 after 切回，保证在 Tk 上下文里弹 Tk Menu。
    """

    def __init__(self):
        self.hwnd = 0
        self._x = self._y = 0
        self._w = self._h = 0
        self._last_img = None
        self._drag = None
        self.on_move = None
        self.on_dblclick = None
        self.on_context = None
        if not _HAS_WIN or _kernel32 is None:
            return
        atom = self._register_class()
        if not atom:
            return
        hInst = _kernel32.GetModuleHandleW(None)
        _user32.CreateWindowExW.argtypes = [
            wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HWND, wintypes.HWND, ctypes.c_void_p, ctypes.c_void_p]
        _user32.CreateWindowExW.restype = wintypes.HWND
        self.hwnd = _user32.CreateWindowExW(
            _WS_EX_LAYERED | _WS_EX_TOPMOST | _WS_EX_TOOLWINDOW
            | _WS_EX_NOACTIVATE,
            ctypes.c_wchar_p("DsbvMiniLayer"), None, _WS_POPUP,
            0, 0, 10, 10, None, None, ctypes.c_void_p(hInst), None)
        if self.hwnd:
            _MINI_INSTANCES[self.hwnd] = self

    @staticmethod
    def _register_class():
        global _MINI_ATOM, _MINI_WNDPROC
        if _MINI_ATOM:
            return _MINI_ATOM
        if not _kernel32:
            return 0
        hInst = _kernel32.GetModuleHandleW(None)
        wc = _WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(_WNDCLASSEXW)
        wc.style = _CS_HREDRAW | _CS_VREDRAW | _CS_DBLCLKS
        if _MINI_WNDPROC is None:
            _MINI_WNDPROC = ctypes.WINFUNCTYPE(
                ctypes.c_long, wintypes.HWND, wintypes.UINT,
                wintypes.WPARAM, wintypes.LPARAM)(_mini_wndproc)
        wc.lpfnWndProc = ctypes.cast(_MINI_WNDPROC, ctypes.c_void_p)
        wc.hInstance = ctypes.c_void_p(hInst)
        wc.lpszClassName = ctypes.cast(
            ctypes.c_wchar_p("DsbvMiniLayer"), ctypes.c_void_p)
        _user32.LoadCursorW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        _user32.LoadCursorW.restype = ctypes.c_void_p
        wc.hCursor = _user32.LoadCursorW(None, ctypes.c_void_p(_IDC_ARROW))
        _user32.RegisterClassExW.argtypes = [ctypes.POINTER(_WNDCLASSEXW)]
        _user32.RegisterClassExW.restype = wintypes.WORD
        _MINI_ATOM = _user32.RegisterClassExW(ctypes.byref(wc))
        return _MINI_ATOM

    def show(self, img_rgba, x, y):
        """贴位图并按 (x,y) 定位后显示（不抢占焦点）。"""
        ok = update_layered_window(self.hwnd, img_rgba, x, y)
        if ok:
            self._x, self._y = x, y
            self._w, self._h = img_rgba.size
            self._last_img = img_rgba
            _user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
            _user32.ShowWindow.restype = wintypes.BOOL
            _user32.ShowWindow(self.hwnd, _SW_SHOWNA)
        return ok

    def move(self, x, y):
        """拖拽时每帧调用：重贴位图到新位置。

        ⚠ 分层窗口的可见内容由 `UpdateLayeredWindow` 的 pptDst 决定，
        `SetWindowPos` 无法移动已贴的位图（会"框动图不动"）。故每帧
        直接用 `_last_img` 重贴，位置/内容一次到位。
        """
        if not self.hwnd:
            return
        if self._last_img is not None:
            update_layered_window(self.hwnd, self._last_img, x, y)
        else:
            _user32.SetWindowPos.argtypes = [
                wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                ctypes.c_int, ctypes.c_int, wintypes.UINT]
            _user32.SetWindowPos.restype = wintypes.BOOL
            _user32.SetWindowPos(self.hwnd, wintypes.HWND(-1), x, y, 0, 0,
                                 _SWP_NOSIZE | _SWP_NOACTIVATE | _SWP_SHOWWINDOW)
        self._x, self._y = x, y
        if self.on_move is not None:
            self.on_move(x, y)

    def destroy(self):
        if self.hwnd:
            _MINI_INSTANCES.pop(self.hwnd, None)
            try:
                _user32.DestroyWindow(self.hwnd)
            except Exception:
                pass
            self.hwnd = 0

    def _dispatch(self, msg, wp, lp):
        if msg == _WM_LBUTTONDOWN:
            cx = ctypes.c_short(lp & 0xFFFF).value
            cy = ctypes.c_short((lp >> 16) & 0xFFFF).value
            self._drag = (cx, cy)
            _user32.SetCapture.argtypes = [wintypes.HWND]
            _user32.SetCapture.restype = wintypes.HWND
            _user32.SetCapture(self.hwnd)
            return 0
        if msg == _WM_MOUSEMOVE:
            if self._drag is not None:
                cx = ctypes.c_short(lp & 0xFFFF).value
                cy = ctypes.c_short((lp >> 16) & 0xFFFF).value
                self.move(self._x + (cx - self._drag[0]),
                          self._y + (cy - self._drag[1]))
            return 0
        if msg == _WM_LBUTTONUP:
            if self._drag is not None:
                _user32.ReleaseCapture.argtypes = []
                _user32.ReleaseCapture.restype = wintypes.BOOL
                _user32.ReleaseCapture()
                self._drag = None
            return 0
        if msg == _WM_LBUTTONDBLCLK:
            if self.on_dblclick is not None:
                self.on_dblclick()
            return 0
        if msg == _WM_RBUTTONUP:
            pt = _POINT()
            _user32.GetCursorPos.argtypes = [ctypes.POINTER(_POINT)]
            _user32.GetCursorPos.restype = wintypes.BOOL
            _user32.GetCursorPos(ctypes.byref(pt))
            if self.on_context is not None:
                self.on_context(pt.x, pt.y)
            return 0
        if msg == _WM_DESTROY:
            _MINI_INSTANCES.pop(self.hwnd, None)
            return 0
        return _user32.DefWindowProcW(self.hwnd, msg, wp, lp)
