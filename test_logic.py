# -*- coding: utf-8 -*-
"""无界面逻辑自测：api 解析/错误映射、config 加解密、history 追踪。"""
import sys, io, json, urllib.error
import api as dsapi
import config as cfg
import history as histmod


class FakeResp:
    def __init__(self, data):
        self._d = json.dumps(data).encode("utf-8")
    def read(self):
        return self._d
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def patch_urlopen(monkeypatch):
    dsapi.urllib.request.urlopen = monkeypatch


# ---------------- 1. 余额解析 ----------------
def test_balance_parse():
    sample = {
        "is_available": True,
        "balance_infos": [{
            "currency": "CNY",
            "total_balance": "110.00",
            "granted_balance": "10.00",
            "topped_up_balance": "100.00",
        }],
    }
    def fake(req, timeout=0):
        return FakeResp(sample)
    patch_urlopen(fake)
    c = dsapi.DeepSeekClient("sk-test")
    r = c.get_balance()
    assert r["is_available"] is True
    info = r["infos"][0]
    assert info["total_balance"] == 110.0
    assert info["granted_balance"] == 10.0
    assert info["topped_up_balance"] == 100.0
    print("[OK] 余额解析正确")


# ---------------- 2. 错误分类 ----------------
def test_error_mapping():
    def make_http(code):
        def fake(req, timeout=0):
            raise urllib.error.HTTPError("url", code, "x", {}, io.BytesIO(b"{}"))
        return fake

    patch_urlopen(make_http(401))
    try:
        dsapi.DeepSeekClient("x").get_balance()
        raise AssertionError("应抛出 AuthError")
    except dsapi.AuthError:
        pass

    patch_urlopen(make_http(429))
    try:
        dsapi.DeepSeekClient("x").get_balance()
        raise AssertionError("应抛出 RateLimitError")
    except dsapi.RateLimitError:
        pass

    def netfake(req, timeout=0):
        raise urllib.error.URLError("timed out")
    patch_urlopen(netfake)
    try:
        dsapi.DeepSeekClient("x").get_balance()
        raise AssertionError("应抛出 NetworkError")
    except dsapi.NetworkError:
        pass
    print("[OK] 错误分类正确 (401/429/网络)")


# ---------------- 3. 用量接口降级 ----------------
def test_usage_fallback():
    def fake_404(req, timeout=0):
        raise urllib.error.HTTPError("url", 404, "nf", {}, io.BytesIO(b"{}"))
    patch_urlopen(fake_404)
    c = dsapi.DeepSeekClient("x")
    assert c.get_usage() is None
    print("[OK] 用量接口 404 优雅降级为 None")


# ---------------- 4. 配置加解密 ----------------
def test_config_crypto():
    # 强制走轻量混淆路径，保证跨平台可测
    cfg._HAS_DPAPI = False
    token = cfg.encrypt_secret("sk-secret-123")
    assert not token.startswith("sk-"), "配置不应以明文存储"
    assert cfg.decrypt_secret(token) == "sk-secret-123"
    # 明文兼容分支
    assert cfg.decrypt_secret("sk-plain") == "sk-plain"
    print("[OK] 配置加解密/明文兼容正确 (密文前缀:", token.split(":")[0], ")")


