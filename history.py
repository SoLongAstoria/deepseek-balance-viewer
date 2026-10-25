# -*- coding: utf-8 -*-
"""本地余额追踪。

DeepSeek 公开接口只返回当前余额，不返回累计消耗 / 历史用量。
本模块在本地保存每次刷新的余额快照，用于：
  - 绘制余额走势图
  - 估算「自首次记录起的累计消耗」（余额下降的累计值，作为用量代理指标）
数据仅存于本机 history.json，不上传。
"""

import os
import json
import time
from datetime import datetime

import config as cfg

# 与 config.ini 同目录（用户级持久目录），避免 onefile 打包后写入临时目录被清理
#
# ⚠ 隔离规则（2026-10-25 踩坑）：必须跟随 `DSBV_CONFIG` / `DSBV_HISTORY` 一起隔离。
# 冒烟脚本 `_smoke_ui.py` 只隔离了配置、没隔离历史，注入的样例余额 12.34 被
# `save_snapshot()` 正式写进了**用户真实** history.json，与真实余额 78.94 交替出现
# → 每次"78.94→12.34"都被算成 66.60 的消耗 → 「累计消耗」虚高到 532.80。
# 现在：任一隔离变量存在时，历史文件跟着临时配置目录走，绝不碰真实数据。
def _default_history_path() -> str:
    explicit = os.environ.get("DSBV_HISTORY")
    if explicit:
        return explicit
    iso_cfg = os.environ.get("DSBV_CONFIG")
    if iso_cfg:                      # 测试 / 截图模式：不写用户真实数据
        return os.path.join(os.path.dirname(os.path.abspath(iso_cfg)),
                            "history.json")
    return os.path.join(cfg.app_data_dir(), "history.json")


HISTORY_PATH = _default_history_path()
MAX_RECORDS = 500


def load_history() -> list:
    if os.path.exists(HISTORY_PATH):
        try:
            with open(HISTORY_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_snapshot(total_balance: float, currency: str) -> list:
    """追加一条余额快照，返回更新后的列表。"""
    hist = load_history()
    # 与上一条相同则跳过，避免自动刷新产生重复点
    if hist and abs(hist[-1].get("balance", -1) - total_balance) < 1e-9:
        return hist
    hist.append({
        "ts": time.time(),
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "balance": total_balance,
        "currency": currency,
    })
    hist = hist[-MAX_RECORDS:]
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=2)
    return hist


def consumption_between(hist: list, start_ts: float,
                        end_ts: float = None) -> float:
    """[start_ts, end_ts) 区间内的累计消耗（仅累计余额下降部分）。

    start_ts 之前最后一个快照作为比较基准，保证跨区间边界的下降不重复计数。
    end_ts 默认为当前时间。区间内不足两条记录时返回 0.0。
    """
    end_ts = time.time() if end_ts is None else end_ts
    if len(hist) < 2:
        return 0.0
    consumed = 0.0
    prev = None
    for rec in hist:
        if rec["ts"] < start_ts:
            prev = rec["balance"]      # 区间前基准点
            continue
        if rec["ts"] >= end_ts:
            break
        if prev is not None:
            delta = prev - rec["balance"]
            if delta > 0:
                consumed += delta
        prev = rec["balance"]
    return consumed


def consumption_since_start(hist: list) -> float:
    """本地追踪起的累计消耗（仅累计余额下降部分）。"""
    return consumption_between(hist, 0.0)
