# -*- coding: utf-8 -*-
"""DeepSeek 余额 / 用量查看器 —— tkinter 界面。

UI 结构完全对照 `_mockup.html` 设计稿实现，绘制逻辑在 uikit.py：
    主窗 560×676：titlebar 35 / Hero 三联 141 / 模型价格 126 /
                  走势图 159 / 设置 137 / 状态栏 22

业务能力（与原版一致）：
- 当前余额、赠金 / 充值构成比例条
- 本地追踪的今日 / 本月消耗与余额走势
- 手动刷新 + 可配置间隔的自动刷新（后台线程，界面不卡顿）
- 网络失败 / Key 无效 / 限流等异常明确提示
- 桌面悬浮迷你卡（真·液态玻璃）+ 实时网速监控
"""

import os
import sys
import tkinter as tk
from tkinter import messagebox, simpledialog
import threading
from datetime import datetime

import config as cfg
import api as dsapi
import history as histmod
import pricing as price_mod
import tray as tray_mod
import netmon
import glass
import uikit
import i18n
from uikit import MAIN_THEMES, MINI_THEMES, APP_VERSION, _mix

# 网速轮询间隔（毫秒）：每 1 秒刷新一次实时上下行速率
NET_REFRESH_MS = 1000

# 迷你窗「液态玻璃」卡 —— 圆角半径（逻辑像素，按 DPI 换算成物理像素裁剪）
# ⚠ 迷你卡的实际圆角已统一到 uikit.MINI_CARD_RADIUS（位图 mask 与窗口
# region 必须同源，否则四角露底色）；本常量仅历史留档。
GLASS_RADIUS = uikit.MINI_CARD_RADIUS
# 迷你卡投影浓度（按主题）：浅色卡在亮桌面上需要更淡，深色卡稍重一点
_SHADOW_ALPHA = {"light": 0.15, "dark": 0.30}

# 迷你卡显示项（顺序 = 设计稿 chips 顺序）；label 为 i18n 键，渲染时再翻译
MINI_CHIPS = (
    ("balance", "chip_balance"),
    ("period", "chip_period"),
    ("price", "chip_price"),
    ("cons", "chip_usage"),
    ("net", "chip_net"),
)


