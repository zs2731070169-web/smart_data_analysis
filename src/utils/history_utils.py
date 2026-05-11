# 历史消息压缩分级阈值(以历史消息条数为单位,一轮对话约 2 条)
import logging
from typing import List

from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("intent_identify")

_LIGHT_MAX = 6  # ≤6 条:全量
_MEDIUM_MAX = 20  # ≤20 条:保留最近 10 条
_RECENT_KEEP = 10  # 中/重级别保留的最近消息条数
_ANCHOR_KEEP = 2  # 重级别保留的首轮锚点消息条数
_KEYPOINT_MAX_CHARS = 20  # 中间轮用户提问摘要单条截断字符数


def compress_history(history: List[AnyMessage]) -> List[AnyMessage]:
    """按对话轮数量级选择压缩策略,避免长历史撑爆上下文。

    - ≤6 条:全量
    - ≤20 条:仅保留最近 10 条
    - >20 条:首轮 2 条(语境锚点) + 中间轮用户提问摘要 + 最近 10 条
    """
    length = len(history)
    if length <= _LIGHT_MAX:
        compressed = history
    elif length <= _MEDIUM_MAX:
        anchor = history[:_ANCHOR_KEEP]
        recent = history[-_RECENT_KEEP:]
        compressed = anchor + recent
    else:
        anchor = history[:_ANCHOR_KEEP]
        recent = history[-_RECENT_KEEP:]
        compressed = anchor + _summarize_middle(history[_ANCHOR_KEEP:-_RECENT_KEEP]) + recent
    logger.info(f"[intent_node] 历史压缩, 原始={length} -> 注入={len(compressed)}")
    return compressed


def _summarize_middle(middle_message: List[AnyMessage]) -> List[AnyMessage]:
    """把中间轮压成一条 SystemMessage:仅取用户提问关键词,每条截断到 40 字符。

    保留中间历史的话题轨迹,避免 >20 档完全丢弃中间上下文。
    若中间无用户消息则返回空列表。
    """
    truncate_seqs = []
    for msg in middle_message:
        if getattr(msg, "type", "") != "human":
            continue
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        truncate_seq = content.strip().replace("\n", " ")[:_KEYPOINT_MAX_CHARS]
        if truncate_seq:
            truncate_seqs.append(truncate_seq)
    if not truncate_seqs:
        return []
    summary = "中间轮历史用户提问摘要(仅供语境参考):\n" + "\n".join(
        f"{i}. {kp}" for i, kp in enumerate(truncate_seqs, 1)
    )
    return [HumanMessage(content=summary)]
