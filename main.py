# -*- coding: utf-8 -*-
"""入口：启动 DeepSeek 余额 / 用量查看器。

可选参数：
  --mini   以「钉在桌面」迷你窗模式启动（配合开机自启使用）。
"""

import sys
import ui


if __name__ == "__main__":
    start_mini = "--mini" in sys.argv
    app = ui.App(start_mini=start_mini)
    app.mainloop()
