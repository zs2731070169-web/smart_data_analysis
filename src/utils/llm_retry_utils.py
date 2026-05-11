"""LLM 调用的异步重试包装器

用法:
    result = await acall_with_retry(
        lambda: llm.with_structured_output(Schema).ainvoke(prompt)
    )

参数 coro_factory 必须是「每次调用返回一个新协程」的 callable,
因为 Python 协程对象不能复用 —— 重试时必须重新构造。

行为:
  - 分类器判定 retryable=True 时,按抖动指数退避 sleep 后重试
  - retryable=False 或达到 max_attempts 时,抛 LLMServiceError
"""

import asyncio
from typing import Awaitable, Callable, TypeVar

from infra.error.classifier import classify_llm_error, LLMServiceError
from infra.error.retry import jittered_backoff
from infra.log.logging import logger

logger.info("LLM 调用的异步重试包装器")

T = TypeVar("T")


async def acall_with_retry(
        coro_factory: Callable[[], Awaitable[T]],
        *,
        max_attempts: int = 3,
        base_delay: float = 2.0,
        max_delay: float = 30.0,
        op_name: str = "llm",
) -> T:
    """对 LLM 异步调用做分类重试

    Args:
        coro_factory: 每次调用返回新协程的工厂(用 lambda 包裹原调用)
        max_attempts: 最大尝试次数(含首次,默认 3)
        base_delay: 退避基础延迟(秒)
        max_delay: 退避上限(秒)
        op_name: 日志标识(如 "intent" / "extract" / "answer")

    Raises:
        LLMServiceError: 永久错误或重试耗尽
    """
    for attempt in range(1, max_attempts + 1):
        try:
            # 调用主逻辑方法
            return await coro_factory()
        except Exception as e:
            # 根据异常类型获取错误分类器
            classified = classify_llm_error(e)

            # 永久错误直接快速失败
            if not classified.retryable:
                logger.warning(
                    "[%s] 永久错误 reason=%s status=%s msg=%s — 立即失败",
                    op_name, classified.reason.value,
                    classified.status_code, classified.message,
                )
                raise LLMServiceError(classified) from e

            # 重试耗尽错误直接快速失败
            if attempt >= max_attempts:
                logger.warning(
                    "[%s] 重试耗尽 reason=%s attempt=%d/%d msg=%s",
                    op_name, classified.reason.value,
                    attempt, max_attempts, classified.message,
                )
                raise LLMServiceError(classified) from e

            # 指数退避延迟后再继续重试
            delay = jittered_backoff(attempt, base_delay=base_delay, max_delay=max_delay)
            logger.warning(
                "[%s] 调用失败 reason=%s attempt=%d/%d,%.1fs 后重试",
                op_name, classified.reason.value, attempt, max_attempts, delay,
            )
            await asyncio.sleep(delay)
