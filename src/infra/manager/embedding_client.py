from langchain_huggingface import HuggingFaceEndpointEmbeddings

from conf.app_config import app_config
from infra.log.logging import logger


class EmbeddingManager:

    def __init__(self):
        try:
            self.embedding_client = HuggingFaceEndpointEmbeddings(
                model=f"http://{app_config.embedding.host}:{app_config.embedding.port}"
            )
            logger.info("成功初始化 EmbeddingManager")
        except Exception as e:
            logger.error(f"初始化 EmbeddingManager 失败: {e}")
            raise


embedding_manager = EmbeddingManager()
