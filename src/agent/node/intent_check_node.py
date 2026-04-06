from langgraph.runtime import Runtime

from agent.schema.context_schema import EnvContext
from agent.schema.state_schema import InputState
from infra.client.llm_client import filter_llm
from infra.log.logging import logger
from utils.loader_utils import load_prompt


async def intent_check_node(state: InputState, runtime: Runtime[EnvContext]) -> dict:
    """
    判断用户意图节点，过滤和数据分析查询无关问题
    :param state:
    :param runtime:
    :return:
    """
    writer = runtime.stream_writer
    writer('开始执行意图识别')

    try:
        question = state["question"]
        resp = await filter_llm.ainvoke([
            {"role": "system", "content": load_prompt("intent_check.md")},
            {"role": "user", "content": question},
        ])
        is_relevant = resp.content.strip().upper().startswith("YES")

        logger.info(f"意图识别结果: {'相关' if is_relevant else '无关'} | 问题: {question}")

        return {"is_relevant": is_relevant}
    except Exception as e:
        logger.error(f"意图识别失败: {str(e)}")
        raise Exception('意图识别失败，请检查 Hive 连接或联系数据团队😿')
