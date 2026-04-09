import asyncio
import re
from typing import Literal

from langchain_core.prompts import PromptTemplate, ChatPromptTemplate
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
            error=_build_hive_error_message(error_str),
            error_type=_classify_hive_error(error_str)  # 抛出上下文错误或语法错误，供后续 missing_complete_node 进行区分处理
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
        prompt_template = ChatPromptTemplate(
            messages=[
                {'role': 'system', 'content': load_prompt('validate_hql_system.md')},
                {'role': 'user', 'content': load_prompt('validate_hql_user.md')}
            ]
        )
        chain = (prompt_template
                 | validate_hql_llm.with_structured_output(schema=ValidateResult, method='function_calling'))
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
        raise Exception('HQL 语义校验失败，请稍后重试或联系数据团队')

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

    - context_missing：字段在上下文/数据库中不存在（10002/10004），
                       应交由 missing_complete_node 处理补全或触发熔断。
    - syntax：纯语法/解析错误，以及表名不存在（10001，通常是 CTE/子查询别名引用问题），
              与字段补全无关，应直接交由 correct_hql_node 修复。

    注意：HAVING 引用 SELECT 别名也会触发 10004，但属于语法问题，不应进入字段补全流程。
    """
    # HAVING 引用别名触发的 10004 本质是语法错误，不应进入字段补全
    if re.search(r"Invalid column reference|Invalid table alias or column reference", error_str):
        if "HAVING" in error_str.upper():
            return "syntax"

    match = re.search(r'errorCode=(\d+)', error_str)
    if match:
        code = int(match.group(1))
        if code in (10002, 10004):
            # 10002: Invalid column reference
            # 10004: Invalid table alias or column reference
            return "context_missing"
    return "syntax"


def _build_hive_error_message(error_str: str) -> str:
    """
    从 Hive 异常信息中提取关键内容，生成简洁的错误描述，供纠错节点自主分析修复。
    """
    # 10001: Table not found
    match_table = re.search(r"Table not found '([^']+)'", error_str)
    if match_table:
        table_name = match_table.group(1)
        return (
            f"HQL 引用了不存在的表 '{table_name}'，该表名不在元数据列表中，"
            f"需重新结合「可用数据表与字段」确认正确的表名。\n"
            f"严禁猜测或编造新表名，必须从以上表出发用子查询或窗口函数重建所需逻辑。"
        )

    # 10002/10004: 字段引用错误
    match_col = re.search(r"(?:Invalid column reference|Invalid table alias or column reference) '([^']+)'", error_str)
    if match_col:
        col_name = match_col.group(1)
        if "HAVING" in error_str.upper():
            return (
                f"HQL 在 HAVING 子句中引用了 SELECT 别名 '{col_name}'，"
                f"Hive 不支持在 HAVING 中使用 SELECT 别名，须替换为完整聚合表达式。"
            )
        return f"HQL 引用了不存在的字段或表别名 '{col_name}'，请检查字段名拼写及表别名是否正确。"

    # ParseException: AS 后无法识别 — 中文别名或保留字别名未加反引号
    if "ParseException" in error_str and "cannot recognize input near 'AS'" in error_str:
        match_token = re.search(r"cannot recognize input near 'AS' '([^']+)'", error_str)
        token = match_token.group(1) if match_token else None
        hive_reserved = {
            "date", "year", "month", "day", "hour", "minute", "second",
            "count", "sum", "avg", "max", "min", "value", "key", "table",
            "select", "from", "where", "group", "order", "having", "limit",
            "join", "left", "right", "inner", "outer", "on", "as", "by",
            "asc", "desc", "and", "or", "not", "in", "is", "null", "true", "false"
        }
        if token and token.lower() in hive_reserved:
            return f"HQL 使用了 Hive 保留字 '{token}' 作为列别名，保留字用作别名时必须加反引号包裹。"
        return "HQL 中存在中文或特殊字符列别名未用反引号包裹，Hive 要求此类别名必须加反引号。"

    # DISTINCT 用于窗口函数
    if "Not yet supported place for DISTINCT" in error_str:
        return "HQL 在窗口函数中使用了 COUNT(DISTINCT x) OVER(...)，Hive 不支持此写法，需改用子查询先去重再聚合。"

    # LIMIT 在子查询中不支持
    if "ParseException" in error_str and "LIMIT" in error_str and "subquery" in error_str.lower():
        return "HQL 在子查询中使用了 LIMIT，Hive 不支持子查询内的 LIMIT，需改用 ROW_NUMBER() OVER(...) 做行号过滤。"

    # UNION ALL 列数不一致
    if "ParseException" in error_str and "UNION" in error_str:
        return "HQL 中 UNION ALL 两侧的 SELECT 列数或类型不一致，须确保各子句列数相同且对应列类型兼容。"

    # 类型不匹配
    if "type mismatch" in error_str.lower():
        return "HQL 存在类型不匹配错误，常见原因是 NVL/COALESCE 的参数类型不一致，须对相关参数显式 CAST。"

    # 通用兜底
    hive_msg_match = re.search(r'errorMessage="([^"]+)"', error_str)
    if hive_msg_match:
        return f"HQL 语法错误：{hive_msg_match.group(1)}。"
    return f"HQL 语法错误：{error_str}"


async def _judge_error_item(item: ErrorItem) -> bool:
    """使用轻量模型裁决 ErrorItem 是真实错误还是幻觉确认"""
    prompt = PromptTemplate(
        template=load_prompt("judge_error.md"),
        input_variables=["error"]
    )
    chain = prompt | judge_llm.with_structured_output(schema=ErrorJudge, method='function_calling')
    result = await chain.ainvoke({'error': item.error})
    is_error = result.is_real_error
    return is_error
