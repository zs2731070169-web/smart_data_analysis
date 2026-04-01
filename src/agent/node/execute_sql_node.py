from langgraph.runtime import Runtime

from agent.context import EnvContext
from agent.state import OverallState


def execute_sql_node(state: OverallState, runtime: Runtime[EnvContext]):
    """
    SQL 执行节点
    :param state:
    :param runtime:
    :return:
    """
    writer = runtime.stream_writer
    writer("开始 SQL 执行节点")
