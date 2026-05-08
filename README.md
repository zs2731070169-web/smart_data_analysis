# 智能数据分析 Agent

一个基于 LangGraph 编排的多节点流水线，实现从自然语言问题到 SQL 查询的完整转换。用户提问 → 意图检测 → 实体抽取 → 多源检索 → HQL 生成与校验 → Hive 查询 → 结果分析，每个阶段通过 FastAPI SSE 流式返回中间事件。

## 核心特性

- 🤖 **多节点 LangGraph 编排**：13+ 个节点组成的复杂工作流，支持条件分支和纠错循环
- 🧠 **智能意图理解**：快速判断问题是否与数据相关，必要时生成澄清问题
- 🔍 **多源信息检索**：并行召回字段、指标、枚举值，融合向量相似度和关键字匹配
- 💬 **自然语言转 SQL**：将用户问题转换为 HQL（Hive Query Language），支持 JOIN、GROUP BY、聚合函数等
- ✅ **自动化 SQL 校验**：利用 LLM 逐个校验 SQL 的语法、逻辑和字段正确性；出错自动纠错，支持最多 15 次循环
- ⚡ **流式响应**：每个节点的中间输出通过 SSE 实时推送，前端可实时展示分析过程
- 📊 **结果智能总结**：使用 LLM 对查询结果进行自然语言总结和解读
- 🔧 **灵活配置**：支持多个 LLM endpoint，按用途细分（检索扩展、过滤、SQL 生成、校验、结果分析）

## 快速开始

### 环境要求

