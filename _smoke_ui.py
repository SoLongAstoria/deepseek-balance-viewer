# -*- coding: utf-8 -*-
"""界面冒烟：真实构建 App → 注入样例数据 → 逐块重绘 → 校验布局。

不发网络请求（用假数据走 UI 路径），只验证绘制/交互/主题切换是否稳定，
以及设计稿关键尺寸是否与 _mockup.html 一致。
"""
import os, tempfile
# 配置 + 历史双重隔离：冒烟测试绝不碰用户真实 config.ini / history.json
# （踩坑：只隔离配置时，注入的样例余额 12.34 被真实写进 history.json，
#   与真实余额交替出现 → 「累计消耗」被算成 8 × 66.60 = 532.80）
_TMP = tempfile.mkdtemp(prefix="dsbv_smoke_")
os.environ.setdefault("DSBV_CONFIG", os.path.join(_TMP, "config.ini"))
os.environ.setdefault("DSBV_HISTORY", os.path.join(_TMP, "history.json"))

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ui
import uikit
import pricing as pm
import config as cfg
import history as histmod

FAIL = []

# 硬护栏：历史文件必须落在临时目录，否则立刻中止（防止再次污染真实数据）
assert os.path.abspath(histmod.HISTORY_PATH).startswith(os.path.abspath(_TMP)), \
    f"历史文件未隔离：{histmod.HISTORY_PATH}（真实数据有被写脏的风险，已中止）"