# ---------------- 5. 历史追踪 ----------------
def test_history():
    histmod.HISTORY_PATH = "_test_history.json"
    import os
    if os.path.exists(histmod.HISTORY_PATH):
        os.remove(histmod.HISTORY_PATH)
    h1 = histmod.save_snapshot(100.0, "CNY")
    h2 = histmod.save_snapshot(90.0, "CNY")
    h3 = histmod.save_snapshot(95.0, "CNY")  # 回充，不算消耗
    assert histmod.consumption_since_start(h3) == 10.0
    # 相同值不重复记录
    h4 = histmod.save_snapshot(95.0, "CNY")
    assert len(h4) == len(h3)
    # 区间消耗：构造跨三天的快照（100 → 90 → 80 → 70，每天降 10）
    import os as _os
    if _os.path.exists(histmod.HISTORY_PATH):
        _os.remove(histmod.HISTORY_PATH)
    day = 86400.0
    t0 = 1_700_000_000.0  # 固定基准，跨天稳定
    rows = []
    for i, bal in enumerate((100.0, 90.0, 80.0, 70.0)):
        rows.append({"ts": t0 + i * day, "time": "x",
                     "balance": bal, "currency": "CNY"})
    # 从第 2 天（t0+day）起算：基准 = 区间前最后一点 100 → 100→90→80→70 = 30
    assert histmod.consumption_between(rows, t0 + day) == 30.0
    # 从第 3 天起算：基准 90 → 90→80→70 = 20
    assert histmod.consumption_between(rows, t0 + 2 * day) == 20.0
    # end_ts 截断：[t0+day, t0+2*day) 只含 90 一点（基准 100）→ 10
    assert histmod.consumption_between(rows, t0 + day, t0 + 2 * day) == 10.0
    # start 之前无基准点（第一条即区间起点）时，从该点后开始累
    assert histmod.consumption_between(rows, t0 + 0.5 * day) == 30.0
    # since_start 与区间版一致（单一来源）
    assert histmod.consumption_since_start(rows) == 30.0
    if _os.path.exists(histmod.HISTORY_PATH):
        _os.remove(histmod.HISTORY_PATH)

    # ⚠ 隔离规则（2026-10-25 数据被写脏的根因）：
    # DSBV_CONFIG / DSBV_HISTORY 存在时，历史文件必须离开用户真实目录，
    # 否则冒烟脚本注入的样例余额会被算成真实消耗。
    import importlib
    import tempfile as _tf
    _keys = ("DSBV_CONFIG", "DSBV_HISTORY")
    _old = {k: _os.environ.get(k) for k in _keys}
    try:
        _td = _tf.mkdtemp(prefix="dsbv_iso_")
        _os.environ.pop("DSBV_HISTORY", None)
        _os.environ["DSBV_CONFIG"] = _os.path.join(_td, "config.ini")
        importlib.reload(histmod)
        assert histmod.HISTORY_PATH == _os.path.join(_td, "history.json"), \
            f"DSBV_CONFIG 未带动历史隔离：{histmod.HISTORY_PATH}"
        _os.environ["DSBV_HISTORY"] = _os.path.join(_td, "custom.json")
        importlib.reload(histmod)
        assert histmod.HISTORY_PATH.endswith("custom.json"), \
            f"DSBV_HISTORY 未生效：{histmod.HISTORY_PATH}"
    finally:
        for k in _keys:
            if _old[k] is None:
                _os.environ.pop(k, None)
            else:
                _os.environ[k] = _old[k]
        importlib.reload(histmod)
        histmod.HISTORY_PATH = "_test_history.json"   # 还原给后续用例
    print("[OK] 本地追踪累计消耗 = 10.00（回充不计入）；区间消耗（今日/本月）正确；"
          "历史隔离变量生效")


# ---------------- 6. 价格时段判定 ----------------
class _FakeTime:
    """只注入到 pricing 模块内部，避免污染全局 time 模块。"""

    def __init__(self, st):
        self._st = st

    def gmtime(self, _ts=None):
        return self._st

    def time(self):
        return 0.0


