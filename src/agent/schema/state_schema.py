from dataclasses import dataclass
from typing import TypedDict, Any


@dataclass
class SysDateTime:
    current_time: str  # 当前时间，格式为"YYYY-MM-DD"
    current_quarter: str  # 当前季度


@dataclass
class DbMeta:
    version: str  # 版本号
    dialect: str  # 方言

@dataclass
class TableColumnState:
    name: str  # 字段名
    type: str  # 数据类型
    role: str  # 字段类型(primary_key,foreign_key,measure,dimension)
    description: str  # 描述信息
    examples: list[str]  # 数据示例
    alias: list[str]  # 字段别称


class TableState:
    name: str  # 表名
    description: str  # 描述信息
    role: str  # 表类型
    columns: list[TableColumnState]  # 字段列表

@dataclass
class MetricState:
    name: str  # 指标名称
    description: str  # 指标描述
    relevant_columns: list[str]  # 关联列
    alias: list[str]  # 指标别称列表


class InputState(TypedDict):
    """输入状态"""
    question: str


class OverallState(InputState):
    """主状态"""
    is_relevant: bool  # 意图识别结果

    clarification_question: str  # 意图识别阶段需要向用户追问的问题（非空则终止 pipeline 等待用户补充）

    entities: list[str]  # 用户查询抽取的实体列表

    retrieval_column_list: list[dict]  # 字段元数据列表，每个字段元数据包含字段名称、所属表、字段描述等信息
    retrieval_value_list: list[dict]  # 字段值列表
    retrieval_metrics_list: list[dict]  # 指标列表，每个指标包含指标名称、所属表、指标描述等信息

    merge_table_info_list: list[TableState]  # 合并以后的表信息列表
    merge_metrics_info_list: list[MetricState]  # 合并以后的指标信息列表

    filter_table_info_list: list[TableState]  # 过滤以后的表信息列表
    filter_metrics_info_list: list[MetricState]  # 过滤以后的指标信息列表

    expand_datetime: SysDateTime  # 扩展系统时间戳
    expand_db_metadata: DbMeta  # 扩展数据库元信息

    hql: str  # 生成的hql

    validates: list[dict[str, str]]  # hql校验列表（错误信息和优化建议）

    fix_history: list[str]  # 纠错记录
    correct_count: int  # 纠错次数

    unfound_fields: list[str]  # 累计查不到的字段/指标名（用于拼装拒答消息）
    unfound_count: int          # 连续查不到字段/指标的累计次数（达到阈值时触发熔断）

    unable_to_answer_advice: str  # generate_hql_node 判定无法回答时的建设性意见，非空则直接触发 fallback

    execute_result: list[dict[str, Any]] # 执行节点执行hql的结果


