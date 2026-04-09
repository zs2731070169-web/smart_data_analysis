from langgraph.runtime import Runtime

from agent.schema.context_schema import EnvContext
from agent.schema.llm_schema import IntentCheckResult
from agent.schema.state_schema import InputState
from infra.client.llm_client import filter_llm
from infra.log.logging import logger
from utils.loader_utils import load_prompt


async def intent_check_node(state: InputState, runtime: Runtime[EnvContext]) -> dict:
    """
    判断用户意图节点，过滤和数据分析查询无关问题；
    对相关但存在关键歧义的问题，生成追问内容，交由 clarify_node 推送给用户。
    :param state:
    :param runtime:
    :return:
    """
    writer = runtime.stream_writer
    writer('开始执行意图识别')

    try:
        question = state["question"]
        chain = filter_llm.with_structured_output(schema=IntentCheckResult, method='function_calling')
        result: IntentCheckResult = await chain.ainvoke([
            {"role": "system", "content": load_prompt("intent_check.md")},
            {"role": "user", "content": question},
        ])

        logger.info(
            f"意图识别结果: "
            f"{'相关' if result.is_relevant else '无关'} | "
            f"{'需追问' if result.needs_clarification else '无需追问'} | "
            f"问题: {question}"
        )

        return {
            "is_relevant": result.is_relevant,
            "clarification_question": result.clarification_question if result.needs_clarification else "",
        }
    except Exception as e:
        logger.error(f"意图识别失败: {str(e)}")
        raise Exception('意图识别失败，请检查 Hive 连接或联系数据团队😿')
