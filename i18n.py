# -*- coding: utf-8 -*-
"""国际化：中文 / 英文 双语支持。

- 所有用户可见文案都走 `t(key, **kwargs)`，不在业务代码里硬编码语言字符串。
- 语言由模块级 `LANG` 控制，启动时由 config `[ui] lang` 决定（见 ui.py）。
- 默认 `zh-CN`：既有中文用户行为与历史一致，除非配置显式改为 `en-US`。
- 键缺失时返回键名本身，方便开发期发现漏翻（不会静默显示空白）。
"""

# 可选语言（顺序即标题栏语言按钮的「目标语言」展示顺序）
LANGS = ("zh-CN", "en-US")
DEFAULT_LANG = "zh-CN"
LANG = DEFAULT_LANG

# 每个键对应一个 {语言: 文案} 字典；带占位符的用 {name} 在调用处 format。
STRINGS = {
    # ---------------- 窗口 / 托盘 ----------------
    "app_title": {
        "zh-CN": "DeepSeek 余额 / 用量查看器",
        "en-US": "DeepSeek Balance / Usage Viewer",
    },
    "tray_name": {
        "zh-CN": "DeepSeek 余额查看器",
        "en-US": "DeepSeek Balance Viewer",
    },

    # ---------------- 标题栏按钮 ----------------
    "pill_mini": {"zh-CN": "迷你窗", "en-US": "Mini"},
    "pill_lang": {"zh-CN": "EN", "en-US": "中文"},
    "pill_theme_light": {"zh-CN": "切换浅色", "en-US": "Light"},
    "pill_theme_dark": {"zh-CN": "切换深色", "en-US": "Dark"},
    "tip_mini": {
        "zh-CN": "开启桌面悬浮迷你卡",
        "en-US": "Pin a floating mini card to the desktop",
    },

    # ---------------- Hero 三联 ----------------
    "hero_balance": {"zh-CN": "账户余额", "en-US": "Account Balance"},
    "hero_speed": {"zh-CN": "实时速率", "en-US": "Network Speed"},
    "hero_down": {"zh-CN": "下载", "en-US": "Down"},
    "hero_up": {"zh-CN": "上传", "en-US": "Up"},
    "hero_usage": {"zh-CN": "累计消耗", "en-US": "Total Usage"},
    "hero_today": {"zh-CN": "今日", "en-US": "Today"},
    "hero_month": {"zh-CN": "本月", "en-US": "This Month"},
    "bar_grant": {"zh-CN": "赠金", "en-US": "Grant"},
    "bar_topup": {"zh-CN": "充值", "en-US": "Top-up"},
    "badge_offpeak_default": {"zh-CN": "闲时 · 5 折", "en-US": "Off-peak · 50% off"},
    "badge_gift_default": {"zh-CN": "赠金 --", "en-US": "Grant --"},

    # ---------------- 模型价格 ----------------
    "price_title": {"zh-CN": "模型价格", "en-US": "Model Pricing"},
    "price_head_model": {"zh-CN": "模型", "en-US": "Model"},
    "price_head_hit": {"zh-CN": "缓存命中", "en-US": "Cached Hit"},
    "price_head_miss": {"zh-CN": "缓存未命中", "en-US": "Cached Miss"},
    "price_head_out": {"zh-CN": "输出", "en-US": "Output"},
    "period_peak": {"zh-CN": "峰时", "en-US": "Peak"},
    "period_offpeak": {"zh-CN": "闲时", "en-US": "Off-peak"},

    # ---------------- 走势图 ----------------
    "chart_title": {"zh-CN": "近 7 日余额", "en-US": "Balance (Last 7 Days)"},
    "chart_empty": {
        "zh-CN": "数据不足，刷新两次后显示走势",
        "en-US": "Not enough data; refresh twice to show the trend",
    },

    # ---------------- 设置 ----------------
    "settings_title": {"zh-CN": "设置", "en-US": "Settings"},
    "settings_autosave": {"zh-CN": "自动保存", "en-US": "Auto-save"},
    "settings_apikey": {"zh-CN": "API Key", "en-US": "API Key"},
    "settings_interval": {"zh-CN": "刷新间隔", "en-US": "Refresh Interval"},
    "settings_autostart": {"zh-CN": "开机自启", "en-US": "Auto-start"},
    "settings_mini_shows": {"zh-CN": "迷你卡显示", "en-US": "Mini Card Shows"},
    "settings_export": {"zh-CN": "数据导出", "en-US": "Export Data"},
    "settings_about": {"zh-CN": "关于", "en-US": "About"},

    # ---------------- 状态栏 ----------------
    "status_ready": {"zh-CN": "就绪", "en-US": "Ready"},
    "status_shot": {"zh-CN": "截图", "en-US": "Shot"},
    "status_refresh": {"zh-CN": "刷新", "en-US": "Refresh"},

    # ---------------- 迷你卡 chips ----------------
    "chip_balance": {"zh-CN": "余额", "en-US": "Balance"},
    "chip_period": {"zh-CN": "时段", "en-US": "Period"},
    "chip_price": {"zh-CN": "价格", "en-US": "Price"},
    "chip_usage": {"zh-CN": "累计", "en-US": "Usage"},
    "chip_net": {"zh-CN": "网速", "en-US": "Net"},

    # ---------------- 迷你卡行标签 ----------------
    "mini_today": {"zh-CN": "今日消耗", "en-US": "Today Used"},
    "mini_month": {"zh-CN": "本月消耗", "en-US": "Month Used"},
    "mini_price": {"zh-CN": "当前计费", "en-US": "Pricing"},

    # ---------------- 时段 / 折扣（数据驱动）----------------
    "fmt_peak_disc": {"zh-CN": "{factor}× 倍价", "en-US": "{factor}× price"},
    "fmt_offpeak_disc": {"zh-CN": "{zhe} 折", "en-US": "{pct}% off"},
    "fmt_more_active": {
        "zh-CN": "{period} {disc}生效中",
        "en-US": "{period} {disc} active",
    },
    "fmt_more_until": {
        "zh-CN": " · 距{next} {left}",
        "en-US": " · {next} in {left}",
    },
    "fmt_badge_peak": {
        "zh-CN": "峰时 · {factor}× 倍价",
        "en-US": "Peak · {factor}× price",
    },
    "fmt_badge_offpeak": {
        "zh-CN": "闲时 · {zhe} 折",
        "en-US": "Off-peak · {pct}% off",
    },
    "fmt_grant": {"zh-CN": "赠金 ¥{v}", "en-US": "Grant ¥{v}"},
    "fmt_price_out": {"zh-CN": "输出 ¥{v}/百万", "en-US": "Output ¥{v}/M"},
    "fmt_daily_avg": {"zh-CN": "日均 ¥{v}", "en-US": "Avg ¥{v}/day"},
    "net_unavailable": {"zh-CN": "不可用", "en-US": "N/A"},
    "fmt_interval_label": {"zh-CN": "{val} 秒", "en-US": "{val} s"},
    "no_key_badge": {"zh-CN": "未配置 Key", "en-US": "No API Key"},

    # ---------------- 刷新间隔 ----------------
    "interval_title": {"zh-CN": "刷新间隔", "en-US": "Refresh Interval"},
    "interval_prompt": {
        "zh-CN": "自动刷新间隔（秒，30–3600）：",
        "en-US": "Auto-refresh interval (seconds, 30–3600): ",
    },
    "fmt_interval_set": {
        "zh-CN": "刷新间隔已设为 {val} 秒",
        "en-US": "Refresh interval set to {val} s",
    },

    # ---------------- 开机自启 ----------------
    "fmt_autostart_on": {
        "zh-CN": "已开启开机自启（启动即钉桌面迷你窗）",
        "en-US": "Auto-start enabled (pins mini card on launch)",
    },
    "fmt_autostart_off": {
        "zh-CN": "已关闭开机自启",
        "en-US": "Auto-start disabled",
    },
    "autostart_fail": {
        "zh-CN": "开机自启设置失败（可能需要管理员权限）",
        "en-US": "Failed to set auto-start (admin rights may be required)",
    },

    # ---------------- 刷新状态 ----------------
    "no_key_refresh": {
        "zh-CN": "未配置 API Key，无法刷新",
        "en-US": "No API Key configured; cannot refresh",
    },
    "refreshing": {
        "zh-CN": "正在请求 DeepSeek ...",
        "en-US": "Requesting DeepSeek ...",
    },
    "empty_response": {
        "zh-CN": "接口返回为空，请稍后重试",
        "en-US": "Empty response; please retry later",
    },
    "fmt_refresh_ok": {"zh-CN": "刷新成功", "en-US": "Refresh succeeded"},
    "refresh_unavailable": {
        "zh-CN": "（账户余额不可用）",
        "en-US": " (balance unavailable)",
    },
    "fmt_apikey_saved": {
        "zh-CN": "API Key 已自动保存",
        "en-US": "API Key saved automatically",
    },
    "apikey_cleared": {"zh-CN": "（已清空）", "en-US": " (cleared)"},
    "fmt_theme": {
        "zh-CN": "已切换到{theme}主题",
        "en-US": "Switched to {theme} theme",
    },
    "theme_dark": {"zh-CN": "深色", "en-US": "dark"},
    "theme_light": {"zh-CN": "浅色", "en-US": "light"},
    "mini_restored": {"zh-CN": "已恢复完整窗口", "en-US": "Restored full window"},
    "mini_open_fail": {
        "zh-CN": "迷你窗打开失败，已恢复主窗（详见日志）",
        "en-US": "Mini window failed to open; restored main window (see log)",
    },
    "tray_restored": {
        "zh-CN": "已从托盘恢复窗口",
        "en-US": "Restored window from tray",
    },
    "tray_unavailable": {
        "zh-CN": "托盘不可用，关闭窗口将直接退出程序",
        "en-US": "Tray unavailable; closing the window quits the app",
    },
    "fmt_csv_exported": {
        "zh-CN": "已导出 CSV：{path}",
        "en-US": "CSV exported: {path}",
    },
    "fmt_shot_saved": {
        "zh-CN": "已截图：{path}",
        "en-US": "Screenshot saved: {path}",
    },

    # ---------------- 错误 ----------------
    "err_auth": {"zh-CN": "API Key 错误", "en-US": "Invalid API Key"},
    "err_insufficient": {"zh-CN": "余额不足", "en-US": "Insufficient Balance"},
    "err_ratelimit": {"zh-CN": "请求被限流", "en-US": "Rate Limited"},
    "err_network": {"zh-CN": "网络异常", "en-US": "Network Error"},
    "err_server": {"zh-CN": "服务端错误", "en-US": "Server Error"},
    "err_api": {"zh-CN": "接口异常", "en-US": "API Error"},
    "err_unknown": {"zh-CN": "未知错误", "en-US": "Unknown Error"},
    "fmt_err": {"zh-CN": "{title}：{msg}", "en-US": "{title}: {msg}"},

    # ---------------- 弹窗：价格说明 ----------------
    "price_info_title": {"zh-CN": "价格说明", "en-US": "Pricing Notes"},
    "price_info_body": {
        "zh-CN":
            "单位：元 / 百万 tokens\n"
            "模型版本：{versions}\n"
            "并发限制：{concs}\n\n"
            "高峰时段：北京时间周一至周五（不含法定节假日）\n"
            "  9:00–12:00、14:00–18:00；其余时段（含周末与节假日全天）为空闲。\n"
            "高峰价 = 空闲价 × {peak:g}\n\n"
            "本程序不自动识别法定节假日（节假日会保守算作高峰）。\n"
            "价格快照：{snapshot}\n"
            "来源：{source}\n以官网为准。",
        "en-US":
            "Unit: CNY / million tokens\n"
            "Model versions: {versions}\n"
            "Concurrency limits: {concs}\n\n"
            "Peak hours: Mon–Fri (Beijing time, statutory holidays excluded)\n"
            "  09:00–12:00, 14:00–18:00; all other times (incl. weekends & holidays) "
            "are off-peak.\n"
            "Peak price = off-peak price × {peak:g}\n\n"
            "This app does not auto-detect statutory holidays (holidays are treated "
            "as peak by default).\n"
            "Price snapshot: {snapshot}\n"
            "Source: {source}\nRefer to the official site.",
    },

    # ---------------- 弹窗：关于 ----------------
    "about_title": {"zh-CN": "关于", "en-US": "About"},
    "about_body": {
        "zh-CN":
            "DeepSeek 余额 / 用量查看器  v{version}\n\n"
            "· 余额与赠金数据来自 DeepSeek 官方接口\n"
            "· 消耗与走势为本机追踪估算（非官方用量）\n"
            "· API Key 使用 Windows DPAPI 加密，仅存本机\n"
            "· 配置文件：{config}\n\n"
            "价格来源：{source}",
        "en-US":
            "DeepSeek Balance / Usage Viewer  v{version}\n\n"
            "· Balance & grant data come from the official DeepSeek API\n"
            "· Usage & trends are estimated locally (not official usage)\n"
            "· API Key is encrypted with Windows DPAPI and stored locally only\n"
            "· Config file: {config}\n\n"
            "Price source: {source}",
    },

    # ---------------- CSV / 截图 弹窗 ----------------
    "csv_no_data": {"zh-CN": "无数据", "en-US": "No Data"},
    "csv_no_data_msg": {
        "zh-CN": "暂无余额历史可导出，请先刷新几次。",
        "en-US": "No balance history to export yet; please refresh a few times first.",
    },
    "csv_exported": {"zh-CN": "已导出", "en-US": "Exported"},
    "csv_exported_msg": {"zh-CN": "已保存：\n{path}", "en-US": "Saved:\n{path}"},
    "csv_fail": {"zh-CN": "导出失败", "en-US": "Export Failed"},
    "shot_no_window": {"zh-CN": "无窗口", "en-US": "No Window"},
    "shot_no_window_msg": {
        "zh-CN": "当前无可截图窗口，请先显示主窗口或迷你窗。",
        "en-US": "No window available to capture; show the main or mini window first.",
    },
    "shot_done": {"zh-CN": "已截图", "en-US": "Captured"},
    "shot_done_msg": {"zh-CN": "已保存：\n{path}", "en-US": "Saved:\n{path}"},
    "shot_fail": {"zh-CN": "截图失败", "en-US": "Capture Failed"},

    # ---------------- 托盘菜单 ----------------
    "tray_show": {"zh-CN": "显示主窗口", "en-US": "Show Window"},
    "tray_pin": {"zh-CN": "钉在桌面", "en-US": "Pin to Desktop"},
    "tray_refresh": {"zh-CN": "刷新", "en-US": "Refresh"},
    "tray_quit": {"zh-CN": "退出", "en-US": "Quit"},
    "tray_notify_title": {
        "zh-CN": "DeepSeek 余额查看器",
        "en-US": "DeepSeek Balance Viewer",
    },
    "tray_notify_msg": {
        "zh-CN": "已最小化到系统托盘，右键图标可恢复或退出",
        "en-US": "Minimized to system tray; right-click the icon to restore or quit",
    },

    # ---------------- 迷你卡右键菜单 ----------------
    "mini_restore": {"zh-CN": "恢复完整窗口", "en-US": "Restore Window"},
    "mini_refresh": {"zh-CN": "手动刷新", "en-US": "Refresh"},
    "mini_toggle_theme": {"zh-CN": "切换深/浅色", "en-US": "Toggle Theme"},
    "mini_quit": {"zh-CN": "退出", "en-US": "Quit"},

    # ---------------- CSV 表头 ----------------
    "csv_header_time": {"zh-CN": "时间", "en-US": "Time"},
    "csv_header_currency": {"zh-CN": "币种", "en-US": "Currency"},
    "csv_header_balance": {"zh-CN": "总余额", "en-US": "Total Balance"},
    "csv_header_used": {
        "zh-CN": "累计消耗(相对首次)",
        "en-US": "Cumulative Used (vs first)",
    },
}


def set_lang(lang: str):
    """设置当前语言（仅当 lang 在 LANGS 内才生效）。"""
    global LANG
    if lang in LANGS:
        LANG = lang


def get_lang() -> str:
    return LANG


def t(key: str, **kwargs) -> str:
    """取当前语言文案；支持 {占位符} 格式化。键缺失返回键名本身。"""
    entry = STRINGS.get(key)
    if entry is None:
        return key
    s = entry.get(LANG, entry.get(DEFAULT_LANG, key))
    if kwargs:
        try:
            return s.format(**kwargs)
        except Exception:
            return s
    return s
