import asyncio
from dataclasses import dataclass

from infra.manager.es_manager import es_manager
from infra.manager.hive_manager import hive_manager
from infra.manager.mysql_manager import mysql_manager
from infra.manager.qdrant_manager import qdrant_manager
from repository.hive.dw_repository import DwHiveRepository
from repository.mysql.meta_repository import MetaMysqlRepository
from repository.qdrant.meta_repository import MetaQdrantRepository
from repository.se.value_repository import ValueESRepository


@dataclass
class Repositories:
    """所有仓库的集合，Service 层直接使用这个对象"""
    dw: DwHiveRepository
    meta: MetaMysqlRepository
    meta_qdrant: MetaQdrantRepository
    value_es: ValueESRepository


class RepositoryFactory:
    """统一管理所有客户端的初始化和销毁"""

    def __init__(self):
        self._hive = hive_manager
        self._mysql = mysql_manager
        self._qdrant = qdrant_manager
        self._es = es_manager

    async def __aenter__(self) -> Repositories:
        # 初始化客户端
        self._hive.init()
        self._mysql.init()
        self._qdrant.init()
        self._es.init()

        # 创建会话或连接
        hive_connect = self._hive.engine.connect()
        mysql_session = self._mysql.session_factory

        # 获取客户端实例
        qdrant_client = self._qdrant.qdrant_client
        es_client = self._es.es_client

        # 返回repository仓库
        return Repositories(
            dw=DwHiveRepository(hive_connect),
            meta=MetaMysqlRepository(mysql_session),
            meta_qdrant=MetaQdrantRepository(qdrant_client),
            value_es=ValueESRepository(es_client)
        )

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # 关闭客户端
        await asyncio.gather(
            self._hive.close(),
            self._mysql.close(),
            self._qdrant.close(),
            self._es.close()
        )


repository_factory = RepositoryFactory()
