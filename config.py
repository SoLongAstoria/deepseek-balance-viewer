# -*- coding: utf-8 -*-
"""本地配置管理。

- 仅在本机读写 config.ini，绝不联网上传。
- API Key 使用 Windows DPAPI 加密落盘（非 Windows 退化为轻量混淆），
  配置文件内不以明文存储，代码中也从不打印 Key。
"""

import os
import base64
import configparser
from typing import Optional

try:
    import ctypes
    from ctypes import wintypes
    _HAS_DPAPI = (os.name == "nt")
except Exception:
    _HAS_DPAPI = False


def app_data_dir() -> str:
    """配置持久化目录（用户级，跨重启存在）。

    PyInstaller --onefile 会把脚本释放到系统临时目录（sys._MEIPASS），
    若把 config.ini 放在 __file__ 旁边，临时目录在进程退出时被清理，
    导致"重启后 Key 丢失"。因此固定写到用户 AppData（或家目录），
    从源码运行与打包成 exe 都指向同一位置，配置不再丢失。
    """
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "DeepSeekBalanceViewer")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


def default_config_path() -> str:
    """配置文件的默认路径。

    优先读环境变量 `DSBV_CONFIG` —— 截图 / 冒烟脚本用它把配置隔离到临时目录。
    ⚠ 这不是洁癖：之前脚本直接跑真实 App，输入框的 `<FocusOut>` 会触发自动保存，
    把用户真实 API Key 覆盖成空值（2026-10-25 真丢过 Key）。隔离后再也不会碰真配置。
    """
    return os.environ.get("DSBV_CONFIG") or os.path.join(app_data_dir(), "config.ini")


CONFIG_PATH = default_config_path()

# 非 Windows 平台的轻量混淆密钥（仅防明文，非强加密；Windows 上用 DPAPI 更安全）
_OBF_KEY = b"ds_balance_viewer_2026"


# ------------------------- DPAPI（Windows 用户态加密） -------------------------
class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _dpapi_protect(plain: bytes) -> bytes:
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    blob_in = _DataBlob(len(plain), ctypes.cast(
        ctypes.create_string_buffer(plain, len(plain)),
        ctypes.POINTER(ctypes.c_byte)))
    blob_out = _DataBlob()
    if not crypt32.CryptProtectData(ctypes.byref(blob_in), None, None, None, None, 0,
                                   ctypes.byref(blob_out)):
        raise ctypes.WinError()
    buf = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    kernel32.LocalFree(blob_out.pbData)
    return buf


def _dpapi_unprotect(cipher: bytes) -> bytes:
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    blob_in = _DataBlob(len(cipher), ctypes.cast(
        ctypes.create_string_buffer(cipher, len(cipher)),
        ctypes.POINTER(ctypes.c_byte)))
    blob_out = _DataBlob()
    if not crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, None, None, None, 0,
                                     ctypes.byref(blob_out)):
        raise ctypes.WinError()
    buf = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    kernel32.LocalFree(blob_out.pbData)
    return buf


# ------------------------- 轻量混淆（非 Windows 备用） -------------------------
def _obf_protect(plain: bytes) -> bytes:
    out = bytes(b ^ _OBF_KEY[i % len(_OBF_KEY)] for i, b in enumerate(plain))
    return base64.b64encode(out)


def _obf_unprotect(cipher: bytes) -> bytes:
    raw = base64.b64decode(cipher)
    return bytes(b ^ _OBF_KEY[i % len(_OBF_KEY)] for i, b in enumerate(raw))


# ------------------------- 对外加解密入口 -------------------------
def encrypt_secret(plain: str) -> str:
    """加密字符串，返回带前缀的存储串。"""
    data = plain.encode("utf-8")
    if _HAS_DPAPI:
        return "dpapi:" + base64.b64encode(_dpapi_protect(data)).decode("ascii")
    return "obf:" + _obf_protect(data).decode("ascii")


def decrypt_secret(token: str) -> str:
    """解密存储串，返回明文（仅在内存中，不打印）。"""
    if not token:
        return ""
    if token.startswith("dpapi:"):
        blob = base64.b64decode(token[len("dpapi:"):])
        return _dpapi_unprotect(blob).decode("utf-8")
    if token.startswith("obf:"):
        return _obf_unprotect(token[len("obf:"):].encode("ascii")).decode("utf-8")
    return token  # 兼容历史明文（首次保存会被重新加密）


# ------------------------- 配置对象 -------------------------
DEFAULTS = {
    "api": {
        "api_key_encrypted": "",
        "base_url": "https://api.deepseek.com",
        "balance_endpoint": "/user/balance",
        "usage_endpoint": "/user/usage",
        "timeout": "10",
        "retries": "3",
    },
    "app": {
        "auto_refresh": "false",
        "refresh_interval": "300",
    },
    # 界面折叠状态：true = 该板块已收起（下次启动保持）
    "ui": {
        # 界面语言：zh-CN / en-US（启动时读取，未设置默认 zh-CN）
        "lang": "zh-CN",
        "collapse_balance": "false",
        "collapse_usage": "false",
        "collapse_price": "false",
        "collapse_chart": "false",
        # 迷你卡（钉在桌面）可显示的子项：true = 显示
        "mini_show_balance": "true",
        "mini_show_period": "true",
        "mini_show_price": "true",
        "mini_show_cons": "false",
        "mini_show_net": "true",
        # 迷你窗玻璃卡主题："" = 跟随系统明暗；light / dark = 固定
        "mini_theme": "",
        # 真·液态玻璃（DWM acrylic）。**默认关闭**——开启后 DWM 会把整块客户区
        # 重新合成，Tk 用 GDI 绘制的文字被一并模糊，字全部发虚看不清（2026-10-25
        # 真机截图确认）。关闭时用实色窗底 + 圆角/受光/描边模拟玻璃质感，清晰可控。
        "glass": "false",
    },
}


class Config:
    def __init__(self, path: str = None):
        self.path = path or default_config_path()
        self.parser = configparser.ConfigParser()
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            self.parser.read(self.path, encoding="utf-8")
        for sec, opts in DEFAULTS.items():
            if not self.parser.has_section(sec):
                self.parser.add_section(sec)
            for k, v in opts.items():
                if not self.parser.has_option(sec, k):
                    self.parser.set(sec, k, v)

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            self.parser.write(f)

    # ---- API Key ----
    @property
    def api_key(self) -> str:
        return decrypt_secret(self.parser.get("api", "api_key_encrypted", fallback=""))

    @api_key.setter
    def api_key(self, value: str):
        self.parser.set("api", "api_key_encrypted", encrypt_secret(value))

    def has_key(self) -> bool:
        return bool(self.api_key.strip())

    # ---- 通用读写 ----
    def get(self, section: str, key: str, fallback=None):
        return self.parser.get(section, key, fallback=fallback)

    def set(self, section: str, key: str, value):
        self.parser.set(section, key, str(value))

    # ---- 语言 ----
    @property
    def lang(self) -> str:
        return self.get("ui", "lang", "zh-CN") or "zh-CN"

    @lang.setter
    def lang(self, value: str):
        self.parser.set("ui", "lang", str(value))
