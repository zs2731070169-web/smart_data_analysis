from typing import Annotated

from fastapi import Depends
from langchain_huggingface import HuggingFaceEndpointEmbeddings

from infra.log.logging import logger
from infra.manager.embedding_manager import embedding_manager
from infra.manager.es_manager import es_manager
from infra.manager.hive_manager import hive_manager
from infra.manager.mysql_manager import mysql_manager
from infra.manager.qdrant_manager import qdrant_manager
from repository.hive.dw_repository import DwHiveRepository
from repository.mysql.meta_repository import MetaMysqlRepository
from repository.qdrant.meta_repository import MetaQdrantRepository
from repository.se.value_repository import ValueESRepository
from service.chat_service import ChatService


async def get_hive_connect():
    return hive_manager.engine.connect()


async def get_mysql_session():
    return mysql_manager.session_factory


async def get_qdrant_client():
    return qdrant_manager.qdrant_client


async def get_es_client():
    return es_manager.es_client


async def get_embedding_client():
    return embedding_manager.embedding_client


async def get_dw_repository(hive_connect=Depends(get_hive_connect)) -> DwHiveRepository:
    return DwHiveRepository(hive_connect)


async def get_meat_repository(mysql_session=Depends(get_mysql_session)) -> MetaMysqlRepository:
    return MetaMysqlRepository(mysql_session)


async def get_qdrant_repository(qdrant_client=Depends(get_qdrant_client)) -> MetaQdrantRepository:
    return MetaQdrantRepository(qdrant_client)


async def get_es_repository(es_client=Depends(get_es_client)) -> ValueESRepository:
    return ValueESRepository(es_client)


async def get_services(
        embedding_client: Annotated[HuggingFaceEndpointEmbeddings, Depends(get_embedding_client)],
        dw_repository: Annotated[DwHiveRepository, Depends(get_dw_repository)],
        meta_repository: Annotated[MetaMysqlRepository, Depends(get_meat_repository)],
        qdrant_repository: Annotated[MetaQdrantRepository, Depends(get_qdrant_repository)],
        es_repository: Annotated[ValueESRepository, Depends(get_es_repository)],
):
    """
    加载各项chatservice所需依赖
    :param embedding_client:
    :param dw_repository:
    :param meta_repository:
    :param qdrant_repository:
    :param es_repository:
    :return:
    """
    chat_service = ChatService(
        embedding_client,
        dw_repository,
        meta_repository,
        qdrant_repository,
        es_repository
    )
    logger.info("chat_service开始执行")
    yield chat_service
    logger.info("chat_service执行完毕")