def test_pricing():
    import time
    import pricing

    # 官方定价页（2026-09-29 快照）空闲时段单价，作为回归基准
    EXPECT_OFFPEAK = {
        "deepseek-flash":  {"hit": 0.02, "miss": 1.0, "out": 4.0},
        "deepseek-v4-pro": {"hit": 0.15, "miss": 4.5, "out": 13.5},
    }
    assert set(pricing.PRICING_OFFPEAK.keys()) == set(EXPECT_OFFPEAK.keys()), \
        "在售模型应仅有两个：deepseek-flash / deepseek-v4-pro"

    real_time = pricing.time

    def check(st, expect_peak, tag):
        pricing.time = _FakeTime(st)
        period, rows = pricing.get_current_prices()
        assert period["peak"] is expect_peak, f"{tag} 时段判定错误"
        want_label = "高峰时段" if expect_peak else "空闲时段"
        assert period["label"] == want_label, f"{tag} 官方术语应为「{want_label}」"
        factor = pricing.PEAK_FACTOR if expect_peak else 1.0
        for r in rows:
            exp = EXPECT_OFFPEAK[r["id"]]
            for k in ("hit", "miss", "out"):
                assert abs(r[k] - exp[k] * factor) < 1e-9, \
                    f"{tag} {r['id']} {k} 应为 {exp[k] * factor}，实际 {r[k]}"
        return rows

    try:
        # 北京时间 周三 10:00（UTC 02:00）—— 高峰
        check(time.struct_time((2026, 9, 30, 10, 0, 0, 2, 273, 0)), True, "周三 10:00")
        # 北京时间 周三 20:00 —— 空闲
        check(time.struct_time((2026, 9, 30, 20, 0, 0, 2, 273, 0)), False, "周三 20:00")
        # 周六 10:00 —— 官方：周末全天空闲
        check(time.struct_time((2026, 10, 3, 10, 0, 0, 5, 276, 0)), False, "周六 10:00")
        # 周三 13:00（午间隔断）—— 空闲
        check(time.struct_time((2026, 9, 30, 13, 0, 0, 2, 273, 0)), False, "周三 13:00")
    finally:
        pricing.time = real_time

    # 6.9 距下次「峰⇄闲」切换：价格卡右上角「距峰时 2h 14m」的数据源
    #     周中 10:00（峰时）→ 下一个不同状态是 12:00 转空闲 → 剩余 2 小时
    real_gm = pricing.time.gmtime
    try:
        pricing.time.gmtime = lambda ts: time.struct_time(
            (2026, 9, 30, 10, 0, 0, 2, 273, 0))      # 周三 10:00（峰时）
        left, label = pricing.next_period_change()
        assert left == 7200 and "空闲" in label, (left, label)
        pricing.time.gmtime = lambda ts: time.struct_time(
            (2026, 9, 30, 13, 0, 0, 2, 273, 0))      # 周三 13:00（空闲）
        left, label = pricing.next_period_change()
        assert left == 3600 and "高峰" in label, (left, label)
    finally:
        pricing.time.gmtime = real_gm

    print("[OK] 价格时段判定与官方单价一致（空闲 0.02/1/4 与 0.15/4.5/13.5）；"
          "距切换倒计时正确")


