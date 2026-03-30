from typing import List

from sqlalchemy import text, quoted_name
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from tenacity import retry, stop_after_attempt, wait_exponential

from infra.log.logging import logger
from models.meta_models import Base


class MetaMysqlRepository:

    def __init__(self, mysql_session: async_sessionmaker[AsyncSession]):
        self.session = mysql_session

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def clear_all(self, table_names: list[str]):
        """
        清空原来的数据
        :param metrics:
        :param table:
        :return:
        """
        try:
            async with self.session() as session:
                async with session.begin():
                    for table_name in table_names:
                        safe_table_name = quoted_name(table_name, quote=True)  # 防止sql注入
                        await session.execute(text(f"TRUNCATE TABLE {safe_table_name}"))
                        logger.info(f"已清空表 {table_name} 的数据")
        except Exception as e:
            logger.error(f"清空原有元数据表数据失败: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def batch_add_meta_records(self, meta_infos: List[Base], batch: int = 200):
        """
        添加字段/指标元数据记录
        :param batch:
        :param meta_infos:
        :return:
        """
        try:
            async with self.session() as session:
                # session.begin() 在退出时触发 commit()，真正的执行sql
                async with session.begin():
                    for index in range(0, len(meta_infos), batch):
                        batch = meta_infos[index:index + batch]
                        #  add_all 只是内存操作
                        session.add_all(batch)
                logger.info(f"已添加 {len(meta_infos)} 条元数据记录")
        except Exception as e:
            logger.error(f"添加元数据记录失败: {e}")
            raise
