# -*- coding: utf-8 -*-
"""最小复现：overrideredirect Toplevel + apply_layered_bitmap 是否稳定。"""
import os, sys, traceback
os.environ.setdefault("DSBV_CONFIG",
                      os.path.join(os.environ.get("TEMP", "/tmp"),
                                   "dsbv_repro_%d" % os.getpid()))
import tkinter as tk
import glass
from PIL import Image, ImageDraw

log = []
def L(*a):
    s = " ".join(str(x) for x in a)
    log.append(s)
    print(s, flush=True)

root = tk.Tk()
root.withdraw()
t = tk.Toplevel(root)
t.overrideredirect(True)
t.wm_attributes("-topmost", True)
t.geometry("420x240+300+200")
t.update()
L("toplevel created, winfo_id", t.winfo_id())

img = Image.new("RGBA", (440, 260), (0, 0, 0, 0))
ImageDraw.Draw(img).rounded_rectangle([10, 10, 429, 249], radius=20,
                                      fill=(40, 44, 52, 255))
L("calling apply_layered_bitmap ...")
try:
    ok = glass.apply_layered_bitmap(t, img)
    L("apply_layered_bitmap returned", ok)
except Exception:
    L("EXC in apply_layered_bitmap:\n" + traceback.format_exc())

def tick(n):
    if n <= 0:
        L("still alive after 3s, exists=%s" % t.winfo_exists())
        try:
            root.quit()
        except Exception:
            pass
        return
    L("tick %d alive, exists=%s" % (4 - n, t.winfo_exists()))
    root.after(1000, tick, n - 1)

root.after(1000, tick, 3)
try:
    root.mainloop()
except Exception:
    L("EXC in mainloop:\n" + traceback.format_exc())
L("END no crash")
with open(os.path.join(os.environ["TEMP"], "dsbv_repro.log"), "w") as f:
    f.write("\n".join(log))
