"""LLM 调用异常分类器

参考 hermes-agent/agent/error_classifier.py 的核心思想,针对 smart_edu 的
单 provider、单 model 场景做了大幅裁剪:

  - 保留: 结构化分类法 (FailoverReason)、优先级流水线、retryable 提示
  - 移除: should_compress / should_rotate_credential / should_fallback、
          provider 特殊模式、model_not_found 等(单 provider 不适用)

优先级:
  1. HTTP status code
  2. message 关键词(billing > rate_limit > auth)
  3. 传输错误类型(TimeoutError / ConnectionError / OpenAI 传输异常)
  4. 兜底 unknown(retryable=True)
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


# ── 错误类别枚举 ──────────────────────────────────────────────────────────

class FailoverReason(enum.Enum):
    """LLM 调用失败原因,决定恢复策略"""

    auth = "auth"  # 401/403 凭据无效 — 立即失败
    billing = "billing"  # 402 / 余额耗尽 — 立即失败
    rate_limit = "rate_limit"  # 429 限流 — 退避重试
    overloaded = "overloaded"  # 503/529 过载 — 退避重试
    server_error = "server_error"  # 500/502 服务端错误 — 退避重试
    timeout = "timeout"  # 网络/读取超时 — 重试
    format_error = "format_error"  # 400 请求格式错误 — 立即失败
    unknown = "unknown"  # 未分类 — 退避重试


# ── 用户文案表(中文,直接给前端) ────────────────────────────────────────

USER_MESSAGES: Dict[FailoverReason, str] = {
    FailoverReason.rate_limit: "请求过于频繁,请稍后再试。",
    FailoverReason.overloaded: "AI 服务暂时拥塞,请稍后重试。",
    FailoverReason.server_error: "AI 服务暂时拥塞,请稍后重试。",
    FailoverReason.timeout: "网络超时,请稍后重试。",
    FailoverReason.auth: "AI 服务配置异常,请联系管理员。",
    FailoverReason.billing: "AI 服务配置异常,请联系管理员。",
    FailoverReason.format_error: "请求格式异常,请刷新页面后重试。",
    FailoverReason.unknown: "AI 服务暂时不可用,请稍后重试。",
}


# ── 分类结果 ─────────────────────────────────────────────────────────────

@dataclass
class ClassifiedError:
    """结构化的异常分类结果,携带恢复动作提示"""

    reason: FailoverReason
    status_code: Optional[int] = None
    message: str = ""
    retryable: bool = True
    error_context: Dict[str, Any] = field(default_factory=dict)

    @property
    def user_message(self) -> str:
        """给前端展示的中文文案"""
        return USER_MESSAGES.get(self.reason, USER_MESSAGES[FailoverReason.unknown])


# ── 自定义异常 ───────────────────────────────────────────────────────────

class LLMServiceError(Exception):
    """LLM 调用永久失败/重试耗尽后的语义化包装

    service 层捕获此异常即可直接拿到 user_message 文案,无需再次分类。
    """

    def __init__(self, classified: ClassifiedError) -> None:
        super().__init__(f"{classified.reason.value}: {classified.message}")
        self.classified = classified


# ── 关键词模式 ───────────────────────────────────────────────────────────

# billing 优先于 rate_limit(后者只是节流,不应误判为已欠费)
_BILLING_PATTERNS = (
    "insufficient credits",
    "insufficient_quota",
    "credit balance",
    "credits have been exhausted",
    "payment required",
    "billing hard limit",
    "exceeded your current quota",
    "account is deactivated",
    "余额不足",
)

_RATE_LIMIT_PATTERNS = (
    "rate limit",
    "rate_limit",
    "too many requests",
    "throttled",
    "requests per minute",
    "tokens per minute",
    "try again in",
    "please retry after",
    "resource_exhausted",
    "请求过于频繁",
)

_AUTH_PATTERNS = (
    "invalid api key",
    "invalid_api_key",
    "authentication",
    "unauthorized",
    "invalid token",
    "token expired",
    "token revoked",
    "access denied",
)

# 传输层异常的类型名(基于 type(e).__name__ 比对,避免硬依赖三方库)
_TRANSPORT_ERROR_TYPES = frozenset({
    # stdlib
    "TimeoutError", "ConnectionError", "ConnectionResetError",
    "ConnectionAbortedError", "BrokenPipeError",
    # httpx
    "ReadTimeout", "ConnectTimeout", "PoolTimeout",
    "ConnectError", "RemoteProtocolError", "ReadError",
    # openai SDK
    "APIConnectionError", "APITimeoutError",
})


# ── 主入口 ───────────────────────────────────────────────────────────────

def classify_llm_error(error: Exception) -> ClassifiedError:
    """把 LLM 调用异常分类为结构化恢复建议"""
    status_code = _extract_status_code(error)
    body = _extract_error_body(error)
    error_type = type(error).__name__
    error_msg = _build_error_msg(error, body)
    message = _extract_message(error, body)

    def _make(reason: FailoverReason, retryable: bool) -> ClassifiedError:
        return ClassifiedError(
            reason=reason,
            status_code=status_code,
            message=message,
            retryable=retryable,
            error_context={"error_type": error_type},
        )

    # ── 1. HTTP status code ─────────────────────────────────────────
    if status_code is not None:
        if status_code in (401, 403):
            return _make(FailoverReason.auth, retryable=False)
        if status_code == 402:
            return _make(FailoverReason.billing, retryable=False)
        if status_code == 429:
            return _make(FailoverReason.rate_limit, retryable=True)
        if status_code in (500, 502):
            return _make(FailoverReason.server_error, retryable=True)
        if status_code in (503, 529):
            return _make(FailoverReason.overloaded, retryable=True)
        if status_code == 400:
            # 400 也可能是被错误编码的 billing/rate_limit,先按关键词识别
            if any(p in error_msg for p in _BILLING_PATTERNS):
                return _make(FailoverReason.billing, retryable=False)
            if any(p in error_msg for p in _RATE_LIMIT_PATTERNS):
                return _make(FailoverReason.rate_limit, retryable=True)
            return _make(FailoverReason.format_error, retryable=False)
        if 500 <= status_code < 600:
            return _make(FailoverReason.server_error, retryable=True)
        if 400 <= status_code < 500:
            return _make(FailoverReason.format_error, retryable=False)

    # ── 2. message 关键词(无 status_code 时) ──────────────────────
    if any(p in error_msg for p in _BILLING_PATTERNS):
        return _make(FailoverReason.billing, retryable=False)
    if any(p in error_msg for p in _RATE_LIMIT_PATTERNS):
        return _make(FailoverReason.rate_limit, retryable=True)
    if any(p in error_msg for p in _AUTH_PATTERNS):
        return _make(FailoverReason.auth, retryable=False)

    # ── 3. 传输错误 ─────────────────────────────────────────────────
    if error_type in _TRANSPORT_ERROR_TYPES or isinstance(
            error, (TimeoutError, ConnectionError, OSError)
    ):
        return _make(FailoverReason.timeout, retryable=True)

    # ── 4. 兜底 ─────────────────────────────────────────────────────
    return _make(FailoverReason.unknown, retryable=True)


# ── 辅助提取 ─────────────────────────────────────────────────────────────

def _extract_status_code(error: Exception) -> Optional[int]:
    """沿 __cause__/__context__ 链查找 HTTP 状态码"""
    current = error
    for _ in range(5):
        code = getattr(current, "status_code", None)
        if isinstance(code, int):
            return code
        code = getattr(current, "status", None)
        if isinstance(code, int) and 100 <= code < 600:
            return code
        cause = getattr(current, "__cause__", None) or getattr(current, "__context__", None)
        if cause is None or cause is current:
            break
        current = cause
    return None


def _extract_error_body(error: Exception) -> dict:
    """从 SDK 异常对象中提取结构化 body"""
    body = getattr(error, "body", None)
    if isinstance(body, dict):
        return body
    response = getattr(error, "response", None)
    if response is not None:
        try:
            json_body = response.json()
            if isinstance(json_body, dict):
                return json_body
        except Exception:
            pass
    return {}


def _extract_message(error: Exception, body: dict) -> str:
    """提取最有信息量的错误消息(截断到 500 字符)"""
    if body:
        err_obj = body.get("error", {})
        if isinstance(err_obj, dict):
            msg = err_obj.get("message", "")
            if isinstance(msg, str) and msg.strip():
                return msg.strip()[:500]
        msg = body.get("message", "")
        if isinstance(msg, str) and msg.strip():
            return msg.strip()[:500]
    return str(error)[:500]


def _build_error_msg(error: Exception, body: dict) -> str:
    """构造用于关键词匹配的小写聚合消息(str(error) + body.message)"""
    raw = str(error).lower()
    body_msg = ""
    if isinstance(body, dict):
        err_obj = body.get("error", {})
        if isinstance(err_obj, dict):
            body_msg = (err_obj.get("message") or "").lower()
        if not body_msg:
            body_msg = (body.get("message") or "").lower()
    if body_msg and body_msg not in raw:
        return f"{raw} {body_msg}"
    return raw