# ---------------- 7. 界面（设计稿布局 / 命中区域 / 主题 token） ----------------
def test_ui_layout():
    import config as cfgmod
    import uikit

    # 7.1 配置默认键：迷你卡显示项必须是 cons（旧版误写成 consumption，
    #     导致 config.ini 里那行是死键，读的时候永远走 fallback）
    import os
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        c1 = cfgmod.Config(path=os.path.join(d, "config.ini"))
        for k in ("balance", "period", "price", "cons", "net"):
            assert c1.get("ui", f"mini_show_{k}") in ("true", "false"), k
        assert c1.get("ui", "mini_show_cons") == "false", "累计消耗默认关闭"
        # 真玻璃必须默认关闭：开启后 DWM 会重新合成整块客户区，GDI 文字被
        # 一并模糊，实测对比度从 15:1 掉到 1.2:1（用户真机截图 + _audit_contrast）
        assert c1.get("ui", "glass") == "false", "真玻璃默认必须关闭"

        # 7.1b DSBV_CONFIG 环境变量必须能覆盖配置路径 —— 截图/冒烟脚本靠它隔离，
        #       否则跑一次验证就可能把用户真实 Key 写坏（10-25 真实发生过）
        _old_env = os.environ.get("DSBV_CONFIG")
        try:
            iso = os.path.join(d, "isolated.ini")
            os.environ["DSBV_CONFIG"] = iso
            assert cfgmod.default_config_path() == iso
            assert cfgmod.Config().path == iso, "Config() 未跟随 DSBV_CONFIG"
        finally:
            if _old_env is None:
                os.environ.pop("DSBV_CONFIG", None)
            else:
                os.environ["DSBV_CONFIG"] = _old_env

    # 7.2 浅色主题 8 项加深必须与 _mockup.html 对照表一致（WCAG AA 的关键）
    L = uikit.MINI_THEMES["light"]
    for k, want in (("fg", "#141A23"), ("fg2", "#46505F"), ("fg3", "#6E7683"),
                    ("down", "#0062D6"), ("up", "#C75B00"),
                    ("idle", "#1E7A38"), ("peak", "#B3231A"),
                    ("rim", "#B9C0CC")):
        assert L[k] == want, f"浅色 {k} 应为 {want}，实际 {L[k]}"

    # 7.3 主窗布局：各区块 y 必须等于设计稿换算值（改了就和效果图不一致）
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
    except Exception as e:  # pragma: no cover
        print(f"[SKIP] 无图形环境，跳过界面布局测试（{e}）")
        return
    try:
        class _Stub:
            theme = "dark"

            def __init__(self):
                self.clicked = []
                self.key_commits = []

            def on_view_click(self, k):
                self.clicked.append(k)

            def on_key_commit(self, t):
                self.key_commits.append(t)

        stub = _Stub()
        v = uikit.MainView(root, stub, scale=1.0)
        v.pack()
        # 非玻璃模式下 Canvas 底色必须是主题窗底色。
        # 曾硬编码 bg="#000000"，导致标题栏/状态栏的深色文字画在黑底上"消失"
        # （用户真机截图的直接原因之一），这里锁死不许回退。
        assert v.glass_on is False
        assert v.cget("bg").lower() == \
            uikit.MAIN_THEMES["dark"]["win_bg"].lower(), \
            f"非玻璃模式底色应为窗底色，实际 {v.cget('bg')}"
        # 关键 y 坐标（全量布局契约）
        assert v.y_hero == 47, v.y_hero
        assert v.y_price == 198, v.y_price
        assert v.y_chart == 334, v.y_chart
        assert v.y_set == 503, v.y_set
        assert v.y_status == 654, v.y_status
        assert v.y_status + v.STATUS_H == v.WIN_H, "内容底部必须正好等于窗口高"

        v.update_state(api_key="sk-test", interval=60, autostart=False,
                       status="测试", cur="¥", balance="12.34",
                       badge_period="闲时 · 5 折", badge_gift="赠金 ¥5.00",
                       net_down="499 KB/s", net_up="12 KB/s",
                       cons_today="¥3.21", cons_month="¥86.40",
                       grant_pct=40, grant_val="¥5.00 / ¥12.34",
                       topup_pct=60, topup_val="¥7.34 / ¥12.34",
                       price_more="闲时 5 折生效中", is_peak=False,
                       price_rows=[
                           {"name": "a", "vals": ["¥0.02", "¥1.00", "¥4.00"],
                            "cur": True, "status": "闲时", "st_kind": "on"},
                           {"name": "b", "vals": ["¥0.15", "¥4.50", "¥13.50"],
                            "cur": True, "status": "闲时", "st_kind": "on"},
                           {"name": "a · 峰时", "vals": ["¥0.04", "¥2.00", "¥8.00"],
                            "cur": False, "status": "峰时", "st_kind": "peak",
                            "dim": True}],
                       chart_vals=[10, 9, 8, 7, 6, 5, 4],
                       chart_labels=["10-19", "10-20", "10-21", "10-22",
                                     "10-23", "10-24", "10-25"],
                       chart_more="日均 ¥3.01",
                       chips=[(k, lab, k != "cons") for k, lab in
                              (("balance", "余额"), ("period", "时段"),
                               ("price", "价格"), ("cons", "累计"),
                               ("net", "网速"))])
        root.update_idletasks()
        assert len(v.find_all()) > 120, f"绘制项目过少：{len(v.find_all())}"

        # 7.4 命中区域：所有可点项都必须登记，否则功能等于被删了
        keys = {r[4] for r in v._regions}
        for need in ("mini", "theme", "refresh", "shot", "price_info",
                     "csv", "about", "interval", "autostart"):
            assert need in keys, f"缺少可点区域：{need}"
        assert sum(1 for k in keys if str(k).startswith("chip:")) == 5

        # 7.5 点击分发到 App 回调（模拟真实点击）
        r = next(r for r in v._regions if r[4] == "theme")
        cx, cy = (r[0] + r[2]) / 2, (r[1] + r[3]) / 2
        v._on_click(type("E", (), {"x": cx, "y": cy})())
        assert stub.clicked == ["theme"], stub.clicked

        # 7.6 局部重绘（网速每秒走的路径）不能让 items 越堆越多
        n0 = len(v.find_all())
        for i in range(4):
            v.update_state(_blocks=("hero",), net_down=f"{i} KB/s", net_up="1 KB/s")
            root.update_idletasks()
        assert abs(len(v.find_all()) - n0) <= 2, \
            f"局部重绘泄漏 items：{n0} → {len(v.find_all())}"

        # 7.7 主题切换后可正常渲染
        for t in ("light", "dark"):
            v.set_theme(t)
            root.update_idletasks()
            assert v.theme == t and len(v.find_all()) > 120

        # 7.8 API Key 提交门槛：没编辑过就绝不提交。
        #     <FocusOut> 在窗口失活/脚本退出/点别处时都会触发，无条件提交会把
        #     显示出来的空值写回配置，静默覆盖用户已存的 Key（10-25 真实丢过）。
        v._key_dirty = False
        v._commit_key()
        assert stub.key_commits == [], "未编辑就提交（会覆盖用户 Key）"
        v._mark_key_dirty()
        v.key_var.set("sk-new-key")
        v._commit_key()
        assert stub.key_commits == ["sk-new-key"], stub.key_commits
        # 提交后 dirty 复位，再失焦不会重复提交
        v._commit_key()
        assert stub.key_commits == ["sk-new-key"], "dirty 未复位，重复提交"
    finally:
        root.destroy()
    print("[OK] 界面布局对齐设计稿 / 命中区域完整 / 局部重绘不泄漏 / 主题切换正常")


