from typing import Any

from elasticsearch import AsyncElasticsearch, NotFoundError

from infra.log.logging import logger


class ValueESRepository:

    def __init__(self, es_client: AsyncElasticsearch):
        self.es_client = es_client

    async def create_index(self, index_name: str):
        """
        不存在索引则新建索引和映射
        :param index_name:
        :return:
        """
        if not await self.es_client.indices.exists(index=index_name):
            await self.es_client.indices.create(
                index=index_name,
                mappings={
                    "properties": {
                        "id": {"type": "keyword"},
                        "value": {"type": "text", "analyzer": "ik_max_word", "search_analyzer": "ik_max_word"},
                        "type": {"type": "keyword"},
                        "column_id": {"type": "keyword"},
                        "column_name": {"type": "keyword"},
                        "table_id": {"type": "keyword"},
                        "table_name": {"type": "keyword"},
                    }
                }
            )

    async def batch_add_documents(self, index_name: str, documents: list[dict[str, Any]]):
        """
        批量向索引添加文档
        :param index_name:
        :param documents:
        :return:
        """
        operations = []
        # Elasticsearch bulk API 的 operations 格式要求 action 字典和 document 字典分开存放（成对出现）
        for document in documents:
            operations.append({"index": {"_index": index_name, "_id": document["id"]}})
            operations.append(document)

        result = await self.es_client.bulk(operations=operations)
        # 检查返回结果中的 errors 字段
        failed = 0
        if result['errors']:
            failed = [item for item in result['items'] if 'error' in item.get('index', {})]
            failed = len(failed)
        logger.info(f"ES 批量写入完成: {len(documents)} 条，失败 {failed} 条")

    async def clear_all(self, column_value_index):
        """
        清空指定索引的集合
        :param column_value_index:
        :return:
        """
        try:
            await self.es_client.indices.delete(index=column_value_index)
            logger.info(f"已清空索引 {column_value_index}")
        except NotFoundError as e:
            logger.warning(f"索引 {column_value_index} 不存在，无法删除: {e}")
        except Exception as e:
            logger.warning(f"清空索引 {column_value_index} 失败: {e}")

    async def search(self, index_name: str, keyword: str, size: int = 8, score: int = 0.5):
        try:
            result = await self.es_client.search(
                index=index_name,
                query={
                    "match": {
                        "value": keyword
                    }
                },
                size=size,
                min_score=score
            )
            hits = result.body['hits']['hits']
            return [hit.get('_source') for hit in hits]
        except Exception as e:
            logger.warning(f"es检索错误：{e}")
            raise
