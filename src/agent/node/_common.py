from typing import Type, TypeVar, Any

from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_huggingface import HuggingFaceEndpointEmbeddings
from qdrant_client.models import QueryResponse

from infra.client.llm_client import expand_keywords_llm, filter_llm, general_hql_llm
from infra.log.logging import logger
from repository.qdrant.meta_repository import MetaQdrantRepository
from utils.text_utils import clean_code_block, extract_hql


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
        ("user", "用户问题\n{question}")
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


T = TypeVar('T')


async def filter_columns_or_metrics(
        query: dict[str, str],
        system_prompt: str,
        schema_cls: Type[T]
) -> T:
    """
    根据用户查询语句，使用大模型过滤召回数据里无用的表字段、指标
    :param query:
    :param schema_cls:
    :param system_prompt:
    :return:
    """
    prompt_template = ChatPromptTemplate(messages=[
        ("system", system_prompt),
        ("user", "用户问题\n{question}\n\n上下文信息\n{context}")
    ])
    chain = prompt_template | filter_llm.with_structured_output(schema_cls, method='function_calling')
    llm_output = await chain.ainvoke(query)
    return llm_output


def build_table_column_text(table_column_list) -> str:
    lines = []
    for table_info in table_column_list:
        lines.append(f"#### 📁 数据表: {table_info.name} ({table_info.role})")
        lines.append(f"内容描述: {table_info.description}")
        lines.append("字段详情:")
        for col in table_info.columns:
            # 采用紧凑的键值对形式
            examples = " / ".join(str(e) for e in col.examples) if col.examples else "无"
            alias = " / ".join(col.alias) if col.alias else "无"

            col_detail = (
                f"- **{col.name}** ({col.type}) | 角色: {col.role} | "
                f"描述: {col.description} | 示例: {examples} | 别名: {alias}"
            )
            lines.append(col_detail)
        lines.append("")  # 表间空行
    return "\n".join(lines)


def build_metric_text(metric_list) -> str:
    lines = []
    for metric in metric_list:
        lines.append(f"### {metric.name}")
        lines.append(f"> {metric.description}")
        if metric.alias:
            lines.append(f"- **别称**：{'、'.join(metric.alias)}")
        if metric.relevant_columns:
            lines.append(f"- **关联字段**：{'、'.join(metric.relevant_columns)}")
        lines.append("")
    return "\n".join(lines)


def build_datetime_text(datetime) -> str:
    if not datetime:
        return ""
    return "\n".join([
        f"- **当前时间**：{datetime.current_time}",
        f"- **当前季度**：{datetime.current_quarter}",
    ])


def build_db_metadata_text(db_meta) -> str:
    if not db_meta:
        return ""
    return "\n".join([
        f"- **数据库版本**：{db_meta.version}",
        f"- **数据库方言**：{db_meta.dialect}",
    ])


async def generate_hql(
        query: dict[str, Any],
        variables: list[str],
        system_prompt: str,
        correct_hql_llm=None
) -> str:
    """
    使用大模型生成hql
    :param variables:
    :param query:
    :param system_prompt:
    :param correct_hql_llm: 指定使用的 LLM 实例，默认使用 general_hql_llm
    :return:
    """
    # 生成sql
    prompt_template = PromptTemplate(
        template=system_prompt,
        input_variables=variables
    )
    chain = prompt_template | (correct_hql_llm or general_hql_llm) | StrOutputParser()
    hql = await chain.ainvoke(query)

    # 去掉 ``` 代码块包裹
    hql = clean_code_block(hql)
    # 若模型输出了分析文本 + HQL 的混合内容，只保留合法 HQL
    hql = extract_hql(hql)

    return hql

