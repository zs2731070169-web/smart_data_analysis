from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_huggingface import HuggingFaceEndpointEmbeddings
from qdrant_client.models import QueryResponse

from infra.client.llm_client import expand_keywords_llm
from infra.log.logging import logger
from repository.qdrant.meta_repository import MetaQdrantRepository


async def expand_keywords(question: str, entities: list[str], system_prompt: str) -> list[str]:
    """
    根据用户查询语句，使用大模型扩展用于字段召回的更多关键词
    :param question:
    :param entities:
    :param system_prompt:
    :return:
    """
    prompt_template = ChatPromptTemplate(messages=[
        ("system", system_prompt),
        ("user", "{question}")
    ])
    chain = prompt_template | expand_keywords_llm | JsonOutputParser()
    keywords = await chain.ainvoke({"question": question})

    unique_keywords = list(set(entities + keywords))

    return unique_keywords


async def qdrant_retrieval(
        collection_name: str,
        keywords: list[str],
        meta_qdrant_repository: MetaQdrantRepository,
        embedding_client: HuggingFaceEndpointEmbeddings
):
    """
    使用关键词列表从qdrant向量库里召回表字段
    :param collection_name:
    :param keywords:
    :param meta_qdrant_repository:
    :param embedding_client:
    :return:
    """
    unique_column_info_map = {}

    # 向量化每一个keyword
    embeddings: list[list[float]] = embedding_client.embed_documents(keywords)

    for embedding in embeddings:
        # 召回
        search_result: QueryResponse = await meta_qdrant_repository.search_column_payload(collection_name, embedding)
        # 获取召回的字段元数据
        column_infos = [point.payload for point in search_result.points]
        # 去重
        unique_column_info_map.update({payload['name']: payload for payload in column_infos})

    logger.info(f"召回的元数据: {unique_column_info_map.keys()}")

    unique_column_info = list(unique_column_info_map.values())

    return unique_column_info
