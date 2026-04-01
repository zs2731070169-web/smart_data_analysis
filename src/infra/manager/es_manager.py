import asyncio
from typing import Optional

from elasticsearch import AsyncElasticsearch

from infra.log import task_id_context
from infra.log.logging import logger

from conf.app_config import app_config


class EsManager:
    def __init__(self):
        self.es_client: Optional[AsyncElasticsearch] = None

    def init(self):
        try:
            self.es_client = AsyncElasticsearch(
                f"http://{app_config.es.host}:{app_config.es.port}",
                basic_auth=(app_config.es.username, app_config.es.password),
                timeout=60
            )
            logger.info("Elasticsearch 客户端初始化完成")
        except RuntimeError as e:
            logger.error(f"Elasticsearch 客户端初始化失败: {e}")
            raise

    async def close(self):
        try:
            if self.es_client:
                await self.es_client.close()
                logger.info("Elasticsearch 客户端已关闭")
        except RuntimeError as e:
            logger.error(f"Elasticsearch 客户端关闭失败: {e}")
            raise


es_manager = EsManager()

if __name__ == '__main__':
    task_id_context.set("test_task_id")


    async def main():

        es_manager.init()

        if not await es_manager.es_client.indices.exists(index="my_index"):
            # await es_manager.es_client.indices.create(index="my_index")

            await es_manager.es_client.indices.create(index="my_index", mappings={
                "properties": {
                    "foo": {"type": "text"},
                    "bar": {
                        "type": "text",
                        "fields": {
                            "keyword": {
                                "type": "keyword",
                                "ignore_above": 256,
                            }
                        },
                    },
                }
            })

        await es_manager.es_client.index(
            index="my_index",
            id="my_document_id",
            document={
                "foo": "foo",
                "bar": "bar",
            }
        )

        result = await es_manager.es_client.search(index="column_value_index", query={
            "match": {
                "value": "1"
            }
        })

        print(result)

        await es_manager.close()


    asyncio.run(main())
