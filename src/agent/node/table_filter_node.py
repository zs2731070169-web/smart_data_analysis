from langgraph.runtime import Runtime

from infra.agent.context import EnvContext
from infra.agent.state import OverallState


def table_filter_node(state: OverallState, runtime: Runtime[EnvContext]):
    """
    表过滤节点
    :param state:
    :param runtime:
    :return:
    """
    writer = runtime.stream_writer
    writer("开始表过滤节点")
