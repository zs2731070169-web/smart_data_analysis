from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langgraph.runtime import Runtime

from agent.schema.context_schema import EnvContext
from agent.schema.state_schema import OverallState, ExecuteState
from infra.client import result_analyze_llm
from infra.log.logging import logger
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

    try:
        execute_result: ExecuteState | None = state.get('execute_result')
        if not execute_result or not execute_result.rows:
            writer("暂无查询结果")
            return

        columns = execute_result.columns

        # 只取 1 行给 LLM 做字段名翻译
        sample_row_dict = dict(zip(columns, execute_result.rows[0]))
        prompt_template = ChatPromptTemplate(messages=[
            ("system", load_prompt("analyze_result.md")),
            ("user", "{result}")
        ])
        chain = prompt_template | result_analyze_llm | JsonOutputParser()
        translated_list = await chain.ainvoke({"result": [sample_row_dict]})

        # 从翻译样本中提取字段名映射，应用到全量行数据
        final_result = []
        if translated_list and isinstance(translated_list, list) and len(translated_list) > 0:
            translate_mapping = {
                origin: translated
                for origin, translated in zip(columns, translated_list[0].keys())
            }
            for row_values in execute_result.rows:
                row_dict = dict(zip(columns, row_values))
                final_result.append(
                    {
                        translate_mapping.get(key, key): value if value else 0
                        for key, value in row_dict.items()
                    }
                )
        else:
            final_result = translated_list

        logger.info(f"最终解析结果：{final_result}")

        writer({"output": final_result})
    except Exception as e:
        logger.error(f"结果解析失败: {str(e)}")
        raise Exception('结果解析失败，请稍后重试或联系数据团队😿')
