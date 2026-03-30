import asyncio
from typing import Optional

from infra.log.logging import logger
from qdrant_client import AsyncQdrantClient

from conf.app_config import app_config


class QdrantManager:

    def __init__(self):
        self.qdrant_client: Optional[AsyncQdrantClient] = None

    def init(self):
        try:
            self.qdrant_client = AsyncQdrantClient(
                url=f"http://{app_config.qdrant.host}:{app_config.qdrant.port}"
            )
            logger.info("Qdrant 客户端初始化完成")
        except RuntimeError as e:
            logger.error(f"Qdrant 客户端初始化失败: {e}")
            raise

    async def close(self):
        try:
            if self.qdrant_client:
                await self.qdrant_client.close()
                logger.info("Qdrant 客户端已关闭")
        except RuntimeError as e:
            logger.error(f"Qdrant 客户端关闭失败: {e}")
            raise


qdrant_manager = QdrantManager()

if __name__ == '__main__':
    qdrant_manager.init()

    async def main():
        from qdrant_client.models import VectorParams, Distance
        if not await qdrant_manager.qdrant_client.collection_exists(collection_name="test_collection"):
            await qdrant_manager.qdrant_client.create_collection(
                collection_name="test_collection",
                vectors_config=VectorParams(size=4, distance=Distance.COSINE),
            )

        from qdrant_client.models import PointStruct
        await qdrant_manager.qdrant_client.upsert(
            collection_name="test_collection",
            wait=True, # 等待数据写入完成后再返回
            points=[
                PointStruct(id=1, vector=[0.05, 0.61, 0.76, 0.74], payload={"city": "Berlin"}),
                PointStruct(id=2, vector=[0.19, 0.81, 0.75, 0.11], payload={"city": "London"}),
                PointStruct(id=3, vector=[0.36, 0.55, 0.47, 0.94], payload={"city": "Moscow"}),
                PointStruct(id=4, vector=[0.18, 0.01, 0.85, 0.80], payload={"city": "New York"}),
                PointStruct(id=5, vector=[0.24, 0.18, 0.22, 0.44], payload={"city": "Beijing"}),
                PointStruct(id=6, vector=[0.35, 0.08, 0.11, 0.44], payload={"city": "Mumbai"}),
            ],
        )

        # noinspection PyTypeChecker
        search_result = await qdrant_manager.qdrant_client.query_points(
            collection_name="test_collection",
            query=[0.2, 0.1, 0.9, 0.7],
            with_payload=True,
            limit=3,
            score_threshold=0.8
        )

        print(search_result.points)

        await qdrant_manager.close()

    asyncio.run(main())