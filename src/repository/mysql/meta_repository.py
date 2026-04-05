from typing import List, Optional, Sequence

from sqlalchemy import text, quoted_name, select, or_, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from tenacity import retry, stop_after_attempt, wait_exponential

from infra.log.logging import logger
from models.meta_models import Base, ColumnInfo, MetricInfo, TableInfo


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
            logger.warning(f"清空原有元数据表数据失败: {e}")

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

    async def get_column_by_id(self, column_id: str) -> ColumnInfo | None:
        """
        根据字段id获取字段信息
        :param column_id:
        :return:
        """
        try:
            async with self.session() as session:
                return await session.get(ColumnInfo, column_id)
        except Exception as e:
            logger.error(f"根据id获取字段信息失败: {e}")
            return None

    async def get_table_name_by_ids(self, table_ids: set[str]) -> dict[str, str] | None:
        """
        根据表id列表获取表id和表名的映射字典
        :param table_ids:
        :return:
        """
        if not table_ids:
            return {}
        try:
            async with self.session() as session:
                sql = text("""
                           select id, name
                           from table_info
                           where id in :table_ids
                           """)
                result = await session.execute(sql, {"table_ids": tuple(table_ids)})
                return {row.id: row.name for row in result.fetchall()}
        except Exception as e:
            logger.error(f"根据id获取表信息失败: {e}")
            return None

    async def get_column_by_metric_id(self, metric_id: str, column_name: str) -> ColumnInfo | None:
        """
        根据指标id和字段名称获取字段信息
        :param metric_id:
        :param column_name:
        :return:
        """
        try:
            async with self.session() as session:
                sql = select(ColumnInfo).where(ColumnInfo.metrics.any(MetricInfo.id == metric_id),
                                               ColumnInfo.name == column_name)
                result = await session.execute(sql)
                # 返回单条记录或none
                return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"根据指标id获取字段信息失败: {e}")
            return None

    async def get_table_by_id(self, table_id) -> Optional[TableInfo]:
        """
        根据表id获取表信息
        :param table_id:
        :return:
        """
        try:
            async with self.session() as session:
                return await session.get(TableInfo, table_id)
        except Exception as e:
            logger.error(f"根据id获取表信息失败: {e}")
            return None

    # async def get_columns_by_role_and_table_role(self, column_role, table_role) -> Sequence[ColumnInfo]:
    #     """
    #     从字段角色和表角色中获取字段信息列表
    #     :param column_role:
    #     :param table_role:
    #     :return:
    #     """
    #     async with self.session() as session:
    #         try:
    #             sql = select(ColumnInfo).join(TableInfo).where(ColumnInfo.role == column_role,
    #                                                            TableInfo.role == table_role)
    #             result = await session.execute(sql)
    #             # 返回多条记录
    #             return result.scalars().all()
    #         except Exception as e:
    #             logger.error(f"根据字段角色和表角色获取字段信息失败: {e}")
    #             return []

    async def get_column_primary_key_by_table_id(self, table_id) -> ColumnInfo | None:
        """
        根据表id查找字段主键
        :param table_id:
        :return:
        """
        try:
            async with self.session() as session:
                sql = select(ColumnInfo).where(ColumnInfo.table_id == table_id, ColumnInfo.role == 'primary_key')
                result = await session.execute(sql)
                return result.scalars().first()
        except Exception as e:
            logger.error(f"根据表id获取主键字段信息失败: {e}")
            return None

    # async def get_column_primary_key_by_table_name(self, table_name) -> ColumnInfo | None:
    #     """通过表名获取字段主键id"""
    #     try:
    #         async with self.session() as session:
    #             sql = select(ColumnInfo).join(TableInfo).where(ColumnInfo.role == 'primary_key',
    #                                                            TableInfo.name == table_name)
    #             result = await session.execute(sql)
    #             return result.scalar_one_or_none()
    #     except Exception as e:
    #         logger.error(f"根据表名获取主键字段信息失败: {e}")
    #         return None

    async def get_columns_foreign_key_by_id(self, table_id) -> Sequence[ColumnInfo] | []:
        try:
            async with self.session() as session:
                sql = select(ColumnInfo).where(ColumnInfo.table_id == table_id, ColumnInfo.role == 'foreign_key')
                result = await session.execute(sql)
                return result.scalars().all()
        except Exception as e:
            logger.error(f"根据表id获取外键字段信息失败: {e}")
            return []

    async def get_column_by_name_list(self, column_names: list[str]) -> Sequence[ColumnInfo] | []:
        """
        根据字段名查询字段信息
        :param column_names:
        :return:
        """
        try:
            async with self.session() as session:
                sql = select(ColumnInfo).options(selectinload(ColumnInfo.table)).where(
                    ColumnInfo.name.in_(column_names))
                result = await session.execute(sql)
                return result.scalars().all()
        except Exception as e:
            logger.info(f"根据字段名查询字段信息失败: {e}")
            return []

    async def get_metric_by_name_list(self, metric_names: list[str]) -> Sequence[MetricInfo] | []:
        """
        根据指标名查询指标信息
        :param metric_names:
        :return:
        """
        try:
            async with self.session() as session:
                sql = select(MetricInfo).where(
                    or_(
                        MetricInfo.name.in_(metric_names),
                        # 判断数据库里存的别名数组与查询数组是否有交集, 返回 1 表示有交集，即命中别名
                        func.JSON_OVERLAPS(MetricInfo.alias, func.JSON_ARRAY(*metric_names)) == 1
                    )
                )
                result = await session.execute(sql)
                seen, unique = set(), []
                for metric in result.scalars().all():
                    if metric.id not in seen:
                        seen.add(metric.id)
                        unique.append(metric)
                return unique
        except Exception as e:
            logger.info(f"根据指标名查询指标信息失败: {e}")
            return []
