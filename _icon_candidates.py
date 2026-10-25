# -*- coding: utf-8 -*-
"""App icon 候选稿渲染（4 个方向，超采样 2048 → 各尺寸）。

跑法: build-venv/Scripts/python.exe _icon_candidates.py
产出: _icon_candidates.png（浅/深任务栏实际尺寸 + 16px 放大 6 倍检视）
"""
from PIL import Image, ImageDraw, ImageFont

MASTER = 2048
FONT_B = "C:/Windows/Fonts/arialbd.ttf"


def _font(px):
    return ImageFont.truetype(FONT_B, px)


def _squircle_mask(size, radius_ratio=0.224):
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=int(size * radius_ratio), fill=255)
    return m


def _vgrad(size, top, bot):
    """竖向渐变（top→bot，RGB 元组）。"""
    g = Image.new("RGB", (1, size))
    for y in range(size):
        t = y / (size - 1)
        g.putpixel((0, y), tuple(round(top[i] + (bot[i] - top[i]) * t)
                                 for i in range(3)))
    return g.resize((size, size)).convert("RGBA")


def _canvas(bg_top, bg_bot, radius_ratio=0.224):
    base = _vgrad(MASTER, bg_top, bg_bot)
    base.putalpha(_squircle_mask(MASTER, radius_ratio))
    # 顶部受光：一层向下衰减的白色
    gloss = Image.new("L", (MASTER, MASTER), 0)
    gd = ImageDraw.Draw(gloss)
    for y in range(int(MASTER * 0.52)):
        a = int(58 * (1 - y / (MASTER * 0.52)) ** 1.6)
        gd.line([(0, y), (MASTER, y)], fill=a)
    white = Image.new("RGBA", (MASTER, MASTER), (255, 255, 255, 255))
    base = Image.composite(white, base, Image.composite(
        gloss, Image.new("L", (MASTER, MASTER), 0), base.getchannel("A")))
    return base


def _center_text(img, text, font, dy=0, fill=(255, 255, 255, 255)):
    d = ImageDraw.Draw(img)
    box = d.textbbox((0, 0), text, font=font)
    w, h = box[2] - box[0], box[3] - box[1]
    d.text(((MASTER - w) / 2 - box[0], (MASTER - h) / 2 - box[1] + dy),
           text, font=font, fill=fill)


# ---------------------------------------------------------------- 候选 A
def icon_a():
    """余额徽章：DeepSeek 蓝渐变圆角方 + 白色 ¥。"""
    img = _canvas((108, 134, 255), (39, 67, 200))
    f = _font(int(MASTER * 0.60))
    _center_text(img, "¥", f, dy=-int(MASTER * 0.02))
    return img


# ---------------------------------------------------------------- 候选 B
def icon_b():
    """水位表：深蓝底 + 270° 圆环水位 + 指针。"""
    img = _canvas((32, 45, 74), (10, 17, 30))
    d = ImageDraw.Draw(img)
    cx, cy, r = MASTER / 2, MASTER * 0.545, MASTER * 0.315
    lw = int(MASTER * 0.088)
    d.arc([cx - r, cy - r, cx + r, cy + r], 140, 400, fill=(255, 255, 255, 46),
          width=lw)
    d.arc([cx - r, cy - r, cx + r, cy + r], 140, 268, fill=(93, 157, 255, 255),
          width=lw)
    # 指针
    import math
    ang = math.radians(268 - 8)
    nx, ny = cx + math.cos(ang) * r * 0.80, cy + math.sin(ang) * r * 0.80
    d.line([cx, cy, nx, ny], fill=(255, 255, 255, 255), width=int(MASTER * 0.036))
    rr = int(MASTER * 0.030)
    d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(255, 255, 255, 255))
    return img


# ---------------------------------------------------------------- 候选 C
def icon_c():
    """硬币：深色底 + 带厚度的白色硬币（¥ 镂空）。"""
    img = _canvas((28, 33, 44), (13, 16, 23))
    d = ImageDraw.Draw(img)
    cx, cy = MASTER / 2, MASTER * 0.475
    r = int(MASTER * 0.275)
    th = int(MASTER * 0.075)          # 硬币厚度
    # 侧面（厚度）
    d.rounded_rectangle([cx - r, cy, cx + r, cy + th + r * 0.55],
                        radius=r, fill=(178, 192, 214, 255))
    d.ellipse([cx - r, cy - r + th, cx + r, cy + r + th],
              fill=(178, 192, 214, 255))
    # 顶面
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255, 255))
    # 内圈刻痕
    ins = int(MASTER * 0.045)
    d.ellipse([cx - r + ins, cy - r + ins, cx + r - ins, cy + r - ins],
              outline=(206, 214, 228, 255), width=int(MASTER * 0.012))
    f = _font(int(MASTER * 0.30))
    dd = ImageDraw.Draw(img)
    box = dd.textbbox((0, 0), "¥", font=f)
    dd.text((cx - (box[2] - box[0]) / 2 - box[0],
             cy - (box[3] - box[1]) / 2 - box[1]),
            "¥", font=f, fill=(24, 31, 48, 255))
    return img


