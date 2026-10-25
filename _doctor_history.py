# -*- coding: utf-8 -*-
"""history.json 体检 / 修复工具。

用途：本地余额快照被写脏（例如测试脚本注入了样例余额）时，
找出可疑记录并清理掉，再给出修正后的「今日 / 本月 / 累计」消耗。

跑法（默认只报告，不改文件）：
    build-venv/Scripts/python.exe _doctor_history.py
    build-venv/Scripts/python.exe _doctor_history.py --drop 12.34 --apply

判定「交替污染」：同一个余额值反复出现、且每次都夹在一个固定值之间
（A,B,A,B...）—— 正常使用中余额只会单调下降（充值时跳升一次），
不会来回震荡，来回震荡基本都是测试数据混入。
"""
import argparse
import os
import shutil
import time
from collections import Counter
from datetime import datetime

import history as H


def load():
    return H.load_history()


def windows(hist):
    now = datetime.now()
    t0 = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    m0 = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp()
    return {
        "今日": H.consumption_between(hist, t0),
        "本月": H.consumption_between(hist, m0),
        "累计": H.consumption_since_start(hist),
    }


def alternation_candidates(hist):
    """找出"来回震荡"的值：在相邻记录里 A,B,A,B... 交替且出现 ≥3 次。"""
    if len(hist) < 5:
        return []
    vals = [round(float(r["balance"]), 2) for r in hist]
    cnt = Counter(vals)
    suspects = []
    for v, n in cnt.items():
        if n < 3:
            continue
        # 该值的相邻两次出现之间，是否总是夹着同一个不同的值
        idx = [i for i, x in enumerate(vals) if x == v]
        between = {vals[i + 1] for i in idx[:-1]
                   if i + 1 < len(vals) and vals[i + 1] != v}
        if len(between) == 1:
            suspects.append((v, n, between.pop()))
    return suspects


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drop", type=float, action="append", default=[],
                    metavar="VALUE", help="删除该余额值的所有记录（可多次指定）")
    ap.add_argument("--apply", action="store_true", help="真正写入（默认只预览）")
    args = ap.parse_args()

    hist = load()
    path = H.HISTORY_PATH
    print(f"文件: {path}")
    print(f"记录: {len(hist)} 条  "
          f"{datetime.fromtimestamp(hist[0]['ts']):%Y-%m-%d %H:%M} ~ "
          f"{datetime.fromtimestamp(hist[-1]['ts']):%Y-%m-%d %H:%M}"
          if hist else "（空）")
    if not hist:
        return 0

    before = windows(hist)
    print("当前统计: " + "  ".join(f"{k} ¥{v:,.2f}" for k, v in before.items()))

    sus = alternation_candidates(hist)
    if sus:
        print("\n⚠ 可疑：以下余额值在记录里来回震荡（正常只会单调下降 / 充值跳升一次）")
        for v, n, other in sorted(sus, key=lambda x: -x[1]):
            print(f"   ¥{v:,.2f} 出现 {n} 次，且总与 ¥{other:,.2f} 交替"
                  f"  →  疑似测试数据混入")
    else:
        print("\n未发现交替震荡的可疑记录。")

    drop = {round(v, 2) for v in args.drop}
    if not drop:
        if sus:
            print("\n如需清理，用：--drop <值> [--drop <值>] --apply")
        return 0

    keep = [r for r in hist if round(float(r["balance"]), 2) not in drop]
    removed = len(hist) - len(keep)
    after = windows(keep)
    print(f"\n将删除 {removed} 条（余额 ∈ "
          + ", ".join(f"¥{v:,.2f}" for v in sorted(drop)) + "）")
    print("修正后: " + "  ".join(f"{k} ¥{v:,.2f}" for k, v in after.items()))

    if not args.apply:
        print("\n（预览模式，未写入。确认无误后加 --apply）")
        return 0
    if removed == 0:
        print("没有可删除的记录，未改动文件。")
        return 0

    backup = f"{path}.bak-{datetime.now():%Y%m%d-%H%M%S}"
    shutil.copyfile(path, backup)
    import json
    with open(path, "w", encoding="utf-8") as f:
        json.dump(keep, f, ensure_ascii=False, indent=2)
    print(f"\n已写入 {path}（备份: {os.path.basename(backup)}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
