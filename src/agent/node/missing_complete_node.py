import asyncio
import re

from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from agent.node._common import build_table_column_text, build_metric_text
from agent.schema.context_schema import EnvContext
from agent.schema.llm_schema import ColumnCompleteInfo, MissingInfo
from agent.schema.state_schema import MetricState, TableColumnState
from agent.schema.state_schema import OverallState, TableState
from conf.app_config import MISSING_COMPLETE_BACKOFF_BASE, \
    MISSING_COMPLETE_BACKOFF_MAX
from infra.client.llm_client import column_complete_llm
from infra.log.logging import logger
from utils.loader_utils import load_prompt


async def missing_complete_node(state: OverallState, runtime: Runtime[EnvContext]):
    """
    HQL 字段/指标补全节点：根据校验结果，用来弥补上下文当中缺失字段或指标的兜底节点
    :param state:
    :param runtime:
    :return:
    """
    writer = runtime.stream_writer
    writer("开始执行 HQL 字段/指标补全节点")

    validates = state.get('validates')

    # 没有错误验证就跳过后续步骤
    if not validates:
        logger.info("没有校验错误，跳过字段补全节点")
        return {}

    # 非"字段/指标缺失"错误就跳过
    context_missing_validates = [validate for validate in validates if validate.get('error_type') == 'context_missing']
    if not context_missing_validates:
        return {}

    # 指数退避等待，避免频繁请求
    unfound_count = state.get('unfound_count', 0)
    if unfound_count > 0:
        delay = min(MISSING_COMPLETE_BACKOFF_BASE * (2 ** (unfound_count - 1)), MISSING_COMPLETE_BACKOFF_MAX)
        logger.info(f"指数退避等待 {delay}s（第 {unfound_count} 次字段查不到）")
        await asyncio.sleep(delay)

    meta_repository = runtime.context.get('repositories').meta

    filter_table_info_list: list[TableState] = state.get('filter_table_info_list')
    filter_metrics_info_list: list[MetricState] = state.get('filter_metrics_info_list')

    # 分类收集hive语法校验和LLM校验抛出的错误
    hive_errors = []
    llm_errors = []
    for validate in context_missing_validates:
        if validate.get('suggestion') == 'HQL语法错误，请进一步审查和修正HQL':
            hive_errors.append(validate)
        else:
            llm_errors.append(validate)

    missing_list: list[MissingInfo] = []

    # Hive抛出的上下文缺失，直接从固定异常文本提取
    for error in hive_errors:
        for field in _extract_fields(error.get('error', '')):
            missing_list.append(MissingInfo(name=field, type='column'))

    logger.info(f"从Hive编译校验错误提取到缺失字段/指标：{[m.name for m in missing_list]}")

    # LLM校验抛出的上下文缺失，使用LLM提取缺失字段/指标
    llm_result = None
    if llm_errors:
        errors_text = "\n".join(
            f"  - 错误：{validate.get('error')} | 建议：{validate.get('suggestion')}"
            for validate in llm_errors
        )
        table_column_text = build_table_column_text(state.get('merge_table_info_list'))
        metric_text = build_metric_text(state.get('merge_metrics_info_list'))

        prompt = PromptTemplate(
            template=load_prompt("missing_complete.md"),
            input_variables=["errors", "table_columns", "metrics"]
        )
        chain = prompt | column_complete_llm.with_structured_output(schema=ColumnCompleteInfo,
                                                                    method='function_calling')
        llm_result = await chain.ainvoke(
            {'errors': errors_text, 'table_columns': table_column_text, 'metrics': metric_text})

        if llm_result and llm_result.missing_list:
            logger.info(f"从LLM语义校验错误提取到缺失字段/指标：{[m.name for m in llm_result.missing_list]}")

    # 如果存在字段缺失，就合并Hive编译和LLM校验导致的缺失字段/指标
    if llm_result and getattr(llm_result, 'is_missing', False):
        missing_list.extend(llm_result.missing_list)

    unfound: list[str] = []

    # 如果字段缺失列表不为空，执行字段/指标补全
    if missing_list:
        logger.info(f"开始执行字段/指标补全，补全列表：{missing_list}")

        # 收集字段名列表, 去除字段名中的表名前缀，如 fact_order.order_id → order_id
        column_names = []
        for name in [missing.name for missing in missing_list if missing.type == 'column']:
            column_names.append(name.split('.')[-1] if '.' in name else name)
        # 收集指标名列表
        metric_names = list({m.name for m in missing_list if m.type == 'metric'})

        # 把补全的字段添加到过滤以后的表字段列表
        if column_names:
            missing_columns = await meta_repository.get_column_by_name_list(column_names)
            if not missing_columns:
                logger.warning(f"字段 {column_names} 在元数据中不存在")
                unfound.extend(column_names)
            else:
                table_map = {table.name: table for table in filter_table_info_list}
                for missing_column in missing_columns:
                    table_name = getattr(missing_column.table, 'name', None)
                    if table_name and table_name in table_map:
                        table_map[table_name].columns.append(
                            TableColumnState(
                                name=missing_column.name or '',
                                type=missing_column.type or '',
                                role=missing_column.role or '',
                                description=missing_column.description or '',
                                examples=missing_column.examples or [],
                                alias=missing_column.alias or []
                            )
                        )
                    else:
                        logger.warning(f"补全字段 "
                                       f"名称：'{missing_column.name}' | "
                                       f"类型：'{missing_column.role}' | "
                                       f"所属表：'{getattr(missing_column.table, 'name', None)}' "
                                       f"找不到对应的表，已跳过"
                                       )

        # 把补全的指标添加到过滤以后的指标列表
        if metric_names:
            missing_metrics = await meta_repository.get_metric_by_name_list(metric_names)
            if not missing_metrics:
                logger.warning(f"指标 {metric_names} 在元数据中不存在")
                unfound.extend(metric_names)
            else:
                filter_metrics_info_list = [
                    MetricState(
                        name=missing_metric.name or '',
                        description=missing_metric.description or '',
                        relevant_columns=missing_metric.columns or [],
                        alias=missing_metric.alias or []
                    )
                    for missing_metric in missing_metrics
                ]

    # 补全失败，无法找到字段/指标就累加失败次数和无效字段名
    if unfound:
        unfound_history = state.get('unfound_fields') or []
        unfound_list = list(set(unfound_history + unfound))
        unfound_count = state.get('unfound_count', 0) + 1
        logger.warning(f"第 {unfound_count} 次查不到字段/指标 {unfound}，累计缺失列表：{unfound_list}")
        return {
            "unfound_fields": unfound_list,
            "unfound_count": unfound_count,
        }

    # 返回补充的字段列表或透传
    return {
        "filter_table_info_list": filter_table_info_list,
        "filter_metrics_info_list": filter_metrics_info_list,
    }


def _extract_fields(error: str) -> list[str]:
    """
    从 Hive 编译异常中直接提取引用了但不存在的字段名。
    适用于 errorCode 10002 / 10004（Invalid column reference）。
    不处理 10001（Table not found），表名不属于字段补全范畴。
    提取后去除表别名前缀（如 fo.order_id → order_id）。
    """
    fields = []
    for pattern in [
        r"Invalid column reference '([^']+)'",
        r"Invalid table alias or column reference '([^']+)'",
    ]:
        for match in re.finditer(pattern, error):
            fields.append(match.group(1))
    return list(set(fields))