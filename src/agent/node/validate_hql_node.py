import asyncio

from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate
from langgraph.runtime import Runtime

from agent.node._common import build_table_column_text, build_metric_text, build_datetime_text, build_db_metadata_text
from agent.schema.context_schema import EnvContext
from agent.schema.llm_schema import ValidateResult
from agent.schema.state_schema import OverallState, ValidateState
from enums.types import ErrorTypes
from infra.client import validate_hql_llm
from infra.log.logging import logger
from utils.loader_utils import load_prompt


async def validate_hql_node(state: OverallState, runtime: Runtime[EnvContext]):
    """
    HQL 校验节点
    :param state:
    :param runtime:
    :return:
    """
    writer = runtime.stream_writer
    writer("开始执行 HQL 校验节点")

    hql = state.get('hql')

    validates: list[ValidateState] = []

    # 基础语法校验
    dw_repository = runtime.context.get('repositories').dw
    try:
        await asyncio.to_thread(dw_repository.validate, hql)
    except Exception as e:
        error_str = str(e)
        logger.warning(f"HQL 基础语法校验失败: {error_str}")
        validates += [
            ValidateState(
                error=f"【语法规范】HQL 基础语法校验未通过：{error_str}",
                suggestion="请根据数据库方言修正语法错误后重试",
                error_type=ErrorTypes.SYNTAX,
                is_valid=False,
            )
        ]

    # 构建过滤后的表字段文本
    table_column_text = build_table_column_text(state.get('filter_table_info_list', []))

    # 构建过滤后的指标列表信息文本
    metric_text = build_metric_text(state.get('filter_metrics_info_list', []))

    # 构建当前时间和数据库元信息文本
    cur_datetime_info = build_datetime_text(state.get('expand_datetime'))
    db_metadata_text = build_db_metadata_text(state.get('expand_db_metadata'))

    # 使用大模型进行意图校验
    try:
        prompt_template = ChatPromptTemplate(
            messages=[
                {'role': 'system', 'content': load_prompt('validate_hql.md')},
                {'role': 'user',
                 'content': 'question: {question}\ntable_column_list: {table_column_list}\nmetric_list: {metric_list}\ndatetime: {datetime}\ndb_metadata: {db_metadata}\nhql: {hql}'}
            ]
        )
        prompt = prompt_template.invoke(
            {
                "table_column_list": table_column_text,
                "metric_list": metric_text,
                "datetime": cur_datetime_info,
                "db_metadata": db_metadata_text,
                "hql": hql,
                "question": state.get('question'),
            }
        )

        llm_with_structured_output = validate_hql_llm.with_structured_output(schema=ValidateResult,
                                                                             method='function_calling')

        raw_output: ValidateResult = await llm_with_structured_output.ainvoke(input=prompt)

        validates += [
            ValidateState(error=item.error, suggestion=item.suggestion, error_type=item.error_type,
                          is_valid=item.is_valid)
            for item in raw_output.errors
            if not item.is_valid
        ]


    except Exception as e:
        logger.error(f"HQL 语义校验失败: {str(e)}")
        raise Exception('HQL 语义校验失败，请稍后重试或联系数据团队')

    # 打印 HQL 校验结果汇总
    if not validates:
        logger.info(f"HQL 校验通过 | hql={hql}")
    else:
        logger.warning(f"HQL 校验未通过，共 {len(validates)} 项错误 | hql={hql}")
        for idx, item in enumerate(validates, 1):
            logger.warning(
                f"  [{idx}/{len(validates)}] is_valid={item.is_valid} | "
                f"error={item.error} | suggestion={item.suggestion}"
            )

    return {"validates": validates}
