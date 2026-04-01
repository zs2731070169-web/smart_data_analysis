import uuid

from langgraph.constants import START, END
from langgraph.graph import StateGraph

from agent.context import EnvContext
from agent.node.column_retrieval_node import column_retrieval_node
from agent.node.correct_sql_node import correct_sql_node
from agent.node.entity_extract_node import entity_extract
from agent.node.execute_sql_node import execute_sql_node
from agent.node.expand_node import expand_node
from agent.node.generate_sql_node import generate_sql_node
from agent.node.merge_node import merge_node
from agent.node.metric_filter_node import metric_filter_node
from agent.node.metrics_retrieval_node import metrics_retrieval_node
from agent.node.table_filter_node import table_filter_node
from agent.node.validate_sql_node import validate_sql_node
from agent.node.value_retrieval_node import value_retrieval_node
from agent.state import OverallState, InputState
from infra.factory.repository_factory import repository_factory
from infra.log import task_id_context
from infra.manager.embedding_client import embedding_manager

# 创建图
builder = StateGraph(
    input_schema=InputState,
    state_schema=OverallState,
    context_schema=EnvContext)

builder.add_node(node="entity_extract", action=entity_extract)
builder.add_node(node="column_retrieval_node", action=column_retrieval_node)
builder.add_node(node="metrics_retrieval_node", action=metrics_retrieval_node)
builder.add_node(node="value_retrieval_node", action=value_retrieval_node)
builder.add_node(node="merge_node", action=merge_node)
builder.add_node(node="table_filter_node", action=table_filter_node)
builder.add_node(node="metric_filter_node", action=metric_filter_node)
builder.add_node(node="expand_node", action=expand_node)
builder.add_node(node="generate_sql_node", action=generate_sql_node)
builder.add_node(node="validate_sql_node", action=validate_sql_node)
builder.add_node(node="correct_sql_node", action=correct_sql_node)
builder.add_node(node="execute_sql_node", action=execute_sql_node)

builder.add_edge(start_key=START, end_key="entity_extract")
builder.add_edge(start_key="entity_extract", end_key="column_retrieval_node")
builder.add_edge(start_key="entity_extract", end_key="metrics_retrieval_node")
builder.add_edge(start_key="entity_extract", end_key="value_retrieval_node")
builder.add_edge(
    start_key=["column_retrieval_node", "metrics_retrieval_node", "value_retrieval_node"],
    end_key="merge_node")
builder.add_edge(start_key="merge_node", end_key="table_filter_node")
builder.add_edge(start_key="merge_node", end_key="metric_filter_node")
builder.add_edge(start_key=["table_filter_node", "metric_filter_node"], end_key="expand_node")
builder.add_edge(start_key="expand_node", end_key="generate_sql_node")
builder.add_edge(start_key="generate_sql_node", end_key="validate_sql_node")
builder.add_conditional_edges(
    source="validate_sql_node",
    path=lambda state: "execute_sql" if not state.get("error") else "correct_sql",
    path_map={"execute_sql": "execute_sql_node", "correct_sql": "correct_sql_node"}
)
builder.add_edge(start_key="correct_sql_node", end_key="validate_sql_node")
builder.add_edge(start_key="execute_sql_node", end_key=END)

graph = builder.compile()

if __name__ == '__main__':
    import asyncio


    # print(graph.get_graph().draw_mermaid())

    async def test():
        task_id_context.set(uuid.uuid4().hex)
        async with repository_factory as repositories:
            async for chunk in graph.astream(
                    input=InputState(question="统计去年重庆地区销售额最高的前5个产品"),
                    context=EnvContext(
                        repositories=repositories,
                        embedding_client=embedding_manager.embedding_client
                    ),
                    stream_mode="custom"
            ):
                print(chunk)


    asyncio.run(test())
