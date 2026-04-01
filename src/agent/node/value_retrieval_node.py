from langgraph.runtime import Runtime

from conf.app_config import COLUMN_VALUE_INDEX
from agent.context import EnvContext
from agent.node._common import expand_keywords
from agent.state import OverallState
from infra.log.logging import logger
from utils.loader_utils import load_prompt


async def value_retrieval_node(state: OverallState, runtime: Runtime[EnvContext]):
    """
    枚举值召回节点
    :param state:
    :param runtime:
    :return:
    """
    writer = runtime.stream_writer
    writer("开始值召回节点")

    # ============== 扩展表字段值召回的关键词 =================

    keywords = await expand_keywords(
        state['question'],
        state['entities'],
        load_prompt("extend_keywords_for_value_recall.md")
    )

    logger.info(f"扩展后的字段值关键词: {keywords}")

    # ============== 从es召回字段值 =================

    value_list = []
    value_repository = runtime.context.get('repositories').value_es
    for keyword in keywords:
        # 到es中检索字段值
        values = await value_repository.search(COLUMN_VALUE_INDEX, keyword)
        value_list.extend(values)
    # 去重
    unique_value_map = {value['value']: value for value in value_list}
    unique_values = list(unique_value_map.values())

    logger.info(f"召回的字段值: {unique_value_map.keys()}")

    return {"value_list": unique_values}
