from langchain_openai import ChatOpenAI

from conf.app_config import app_config

expand_keywords_llm = ChatOpenAI(
    model=app_config.llm.llm_expand_keywords.model_name,
    base_url=app_config.llm.llm_expand_keywords.url,
    api_key=app_config.llm.llm_expand_keywords.api_key,
    temperature=0
)
