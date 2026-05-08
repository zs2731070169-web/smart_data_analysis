from langgraph.constants import START, END
from langgraph.graph import StateGraph

from agent.node.column_retrieval_node import column_retrieval_node
from agent.node.entity_extract_node import entity_extract_node
from agent.node.execute_hql_node import execute_hql_node
from agent.node.expand_node import expand_node
from agent.node.generate_hql_node import generate_hql_node
from agent.node.generate_result_node import generate_result_node
from agent.node.intent_check_node import intent_check_node
from agent.node.merge_node import merge_node
from agent.node.metric_filter_node import metric_filter_node
from agent.node.metrics_retrieval_node import metrics_retrieval_node
from agent.node.table_filter_node import table_filter_node
from agent.node.validate_hql_node import validate_hql_node
from agent.node.value_retrieval_node import value_retrieval_node
from agent.schema.context_schema import EnvContext
from agent.schema.state_schema import OverallState, InputState, ValidateState
from infra.log.logging import logger

# 创建图
builder = StateGraph(
    input_schema=InputState,
    state_schema=OverallState,
    context_schema=EnvContext)

builder.add_node(node="intent_check_node", action=intent_check_node)
builder.add_node(node="entity_extract_node", action=entity_extract_node)
builder.add_node(node="column_retrieval_node", action=column_retrieval_node)
builder.add_node(node="metrics_retrieval_node", action=metrics_retrieval_node)
builder.add_node(node="value_retrieval_node", action=value_retrieval_node)
builder.add_node(node="merge_node", action=merge_node)
builder.add_node(node="table_filter_node", action=table_filter_node)
builder.add_node(node="metric_filter_node", action=metric_filter_node)
builder.add_node(node="expand_node", action=expand_node)
builder.add_node(node="generate_hql_node", action=generate_hql_node)
builder.add_node(node="validate_hql_node", action=validate_hql_node)
builder.add_node(node="execute_hql_node", action=execute_hql_node)
builder.add_node(node="generate_result_node", action=generate_result_node)

builder.add_edge(start_key=START, end_key="intent_check_node")


def route_intent_check(state: OverallState) -> str:
    """
    意图识别后的路由：
    - 无关问题 → 直接结束（已在节点内推送拒答）
    - 需用户补充 → 直接结束（已推送追问，等待用户重新发起）
    - 相关且明确 → 继续抽实体进入主流程
    """
    if not state.get("is_relevant"):
        return "end"
    if state.get("clarification_question"):
        return "end"
    return "continue"


builder.add_conditional_edges(
    source="intent_check_node",
    path=route_intent_check,
    path_map={"continue": "entity_extract_node", "end": END},
)
builder.add_edge(start_key="entity_extract_node", end_key="column_retrieval_node")
builder.add_edge(start_key="entity_extract_node", end_key="metrics_retrieval_node")
builder.add_edge(start_key="entity_extract_node", end_key="value_retrieval_node")
builder.add_edge(
    start_key=["column_retrieval_node", "metrics_retrieval_node", "value_retrieval_node"],
    end_key="merge_node")
builder.add_edge(start_key="merge_node", end_key="table_filter_node")
builder.add_edge(start_key="merge_node", end_key="metric_filter_node")
builder.add_edge(start_key=["table_filter_node", "metric_filter_node"], end_key="expand_node")
builder.add_edge(start_key="expand_node", end_key="generate_hql_node")
builder.add_edge(start_key="generate_hql_node", end_key="validate_hql_node")

# generate→validate 纠错回路的最大次数
MAX_CORRECT_LOOPS = 15


def route_validate_hql(state: OverallState) -> str:
    validates: list[ValidateState] = state.get("validates") or []
    has_error = any(not validate.is_valid for validate in validates)
    if not has_error:
        return "execute_hql"
    correct_count = state.get("correct_count", 0) or 0
    if correct_count >= MAX_CORRECT_LOOPS:
        logger.warning(
            f"HQL 纠错回路达到上限 {MAX_CORRECT_LOOPS} 次，仍未通过校验，直接结束流程"
        )
        return "end"
    return "generate_hql"


builder.add_conditional_edges(
    source="validate_hql_node",
    path=route_validate_hql,
    path_map={
        "execute_hql": "execute_hql_node",
        "generate_hql": "generate_hql_node",
        "end": END,
    },
)
builder.add_edge(start_key="execute_hql_node", end_key="generate_result_node")
builder.add_edge(start_key="generate_result_node", end_key=END)

graph = builder.compile()

if __name__ == '__main__':
    print(graph.get_graph().draw_mermaid())
