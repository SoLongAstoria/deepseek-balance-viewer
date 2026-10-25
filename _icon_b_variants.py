# -*- coding: utf-8 -*-
"""B 方向（水位表）三个改良版：解决 16px 糊成一团的问题。

B1 纯净进度环（无指针，环尾一个亮白圆点）
B2 加粗指针版（轨道加深、指针加粗、中心轴实心）
B3 环 + 中心 ¥（无指针，兼顾"余额"语义）

跑法: build-venv/Scripts/python.exe _icon_b_variants.py
产出: _icon_b_variants.png
"""
import math

from PIL import Image, ImageDraw, ImageFont

M = 2048                                  # 母版边长（超采样）
FONT_B = "C:/Windows/Fonts/arialbd.ttf"

BG_TOP = (40, 53, 84)
BG_BOT = (11, 18, 31)
BLUE = (77, 159, 255, 255)                # App 强调蓝（深色主题同款）
WHITE = (255, 255, 255, 255)


def squircle(size, radius_ratio=0.224):
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=int(size * radius_ratio), fill=255)
    return mask


def vgrad(size, top, bot):
    g = Image.new("RGB", (1, size))
    for y in range(size):
        t = y / (size - 1)
        g.putpixel((0, y), tuple(round(top[i] + (bot[i] - top[i]) * t)
                                 for i in range(3)))
    return g.resize((size, size)).convert("RGBA")


def base_plate():
    img = vgrad(M, BG_TOP, BG_BOT)
    img.putalpha(squircle(M))
    # 顶部受光
    gloss = Image.new("L", (M, M), 0)
    gd = ImageDraw.Draw(gloss)
    hh = int(M * 0.50)
    for y in range(hh):
        gd.line([(0, y), (M, y)], fill=int(52 * (1 - y / hh) ** 1.7))
    white = Image.new("RGBA", (M, M), (255, 255, 255, 255))
    img = Image.composite(white, img,
                          Image.composite(gloss, Image.new("L", (M, M), 0),
                                          img.getchannel("A")))
    return img


def ring(img, start, end, color, width, r=None, cx=None, cy=None):
    cx = M / 2 if cx is None else cx
    cy = M * 0.515 if cy is None else cy
    r = M * 0.285 if r is None else r
    ImageDraw.Draw(img).arc([cx - r, cy - r, cx + r, cy + r],
                            start, end, fill=color, width=width)
    return (cx, cy, r)


def icon_b1():
    """B1：纯净进度环 —— 环尾一个亮白圆点，无指针。"""
    img = base_plate()
    lw = int(M * 0.105)
    cx, cy, r = ring(img, 135, 405, (255, 255, 255, 34), lw)
    end = 135 + 270 * 0.66
    ring(img, 135, end, BLUE, lw)
    a = math.radians(end)
    px, py = cx + math.cos(a) * r, cy + math.sin(a) * r
    dr = lw * 0.62
    ImageDraw.Draw(img).ellipse([px - dr, py - dr, px + dr, py + dr],
                                fill=WHITE)
    return img


def icon_b2():
    """B2：加粗指针版 —— 轨道加深、指针/轴心都加粗，小尺寸也立得住。"""
    img = base_plate()
    lw = int(M * 0.105)
    cx, cy, r = ring(img, 135, 405, (255, 255, 255, 52), lw)
    ring(img, 135, 135 + 270 * 0.62, BLUE, lw)
    d = ImageDraw.Draw(img)
    ang = math.radians(135 + 270 * 0.62 - 12)
    nx, ny = cx + math.cos(ang) * r * 0.76, cy + math.sin(ang) * r * 0.76
    d.line([cx, cy, nx, ny], fill=WHITE, width=int(M * 0.052))
    hr = int(M * 0.058)
    d.ellipse([cx - hr, cy - hr, cx + hr, cy + hr], fill=WHITE)
    return img


def icon_b3():
    """B3：环 + 中心 ¥（无指针，语义最直白）。"""
    img = base_plate()
    lw = int(M * 0.098)
    cx, cy, r = ring(img, 135, 405, (255, 255, 255, 40), lw)
    ring(img, 135, 135 + 270 * 0.72, BLUE, lw)
    f = ImageFont.truetype(FONT_B, int(M * 0.245))
    d = ImageDraw.Draw(img)
    box = d.textbbox((0, 0), "¥", font=f)
    w, h = box[2] - box[0], box[3] - box[1]
    d.text((cx - w / 2 - box[0], cy - h / 2 - box[1]), "¥", font=f,
           fill=WHITE)
    return img


CANDS = [("B1 纯净进度环", icon_b1), ("B2 加粗指针", icon_b2),
         ("B3 环+¥", icon_b3)]
SIZES = (48, 32, 24, 16)


def main():
    master = {n: f() for n, f in CANDS}
    col_w, left, H = 300, 18, 560
    W = left + col_w * len(CANDS)
    sheet = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    ft = ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc", 22)
    fs = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 14)

    for i, (name, _f) in enumerate(CANDS):
        x0 = left + i * col_w
        d.text((x0, 10), name, font=ft, fill=(20, 20, 24))
        big = master[name].resize((200, 200), Image.LANCZOS)
        sheet.paste(big, (x0, 46), big)
        for row, (bg, label) in enumerate(
                [((246, 247, 249), "浅色任务栏"), ((28, 29, 34), "深色任务栏")]):
            y = 266 + row * 92
            d.text((x0, y - 19), label, font=fs,
                   fill=(110, 114, 122) if row == 0 else (120, 124, 134))
            d.rectangle([x0, y, x0 + 266, y + 62], fill=bg)
            cx = x0 + 14
            for s in SIZES:
                ic = master[name].resize((s, s), Image.LANCZOS)
                sheet.paste(ic, (cx, y + 31 - s // 2), ic)
                cx += s + 12
        y = 460
        d.text((x0, y), "16px ×6", font=fs, fill=(20, 20, 24))
        sheet.paste(master[name].resize((16, 16), Image.LANCZOS).resize(
            (96, 96), Image.NEAREST), (x0, y + 20))
        d.text((x0 + 110, y), "32px ×3", font=fs, fill=(20, 20, 24))
        sheet.paste(master[name].resize((32, 32), Image.LANCZOS).resize(
            (96, 96), Image.NEAREST), (x0 + 110, y + 20))
    sheet.save("_icon_b_variants.png")
    print("saved", sheet.size)


if __name__ == "__main__":
    main()