# ---------------- 8. 托盘：线程切换 + 缺依赖降级 ----------------
def test_tray():
    import tray as traymod
    import ui as uimod

    # 8.0 本项目 App 就是 tk.Tk 子类、没有 .root —— 托盘回调必须兼容这种形态
    assert not hasattr(uimod.App, "root"), \
        "App 没有 root 属性：托盘回调若写 app.root.after 会 AttributeError（且被托盘线程吞掉）"

    class _Bare:      # 无 .root，自带 after（Tk 实例即此形态）
        def __init__(self):
            self.calls = []

        def after(self, delay, fn):
            self.calls.append((delay, fn))

    class _Wrapped:   # 包装对象：经 .root 转发
        def __init__(self):
            self.root = _Bare()
            self.calls = self.root.calls

    for app in (_Bare(), _Wrapped()):
        traymod.TrayManager(app)._post(lambda: None)
        assert app.calls and app.calls[0][0] == 0, "必须通过 after(0, ...) 切回主线程"

    # 8.1 缺 pystray/Pillow 时要能导入、且 start() 返回 False 而非抛异常
    if not traymod.TRAY_AVAILABLE:
        assert traymod.TrayManager(_Bare()).start() is False
        print("[OK] 托盘回调切主线程正确；缺 pystray/Pillow 时优雅降级")
    else:
        print("[OK] 托盘回调切主线程正确（pystray/Pillow 已就绪）")


