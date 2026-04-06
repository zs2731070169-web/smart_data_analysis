from contextlib import asynccontextmanager

from fastapi import FastAPI

from infra.manager.hive_manager import hive_manager
from infra.log.logging import logger
from infra.manager.es_manager import es_manager
from infra.manager.mysql_manager import mysql_manager
from infra.manager.qdrant_manager import qdrant_manager


@asynccontextmanager
async def init_connect(api: FastAPI):
    try:
        hive_manager.init()
        mysql_manager.init()
        qdrant_manager.init()
        es_manager.init()
        logger.info("所有初始化连接完毕！")
        yield
    except Exception as e:
        logger.error(f"初始化连接异常 {e}")
        raise
    finally:
        logger.info("关闭连接...")
        if hive_manager:
            hive_manager.close()
        if mysql_manager:
            mysql_manager.close()
        if es_manager:
            qdrant_manager.close()
        if es_manager:
            es_manager.close()
