# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Smart Data Analysis 是一个基于 LangGraph 的智能数据分析 Agent，接收用户自然语言查询，通过多阶段 pipeline 自动生成 HQL（Hive SQL）并在 Hive 数据仓库上执行，最终以流式返回查询结果。核心技术栈：Python 3.12 + LangGraph + LangChain + FastAPI。

## 常用命令

```bash
# 依赖管理（使用 uv）
uv sync                          # 安装依赖
uv add <package>                 # 添加依赖

# 启动基础设施（MySQL、Hive、ES、Qdrant、Embedding服务）
cd docker && docker compose up -d

# 元数据索引构建（将 meta.yml 中的表/字段/指标元数据写入 MySQL、Qdrant、ES）
# 需在项目根目录执行，PYTHONPATH=src
PYTHONPATH=src python -m cli.ingestion_cli --conf meta/meta.yml

# 启动 FastAPI 服务（端口 8080，API 前缀 /smart/data/analysis）
PYTHONPATH=src python src/api/main.py

# 运行基准测试（20条端到端测试用例，输出成功率/纠错轮次/耗时等多维指标）
# 需先取消 graph.py 末尾 asyncio.run(run_benchmark()) 的注释
PYTHONPATH=src python -m agent.graph
```

## 架构概览

### LangGraph Agent Pipeline

用户问题经过以下节点顺序处理（完整流程图见 `graph.mmd`）：

```
__start__ → intent_check_node → (条件分支)
              ├── 不相关 → fallback_node → __end__
              ├── 需要追问 → clarify_node → __end__   ← 推送追问内容给前端，等待用户补充后重发
              └── 相关且明确 → entity_extract_node
                               ↓ [并行]
              [column_retrieval_node, metrics_retrieval_node, value_retrieval_node]
                               ↓
                           merge_node
                               ↓ [并行]
              [table_filter_node, metric_filter_node]
                               ↓
                           expand_node → generate_hql_node → (条件分支)
              ├── 无法回答（UNABLE_TO_ANSWER: 前缀）→ fallback_node → __end__
              └── 生成HQL → validate_hql_node → (条件分支)
                    ├── 校验通过 → execute_hql_node → (条件分支)
                    │               ├── 有结果 → analyze_result_node → __end__
                    │               └── 无结果 → fallback_node → __end__
                    ├── 可纠错 → missing_complete_node → (条件分支)
                    │               ├── 字段缺失超限 → fallback_node → __end__
                    │               └── 继续 → correct_hql_node → validate_hql_node（循环）
                    └── 纠错超限 → fallback_node → __end__
```

**关键熔断阈值与退避常量**（`src/conf/app_config.py`）：
- `MAX_CORRECT_COUNT = 10`：纠错轮次上限，`validate_hql_node` 超限后触发熔断
- `MAX_UNFOUND_COUNT = 3`：连续查不到字段的累计上限，`missing_complete_node` 超限后触发熔断
- `CORRECT_BACKOFF_BASE = 1` / `CORRECT_BACKOFF_MAX = 4`：纠错节点指数退避（秒）
- `MISSING_COMPLETE_BACKOFF_BASE = 1` / `MISSING_COMPLETE_BACKOFF_MAX = 2`：字段补全节点指数退避（秒）

### 分层架构

