from langgraph.runtime import Runtime

from conf.app_config import META_TABLE_COLUMN_COLLECTION
from agent.schema.context_schema import EnvContext
from agent.node._common import expand_keywords, qdrant_retrieval
from agent.schema.state_schema import OverallState
from infra.log.logging import logger
from utils.loader_utils import load_prompt


async def column_retrieval_node(state: OverallState, runtime: Runtime[EnvContext]):
    """
    字段召回节点
    :param state:
    :param runtime:
    :return:
    """
    writer = runtime.stream_writer
    writer("开始执行字段召回节点")

    # ============== 扩展用于表字段召回的关键词 =================

    keywords = await expand_keywords(
        state['question'],
        state['entities'],
        load_prompt("extend_keywords_for_column_recall.md")
    )

    logger.info(f"扩展后的表字段关键词: {keywords}")

    # ============== 从qdrant召回字段元数据 =================

    unique_column_list = await qdrant_retrieval(
        collection_name=META_TABLE_COLUMN_COLLECTION,
        keywords=keywords,
        meta_qdrant_repository=runtime.context.get('repositories').meta_qdrant,
        embedding_client=runtime.context.get('embedding_client')
    )

    return {"retrieval_column_list": unique_column_list}
