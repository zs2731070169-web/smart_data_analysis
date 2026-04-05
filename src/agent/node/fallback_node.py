from langgraph.runtime import Runtime

from agent.schema.context_schema import EnvContext
from agent.schema.state_schema import OverallState
from conf.app_config import MAX_CORRECT_COUNT
from infra.log.logging import logger


async def fallback_node(state: OverallState, runtime: Runtime[EnvContext]):
    """
    熔断兜底节点：当查询无法被满足时返回友好拒答提示。

    触发场景：
    1. missing_complete_node 在元数据中查不到所需字段/指标（unfound_fields 非空），且重试次数达到上限（unfound_count >= MAX_UNFOUND_COUNT）
    2. validate_hql_node 判定纠错轮次已达上限（correct_count >= MAX_CORRECT_COUNT）
    """
    writer = runtime.stream_writer

    unfound_fields: list[str] = state.get('unfound_fields') or []
    correct_count: int = state.get('correct_count', 0)

    if unfound_fields:
        fields_str = "、".join(f"[{f}]" for f in unfound_fields)
        answer = f"当前数据源不包含所需字段 {fields_str}，无法完成该查询"
    elif correct_count >= MAX_CORRECT_COUNT:
        answer = f"HQL 经 {correct_count} 轮纠错后仍无法满足查询要求，无法完成该查询"
    else:
        answer = "无法完成该查询，请检查查询条件或联系数据团队"

    logger.warning(f"触发熔断拒答：{answer}")
    writer(answer)
    return {"answer": answer, "output": []}

