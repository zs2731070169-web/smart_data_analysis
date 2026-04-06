from langgraph.runtime import Runtime

from conf.app_config import META_METRICS_COLLECTION
from agent.schema.context_schema import EnvContext
from agent.node._common import expand_keywords, qdrant_retrieval
from agent.schema.state_schema import OverallState
from infra.log.logging import logger
from utils.loader_utils import load_prompt


async def metrics_retrieval_node(state: OverallState, runtime: Runtime[EnvContext]):
    """
    指标召回节点
    :param state:
    :param runtime:
    :return:
    """
    writer = runtime.stream_writer
    writer("开始执行指标召回节点")

    try:
        # ============== 扩展指标召回的关键词 =================

        keywords = await expand_keywords(
            state['question'],
            state['entities'],
            load_prompt("extend_keywords_for_metric_recall.md")
        )

        logger.info(f"扩展后的指标关键词: {keywords}")

        # ============== 从qdrant召回指标元数据 =================

        unique_metrics_list = await qdrant_retrieval(
            collection_name=META_METRICS_COLLECTION,
            keywords=keywords,
            meta_qdrant_repository=runtime.context.get('repositories').meta_qdrant,
            embedding_client=runtime.context.get('embedding_client')
        )

        return {"retrieval_metrics_list": unique_metrics_list}

    except Exception as e:
        logger.error(f"指标召回失败: {str(e)}")
        raise Exception('指标召回失败，请稍后重试或联系数据团队😿')
