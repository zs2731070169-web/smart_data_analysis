import json
from typing import AsyncGenerator

from langchain_huggingface import HuggingFaceEndpointEmbeddings

from agent.graph import graph
from agent.schema.context_schema import EnvContext
from agent.schema.state_schema import InputState
from infra.factory.repository_factory import Repositories
from infra.log.logging import logger
from repository.hive.dw_repository import DwHiveRepository
from repository.mysql.meta_repository import MetaMysqlRepository
from repository.qdrant.meta_repository import MetaQdrantRepository
from repository.se.value_repository import ValueESRepository


class ChatService:

    def __init__(self,
                 embedding_client: HuggingFaceEndpointEmbeddings,
                 dw_repository: DwHiveRepository,
                 meta_repository: MetaMysqlRepository,
                 qdrant_repository: MetaQdrantRepository,
                 es_repository: ValueESRepository
                 ):
        self._embedding_client = embedding_client
        self._repositories = Repositories(
            dw=dw_repository,
            meta=meta_repository,
            meta_qdrant=qdrant_repository,
            value_es=es_repository
        )

    async def stream_chat(self, question: str) -> AsyncGenerator[str, None]:
        try:
            async for chunk in graph.astream(
                    input=InputState(question=question),
                    context=EnvContext(
                        repositories=self._repositories,
                        embedding_client=self._embedding_client,
                    ),
                    stream_mode=["custom"],
            ):
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"流式对话执行异常：{str(e)}")
            yield f"data: {str(e) or '😒服务暂时不可用，请稍后再试...'}\n\n"