- Python ≥ 3.12
- 依赖管理：[uv](https://github.com/astral-sh/uv)

### 安装与启动

```bash
# 1. 安装依赖
uv sync

# 2. 启动本地基础设施（Hive、ES、Qdrant、嵌入模型容器）
docker compose -f docker/docker-compose.yaml up -d

# 3. 构建知识库索引（从 meta/meta.yml 读取）
uv run python src/cli/ingestion_cli.py -c meta/meta.yml

# 4. 启动 API 服务（监听 0.0.0.0:8080，根路径 /smart/data/analysis）
uv run python src/api/main.py
```

### 验证安装

```bash
# 检查 LangGraph 流程图
uv run python src/agent/graph.py
```

## 项目结构

```
smart_data_analysis/
├── src/
│   ├── api/                           # FastAPI 应用
│   │   ├── main.py                   # 入口、路由、SSE 端点
│   │   ├── dependencies.py           # 依赖注入
│   │   └── schemas.py                # 请求/响应模式
│   │
│   ├── service/
│   │   ├── chat_service.py           # 驱动 LangGraph、SSE 流式处理
│   │   └── knowledge_service.py      # 知识库索引构建
│   │
│   ├── agent/
│   │   ├── graph.py                  # LangGraph 主编排文件
│   │   ├── schema/
│   │   │   ├── state_schema.py      # OverallState（累积所有中间产物）
│   │   │   └── context_schema.py    # EnvContext（运行时上下文）
│   │   └── node/                     # 13+ 个节点实现
│   │       ├── intent_check_node.py         # 意图检测
│   │       ├── entity_extract_node.py       # 实体抽取
│   │       ├── column_retrieval_node.py     # 字段检索
│   │       ├── metrics_retrieval_node.py    # 指标检索
│   │       ├── value_retrieval_node.py      # 枚举值检索
│   │       ├── merge_node.py                # 结果合并
│   │       ├── table_filter_node.py         # 表字段过滤
│   │       ├── metric_filter_node.py        # 指标过滤
│   │       ├── expand_node.py               # 关键词扩展
│   │       ├── generate_hql_node.py         # SQL 生成
│   │       ├── validate_hql_node.py         # SQL 校验
│   │       ├── execute_hql_node.py          # 查询执行
��   │       ├── generate_result_node.py      # 结果分析
│   │       └── _common.py                   # 共用工具函数
│   │
│   ├── repository/                   # 数据访问层
│   │   ├── hive_repository.py       # Hive/DW 查询
│   │   ├── meta_repository.py       # MySQL 元数据（字段/指标定义）
│   │   ├── qdrant_repository.py     # Qdrant 向量检索
│   │   ├── es_repository.py         # ES 全文检索（枚举值）
│   │   └── factory.py                # Repository 工厂 + 连接管理
│   │
│   ├── infra/
│   │   ├── client/
│   │   │   └── __init__.py          # LLM 客户端工厂（ChatOpenAI）
│   │   ├── manager/
│   │   │   ├── hive_manager.py
│   │   │   ├── mysql_manager.py
│   │   │   ├── qdrant_manager.py
│   │   │   ├── es_manager.py
│   │   │   └── embedding_manager.py
│   │   ├── factory/
│   │   │   └── repository_factory.py  # 异步上下文管理器
│   │   ├── lifespan/
│   │   │   └── lifespan.py           # FastAPI 生命周期钩子
│   │   ├── middleware/
│   │   │   └── task_id_middleware.py # 请求级 task_id
│   │   └── log/
│   │       └── loguru_config.py      # 日志配置 + task_id_context
│   │
│   ├── conf/
│   │   └── app_config.py             # 配置 dataclass 与加载逻辑
│   │
│   ├── utils/
│   │   ├── config_loader.py          # OmegaConf 配置加载
│   │   ├── prompt_loader.py          # 加载 prompts/*.md
│   │   ├── text_utils.py             # 文本处理
│   │   ├── time_utils.py             # 时间工具
│   │   └── param_parser.py           # 参数解析
│   │
│   ├── models/
│   │   └── ...                       # SQLAlchemy ORM 模型（如需）
│   │
│   ├── prompts/                      # 所有 LLM prompt（Markdown 格式）
│   │   ├── intent_check.md
│   │   ├── entity_extract.md
│   │   ├── filter.md
│   │   ├── expand_keywords.md
│   │   ├── generate_hql.md
│   │   ├── validate_hql.md
│   │   └── result_analyze.md
│   │
│   ├── application.yml               # 主配置文件
│   └── api/
│       └── ...
│
├── meta/
│   └── meta.yml                      # 知识库元数据（表/字段/指标定义）
│
├── docker/
│   └── docker-compose.yaml           # 本地依赖容器编排
│
├── pyproject.toml                    # 项目配置与依赖
├── .env.example                      # 环境变量示例
├── .gitignore
└── README.md
```

## 核心依赖

| 包 | 版本 | 用途 |
|-----|------|------|
| `fastapi[standard]` | ≥0.135.2 | Web 框架 |
| `langgraph` | ≥1.1.3 | 流程编排 |
| `langchain` | ≥1.2.13 | LLM 调用/Chain 构造 |
| `langchain-huggingface` | ≥1.2.1 | Hugging Face 集成 |
| `elasticsearch[async]` | ≥8,<9 | 全文检索 |
| `qdrant-client` | ≥1.17.1 | 向量检索 |
| `pyhive[sasl]` | ≥0.7.0 | Hive 连接 |
| `aiomysql` | ≥0.3.2 | 异步 MySQL |
| `sqlalchemy` | ≥2.0.48 | ORM |
| `omegaconf` | ≥2.3.0 | 配置管理 |
| `loguru` | ≥0.7.3 | 日志记录 |
| `python-dotenv` | ≥1.0.1 | 环境变量加载 |
| `jieba` | ≥0.42.1 | 中文分词 |
| `json-repair` | ≥0.30.0 | JSON 修复 |

## 系统架构

### LangGraph 流程图

```
                              ┌─────────────┐
                              │Intent Check │
                              └──────┬──────┘
                                     │
                    ┌────────────────┴────────────────┐
                    │                                 │
              [不相关/澄清]                        [相关]
                    │                                 │
                  END                    ┌─────────────────────┐
                                        │ Entity Extract      │
                                        └─────────┬───────────┘
                                                  │
                           ┌──────────────────────┼──────────────────────┐
                           │                      │                      │
                    ┌──────────────┐      ┌────────────────┐     ┌──────────────┐
                    │Column        │      │Metrics         │     │Value         │
                    │Retrieval     │      │Retrieval       │     │Retrieval     │
                    └──────┬───────┘      └────────┬───────┘     └───────┬──────┘
                           │                      │                      │
                           └──────────────────────┼──────────────────────┘
                                                  │
                                        ┌─────────────────┐
                                        │Merge            │
                                        └────────┬────────┘
                                                 │
                           ┌─────────────────────┼─────────────────────┐
                           │                     │                     │
                    ┌─────────────────┐  ┌──────────────────┐         │
                    │Table Filter     │  │Metric Filter     │         │
                    └────────┬────────┘  └────────┬─────────┘         │
                             │                    │                    │
                             └────────────────────┼────────────────────┘
                                                  │
                                        ┌─────────────────┐
                                        │Expand Keywords  │
                                        └────────┬────────┘
                                                 │
                                        ┌─────────────────┐
                                        │Generate HQL     │
                                        └────────┬────────┘
                                                 │
                                        ┌─────────────────┐
                                        │Validate HQL     │
                                        └────────┬────────┘
                                                 │
                        ┌────────────────────────┴────────────────────────┐
                        │                                                 │
                    [有错]                                          [通过]
                        │                                                 │
                    ┌───▼────┐                                           │
                    │纠错    │                                           │
                    │(≤15次)│                                           │
                    └───┬────┘                                           │
                        │                                    ┌────────────────┐
                        └───────────────────────────────────►│Execute HQL     │
                                                             └────────┬───────┘
                                                                      │
                                                             ┌────────────────┐
                                                             │Generate Result │
                                                             └────────┬───────┘
                                                                      │
                                                                    END
```

**关键特性**：
- **三路并行检索**：`column_retrieval`、`metrics_retrieval`、`value_retrieval` 并发执行，通过 `merge_node` fan-in
- **条件路由**：`intent_check_node` 后若问题不相关或需要澄清，直接到 END
- **纠错循环**：`validate_hql_node` 返回错误时回到 `generate_hql_node`，最多 15 次循环
- **流式事件推送**：每个节点完成后推送自定义 event，前端实时更新

### 节点说明

| 节点 | 输入 | 主要逻辑 | 输出 |
|------|------|---------|------|
| **intent_check** | question | 用 LLM 判断问题是否与数据相关 | is_relevant, clarification_question |
| **entity_extract** | question | 用 NER 模型抽取实体（表名、指标名、维度、时间等） | entities |
| **column_retrieval** | entities | 向量 + 关键字混合召回字段 | retrieval_column_list |
| **metrics_retrieval** | entities | 向量 + 关键字混合召回指标 | retrieval_metrics_list |
| **value_retrieval** | entities | 从 ES 召回枚举值 | retrieval_value_list |
| **merge** | 三路检索结果 | 融合结果，去重 | merge_columns, merge_metrics, merge_values |
| **table_filter** | merge 结果 + question | LLM 过滤字段 | filter_columns |
| **metric_filter** | merge 结果 + question | LLM 过滤指标 | filter_metrics |
| **expand** | question + 检索结果 | 关键词扩展、同义词补充 | expand_keywords |
| **generate_hql** | 所有信息 | 用 LLM 生成 HQL | hql |
| **validate_hql** | hql + 元数据 | 逐项校验语法/字段/逻辑 | validates, has_error |
| **execute_hql** | hql | 连接 Hive 执行 | execute_result |
| **generate_result** | 查询结果 + question | LLM 总结结果 | final_result |

### State 结构

**OverallState** 累积所有中间产物：

```python
@dataclass
class OverallState:
    # 输入
    question: str
    
    # intent_check 阶段
    is_relevant: bool
    clarification_question: str | None
    
    # entity_extract 阶段
    entities: list[str]
    
    # 并行检索阶段
    retrieval_column_list: list[Column]
    retrieval_metrics_list: list[Metric]
    retrieval_value_list: list[str]
    
    # merge 阶段
    merge_columns: list[Column]
    merge_metrics: list[Metric]
    merge_values: list[str]
    
    # filter 阶段
    filter_columns: list[Column]
    filter_metrics: list[Metric]
    
    # expand 阶段
    expand_keywords: list[str]
    
    # HQL 生成与校验
    hql: str
    validates: list[Validation]  # 每次校验的结果
    correct_count: int
    
    # 执行阶段
    execute_result: ExecuteResult  # SQL 执行结果 + 元数据
    
    # 最终结果
    final_result: str  # LLM 总结
```

**EnvContext** 注入运行时依赖：

```python
@dataclass
class EnvContext:
    repositories: Repositories  # 所有数据访问对象
    embedding_client: EmbeddingClient
    task_id: str
```

## 配置管理

### application.yml

主配置文件，定义数据库、LLM、向量库等连接信息：

```yaml
database:
  mysql:
    host: ${oc.env:MYSQL_HOST,localhost}
    port: 3306
    user: root
    password: ${oc.env:MYSQL_PASSWORD}
    database: meta_db

hive:
  host: ${oc.env:HIVE_HOST,localhost}
  port: 10000
  user: hive
  database: default

qdrant:
  url: ${oc.env:QDRANT_URL,http://localhost:6333}
  collection_name: meta

elasticsearch:
  hosts: [${oc.env:ES_HOST,localhost:9200}]
  index_name: values

llm:
  expand_keywords_llm:
    api_key: ${oc.env:DASHSCOPE_API_KEY}
    model: qwen-max
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
  
  general_hql_llm:
    api_key: ${oc.env:OPENAI_API_KEY}
    model: gpt-4o
    base_url: ${oc.env:OPENAI_BASE_URL}
  
  # ... 其他 LLM 配置

embedding:
  model: sentence-transformers/paraphrase-multilingual-mpnet-base-v2
  device: cuda
```

### 环境变量（.env）

敏感信息通过 `.env` 注入：

```env
DASHSCOPE_API_KEY=sk-xxx
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1
MYSQL_PASSWORD=xxx
HIVE_HOST=hive-server
QDRANT_URL=http://qdrant:6333
ES_HOST=elasticsearch:9200
```

### 配置类（app_config.py）

使用 `@dataclass` 定义配置结构，OmegaConf 自动解析：

```python
@dataclass
class LLMConfig:
    expand_keywords_llm: ChatOpenAIConfig
    filter_llm: ChatOpenAIConfig
    general_hql_llm: ChatOpenAIConfig
    validate_hql_llm: ChatOpenAIConfig
    result_analyze_llm: ChatOpenAIConfig

@dataclass
class AppConfig:
    database: DatabaseConfig
    hive: HiveConfig
    qdrant: QdrantConfig
    elasticsearch: ElasticsearchConfig
    llm: LLMConfig
    embedding: EmbeddingConfig
```

加载配置：

```python
config = load_conf("src/application.yml")
```

## FastAPI 接口

### POST /chat

实时流式聊天接口，通过 SSE 推送分析过程的每个阶段。

**请求**：
```json
{
  "question": "2024年1月用户活跃度排名前10的城市"
}
```

**响应**（Server-Sent Events）：

```
event: data
data: {"event_type": "intent_check", "data": {"is_relevant": true, "clarification_question": null}}

event: data
data: {"event_type": "entity_extract", "data": {"entities": ["2024年1月", "用户活跃度", "城市", "排名前10"]}}

event: data
data: {"event_type": "column_retrieval", "data": {"columns": ["user_id", "city", "active_days", ...], "scores": [0.95, 0.92, ...]}}

...

event: data
data: {"event_type": "final_result", "data": "基于查询结果，2024年1月用户活跃度排名前10的城市分别是..."}
```

### 事件类型

| 类型 | 说明 | 数据字段 |
|------|------|---------|
| `intent_check` | 意图检测 | is_relevant, clarification_question |
| `entity_extract` | 实体抽取 | entities |
| `column_retrieval` | 字段检索 | columns, scores |
| `metrics_retrieval` | 指标检索 | metrics, scores |
| `value_retrieval` | 枚举值检索 | values, scores |
| `merge` | 结果合并 | merge_columns, merge_metrics, merge_values |
| `table_filter` | 表字段过滤 | filter_columns |
| `metric_filter` | 指标过滤 | filter_metrics |
| `expand` | 关键词扩展 | expand_keywords |
| `generate_hql` | SQL 生成 | hql, explanation |
| `validate_hql` | SQL 校验 | validates |
| `execute_hql` | 查询执行 | execute_result, row_count |
| `generate_result` | 结果分析 | final_result |
| `error` | 错误信息 | error_message, stage |

## 节点开发

### 节点实现规范

每个节点是异步函数，参数为 `state` 和 `runtime`，返回 partial state dict：

```python
async def my_node(state: OverallState, runtime: Runtime[EnvContext]) -> dict:
    """
    节点实现示例
    
    Args:
        state: 全局状态对象
        runtime: 运行时上下文（包含 repositories、embedding_client）
    
    Returns:
        更新的 state 字段字典
    """
    # 访问数据
    env_ctx = runtime.context
    repos = env_ctx.repositories
    
    # 业务逻辑
    result = await repos.hive.execute_query(...)
    
    # 返回更新
    return {
        "my_field": result,
    }
```

### Prompt 加载

所有 LLM prompt 放在 `src/prompts/` 下的 Markdown 文件中，节点通过 `prompt_loader` 读取：

```python
from src.utils.prompt_loader import load_prompt

# 从 src/prompts/intent_check.md 读取
template = load_prompt("intent_check")

# 返回 PromptTemplate 对象，可直接用 | 链接
chain = template | llm_client | output_parser
```

Prompt 文件格式（Markdown）：

```markdown
# Intent Check Prompt

你是一个数据分析助手。判断以下问题是否与数据分析相关。

问题：{question}

如果不相关或需要澄清，返回澄清问题；否则返回 JSON：
{{"is_relevant": true}}
```

修改 prompt 只需编辑 Markdown 文件，无需改代码。

### 共用工具函数

`src/agent/node/_common.py` 包含可复用的工具：

```python
# 关键词扩展（同义词、拼音等）
async def expand_keywords(keywords: list[str], llm_client) -> list[str]:
    pass

# 向量检索
async def qdrant_retrieval(
    query: str,
    collection: str,
    top_k: int,
    embedding_client,
    qdrant_client
) -> list[RetrievalResult]:
    pass

# 字段/指标过滤
async def filter_columns_or_metrics(
    candidates: list,
    question: str,
    llm_client
) -> list:
    pass

# 构建检索文本（结构化数据转文本）
def build_column_text(column: Column) -> str:
    return f"{column.name}({column.description})"
```

## 知识库索引

通过 `meta/meta.yml` 定义表、字段、指标，然后构建向量索引和 ES 索引。

### meta.yml 格式

```yaml
tables:
  - name: user_profile
    description: 用户基本信息
    fields:
      - name: user_id
        type: string
        description: 用户ID
      - name: city
        type: string
        description: 用户所在城市
        enumeration: [北京, 上海, 深圳, ...]
  
  - name: user_activity
    description: 用户活跃度数据
    fields:
      - name: user_id
        type: string
      - name: active_days
        type: int
        description: 活跃天数

metrics:
  - name: dau
    table: user_activity
    description: 日活跃用户数
    sql: count(distinct user_id)
  
  - name: avg_active_days
    table: user_activity
    description: 平均活跃天数
    sql: avg(active_days)
```

### 构建索引

```bash
uv run python src/cli/ingestion_cli.py -c meta/meta.yml
```

该命令会：
1. 解析 `meta.yml`
2. 生成字段/指标/枚举值的向量嵌入，写入 Qdrant
3. 将枚举值索引到 ES（支持全文检索）
4. 元数据写入 MySQL（供运行时查询）

## 故障排查

### Q: LLM 返回格式错误，JSON 解析失败

**A:** 使用 `json_repair` 库自动修复 JSON。在 `_common.py` 中有一个 `repair_json_string()` 函数。

### Q: Hive 连接超时

**A:** 检查 `application.yml` 中的 Hive 主机和端口，确保 Hive 服务运行。或通过 `docker compose up -d` 启动本地 Hive 容器。

### Q: 向量检索精度低

**A:** 
- 检查 embedding 模型是否合适（当前用的是多语言模型）
- 增加向量索引的 `top_k` 参数
- 改进 `meta.yml` 中字段/指标的描述质量

### Q: SQL 生成后频繁纠错，超过 15 次循环

**A:**
- 改进 `generate_hql.md` prompt
- 检查 `meta.yml` 中的字段定义是否准确
- 增加 `validate_hql.md` 中的校验规则

### Q: 前端没有收到 SSE 事件

**A:**
- 检查 FastAPI `lifespan` 是否正确初始化连接
- 查看服务端日志（loguru），是否有异常
- 确保浏览器支持 EventSource（跨域问题可能需要 CORS 配置）

## 开发工作流

### 1. 添加新节点

1. 在 `src/agent/node/` 下创建 `my_node.py`
2. 实现 async 函数，参数为 `state` 和 `runtime`
3. 在 `src/prompts/` 下创建对应的 Markdown prompt（如需 LLM 调用）
4. 在 `src/agent/graph.py` 中注册节点和连接关系
5. 运行 `uv run python src/agent/graph.py` 检查流程图

### 2. 修改 Prompt

直接编辑 `src/prompts/` 下的 Markdown 文件，无需重新启动服务（仅需重新加载模块）。

### 3. 新增配置字段

1. 修改 `src/application.yml`
2. 在 `src/conf/app_config.py` 中对应的 dataclass 添加字段
3. 调用 `load_conf()` 时会自动解析

### 4. 添加数据源

在 `src/repository/` 下创建新 Repository 类，实现数据访问接口。在 `src/infra/manager/` 下创建对应的 Manager（管理连接生命周期）。

## 性能优化

- ✅ 并行检索：三路检索通过 LangGraph 的条件分支并发执行
- ✅ 异步 I/O：所有数据库查询使用异步驱动（aiomysql、asyncmy）
- ✅ 连接池：Hive、MySQL、Qdrant、ES 都配置了连接池
- ✅ 缓存：Qdrant 和 ES 的检索结果可在节点间复用
- ✅ 流式响应：利用 SSE 让前端实时展示过程，无需等待完成

## 许可证

[待定]

## 联系方式

[待定]
