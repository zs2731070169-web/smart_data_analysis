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
    writer("开始执行 HQL 执行节点")

    try:
        dw_repository = runtime.context.get('repositories').dw
        hql = state.get('hql', "").strip()
        if not hql:
            return {"output": []}

        rows = await asyncio.to_thread(dw_repository.execute_query, hql)

        if not rows:
            writer("HQL 执行完毕，查询结果为空")
            return {"output": []}

        # 解析结果：None转为'', Decimal/float 保留3位小数，date/datetime 转 ISO 字符串
        result = [
            {col: _normalize(val) for col, val in row.items()}
            for row in rows
        ]

        logger.info(f"HQL 执行结果: {result}")
        return {"output": result, 'answer': '执行成功，已返回查询结果'}

    except Exception as e:
        logger.error(f"HQL 执行失败: {str(e)}")
        return {"output": [], 'answer': '查询执行失败，请检查HQL或联系数据团队'}


def _normalize(value):
    """将 Hive 返回值统一转为 Python 基础类型"""
    if value is None:
        return ''
    if isinstance(value, float):
        return round(value, 3)
    if isinstance(value, Decimal):
        return round(float(value), 3)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value
