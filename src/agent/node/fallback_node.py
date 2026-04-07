from langgraph.runtime import Runtime

from agent.schema.context_schema import EnvContext
from agent.schema.state_schema import OverallState
from conf.app_config import MAX_CORRECT_COUNT
from infra.log.logging import logger


async def fallback_node(state: OverallState, runtime: Runtime[EnvContext]):
    """
    熔断兜底节点：当查询无法被满足时返回友好拒答提示。

    触发场景：
    1. generate_hql_node 判定现有数据表无法满足用户问题（unable_to_answer_advice 非空）
    2. missing_complete_node 在元数据中查不到所需字段/指标，且重试次数达到上限（unfound_count >= MAX_UNFOUND_COUNT）
    3. validate_hql_node 判定纠错轮次已达上限（correct_count >= MAX_CORRECT_COUNT）
    4. correct_hql_node 成功执行hql，但是由于业务数据缺失，导致无法统计有效结果（execute_result == []）
    """
    writer = runtime.stream_writer

    unfound_fields: list[str] = state.get('unfound_fields') or []
    correct_count: int = state.get('correct_count', 0)
    unable_to_answer_advice: str = state.get('unable_to_answer_advice') or ''
    execute_result = state.get('execute_result') or []

    if not state.get("is_relevant", True):
        answer = "您的问题与数据查询无关，我只能回答业务数据相关的问题，例如销售额、订单数、客户分析等。🤗"
    elif unable_to_answer_advice:
        answer = f"🫠 抱歉，当前数据暂不支持该查询。{unable_to_answer_advice}"
    elif unfound_fields:
        fields_str = "、".join(f"[{f}]" for f in unfound_fields)
        answer = f"当前数据源不包含所需字段 {fields_str}，无法完成该查询 🤔"
    elif correct_count >= MAX_CORRECT_COUNT:
        answer = f"HQL 经 {correct_count} 轮纠错后仍无法满足查询要求，无法完成该查询 😓"
    elif not execute_result:
        answer = "查询结果为空，暂时没有业务数据可供统计... 🧐"
    else:
        answer = "无法完成该查询，请检查查询条件或联系数据团队 📞"

    logger.warning(f"触发熔断拒答：{answer}")
    writer(answer)