```
src/
├── agent/           # LangGraph Agent 核心
│   ├── graph.py     # 图定义与编排（节点注册、边连接、条件分支、基准测试）
│   ├── node/        # 各 pipeline 节点实现
│   │   ├── _common.py              # 共享函数：关键词扩展、向量召回、LLM过滤、HQL生成
│   │   ├── intent_check_node.py    # 意图识别：判断问题是否与数据分析相关
│   │   ├── entity_extract_node.py  # jieba 分词实体抽取
│   │   ├── column_retrieval_node.py# Qdrant 向量检索字段元数据
│   │   ├── metrics_retrieval_node.py # Qdrant 向量检索指标元数据
│   │   ├── value_retrieval_node.py # ES 全文检索字段值
│   │   ├── merge_node.py           # 合并召回结果，组装表结构
│   │   ├── table_filter_node.py    # LLM 过滤无关表/字段
│   │   ├── metric_filter_node.py   # LLM 过滤无关指标
│   │   ├── expand_node.py          # 扩展系统时间、数据库元信息
│   │   ├── generate_hql_node.py    # LLM 生成 HQL
│   │   ├── validate_hql_node.py    # Hive 语法校验 + LLM 语义校验 + 幻觉裁决
│   │   ├── missing_complete_node.py# 字段缺失补全
│   │   ├── correct_hql_node.py     # LLM 纠错重写 HQL
│   │   ├── execute_hql_node.py     # 在 Hive 执行 HQL 并返回结果
│   │   ├── analyze_result_node.py  # LLM 对查询结果进行自然语言分析解读
│   │   └── fallback_node.py        # 熔断拒答
│   └── schema/      # 状态定义
│       ├── state_schema.py    # InputState/OverallState（LangGraph 状态，含所有中间状态字段）
│       ├── context_schema.py  # EnvContext（注入 repositories 和 embedding_client）
│       └── llm_schema.py      # LLM 输出结构化 schema（Pydantic）
├── api/             # FastAPI Web 服务
│   ├── main.py      # FastAPI 应用入口（端口 8080，路由前缀 /smart/data/analysis）
│   ├── router/chat.py  # POST /chat 接口，返回 SSE 流式响应
│   ├── dependiences.py # 依赖注入：ChatService
│   └── schema/      # 请求/响应 Pydantic schema
├── cli/             # CLI 入口
│   └── ingestion_cli.py  # 元数据索引构建命令行工具
├── conf/            # 配置层
│   ├── app_config.py     # 总配置加载（OmegaConf）+ 全局常量（MAX_CORRECT_COUNT 等）
│   └── meta_config.py    # meta.yml 元数据配置 schema
├── infra/           # 基础设施层
│   ├── client/llm_client.py   # 8个独立的 ChatOpenAI 实例（不同节点使用不同模型）
│   ├── factory/repository_factory.py  # RepositoryFactory：async context manager
│   ├── lifespan/init_client.py        # FastAPI lifespan：初始化/关闭所有连接
│   ├── log/         # Loguru 日志配置 + task_id_context 上下文追踪
│   ├── manager/     # 各数据源管理器（MySQL/Hive/Qdrant/ES/Embedding）
│   └── middware/track.py  # 请求级 context_id 注入中间件
├── models/          # SQLAlchemy ORM 模型（TableInfo/ColumnInfo/MetricInfo）
├── repository/      # 数据访问层
│   ├── hive/        # Hive 数据仓库（查字段类型、字段值、执行/校验 HQL）
│   ├── mysql/       # MySQL 元数据存储
│   ├── qdrant/      # Qdrant 向量检索
│   └── se/          # Elasticsearch 全文检索
├── service/         # 业务服务层
│   ├── chat_service.py       # ChatService：封装 graph.astream()，输出 SSE 流
│   └── knowledge_service.py  # 知识库索引构建（meta.yml → MySQL/Qdrant/ES）
└── utils/           # 工具函数
```

### 配置体系

- **`src/application.yml`**：主配置文件（不提交到 git，参考 `application.yml.example`）。支持 YAML 锚点（`&`/`*`）共享 API key，通过 OmegaConf 的 `structured` + `merge` 模式加载为 `AppConfig` dataclass
- **`meta/meta.yml`**：数据仓库元数据定义（表结构、字段别名、指标定义及关联字段）
- **`prompts/`**：各节点使用的 LLM prompt 模板（Markdown 格式），通过 `load_prompt(filename)` 加载。新节点的 prompt 拆分为 `*_system.md` + `*_user.md` 两文件；旧的单文件格式已移至 `prompts/deprecated/` 归档

### 数据存储分工

| 存储 | 用途 |
|------|------|
| MySQL | 表/字段/指标元数据持久化（SQLAlchemy ORM） |
| Qdrant | 字段和指标的向量检索（bge-large-zh-v1.5 嵌入，1024维） |
| Elasticsearch | 字段值全文检索（IK 中文分词） |
| Hive | 数据仓库，HQL 执行目标 |

