from langgraph.runtime import Runtime

from infra.agent.context import EnvContext
from infra.agent.state import OverallState


def expand_node(state: OverallState, runtime: Runtime[EnvContext]):
    """
    字段扩展节点
    :param state:
    :param runtime:
    :return:
    """
    writer = runtime.stream_writer
    writer("开始扩展节点")