# ---------------- 9. 网速格式化与采样器（纯函数 + 假时钟） ----------------
def test_netmon():
    import netmon

    # 9.1 格式化：B / KB / MB / GB 自动进位，None 显示占位
    assert netmon.fmt_speed(None) == "--"
    assert netmon.fmt_speed(512) == "512 B/s"
    assert netmon.fmt_speed(1023) == "1023 B/s"
    assert netmon.fmt_speed(1024) == "1.00 KB/s"
    assert netmon.fmt_speed(1536) == "1.50 KB/s"
    assert netmon.fmt_speed(1024 * 1024) == "1.00 MB/s"
    assert netmon.fmt_speed(1024 ** 3) == "1.00 GB/s"

    # 9.2 采样器：首次返回 None 建立基线；第二次按 (Δ字节 / Δ秒) 求速率
    bi = iter([(0, 0), (5120, 1024)])        # 1 秒内：下载 +5KB，上传 +1KB
    ti = iter([1000.0, 1001.0])
    netmon.get_total_bytes = lambda: next(bi)
    netmon.time.time = lambda: next(ti)
    s = netmon.NetSampler()
    assert s.sample() is None, "首次采样应返回 None 仅建立基线"
    din, dout = s.sample()
    assert abs(din - 5120.0) < 1e-6, f"下载速率应≈5120 B/s，实际 {din}"
    assert abs(dout - 1024.0) < 1e-6, f"上传速率应≈1024 B/s，实际 {dout}"

    # 9.3 32 位计数器回绕保护：增量变负应自动加 2^32
    bi2 = iter([(2 ** 32 - 1000, 0), (500, 0)])  # 跨 0 回绕
    ti2 = iter([2000.0, 2001.0])
    netmon.get_total_bytes = lambda: next(bi2)
    netmon.time.time = lambda: next(ti2)
    s2 = netmon.NetSampler()
    s2.sample()
    d = s2.sample()[0]
    assert abs(d - 1500.0) < 1e-6, f"回绕后下载速率应≈1500 B/s，实际 {d}"
    print("[OK] 网速格式化 / 采样器（含回绕保护）正确")

    # 9.4 多显示器边界查询（修复"副屏闪回主屏"的核心）：
    # API 必须能调用且不抛异常；非法 hwnd 安全返回 None
    assert netmon.get_window_monitor_workarea(0) is None, "空 hwnd 应安全返回 None"
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        try:
            rect = netmon.get_window_monitor_workarea(root.winfo_id())
            assert rect is None or (
                len(rect) == 4 and rect[2] > rect[0] and rect[3] > rect[1]
            ), f"work area 应返回 4 元组且右>左、底>顶，实际 {rect}"
        finally:
            root.destroy()
    except ImportError:
        pass  # 无 tkinter 环境跳过真实窗口验证
    print("[OK] 多显示器 work area 查询（API 不抛异常 / 非法 hwnd 返回 None）")


