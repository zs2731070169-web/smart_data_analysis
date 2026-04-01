from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import Distance, PointStruct, QueryResponse
from qdrant_client.models import VectorParams
from tenacity import retry, stop_after_attempt, wait_exponential

from infra.log.logging import logger


class MetaQdrantRepository:

    def __init__(self, qdrant_client: AsyncQdrantClient):
        self.qdrant_client = qdrant_client

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def create_collection(self, collection_name: str, vector_size: int):
        """
        不存在就创建集合
        :param collection_name:
        :param vector_size:
        :return:
        """
        try:
            if await self.qdrant_client.collection_exists(collection_name=collection_name):
                # 如果 collection 已存在但向量维度不匹配（比如换了 embedding 模型），不会报错，后续 upsert 会出现难以排查的错误
                collection = await self.qdrant_client.get_collection(collection_name=collection_name)
                if collection.config.params.vectors.size != vector_size:
                    raise ValueError(f"集合 {collection} 的维度不匹配")
                logger.info(f"集合 {collection_name} 已存在，维度 {collection.config.params.vectors.size}")
            else:
                await self.qdrant_client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
                )
                logger.info(f"已创建集合 {collection_name}，维度 {vector_size}")
        except Exception as e:
            logger.error(f"创建集合失败: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def batch_add_embeddings(self, collection_name: str, points: list[PointStruct]):
        try:
            await self.qdrant_client.upsert(
                collection_name=collection_name,
                wait=True,  # 等待数据写入完成后再返回
                points=points
            )
            logger.info(f"Qdrant 批量写入完成: {len(points)} 条")
        except Exception as e:
            logger.error(f"Qdrant 批量写入失败: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def clear_all(self, collections: list[str]):
        try:
            for collection in collections:
                await self.qdrant_client.delete_collection(collection_name=collection)
                logger.info(f"已清空集合 {collection}")
        except Exception as e:
            logger.warning(f"清空原有元数据集合失败: {e}")

    async def search_column_payload(self,
                                    collection_name: str,
                                    embeddings: list[float],
                                    k_top: int=8,
                                    threshold: int=0.5
                                    ) -> QueryResponse:
        return await self.qdrant_client.query_points(
            collection_name=collection_name,
            query=embeddings,
            with_payload=True,
            limit=k_top,
            score_threshold=threshold
        )
