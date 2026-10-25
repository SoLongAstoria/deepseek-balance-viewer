# -*- coding: utf-8 -*-
"""桌面迷你窗网速实时监控（零依赖，基于 Windows IPHelper GetIfTable）。

- 跨所有"真实网络接口"（按 IP 适配器索引去重，避开 WFP / WinpkFilter 等
  过滤模块对同一个物理网卡计数器的重复上报）累加收 / 发字节数
- 按固定间隔采样两次，求差值 ÷ 时间 = 实时速率
- 32 位计数器回绕保护（高带宽链路长时间运行后可能回绕）
"""

import time
import ctypes
from ctypes import wintypes

try:
    _iphlpapi = ctypes.windll.iphlpapi
    _HAS_IPHELPER = True
except Exception:
    _iphlpapi = None
    _HAS_IPHELPER = False


MAX_LEN_IFDESCR = 256
MAXLEN_PHYSADDR = 8


class MIB_IFROW(ctypes.Structure):
    _fields_ = [
        ("wszName", ctypes.c_wchar * MAX_LEN_IFDESCR),
        ("dwIndex", wintypes.DWORD),
        ("dwType", wintypes.DWORD),
        ("dwMtu", wintypes.DWORD),
        ("dwSpeed", wintypes.DWORD),
        ("dwPhysAddrLen", wintypes.DWORD),
        ("bPhysAddr", ctypes.c_byte * MAXLEN_PHYSADDR),
        ("dwAdminStatus", wintypes.DWORD),
        ("dwOperStatus", wintypes.DWORD),
        ("dwLastChange", wintypes.DWORD),
        ("dwInOctets", wintypes.DWORD),
        ("dwInUcastPkts", wintypes.DWORD),
        ("dwInNUcastPkts", wintypes.DWORD),
        ("dwInDiscards", wintypes.DWORD),
        ("dwInErrors", wintypes.DWORD),
        ("dwInUnknownProtos", wintypes.DWORD),
        ("dwOutOctets", wintypes.DWORD),
        ("dwOutUcastPkts", wintypes.DWORD),
        ("dwOutNUcastPkts", wintypes.DWORD),
        ("dwOutDiscards", wintypes.DWORD),
        ("dwOutErrors", wintypes.DWORD),
        ("dwOutQLen", wintypes.DWORD),
        ("dwDescrLen", wintypes.DWORD),
        ("bDescr", ctypes.c_byte * MAX_LEN_IFDESCR),
    ]


IF_TYPE_SOFTWARE_LOOPBACK = 24


class IP_ADDR_STRING(ctypes.Structure):
    pass


IP_ADDR_STRING._fields_ = [
    ("Next", ctypes.POINTER(IP_ADDR_STRING)),
    ("IpAddress", ctypes.c_char * 16),
    ("IpMask", ctypes.c_char * 16),
    ("Context", wintypes.DWORD),
]


class IP_ADAPTER_INFO(ctypes.Structure):
    pass


IP_ADAPTER_INFO._fields_ = [
    ("Next", ctypes.POINTER(IP_ADAPTER_INFO)),
    ("ComboIndex", wintypes.DWORD),
    ("AdapterName", ctypes.c_char * 260),
    ("Description", ctypes.c_char * 132),
    ("AddressLength", wintypes.DWORD),
    ("Address", ctypes.c_byte * 8),
    ("Index", wintypes.DWORD),
    ("Type", wintypes.DWORD),
    ("DhcpEnabled", wintypes.DWORD),
    ("CurrentIpAddress", ctypes.POINTER(IP_ADDR_STRING)),
    ("IpAddressList", IP_ADDR_STRING),
]


def _get_if_table():
    if not _HAS_IPHELPER:
        raise OSError("当前平台不支持 IPHelper（仅 Windows 可用）")
    size = ctypes.c_ulong(16384)
    buf = ctypes.create_string_buffer(size.value)
    ret = _iphlpapi.GetIfTable(buf, ctypes.byref(size), 0)
    if ret == 122:  # ERROR_INSUFFICIENT_BUFFER
        buf = ctypes.create_string_buffer(size.value)
        ret = _iphlpapi.GetIfTable(buf, ctypes.byref(size), 0)
    if ret != 0:
        raise ctypes.WinError(ret)
    num = ctypes.cast(buf, ctypes.POINTER(wintypes.DWORD))[0]
    row_size = ctypes.sizeof(MIB_IFROW)
    rows = []
    for i in range(num):
        off = 4 + i * row_size
        rows.append(MIB_IFROW.from_buffer_copy(buf[off:off + row_size]))
    return rows


