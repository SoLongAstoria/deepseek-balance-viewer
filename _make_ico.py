# -*- coding: utf-8 -*-
"""生成 app 图标文件（exe / 高分辨率预览用）。

跑法: build-venv/Scripts/python.exe _make_ico.py
产出:
  app_icon.ico   多尺寸（16/24/32/48/64/128/256），打包时 --icon 用它
  app_icon.png   256px 预览（README / 商店素材可用）

图标图形本身在 `icon_art.py`（运行时托盘/窗口图标也用同一份代码），
这里只是把图形落成文件，不改设计。
"""
import sys

import icon_art


def main():
    if not icon_art.AVAILABLE:
        print("缺少 Pillow，无法生成图标（先 pip install pillow）")
        return 1
    ok1 = icon_art.save_ico("app_icon.ico")
    ok2 = icon_art.save_png("app_icon.png", 256)
    print("app_icon.ico", "OK" if ok1 else "FAIL",
          "| app_icon.png", "OK" if ok2 else "FAIL")
    # 逐档读回校验（手写 ICO 结构，坏了要当场发现）
    import io
    import struct

    from PIL import Image
    raw = open("app_icon.ico", "rb").read()
    _, typ, cnt = struct.unpack("<HHH", raw[:6])
    assert typ == 1 and cnt == len(icon_art.ICO_SIZES), f"ICO 目录异常 {typ}/{cnt}"
    off = 6
    for s in sorted(icon_art.ICO_SIZES):
        w, h, _c, _r, _p, bpp, sz, o = struct.unpack("<BBBBHHII",
                                                     raw[off:off + 16])
        off += 16
        assert (w or 256) == s and (h or 256) == s and bpp == 32
        assert Image.open(io.BytesIO(raw[o:o + sz])).size == (s, s)
    print(f"ICO 校验通过：{cnt} 档，" + "/".join(
        str(s) for s in sorted(icon_art.ICO_SIZES)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
