from langgraph.runtime import Runtime

from agent.schema.context_schema import EnvContext
from agent.schema.state_schema import OverallState
from infra.log.logging import logger


async def clarify_node(state: OverallState, runtime: Runtime[EnvContext]):
    """
    追问节点：当意图识别发现用户问题存在关键歧义时，将追问内容推送给前端，
    由前端展示给用户，用户补充后重新发起请求。
    :param state:
    :param runtime:
    """
    writer = runtime.stream_writer
    clarification_question = state.get("clarification_question", "")
    logger.info(f"触发追问节点，追问内容：{clarification_question}")
    writer(clarification_question)
