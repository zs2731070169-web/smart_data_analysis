from typing import TypedDict

from langchain_huggingface import HuggingFaceEndpointEmbeddings

from infra.factory.repository_factory import Repositories


class EnvContext(TypedDict):
    repositories: Repositories  # repository实例
    embedding_client: HuggingFaceEndpointEmbeddings  # 嵌入模型实例
