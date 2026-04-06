import asyncio
import re
from typing import Literal

from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from agent.node._common import build_table_column_text, build_metric_text, build_datetime_text, build_db_metadata_text
from agent.schema.context_schema import EnvContext
from agent.schema.llm_schema import ValidateResult, ErrorItem, ErrorJudge
from agent.schema.state_schema import OverallState
from infra.client.llm_client import validate_hql_llm, judge_llm
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

    validates: list[ErrorItem] = []

    # 基础语法校验
    dw_repository = runtime.context.get('repositories').dw
    try:
        await asyncio.to_thread(dw_repository.validate, hql)
    except Exception as e:
        error_str = str(e)
        logger.warning(f"HQL 基础语法校验失败: {error_str}")
        validates.append(ErrorItem(
            error=error_str,
            suggestion="HQL语法错误，请进一步审查和修正HQL",
            error_type=_classify_hive_error(error_str) # 抛出上下文错误或语法错误，供后续 missing_complete_node 进行区分处理
        ).model_dump())
        return {"validates": validates}

    # 构建过滤后的表字段文本
    table_column_text = build_table_column_text(state.get('filter_table_info_list', []))

    # 构建过滤后的指标列表信息文本
    metric_text = build_metric_text(state.get('filter_metrics_info_list', []))

    # 构建当前时间和数据库元信息文本
    cur_datetime_info = build_datetime_text(state.get('expand_datetime'))
    db_metadata_text = build_db_metadata_text(state.get('expand_db_metadata'))

    # 使用大模型进行意图校验
    try:
        prompt_template = PromptTemplate(
            template=load_prompt("validate_hql.md"),
            input_variables=['question', 'table_column_list', 'metric_list', 'datetime', 'db_metadata', 'hql']
        )
        chain = prompt_template | validate_hql_llm.with_structured_output(schema=ValidateResult, method='function_calling')
        raw_output = await chain.ainvoke(
            {
                "question": state.get('question'),
                "table_column_list": table_column_text,
                "metric_list": metric_text,
                "datetime": cur_datetime_info,
                "db_metadata": db_metadata_text,
                "hql": hql
            }
        )

        # 判断模型输出是否为真实错误
        if raw_output.errors:
            for index, error in enumerate(raw_output.errors, 1):
                valid = await _judge_error_item(error)
                validates += [error] if valid else []
                logger.info(f"裁决错误项结果 {index}: {'真实错误' if valid else '幻觉输出'}")

    except Exception as e:
        logger.error(f"HQL 语义校验失败: {str(e)}")
        raise Exception('HQL 语义校验失败，请稍后重试或联系数据团队😿')

    # 根据条件解析为字典
    errors = []
    if not validates:
        logger.info("HQL 语义校验通过")
    else:
        logger.warning(f"HQL 语义校验发现问题: {validates}")
        # validates转字典列表
        for error_item in validates:
            errors.append(error_item.model_dump())

    return {"validates": errors}


def _classify_hive_error(error_str: str) -> Literal["syntax", "context_missing"]:
    """
    根据 Hive 异常内容判断错误类型。

    - context_missing：字段或表在上下文/数据库中不存在（10002/10004/10001），
                       应交由 missing_complete_node 处理补全或触发熔断。
    - syntax：纯语法/解析错误（40000 ParseException 等），
              与上下文无关，应直接交由 correct_hql_node 修复。
    """
    # 提取 Hive errorCode
    match = re.search(r'errorCode=(\d+)', error_str)
    if match:
        code = int(match.group(1))
        if code in (10001, 10002, 10004):
            # 10001: Table not found
            # 10002: Invalid column reference
            # 10004: Invalid table alias or column reference
            return "context_missing"
    return "syntax"


async def _judge_error_item(item: ErrorItem) -> bool:
    """使用轻量模型裁决 ErrorItem 是真实错误还是幻觉确认"""
    prompt = PromptTemplate(
        template=load_prompt("judge_error.md"),
        input_variables=["error", "suggestion"]
    )
    chain = prompt | judge_llm.with_structured_output(schema=ErrorJudge, method='function_calling')
    result = await chain.ainvoke({'error': item.error, 'suggestion': item.suggestion})
    is_error = result.is_real_error
    return is_error
