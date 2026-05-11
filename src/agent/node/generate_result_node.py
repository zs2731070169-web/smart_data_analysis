from langchain_core.messages import AIMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langgraph.runtime import Runtime

from agent.node._common import rewrite_question
from agent.schema.context_schema import EnvContext
from agent.schema.state_schema import OverallState, ExecuteState
from infra.client import result_analyze_llm
from infra.error import LLMServiceError
from infra.log.logging import logger
from utils.llm_retry_utils import acall_with_retry
from utils.loader_utils import load_prompt


async def generate_result_node(state: OverallState, runtime: Runtime[EnvContext]):
    """
    对hql生成的结果进行解析
    :param state:
    :param runtime:
    :return:
    """
    writer = runtime.stream_writer
    writer("开始解析最终结果")

    execute_result: ExecuteState | None = state.get('execute_result')
    if not execute_result or not execute_result.rows:
        writer("暂无查询结果")
        # 空结果路径也要写回历史，避免下一轮 LLM 看到"用户问→沉默→用户又问"的断层
        return {
            "messages": [
                AIMessage(content=f"已根据『{rewrite_question(state)}』执行查询，未返回数据。")
            ]
        }

    columns = execute_result.columns

    # 取一个适合做表头的短名：优先 alias[0]，否则截取 description 第一个分隔符前的片段，再裁剪长度
    def _short_label(alias: list[str] | None, description: str, max_len: int = 12) -> str:
        if alias:
            for a in alias:
                if a and a.strip():
                    return a.strip()[:max_len]
        head = description.strip()
        for sep in ("，", ",", "。", ".", "；", ";", "：", ":", "（", "(", "/", " ", "-"):
            idx = head.find(sep)
            if idx > 0:
                head = head[:idx]
                break
        return head[:max_len]

    # 使用 filter 列表里的字段描述/别名作为表头，构建原始字段名称到短标签的映射
    col_desc_mapping: dict[str, str] = {}
    for table in state.get('filter_table_info_list') or []:
        for column in table.columns:
            if column.description or column.alias:
                col_desc_mapping[column.name.lower()] = _short_label(column.alias, column.description)
    for metric in state.get('filter_metrics_info_list') or []:
        if metric.description or metric.alias:
            col_desc_mapping[metric.name.lower()] = _short_label(metric.alias, metric.description)

    # 字段描述字典当中没有匹配的原始字段名列表
    unmatched_columns = [col for col in columns if col.lower() not in col_desc_mapping]
    llm_translated_mapping: dict[str, str] = {}

    # 把未能再字段描述中匹配的原始字段名进行翻译
    if unmatched_columns:
        # 构建一行记录的样例，把原始字段名和查询出的对应字段值匹配，构建翻译样本
        sample_row_dict = {column: dict(zip(columns, execute_result.rows[0]))[column] for column in unmatched_columns}
        prompt_template = ChatPromptTemplate(messages=[
            ("system", load_prompt("analyze_result.md")),
            ("user", "{result}")
        ])
        chain = prompt_template | result_analyze_llm | JsonOutputParser()

        # LLM 调用：翻译失败时回退为原列名，保证用户至少看到数据
        try:
            translated_list = await acall_with_retry(
                lambda: chain.ainvoke({"result": [sample_row_dict]}),
                op_name="generate_result",
            )
            if translated_list and isinstance(translated_list, list) and len(translated_list) > 0:
                # 构建未匹配描述信息列表的原始字段名和翻译后对应的字段名映射，即翻译后的字典
                llm_translated_mapping = dict(zip(unmatched_columns, translated_list[0].keys()))
        except LLMServiceError as e:
            logger.warning(
                f"结果字段翻译 LLM 失败回退为原列名: reason={e.classified.reason.value}"
            )

    # 合并映射 -> 原始字段名: 翻译过后的名称，构建翻译字段映射
    # 翻译的名称先从字段描述字典列表里取，没有，就从llm翻译的字典列表里取，还没有或者翻译失败，就使用原始字段名
    translate_mapping = {
        column: col_desc_mapping.get(column.lower(), llm_translated_mapping.get(column, column))
        for column in columns
    }
    # 构建最终返回列表，使用翻译字段映射，构建中文字段到对应字段值的字典列表
    final_result = [
        {translate_mapping[col]: (val if val else 0) for col, val in zip(columns, row_values)}
        for row_values in execute_result.rows
    ]

    logger.info(f"最终解析结果：{final_result}")
    writer({"output": final_result})

    # 写回历史：包含本轮规范化问题 + 行数 + 字段名（不含数据值）
    display_columns = list(final_result[0].keys()) if final_result else columns
    summary = (
        f"已根据『{rewrite_question(state)}』完成查询，"
        f"返回 {execute_result.row_count} 行，字段：{'、'.join(display_columns)}。"
    )
    return {"messages": [AIMessage(content=summary)]}