def test_icon_art():
    """icon_art：多尺寸渲染 + ICO 目录结构（exe/托盘/窗口三处同源）。"""
    try:
        import icon_art
    except ImportError:
        print("[SKIP] 无 icon_art")
        return
    if not icon_art.AVAILABLE:
        print("[SKIP] 无 Pillow，图标功能降级")
        return
    # 各尺寸都能出图，且正方形、透明角、中心不透明
    # （阈值不放 0/255：LANCZOS 降采样在边缘会有 1~3 的振铃）
    for s in (16, 24, 32, 48, 64, 128, 256):
        img = icon_art.render(s)
        assert img.size == (s, s) and img.mode == "RGBA", f"{s}px 渲染异常"
        assert img.getpixel((0, 0))[3] <= 8, f"{s}px 角点应透明（squircle）"
        assert img.getpixel((s // 2, s // 2))[3] >= 250, f"{s}px 中心应不透明"
    # 光学尺寸：小尺寸自动省指针，大尺寸才是指针版
    small = icon_art.render(16).tobytes()
    assert small == icon_art.render(16, "plain").tobytes(), "16px 应为简化版"
    assert icon_art.render(48).tobytes() == \
        icon_art.render(48, "needle").tobytes(), "48px 应为完整指针版"
    # ICO 文件结构：7 档、每档可解、PNG 载荷
    import io
    import struct
    import tempfile
    from PIL import Image as _I
    path = tempfile.mktemp(suffix=".ico")
    assert icon_art.save_ico(path)
    raw = open(path, "rb").read()
    _, typ, cnt = struct.unpack("<HHH", raw[:6])
    assert typ == 1 and cnt == len(icon_art.ICO_SIZES), f"ICO 目录异常 {typ}/{cnt}"
    off = 6
    for s in sorted(icon_art.ICO_SIZES):
        w, h, _cc, _rv, _pl, bpp, sz, o = struct.unpack("<BBBBHHII",
                                                        raw[off:off + 16])
        off += 16
        assert (w or 256) == s and (h or 256) == s, f"ICO 档位尺寸不符 {w}/{h}"
        assert bpp == 32, "ICO 必须是 32 位带 alpha"
        assert raw[o:o + 4] == b"\x89PNG", "ICO 载荷应为 PNG"
        assert _I.open(io.BytesIO(raw[o:o + sz])).size == (s, s)
    print("[OK] 图标渲染（7 档尺寸 / 透明圆角 / 光学尺寸）+ ICO 多尺寸结构正确")


def test_glass():
    import glass
    # 非法输入必须安全短路，绝不抛异常
    assert glass.set_round_region(0, 200, 240, 16) is False
    assert glass.set_round_corners(0) is False
    assert glass.apply_acrylic(0, 0x99FFFFFF) is False
    assert glass.apply_liquid_glass(0, 0x8CFFFFFF, 200, 240, 16) is False
    assert glass.apply_window_glass(0, 0xD1201410) is False
    assert glass.extend_frame_into_client_area(0) is False
    assert glass.clear_window_glass(0) is False
    assert glass.get_toplevel_hwnd(0) == 0
    assert glass.get_toplevel_hwnd(None) == 0
    assert glass.dpi_scale(0) == 1.0
    assert isinstance(glass.system_is_light(), bool)
    # 真实窗口：顶级 HWND 解析 / 圆角裁剪 / acrylic API 能调通、DPI 缩放 ≥ 1.0
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        try:
            hwnd = root.winfo_id()
            # 顶级句柄解析：GetParent 链末端（Tk 主窗本身就是顶级，可能相等）
            top = glass.get_toplevel_hwnd(root)
            assert isinstance(top, int) and top > 0
            ok = glass.set_round_region(root, 200, 240, 16)
            assert ok in (True, False)
            # apply_acrylic / extend 返回 bool；Windows 上应为 True
            r = glass.apply_acrylic(root, 0x8CFFFFFF)
            assert isinstance(r, bool)
            if glass.HAS_ACRYLIC:
                assert r is True, "Windows 上 apply_acrylic 应调通"
                assert glass.extend_frame_into_client_area(root, -1) is True, \
                    "Windows 上 DwmExtendFrameIntoClientArea 应调通"
                # 完整配方（dark + accent + extend + region）应一次成功
                assert glass.apply_liquid_glass(
                    root, 0x8CFFFFFF, 200, 240, 16) is True, \
                    "Windows 上 apply_liquid_glass 应调通"
            assert glass.dpi_scale(root) >= 1.0
            # Win11 系统圆角（DWMWA_WINDOW_CORNER_PREFERENCE）：Win10 上会
            # 返回 False，但任何平台都不得抛异常
            assert glass.set_round_corners(root, True) in (True, False)
            assert glass.set_round_corners(root, False) in (True, False)
            # 撤销玻璃：主窗的默认路径（关掉后 DWM 不再合成整窗）——
            # 这是「文字看不清」的兜底，必须能调通且不抛异常
            assert glass.clear_window_glass(root) in (True, False)
            # region 圆角**四角都要切掉**：SetWindowRgn 返回 True 不代表覆盖
            # 范围正确（region 比窗口大时只有左上角圆弧落在窗口内，其余三角
            # 是直角 → 真机「四角黑底」）。这里实测四个角点。
            import glass as _g
            win = tk.Toplevel(root)
            win.overrideredirect(True)
            win.geometry("375x145+200+200")
            win.update()
            try:
                W, H, R = 375, 145, 23
                s = _g.dpi_scale(win)
                assert _g.set_round_region(win, W, H, R, physical=True)
                lw, lh = W / s, H / s
                cuts = [_g.region_corner_cut(win, x, y) for x, y in
                        ((1, 1), (lw - 2, 1), (1, lh - 2), (lw - 2, lh - 2))]
                assert all(cuts), f"region 未切掉四角（{cuts}）→ 真机会露黑角"
                # 中心不能被裁掉
                assert not _g.region_corner_cut(win, lw / 2, lh / 2)
            finally:
                win.destroy()
        finally:
            root.destroy()
    except ImportError:
        pass  # 无 tkinter 环境跳过真实窗口验证
    print("[OK] 玻璃 acrylic / extend frame / 顶级 HWND 解析 / 圆角裁剪 / "
          "明暗检测 / DPI 换算（API 不抛异常）")


if __name__ == "__main__":
    test_balance_parse()
    test_error_mapping()
    test_usage_fallback()
    test_config_crypto()
    test_history()
    test_pricing()
    test_ui_layout()
    test_tray()
    test_netmon()
    test_icon_art()
    test_glass()
    print("\n全部逻辑自测通过 ✅")