class App(tk.Tk):
    def __init__(self, start_mini=False):
        # 高 DPI 适配：必须在创建任何 Tk 窗口前声明，否则之后设置无效。
        # 让 tkinter 拿到真实逻辑像素，高缩放屏下不模糊、布局不被裁切。
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
        except Exception:
            pass

        super().__init__()
        self.title(i18n.t("app_title"))
        self.resizable(False, False)
        self._apply_app_icon()

        self.config_obj = cfg.Config()
        # 界面语言：优先读配置，未设置保持默认（zh-CN）
        i18n.set_lang(self.config_obj.lang)
        self.title(i18n.t("app_title"))
        self._auto_timer = None
        self.mini = None            # 迷你置顶窗口（Tk Toplevel），未打开为 None
        self.mini_view = None       # 迷你卡渲染器（MiniView）
        self.mini_img = None        # 卡片位图（PIL.ImageTk.PhotoImage 引用）
        self.mini_img_label = None  # 承载位图的 Label
        self._glass_on = False      # 预留：真·acrylic 是否生效（当前路径未用）
        self.last_main_data = None  # 最近一次成功刷新的数据，供迷你窗展示
        self.last_balance = None    # 最近一次余额响应，主题切换后回填

        # 主题：config 固定值优先；为空则跟随系统明暗
        _t = self.config_obj.get("ui", "mini_theme", "") or (
            "light" if glass.system_is_light() else "dark")
        self.theme = _t if _t in MAIN_THEMES else "dark"

        # 布局缩放：DPI 优先，屏幕放不下时整体等比缩小
        try:
            dpi = glass.dpi_scale(self)
        except Exception:
            dpi = 1.0
        self.S = uikit.compute_scale(self.winfo_screenwidth(),
                                     self.winfo_screenheight(), dpi,
                                     uikit.MainView.WIN_W, uikit.MainView.WIN_H)

        # 网速监控
        self.net_sampler = netmon.NetSampler()
        self._net_timer = None
        self._net_last = None
        self._mini_tween_id = None

        # 迷你卡可配置显示项（持久化于 config.ini [ui] 段）
        self.mini_show_vars = {
            k: tk.BooleanVar(
                value=self.config_obj.get("ui", f"mini_show_{k}",
                                          "true" if k != "cons" else "false") == "true")
            for k, _lab in MINI_CHIPS
        }

        # 数据快照（界面状态由它驱动）
        self._data = {}
        self._status_text = i18n.t("status_ready")
        self._history_cache = []

        self._build_ui()
        self._evaluate_key_state()
        self._start_net_monitor()

        # 系统托盘（常驻）；无桌面环境会失败并退化为「关闭即退出」
        self.tray_mgr = tray_mod.TrayManager(self)
        self.tray_ok = self.tray_mgr.start()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        if not self.tray_ok:
            self.set_status(i18n.t("tray_unavailable"))

        if self.config_obj.has_key():
            if start_mini:
                self._open_mini()
            else:
                self.trigger_refresh()

    # ==================================================================
    # 界面装配
    # ==================================================================
    def _apply_app_icon(self):
        """窗口标题栏 / 任务栏图标 —— 与 exe、托盘图标**同源**（icon_art）。

        exe 图标由打包时的 `--icon app_icon.ico` 写进 PE 资源；运行时的窗口图标
        另需显式设置，否则从源码跑会显示 Tk 默认羽毛。缺 Pillow 时静默跳过。
        """
        try:
            import icon_art
            img = icon_art.render(64)
            if img is None:
                return
            from PIL import ImageTk
            # ⚠ 必须留引用：PhotoImage 被 GC 后图标会变空白
            self._icon_photo = ImageTk.PhotoImage(img)
            self.iconphoto(True, self._icon_photo)
        except Exception:
            pass

    def _build_ui(self):
        """放置整窗 Canvas（设计稿尺寸），并套用主窗玻璃化。"""
        glass_ok = self._apply_window_glass()
        self.view = uikit.MainView(self, self, scale=self.S, glass_on=glass_ok)
        self.view.pack(fill="both", expand=True)
        self.geometry(f"{self.view.px_(uikit.MainView.WIN_W)}x"
                      f"{self.view.px_(uikit.MainView.WIN_H)}")
        # 居中到主屏
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 3)}")

    def _glass_enabled(self):
        """真·液态玻璃开关（config `[ui] glass`），**默认关闭**。

        ⚠ 2026-10-25 用户真机截图确认的硬事实：`AccentState=3(BLURBEHIND)`
        会让 DWM 把整块客户区纳入合成，Tk/GDI 绘制的文字被一起模糊——
        表现为"字全部发虚、完全看不清"，且与配色无关，调色救不回来。
        因此默认走**实色窗底 + 圆角/受光/描边模拟玻璃**：像素级可控、对比度达标。
        想体验真 backdrop 可在 config.ini 里把 `[ui] glass` 改成 true（字会变糊）。
        """
        try:
            return str(self.config_obj.get("ui", "glass", "false")).strip().lower() \
                in ("1", "true", "yes", "on")
        except Exception:
            return False

    def _apply_window_glass(self):
        """主窗玻璃化（对照效果图 .win）：acrylic 染色 + Win11 系统圆角。

        注意顺序问题：glass 要在窗口已有 hwnd 之后套用，而 Canvas 的底色
        取决于 glass 是否生效（生效时铺纯黑作掩膜，让 DWM 换成 backdrop）。
        未开启（默认）时会主动 clear 一次，确保没有残留的 DWM 合成状态。
        """
        pal = MAIN_THEMES[self.theme]
        self.update_idletasks()
        if not self._glass_enabled():
            try:
                glass.clear_window_glass(self)
            except Exception:
                pass
            self.configure(bg=pal["win_bg"])
            return False
        try:
            ok = glass.apply_window_glass(self, pal["tint"],
                                          dark=(self.theme == "dark"))
        except Exception:
            ok = False
        if not ok:
            try:
                glass.clear_window_glass(self)
            except Exception:
                pass
        self.configure(bg="#000000" if ok else pal["win_bg"])
        return ok

    # ==================================================================
    # 状态组装
    # ==================================================================
    def _build_state(self):
        """把所有界面需要的字段拼成一个 dict，交给 MainView 渲染。"""
        pal = MAIN_THEMES[self.theme]
        st = dict(self._data)
        st.update({
            "api_key": self.config_obj.api_key,
            "interval": self._interval(),
            "autostart": self._is_autostart_enabled(),
            "status": self._status_text,
            "chips": [(k, i18n.t(lab), self.mini_show_vars[k].get())
                      for k, lab in MINI_CHIPS],
            "net_down": self._data.get("net_down", "--"),
            "net_up": self._data.get("net_up", "--"),
        })
        return st

    def refresh_view(self, *blocks):
        if getattr(self, "view", None) is None:
            return
        if blocks:
            self.view.update_state(_blocks=blocks, **self._build_state())
        else:
            self.view.update_state(**self._build_state())

    def _interval(self):
        try:
            return max(30, int(self.config_obj.get("app", "refresh_interval", "300")))
        except Exception:
            return 300

    def set_status(self, msg: str):
        self._status_text = f"{datetime.now().strftime('%H:%M:%S')}  {msg}"
        self.refresh_view("status")

    # ==================================================================
    # 视图交互回调
    # ==================================================================
    def on_view_click(self, key):
        if key == uikit.MainView.K_MINI:
            self._open_mini()
        elif key == uikit.MainView.K_THEME:
            self._toggle_theme()
        elif key == uikit.MainView.K_REFRESH:
            self.trigger_refresh()
        elif key == uikit.MainView.K_SHOT:
            self.export_screenshot()
        elif key == uikit.MainView.K_PRICE_INFO:
            self.show_price_info()
        elif key == uikit.MainView.K_CSV:
            self.export_csv()
        elif key == uikit.MainView.K_ABOUT:
            self.show_about()
        elif key == uikit.MainView.K_AUTOSTART:
            self._toggle_autostart()
        elif key == uikit.MainView.K_INTERVAL:
            self._edit_interval()
        elif key == uikit.MainView.K_LANG:
            self._toggle_lang()
        elif key.startswith("chip:"):
            k = key.split(":", 1)[1]
            var = self.mini_show_vars.get(k)
            if var is not None:
                var.set(not var.get())
                self._on_mini_show_toggle()

    def on_key_commit(self, text):
        """API Key 输入框失焦 / 回车：内容有变化才落盘。"""
        val = (text or "").strip()
        if val == self.config_obj.api_key.strip():
            return
        self.config_obj.api_key = val
        self.config_obj.save()
        self._evaluate_key_state()
        self.set_status(i18n.t("fmt_apikey_saved")
                       + ("" if val else i18n.t("apikey_cleared")))
        if val:
            self.trigger_refresh()

    def _toggle_autostart(self):
        want = not self._is_autostart_enabled()
        ok = self._set_autostart(want)
        if ok:
            self.set_status(i18n.t("fmt_autostart_on") if want
                            else i18n.t("fmt_autostart_off"))
        else:
            self.set_status(i18n.t("autostart_fail"))
        self.refresh_view("settings")

    def _edit_interval(self):
        cur = self._interval()
        val = simpledialog.askinteger(
            i18n.t("interval_title"), i18n.t("interval_prompt"),
            initialvalue=cur, minvalue=30, maxvalue=3600, parent=self)
        if not val:
            return
        self.config_obj.set("app", "refresh_interval", str(val))
        self.config_obj.save()
        if self.auto_on():
            self._schedule_auto()
        self.set_status(i18n.t("fmt_interval_set", val=val))
        self.refresh_view("settings")

    def show_price_info(self):
        """价格卡右上角说明（原价格表下方的注释，收进弹窗以保持卡面紧凑）。"""
        _p, rows = price_mod.get_price_table()
        versions = " / ".join(f"{m['id']} = {m['version']}" for m in rows)
        concs = " / ".join(f"{m['id']} {m['conc']}" for m in rows)
        messagebox.showinfo(
            i18n.t("price_info_title"),
            i18n.t("price_info_body",
                   versions=versions, concs=concs,
                   peak=price_mod.PEAK_FACTOR,
                   snapshot=price_mod.PRICING_SNAPSHOT,
                   source=price_mod.PRICING_SOURCE),
            parent=self)

    def show_about(self):
        messagebox.showinfo(
            i18n.t("about_title"),
            i18n.t("about_body",
                   version=APP_VERSION,
                   config=cfg.CONFIG_PATH,
                   source=price_mod.PRICING_SOURCE),
            parent=self)

    # ==================================================================
    # 数据 → 界面
    # ==================================================================
    def _evaluate_key_state(self):
        if not self.config_obj.has_key():
            self._data = {
                "cur": "¥", "balance": "--",
                "badge_period": i18n.t("no_key_badge"), "badge_gift": i18n.t("badge_gift_default"),
                "cons_today": "--", "cons_month": "--",
                "grant_pct": 0, "grant_val": "--", "topup_pct": 0, "topup_val": "--",
            }
            self._fill_price(None)
            self._fill_chart([])
            self.refresh_view()
            return
        self._fill_price(None)
        self.refresh_view()

    def _fill_price(self, _unused=None):
        """价格表状态：当前时段两行 + 另一时段对比一行（设计稿 3 行）。"""
        period, rows = price_mod.get_price_table()
        is_peak = period["peak"]
        short_cur = i18n.t("period_peak") if is_peak else i18n.t("period_offpeak")
        short_ref = i18n.t("period_offpeak") if is_peak else i18n.t("period_peak")
        off_zhe = 10 / price_mod.PEAK_FACTOR
        out = []
        for m in rows:
            cur = m["peak"] if is_peak else m["offpeak"]
            out.append({
                "name": m["id"],
                "vals": [f"¥{cur[k]:.2f}" for k, _l in price_mod.BILLING_ITEMS],
                "cur": True, "status": short_cur,
                "st_kind": "peak" if is_peak else "on",
            })
        first = rows[0]
        ref = first["offpeak"] if is_peak else first["peak"]
        out.append({
            "name": f"{first['id']} · {short_ref}",
            "vals": [f"¥{ref[k]:.2f}" for k, _l in price_mod.BILLING_ITEMS],
            "cur": False, "status": short_ref,
            "st_kind": "on" if is_peak else "peak", "dim": True,
        })
        # 卡头右侧：当前折扣 + 距切换时间
        disc = (i18n.t("fmt_peak_disc", factor=price_mod.PEAK_FACTOR)
                if is_peak else
                i18n.t("fmt_offpeak_disc", zhe=off_zhe, pct=off_zhe * 10))
        nxt = price_mod.next_period_change()
        more = i18n.t("fmt_more_active", period=short_cur, disc=disc)
        if nxt:
            next_period = (i18n.t("period_offpeak") if is_peak
                           else i18n.t("period_peak"))
            more += i18n.t("fmt_more_until",
                           next=next_period, left=self._fmt_left(nxt[0]))
        self._data.update({"price_rows": out, "is_peak": is_peak, "price_more": more})

    @staticmethod
    def _fmt_left(sec):
        h, m = int(sec // 3600), int(sec % 3600 // 60)
        return f"{h}h {m:02d}m" if h else f"{m}m"

    def _fill_chart(self, hist):
        """走势图：近 7 日余额曲线 + 底部日期轴 + 日均消耗。"""
        self._history_cache = hist or []
        vals, labels = [], []
        now = datetime.now()
        days = 7
        all_vals = [r["balance"] for r in (hist or [])]
        # 按天取样：最后一天为当前余额；历史每天取当天最后一个快照
        bmap = {}
        for r in (hist or []):
            d = r["time"][:10]
            bmap[d] = r["balance"]
        for i in range(days - 1, -1, -1):
            d = (now.timestamp() - i * 86400)
            key = datetime.fromtimestamp(d).strftime("%Y-%m-%d")
            if key in bmap:
                vals.append(bmap[key])
                labels.append(key[5:])
        if not vals and all_vals:
            vals = all_vals[-2:]
            labels = [r["time"][5:10] for r in (hist or [])][-2:]
        # 日均消耗
        t0 = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() - 6 * 86400
        cons7 = histmod.consumption_between(hist or [], t0)
        span = max(1, min(7, len(vals) or 1))
        self._data.update({
            "chart_vals": vals,
            "chart_labels": labels,
            "chart_more": i18n.t("fmt_daily_avg", v=f"{cons7 / span:,.2f}") if vals else "",
        })

    def _fill_from_balance(self, balance):
        """把一次余额响应转成界面数据（Hero 三格 + 双比例条 + 图表）。"""
        info = balance["infos"][0] if balance["infos"] else None
        if info is None:
            return False
        cur_sym = "¥" if info["currency"] in ("CNY", "RMB") else info["currency"]
        total = info["total_balance"]
        grant = info["granted_balance"]
        topup = info["topped_up_balance"]

        hist = histmod.save_snapshot(total, cur_sym)
        now = datetime.now()
        today0 = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        month0 = now.replace(day=1, hour=0, minute=0, second=0,
                             microsecond=0).timestamp()
        cons_today = histmod.consumption_between(hist, today0)
        cons_month = histmod.consumption_between(hist, month0)
        cons = histmod.consumption_since_start(hist)

        period, _r = price_mod.get_price_table()
        off_zhe = 10 / price_mod.PEAK_FACTOR
        if period["peak"]:
            badge = i18n.t("fmt_badge_peak", factor=price_mod.PEAK_FACTOR)
        else:
            badge = i18n.t("fmt_badge_offpeak", zhe=off_zhe, pct=off_zhe * 10)

        gp = (grant / total * 100) if total > 0 else 0
        tp = (topup / total * 100) if total > 0 else 0
        self._data.update({
            "cur": cur_sym,
            "balance": f"{total:,.2f}",
            "badge_period": badge,
            "badge_gift": i18n.t("fmt_grant", v=f"{grant:,.2f}"),
            "cons_today": f"{cur_sym}{cons_today:,.2f}",
            "cons_month": f"{cur_sym}{cons_month:,.2f}",
            "grant_pct": gp, "grant_val": f"¥{grant:,.2f} / ¥{total:,.2f}",
            "topup_pct": tp, "topup_val": f"¥{topup:,.2f} / ¥{total:,.2f}",
        })
        self._fill_chart(hist)
        self.last_main_data = {
            "total": total, "cur": cur_sym, "grant": grant,
            "topup": topup, "avail": balance.get("is_available"), "cons": cons,
        }
        return True

    # ==================================================================
    # 刷新逻辑（后台线程）
    # ==================================================================
    def trigger_refresh(self):
        if not self.config_obj.has_key():
            self.set_status(i18n.t("no_key_refresh"))
            return
        self.set_status(i18n.t("refreshing"))
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        def post(fn, *a):
            """把结果抛回主线程；窗口已销毁（退出竞态）时静默丢弃。"""
            try:
                self.after(0, fn, *a)
            except Exception:
                pass

        try:
            client = dsapi.DeepSeekClient(
                api_key=self.config_obj.api_key,
                base_url=self.config_obj.get("api", "base_url"),
                timeout=int(self.config_obj.get("api", "timeout", "10")),
                retries=int(self.config_obj.get("api", "retries", "3")),
            )
            balance = client.get_balance()
            usage = client.get_usage()  # 官方未公开时为 None
            post(self._on_success, balance, usage)
        except dsapi.AuthError as e:
            post(self._on_error, i18n.t("err_auth"), str(e))
        except dsapi.InsufficientBalanceError as e:
            post(self._on_error, i18n.t("err_insufficient"), str(e))
        except dsapi.RateLimitError as e:
            post(self._on_error, i18n.t("err_ratelimit"), str(e))
        except dsapi.NetworkError as e:
            post(self._on_error, i18n.t("err_network"), str(e))
        except dsapi.ServerError as e:
            post(self._on_error, i18n.t("err_server"), str(e))
        except dsapi.DeepSeekApiError as e:
            post(self._on_error, i18n.t("err_api"), str(e))
        except Exception as e:
            post(self._on_error, i18n.t("err_unknown"), str(e))

    def _on_success(self, balance, usage):
        # usage：官方用量接口暂未公开，界面以本地余额追踪为准
        self.last_balance = balance
        self._fill_price()
        ok = self._fill_from_balance(balance)
        if not ok:
            self._data["balance"] = "--"
            self.set_status(i18n.t("empty_response"))
        else:
            self.set_status(i18n.t("fmt_refresh_ok")
                           + ("" if balance.get("is_available")
                              else i18n.t("refresh_unavailable")))
        self.refresh_view()
        self._update_mini()

    def _on_error(self, title, msg):
        self.set_status(i18n.t("fmt_err", title=title, msg=msg))
        messagebox.showwarning(title, msg, parent=self)

    # ==================================================================
    # 主题切换
    # ==================================================================
    def _toggle_theme(self):
        self.theme = "dark" if self.theme == "light" else "light"
        self.config_obj.set("ui", "mini_theme", self.theme)
        self.config_obj.save()
        ok = self._apply_window_glass()
        self.view.set_theme(self.theme, glass_on=ok)
        # 数据在换肤后回填（徽章 / 图表配色随主题）
        if self.last_balance is not None:
            self._fill_from_balance(self.last_balance)
        else:
            self._fill_price()
            self._fill_chart(self._history_cache)
        self.refresh_view()
        self._apply_mini_theme()
        self.set_status(i18n.t("fmt_theme",
                               theme=i18n.t("theme_dark" if self.theme == "dark"
                                            else "theme_light")))

    # ==================================================================
    # 语言切换
    # ==================================================================
    def _toggle_lang(self):
        """在 zh-CN / en-US 之间切换，持久化到配置并整窗重绘。"""
        new_lang = "en-US" if i18n.get_lang() == "zh-CN" else "zh-CN"
        i18n.set_lang(new_lang)
        self.config_obj.lang = new_lang
        self.config_obj.save()
        self.title(i18n.t("app_title"))
        self.refresh_view()           # 整窗重绘，标题栏语言按钮同步更新
        if self.mini is not None:
            self._update_mini()
        # 托盘菜单在启动时已按语言生成；运行中切换需重建菜单才即时生效
        if self.tray_ok:
            try:
                self.tray_mgr.rebuild_menu(self)
            except Exception:
                pass
        self.set_status(i18n.t("status_ready"))

    # ==================================================================
    # 迷你置顶窗（钉在桌面）
    # ==================================================================
    def _mini_scale(self):
        try:
            return max(0.75, glass.dpi_scale(self))
        except Exception:
            return self.S

    def _open_mini(self):
        """隐藏主窗，弹出无边框、置顶的迷你卡（统一 Tk 路径）。

        渲染方案（2026-10-25 回退，最稳）：Tk overrideredirect 窗口承载整张
        卡片位图（Label 显示 PIL 渲染图），窗口用 `set_round_region` 裁圆角。
        **不使用**独立阴影窗 / layered 贴图 / 纯 Win32 分层窗 —— 这些在真实
        DWM + 打包 exe 下会触发「隐形 / 闪退 / 打不开」（WS_EX_LAYERED 与 Tk
        窗口过程冲突，或被动态加 layered 后内容清空）。卡片本身已有顶部受光 +
        底部内阴影的层次，无需外部投影。
        """
        if self.mini is not None:
            self.mini.lift()
            return
        pal = MINI_THEMES[self.theme]
        ms = self._mini_scale()
        x = max(0, self.winfo_screenwidth() - int(340 * ms))
        self._mini_pos = (x, 40)
        self._glass_on = False

        self.mini = tk.Toplevel(self)
        self.mini.overrideredirect(True)
        self._mini_region_key = None    # 新窗口 → region 需要重设
        self.mini.wm_attributes("-topmost", True)
        # 窗口底色 = 卡片主色：圆角外（region 裁掉前）即便露出也是同色，无缝
        self.mini.configure(bg=pal["card"])
        self.mini_view = uikit.MiniView(scale=ms)
        self.mini_img = None
        self.mini_img_label = tk.Label(self.mini, bg=pal["card"])
        self.mini_img_label.pack(fill="both", expand=True)

        self.mini_menu = tk.Menu(self, tearoff=0)
        self.mini_menu.add_command(label=i18n.t("mini_restore"), command=self._close_mini)
        self.mini_menu.add_command(label=i18n.t("mini_refresh"), command=self.trigger_refresh)
        self.mini_menu.add_command(label=i18n.t("mini_toggle_theme"), command=self._toggle_theme)
        self.mini_menu.add_separator()
        self.mini_menu.add_command(label=i18n.t("mini_quit"), command=self._quit_app)

        # 事件直接绑在窗口与 Label 上（Label 覆盖整个窗口区域）
        for w in (self.mini, self.mini_img_label):
            w.bind("<ButtonPress-1>", self._mini_start_drag)
            w.bind("<B1-Motion>", self._mini_do_drag)
            w.bind("<Double-1>", lambda e: self.trigger_refresh())
            w.bind("<Button-3>",
                   lambda e: self.mini_menu.tk_popup(e.x_root, e.y_root))

        # ⚠ 先成功渲染迷你窗，再隐藏主窗；任何异常都要把主窗还原，
        # 否则会「主窗没了 + 迷你窗也没出来」= 看起来像打不开。
        try:
            self._update_mini()
        except Exception:
            import traceback
            traceback.print_exc()
            try:
                self._close_mini()
            except Exception:
                pass
            self.deiconify()
            self.set_status(i18n.t("mini_open_fail"))
            return
        self.withdraw()
        # region 保险：窗口真正映射 / 主窗 withdraw 之后 Tk 可能重设一次尺寸，
        # 延迟再裁一次，避免 region 与实际窗口大小错位（四角逐个露底色）。
        try:
            self.mini.after(80, lambda: self._cut_mini_region(force=True))
        except Exception:
            pass
        if not self.last_main_data:
            self.trigger_refresh()

    def _apply_mini_theme(self):
        if self.mini is None or self.mini_view is None:
            return
        # 切换主题只是重设底色 + 重渲染卡片位图（统一 Tk 路径，无 acrylic）
        pal = MINI_THEMES[self.theme]
        self.mini.configure(bg=pal["card"])
        if getattr(self, "mini_img_label", None) is not None:
            self.mini_img_label.configure(bg=pal["card"])
        self._update_mini()

    def _close_mini(self):
        """销毁迷你窗并恢复主窗。网速轮询常驻（Hero 仍在用），仅取消缓动。"""
        if getattr(self, "_mini_tween_id", None):
            try:
                self.mini.after_cancel(self._mini_tween_id)
            except Exception:
                pass
            self._mini_tween_id = None
        if self.mini is not None:
            self.mini.destroy()
            self.mini = None
        self.mini_img = None
        self.mini_img_label = None
        self.mini_view = None
        self._mini_region_key = None
        self.deiconify()
        self.set_status(i18n.t("mini_restored"))

    def _mini_start_drag(self, event):
        # Tk 卡片方案：窗口即卡片（无阴影外扩），锚点直接用窗口坐标
        self._drag_x = event.x_root - self.mini.winfo_x()
        self._drag_y = event.y_root - self.mini.winfo_y()

    def _mini_do_drag(self, event):
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self._move_mini(x, y)

    def _mini_pad_px(self):
        """Tk 卡片方案：窗口即卡片，无阴影外扩，返回 0。"""
        return 0

    def _move_mini(self, x, y):
        """只移动窗口，不重新渲染位图（拖动时每帧调用，必须轻）。"""
        if self.mini is None:
            return
        self._mini_pos = (x, y)
        self.mini.geometry(f"+{x}+{y}")

    def _place_mini(self, x, y, pw, ph):
        """把迷你窗放到 (x,y)。窗口尺寸由位图决定，圆角靠 region 裁切。"""
        self._mini_pos = (x, y)
        if self.mini is None or self.mini_view is None:
            return
        ws = self.mini_view.window_size
        if ws is None:
            return
        # 用最新位图更新 Label（尺寸变化或首次显示都走这里）
        img = self.mini_view._last_img
        if img is not None:
            try:
                from PIL import ImageTk
                self.mini_img = ImageTk.PhotoImage(img)
                self.mini_img_label.configure(image=self.mini_img)
            except Exception:
                pass
        self.mini.geometry(f"{ws[0]}x{ws[1]}+{x}+{y}")
        # ⚠ 设了 geometry 后必须 pump 一次，尺寸才会真正生效；否则窗口停留在
        # 初始 1x1（Label 空白时 autosize），真机上表现为「打不开」（极小无法点）。
        self.mini.update_idletasks()
        # 圆角：裁切窗口四角（卡片圆角已在位图里画好，region 与之一致）
        self._cut_mini_region(ws[0], ws[1])

    def _cut_mini_region(self, pw=None, ph=None, force=False):
        """把迷你窗窗口 region 裁成圆角（四角露出桌面，而不是窗口底色）。

        ⚠ 位图尺寸是**物理像素**（w_css × S，S 已含 DPI 缩放），必须用
        `physical=True` 传入，否则 set_round_region 会再乘一次 DPI →
        region 比窗口大 25% → 被系统按窗口边界截成矩形 → 四角切不掉
        （2026-10-25 用户真机截图抓到的最后一个 bug）。
        圆角半径取自 uikit.MINI_CARD_RADIUS（与位图 mask 同一来源）。
        """
        if self.mini is None or self.mini_view is None:
            return
        try:
            ws = (pw, ph) if pw and ph else self.mini_view.window_size
            if not ws:
                return
            S = getattr(self.mini_view, "S", 1.0)
            R = max(3, int(round(uikit.MINI_CARD_RADIUS * S)))
            key = (ws[0], ws[1], R)
            # 尺寸没变就不重复调 SetWindowRgn（每秒网速刷新都会走到这里，
            # 反复设 region 会触发多余重绘 / 轻微闪烁）
            if key == getattr(self, "_mini_region_key", None) and not force:
                return
            if glass.set_round_region(self.mini, ws[0], ws[1], R,
                                      physical=True):
                self._mini_region_key = key
        except Exception:
            pass

    def _update_mini(self):
        """把最新数据渲染到迷你卡（无迷你窗时跳过）。"""
        if (self.mini is None
                and getattr(self, "mini_win", None) is None) \
                or self.mini_view is None:
            return
        pal = MINI_THEMES[self.theme]
        period, prows = price_mod.get_price_table()
        flash = prows[0]
        pv = flash["peak" if period["peak"] else "offpeak"]["out"]
        d = self.last_main_data or {}
        cur = d.get("cur", "¥")
        off_zhe = 10 / price_mod.PEAK_FACTOR
        badge = (i18n.t("fmt_badge_peak", factor=price_mod.PEAK_FACTOR)
                 if period["peak"] else
                 i18n.t("fmt_badge_offpeak", zhe=off_zhe, pct=off_zhe * 10))
        data = {
            "balance": f"{cur}{d['total']:,.2f}" if d else "--",
            "badge_period": badge,
            "badge_gift": "",
            "cons_today": f"{cur}{self._cons_of('today'):,.2f}",
            "cons_month": f"{cur}{self._cons_of('month'):,.2f}",
            "price": i18n.t("fmt_price_out", v=f"{pv:g}"),
            "net_down": "--", "net_up": "--",
        }
        if self._net_last is not None:
            data["net_down"] = f"↓ {netmon.fmt_speed(self._net_last[0])}"
            data["net_up"] = f"↑ {netmon.fmt_speed(self._net_last[1])}"
        show = {k: self.mini_show_vars[k].get() for k, _l in MINI_CHIPS}
        # 实底：纯卡片位图（无阴影外扩），由 Tk 窗口承载 + region 圆角
        self.mini_view.render(pal, data, show, glass_on=False, shadow=False)
        self._mini_autosize()

    def _cons_of(self, which):
        hist = self._history_cache
        if not hist:
            return 0.0
        now = datetime.now()
        if which == "today":
            t0 = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        else:
            t0 = now.replace(day=1, hour=0, minute=0, second=0,
                             microsecond=0).timestamp()
        return histmod.consumption_between(hist, t0)

    def _on_mini_show_toggle(self):
        """切换即保存配置；迷你窗开着则实时重建。"""
        for k, var in self.mini_show_vars.items():
            self.config_obj.set("ui", f"mini_show_{k}",
                                "true" if var.get() else "false")
        self.config_obj.save()
        self.refresh_view("settings")
        self._update_mini()

    # ==================================================================
    # 迷你窗自适应尺寸
    # ==================================================================
    def _mini_autosize(self, animate=True):
        """按内容重算迷你卡尺寸与位置，再交给 _place_mini 落地（统一 Tk 路径）。

        窗口是 Tk overrideredirect 窗（self.mini），坐标用 Tk winfo；首次显示在
        self._mini_pos（右上角默认）。窗口尺寸由位图决定（离散），无需缓动，
        直接 _place_mini 一步到位。
        """
        if self.mini is None or self.mini_view is None:
            return
        ms = self.mini_view.S
        w = max(180, int(self.mini_view.w_css))
        h = max(96, int(self.mini_view.h_css))
        pw, ph = int(w * ms), int(h * ms)

        x, y = self.mini.winfo_x(), self.mini.winfo_y()
        # ⚠ 主窗 withdraw 之后 winfo_x/y 可能返回 (0,0)。若直接用会把迷你卡
        # 瞬间搬到屏幕左上角，用记录值兜底。
        if not x and not y and getattr(self, "_mini_pos", None):
            x, y = self._mini_pos
        hwnd = self.mini.winfo_id()

        # 按真实显示器边界 clamp（多屏：winfo_screenwidth 只返回主屏，不够）
        rect = netmon.get_window_monitor_workarea(hwnd)
        if rect:
            ml, mt, mr, mb = rect
            if x + pw > mr:
                x = max(ml, mr - pw)
            if y + ph > mb:
                y = max(mt, mb - ph)

        self._place_mini(x, y, pw, ph)

    def _mini_tween(self, x, y, tw, th, step=0, max_steps=12, step_ms=16):
        """指数缓动逼近目标尺寸（历史遗留，当前 Tk 卡片路径未使用）。"""
        if self.mini is None:
            return
        cw, ch = self.mini.winfo_width(), self.mini.winfo_height()
        nw = cw + (tw - cw) * 0.35
        nh = ch + (th - ch) * 0.35
        nw_r, nh_r = round(nw), round(nh)
        self._place_mini(x, y, nw_r, nh_r)
        if step < max_steps and (abs(nw_r - tw) > 1 or abs(nh_r - th) > 1):
            self._mini_tween_id = self.mini.after(
                step_ms,
                lambda: self._mini_tween(x, y, tw, th, step + 1,
                                         max_steps, step_ms))
        else:
            self._place_mini(x, y, tw, th)
            self._mini_tween_id = None

    # ==================================================================
    # 网速实时监控（Hero + 迷你卡共用同一采样器）
    # ==================================================================
    def _start_net_monitor(self):
        if self._net_timer is not None:
            return
        self._net_last = None
        self._net_tick()

    def _net_tick(self):
        try:
            res = self.net_sampler.sample()
            if res is not None:
                self._net_last = res
                dt, ut = netmon.fmt_speed(res[0]), netmon.fmt_speed(res[1])
                self._data["net_down"] = f"{dt}"
                self._data["net_up"] = f"{ut}"
                self.refresh_view("hero")
                if self.mini is not None:
                    self._update_mini()
            else:
                self._data["net_down"] = "--"
                self._data["net_up"] = "--"
                self.refresh_view("hero")
        except Exception:
            self._data["net_down"] = i18n.t("net_unavailable")
            self._data["net_up"] = i18n.t("net_unavailable")
            self.refresh_view("hero")
        self._net_timer = self.after(NET_REFRESH_MS, self._net_tick)

    # ==================================================================
    # 自动刷新
    # ==================================================================
    def auto_on(self):
        return self.config_obj.get("app", "auto_refresh") == "true"

    def _schedule_auto(self):
        if self._auto_timer:
            self.after_cancel(self._auto_timer)
        self._auto_timer = self.after(max(30, self._interval()) * 1000,
                                      self._auto_tick)

    def _auto_tick(self):
        if self.auto_on() and self.config_obj.has_key():
            self.trigger_refresh()
        if self.auto_on():
            self._schedule_auto()

    # ==================================================================
    # 托盘 / 退出 / 自启 / 导出
    # ==================================================================
    def _on_close(self):
        """点 X：有托盘则最小化到托盘；无托盘（headless）则直接退出。"""
        self._commit_key()
        if self.tray_ok:
            self.withdraw()
            self.tray_mgr.notify(i18n.t("tray_notify_title"),
                                 i18n.t("tray_notify_msg"))
        else:
            self._quit_app()

    def _commit_key(self):
        try:
            self.on_key_commit(self.view.key_var.get())
        except Exception:
            pass

    def _restore_from_tray(self):
        if self.mini is not None:
            self._close_mini()
        self.deiconify()
        self.lift()
        self.set_status(i18n.t("tray_restored"))

    def _quit_app(self):
        self._commit_key()
        for attr in ("_net_timer", "_auto_timer"):
            t = getattr(self, attr, None)
            if t:
                try:
                    self.after_cancel(t)
                except Exception:
                    pass
                setattr(self, attr, None)
        self.tray_mgr.stop()
        self.destroy()

    # ---- 开机自启（HKCU\Run）----
    def _is_autostart_enabled(self) -> bool:
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run")
            try:
                winreg.QueryValueEx(key, "DeepSeekBalanceViewer")
                return True
            except FileNotFoundError:
                return False
        except Exception:
            return False

    def _set_autostart(self, enable: bool) -> bool:
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE)
            if enable:
                if getattr(sys, "frozen", False):
                    target = f'"{sys.executable}" --mini'
                else:
                    target = (f'"{sys.executable}" '
                              f'"{os.path.abspath(sys.argv[0])}" --mini')
                winreg.SetValueEx(key, "DeepSeekBalanceViewer", 0,
                                  winreg.REG_SZ, target)
            else:
                try:
                    winreg.DeleteValue(key, "DeepSeekBalanceViewer")
                except FileNotFoundError:
                    pass
            return True
        except Exception as e:
            print(f"[autostart] 失败：{e}")
            return False

    # ---- 导出 CSV ----
    def export_csv(self):
        import csv
        hist = histmod.load_history()
        if not hist:
            messagebox.showwarning(i18n.t("csv_no_data"),
                                   i18n.t("csv_no_data_msg"), parent=self)
            return
        first = hist[0]["balance"]
        path = f"balance_history_{datetime.now():%Y%m%d}.csv"
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow([i18n.t("csv_header_time"), i18n.t("csv_header_currency"),
                            i18n.t("csv_header_balance"), i18n.t("csv_header_used")])
                for r in hist:
                    w.writerow([r["time"], r["currency"],
                                f"{r['balance']:.2f}",
                                f"{first - r['balance']:.2f}"])
            messagebox.showinfo(i18n.t("csv_exported"),
                                i18n.t("csv_exported_msg", path=os.path.abspath(path)),
                                parent=self)
            self.set_status(i18n.t("fmt_csv_exported", path=path))
        except Exception as e:
            messagebox.showerror(i18n.t("csv_fail"), str(e), parent=self)

    # ---- 截图当前可见窗口 ----
    def export_screenshot(self):
        try:
            from PIL import ImageGrab
            if self.mini is not None and self.mini.winfo_viewable():
                target = self.mini
            elif self.winfo_viewable():
                target = self
            else:
                messagebox.showwarning(i18n.t("shot_no_window"),
                                       i18n.t("shot_no_window_msg"), parent=self)
                return
            s = self.S
            x, y = target.winfo_rootx(), target.winfo_rooty()
            w, h = target.winfo_width(), target.winfo_height()
            img = ImageGrab.grab((x, y, x + w, y + h))
            path = f"balance_snapshot_{datetime.now():%Y%m%d_%H%M%S}.png"
            img.save(path)
            messagebox.showinfo(i18n.t("shot_done"),
                                i18n.t("shot_done_msg", path=os.path.abspath(path)),
                                parent=self)
            self.set_status(i18n.t("fmt_shot_saved", path=path))
        except Exception as e:
            messagebox.showerror(i18n.t("shot_fail"), str(e), parent=self)


if __name__ == "__main__":
    App().mainloop()
