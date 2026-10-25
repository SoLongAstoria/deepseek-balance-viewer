# -*- coding: utf-8 -*-
"""App icon 绘制（唯一来源）。

同一份代码服务三处，保证视觉一致：
  1. exe 图标 —— `_make_ico.py` 生成 `app_icon.ico`（多尺寸，每档独立出图）
  2. 托盘图标 —— `tray.make_icon()` 调 `render()`
  3. 主窗标题栏/任务栏 —— `ui` 用 `render(64)` 转 PhotoImage

设计：深蓝渐变圆角方 + 270° 水位环（缺口朝下）+ 亮蓝进度 + 白色指针。
**光学尺寸（optical size）**：≤24px 自动省略指针（16px 下指针会和环糊成一团，
实测；小尺寸只保留环，形状同族且清晰），≥32px 才是完整的水位表。

依赖：仅 Pillow。缺 Pillow 时 `render()` 返回 None，调用方跳过图标即可。
"""
import math
import struct

try:
    from PIL import Image, ImageDraw
    AVAILABLE = True
except Exception:                                  # pragma: no cover
    Image = ImageDraw = None
    AVAILABLE = False

M = 2048                                    # 母版边长（超采样）
BG_TOP = (44, 58, 92)
BG_BOT = (11, 18, 31)
BLUE = (95, 168, 255, 255)                  # 进度环（与深色主题强调蓝同族）
WHITE = (255, 255, 255, 255)
START, SWEEP = 135, 270                     # 缺口朝下的 270° 水位环
RING_R = 0.295                              # 环中线半径 / 母版边长
RING_W = 0.118                              # 环宽 / 母版边长
PROGRESS = 0.70                             # 水位（纯装饰，不随真实余额变化）
SMALL_CUT = 28                              # < 28px 用简化版（无指针）

_MASTER = {}
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def _squircle_mask(size, radius_ratio=0.224):
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=int(size * radius_ratio), fill=255)
    return mask


def _plate():
    """深蓝竖向渐变 + 顶部受光 + squircle 圆角。"""
    grad = Image.new("RGB", (1, M))
    for y in range(M):
        t = y / (M - 1)
        grad.putpixel((0, y), tuple(
            round(BG_TOP[i] + (BG_BOT[i] - BG_TOP[i]) * t) for i in range(3)))
    img = grad.resize((M, M)).convert("RGBA")
    img.putalpha(_squircle_mask(M))

    gloss = Image.new("L", (M, M), 0)
    gd = ImageDraw.Draw(gloss)
    hh = int(M * 0.50)
    for y in range(hh):
        gd.line([(0, y), (M, y)], fill=int(46 * (1 - y / hh) ** 1.7))
    white = Image.new("RGBA", (M, M), WHITE)
    return Image.composite(
        white, img,
        Image.composite(gloss, Image.new("L", (M, M), 0), img.getchannel("A")))


def _draw(style="full"):
    """在 2048 母版上绘制。style: full / plain / thumb / mark / needle。"""
    img = _plate()
    d = ImageDraw.Draw(img)
    cx, cy = M / 2, M * 0.515
    r = M * RING_R
    lw = int(M * RING_W)
    box = [cx - r, cy - r, cx + r, cy + r]

    # 轨道（淡白）→ 进度（亮蓝）
    d.arc(box, START, START + SWEEP, fill=(255, 255, 255, 26), width=lw)
    end = START + SWEEP * PROGRESS
    d.arc(box, START, end, fill=BLUE, width=lw)

    if style == "needle":
        a = math.radians(end - 10)
        d.line([cx, cy, cx + math.cos(a) * r * 0.80,
                cy + math.sin(a) * r * 0.80],
               fill=WHITE, width=int(M * 0.044))
        hr = int(M * 0.048)
        d.ellipse([cx - hr, cy - hr, cx + hr, cy + hr], fill=WHITE)
    elif style == "thumb":
        # 进度终点一颗"水位珠"（给蓝弧收一个圆头，像滑杆把手）
        a = math.radians(end)
        px, py = cx + math.cos(a) * r, cy + math.sin(a) * r
        dr = lw * 0.52
        d.ellipse([px - dr, py - dr, px + dr, py + dr], fill=BLUE)
    elif style == "mark":
        a = math.radians(end)
        r_out, r_in = r + lw * 0.30, r - lw * 0.30
        d.line([cx + math.cos(a) * r_out, cy + math.sin(a) * r_out,
                cx + math.cos(a) * r_in, cy + math.sin(a) * r_in],
               fill=WHITE, width=int(M * 0.030))
    # style == "plain"：只有环
    return img


