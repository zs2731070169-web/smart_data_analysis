from langchain_openai import ChatOpenAI


def build_llm(cfg, **overrides) -> ChatOpenAI:
    """
    根据配置构建OpenAI风格的 LLM
    :param cfg:
    :param overrides:
    :return:
    """
    params = {
        "model": cfg.model_name,
        "base_url": cfg.url,
        "api_key": cfg.api_key,
        "temperature": cfg.temperature,
    }
    params.update(overrides)
    return ChatOpenAI(**params)
