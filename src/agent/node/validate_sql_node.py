from langgraph.runtime import Runtime

from infra.agent.context import EnvContext
from infra.agent.state import OverallState


def validate_sql_node(state: OverallState, runtime: Runtime[EnvContext]):
    """
    SQL 校验节点
    :param state:
    :param runtime:
    :return:
    """
    writer = runtime.stream_writer
    writer("开始 SQL 校验节点")
