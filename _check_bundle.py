# -*- coding: utf-8 -*-
"""检查 dist 里的单文件 exe 是否真的打进了指定模块（无需启动 GUI）。

用法：
    build-venv/Scripts/python.exe _check_bundle.py netmon ui tray

为什么需要它：打包产物是源码的**快照**，改了 .py 不重打包，
运行时仍是旧行为（表现为"新功能就是没有"）。此脚本给出客观证据：
模块在不在包里、包的构建时间是否晚于源码。
"""

import os
import sys
import tempfile
from datetime import datetime

from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader

HERE = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(HERE, "dist", "DeepSeekBalanceViewer.exe")
SOURCES = ["main.py", "ui.py", "api.py", "config.py", "history.py",
           "netmon.py", "pricing.py", "tray.py", "glass.py"]


def bundled_names(exe: str) -> set:
    """读出单文件 exe 内 PYZ 里的顶层模块名集合。"""
    reader = CArchiveReader(exe)
    pyz_names = [t for t in reader.toc if "PYZ" in t.upper()]
    if not pyz_names:
        raise RuntimeError("exe 内未找到 PYZ 归档，可能不是 PyInstaller onefile 产物")
    tmp = os.path.join(tempfile.gettempdir(), "_bundle_probe.pyz")
    with open(tmp, "wb") as f:
        f.write(reader.extract(pyz_names[0]))
    try:
        names = set(ZlibArchiveReader(tmp).toc.keys())
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return {n.split(".")[0] for n in names}


def main() -> int:
    wanted = sys.argv[1:] or ["netmon"]
    if not os.path.exists(EXE):
        print("EXE_NOT_FOUND:", EXE)
        return 2

    exe_mtime = os.path.getmtime(EXE)
    print("exe : %s" % EXE)
    print("      size %.1f MB   built %s"
          % (os.path.getsize(EXE) / 1024 / 1024,
             datetime.fromtimestamp(exe_mtime).strftime("%Y-%m-%d %H:%M:%S")))

    newest_src, newest_name = 0.0, ""
    for name in SOURCES:
        p = os.path.join(HERE, name)
        if os.path.exists(p):
            m = os.path.getmtime(p)
            if m > newest_src:
                newest_src, newest_name = m, name
    print("src : newest is %s at %s"
          % (newest_name, datetime.fromtimestamp(newest_src).strftime("%Y-%m-%d %H:%M:%S")))

    stale = newest_src > exe_mtime + 1
    print("STALENESS: %s" % ("*** STALE — 源码比 exe 新，必须重新打包 ***"
                             if stale else "OK — exe 不晚于最新源码"))

    names = bundled_names(EXE)
    print("PYZ modules: %d" % len(names))
    ok = True
    for w in wanted:
        hit = w in names
        ok = ok and hit
        print("  %-10s %s" % (w, "BUNDLED ✅" if hit else "MISSING ❌"))

    if stale:
        print("RESULT: FAIL (源码已改但未重打包，用户看到的仍是旧行为)")
        return 1
    if not ok:
        print("RESULT: FAIL (目标模块未打进包)")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
