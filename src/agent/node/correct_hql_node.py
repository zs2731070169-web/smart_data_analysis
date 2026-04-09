import asyncio

from langgraph.runtime import Runtime

from agent.node._common import build_table_column_text, build_metric_text, build_datetime_text, build_db_metadata_text, \
    generate_hql
from agent.schema.context_schema import EnvContext
from agent.schema.state_schema import OverallState
from conf.app_config import CORRECT_BACKOFF_BASE, CORRECT_BACKOFF_MAX
from infra.client.llm_client import correct_hql_llm
from infra.log.logging import logger
from utils.loader_utils import load_prompt


async def correct_hql_node(state: OverallState, runtime: Runtime[EnvContext]):
    """
    HQL 纠错节点
    :param state:
    :param runtime:
    :return:
    """
    writer = runtime.stream_writer
    writer("开始执行 HQL 纠错节点")

    try:
        # 指数退避等待
        correct_count = state.get('correct_count', 0)
        if correct_count > 0:
            delay = min(CORRECT_BACKOFF_BASE * (2 ** (correct_count - 1)), CORRECT_BACKOFF_MAX)
            logger.info(f"指数退避等待 {delay}s（第 {correct_count} 轮纠错）")
            await asyncio.sleep(delay)

        # 构建过滤后的表字段文本
        table_column_text = build_table_column_text(state.get('filter_table_info_list', []))

        # 构建过滤后的指标列表信息文本
        metric_text = build_metric_text(state.get('filter_metrics_info_list', []))

        # 构建当前时间和数据库元信息文本
        cur_datetime_info = build_datetime_text(state.get('expand_datetime'))
        db_metadata_text = build_db_metadata_text(state.get('expand_db_metadata'))

        # 构建校验结果信息文本
        validates = state.get('validates', [])
        if not validates:
            return "无校验问题"
        lines = [f"{i}. 错误：{validate.get('error')}" for i, validate in enumerate(validates, 1)]
        validates_text = "\n".join(lines).strip()

        # 历史纠错记录
        fix_history = state.get('fix_history', [])
        fix_history_text = "\n\n---\n\n".join(fix_history[-2:]).rstrip()

        # 数据源中查不到的字段/指标
        unfound_fields = state.get('unfound_fields') or []
        unfound_text = "、".join(f"`{field}`" for field in unfound_fields) if unfound_fields else ""

        hql = await generate_hql(
            query={
                "question": state.get('question'),
                "table_column_list": table_column_text,
                "metric_list": metric_text,
                "datetime": cur_datetime_info,
                "db_metadata": db_metadata_text,
                "hql": state.get('hql'),
                "validates": validates_text,
                "fix_history": fix_history_text,
                "unfound_fields": unfound_text,
            },
            system_prompt=load_prompt("correct_hql_system.md"),
            user_prompt=load_prompt("correct_hql_user.md"),
            correct_hql_llm=correct_hql_llm
        )

        # 添加历史轨迹（一轮一条，因果顺序：校验原因 → 修复结果）
        errors_text = "\n".join(f"  - 错误：{validate.get('error')}" for validate in validates)
        fix_history.append((
            f"第{len(fix_history) + 1}轮：针对以下校验问题尝试修复\n"
            f"{errors_text}\n"
            f"修复后的 HQL：{hql}>-"
        ))

        logger.info(f"纠错后的SQL: {hql}")

        return {
            "hql": hql,
            "correct_count": state.get('correct_count', 0) + 1,
            "fix_history": fix_history
        }

    except Exception as e:
        logger.error(f"HQL 纠错失败: {str(e)}")
        raise Exception('HQL 纠错失败，请稍后重试或联系数据团队')