def _get_real_indices():
    """返回"真实 IP 适配器"的索引集合（过滤模块不在其中，天然去重）。

    调用失败（极少见）时返回 None，由调用方决定降级策略。
    """
    if not _HAS_IPHELPER:
        return None
    size = ctypes.c_ulong(16384)
    buf = ctypes.create_string_buffer(size.value)
    ret = _iphlpapi.GetAdaptersInfo(buf, ctypes.byref(size))
    if ret == 111:  # ERROR_BUFFER_OVERFLOW
        buf = ctypes.create_string_buffer(size.value)
        ret = _iphlpapi.GetAdaptersInfo(buf, ctypes.byref(size))
    if ret != 0:
        return None
    indices = set()
    p = ctypes.cast(buf, ctypes.POINTER(IP_ADAPTER_INFO))
    while p:
        indices.add(p.contents.Index)
        p = p.contents.Next
    return indices


def get_total_bytes():
    """返回 (in_bytes, out_bytes)：所有真实网络接口的累计字节数（已去重）。"""
    real = _get_real_indices()
    in_b = out_b = 0
    for r in _get_if_table():
        if r.dwType == IF_TYPE_SOFTWARE_LOOPBACK:
            continue
        # 能拿到真实适配器索引时，只累加真实接口（过滤掉重复计数的过滤模块）；
        # 拿不到时退化为"非回环全累加"，保证至少不报错。
        if real is not None and r.dwIndex not in real:
            continue
        in_b += r.dwInOctets
        out_b += r.dwOutOctets
    return in_b, out_b


class NetSampler:
    """采样器：保存上一次累计字节数与时间戳，求实时速率。"""

    def __init__(self):
        self._prev = None  # (in_bytes, out_bytes, ts)

    def sample(self):
        """返回 (下载速率, 上传速率)（字节/秒）；首次调用返回 None 建立基线。"""
        try:
            in_b, out_b = get_total_bytes()
        except Exception:
            self._prev = None
            return None
        now = time.time()
        if self._prev is None:
            self._prev = (in_b, out_b, now)
            return None
        dt = now - self._prev[2]
        din = in_b - self._prev[0]
        dout = out_b - self._prev[1]
        # 32 位计数器回绕保护
        if din < 0:
            din += 2 ** 32
        if dout < 0:
            dout += 2 ** 32
        self._prev = (in_b, out_b, now)
        if dt <= 0:
            return (0.0, 0.0)
        return (din / dt, dout / dt)


def fmt_speed(bps):
    """把字节/秒格式化为带单位的速率字符串。"""
    if bps is None:
        return "--"
    if bps < 1024:
        return f"{bps:.0f} B/s"
    elif bps < 1024 ** 2:
        return f"{bps / 1024:.2f} KB/s"
    elif bps < 1024 ** 3:
        return f"{bps / 1024 ** 2:.2f} MB/s"
    else:
        return f"{bps / 1024 ** 3:.2f} GB/s"


# ----------------------------------------------------------------------------
# 多显示器感知：拿到"某窗口当前所在显示器"的真实 work area（虚拟屏幕坐标）。
# 这是修复迷你窗"拖到副屏被闪回主屏"的关键——tkinter 的
# winfo_screenwidth()/winfo_screenheight() 在 Windows 多显示器下只返回**主屏**尺寸，
# 用它来 clamp 会把"在主屏右侧（其实位于副屏）"的窗口误判为越界并 snap 回主屏。
# 改用 MonitorFromWindow + GetMonitorInfoW 取窗口实际所在显示器的边界（可负／可超主屏）。
# ----------------------------------------------------------------------------
try:
    _user32 = ctypes.windll.user32
    _HAS_USER32 = True
except Exception:
    _user32 = None
    _HAS_USER32 = False


def get_window_monitor_workarea(hwnd):
    """返回 hwnd 所在显示器的 work area (left, top, right, bottom)，虚拟屏坐标。

    - 多显示器下 left/top 可能为**负数**（副屏在左 / 上）或**大于主屏宽高**（副屏在右 / 下）。
    - 取不到（非 Windows / API 失败）时返回 None，调用方应跳过 clamp。
    """
    if not _HAS_USER32 or not hwnd:
        return None
    try:
        class _RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                        ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

        class _MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_ulong),
                        ("rcMonitor", _RECT),
                        ("rcWork", _RECT),
                        ("dwFlags", ctypes.c_ulong)]

        _user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        _user32.MonitorFromWindow.restype = wintypes.HMONITOR
        _user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR,
                                            ctypes.POINTER(_MONITORINFO)]
        _user32.GetMonitorInfoW.restype = wintypes.BOOL

        MONITOR_DEFAULTTONEAREST = 0x00000002
        hmon = _user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
        if not hmon:
            return None
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        if not _user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            return None
        w = mi.rcWork
        return (w.left, w.top, w.right, w.bottom)
    except Exception:
        return None