def _norm(style, size):
    if style == "auto":
        return "needle" if size >= SMALL_CUT else "plain"
    return "needle" if style == "full" else style


def render(size=256, style="auto"):
    """返回 size×size 的 RGBA 图标；无 Pillow 时返回 None。"""
    if not AVAILABLE:
        return None
    size = int(size)
    st = _norm(style, size)
    if st not in _MASTER:
        _MASTER[st] = _draw(st)
    return _MASTER[st].resize((size, size), Image.LANCZOS)


def save_ico(path, sizes=ICO_SIZES, style="auto"):
    """写多尺寸 .ico —— **每档单独出图**（16/24 无指针、32+ 完整版）。

    PIL 自带的 ICO 写入会把同一张图缩成多档（append_images 在 ICO 上无效），
    拿不到光学尺寸，所以这里按 ICO 规范手写：头部 + 每档一张 PNG（Vista+ 支持）。
    """
    if not AVAILABLE:
        return False
    blobs = []
    for s in sorted(sizes):
        import io
        buf = io.BytesIO()
        render(s, style).save(buf, format="PNG", optimize=True)
        blobs.append((s, buf.getvalue()))

    header = struct.pack("<HHH", 0, 1, len(blobs))
    offset = 6 + 16 * len(blobs)
    entries, body = b"", b""
    for s, png in blobs:
        dim = 0 if s >= 256 else s          # 256 在目录里记 0
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32,
                               len(png), offset)
        offset += len(png)
        body += png
    with open(path, "wb") as f:
        f.write(header + entries + body)
    return True


def save_png(path, size=256, style="auto"):
    if not AVAILABLE:
        return False
    render(size, style).save(path)
    return True


if __name__ == "__main__":
    from PIL import ImageFont
    styles = [("auto 自动（默认）", "auto"), ("plain 纯净环", "plain"),
              ("thumb 水位珠", "thumb"), ("needle 指针", "needle")]
    W, H = 1290, 470
    sheet = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    ft = ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc", 21)
    fs = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 14)
    for i, (label, st) in enumerate(styles):
        x0 = 18 + i * 320
        d.text((x0, 8), label, font=ft, fill=(20, 20, 24))
        big = render(200, st)
        sheet.paste(big, (x0, 44), big)
        for row, (bg, tag) in enumerate([((246, 247, 249), "浅色"),
                                         ((28, 29, 34), "深色")]):
            y = 264 + row * 88
            d.text((x0, y - 19), tag + "任务栏", font=fs,
                   fill=(110, 114, 122) if row == 0 else (120, 124, 134))
            d.rectangle([x0, y, x0 + 286, y + 60], fill=bg)
            cx = x0 + 14
            for s in (48, 32, 24, 16):
                sheet.paste(render(s, st), (cx, y + 30 - s // 2))
                cx += s + 12
        y = 446
        d.text((x0, y), "16px ×6", font=fs, fill=(20, 20, 24))
        sheet.paste(render(16, st).resize((96, 96), Image.NEAREST),
                    (x0, y + 18))
        d.text((x0 + 110, y), "32px ×3", font=fs, fill=(20, 20, 24))
        sheet.paste(render(32, st).resize((96, 96), Image.NEAREST),
                    (x0 + 110, y + 18))
    sheet.save("_icon_preview.png")
    print("saved _icon_preview.png", sheet.size)
