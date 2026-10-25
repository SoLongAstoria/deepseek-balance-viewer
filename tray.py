# -*- coding: utf-8 -*-
"""系统托盘封装（pystray + Pillow）。

- 托盘图标与 exe / 窗口图标同源：由 `icon_art.py` 统一绘制，无需外部图片文件。
- 菜单：显示主窗口 / 钉在桌面 / 刷新 / 退出。
- 菜单回调必须经 tkinter 主线程执行（tkinter 非线程安全），故全部用 `_post()` → `after(0, ...)` 切回。
- 在无桌面环境（如服务器会话）下 run() 会失败，start() 返回 False，由调用方退化为「关闭即退出」。
- **未安装 pystray / Pillow 时不报错**：模块仍可导入，只是 start() 返回 False（核心功能零依赖）。
"""

try:
    from PIL import Image, ImageDraw
    import pystray
    TRAY_AVAILABLE = True
    TRAY_IMPORT_ERROR = None
except Exception as _e:   # 缺依赖则降级为无托盘，不能因此让主程序起不来
    TRAY_AVAILABLE = False
    TRAY_IMPORT_ERROR = _e


def make_icon(size: int = 64):
    """托盘图标 —— 与 exe / 窗口图标**同源**（`icon_art`）。

    托盘实际显示只有 16~24px，所以固定用**简化版**（`plain`：只有水位环，
    无指针）——带指针的完整版在这个尺寸会和环糊成一团。
    """
    try:
        import icon_art
        img = icon_art.render(size, "plain")
        if img is not None:
            return img
    except Exception:
        pass
    # 兜底：极简绿圆（仅防 icon_art 异常，正常路径不会走到）
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((6, 6, size - 6, size - 6), fill="#2E7D32")
    return img


class TrayManager:
    def __init__(self, app):
        self.app = app
        self.icon = None

    def start(self) -> bool:
        """在后台线程启动托盘；失败返回 False。"""
        if not TRAY_AVAILABLE:
            print(f"[tray] 未安装 pystray/Pillow，降级为无托盘模式：{TRAY_IMPORT_ERROR}")
            return False
        try:
            self.icon = pystray.Icon(
                "DeepSeekBalanceViewer",
                make_icon(),
                "DeepSeek 余额查看器",
            )
            self.icon.menu = pystray.Menu(
                pystray.MenuItem("显示主窗口", self._show_main),
                pystray.MenuItem("钉在桌面", self._open_mini),
                pystray.MenuItem("刷新", self._refresh),
                pystray.MenuItem("退出", self._quit),
            )
            self.icon.run_detached()   # 非阻塞，内部启线程
            return True
        except Exception as e:   # 无桌面 / 缺依赖等
            print(f"[tray] 启动失败，降级为无托盘模式：{e}")
            return False

    def stop(self):
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass

    def notify(self, title: str, message: str):
        if self.icon:
            try:
                self.icon.notify(message, title)
            except Exception:
                pass

    # ---- 菜单回调（签名固定为 icon, item）；切回主线程操作 tkinter ----
    def _post(self, fn):
        """把回调排到 tkinter 主线程执行。

        app 可能是 Tk 实例本身（本项目 App 即 tk.Tk 子类），也可能是持有 .root 的包装对象，
        故两者都兼容——直接写 app.root.after 会在前者上抛 AttributeError，
        且异常发生在托盘线程里会被静默吞掉，表现为「点菜单没反应」。
        """
        tk_app = getattr(self.app, "root", self.app)
        tk_app.after(0, fn)

    def _show_main(self, icon, item):
        self._post(self.app._restore_from_tray)

    def _open_mini(self, icon, item):
        self._post(self.app._open_mini)

    def _refresh(self, icon, item):
        self._post(self.app.trigger_refresh)

    def _quit(self, icon, item):
        self._post(self.app._quit_app)
