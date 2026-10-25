# -*- coding: utf-8 -*-
"""对截图做 WCAG 对比度审计 —— 把「看不清」变成可量化、可回归的指标。

背景（2026-10-25）：用户真机截图反馈「完全看不清」。复盘发现两个真实缺陷，
都无法靠肉眼看自己生成的截图发现（截图工具会用回退色掩盖问题）：

  1. Canvas 底色硬编码 #000000  → 标题栏 / 状态栏文字是深色画在黑底上；
  2. 真 acrylic(BLURBEHIND) 让 DWM 重新合成整块客户区 → GDI 文字被一起模糊。

所以这里做两件事：
  - **文字对比度**：区域内「众数色(底色)」vs「最极端 0.4% 像素(文字笔画)」
    的 WCAG 对比度，低于阈值即判失败；
  - **锐度**：拉普拉斯方差，糊掉的字方差会显著偏低。

用法：
    python _audit_contrast.py _ui_real_light.png light
    python _audit_contrast.py _ui_real_dark.png dark
退出码 0 = 全部达标。
"""

import sys

# 审计区域（设计稿 CSS px，相对内容区左上角）。只挑**文字密集**的小块，
# 避免图表曲线、彩色进度条这类天然极值色污染统计。
ZONES = {
    "标题栏文字":   (26, 6, 320, 30),
    "余额大字":     (30, 55, 200, 110),
    "明细行":       (30, 115, 200, 145),
    "价格表数值":   (390, 240, 520, 268),
    "价格表模型名": (30, 240, 200, 268),
    "设置区文字":   (30, 505, 300, 560),
    "状态栏文字":   (6, 658, 380, 675),
}

MIN_RATIO = 4.5     # WCAG AA 正文
MIN_SHARPNESS = 12  # 拉普拉斯方差下限（经验值，糊字通常 < 6）


def _lum(c):
    """WCAG 相对亮度。"""
    def f(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = c
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _ratio(c1, c2):
    l1, l2 = _lum(c1), _lum(c2)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


def _sharpness(gray):
    """拉普拉斯方差（无 numpy，用 PIL 卷积近似）。"""
    from PIL import ImageFilter, ImageStat
    return ImageStat.Stat(gray.filter(ImageFilter.FIND_EDGES)).var[0]


def audit(png_path, theme, win_w=560, win_h=676):
    from PIL import Image

    im = Image.open(png_path).convert("RGB")
    W, H = im.size
    # 截图含原生标题栏与边框：内容区宽 = win_w*S，底部对齐，左右居中
    S = round((W - 18) / win_w, 4) if W > win_w else 1.0
    if abs(S - round(S * 4) / 4) > 0.02:
        S = 1.25 if W / win_w > 1.1 else 1.0
    x_off = (W - int(win_w * S)) // 2
    y_off = H - int(win_h * S)

    print(f"\n=== 对比度审计  {png_path}  主题={theme}  "
          f"图={W}x{H}  内容缩放={S}  原点=({x_off},{y_off}) ===")
    print(f"{'区域':<14}{'底色':<10}{'文字色':<10}{'对比度':>8}  判定")

    fails = []
    for name, (x0, y0, x1, y1) in ZONES.items():
        box = (x_off + int(x0 * S), y_off + int(y0 * S),
               x_off + int(x1 * S), y_off + int(y1 * S))
        box = (max(0, box[0]), max(0, box[1]),
               min(W, box[2]), min(H, box[3]))
        if box[2] <= box[0] or box[3] <= box[1]:
            print(f"{name:<14}{'区域越界，跳过':<30}")
            continue
        crop = im.crop(box)
        colors = crop.getcolors(maxcolors=1 << 20) or []
        if not colors:
            continue
        base = max(colors, key=lambda t: t[0])[1]      # 众数 = 底色
        lum_base = _lum(base)
        # 与底色亮度差最大的 0.4% 像素 ≈ 文字笔画（排除抗锯齿过渡）
        px = list(crop.getdata())
        px.sort(key=lambda c: -abs(_lum(c) - lum_base))
        k = max(1, len(px) // 250)
        ink = px[:k]
        ink_c = tuple(round(sum(p[i] for p in ink) / len(ink)) for i in range(3))
        r = _ratio(base, ink_c)
        ok = r >= MIN_RATIO
        if not ok:
            fails.append((name, r))
        hx = lambda c: "#%02X%02X%02X" % c
        print(f"{name:<14}{hx(base):<10}{hx(ink_c):<10}{r:>8.2f}  "
              f"{'OK' if ok else '!! 偏低'}")

    gray = im.convert("L")
    sharp_full = _sharpness(gray)
    print(f"\n全图锐度（拉普拉斯方差）= {sharp_full:.1f}   "
          f"{'OK' if sharp_full >= MIN_SHARPNESS else '!! 偏糊'}")

    bad = []
    if fails:
        bad.append("对比度不足：" + "、".join(f"{n}({r:.2f})" for n, r in fails))
    if sharp_full < MIN_SHARPNESS:
        bad.append(f"文字模糊(锐度 {sharp_full:.1f} < {MIN_SHARPNESS})")
    if bad:
        print("RESULT: FAIL —— " + "；".join(bad))
        return 1
    print(f"RESULT: PASS —— 全部区域对比度 ≥ {MIN_RATIO}:1，文字锐度达标")
    return 0


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    png = sys.argv[1]
    theme = sys.argv[2] if len(sys.argv) > 2 else "light"
    return audit(png, theme)


if __name__ == "__main__":
    sys.exit(main())
