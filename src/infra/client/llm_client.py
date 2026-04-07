from langchain_openai import ChatOpenAI

from conf.app_config import app_config

expand_keywords_llm = ChatOpenAI(
    model=app_config.llm.expand_keywords_llm.model_name,
    base_url=app_config.llm.expand_keywords_llm.url,
    api_key=app_config.llm.expand_keywords_llm.api_key,
    temperature=0
)

filter_llm = ChatOpenAI(
    model=app_config.llm.filter_llm.model_name,
    base_url=app_config.llm.filter_llm.url,
    api_key=app_config.llm.filter_llm.api_key,
    temperature=0
)

general_hql_llm = ChatOpenAI(
    model=app_config.llm.general_hql_llm.model_name,
    base_url=app_config.llm.general_hql_llm.url,
    api_key=app_config.llm.general_hql_llm.api_key,
    temperature=0,
    extra_body={"enable_thinking": False}
)

validate_hql_llm = ChatOpenAI(
    model=app_config.llm.validate_hql_llm.model_name,
    base_url=app_config.llm.validate_hql_llm.url,
    api_key=app_config.llm.validate_hql_llm.api_key,
    temperature=0,
    # 关闭 validate_hql_llm 的思考链路输出，避免干扰 structured_output 的 JSON 解析
    extra_body={"enable_thinking": False}
)

correct_hql_llm = ChatOpenAI(
    model=app_config.llm.correct_hql_llm.model_name,
    base_url=app_config.llm.correct_hql_llm.url,
    api_key=app_config.llm.correct_hql_llm.api_key,
    temperature=0,
    extra_body={"enable_thinking": False}
)

judge_llm = ChatOpenAI(
    model=app_config.llm.judge_llm.model_name,
    base_url=app_config.llm.judge_llm.url,
    api_key=app_config.llm.judge_llm.api_key,
    temperature=0
)

column_complete_llm = ChatOpenAI(
    model=app_config.llm.column_complete_llm.model_name,
    base_url=app_config.llm.column_complete_llm.url,
    api_key=app_config.llm.column_complete_llm.api_key,
)

result_analyze_llm = ChatOpenAI(
    model=app_config.llm.result_analyze_llm.model_name,
    base_url=app_config.llm.result_analyze_llm.url,
    api_key=app_config.llm.result_analyze_llm.api_key,
)