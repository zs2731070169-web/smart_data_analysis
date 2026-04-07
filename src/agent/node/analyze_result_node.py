from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langgraph.runtime import Runtime

from agent.schema.context_schema import EnvContext
from agent.schema.state_schema import OverallState
from infra.client.llm_client import result_analyze_llm
from infra.log.logging import logger
from utils.loader_utils import load_prompt


async def analyze_result_node(state: OverallState, runtime: Runtime[EnvContext]):
    """
    对hql生成的结果进行解析
    :param state:
    :param runtime:
    :return:
    """
    writer = runtime.stream_writer
    writer("开始解析最终结果")

    try:
        execute_result = state.get('execute_result') or []

        # 只取1行给 LLM 进行字段名翻译
        sample = execute_result[:1]
        prompt_template = ChatPromptTemplate(messages=[
            ("system", load_prompt("analyze_result.md")),
            ("user", "{result}")
        ])
        chain = prompt_template | result_analyze_llm | JsonOutputParser()
        translated_list = await chain.ainvoke({"result": sample})

        # 从翻译样本中提取字段名映射，应用到全量结果
        final_result = []
        if translated_list and isinstance(translated_list, list) and len(translated_list) > 0:
            # 得到原始key到翻译名称的映射
            translate_mapping = {origin: translated for origin, translated in
                                 zip(sample[0].keys(), translated_list[0].keys())}
            for row in execute_result:
                # 逐行翻译
                final_result.append(
                    {
                        translate_mapping.get(key, key): value if value else 0
                        for key, value in row.items()
                    }
                )
        else:
            final_result = translated_list

        logger.info(f"最终解析结果：{final_result}")

        writer({"output": final_result})
    except Exception as e:
        logger.error(f"结果解析失败: {str(e)}")
        raise Exception('结果解析失败，请稍后重试或联系数据团队😿')
