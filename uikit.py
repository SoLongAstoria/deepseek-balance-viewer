# -*- coding: utf-8 -*-
"""界面绘制层 —— 把 `_mockup.html` 设计稿逐 token 复刻到 tkinter Canvas。

## 为什么要整窗自绘

ttk / tk 原生控件做不到设计稿里的这些东西：
  - 圆角卡片（ttk.Frame 恒为直角）
  - 卡片顶部受光渐变（tk 无渐变、无 alpha）
  - 价格表「整列高亮」+「整行置灰」（ttk 只能整卡同色）
  - 圆角 pill 徽章 / chips 胶囊 / iOS 风格 switch
  - 精确到 0.5px 的行高与 padding

之前用 ttk 拼装的版本与效果图差距明显（用户原话「跟效果图差别不是一点点大」），
所以这里改用**单个 Canvas 承载全部视觉**：PIL 只负责预渲染渐变位图，
其余全部是 Canvas 原语。控件样式 100% 由本模块决定，不再受 ttk 主题摆布。

## 尺度换算（关键）

设计稿单位是 CSS px。窗口以 PROCESS_PER_MONITOR_DPI_AWARE 运行，
Canvas 坐标 = 物理像素。因此：

  - 几何：`S = 缩放比`，所有设计稿 px × S
  - 字体：`tkfont.Font(size=-round(px*S))` —— tk 的**负数 size 是像素**，
    所以字体物理高度同样 = px × S，与几何同比例，永不糊、不跑偏

## 交互模型

Canvas 没有控件树，所以：
  - 绘制时把可点击区域登记到 `_regions`（矩形 + key + cursor + 所属 block）
  - `<Motion>` 命中测试 → 切换 cursor + 只重绘受影响 block（局部，不闪）
  - `<Button-1>` 命中 → 回调 `on_click(key)`
  - 需要文本输入的（API Key / 刷新间隔）用 `place` 放真 Entry，
    它不属于 Canvas items，`delete("all")` 不会误删
"""

import tkinter as tk
from tkinter import font as tkfont

import glass

# 中英文统一字体：雅黑 UI 的中文比雅黑更紧凑，数字宽度适中
FONT_FAMILY = "Microsoft YaHei UI"
FONT_FALLBACK = "Microsoft YaHei"

APP_VERSION = "1.4.0"


# ============================================================================
# 主题 token —— 逐项对照 _mockup.html 的 CSS 变量，注释里保留原始 rgba
# ============================================================================
# 主窗（.win-dark / .win-light）。rgba 值已按「叠在窗底上」换算成实色，
# 因为 tk 不支持 alpha；换算公式见 _mix()。
MAIN_THEMES = {
    "dark": dict(
        win_bg="#101420",        # rgba(16,20,30,.82)  窗底（acrylic 失败时的降级实底）
        tint=0xD1201410,         # 同上的 acrylic 染色（A,B,G,R）
        fg="#E9EDF5",            # .win color
        fg2="#9AA6BC",           # --wfg2
        fg3="#75809A",           # --wfg3
        wline="#232732",         # rgba(255,255,255,.08) titlebar / 状态栏分隔线
        card="#1B1F2A",          # rgba(255,255,255,.045) 卡片底
        cardline="#2B2F39",      # rgba(255,255,255,.07)  卡片描边 / 分隔线
        hl="#FFFFFF", hl_a=0.09,  # --whl rgba(255,255,255,.09) Hero 顶部受光
        accent="#2E8BFF",        # 强调蓝（当前列 / chips on / more 可点）
        down="#4D9FFF", up="#F08C00",
        idle="#30D158", peak="#FF453A",
        switch_on="#1FA84A",
    ),
    "light": dict(
        win_bg="#FAFAFC",
        tint=0xDBFCFAFA,
        fg="#161C27",
        fg2="#46505F",
        fg3="#667080",
        wline="#E3E4E6",         # rgba(20,26,36,.10)
        card="#F2F2F4",          # rgba(20,26,36,.035)
        cardline="#DEDFE1",      # rgba(20,26,36,.09)
        hl="#FFFFFF", hl_a=0.90,  # --whl rgba(255,255,255,.9)（浅色玻璃强受光）
        accent="#0057B8",
        down="#0062D6", up="#C75B00",
        idle="#1E7A38", peak="#B3231A",
        switch_on="#1FA84A",
    ),
}

# 设计稿里不随明暗切换的固定色（.fill.b / .fill.g、状态 pill、chips on 等）
FIXED = dict(
    bar_grant=("#1FA84A", "#55D983"),    # .fill.g 绿色渐变（赠金）
    bar_topup=("#2E8BFF", "#6FB4FF"),    # .fill.b 蓝色渐变（充值）
    st_on_bg=("#1FA84A", "#1E7A38"),     # .st.on  (dark, light)
    st_on_fg=("#1FA84A", "#1B6E33"),
    st_peak_bg=("#FF453A", "#B3231A"),   # .st.peak
    st_peak_fg=("#FF6961", "#B3231A"),
)

# 迷你卡（.glass）。mask 是 acrylic 的玻璃掩膜色：纯黑像素会被 DWM
# 替换成「背后桌面实时模糊 + 染色」，所以卡面必须是纯黑，任何装饰都不能
# 大面积覆盖它（见 README「玻璃掩膜的硬限制」）。
MINI_THEMES = {
    "light": dict(
        mask="#000000", card="#F6F7F9", tint=0x40F0F0F0,
        rim="#B9C0CC", line="#D7DAE0",
        fg="#141A23", fg2="#46505F", fg3="#6E7683",
        down="#0062D6", up="#C75B00", idle="#1E7A38", peak="#B3231A",
        badge_period=("#DAE4F2", "#0057B8"),
        badge_gift=("#DBE5E2", "#1B6E33"),
        hl="#FFFFFF",
        # --- 实底「模拟玻璃」用的层次 token（Canvas 叠不出 alpha，只能 PIL 合成）---
        grad_top="#FFFFFF",     # 卡面竖向渐变：顶部亮
        grad_bot="#EAECF0",     # 底部略压暗 → 有厚度
        rim_in="#FFFFFF",       # 内圈高光描边
        rim_in_a=0.90,          # 浅色卡内高光强（玻璃受光）
        shade_a=0.05,           # 底部内阴影浓度
        gloss_ratio=0.34,       # 顶部高光带占卡高比例
        topline_a=0.85,         # 顶边 1px 反光线
        shadow_a=0.20,         # 外扩柔和阴影浓度（浅色桌面要淡）
    ),
    "dark": dict(
        mask="#000000", card="#1C1D22", tint=0x292929,
        rim="#5A606B", line="#33363D",
        fg="#F2F5FA", fg2="#BFC8D8", fg3="#97A1B4",
        down="#4D9FFF", up="#FF9F0A", idle="#30D158", peak="#FF453A",
        badge_period=("#213047", "#6FB4FF"),
        badge_gift=("#1C352D", "#55D983"),
        hl="#3B3F49",
        grad_top="#272931",
        grad_bot="#17181C",
        rim_in="#FFFFFF",
        rim_in_a=0.12,
        shade_a=0.12,
        gloss_ratio=0.38,
        topline_a=0.22,
        shadow_a=0.42,
    ),
}


