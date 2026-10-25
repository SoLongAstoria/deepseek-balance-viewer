# -*- coding: utf-8 -*-
"""导出迷你卡位图预览（= 真机所见，含阴影外扩）。

沙箱无法可靠抓 Tk 窗口，但 MiniView 渲染出的 PIL 位图就是 apply_layered_bitmap
贴到桌面窗口上的那张图——所以直接导出它就是"用户真实会看到的画面"，
也是验证「四周黑边已消失」最权威的物证（四角 alpha=0）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uikit

SCALE = 1.25  # 与 _mini_scale 默认档位接近
SHOW_ALL = {k: True for k in ("balance", "period", "price", "cons")}
DATA = {
    "balance": "¥128.34",
    "badge_period": "闲时 · 5 折",
    "cons_today": "¥3.21",
    "cons_month": "¥86.40",
    "price": "输出 ¥4/百万",
    "net_down": "↓ 499 KB/s",
    "net_up": "↑ 12 KB/s",
}
ONLY_BAL = {k: (k == "balance") for k in ("balance", "period", "price", "cons")}


def export(pal_name, show, fname):
    pal = uikit.MINI_THEMES[pal_name]
    mv = uikit.MiniView(scale=SCALE)
    # shadow=False → 纯卡片位图（无阴影外扩），与 Tk Label 实际显示一致
    mv.render(pal, DATA, show, glass_on=False, shadow=False)
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)
    ok = mv.export(path)
    a = mv._last_img.getchannel("A").load()
    TW, TH = mv._last_img.size
    corners = (a[0, 0], a[TW - 1, 0], a[0, TH - 1], a[TW - 1, TH - 1])
    print(f"  {fname}: size={mv._last_img.size} 四角alpha={corners} "
          f"中心alpha={a[TW//2, TH//2]} ok={ok}")


if __name__ == "__main__":
    print("导出迷你卡预览位图：")
    export("dark", SHOW_ALL, "_preview_mini_dark.png")
    export("light", SHOW_ALL, "_preview_mini_light.png")
    export("dark", ONLY_BAL, "_preview_mini_dark_onlybal.png")
    print("完成。")
