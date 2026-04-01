import asyncio
from typing import Optional

from infra.log.logging import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, async_sessionmaker, AsyncSession

from conf.app_config import app_config


class MySqlManager:

    def __init__(self):
        self.db_engine: Optional[AsyncEngine] = None
        self.session_factory: Optional[
            async_sessionmaker[AsyncSession]] = None  # async_sessionmaker是一个类, AsyncSession是它的泛型

    def init(self):
        """
        初始化数据库引擎和会话工厂
        :return:
        """
        try:
            # 创建数据库引擎
            self.db_engine = create_async_engine(
                url=f"mysql+aiomysql://{app_config.db.user}:{app_config.db.password}@{app_config.db.host}:{app_config.db.port}/{app_config.db.database}",
                pool_size=app_config.db.pool_size,  # 最大连接数
                max_overflow=app_config.db.max_overflow,  # 额外可扩展连接数
                pool_timeout=app_config.db.pool_timeout, # 连接等待超时时间
                pool_pre_ping=True,  # 每次使用连接之前检查session是否可用，不可用则重新建立连接
                pool_recycle=app_config.db.pool_recycle_timeout, # 连接超过多长空闲时间后回收，单位是秒
                # echo=app_config.db.logger,  # 打印 SQL 日志（调试用）
            )

            # 创建会话工厂
            self.session_factory = async_sessionmaker(
                bind=self.db_engine,
                # 当为True，对于同一个session，如果临时改动了对象的任何状态，即使没有commit，在后续执行任何查询前，会自动将内存中的改动同步到数据库事务缓冲区（此时数据尚未持久化），保证了同一个 Session 内，“先改后查”能查到最新的改动
                autoflush=True,
                # 当为True，对于同一个Session，如果执行了commit动作以后，自己持有的对象状态会被全部标记为过期，后续再获取该对象属性会自动触发数据库查询获取最新记录
                # 该属性只针对自己的会话有效，不影响其他会话
                # 异步环境只能为False，因为异步下属性访问（如 obj.name）会触发异步 I/O 导致崩溃，需要最新数据时只能手动 await session.refresh()
                expire_on_commit=False
            )

            logger.info("MySQL 客户端初始化完成")
        except Exception as e:
            logger.error(f"MySQL 客户端初始化失败: {e}")
            raise

    async def close(self):
        try:
            if self.db_engine:
                await self.db_engine.dispose()
                logger.info("MySQL 客户端已关闭")
        except Exception as e:
            logger.error(f"MySQL 客户端关闭失败: {e}")
            raise


mysql_manager = MySqlManager()

if __name__ == '__main__':
    mysql_manager.init()


    async def main():
        if mysql_manager.session_factory:
            async with mysql_manager.session_factory() as session:
                result = await session.execute(text("SELECT 1"))
                print(result.fetchall())

        await mysql_manager.close()


    asyncio.run(main())