def check(name, cond, extra=""):
    print(("  [OK]   " if cond else "  [FAIL] ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        FAIL.append(name)


def main():
    app = ui.App()
    app.withdraw()          # 不弹窗，纯逻辑 + 绘制
    app.update()

    v = app.view
    print("\n== 设计稿尺寸核对 ==")
    check("窗口宽 560", abs(uikit.MainView.WIN_W - 560) < 0.01)
    check("窗口高 676", abs(uikit.MainView.WIN_H - 676) < 0.01,
          f"实际 {uikit.MainView.WIN_H}")
    check("Hero 起点 y=47", abs(v.y_hero - 47) < 0.01, f"{v.y_hero}")
    check("价格卡起点 y=198", abs(v.y_price - 198) < 0.01, f"{v.y_price}")
    check("走势卡起点 y=334", abs(v.y_chart - 334) < 0.01, f"{v.y_chart}")
    check("设置卡起点 y=503", abs(v.y_set - 503) < 0.01, f"{v.y_set}")
    check("状态栏起点 y=654", abs(v.y_status - 654) < 0.01, f"{v.y_status}")
    check("内容底部 = 窗口高", abs(v.y_status + v.STATUS_H - v.WIN_H) < 0.01)
    check("缩放比合理", 0.7 <= v.S <= 3.0, f"S={v.S:.3f}")

    print("\n== 渲染基线 ==")
    n0 = len(v.find_all())
    check("Canvas 有绘制内容", n0 > 120, f"{n0} items")
    check("交互区域已登记", len(v._regions) >= 6, f"{len(v._regions)} 个")

    print("\n== 注入样例数据（模拟一次成功刷新） ==")
    app._fill_price()
    fake = {"is_available": True, "infos": [{
        "currency": "CNY", "total_balance": 12.34,
        "granted_balance": 5.00, "topped_up_balance": 7.34}]}
    ok = app._fill_from_balance(fake)
    app.refresh_view()
    app.update()
    check("余额填充成功", ok)
    check("Hero 余额文案", app._data.get("balance") == "12.34",
          app._data.get("balance"))
    check("价格表 3 行", len(app._data.get("price_rows", [])) == 3,
          f"{len(app._data.get('price_rows', []))} 行")
    check("比例条有值", app._data.get("grant_pct", 0) > 0,
          f"赠金 {app._data.get('grant_pct'):.1f}%")
    n1 = len(v.find_all())
    check("数据注入后重绘正常", n1 > 120, f"{n1} items")

    print("\n== 局部重绘（网速每秒走的路径） ==")
    before = len(v.find_all())
    for i in range(3):
        app._data["net_down"] = f"{10 + i} KB/s"
        app._data["net_up"] = f"{i} KB/s"
        app.refresh_view("hero")
        app.update()
    after = len(v.find_all())
    check("hero 局部重绘不增长 items", abs(after - before) <= 2,
          f"{before} → {after}")
    check("hero 区块仍存在", len(v.find_all()) > 0)

    print("\n== 交互命中测试 ==")
    for key in (v.K_THEME, v.K_MINI, v.K_REFRESH, v.K_CSV, v.K_ABOUT,
                v.K_INTERVAL, v.K_AUTOSTART, v.K_PRICE_INFO):
        hit = [r for r in v._regions if r[4] == key]
        check(f"可点击：{key}", bool(hit), f"{len(hit)} 处")
    chip_hits = [r for r in v._regions if str(r[4]).startswith("chip:")]
    check("5 个 chips 均可点", len(chip_hits) == 5, f"{len(chip_hits)} 个")

    print("\n== 定时器 / 状态 ==")
    check("网速轮询已启动", app._net_timer is not None)
    check("价格倒计时文案", "距" in app._data.get("price_more", ""),
          app._data.get("price_more", ""))

    print("\n== 主题切换 ==")
    for t in ("light", "dark"):
        app.theme = "dark" if t == "light" else "light"   # 触发翻转
        app._toggle_theme()
        app.update()
        check(f"切到 {app.theme} 正常", app.view.theme == app.theme,
              f"{len(v.find_all())} items")
    app._toggle_theme()
    app.update()

    print("\n== 迷你卡渲染（纯 PIL 位图，与真机路径一致） ==")
    # MiniView 现在是纯渲染器（非 Canvas）：整窗 = 卡片 + 四周阴影外扩，
    # 由 PIL 合成一张位图，App 再用 apply_layered_bitmap 逐像素贴到无控件窗口。
    mv = uikit.MiniView(scale=v.S)
    show_all = {k: True for k, _l in ui.MINI_CHIPS}
    data = {"balance": "¥12.34", "badge_period": "闲时 · 5 折",
            "cons_today": "¥3.21", "cons_month": "¥86.40",
            "price": "输出 ¥4/百万", "net_down": "↓ 499 KB/s",
            "net_up": "↑ 12 KB/s"}
    w, h = mv.render(uikit.MINI_THEMES["dark"], data, show_all, False)
    check("迷你卡宽 300", w == 300, f"{w}")
    # 全显示 = 余额+时段 / 今日 / 本月 / 计费 / 网速 → 149
    check("迷你卡全显示高 149", abs(h - 149) < 0.6, f"{h}")
    # 设计稿原图组合（无「当前计费」行）= 131
    show_design = dict(show_all, price=False)
    _w, hd = mv.render(uikit.MINI_THEMES["dark"], data, show_design, False)
    check("迷你卡对齐设计稿高 131", abs(hd - 131) < 0.6, f"{hd}")
    w2, h2 = mv.render(uikit.MINI_THEMES["light"], data,
                       {k: (k == "balance") for k, _l in ui.MINI_CHIPS}, False)
    check("只显示余额时变矮", h2 < h, f"{h2}")
    img = getattr(mv, "_last_img", None)
    check("迷你卡位图已生成", img is not None,
          "None" if img is None else f"{img.size}")
    if img is not None:
        TW, TH = img.size
        # 位图含阴影外扩，应比卡片（= w2×h2 × S）更大
        check("位图含阴影外扩",
              TW > mv.px_(w2) and TH > mv.px_(h2),
              f"{img.size} vs 卡片 {(mv.px_(w2), mv.px_(h2))}")
        colors = img.convert("RGB").getcolors(maxcolors=1 << 18) or []
        # 渐变 + 文字 + 徽章 → 颜色数远多于纯色块
        check("位图有真实绘制内容（渐变+文字）", len(colors) > 200, f"{len(colors)} 色")
        # ⚠ 关键回归：四角必须完全透明（证明「没有一圈黑边」），
        # 卡面中心必须不透明（卡片完整）。这正是用户报的「黑边」根因。
        a = img.getchannel("A")
        pa = a.load()
        corners = [pa[0, 0], pa[TW - 1, 0], pa[0, TH - 1], pa[TW - 1, TH - 1]]
        check("四角透明（无黑边）", all(c == 0 for c in corners), str(corners))
        check("卡面中心不透明", pa[TW // 2, TH // 2] == 255,
              f"{pa[TW // 2, TH // 2]}")

    print("\n== 实底迷你窗（统一 Tk 卡片 + region 圆角）集成 ==")
    # 回退方案：Tk overrideredirect 窗口承载卡片位图，region 裁圆角。
    # 彻底移除 Win32 分层窗 / layered 贴图 / 独立阴影窗（真实 DWM 下冲突源）。
    app.config_obj.set("ui", "glass", "false")
    try:
        app._open_mini()
        check("实底模式创建了 Tk 迷你窗", app.mini is not None)
        check("实底模式无遗留 mini_win", getattr(app, "mini_win", None) is None)
        check("迷你卡位图已渲染",
              getattr(app.mini_view, "_last_img", None) is not None)
        check("Label 已承载卡片位图 (PhotoImage)",
              getattr(app, "mini_img", None) is not None)
        check("位置已记录到 _mini_pos", getattr(app, "_mini_pos", None) is not None)
        # ⚠ 关键：之前「打不开」的真凶就是设了 geometry 却不 update_idletasks，
        # 窗口停在初始 1x1（看不见）。必须验证尺寸真的生效。
        if app.mini is not None:
            g = app.mini.geometry()
            ws = getattr(app.mini_view, "window_size", None)
            check("开迷你窗后窗口尺寸生效(非1x1)",
                  "1x1" not in g and ws is not None
                  and f"{ws[0]}x{ws[1]}" in g,
                  f"geo={g} ws={ws}")
        # ⚠ 四角必须被 region 裁掉：位图角落是 alpha=0，Tk 会把它们合成到
        # 窗口底色上 → 真机看到「四角黑底」。只有窗口 region 真的切圆角才行。
        if app.mini is not None and ws is not None:
            import glass as _g
            s = _g.dpi_scale(app.mini)
            lw, lh = ws[0] / s, ws[1] / s
            cuts = [_g.region_corner_cut(app.mini, x, y) for x, y in
                    ((1, 1), (lw - 2, 1), (1, lh - 2), (lw - 2, lh - 2))]
            check("迷你窗四角被 region 切掉(无黑底)", all(cuts), str(cuts))
            check("迷你窗中心未被误裁",
                  not _g.region_corner_cut(app.mini, lw / 2, lh / 2))
        # 拖拽：直接走移动逻辑，验证位置记录与窗口几何更新
        ox, oy = 2000, 50
        app._move_mini(ox, oy)
        check("拖拽更新 _mini_pos", app._mini_pos == (ox, oy),
              f"{app._mini_pos}")
        if app.mini is not None:
            g2 = app.mini.geometry()
            check("拖拽更新窗口几何(位置+尺寸)",
                  "1x1" not in g2 and f"+{ox}+{oy}" in g2,
                  g2)
        app._close_mini()
        check("关闭后迷你窗已销毁", app.mini is None)
        check("关闭后渲染器已清空", app.mini_view is None)
        check("关闭后主窗恢复可见", app.winfo_viewable())
    except Exception as e:
        import traceback
        traceback.print_exc()
        check("实底迷你窗集成不抛异常", False, str(e))

    app._quit_app()

    print("\n" + ("=" * 52))
    if FAIL:
        print(f"RESULT: FAIL ({len(FAIL)}) -> " + ", ".join(FAIL))
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
