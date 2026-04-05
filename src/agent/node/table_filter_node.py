from langgraph.runtime import Runtime

from agent.node._common import filter_columns_or_metrics, build_table_column_text
from agent.schema.context_schema import EnvContext
from agent.schema.llm_schema import TableColumnInfo
from agent.schema.state_schema import OverallState
from infra.log.logging import logger
from utils.loader_utils import load_prompt


async def table_filter_node(state: OverallState, runtime: Runtime[EnvContext]):
    """
    表过滤节点
    :param state:
    :param runtime:
    :return:
    """
    writer = runtime.stream_writer
    writer("开始执行表过滤节点")

    # 把合并以后的表-字段列表构转为文本
    table_info_list = state.get('merge_table_info_list', [])
    table_info_text = build_table_column_text(table_info_list)

    # 使用模型对召回的表进行过滤，得到最终的相关表列表
    selected_table_columns = await filter_columns_or_metrics(
        {"question": state.get('question'), "context": table_info_text},
        system_prompt=load_prompt("filter_table_info.md"),
        schema_cls=TableColumnInfo
    )

    # selected_table_columns转为table_name->columns字典映射
    selected_table_column_map = {selected_table.table_name: selected_table.columns for selected_table in
                                 selected_table_columns.tables}

    # 收集一个表名列表
    selected_table_name_list = [selected_table.table_name for selected_table in selected_table_columns.tables]

    filter_table_info_list = []

    # 对合并后的table_info_list进行筛选
    for table_info in table_info_list:
        # 如果合并的表名在被选中的表名列表里就保留
        if table_info.name in selected_table_name_list:
            # 进一步判断该表的字段是否被选中，把被选中的字段保留，并作为新的字段列表添加到表信息
            columns = selected_table_column_map[table_info.name]
            table_info.columns = [column for column in table_info.columns if column.name in columns]
            filter_table_info_list.append(table_info)

    logger.info(f"表过滤完成后的字段列表: {[
        table_info.name + ':' +
        ','.join([column.name for column in table_info.columns])
        for table_info in filter_table_info_list
    ]}")

    return {"filter_table_info_list": filter_table_info_list}
