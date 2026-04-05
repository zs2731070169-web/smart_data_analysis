# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Smart Data Analysis 是一个基于 LangGraph 的智能数据分析 Agent，接收用户自然语言查询，通过多阶段 pipeline 自动生成 HQL（Hive SQL）并在 Hive 数据仓库上执行，最终返回查询结果。核心技术栈：Python 3.12 + LangGraph + LangChain + FastAPI。

## 常用命令

```bash
# 依赖管理（使用 uv）
uv sync                          # 安装依赖
uv add <package>                 # 添加依赖

# 启动基础设施（MySQL、Hive、ES、Qdrant、Embedding服务）
cd docker && docker compose up -d

# 元数据索引构建（将 meta.yml 中的表/字段/指标元数据写入 MySQL、Qdrant、ES）
python -m cli.ingestion_cli --conf meta/meta.yml

# 运行基准测试（20条用例的端到端测试）
python -m agent.graph

# 需要从 src/ 目录运行，或设置 PYTHONPATH=src
```

## 架构概览

### LangGraph Agent Pipeline

用户问题经过以下节点顺序处理（见 `geaph.mmd` 中的流程图）：

```
__start__ → entity_extract → [column_retrieval, metrics_retrieval, value_retrieval]（并行）
         → merge_node → [table_filter, metric_filter]（并行）→ expand_node
         → generate_hql → validate_hql → (条件分支)
              ├── 校验通过 → execute_hql → __end__
              ├── 可纠错 → missing_complete → correct_hql → validate_hql（循环）
              └── 超限/不可恢复 → fallback → __end__
```

**关键条件分支逻辑**（`src/agent/graph.py`）：
- `validate_hql_node`：校验无错误→执行；纠错次数≥`MAX_CORRECT_COUNT`(10)→熔断；否则→补全+纠错
- `missing_complete_node`：找不到字段次数≥`MAX_UNFOUND_COUNT`(3)→熔断；否则→继续纠错

### 分层架构

```
src/
├── agent/           # LangGraph Agent 核心
│   ├── graph.py     # 图定义与编排（节点注册、边连接、条件分支）
│   ├── node/        # 各 pipeline 节点实现
│   │   ├── _common.py          # 共享函数：关键词扩展、向量召回、LLM过滤、HQL生成
│   │   ├── entity_extract_node.py   # jieba 分词实体抽取
│   │   ├── column_retrieval_node.py # Qdrant 向量检索字段元数据
│   │   ├── metrics_retrieval_node.py# Qdrant 向量检索指标元数据
│   │   ├── value_retrieval_node.py  # ES 全文检索字段值
│   │   ├── merge_node.py           # 合并召回结果，组装表结构
│   │   ├── table_filter_node.py    # LLM 过滤无关表/字段
│   │   ├── metric_filter_node.py   # LLM 过滤无关指标
│   │   ├── expand_node.py          # 扩展系统时间、数据库元信息
│   │   ├── generate_hql_node.py    # LLM 生成 HQL
│   │   ├── validate_hql_node.py    # Hive 语法校验 + LLM 语义校验 + 幻觉裁决
│   │   ├── missing_complete_node.py # 字段缺失补全
│   │   ├── correct_hql_node.py     # LLM 纠错重写 HQL
│   │   ├── execute_hql_node.py     # 在 Hive 执行 HQL 并返回结果
│   │   └── fallback_node.py        # 熔断拒答
│   └── schema/      # 状态定义
│       ├── state_schema.py    # InputState/OutputState/OverallState（LangGraph 状态）
│       ├── context_schema.py  # EnvContext（注入 repositories 和 embedding_client）
│       └── llm_schema.py      # LLM 输出结构化 schema（Pydantic）
├── cli/             # CLI 入口
│   └── ingestion_cli.py  # 元数据索引构建命令行工具
├── conf/            # 配置层
│   ├── app_config.py     # 总配置加载 + 全局常量（MAX_CORRECT_COUNT 等）
│   └── meta_config.py    # meta.yml 元数据配置 schema
├── infra/           # 基础设施层
│   ├── client/      # LLM 客户端实例（7个不同用途的 ChatOpenAI）
│   ├── factory/     # RepositoryFactory：统一管理所有数据源连接生命周期
│   ├── log/         # Loguru 日志配置 + task_id 上下文
│   └── manager/     # 各数据源管理器（MySQL/Hive/Qdrant/ES/Embedding）
├── models/          # SQLAlchemy ORM 模型（TableInfo/ColumnInfo/MetricInfo）
├── repository/      # 数据访问层
│   ├── hive/        # Hive 数据仓库（查字段类型、字段值、执行/校验 HQL）
│   ├── mysql/       # MySQL 元数据存储
│   ├── qdrant/      # Qdrant 向量检索
│   └── se/          # Elasticsearch 全文检索
├── service/         # 业务服务层
│   └── knowledge_service.py  # 知识库索引构建（meta.yml → MySQL/Qdrant/ES）
└── utils/           # 工具函数
```

### 配置体系

- **`src/application.yml`**：主配置文件，包含数据库、向量库、ES、嵌入模型、LLM 连接信息。通过 OmegaConf 加载为 `AppConfig` dataclass
- **`meta/meta.yml`**：数据仓库元数据定义（表结构、字段别名、指标定义及关联字段）
- **`prompts/`**：各节点使用的 LLM prompt 模板（Markdown 格式）

### 数据存储分工

| 存储 | 用途 |
|------|------|
| MySQL | 表/字段/指标元数据持久化（SQLAlchemy ORM） |
| Qdrant | 字段和指标的向量检索（bge-large-zh-v1.5 嵌入） |
| Elasticsearch | 字段值全文检索（IK 中文分词） |
| Hive | 数据仓库，HQL 执行目标 |

### 关键设计模式

- **RepositoryFactory**（`src/infra/factory/`）：async context manager，统一管理所有数据源连接的初始化和销毁
- **EnvContext**：通过 LangGraph 的 `context_schema` 注入，所有节点通过 `runtime.context` 访问 repositories 和 embedding_client
- **LLM 客户端分离**（`src/infra/client/llm_client.py`）：7个独立的 ChatOpenAI 实例，不同节点使用不同模型（关键词扩展用 qwen-max，HQL 生成/校验/纠错用 claude-haiku-4-5，过滤/裁决用 deepseek-v3.2）
- **Prompt 模板外置**：所有 LLM prompt 以 `.md` 文件存放在 `prompts/` 目录，通过 `load_prompt()` 加载

## 开发注意事项

- Python 源码根路径为 `src/`，模块导入以 `src/` 为基准（如 `from agent.graph import graph`）
- 所有异步操作使用 `async/await`，Hive 同步操作通过 `asyncio.to_thread()` 包装
- 配置加载使用 OmegaConf 的 `structured` + `merge` 模式，配置类均为 dataclass
- 日志使用 loguru，支持 `task_id_context` 上下文追踪
