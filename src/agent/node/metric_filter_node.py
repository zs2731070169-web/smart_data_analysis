from langgraph.runtime import Runtime

from agent.node._common import filter_columns_or_metrics, build_metric_text, rewrite_question
from agent.schema.context_schema import EnvContext
from agent.schema.llm_schema import MetricInfo
from agent.schema.state_schema import OverallState
from infra.log.logging import logger
from utils.loader_utils import load_prompt


async def metric_filter_node(state: OverallState, runtime: Runtime[EnvContext]):
    """
    指标过滤节点
    :param state:
    :param runtime:
    :return:
    """
    writer = runtime.stream_writer
    writer("开始执行指标过滤节点")

    metrics_info_list = state.get('merge_metrics_info_list')
    metrics_info_text = build_metric_text(metrics_info_list)

    # 使用模型对召回的指标进行过滤
    selected_metrics = await filter_columns_or_metrics(
        {"question": rewrite_question(state), "context": metrics_info_text},
        system_prompt=load_prompt("filter_metric_info.md"),
        schema_cls=MetricInfo
    )

    for metrics_info in metrics_info_list[:]:
        if metrics_info.name not in selected_metrics.metrics:
            metrics_info_list.remove(metrics_info)

    logger.info(f"过滤后的指标列表: {[metrics_info.name for metrics_info in metrics_info_list]}")
    return {"filter_metrics_info_list": metrics_info_list}