def _mix(fg, bg, alpha):
    """把半透明前景 fg 按 alpha 叠到底色 bg 上，返回实色 hex。

    tk 没有 alpha 通道，设计稿里所有 rgba() 叠层都用这个函数换算成实色。
    """
    f = tuple(int(fg[i:i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(bg[i:i + 2], 16) for i in (1, 3, 5))
    c = tuple(round(f[i] * alpha + b[i] * (1 - alpha)) for i in range(3))
    return "#%02X%02X%02X" % c


def compute_scale(screen_w, screen_h, dpi_scale=1.0, want_w=560, want_h=676):
    """计算布局缩放比：优先用 DPI 缩放，屏幕放不下时等比缩小整体（防截断）。"""
    s = max(1.0, float(dpi_scale or 1.0))
    if want_h * s > screen_h - 80:
        s = max(0.75, (screen_h - 80) / want_h)
    if want_w * s > screen_w - 60:
        s = max(0.75, min(s, (screen_w - 60) / want_w))
    return s


# ============================================================================
# Painter —— Canvas 绘制原语
# ============================================================================
class Painter:
    """在任意 Canvas 上作画的原语集合（圆角 / 渐变 / pill / switch …）。

    所有方法接收**设计稿 CSS px** 坐标，内部统一 × S 转物理像素。
    """

    def __init__(self, canvas, scale=1.0):
        self.c = canvas
        self.S = scale
        self._fonts = {}
        self._imgs = {}          # 渐变 / 卡片背景位图缓存

    # ---------- 尺度 ----------
    def s(self, v):
        return v * self.S

    def px(self, v):
        return int(round(v * self.S))

    # ---------- 字体 ----------
    def font(self, px, bold=False):
        """返回 tkfont.Font，size 用负数 = 像素，物理高度正好 px×S。"""
        size = max(6, int(round(px * self.S)))
        key = (size, bool(bold))
        f = self._fonts.get(key)
        if f is None:
            try:
                f = tkfont.Font(root=self.c, family=FONT_FAMILY, size=-size,
                                weight="bold" if bold else "normal")
            except Exception:
                f = tkfont.Font(root=self.c, family=FONT_FALLBACK, size=-size,
                                weight="bold" if bold else "normal")
            self._fonts[key] = f
        return f

    def tw(self, txt, px, bold=False):
        """文本宽度（物理像素）。"""
        return self.font(px, bold).measure(txt)

    def th(self, px, bold=False):
        """行高（物理像素）。"""
        return self.font(px, bold).metrics("linespace")

    # ---------- 文本 ----------
    def text(self, x, y, txt, px, color, bold=False, anchor="w", tags=()):
        """画文字。anchor 默认 "w" = 左端 + 垂直居中于 y（行距由调用方完全掌控）。"""
        return self.c.create_text(
            self.s(x), self.s(y), text=txt, fill=color,
            font=self.font(px, bold), anchor=anchor, tags=tags)

    def text_r(self, x, y, txt, px, color, bold=False, tags=()):
        return self.text(x, y, txt, px, color, bold, anchor="e", tags=tags)

    def text_c(self, x, y, txt, px, color, bold=False, tags=()):
        return self.text(x, y, txt, px, color, bold, anchor="center", tags=tags)

    # ---------- 圆角矩形 ----------
    def _rr_fill(self, x0, y0, x1, y1, r, color, tags):
        """实心圆角矩形：4 个 pieslice + 2 个矩形（tk 无原生圆角矩形）。"""
        if x1 - x0 < 1 or y1 - y0 < 1 or not color:
            return []
        r = max(0.0, min(r, (x1 - x0) / 2.0, (y1 - y0) / 2.0))
        c = self.c
        if r < 0.6:
            return [c.create_rectangle(x0, y0, x1, y1, fill=color,
                                       outline=color, tags=tags)]
        d = 2 * r
        kw = dict(fill=color, outline=color, style="pieslice", tags=tags)
        ids = [
            c.create_arc(x0, y0, x0 + d, y0 + d, start=90, extent=90, **kw),
            c.create_arc(x1 - d, y0, x1, y0 + d, start=0, extent=90, **kw),
            c.create_arc(x1 - d, y1 - d, x1, y1, start=270, extent=90, **kw),
            c.create_arc(x0, y1 - d, x0 + d, y1, start=180, extent=90, **kw),
            c.create_rectangle(x0 + r, y0, x1 - r, y1, fill=color,
                               outline=color, tags=tags),
            c.create_rectangle(x0, y0 + r, x1, y1 - r, fill=color,
                               outline=color, tags=tags),
        ]
        return ids

    def rounded(self, x0, y0, x1, y1, r, fill=None, outline=None, width=1, tags=()):
        """圆角矩形（设计稿 px 入参）。描边用「外圈涂描边色 + 内圈涂填充色」实现。"""
        X0, Y0, X1, Y1 = self.s(x0), self.s(y0), self.s(x1), self.s(y1)
        R, W = self.s(r), max(1.0, self.s(width))
        ids = []
        if outline:
            ids += self._rr_fill(X0, Y0, X1, Y1, R, outline, tags)
            if fill:
                ids += self._rr_fill(X0 + W, Y0 + W, X1 - W, Y1 - W,
                                     max(0.0, R - W), fill, tags)
        elif fill:
            ids += self._rr_fill(X0, Y0, X1, Y1, R, fill, tags)
        return ids

    def hline(self, x0, x1, y, color, tags=(), width=1):
        return self.c.create_line(self.s(x0), self.s(y), self.s(x1), self.s(y),
                                  fill=color, width=max(1, self.px(width)),
                                  tags=tags)

    def vline(self, x, y0, y1, color, tags=()):
        return self.c.create_line(self.s(x), self.s(y0), self.s(x), self.s(y1),
                                  fill=color, width=1, tags=tags)

    # ---------- Pill 徽章 / chips ----------
    def pill(self, x, yc, txt, px, fg, bg, pad_x=7, pad_y=2, tags=(),
             bold=True, outline=None):
        """设计稿 .badge / chips：全圆角胶囊，返回占用宽度（设计稿 px）。"""
        tw = self.tw(txt, px, bold) / self.S
        th = self.th(px, bold) / self.S
        h = th + pad_y * 2
        w = tw + pad_x * 2
        self.rounded(x, yc - h / 2, x + w, yc + h / 2, h / 2,
                     fill=bg, outline=outline, tags=tags)
        self.text(x + pad_x, yc, txt, px, fg, bold, anchor="w", tags=tags)
        return w

    # ---------- Switch（iOS 风格）----------
    def switch(self, x, yc, on, pal, tags=()):
        """设计稿 .switch：26×15 胶囊 + 11px 圆钮。返回占用宽度。"""
        w, h = 26, 15
        bg = pal["switch_on"] if on else pal["cardline"]
        self.rounded(x, yc - h / 2, x + w, yc + h / 2, h / 2, fill=bg, tags=tags)
        kx = x + w - 2 - 11 if on else x + 2
        self.c.create_oval(self.s(kx), self.s(yc - 5.5),
                           self.s(kx + 11), self.s(yc + 5.5),
                           fill="#FFFFFF", outline="", tags=tags)
        return w

    # ---------- 水平渐变条（比例条 fill）----------
    def hgrad(self, x, y, w, h, c1, c2, tags=()):
        """水平线性渐变的小色条（比例条）。PIL 渲染，尺寸小、开销可忽略。"""
        pw, ph = max(1, self.px(w)), max(1, self.px(h))
        try:
            from PIL import Image, ImageTk
        except Exception:
            return self.rounded(x, y, x + w, y + h, h / 2, fill=c2, tags=tags)
        key = ("hg", pw, ph, c1, c2)
        img = self._imgs.get(key)
        if img is None:
            base = Image.new("RGB", (pw, 1))
            a = tuple(int(c1[i:i + 2], 16) for i in (1, 3, 5))
            b = tuple(int(c2[i:i + 2], 16) for i in (1, 3, 5))
            for i in range(pw):
                t = i / max(1, pw - 1)
                base.putpixel((i, 0), tuple(
                    round(a[k] + (b[k] - a[k]) * t) for k in range(3)))
            img = ImageTk.PhotoImage(base.resize((pw, ph)))
            if len(self._imgs) > 160:
                self._imgs.clear()
            self._imgs[key] = img
        return self.c.create_image(self.s(x), self.s(y), image=img,
                                   anchor="nw", tags=tags)

    # ---------- 卡片背景（圆角 + 顶部受光 + 1px 描边，PIL 一次渲染）----------
    def card_bg(self, x, y, w, h, pal, r=12, glow_h=0, tags=()):
        """把卡片底 + 受光渐变 + 描边渲染成一张位图贴上。

        tk 无法在 Canvas 上叠半透明，所以这三层在 PIL 里合成好再贴，
        高 DPI 下按物理像素渲染，不糊。
        """
        pw, ph = max(1, self.px(w)), max(1, self.px(h))
        key = ("card", pw, ph, pal["card"], pal["cardline"], pal["hl"],
               pal["hl_a"] if glow_h else 0, glow_h, r)
        img = self._imgs.get(key)
        if img is None:
            try:
                from PIL import Image, ImageDraw, ImageTk, ImageChops
            except Exception:
                self.rounded(x, y, x + w, y + h, r, fill=pal["card"],
                             outline=pal["cardline"], tags=tags)
                return None
            rad = self.px(r)
            base = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
            d = ImageDraw.Draw(base)
            d.rounded_rectangle([0, 0, pw - 1, ph - 1], radius=rad,
                                fill=pal["card"])
            if glow_h > 0:
                gh = min(ph, self.px(glow_h))
                # 圆角形状 mask：高光不能溢出卡片圆角
                mask = Image.new("L", (pw, ph), 0)
                ImageDraw.Draw(mask).rounded_rectangle(
                    [0, 0, pw - 1, ph - 1], radius=rad, fill=255)
                # 竖向 alpha：顶部 hl_a → 底部 0
                ramp = Image.linear_gradient("L").resize((pw, gh))
                top_a = int(round(255 * pal["hl_a"]))
                ramp = ramp.point(lambda v, a=top_a: int(a * (255 - v) / 255))
                ramp = ImageChops.multiply(ramp, mask.crop((0, 0, pw, gh)))
                glow = Image.new("RGBA", (pw, gh), pal["hl"])
                glow.putalpha(ramp)
                base.alpha_composite(glow, (0, 0))
            d.rounded_rectangle([0, 0, pw - 1, ph - 1], radius=rad,
                                outline=pal["cardline"], width=max(1, self.px(1)))
            img = ImageTk.PhotoImage(base)
            if len(self._imgs) > 60:
                self._imgs.clear()
            self._imgs[key] = img
        return self.c.create_image(self.s(x), self.s(y), image=img,
                                   anchor="nw", tags=tags)

    # ---------- 面积渐变（走势图）----------
    def area_gradient(self, x, y, w, h, pts, color, top_alpha, tags=()):
        """折线下方填充「竖向由深到透明」的面积（设计稿 svg linearGradient）。"""
        if len(pts) < 2:
            return None
        try:
            from PIL import Image, ImageDraw, ImageTk
        except Exception:
            return None
        pw, ph = max(1, self.px(w)), max(1, self.px(h))
        try:
            mask = Image.new("L", (pw, ph), 0)
            poly = [(self.s(px_), self.s(py_)) for px_, py_ in pts]
            poly += [(self.s(pts[-1][0]), ph), (self.s(pts[0][0]), ph)]
            ImageDraw.Draw(mask).polygon(poly, fill=255)
            ramp = Image.linear_gradient("L").resize((pw, ph))
            a0 = int(round(255 * top_alpha))
            ramp = ramp.point(lambda v, a=a0: int(a * (255 - v) / 255))
            from PIL import ImageChops
            ramp = ImageChops.multiply(ramp, mask)
            img = Image.new("RGBA", (pw, ph), color)
            img.putalpha(ramp)
            ph_img = ImageTk.PhotoImage(img)
        except Exception:
            return None
        return self.c.create_image(self.s(x), self.s(y), image=ph_img,
                                   anchor="nw", tags=tags)


# ============================================================================
# MainView —— 主程序窗口（对照设计稿 .win）
# ============================================================================
class MainView(tk.Canvas):
    """主窗全部视觉。布局常量一律是设计稿 CSS px，运行时 × S。"""

    # ---- 设计稿尺寸（单位 CSS px，勿随意改，改了就和效果图不一致）----
    WIN_W = 560
    WIN_H = 676
    TB_H = 35                       # titlebar: pad 9+9 + 行高 16 + 1px 底边
    PAD_L = PAD_R = 14              # .win .body padding
    PAD_T, PAD_B = 12, 14
    GAP = 10                        # .win .body gap
    CARD_R = 12                     # .hero / .card border-radius
    HERO_H = 141
    PRICE_H = 126
    CHART_H = 159
    SET_H = 137
    STATUS_H = 22

    # 交互 key（供 App 分发）
    K_MINI, K_THEME, K_REFRESH, K_SHOT = "mini", "theme", "refresh", "shot"
    K_PRICE_INFO, K_CSV, K_ABOUT = "price_info", "csv", "about"
    K_AUTOSTART, K_INTERVAL = "autostart", "interval"

    def __init__(self, master, app, scale=1.0, glass_on=False):
        self.S = scale
        # ⚠ 底色必须跟 glass_on / 主题走：曾硬编码 "#000000"，导致非玻璃模式下
        # 标题栏、卡片间隙、状态栏全部是纯黑，深色文字直接"消失"（真机截图抓到）。
        super().__init__(master, width=self.px_(self.WIN_W), height=self.px_(self.WIN_H),
                         highlightthickness=0, bd=0,
                         bg="#000000" if glass_on else MAIN_THEMES[app.theme]["win_bg"])
        self.app = app
        self.p = Painter(self, scale)
        self.theme = app.theme
        self.pal = MAIN_THEMES[self.theme]
        self.glass_on = glass_on
        self.state = {}
        self._regions = []
        self._hover = None
        self._entries = {}          # key -> tk.Entry（place 上去的输入框）
        self._editing = None
        self._key_dirty = False     # 用户是否真的编辑过 API Key 输入框
        self.key_var = tk.StringVar(value="")
        self.bind("<Motion>", self._on_motion)
        self.bind("<Button-1>", self._on_click)
        self.bind("<Leave>", lambda e: self._set_hover(None))

    # ---------- 基础 ----------
    def px_(self, v):
        return int(round(v * self.S))

    def s_(self, v):
        return v * self.S

    def _pal(self):
        return MAIN_THEMES[self.theme]

    def __getattr__(self, name):
        """未定义的绘制方法转发给 Painter（rounded / pill / text / hline …）。

        `__getattr__` 只在常规属性查找失败时触发，所以 tk.Canvas 自身的方法
        不受影响；p 尚未建立时用 __dict__ 直取，避免递归。
        """
        p = self.__dict__.get("p")
        if p is not None and hasattr(p, name):
            return getattr(p, name)
        raise AttributeError(
            f"{type(self).__name__!r} object has no attribute {name!r}")

    @property
    def y_hero(self):
        return self.TB_H + self.PAD_T

    @property
    def y_price(self):
        return self.y_hero + self.HERO_H + self.GAP

    @property
    def y_chart(self):
        return self.y_price + self.PRICE_H + self.GAP

    @property
    def y_set(self):
        return self.y_chart + self.CHART_H + self.GAP

    @property
    def y_status(self):
        return self.y_set + self.SET_H + self.PAD_B

    # ---------- 主题 / 数据 ----------
    def set_theme(self, theme, glass_on=None):
        self.theme = theme
        self.pal = MAIN_THEMES[theme]
        if glass_on is not None:
            self.glass_on = glass_on
        self.p._imgs.clear()
        self.configure(bg="#000000" if self.glass_on else self.pal["win_bg"])
        self.render_all()

    def update_state(self, **kw):
        """更新数据；默认整窗重绘（调用方也可指定 blocks 做局部重绘）。"""
        blocks = kw.pop("_blocks", None)
        self.state.update(kw)
        if blocks:
            self.redraw(*blocks)
        else:
            self.render_all()

    def render_all(self):
        self._regions.clear()
        self._hover = None
        self.delete("all")
        # 窗底显式铺满：玻璃模式必须纯黑（acrylic 掩膜），否则用主题窗底。
        # 不依赖 Canvas 原生 bg —— 任何 DPI / 重绘时机下的底色错位都会让
        # 标题栏和状态栏的文字失去对比度。
        base = "#000000" if self.glass_on else self.pal["win_bg"]
        self.configure(bg=base)
        self.create_rectangle(0, 0, self.px_(self.WIN_W), self.px_(self.WIN_H),
                              fill=base, outline="", tags=("winbg",))
        self._draw_title()
        self._draw_hero()
        self._draw_price()
        self._draw_chart()
        self._draw_settings()
        self._draw_status()
        self._place_entries()

    def redraw(self, *blocks):
        """局部重绘指定板块（网速每秒钟只动 hero，避免整窗闪）。"""
        for b in blocks:
            self.delete(b)
            # 该板块的交互区域重算（避免重复登记）
            self._regions = [r for r in self._regions if r[3] != b]
            getattr(self, f"_draw_{b}")()
        self._sync_entries()

    # ---------- 交互区域 ----------
    def _reg(self, x0, y0, x1, y1, key, block, cursor="hand2"):
        self._regions.append((self.s_(x0), self.s_(y0), self.s_(x1),
                              self.s_(y1), key, cursor, block))

    def _hit(self, x, y):
        for r in self._regions:
            if r[0] <= x <= r[2] and r[1] <= y <= r[3]:
                return r
        return None

    def _set_hover(self, key):
        if key == self._hover:
            return
        old = self._hover
        self._hover = key
        blocks = set()
        for r in self._regions:
            if r[4] in (old, key):
                blocks.add(r[6])
        for b in blocks:
            self.redraw(b)
        self.configure(cursor="hand2" if key else "")

    def _on_motion(self, e):
        r = self._hit(e.x, e.y)
        self._set_hover(r[4] if r else None)

    def _on_click(self, e):
        r = self._hit(e.x, e.y)
        if r:
            self.app.on_view_click(r[4])
        else:
            self.focus_set()

    # ---------- 文本输入控件（place 上去，不参与 Canvas items）----------
    def _place_entries(self):
        self._sync_entries()

    def _sync_entries(self):
        st = self.state
        pal = self.pal
        # --- API Key ---
        x0, y0, w, h = self._key_box()
        ent = self._entries.get("key")
        if ent is None:
            ent = tk.Entry(self, bd=0, relief="flat",
                           textvariable=self.key_var,
                           highlightthickness=0, font=self.p.font(10),
                           bg=pal["card"], fg=pal["fg"],
                           insertbackground=pal["fg"],
                           # ⚠ 默认遮罩：截图 / 录屏 / 旁人围观时不会泄露 Key
                           show="\u2022")
            # 首次创建就带上真实值：若此时 state 还没填好，key_var 会是空，
            # 一旦拿到焦点再失焦，<FocusOut> 就会把空值写回配置（丢 Key 的根因）。
            self.key_var.set(st.get("api_key", ""))
            self._key_dirty = False
            ent.bind("<Key>", lambda ev: self._mark_key_dirty())
            ent.bind("<FocusOut>",
                     lambda ev: (self._mask_key(True), self._commit_key()))
            ent.bind("<Return>", lambda ev: (self._commit_key(), self.focus_set()))
            ent.bind("<FocusIn>", lambda ev: self._on_entry_focus())
            self._entries["key"] = ent
        else:
            # 用户没编辑过输入框时无条件回灌真实值（**即使它当前有焦点**）。
            # 只按"焦点不在就回灌"是错的：焦点在且用户没动过，显示的仍是旧值，
            # 失焦提交时就会把旧值/空值写回，覆盖用户存的 Key。
            if not self._key_dirty:
                want = st.get("api_key", "")
                if self.key_var.get() != want:
                    self.key_var.set(want)
        ent.configure(bg=pal["card"], fg=pal["fg"], insertbackground=pal["fg"],
                      font=self.p.font(10))
        ent.place(x=self.px_(x0), y=self.px_(y0), width=self.px_(w), height=self.px_(h))

    def _mark_key_dirty(self):
        """用户真的在输入框里敲了键 —— 只有这时才允许提交。"""
        self._key_dirty = True

    def _commit_key(self):
        """提交 API Key（失焦 / 回车）。

        ⚠ 必须用 dirty 门槛：`<FocusOut>` 在窗口失活、脚本退出、点其它控件时
        都会触发，无条件提交会把"显示出来的旧值/空值"写回配置，
        导致用户存的 Key 被静默覆盖（2026-10-25 真实发生过）。
        """
        if not getattr(self, "_key_dirty", False):
            return
        self._key_dirty = False
        self.app.on_key_commit(self.key_var.get())

    def _on_entry_focus(self):
        """API Key 输入框获得焦点 → 描边变强调色，并临时显示明文便于核对粘贴。

        失焦后立刻回到遮罩（`_mask_key(True)`）：默认状态永远是 `••••`，
        所以截图 / 录屏 / 演示时不会把 Key 露在画面里。
        """
        self._mask_key(False)
        self.redraw("settings")

    def _mask_key(self, masked=True):
        """切换 API Key 输入框的遮罩显示（只影响显示，`key_var` 的值不变）。"""
        ent = self._entries.get("key")
        if ent is None:
            return
        try:
            ent.configure(show="\u2022" if masked else "")
        except Exception:
            pass

    def _key_box(self):
        """API Key 输入框在 Canvas 上的位置（与 _draw_settings 保持一致）。"""
        st, sp = 26, 76
        return sp, self.y_set + 32 + 2, (534 - sp), 18

    # ==================================================================
    # 绘制：titlebar
    # ==================================================================
    def _draw_title(self):
        pal = self.pal
        t = ("title",)
        self.hline(0, self.WIN_W, self.TB_H - 0.5, pal["wline"], tags=t)
        self.text(self.PAD_L, self.TB_H / 2, "DeepSeek 余额 / 用量查看器",
                  12, pal["fg"], bold=True, tags=t)
        # 右侧两个 pill 按钮（设计稿 .ops i）
        ops = ((self.K_MINI, "迷你窗", "开启桌面悬浮迷你卡"),
               (self.K_THEME, "切换浅色" if self.theme == "dark" else "切换深色",
                "切换深色" if self.theme == "dark" else "切换浅色"))
        x = self.WIN_W - self.PAD_R
        for key, label, _tip in reversed(ops):
            hovered = self._hover == key
            px_h = 10
            tw = self.p.tw(label, px_h) / self.S
            w = tw + 16
            h = 20
            x0 = x - w
            self.rounded(x0, self.TB_H / 2 - h / 2, x, self.TB_H / 2 + h / 2, 6,
                         fill=pal["card"] if not hovered else self._hl(pal["card"]),
                         outline=pal["cardline"], tags=t)
            self.text_c(x0 + w / 2, self.TB_H / 2, label, px_h,
                        pal["fg2"] if not hovered else pal["fg"], tags=t)
            self._reg(x0, self.TB_H / 2 - h / 2, x, self.TB_H / 2 + h / 2, key, "title")
            x = x0 - 8

    def _hl(self, color, amount=0.10, base=None):
        """hover 提亮/压暗：把 color 往文字色方向混 amount。"""
        base = base or self.pal["card"]
        return _mix(self.pal["fg"], base, amount if self.theme == "dark" else 0.06)

    # ==================================================================
    # 绘制：Hero 三联
    # ==================================================================
    def _draw_hero(self):
        pal, st = self.pal, self.state
        t = ("hero",)
        y0, h = self.y_hero, self.HERO_H
        x0, x1 = self.PAD_L, self.WIN_W - self.PAD_R
        self.p.card_bg(x0, y0, x1 - x0, h, pal, r=self.CARD_R, glow_h=40, tags=t)

        padL, padT = 14, 12
        inner = (x1 - x0) - padL * 2
        w1 = (inner - self.GAP * 2) * 1.15 / 3.15
        w2 = (inner - self.GAP * 2) / 3.15
        xa = x0 + padL
        xb = xa + w1 + self.GAP
        xc = xb + w2 + self.GAP
        wA, wB, wC = w1, w2, x1 - padL - xc

        # 竖分隔线：只覆盖主体区（设计稿 .cell + .cell { border-left }）
        for xx in (xb - self.GAP / 2, xc - self.GAP / 2):
            self.vline(xx, y0 + padT, y0 + padT + 66, pal["cardline"], tags=t)

        # --- 格 1：账户余额 ---
        self.text(xa, y0 + padT + 6.75, "账户余额", 10, pal["fg3"], bold=True, tags=t)
        cur = st.get("cur", "¥")
        bs = st.get("balance", "--")
        big_y = y0 + padT + 13.5 + 3 + 14.2
        cur_w = self.p.tw(cur, 14, True) / self.S
        self.text(xa, big_y, cur, 14, pal["fg2"], bold=True, tags=t)
        self.text(xa + cur_w + 1, big_y, bs, 27, pal["fg"], bold=True, tags=t)
        by = y0 + padT + 13.5 + 3 + 28.4 + 6 + 7.5
        gp = _mix(pal["accent"], pal["card"], 0.15)
        gg = _mix(pal["idle"], pal["card"], 0.14)
        px_ = xa
        px_ += self.p.pill(px_, by, st.get("badge_period", "闲时 · 5 折"), 9.5,
                           pal["accent"] if self.theme == "dark" else "#0057B8",
                           gp, tags=t) + 5
        self.p.pill(px_, by, st.get("badge_gift", "赠金 --"), 9.5,
                    pal["idle"] if self.theme == "dark" else "#1B6E33", gg, tags=t)

        # --- 格 2：实时速率（space-between：标签左、数值右）---
        self.text(xb, y0 + padT + 6.75, "实时速率", 10, pal["fg3"], bold=True, tags=t)
        r1 = y0 + padT + 13.5 + 5 + 9.45
        r2 = r1 + 18.9
        self.text(xb, r1, "下载", 10, pal["fg3"], tags=t)
        self.text_r(xb + wB, r1, st.get("net_down", "--"), 14, pal["down"],
                    bold=True, tags=t)
        self.text(xb, r2, "上传", 10, pal["fg3"], tags=t)
        self.text_r(xb + wB, r2, st.get("net_up", "--"), 14, pal["up"],
                    bold=True, tags=t)

        # --- 格 3：累计消耗 ---
        self.text(xc, y0 + padT + 6.75, "累计消耗", 10, pal["fg3"], bold=True, tags=t)
        c1 = y0 + padT + 13.5 + 5 + 7.5
        c2 = c1 + 14.2 + 4
        self.text(xc, c1, "今日", 10, pal["fg3"], tags=t)
        self.text_r(xc + wC, c1, st.get("cons_today", "--"), 12, pal["fg"],
                    bold=True, tags=t)
        self.text(xc, c2, "本月", 10, pal["fg3"], tags=t)
        self.text_r(xc + wC, c2, st.get("cons_month", "--"), 12, pal["fg"],
                    bold=True, tags=t)

        # --- 底部双比例条（.bars）---
        bars_y = y0 + padT + 66 + 9
        self.hline(x0 + padL, x1 - padL, bars_y, pal["cardline"], tags=t)
        row1 = bars_y + 1 + 9 + 6.75
        for i, (lab, pct_k, val_k, colors) in enumerate((
                ("赠金", "grant_pct", "grant_val", FIXED["bar_grant"]),
                ("充值", "topup_pct", "topup_val", FIXED["bar_topup"]))):
            yc = row1 + i * 18.5
            self.text(xa, yc, lab, 10, pal["fg3"], bold=True, tags=t)
            tx0 = xa + 44
            tx1 = x1 - padL - 66 - 8
            self.rounded(tx0, yc - 2.5, tx1, yc + 2.5, 3,
                         fill=pal["cardline"], tags=t)
            pct = max(0.0, min(100.0, st.get(pct_k, 0) or 0))
            if pct > 0.5:
                fw = max(3.0, (tx1 - tx0) * pct / 100.0)
                self.p.hgrad(tx0, yc - 2.5, fw, 5, colors[0], colors[1], tags=t)
            self.text_r(x1 - padL, yc, st.get(val_k, "--"), 10, pal["fg2"],
                        bold=True, tags=t)

    # ==================================================================
    # 绘制：模型价格
    # ==================================================================
    def _draw_price(self):
        pal, st = self.pal, self.state
        t = ("price",)
        y0, h = self.y_price, self.PRICE_H
        x0, x1 = self.PAD_L, self.WIN_W - self.PAD_R
        self.p.card_bg(x0, y0, x1 - x0, h, pal, r=self.CARD_R, tags=t)
        padL = 12
        # 卡头
        self.text(x0 + padL, y0 + 10 + 7.5, "模型价格", 11, pal["fg2"],
                  bold=True, tags=t)
        more = st.get("price_more", "")
        is_peak = st.get("is_peak", False)
        mx = x1 - padL
        self.text_r(mx, y0 + 10 + 7.5, more, 9.5,
                    pal["peak"] if is_peak else pal["accent"], tags=t)
        mw = self.p.tw(more, 9.5) / self.S
        self._reg(mx - mw - 4, y0 + 10, mx, y0 + 10 + 15, self.K_PRICE_INFO, "price")
        # 表格
        rows = st.get("price_rows", [])
        heads = ("模型", "缓存命中", "缓存未命中", "输出")
        top = y0 + 32
        th_h, td_h = 18.8, 21.2
        # 列宽：数值列恰好容纳内容，模型列吃剩余，状态列贴右
        st_w = 44
        col_w = [0, 0, 0]
        for ci in range(3):
            wmax = self.p.tw(heads[ci + 1], 9.5, True) / self.S
            for r in rows:
                wmax = max(wmax, self.p.tw(r["vals"][ci], 10.5,
                                           r["cur"]) / self.S)
            col_w[ci] = wmax + 18
        right = x1 - padL - st_w
        name_w = right - (x0 + padL) - sum(col_w)
        xs = [x0 + padL + name_w]
        for wv in col_w:
            xs.append(xs[-1] + wv)
        # 表头
        self.text(x0 + padL, top + th_h / 2, heads[0], 9.5, pal["fg3"],
                  bold=True, tags=t)
        for ci, hd in enumerate(heads[1:]):
            self.text_r(xs[ci] + col_w[ci] - 8, top + th_h / 2, hd, 9.5,
                        pal["fg3"], bold=True, tags=t)
        self.hline(x0 + padL, x1 - padL, top + th_h, pal["cardline"], tags=t)
        # 当前列整列高亮：设计稿里连续几个 td.cur 无间隙 → 视觉上是一条整列色块
        cy = top + th_h
        cur_idx = [i for i, r in enumerate(rows) if r.get("cur")]
        if cur_idx:
            i0, i1 = cur_idx[0], cur_idx[-1]
            if i1 - i0 + 1 == len(cur_idx):      # 连续才铺整块
                self.create_rectangle(
                    self.s_(xs[0]), self.s_(cy + i0 * td_h),
                    self.s_(xs[-1]), self.s_(cy + (i1 + 1) * td_h),
                    fill=_mix(pal["accent"], pal["card"], 0.10), outline="",
                    tags=t)
        # 行
        for ri, r in enumerate(rows):
            ry = cy + ri * td_h
            yc = ry + td_h / 2
            self.text(x0 + padL, yc, r["name"], 10.5,
                      pal["fg"] if r.get("cur") else pal["fg3"],
                      bold=bool(r.get("cur")), tags=t)
            for ci, val in enumerate(r["vals"]):
                self.text_r(xs[ci] + col_w[ci] - 8, yc, val, 10.5,
                            pal["fg"] if r.get("cur") else pal["fg3"],
                            bold=bool(r.get("cur")), tags=t)
            # 状态 pill：按所代表时段取色（设计稿 .st.on 绿 / .st.peak 红），
            # 对比行（非当前生效）降一档浓度以示区别
            st_txt = r["status"]
            kind = r.get("st_kind", "on")
            dim = bool(r.get("dim"))
            i = 0 if self.theme == "dark" else 1
            alpha = 0.08 if dim else 0.15
            if kind == "peak":
                bg = _mix(FIXED["st_peak_bg"][i], pal["card"], alpha)
                fg = _mix(FIXED["st_peak_fg"][i], pal["fg3"], 0.45) if dim \
                    else FIXED["st_peak_fg"][i]
            else:
                bg = _mix(FIXED["st_on_bg"][i], pal["card"], alpha)
                fg = _mix(FIXED["st_on_fg"][i], pal["fg3"], 0.45) if dim \
                    else FIXED["st_on_fg"][i]
            pw = self.p.tw(st_txt, 9, True) / self.S + 10
            self.p.pill(x1 - padL - pw, yc, st_txt, 9, fg, bg, pad_x=5,
                        pad_y=1, tags=t)
            if ri < len(rows) - 1:
                self.hline(x0 + padL, x1 - padL, ry + td_h, pal["cardline"], tags=t)

    # ==================================================================
    # 绘制：走势图
    # ==================================================================
    def _draw_chart(self):
        pal, st = self.pal, self.state
        t = ("chart",)
        y0, h = self.y_chart, self.CHART_H
        x0, x1 = self.PAD_L, self.WIN_W - self.PAD_R
        self.p.card_bg(x0, y0, x1 - x0, h, pal, r=self.CARD_R, tags=t)
        padL = 12
        self.text(x0 + padL, y0 + 10 + 7.5, "近 7 日余额", 11, pal["fg2"],
                  bold=True, tags=t)
        self.text_r(x1 - padL, y0 + 10 + 7.5, st.get("chart_more", ""), 9.5,
                    pal["fg3"], tags=t)

        cx0, cx1 = x0 + padL, x1 - padL
        cy0, ch = y0 + 32, 100
        vals = st.get("chart_vals") or []
        if len(vals) < 2:
            self.text_c((cx0 + cx1) / 2, cy0 + ch / 2,
                        "数据不足，刷新两次后显示走势", 10, pal["fg3"], tags=t)
            self._draw_xlab(cx0, cx1, cy0 + ch, st.get("chart_labels") or [], t)
            return
        vmin, vmax = min(vals), max(vals)
        if vmax - vmin < 1e-9:
            vmax = vmin + 1
        n = len(vals)
        step = (cx1 - cx0) / (n - 1)
        pad_v = 8
        pts = [(cx0 + i * step,
                cy0 + pad_v + (1 - (v - vmin) / (vmax - vmin)) * (ch - pad_v * 2))
               for i, v in enumerate(vals)]
        self.p.area_gradient(cx0, cy0, cx1 - cx0, ch, pts,
                             pal["down"] if self.theme == "dark" else "#2E8BFF",
                             0.42 if self.theme == "dark" else 0.38, tags=t)
        flat = []
        for (px_, py_) in pts:
            flat += [self.s_(px_), self.s_(py_)]
        self.create_line(flat, fill=pal["down"] if self.theme == "dark" else "#2E8BFF",
                         width=max(2, self.px(2)), smooth=True, tags=t)
        # 末点圆点（当前值）
        lx, ly = pts[-1]
        r = 2.6
        self.create_oval(self.s_(lx - r), self.s_(ly - r),
                         self.s_(lx + r), self.s_(ly + r),
                         fill=pal["down"] if self.theme == "dark" else "#2E8BFF",
                         outline=pal["card"], width=max(1, self.px(1)), tags=t)
        self._draw_xlab(cx0, cx1, cy0 + ch, st.get("chart_labels") or [], t)

    def _draw_xlab(self, x0, x1, y, labels, t):
        if not labels:
            return
        n = len(labels)
        for i, lab in enumerate(labels):
            if n == 1:
                self.text_c((x0 + x1) / 2, y + 8, lab, 9, self.pal["fg3"], tags=t)
                continue
            x = x0 + (x1 - x0) * i / (n - 1)
            if i == 0:
                self.text(x, y + 8, lab, 9, self.pal["fg3"], tags=t)
            elif i == n - 1:
                self.text_r(x, y + 8, lab, 9, self.pal["fg3"], tags=t)
            else:
                self.text_c(x, y + 8, lab, 9, self.pal["fg3"], tags=t)

    # ==================================================================
    # 绘制：设置（grid 两列）
    # ==================================================================
    def _draw_settings(self):
        pal, st = self.pal, self.state
        t = ("settings",)
        y0, h = self.y_set, self.SET_H
        x0, x1 = self.PAD_L, self.WIN_W - self.PAD_R
        self.p.card_bg(x0, y0, x1 - x0, h, pal, r=self.CARD_R, tags=t)
        padL = 12
        self.text(x0 + padL, y0 + 10 + 7.5, "设置", 11, pal["fg2"], bold=True, tags=t)
        self.text_r(x1 - padL, y0 + 10 + 7.5, "自动保存", 9.5, pal["fg3"], tags=t)

        # 设计稿 .settings { grid-template-columns: 1fr 1fr; gap: 8px 14px }
        L = x0 + padL
        COLW = (x1 - padL - L - 14) / 2      # 单列宽
        LEND = L + COLW                       # 左列右边界
        R = LEND + 14                         # 右列起点
        REND = x1 - padL                      # 右列右边界
        HL = 15

        # --- row1：API Key（横跨，输入框由 Entry 覆盖）---
        y = y0 + 32
        self.text(L, y + 11, "API Key", 10.5, pal["fg3"], bold=True, tags=t)
        kx, ky, kw, kh = self._key_box()
        focused = self._entries.get("key") is not None and \
            self.focus_get() is self._entries.get("key")
        self.rounded(kx - 8, y + 1, kx + kw, y + 21, 6, fill=pal["card"],
                     outline=pal["accent"] if focused else pal["cardline"], tags=t)

        # --- row2：刷新间隔 / 开机自启 ---
        y2 = y + 22 + 8
        yc = y2 + HL / 2
        self.text(L, yc, "刷新间隔", 10.5, pal["fg3"], bold=True, tags=t)
        iv_txt = f"{st.get('interval', 60)} 秒"
        hovering = self._hover == self.K_INTERVAL
        self.text_r(LEND, yc, iv_txt, 10.5,
                    pal["fg"] if hovering else pal["fg2"], bold=hovering, tags=t)
        iw = self.p.tw(iv_txt, 10.5) / self.S
        self._reg(LEND - iw - 4, y2, LEND, y2 + HL, self.K_INTERVAL, "settings")

        self.text(R, yc, "开机自启", 10.5, pal["fg3"], bold=True, tags=t)
        sw = 26
        self.p.switch(REND - sw, yc, bool(st.get("autostart")), pal, tags=t)
        self._reg(REND - sw - 2, y2, REND, y2 + HL, self.K_AUTOSTART, "settings")

        # --- row3：迷你卡显示 chips（横跨）---
        y3 = y2 + HL + 8
        yc3 = y3 + 9
        self.text(L, yc3, "迷你卡显示", 10.5, pal["fg3"], bold=True, tags=t)
        chips = st.get("chips") or []
        cx = L + self.p.tw("迷你卡显示", 10.5, True) / self.S + 10
        for i, (ckey, label, on) in enumerate(chips):
            tw = self.p.tw(label, 9.5) / self.S
            w = tw + 14
            if on:
                bg = _mix(pal["accent"], pal["card"], 0.10)
                self.rounded(cx, yc3 - 9, cx + w, yc3 + 9, 9, fill=bg,
                             outline=_mix(pal["accent"], pal["card"], 0.45), tags=t)
                self.text_c(cx + w / 2, yc3, label, 9.5, pal["accent"], tags=t)
            else:
                self.rounded(cx, yc3 - 9, cx + w, yc3 + 9, 9, fill=pal["card"],
                             outline=pal["cardline"], tags=t)
                self.text_c(cx + w / 2, yc3, label, 9.5, pal["fg3"], tags=t)
            self._reg(cx, yc3 - 9, cx + w, yc3 + 9, f"chip:{ckey}", "settings")
            cx += w + 5

        # --- row4：数据导出 / 关于 ---
        y4 = y3 + 18 + 8
        yc4 = y4 + HL / 2
        self.text(L, yc4, "数据导出", 10.5, pal["fg3"], bold=True, tags=t)
        hov = self._hover == self.K_CSV
        self.text_r(LEND, yc4, "CSV", 10.5, pal["accent"] if hov else pal["fg2"],
                    bold=hov, tags=t)
        self._reg(LEND - 30, y4, LEND, y4 + HL, self.K_CSV, "settings")
        self.text(R, yc4, "关于", 10.5, pal["fg3"], bold=True, tags=t)
        hov = self._hover == self.K_ABOUT
        self.text_r(REND, yc4, f"v{APP_VERSION}", 10.5,
                    pal["accent"] if hov else pal["fg3"], tags=t)
        self._reg(REND - 46, y4, REND, y4 + HL, self.K_ABOUT, "settings")

    # ==================================================================
    # 绘制：底部状态栏（设计稿之外的必要功能反馈）
    # ==================================================================
    def _draw_status(self):
        pal, st = self.pal, self.state
        t = ("status",)
        y = self.y_status
        self.hline(0, self.WIN_W, y, pal["wline"], tags=t)
        yc = y + self.STATUS_H / 2
        # 状态栏是 9.5px 小字，抗锯齿会稀释笔画颜色：用 fg3 实测对比度只有
        # 4.28:1（低于 WCAG AA），提一档到 fg2 才稳。
        self.text(self.PAD_L, yc, st.get("status", "就绪"), 9.5, pal["fg2"], tags=t)
        x = self.WIN_W - self.PAD_R
        for key, label in ((self.K_SHOT, "截图"), (self.K_REFRESH, "刷新")):
            hov = self._hover == key
            w = self.p.tw(label, 9.5) / self.S + 4
            self.text_r(x, yc, label, 9.5, pal["accent"] if hov else pal["fg2"],
                        bold=hov, tags=t)
            self._reg(x - w, y, x, y + self.STATUS_H, key, "status")
            x -= w + 12


# ============================================================================
# 迷你卡位图渲染（PIL 全量合成）
# ============================================================================
# 为什么用 PIL 而不是 Canvas 画：
#   1. Canvas 无法叠加 alpha —— 渐变受光 / 内阴影 / 双描边这些「玻璃层次」
#      只能靠 PIL 先在位图里合成好再整张贴上去；
#   2. **可验收**：位图就是真机 1:1 的样子，能直接导出 PNG 看，
#      不用依赖 PrintWindow（它对 overrideredirect 窗口会返回灰底假象）。
_MPL_FONTS = {}


def _mfont(px, bold=False):
    """取 PIL 字体（雅黑优先），按物理像素缓存。"""
    key = (int(round(px)), bool(bold))
    f = _MPL_FONTS.get(key)
    if f is not None:
        return f
    from PIL import ImageFont
    names = ([r"C:\Windows\Fonts\msyhbd.ttc"] if bold else []) + \
            [r"C:\Windows\Fonts\msyh.ttc",
             r"C:\Windows\Fonts\segoeuib.ttf" if bold
             else r"C:\Windows\Fonts\segoeui.ttf"]
    f = None
    for p in names:
        try:
            f = ImageFont.truetype(p, max(8, int(round(px))))
            break
        except Exception:
            continue
    if f is None:
        f = ImageFont.load_default()
    if len(_MPL_FONTS) > 120:
        _MPL_FONTS.clear()
    _MPL_FONTS[key] = f
    return f


def _hex2rgb(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def render_mini_card(pal, data, show, w_css, h_css, rows, net_y, S,
                     flat=False):
    """把迷你卡渲染成 PIL 位图（= 真机所见，可直接存盘验收）。

    层次（自下而上）：竖向渐变卡面 → 顶部受光渐隐 → 底部内阴影 →
    外描边 + 内高光描边 → 文字 / 徽章 / 分隔线。

    flat=True 时切到「玻璃掩膜模式」：卡面纯黑、只画文字与细描边
    （配合真 acrylic，任何大面积亮色都会破坏掩膜）。
    """
    from PIL import Image, ImageDraw, ImageChops

    W = max(1, int(round(w_css * S)))
    H = max(1, int(round(h_css * S)))
    R = max(3, int(round(MINI_CARD_RADIUS * S)))   # 苹果风圆角
    px1 = max(1, int(round(S)))

    if flat:
        # 玻璃掩膜模式：卡面必须**纯黑**（DWM 把纯黑像素替换成 backdrop），
        # 因此不能有渐变 / 受光 / 内阴影 / 反光 —— 任何大面积亮色都会让
        # 掩膜失效、玻璃退回实底。只画文字与细描边。
        card = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    else:
        # 1) 卡面竖向渐变：顶部亮 → 底部压暗，给"有一块玻璃"的厚度
        a, b = _hex2rgb(pal["grad_top"]), _hex2rgb(pal["grad_bot"])
        col = Image.new("RGB", (1, H))
        for y in range(H):
            t = y / max(1, H - 1)
            col.putpixel((0, y), tuple(
                round(a[i] + (b[i] - a[i]) * t) for i in range(3)))
        card = col.resize((W, H)).convert("RGBA")

        mask = Image.new("L", (W, H), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, W - 1, H - 1], radius=R, fill=255)

        # 卡面本身也裁成圆角透明（四角不留填充）：窗口 region 再裁一次做双保险，
        # 这样位图四角即透明 —— 预览图 = 真机所见，且不纯依赖 region 生效。
        card.putalpha(mask)

        # 2) 顶部受光：alpha 平滑衰减（不是一条硬白线）
        gh = max(1, int(round(H * pal["gloss_ratio"])))
        gloss = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(gloss)
        top_a = 255 * float(pal["rim_in_a"]) * 0.85
        for y in range(gh):
            k = 1.0 - y / max(1, gh - 1)
            gd.line([(0, y), (W - 1, y)],
                    fill=(255, 255, 255, int(top_a * (k ** 2.2))))
        gloss.putalpha(ImageChops.multiply(gloss.getchannel("A"), mask))
        card = Image.alpha_composite(card, gloss)

        # 3) 底部内阴影：底部积一点暗，卡片才"沉"得下去
        bh = max(1, int(round(H * 0.16)))
        shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(shade)
        amax = int(255 * float(pal["shade_a"]))
        for i in range(bh):
            y = H - bh + i
            sd.line([(0, y), (W - 1, y)],
                    fill=(0, 0, 0, int(amax * ((i + 1) / bh) ** 2)))
        shade.putalpha(ImageChops.multiply(shade.getchannel("A"), mask))
        card = Image.alpha_composite(card, shade)

    d = ImageDraw.Draw(card)
    if flat:
        # 掩膜模式只保留一圈细描边（不影响掩膜主体）
        d.rounded_rectangle([0, 0, W - 1, H - 1], radius=R,
                            outline=_hex2rgb(pal["rim"]), width=px1)
    else:
        # 4) 双描边：外圈主题描边 + 内圈高光（玻璃边缘的经典画法）
        d.rounded_rectangle([0, 0, W - 1, H - 1], radius=R,
                            outline=_hex2rgb(pal["rim"]), width=px1)
        if W > 3 and H > 3:
            ia = int(255 * float(pal["rim_in_a"]) * 0.55)
            d.rounded_rectangle([px1, px1, W - 1 - px1, H - 1 - px1],
                                radius=max(2, R - px1),
                                outline=_hex2rgb(pal["rim_in"]) + (ia,),
                                width=px1)

        # 4b) 顶边反光线：玻璃边缘的一道亮线（"苹果感"的关键细节）
        tl_a = int(255 * float(pal.get("topline_a", 0.2)))
        if tl_a > 0 and W > 2 * R + 2:
            d.line([(R, px1), (W - 1 - R, px1)],
                   fill=(255, 255, 255, tl_a), width=px1)

    # 5) 文字层
    L = int(round(14 * S))
    Rt = W - int(round(14 * S))
    yc1 = int(round((12 + 17.5) * S))
    d.text((L, yc1), data.get("balance", "--"), font=_mfont(26 * S, True),
           fill=_hex2rgb(pal["fg"]), anchor="lm")

    if show.get("period") and data.get("badge_period"):
        txt = data["badge_period"]
        bf = _mfont(10 * S, True)
        bh_ = int(round(20 * S))
        padx = int(round(7 * S))
        bw = int(round(d.textlength(txt, font=bf) + padx * 2))
        x0, y0 = Rt - bw, yc1 - bh_ // 2
        bgc, fgc = pal["badge_period"]
        d.rounded_rectangle([x0, y0, x0 + bw, y0 + bh_],
                            radius=bh_ // 2, fill=_hex2rgb(bgc),
                            outline=_hex2rgb(fgc) + (int(255 * 0.24),),
                            width=px1)
        d.text((x0 + bw // 2, yc1), txt, font=bf,
               fill=_hex2rgb(fgc), anchor="mm")

    fl, fv = _mfont(11 * S), _mfont(11 * S)
    for _kind, yc, dkey, label in rows:
        yy = int(round(yc * S))
        d.text((L, yy), label, font=fl, fill=_hex2rgb(pal["fg3"]), anchor="lm")
        d.text((Rt, yy), data.get(dkey, "--"), font=fv,
               fill=_hex2rgb(pal["fg2"]), anchor="rm")

    if net_y is not None:
        ly = int(round(net_y * S))
        d.line([(L, ly), (Rt, ly)], fill=_hex2rgb(pal["line"]), width=px1)
        yn = int(round((net_y + 17) * S))
        fnet = _mfont(12 * S, True)
        dtxt = data.get("net_down", "--")
        d.text((L, yn), dtxt, font=fnet, fill=_hex2rgb(pal["down"]),
               anchor="lm")
        dw = d.textlength(dtxt, font=fnet)
        d.text((L + dw + int(round(12 * S)), yn), data.get("net_up", "--"),
               font=fnet, fill=_hex2rgb(pal["up"]), anchor="lm")
    return card


# 阴影外扩量（CSS px）：窗口比卡片大这么多，多出来的区域全画柔和阴影
MINI_SHADOW_PAD = 10

# 迷你卡圆角半径（CSS px）—— **单一来源**：位图 mask 与窗口 region 裁切
# 必须用同一个值，否则 region 裁得比卡片圆角更方/更圆，四角会露出窗口底色
# （表现为「四个角有黑底没切掉」）。ui.py::_place_mini 直接引用本常量。
MINI_CARD_RADIUS = 18


def render_mini_window(pal, data, show, w_css, h_css, rows, net_y, S,
                       flat=False, shadow=True):
    """渲染位图。

    - flat=True（玻璃掩膜模式）：返回纯黑卡片位图（acrylic 掩膜），不走阴影。
    - shadow=False：只渲染**纯卡片**（无阴影外扩），供 Tk 窗口直接承载。
    - 默认（flat=False, shadow=True）：卡片 + 四周高斯模糊阴影。
    """
    from PIL import Image, ImageDraw, ImageFilter
    card = render_mini_card(pal, data, show, w_css, h_css, rows, net_y, S,
                            flat=flat)
    if flat or not shadow:
        return card
    p = max(2, int(round(MINI_SHADOW_PAD * S)))
    W, H = card.size
    TW, TH = W + 2 * p, H + 2 * p
    R = max(3, int(round(MINI_CARD_RADIUS * S)))
    layer = Image.new("L", (TW, TH), 0)
    ImageDraw.Draw(layer).rounded_rectangle(
        [p, p, p + W - 1, p + H - 1], radius=R,
        fill=int(255 * float(pal.get("shadow_a", 0.40))))
    layer = layer.filter(ImageFilter.GaussianBlur(radius=max(2.0, p * 0.8)))
    out = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
    out.paste(Image.new("RGBA", (TW, TH), (0, 0, 0, 255)), (0, 0), layer)
    out.alpha_composite(card, (p, p))
    return out


# ============================================================================
# MiniView —— 桌面迷你卡（对照设计稿 .glass .mini，宽 300）
# ============================================================================
class MiniView:
    """迷你卡渲染器（2026-10-25 起**不再继承 tk.Canvas**）。

    实底模式下整张卡（含外扩柔和阴影）由 PIL 渲染成一张位图，交给 App 用
    `glass.apply_layered_bitmap()` 贴到顶级窗口上：
      - 阴影在位图里渐隐、卡片外 alpha=0 → 不会有一圈黑边；
      - 窗口里**不放任何 Tk 控件** —— Tk 控件全是不透明的，只要放一个 Canvas
        就会把阴影区糊成一片实色，半透明就白做了。
    """

    W_BASE = 300
    PAD_L = PAD_R = 14
    PAD_T, PAD_B = 12, 11
    ROW1_H = 35                 # .bal 26px 行（normal line-height）
    SUB_H = 15                  # .sub 11px 行
    NET_LH = 16                 # .net 12px 行

    def __init__(self, master=None, scale=1.0, **kw):
        self.S = scale
        self.master = master    # 兼容旧签名，不再使用
        self.w_css = self.W_BASE
        self.h_css = 0
        self._last_img = None
        self._last = None

    def s_(self, v):
        return v * self.S

    def px_(self, v):
        return int(round(v * self.S))

    # ---------- 布局 ----------
    def layout(self, show):
        """返回 (width, height, rows)：rows 为 [(kind, y_center, ...)]（CSS px）。"""
        rows = []
        y = self.PAD_T
        y += self.ROW1_H
        first = True
        if show.get("cons"):
            y += 7 if first else 3
            rows.append(("sub", y + self.SUB_H / 2, "cons_today", "今日消耗"))
            y += self.SUB_H
            first = False
            y += 3
            rows.append(("sub", y + self.SUB_H / 2, "cons_month", "本月消耗"))
            y += self.SUB_H
        if show.get("price"):
            y += 7 if first else 3
            rows.append(("sub", y + self.SUB_H / 2, "price", "当前计费"))
            y += self.SUB_H
            first = False
        h = y
        net_y = None
        if show.get("net"):
            net_y = h + 8
            h = net_y + 1 + 8 + self.NET_LH
        h += self.PAD_B
        return self.W_BASE, h, rows, net_y

    # ---------- 渲染 ----------
    def render(self, pal, data, show, glass_on=False, shadow=True):
        """渲染位图，返回 (卡片宽, 卡片高)（CSS px）。

        glass_on=True → flat 模式：纯黑卡面只画文字（acrylic 掩膜）。
        shadow=False → 只渲染**纯卡片**位图（无阴影外扩），供 Tk 窗口直接
          承载：窗口尺寸 = 卡片尺寸，圆角靠 Tk 窗口的 region 裁切，不需要
          半透明层，因此既不会黑边也不会隐形（2026-10-25 回退方案）。
        """
        w, h, rows, net_y = self.layout(show)
        self.w_css, self.h_css = w, h
        img = render_mini_window(pal, data, show, w, h, rows, net_y, self.S,
                                 flat=bool(glass_on), shadow=shadow)
        self._last_img = img
        self._last = (pal, data, show, glass_on, shadow)
        return w, h

    def reapply(self):
        """位置 / 尺寸变化后重贴位图（沿用上次数据，不重算布局）。"""
        last = getattr(self, "_last", None)
        if last is None:
            return None
        return self.render(*last)

    def export(self, path):
        """把最近一次渲染的位图存盘 —— 真机 1:1 效果图，用于验收。"""
        img = getattr(self, "_last_img", None)
        if img is None:
            return False
        img.save(path)
        return True

    @property
    def window_size(self):
        """当前位图尺寸（= 窗口应有的物理像素尺寸，含阴影外扩）。"""
        img = getattr(self, "_last_img", None)
        if img is None:
            return None
        return img.size
