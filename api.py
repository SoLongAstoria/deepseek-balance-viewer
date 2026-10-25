# -*- coding: utf-8 -*-
"""DeepSeek 开放平台 API 客户端。

接口地址与字段集中定义在本文件顶部，便于按官方文档校正。
官方文档：https://api-docs.deepseek.com/zh-cn/api/get-user-balance/
认证方式：Header `Authorization: Bearer <API_KEY>`
"""

import json
import time
import socket
import urllib.request
import urllib.error
from typing import Optional


# ===================== 接口集中定义（按官方文档校正） =====================
# 官方 API 根地址。如官方调整，改这里即可。
API_BASE_DEFAULT = "https://api.deepseek.com"

# 查询余额（官方已确认公开，2025-09 文档）
# GET {API_BASE}/user/balance
BALANCE_ENDPOINT = "/user/balance"

# 用量接口（官方当前公开文档未提供；此处为预留占位）。
# 若 DeepSeek 后续开放 /user/usage，请同步校正下方 get_usage() 的字段解析。
# 当前请求到 404 时会自动降级，界面给出诚实说明。
USAGE_ENDPOINT = "/user/usage"

# 默认网络参数（可在 config.ini 的 [api] 段覆盖）
DEFAULT_TIMEOUT = 10   # 单次请求超时（秒）
DEFAULT_RETRIES = 3    # 可重试错误的最大重试次数
# ==========================================================================


class DeepSeekApiError(Exception):
    """API 通用异常基类。retryable=True 表示可重试。"""
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.message = message
        self.retryable = retryable


class AuthError(DeepSeekApiError):
    """401：Key 无效 / 被吊销 —— 不可重试。"""
    def __init__(self, message: str = "API Key 无效或已被吊销，请检查设置"):
        super().__init__(message, retryable=False)


class InsufficientBalanceError(DeepSeekApiError):
    """402：账户余额不足 —— 不可重试。"""
    def __init__(self, message: str = "账户余额不足（HTTP 402），请充值"):
        super().__init__(message, retryable=False)


class RateLimitError(DeepSeekApiError):
    """429：请求被限流 —— 可重试。"""
    def __init__(self, message: str = "请求过于频繁，已被限流（HTTP 429）"):
        super().__init__(message, retryable=True)


class NetworkError(DeepSeekApiError):
    """网络异常 / 超时 —— 可重试。"""
    def __init__(self, message: str = "网络连接失败或超时"):
        super().__init__(message, retryable=True)


class ServerError(DeepSeekApiError):
    """5xx：服务端错误 —— 可重试。"""
    def __init__(self, message: str = "DeepSeek 服务端错误"):
        super().__init__(message, retryable=True)


class DeepSeekClient:
    """封装 DeepSeek 余额 / 用量接口的调用，内置超时与指数退避重试。"""

    def __init__(self, api_key: str, base_url: str = API_BASE_DEFAULT,
                 timeout: int = DEFAULT_TIMEOUT, retries: int = DEFAULT_RETRIES):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries

    def _request(self, endpoint: str):
        """发起一次 GET 请求，统一处理超时 / 重试 / 错误分类。"""
        url = self.base_url + endpoint
        last_exc: Optional[DeepSeekApiError] = None

        for attempt in range(self.retries + 1):
            try:
                req = urllib.request.Request(url, method="GET")
                req.add_header("Authorization", f"Bearer {self.api_key}")
                req.add_header("Accept", "application/json")
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read().decode("utf-8")
                    return json.loads(raw)

            except urllib.error.HTTPError as e:
                # HTTPError 已被服务器响应，status 已知
                if e.code == 401:
                    raise AuthError()
                if e.code == 402:
                    raise InsufficientBalanceError()
                if e.code == 429:
                    last_exc = RateLimitError()
                elif 500 <= e.code < 600:
                    last_exc = ServerError(f"DeepSeek 服务端错误（HTTP {e.code}）")
                else:
                    # 404 等其它状态码（用量接口未公开时走这里）
                    raise DeepSeekApiError(
                        f"HTTP {e.code}：{getattr(e, 'reason', '')}", retryable=False)

            except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
                reason = getattr(e, "reason", e)
                last_exc = NetworkError(f"网络错误：{reason}")

            # 仅在可重试异常上退避重试
            if last_exc is not None and last_exc.retryable and attempt < self.retries:
                # 指数退避：1s, 2s, 4s ... 上限 30s
                time.sleep(min(2 ** attempt, 30))
                continue

            if last_exc is not None:
                raise last_exc

        raise last_exc or DeepSeekApiError("未知错误")

    def get_balance(self) -> dict:
        """查询余额。返回结构化 dict：{is_available, infos:[{currency,total,granted,topped_up}]}"""
        data = self._request(BALANCE_ENDPOINT)
        infos = data.get("balance_infos", [])
        result = {"is_available": data.get("is_available", None), "infos": []}
        for item in infos:
            # 官方字段均为字符串，转换为 float 便于计算与显示
            result["infos"].append({
                "currency": item.get("currency", "CNY"),
                "total_balance": float(item.get("total_balance", 0) or 0),
                "granted_balance": float(item.get("granted_balance", 0) or 0),
                "topped_up_balance": float(item.get("topped_up_balance", 0) or 0),
            })
        return result

    def get_usage(self):
        """用量接口（官方当前未公开）。成功返回原始 dict，失败（如 404）返回 None。"""
        try:
            data = self._request(USAGE_ENDPOINT)
            # 注：官方字段未公开，预留解析位置。
            # 若开放，请在此映射请求数 / Token 用量到统一结构。
            return data
        except DeepSeekApiError:
            return None
