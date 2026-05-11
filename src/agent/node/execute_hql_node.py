import asyncio
from datetime import date, datetime
from decimal import Decimal

from langgraph.runtime import Runtime

from agent.schema.context_schema import EnvContext
from agent.schema.state_schema import OverallState, ExecuteState
from infra.log.logging import logger


async def execute_hql_node(state: OverallState, runtime: Runtime[EnvContext]):
    """
    HQL 执行节点
    :param state:
    :param runtime:
    :return:
    """
    writer = runtime.stream_writer
    writer("开始 HQL 执行节点，并解析最终结果")

    dw_repository = runtime.context.get('repositories').dw
    hql = state.get('hql', "").strip()
    empty_result = ExecuteState(columns=[], rows=[], row_count=0)
    if not hql:
        return {"execute_result": empty_result}

    # 只在 Hive 实际执行处兜底：HQL 错误不应中断流程，让 generate_result 给出"无结果"
    try:
        rows = await asyncio.to_thread(dw_repository.execute_query, hql)
    except Exception as e:
        logger.warning(f"HQL 执行失败（返回空结果）: {e}")
        return {"execute_result": empty_result}

    if not rows:
        return {"execute_result": empty_result}

    columns = list(rows[0].keys())
    data = [[_normalize(row.get(col)) for col in columns] for row in rows]
    execute_result = ExecuteState(columns=columns, rows=data, row_count=len(data))

    logger.info(f"HQL 执行结果: {execute_result}")
    return {"execute_result": execute_result}


def _normalize(value):
    """将 Hive 返回值统一转为 Python 基础类型，避免序列化报错"""
    if isinstance(value, float):
        return round(value, 3)
    if isinstance(value, Decimal):
        return round(float(value), 3)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value
