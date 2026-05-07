from conf.app_config import app_config
from infra.client.llm_client import build_llm
from infra.log.logging import logger

_NO_THINKING = {"extra_body": {"enable_thinking": False}}

expand_keywords_llm = build_llm(app_config.llm.expand_keywords_llm)
filter_llm = build_llm(app_config.llm.filter_llm)
general_hql_llm = build_llm(app_config.llm.general_hql_llm, **_NO_THINKING)
validate_hql_llm = build_llm(app_config.llm.validate_hql_llm, **_NO_THINKING)
result_analyze_llm = build_llm(app_config.llm.result_analyze_llm)

logger.info("所有模型初始化完毕!")