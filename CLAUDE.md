# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目简介

智能数据分析 Agent：用户用自然语言提问 → LangGraph 编排的多节点流水线 → 召回字段/指标/枚举值 → 生成并校验 HQL → 在 Hive 上执行 → LLM 总结结果。FastAPI 通过 SSE 流式返回每个节点的中间事件。

## 常用命令

依赖管理使用 [uv](https://github.com/astral-sh/uv)，Python ≥ 3.12。

```powershell
# 安装依赖
uv sync

# 启动 API（监听 0.0.0.0:8080，root_path=/smart/data/analysis）
uv run python src/api/main.py

# 构建知识库索引（向量库 + ES，从 meta/meta.yml 读取）
uv run python src/cli/ingestion_cli.py -c meta/meta.yml

# 渲染 LangGraph 流程图（mermaid，写入 stdout）
uv run python src/agent/graph.py

# 启动本地依赖（Hive / ES / Qdrant / 嵌入模型容器）
docker compose -f docker/docker-compose.yaml up -d
```

注意：`pyproject.toml` 中没有定义测试 / lint 脚本，仓库目前不提供单测和静态检查。改动后请至少手动跑一次 `python src/agent/graph.py` 与对应的节点入口。

## 配置

- `src/application.yml`：主配置（DB、Hive、Qdrant、ES、Embedding、各 LLM endpoint）。被 OmegaConf 加载，通过 `${oc.env:VAR}` 注入环境变量。
- `.env`（参考 `.env.example`）：放敏感密钥，例如 `DASHSCOPE_API_KEY`、`OPENAI_PROXY_API_KEY`。`src/conf/app_config.py` 在加载 yml 前会先 `load_dotenv` 项目根目录的 `.env`。
- `meta/meta.yml`：知识库构建用的元数据（表/字段/指标定义），仅 ingestion CLI 使用。
- 配置类用 `@dataclass` 定义在 `src/conf/app_config.py`，`load_conf` 把 yml 解析成结构化对象。新加配置字段必须同时改 yml 和 dataclass。

LLM endpoint 在 `LLMConfig` 中按用途细分，不要复用：`expand_keywords_llm` / `filter_llm` / `general_hql_llm` / `validate_hql_llm` / `result_analyze_llm`。`src/infra/client/__init__.py` 在模块导入时一次性构建所有 `ChatOpenAI` 客户端，节点直接 import 用。

## 架构总览

### LangGraph 流水线（`src/agent/graph.py`）

主流程节点（按执行顺序）：

```
intent_check → entity_extract
            ├─ column_retrieval ┐
            ├─ metrics_retrieval├→ merge ─┬→ table_filter ┐
            └─ value_retrieval ─┘         └→ metric_filter┴→ expand
                                                            → generate_hql
                                                            ↻ validate_hql
                                                            → execute_hql
                                                            → generate_result
```

关键路由：
- `intent_check_node` 后，若问题与数据无关或需要追问用户（`clarification_question` 非空），直接到 END。
- `validate_hql_node` 后存在错误则回到 `generate_hql_node` 形成纠错回路；上限 `MAX_CORRECT_LOOPS = 15`（在 `graph.py` 顶部），超限直接 END。
- 三路并行召回（column / metrics / value）共同 fan-in 到 `merge_node`；table_filter 与 metric_filter 也是并行。

State：
- `InputState`：仅 `question`。
- `OverallState`（`src/agent/schema/state_schema.py`）：累积所有中间产物——`is_relevant`、`entities`、`retrieval_*_list`、`merge_*`、`filter_*`、`expand_*`、`hql`、`validates`、`correct_count`、`execute_result`。
- `EnvContext`（`src/agent/schema/context_schema.py`）：注入 `Repositories` 与 `embedding_client`，由 `ChatService` 在 invoke 时传入。

### 节点实现约定（`src/agent/node/`）

- 每个节点是 async 函数，参数是 `state, runtime: Runtime[EnvContext]`，返回 partial state dict。
- 节点共用工具集中在 `_common.py`：`expand_keywords` / `qdrant_retrieval` / `filter_columns_or_metrics` / `build_*_text`。新增 LLM 调用先看这里有没有可复用的 chain 构造。
- LLM prompt 全部放 `prompts/*.md`，节点用 `loader_utils` 读取。Prompt 文件名与节点强对应——改 prompt 不需要改代码。
- 流式中间事件通过 LangGraph 的 `custom` stream 通道推送给前端（参考 `chat_service.py`：`stream_mode=["custom"]`）。

### 分层

```
api/        FastAPI 入口、路由、依赖注入
service/    ChatService（驱动 graph）、KnowledgeService（构建索引）
agent/      LangGraph 编排、节点、state/context schema
repository/ 数据访问：hive/dw_repository、mysql/meta_repository、qdrant/meta_repository、se/value_repository
infra/
  client/   LLM 客户端工厂（OpenAI 兼容）
  manager/  Hive/MySQL/Qdrant/ES/Embedding 连接管理（init / close）
  factory/  RepositoryFactory：async context manager，统一打开/关闭所有连接
  lifespan/ FastAPI lifespan 钩子，启动时初始化连接
  middware/ 请求级 task_id 中间件
  log/      loguru 配置 + task_id_context
conf/       配置 dataclass 与加载
utils/      参数解析、配置加载、文本/时间工具
models/     SQLAlchemy ORM
cli/        ingestion 入口
```

### 数据存储职责

- **MySQL** (`db`)：表/字段/指标的元信息（结构化），由 `MetaMysqlRepository` 读写。
- **Hive** (`dw`)：业务数仓，`execute_hql_node` 在这里跑 LLM 生成的 HQL。
- **Qdrant** (`qdrant`)：向量召回字段元数据和指标元数据，集合名 `META_TABLE_COLUMN_COLLECTION` / `META_METRICS_COLLECTION`（在 `app_config.py`）。
- **Elasticsearch** (`es`)：召回字段枚举值（"用户提到'华东'要先映射到 region 字段值"），索引名 `COLUMN_VALUE_INDEX`。
- **Embedding 服务**：HuggingFace TEI 容器，托管 `BAAI/bge-large-zh-v1.5`，端口 8081。

四者由 `RepositoryFactory.__aenter__` 统一初始化 → 包装成 `Repositories` dataclass → 由 `ChatService` / `KnowledgeService` 持有。

## 开发约定

- **回复、文档、代码注释统一使用简体中文**（见用户全局指令）。
- **新增节点**：在 `src/agent/node/` 加文件 → 在 `graph.py` `add_node` + `add_edge` → state 字段加到 `OverallState`。
- **新增 LLM 用途**：在 `LLMConfig` 加字段、在 yml 加 endpoint、在 `infra/client/__init__.py` 顶层 build。
- **新增召回源**：实现 `repository/*/`，在 `RepositoryFactory` 中初始化与销毁，加入 `Repositories` dataclass，再在节点中通过 `runtime.context.repositories.<xxx>` 使用。
- **HQL 校验回路**：`correct_count` 由 `validate_hql_node` 自增；如需调整最大重试，改 `graph.py` 顶部 `MAX_CORRECT_LOOPS`。
- **Skill 安装**：仅安装到已存在的相对目录 `.claude/skills`（用户全局指令）。