### LLM 客户端分工

`src/infra/client/llm_client.py` 中定义了 8 个独立的 ChatOpenAI 实例（均兼容 OpenAI 接口），对应 `application.yml` 中 `llm.*` 的各项配置：

| 配置键 | 默认模型 | 用途 |
|--------|---------|------|
| `expand_keywords_llm` | qwen-max | 关键词扩展（entity_extract → 检索） |
| `filter_llm` | deepseek-v3.2 | 表/指标过滤 |
| `general_hql_llm` | qwen3-max | HQL 生成 |
| `validate_hql_llm` | claude-sonnet-4-6 | HQL 语义校验 |
| `correct_hql_llm` | qwen3-max | HQL 纠错重写 |
| `judge_llm` | deepseek-v3.2 | 幻觉裁决 |
| `column_complete_llm` | deepseek-v3.2 | 字段缺失补全 |
| `result_analyze_llm` | deepseek-v3.2 | 结果分析解读 |

### 关键设计模式

- **RepositoryFactory**：async context manager，统一管理所有数据源连接的初始化和销毁（基准测试使用）；FastAPI 场景下由 `lifespan/init_client.py` 管理连接，依赖注入通过 `api/dependiences.py` 完成
- **EnvContext**：通过 LangGraph 的 `context_schema` 注入，所有节点通过 `runtime.context` 访问 repositories 和 embedding_client（不经过 LangGraph 状态传播）
- **流式输出**：节点通过 `adispatch_custom_event()` 向外推送自定义事件，`chat_service.py` 以 `stream_mode=["custom"]` 消费并封装为 SSE

## 开发注意事项

- Python 源码根路径为 `src/`，所有模块导入以 `src/` 为基准（如 `from agent.graph import graph`）；运行时需设置 `PYTHONPATH=src` 或从 `src/` 目录执行
- 所有异步操作使用 `async/await`，Hive 同步操作通过 `asyncio.to_thread()` 包装
- 日志使用 loguru，`task_id_context`（contextvars）在每个请求/测试用例开始时设置，用于追踪完整链路日志
- `src/agent/node/final_evaluate_node.py` 已存在但尚未注册到 graph（待开发节点）
- `graph.py` 的 `__main__` 入口默认打印 Mermaid 图（`graph.get_graph().draw_mermaid()`），基准测试入口需手动取消注释 `asyncio.run(run_benchmark())`

### 关键实现细节

**`generate_hql_node` 拒答协议**：当 LLM 判定数据表无法满足问题时，输出以 `UNABLE_TO_ANSWER:` 为前缀的字符串。节点检测到此前缀后直接将 `correct_count` 打满至 `MAX_CORRECT_COUNT`，触发 `validate_hql_node → fallback` 分支，跳过无意义的校验/纠错循环。

**`validate_hql_node` 双阶段校验**：
1. 先调用 Hive 做语法编译（`dw_repository.validate(hql)`）；
2. 语法通过后再用 `validate_hql_llm` 做语义校验；
3. 语义校验的每条 `ErrorItem` 再经 `judge_llm` 裁决（过滤幻觉输出）。
Hive 错误码映射：`10002/10004` → `context_missing`（交 `missing_complete_node` 补全），其余 → `syntax`（直接交 `correct_hql_node` 修复）。HAVING 子句中引用 SELECT 别名触发的 10004 属语法问题，被特殊处理为 `syntax`。

**`intent_check_node` 追问机制**：`IntentCheckResult.needs_clarification=True` 时，节点返回非空 `clarification_question`，图的条件边路由至 `clarify_node`，后者通过 `stream_writer` 将追问内容推送给前端，pipeline 结束，等待用户补充后重发请求。

**所有 LLM 实例均设 `temperature=0`**；使用思考链模型（qwen3-max）时额外加 `extra_body={"enable_thinking": False}` 避免干扰 structured output 的 JSON 解析。
