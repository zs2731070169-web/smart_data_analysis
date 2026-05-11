import json
from typing import AsyncGenerator

from langchain_core.messages import HumanMessage
from langchain_huggingface import HuggingFaceEndpointEmbeddings

from agent.graph import graph
from agent.schema.context_schema import EnvContext
from agent.schema.state_schema import InputState
from api.schema.request import ChatRequest
from infra.error import LLMServiceError
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

    async def stream_chat(self, chat_req: ChatRequest) -> AsyncGenerator[str, None]:
        try:
            async for chunk in graph.astream(
                    input=InputState(
                        question=chat_req.question,
                        messages=[HumanMessage(content=chat_req.question)],
                    ),
                    context=EnvContext(
                        repositories=self._repositories,
                        embedding_client=self._embedding_client,
                    ),
                    config={"configurable": {"thread_id": chat_req.session}},
                    stream_mode=["custom"],
            ):
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        except LLMServiceError as e:
            # 已分类的 LLM 异常：直接吐结构化的用户文案，无需再分类重试
            classified = e.classified
            logger.warning(
                f"流式对话 LLM 调用失败 reason={classified.reason.value} "
                f"status={classified.status_code} retryable={classified.retryable} "
                f"msg={classified.message}"
            )
            payload = {
                "error": {
                    "reason": classified.reason.value,
                    "retryable": classified.retryable,
                    "message": classified.user_message,
                }
            }
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"流式对话执行异常：{str(e)}")
            yield f"data: {str(e) or '😒服务暂时不可用，请稍后再试...'}\n\n"
