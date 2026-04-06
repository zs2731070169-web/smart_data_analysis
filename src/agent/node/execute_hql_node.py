import asyncio
from datetime import date, datetime
from decimal import Decimal

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langgraph.runtime import Runtime

from agent.schema.context_schema import EnvContext
from agent.schema.state_schema import OverallState
from infra.client.llm_client import result_analyze_llm
from infra.log.logging import logger
from utils.loader_utils import load_prompt
from utils.text_utils import clean_code_block


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
            return {"output": []}

        rows = await asyncio.to_thread(dw_repository.execute_query, hql)

        if not rows:
            writer("HQL 执行完毕，查询结果为空")
            return {"output": []}

        result = [
            {col: _normalize(val) for col, val in row.items()}
            for row in rows
        ]

        logger.info(f"HQL 执行结果: {result}")

        prompt_template = ChatPromptTemplate(messages=[
            ("system", load_prompt("analyze_result.md")),
            ("user", "{result}")
        ])
        chain = prompt_template | result_analyze_llm | JsonOutputParser()
        final_result = await chain.ainvoke({"result": result})

        # 进一步去掉代码块
        if isinstance(final_result, str):
            final_result = clean_code_block(final_result)

        logger.info(f"最终解析结果：{final_result}")

        writer({"output": final_result})

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