# ---------------------------------------------------------------- 候选 D
def icon_d():
    """DS 字标：蓝渐变圆角方 + 紧凑 DS（S 略降透明度做层次）。"""
    img = _canvas((96, 120, 250), (44, 66, 190))
    f = _font(int(MASTER * 0.50))
    d = ImageDraw.Draw(img)
    box = d.textbbox((0, 0), "DS", font=f)
    w, h = box[2] - box[0], box[3] - box[1]
    d.text(((MASTER - w) / 2 - box[0], (MASTER - h) / 2 - box[1]),
           "DS", font=f, fill=(255, 255, 255, 255))
    return img


# ---------------------------------------------------------------- 候选 E
def icon_e():
    """深色玻璃卡：迷你卡同色 #1C1D22 + 蓝色发光 ¥。"""
    img = _canvas((38, 41, 52), (16, 17, 22))
    glow = Image.new("RGBA", (MASTER, MASTER), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    cx = cy = MASTER / 2
    for i in range(28, 0, -1):
        rr = int(MASTER * 0.10 + i * MASTER * 0.011)
        a = int(3.2 * i)
        gd.ellipse([cx - rr, cy - rr, cx + rr, cy + rr],
                   fill=(77, 159, 255, min(a, 78)))
    glow.putalpha(Image.composite(glow.getchannel("A"),
                                  Image.new("L", (MASTER, MASTER), 0),
                                  img.getchannel("A")))
    img = Image.alpha_composite(img, glow)
    f = _font(int(MASTER * 0.58))
    _center_text(img, "¥", f, dy=-int(MASTER * 0.02),
                 fill=(190, 219, 255, 255))
    return img


CANDS = [("A 余额徽章", icon_a), ("B 水位表", icon_b),
         ("C 硬币", icon_c), ("D DS 字标", icon_d),
         ("E 深色玻璃卡", icon_e)]

SIZES = (256, 48, 32, 24, 16)


def main():
    master = {name: fn() for name, fn in CANDS}
    col_w, left = 270, 18
    W = left + col_w * len(CANDS)
    H = 660
    sheet = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    ft = ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc", 22)
    fs = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 14)

    for i, (name, _fn) in enumerate(CANDS):
        x0 = left + i * col_w
        d.text((x0, 10), name, font=ft, fill=(20, 20, 24))
        big = master[name].resize((192, 192), Image.LANCZOS)
        sheet.paste(big, (x0, 44), big)

        # 浅色 / 深色任务栏上的实际尺寸
        for row, (bg, label) in enumerate(
                [((246, 247, 249), "浅色任务栏"), ((28, 29, 34), "深色任务栏")]):
            y = 258 + row * 92
            d.text((x0, y - 19), label, font=fs,
                   fill=(110, 114, 122) if row == 0 else (120, 124, 134))
            d.rectangle([x0, y, x0 + 236, y + 62], fill=bg)
            cx = x0 + 14
            for s in (48, 32, 24, 16):
                ic = master[name].resize((s, s), Image.LANCZOS)
                sheet.paste(ic, (cx, y + 31 - s // 2), ic)
                cx += s + 12

        # 小尺寸放大检视（最近邻）
        y = 452
        d.text((x0, y), "16px ×6（放大看轮廓）", font=fs, fill=(20, 20, 24))
        z = master[name].resize((16, 16), Image.LANCZOS).resize(
            (96, 96), Image.NEAREST)
        sheet.paste(z, (x0, y + 22))
        d.text((x0, y + 128), "32px ×3", font=fs, fill=(20, 20, 24))
        z2 = master[name].resize((32, 32), Image.LANCZOS).resize(
            (96, 96), Image.NEAREST)
        sheet.paste(z2, (x0, y + 150))

    sheet.save("_icon_candidates.png")
    for name, img in master.items():
        img.resize((256, 256), Image.LANCZOS).save(
            "_icon_draft_%s.png" % name[0].lower())
    print("saved _icon_candidates.png", sheet.size)


if __name__ == "__main__":
    main()
