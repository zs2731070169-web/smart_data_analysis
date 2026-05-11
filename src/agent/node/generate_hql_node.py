from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langgraph.runtime import Runtime

from agent.node._common import build_table_column_text, build_metric_text, build_datetime_text, build_db_metadata_text, rewrite_question
from agent.schema.context_schema import EnvContext
from agent.schema.state_schema import OverallState
from enums.types import ErrorTypes
from infra.client import general_hql_llm
from infra.log.logging import logger
from utils.llm_retry_utils import acall_with_retry
from utils.loader_utils import load_prompt
from utils.text_utils import clean_block, extract_hql


async def generate_hql_node(state: OverallState, runtime: Runtime[EnvContext]):
    """
    HQL 生成节点
    :param state:
    :param runtime:
    :return:
    """
    writer = runtime.stream_writer
    writer("开始执行 HQL 生成节点")

    # 结构化信息转为文本
    validate_list = state.get('validates', [])
    validate_text = "".join(
        f"\nerror: {v.error}\nsuggestion: {v.suggestion}\n\n" for v in validate_list
    )

    # 是否存在字段类错误：是 → 切换到 merge 全集（升级路径，避免被过滤丢字段卡死）
    has_field_error = any(v.error_type == ErrorTypes.FIELD for v in validate_list)
    if has_field_error:
        table_column_text = build_table_column_text(state.get('merge_table_info_list', []))
        metric_text = build_metric_text(state.get('merge_metrics_info_list', []))
    else:
        table_column_text = build_table_column_text(state.get('filter_table_info_list', []))
        metric_text = build_metric_text(state.get('filter_metrics_info_list', []))

    cur_datetime_info = build_datetime_text(state.get('expand_datetime'))
    db_metadata_text = build_db_metadata_text(state.get('expand_db_metadata'))

    prompt_template = ChatPromptTemplate(
        messages=[
            {'role': 'system', 'content': load_prompt('generate_hql.md')},
            {'role': 'user',
             'content': 'question: {question}\ntable_column_list: {table_column_list}\nmetric_list: {metric_list}\ndatetime: {datetime}\ndb_metadata: {db_metadata}\nvalidate: {validate}'}
        ]
    )
    chain = prompt_template | general_hql_llm | StrOutputParser()

    # 主链路关键步骤：失败直接抛 LLMServiceError 由 chat_service 兜底，不在此处降级
    hql = await acall_with_retry(
        lambda: chain.ainvoke({
            "question": rewrite_question(state),
            "table_column_list": table_column_text,
            "metric_list": metric_text,
            "datetime": cur_datetime_info,
            "db_metadata": db_metadata_text,
            "validate": validate_text,
        }),
        op_name="generate_hql",
    )

    hql = extract_hql(clean_block(hql))
    logger.info(f"生成的SQL: {hql}")

    # 仅当本次是由校验失败回流触发时累计纠错次数；首次生成不计
    correct_count = state.get('correct_count', 0) or 0
    if validate_list:
        correct_count += 1
    return {"hql": hql, "correct_count": correct_count}
