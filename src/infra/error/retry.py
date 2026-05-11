"""抖动指数退避工具

来源:hermes-agent/agent/retry_utils.py(整段搬运,仅调小默认上限)。
抖动可避免多会话并发重试时撞在同一时刻造成 thundering-herd。
"""

import random
import threading
import time

# 进程内单调计数器,用于抖动随机种子唯一性;由锁保护以避免并发竞争。
_jitter_counter = 0
_jitter_lock = threading.Lock()


def jittered_backoff(
        attempt: int,
        *,
        base_delay: float = 2.0,
        max_delay: float = 30.0,
        jitter_ratio: float = 0.5,
) -> float:
    """计算带抖动的指数退避延迟(秒)

    delay = min(base * 2^(attempt-1), max_delay) + uniform(0, jitter_ratio * delay)

    Args:
        attempt: 1-based 重试次数
        base_delay: 第 1 次重试的基础延迟(秒)
        max_delay: 延迟上限(秒)
        jitter_ratio: 抖动占 delay 的比例,0.5 即 [0, 0.5*delay] 均匀分布
    """
    global _jitter_counter
    with _jitter_lock:
        _jitter_counter += 1
        tick = _jitter_counter

    exponent = max(0, attempt - 1)
    if exponent >= 63 or base_delay <= 0:
        delay = max_delay
    else:
        delay = min(base_delay * (2 ** exponent), max_delay)

    # 用时间 + 计数器双重打散,避免粗时钟下种子相同
    seed = (time.time_ns() ^ (tick * 0x9E3779B9)) & 0xFFFFFFFF
    rng = random.Random(seed)
    jitter = rng.uniform(0, jitter_ratio * delay)

    return delay + jitter
