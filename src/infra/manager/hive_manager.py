import asyncio
from contextlib import contextmanager
from typing import Optional, Generator

from infra.log.logging import logger
from sqlalchemy import Engine, create_engine, text, Connection
from sqlalchemy.pool.impl import NullPool

from conf.app_config import app_config


class HiveManager:

    def __init__(self):
        self.engine: Optional[Engine] = None

    def init(self):
        """
        初始化数据库引擎
        :return:
        """
        try:
            self.engine = create_engine(
                url=f"hive://{app_config.dw.user}@{app_config.dw.host}:{app_config.dw.port}/{app_config.dw.database}",
                poolclass=NullPool,
                connect_args={"auth": "NONE"},
            )

            logger.info("Hive 客户端初始化完成")
        except RuntimeError as e:
            logger.error(f"Hive 客户端初始化失败: {e}")
            raise

    async def close(self):
        try:
            if self.engine:
                await asyncio.to_thread(self.engine.dispose)
                logger.info("Hive 客户端已关闭")
        except RuntimeError as e:
            logger.error(f"Hive 客户端关闭失败: {e}")
            raise


hive_manager = HiveManager()

if __name__ == '__main__':
    hive_manager.init()


    def _sync_query():
        conn = hive_manager.engine.connect()
        result = conn.execute(text("SELECT 1"))
        return result.fetchall()


    async def main():
        result = await asyncio.to_thread(_sync_query)
        print(result)
        await hive_manager.close()

    asyncio.run(main())


