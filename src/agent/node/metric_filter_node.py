from langgraph.runtime import Runtime

from agent.context import EnvContext
from agent.state import OverallState


def metric_filter_node(state: OverallState, runtime: Runtime[EnvContext]):
    """
    指标过滤节点
    :param state:
    :param runtime:
    :return:
    """
    writer = runtime.stream_writer
    writer("开始指标过滤节点")
