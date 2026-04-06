import asyncio
import re
import uuid
from pathlib import Path
from typing import AsyncGenerator, Any, TypeVar

from qdrant_client.models import PointStruct
from sqlalchemy.inspection import inspect
from tenacity import retry, stop_after_attempt, wait_exponential

from conf.app_config import app_config, COLUMN_VALUE_INDEX, META_METRICS_COLLECTION, META_TABLE_COLUMN_COLLECTION
from conf.meta_config import MetaConfig, TableConfig, MetricConfig
from infra.factory.repository_factory import Repositories
from infra.log.logging import logger
from infra.manager.embedding_manager import embedding_manager
from models.meta_models import TableInfo, ColumnInfo, MetricInfo
from utils.loader_utils import load_conf

BATCH_SIZE = 20
COLUMN_VALUES_BATCH_SIZE = 1000
COLUMN_VALUES_TOTAL_SIZE = 10000

T = TypeVar("T")


class KnowledgeService:

    def __init__(self, repos: Repositories):
        self.dw_repository = repos.dw
        self.meta_repository = repos.meta
        self.qdrant_repository = repos.meta_qdrant
        self.value_repository = repos.value_es
        self.embedding_client = embedding_manager.embedding_client

    async def execute(self, conf_path: str):
        """
        执行知识库索引创建
        :param conf_path:
        :return:
        """
        # 加载配置文件
        meta_conf = load_conf(MetaConfig, Path(conf_path))
        logger.info(f"加载配置文件成功")

        # 清除所有现有数据（幂等创建）
        await self.meta_repository.clear_all(
            ["column_metric", "column_info", "metric_info", "table_info"]
        )
        await self.qdrant_repository.clear_all(
            [META_TABLE_COLUMN_COLLECTION, META_METRICS_COLLECTION]
        )
        await self.value_repository.clear_all(COLUMN_VALUE_INDEX)

        # =====================处理表、字段元信息=========================

        table_configs = meta_conf.tables

        logger.info(f"开始处理表结构元数据，共 {len(table_configs)} 张表")

        # 摄入元数据
        column_infos, table_infos = await self._build_table_column_meta_info(table_configs)

        # 字段元数据转为向量
        await self._async_to_qdrant(META_TABLE_COLUMN_COLLECTION, column_infos, ColumnInfo)

        # 将字段元数据对应的值构建为全文索引
        await self._async_to_es(COLUMN_VALUE_INDEX, table_infos, table_configs, column_infos)

        # =====================处理指标元信息=========================

        metrics = meta_conf.metrics

        logger.info(f"开始处理指标元数据，共 {len(metrics)} 个指标")

        # 摄入元数据
        metric_infos = await self._build_metrics_meta_info(table_infos, column_infos, metrics)

        # 指标元数据转为向量
        await self._async_to_qdrant(META_METRICS_COLLECTION, metric_infos, MetricInfo)

    async def _build_table_column_meta_info(self, table_configs: list[TableConfig]) -> tuple[list[Any], list[Any]]:
        """
        构建表和字段元信息
        :param table_configs:
        :return:
        """
        column_infos = []
        table_infos = []

        # 添加表和字段元数据
        for table in table_configs:
            logger.debug(f"正在构建表 {table.name} 的字元数据")

            if not table.name or not table.role or not table.description:
                continue

            # 构建表结构元数据对象
            table_info = TableInfo(
                id=uuid.uuid4().hex,
                name=table.name.strip(),
                role=table.role.strip(),
                description=table.description.strip()
            )

            # 获取该表字段名对应的字段类型
            column_types = await asyncio.to_thread(self.dw_repository.get_column_types, table.name)

            for column in table.columns:
                logger.debug(f"正在构建字段 {column.name} 的元数据")

                if not column.name or not column.role or not column.description or not column.alias:
                    continue

                # 获取该表字段名对应的10条示例值
                column_values = await asyncio.to_thread(
                    self.dw_repository.get_column_values,
                    table.name,
                    column.name,
                    10)

                # 把多个空格替换为一个，把多个换行替换为一个
                description = re.sub(r'\s+', ' ', column.description.strip())
                description = re.sub(r'\n+', '\n', description)

                # 添加字段元数据
                column_info = ColumnInfo(
                    id=uuid.uuid4().hex,
                    name=column.name.strip(),
                    role=column.role.strip(),
                    type=column_types.get(column.name),
                    examples=column_values,
                    description=description,
                    alias=[alias for alias in column.alias if alias.strip()],
                    table_id=table_info.id
                )
                column_infos.append(column_info)

            table_infos.append(table_info)

        logger.info(f"已构建 {len(table_infos)} 张表的元数据，{len(column_infos)} 个字段的元数据")

        # 添加表和字段元数据
        await self.meta_repository.batch_add_meta_records(column_infos + table_infos)
        return column_infos, table_infos

    async def _async_to_qdrant(self, collection_name, items, item_cls: T, extra_payload_fn=None):
        """
        把元数据转为向量存储到qdrant
        :param items:
        :param collection_name:
        :param extra_payload_fn:
        :param item_cls:
        :return:
        """
        logger.info(f"正在把 {item_cls.__name__} 元数据转为向量存储到qdrant, 共 {len(items)} 条数据")

        # 创建集合(不存在则创建)
        await self.qdrant_repository.create_collection(
            collection_name=collection_name,
            vector_size=app_config.qdrant.embedding_size
        )

        candidate_embed_texts = []
        payloads = []

        # 获取item_cls所有映射到数据库列的属性
        column_attrs = inspect(item_cls).column_attrs

        # 得到要向量化的文本字典列表
        for item in items:
            text_list = [item.name, item.description] + item.alias
            for text in text_list:
                # 待向量化的文本列表
                candidate_embed_texts.append(text)
                # 把column对象转字典，并添加到载荷列表
                payload = {}
                for column_attr in column_attrs:  # type: ignore
                    payload.update({column_attr.key: getattr(item, column_attr.key)})
                payloads.append(payload)

        offset = 0  # 偏移量

        # 流式批量的把元数据向量化, 每生成一批向量就立刻写入
        async for embeddings in self.stream_batch_embed_texts(candidate_embed_texts, BATCH_SIZE):
            # 得到一批payload
            batch_payloads = payloads[offset: offset + len(embeddings)]

            # 构造pointstructs
            points = [
                PointStruct(
                    id=uuid.uuid4().hex,
                    vector=embedding,
                    payload=payload
                )
                for embedding, payload in zip(embeddings, batch_payloads)
            ]

            # 把向量存储到qdrant
            await self.qdrant_repository.batch_add_embeddings(collection_name, points=points)

            offset += len(embeddings)

        logger.info(f"已完成 {item_cls.__name__} 元数据向量化并存储到qdrant")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def stream_batch_embed_texts(self, texts: list[str], limit: int = 20) -> AsyncGenerator[
        list[list[float]], None]:
        """
        批量向量化
        :param texts:
        :param limit:
        :return:
        """
        for i in range(0, len(texts), limit):
            batch = texts[i:i + limit]
            yield await self.embedding_client.aembed_documents(batch)

    async def _async_to_es(self,
                           index_name: str,
                           table_infos: list[TableInfo],
                           table_configs: list[TableConfig],
                           column_infos: list[ColumnInfo]):
        """
        把字段对应的值添加到es
        :param index_name:
        :param table_infos:
        :param table_configs:
        :param column_infos:
        :return:
        """
        # 创建索引和映射（如果不存在索引）
        await self.value_repository.create_index(index_name)

        # 过滤允许构建全文索引的字段名映射
        sync_columns_map = {}
        for table_config in table_configs:
            sync_columns_map.update({
                table_column.name: table_column.sync
                for table_column in table_config.columns
            })

        # 从字段信息里过滤出需要构建全文索引的字段列表
        sync_column_infos = []
        for column_info in column_infos:
            sync = sync_columns_map.get(column_info.name) or False
            if sync: sync_column_infos.append(column_info)

        # 表id->表名 映射
        table_id_name_map: dict[str, str] = {
            table_info.id: table_info.name for table_info in table_infos
        }

        # 获取表对应的字段
        for column_info in sync_column_infos:
            if column_info.table_id not in table_id_name_map:
                continue
            # 获取表名
            table_name = table_id_name_map[column_info.table_id]
            # 流式获取每个表里每个字段对应的值
            async for values in self._stream_column_values(table_name, column_info.name,
                                                           COLUMN_VALUES_BATCH_SIZE,
                                                           COLUMN_VALUES_TOTAL_SIZE):
                # 构建文档
                documents = [
                    {
                        "id": uuid.uuid4().hex,
                        "value": value,
                        "type": column_info.type,
                        "column_id": column_info.id,
                        "column_name": column_info.name,
                        "table_id": column_info.table_id,
                        "table_name": table_name,
                    }
                    for value in values
                ]

                # 批量添加到es
                await self.value_repository.batch_add_documents(index_name, documents)

        logger.info("已完成字段值的全文索引构建")

    async def _stream_column_values(self,
                                    table_name: str,
                                    column_name: str,
                                    limit: int,
                                    total_rows: int
                                    ) -> AsyncGenerator:
        """
        流式查询每个表里每个字段对应的值，避免一次性查询占用过多内存
        :param table_name:
        :param column_name:
        :param limit:
        :param total_rows:
        :return:
        """
        offset = 0
        while offset < total_rows:
            column_values = await asyncio.to_thread(
                self.dw_repository.get_column_values,
                table_name,
                column_name,
                limit,
                offset
            )
            # 如果查询结果为空，就退出循环
            if not len(column_values):
                logger.info(f"表 {table_name} 字段 {column_name} 已经没有更多值可供查询，结束流式查询，offset {offset}")
                break
            # 有结果就返回
            yield column_values

            offset += limit

    async def _build_metrics_meta_info(self,
                                       tables: list[TableInfo],
                                       columns: list[ColumnInfo],
                                       metrics: list[MetricConfig]
                                       ) -> list[MetricInfo]:
        """
        构建指标元数据信息
        :param tables:
        :param columns:
        :param metrics:
        :return:
        """
        # 构建 table.column -> column 字典
        relevant_column_map = {}
        for table in tables:
            for column in columns:
                relevant_column = f"{table.name}.{column.name}"
                relevant_column_map.update({relevant_column: column})

        # 添加指标元数据
        metric_infos = []
        for metric in metrics:
            logger.debug(f"正在构建指标 {metric.name} 的元数据")

            name = metric.name.strip()
            desc = metric.description.strip()
            alias = [alias.strip() for alias in metric.alias if alias.strip()]
            relevant_columns = [relevant_column.strip()
                                for relevant_column in metric.relevant_columns
                                if relevant_column.strip()
                                ]

            # 过滤 字段-指标 关系的字段
            relationship = []
            for relevant_column in relevant_columns:
                relationship.append(relevant_column_map.get(relevant_column))

            metric_info = MetricInfo(
                id=uuid.uuid4().hex,
                name=name,
                description=desc,
                alias=alias,
                relevant_columns=relevant_columns,
                columns=relationship,
            )

            metric_infos.append(metric_info)

        logger.info(f"已构建 {len(metric_infos)} 个指标的元数据")

        await self.meta_repository.batch_add_meta_records(metric_infos)
        return metric_infos
