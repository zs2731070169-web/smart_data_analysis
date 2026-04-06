from langgraph.runtime import Runtime

from agent.node._common import build_table_column_text, build_metric_text, build_datetime_text, build_db_metadata_text, \
    generate_hql
from agent.schema.context_schema import EnvContext
from agent.schema.state_schema import OverallState
from infra.log.logging import logger
from utils.loader_utils import load_prompt


async def generate_hql_node(state: OverallState, runtime: Runtime[EnvContext]):
    """
    HQL 生成节点
    :param state:
    :param runtime:
    :return:
    """
    writer = runtime.stream_writer
    writer("开始执行 HQL 生成节点")

    try:
        # 构建过滤后的表字段文本
        table_column_text = build_table_column_text(state.get('filter_table_info_list', []))

        # 构建过滤后的指标列表信息文本
        metric_text = build_metric_text(state.get('filter_metrics_info_list', []))

        # 构建当前时间和数据库元信息文本
        cur_datetime_info = build_datetime_text(state.get('expand_datetime'))
        db_metadata_text = build_db_metadata_text(state.get('expand_db_metadata'))

        hql = await generate_hql(
            query={
                "question": state.get('question'),
                "table_column_list": table_column_text,
                "metric_list": metric_text,
                "datetime": cur_datetime_info,
                "db_metadata": db_metadata_text
            },
            variables=['question', 'table_column_list', 'metric_list', 'datetime', 'db_metadata'],
            system_prompt=load_prompt("generate_hql.md")
        )

        logger.info(f"生成的SQL: {hql}")

        return {"hql": hql}

    except Exception as e:
        logger.error(f"HQL 生成失败: {str(e)}")
        raise Exception('HQL 生成失败，请稍后重试或联系数据团队😿')
