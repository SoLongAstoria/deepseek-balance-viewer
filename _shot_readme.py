# -*- coding: utf-8 -*-
"""生成 README 用的界面截图（演示数据，不含任何真实账户信息）。

跑法: build-venv/Scripts/python.exe _shot_readme.py
产出: docs/screenshot-light.png / docs/screenshot-dark.png / docs/screenshot-mini.png

安全设计：
  - 配置与历史都指向临时目录（DSBV_CONFIG / DSBV_HISTORY），绝不碰用户真实数据；
  - 注入的是**演示用假 Key**（`sk-demo…`），且输入框默认 `•` 遮罩，截不到明文；
  - 余额 / 消耗 / 网速全是构造的演示值；
  - 用 PrintWindow 只抓窗口自身，不会带上桌面壁纸或其它窗口。
"""
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta

# ⚠ 必须在 import ui / config / history 之前设好，模块加载时就会读这两个变量
_TMP = tempfile.mkdtemp(prefix="dsbv_readme_")
os.environ["DSBV_CONFIG"] = os.path.join(_TMP, "config.ini")
os.environ["DSBV_HISTORY"] = os.path.join(_TMP, "history.json")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DEMO_KEY = "sk-demo0000000000000000000000000000000000"   # 假 Key，仅用于显示遮罩效果
BAL_TOTAL = 86.42
BAL_GRANT = 10.00
BAL_TOPUP = 76.42
MONTH_START_BAL = 104.82          # 月初余额 → 本月消耗 = 104.82-86.42 = 18.40
TODAY_START_BAL = 89.28           # 今日 0 点余额 → 今日消耗 = 89.28-86.42 = 2.86

OUT_DIR = "docs"


def build_history():
    """构造一个月内的余额快照：月初 104.82 → 今天 86.42（今日消耗 2.86）。"""
    now = datetime.now()
    today0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month0 = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    rows = []

    def add(ts, bal):
        rows.append({"ts": ts.timestamp(),
                     "time": ts.strftime("%Y-%m-%d %H:%M:%S"),
                     "balance": round(bal, 2), "currency": "CNY"})

    # 月初之前两条（作为「本月」区间基准）
    add(month0 - timedelta(days=3), MONTH_START_BAL)
    add(month0 - timedelta(hours=6), MONTH_START_BAL)

    # 月初 → 今天 0 点：均匀下降 104.82 → 89.28
    span = (today0 - month0).total_seconds()
    steps = 40
    for i in range(1, steps + 1):
        ts = month0 + timedelta(seconds=span * i / steps)
        bal = MONTH_START_BAL + (TODAY_START_BAL - MONTH_START_BAL) * i / steps
        add(ts, bal)

    # 今天：89.28 → 86.42
    now_span = (now - today0).total_seconds()
    for i in range(1, 7):
        ts = today0 + timedelta(seconds=now_span * i / 6)
        bal = TODAY_START_BAL + (BAL_TOTAL - TODAY_START_BAL) * i / 6
        add(ts, bal)
    return rows


def main():
    import config as cfg
    import history as histmod
    import ui

    # 演示配置：写入假 Key（DPAPI 加密到临时 config.ini）
    c = cfg.Config()
    c.api_key = DEMO_KEY
    c.set("ui", "refresh_sec", "300")
    c.set("ui", "auto_start", "true")
    c.set("ui", "glass", "false")
    c.save()

    # 演示历史（不落盘：直接替换读取函数）
    fake_hist = build_history()
    histmod.load_history = lambda: list(fake_hist)
    histmod.save_snapshot = lambda b, cur: list(fake_hist)

    os.makedirs(OUT_DIR, exist_ok=True)

    app = ui.App()
    app.update()
    fake = {"is_available": True, "infos": [{
        "currency": "CNY", "total_balance": BAL_TOTAL,
        "granted_balance": BAL_GRANT, "topped_up_balance": BAL_TOPUP}]}
    app._fill_price()
    app._fill_from_balance(fake)
    app._data["net_down"] = "128 KB/s"
    app._data["net_up"] = "8 KB/s"
    app.refresh_view()
    for _ in range(6):
        app.update()
    app.lift()
    app.update()

    # 主窗截图（只抓窗口自身，不含桌面）
    for t in ("light", "dark"):
        if app.theme != t:
            app._toggle_theme()
        for _ in range(8):
            app.update()
        fn = os.path.join(OUT_DIR, f"screenshot-{t}.png")
        w, h = ui_grab(app.winfo_id(), fn)
        print(f"{t:5s} -> {fn}  {w}x{h}")

    # 迷你卡（钉在桌面）：切回浅色，再抓一张卡片
    try:
        if app.theme != "light":
            app._toggle_theme()
        # 迷你卡的网速行读 _net_last（主窗是自己塞进 _data 的），这里补一份，
        # 否则卡片底部会显示 "-- --"（演示图不好看，且不反映真实排版）
        app._net_last = (128 * 1024, 8 * 1024)
        for _k in app.mini_show_vars:
            app.mini_show_vars[_k].set(True)
        app._open_mini()
        for _ in range(6):
            app.update()
        app._mini_autosize(animate=False)
        for _ in range(8):
            app.update()
        if app.mini is not None:
            fn = os.path.join(OUT_DIR, "screenshot-mini.png")
            w, h = ui_grab(app.mini.winfo_id(), fn)
            print(f"mini  -> {fn}  {w}x{h}")
    except Exception as e:
        print("mini shot failed:", e)

    app.tray_mgr.stop()
    app.destroy()
    return 0


def ui_grab(hwnd, path):
    import _shot_ui
    return _shot_ui.grab(hwnd, path)


if __name__ == "__main__":
    sys.exit(main())
