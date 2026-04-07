import asyncio
from datetime import date, datetime
from decimal import Decimal

from langgraph.runtime import Runtime

from agent.schema.context_schema import EnvContext
from agent.schema.state_schema import OverallState
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

    try:
        dw_repository = runtime.context.get('repositories').dw
        hql = state.get('hql', "").strip()
        if not hql:
            return {"execute_result": []}

        rows = await asyncio.to_thread(dw_repository.execute_query, hql)

        if not rows:
            return {"execute_result": []}

        execute_result = [
            {col: _normalize(val) for col, val in row.items()}
            for row in rows
        ]

        logger.info(f"HQL 执行结果: {execute_result}")

        return {"execute_result": execute_result}
    except Exception as e:
        logger.error(f"HQL 执行失败: {str(e)}")
        raise Exception('查询执行失败，请检查HQL或联系数据团队😿')


def _normalize(value):
    """将 Hive 返回值统一转为 Python 基础类型，避免序列化报错"""
    if isinstance(value, float):
        return round(value, 3)
    if isinstance(value, Decimal):
        return round(float(value), 3)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value
