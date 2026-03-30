from dataclasses import dataclass
from pathlib import Path

from utils.config_loader_utils import load_conf


# ============================== 日志配置 ==============================
@dataclass
class File:
    enable: bool
    level: str
    path: str
    rotation: str
    retention: str


@dataclass
class Console:
    enable: bool
    level: str


@dataclass
class LoggingConfig:
    file: File
    console: Console


# ============================== mysql数据库配置 ==============================
@dataclass
class DBConfig:
    host: str
    port: int
    user: str
    password: str
    database: str
    logger: bool
    pool_size: int
    max_overflow: int
    pool_timeout: int
    pool_recycle_timeout: int


# ============================== Hive数据仓库配置 ==============================
@dataclass
class HiveConfig:
    host: str
    port: int
    user: str
    database: str


# ============================== 向量库配置 ==============================
@dataclass
class QdrantConfig:
    host: str
    port: int
    embedding_size: int


# ============================== 嵌入模型配置 ==============================
@dataclass
class EmbeddingConfig:
    host: str
    port: int
    model: str


# ============================== es数据库配置 ==============================
@dataclass
class ESConfig:
    host: str
    port: int
    username: str
    password: str
    index_name: str


# ============================== 大模型配置 ==============================
@dataclass
class LLMConfig:
    model_name: str
    api_key: str


# ============================== 总配置 ==============================
@dataclass
class AppConfig:
    logging: LoggingConfig
    db: DBConfig
    dw: HiveConfig
    qdrant: QdrantConfig
    embedding: EmbeddingConfig
    es: ESConfig
    llm: LLMConfig


# 加载配置内容，返回AppConfig实例
app_config = load_conf(AppConfig, Path(__file__).parents[2] / 'src' / 'application.yml')

if __name__ == '__main__':
    print(app_config.logging.file)
