# -*- coding: utf-8 -*-
"""DeepSeek API 价格（当前时段）。

数据来源：DeepSeek 官方「模型 & 价格」页
  https://api-docs.deepseek.com/zh-cn/quick_start/pricing
快照日期：2026-09-29（价格可能调整，请以官网为准）
单位：元(CNY) / 百万 tokens。

官方规则（原始表述，勿改动语义）：
  1. 空闲时段价格为高峰时段价格的一半（即 高峰 = 空闲 × 2）。
  2. 北京时间周一至周五（不含中国法定节假日）9:00-12:00、14:00-18:00 为高峰时段；
     其余时段，包括周末及中国法定节假日全天均为空闲时段。
     → 本程序**不自动识别法定节假日**，仅按"工作日 + 时间窗"估算，
       节假日当天会保守地把高峰时段算成高峰（仅影响展示，不影响账户数据）。
  3. 仅有两个在售模型：deepseek-flash、deepseek-v4-pro。
     旧模型名 deepseek-v4-flash / deepseek-v4-flash-vision-exp 仍可调用，
     但对应模型已下线，请求由 DeepSeek-V4.1-Flash 提供服务并按 Flash 价格计费，
     因此此处**不作为独立模型列出**。
  4. 图像理解是 deepseek-flash 的能力（deepseek-v4-pro 不支持），并非独立模型。
  5. 扣费优先扣减赠送余额，再扣充值余额。

如官方调价，只需改下方 PRICING_OFFPEAK（空闲时段单价）一处；
高峰价按官方规则 ×2 自动推导。
"""

import time

# 各模型「空闲时段」单价（元 / 百万 tokens）
#   键      = 官方模型 ID，调用 API 时 model 参数填这个
#   version = 模型版本（官网「模型版本」行）
#   hit     = 百万tokens 输入（缓存命中）
#   miss    = 百万tokens 输入（缓存未命中）
#   out     = 百万tokens 输出
#   conc    = 并发限制（官方数据，非价格，仅作参考展示）
PRICING_OFFPEAK = {
    "deepseek-flash": {
        "version": "DeepSeek-V4.1-Flash",
        "hit": 0.02,
        "miss": 1.0,
        "out": 4.0,
        "conc": 2500,
    },
    "deepseek-v4-pro": {
        "version": "DeepSeek-V4-Pro-0813",
        "hit": 0.15,
        "miss": 4.5,
        "out": 13.5,
        "conc": 500,
    },
}

# 高峰时段价格 = 空闲时段价格 × 该系数（官方规则第 1 条）
PEAK_FACTOR = 2.0

# 高峰时段窗口（北京时间，24 小时制，[起, 止)）
PEAK_WINDOWS = ((9, 12), (14, 18))

# 价格来源，展示在界面上便于追溯
PRICING_SOURCE = "https://api-docs.deepseek.com/zh-cn/quick_start/pricing"
PRICING_SNAPSHOT = "2026-09-29"


def current_period() -> dict:
    """返回当前时段信息（基于北京时间 UTC+8，无夏令时）。"""
    # 把 UTC 时间整体加 8 小时，得到的"伪 UTC"即北京时间的时分与星期
    bj = time.gmtime(time.time() + 8 * 3600)
    is_weekday = bj.tm_wday < 5          # 0=周一 ... 4=周五
    in_window = any(start <= bj.tm_hour < end for start, end in PEAK_WINDOWS)
    is_peak = is_weekday and in_window
    return {
        "peak": is_peak,
        # 官方术语为「高峰时段」/「空闲时段」
        "label": "高峰时段" if is_peak else "空闲时段",
        "beijing": f"{bj.tm_mon:02d}-{bj.tm_mday:02d} {bj.tm_hour:02d}:00 (北京时间)",
    }


def get_current_prices():
    """返回 (时段信息, 各模型当前时段价格列表)。

    高峰时段返回高峰价，空闲时段返回空闲价（均为官方口径）。
    """
    period = current_period()
    factor = PEAK_FACTOR if period["peak"] else 1.0
    rows = []
    for model_id, p in PRICING_OFFPEAK.items():
        rows.append({
            "id": model_id,
            "version": p["version"],
            "hit": p["hit"] * factor,
            "miss": p["miss"] * factor,
            "out": p["out"] * factor,
            "conc": p["conc"],
        })
    return period, rows


# 计费项（顺序与官方表格一致）
BILLING_ITEMS = (
    ("hit", "输入（缓存命中）"),
    ("miss", "输入（缓存未命中）"),
    ("out", "输出"),
)


def get_price_table():
    """返回 (时段信息, 模型列表)，每个模型含「空闲」「高峰」两套单价。

    供界面同时展示两个时段并高亮当前时段，结构对齐官方定价表，便于肉眼核对。
    """
    period = current_period()
    rows = []
    for model_id, p in PRICING_OFFPEAK.items():
        rows.append({
            "id": model_id,
            "version": p["version"],
            "conc": p["conc"],
            "offpeak": {k: p[k] for k, _ in BILLING_ITEMS},
            "peak": {k: p[k] * PEAK_FACTOR for k, _ in BILLING_ITEMS},
        })
    return period, rows


def _peak_at(wday: int, hour: int) -> bool:
    """给定「星期(0=周一) + 小时」判断是否高峰时段。"""
    return wday < 5 and any(start <= hour < end for start, end in PEAK_WINDOWS)


def next_period_change():
    """返回 (剩余秒数, 目标时段标签)，即距下一次「峰⇄闲」切换还有多久。

    设计稿价格卡右上角展示「距峰时 2h 14m」就是这里算的。
    找不到（理论上不会）返回 None。
    """
    bj = time.gmtime(time.time() + 8 * 3600)
    cur_peak = _peak_at(bj.tm_wday, bj.tm_hour)
    now_sec = bj.tm_hour * 3600 + bj.tm_min * 60 + bj.tm_sec
    bounds = sorted({h for win in PEAK_WINDOWS for h in win})
    for day in range(9):
        wday = (bj.tm_wday + day) % 7
        for hh in bounds:
            off = day * 86400 + hh * 3600 - now_sec
            if off <= 0:
                continue
            if _peak_at(wday, hh) != cur_peak:
                return off, ("高峰时段" if not cur_peak else "空闲时段")
    return None
