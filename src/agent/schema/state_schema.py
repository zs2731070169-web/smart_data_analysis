from dataclasses import dataclass
from typing import TypedDict, Any, List, Annotated

from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages

from enums.types import ErrorTypes


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


@dataclass
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


@dataclass
class ValidateState:
    error: str  # 校验错误
    suggestion: str  # 校验建议
    error_type: ErrorTypes  # 错误类别
    is_valid: bool = False  # 校验是否通过


@dataclass
class ExecuteState:
    """HQL 执行结果"""
    columns: list[str]  # 列名顺序
    rows: list[list[Any]]  # 行数据，每行与 columns 一一对应
    row_count: int = 0  # 行数


class InputState(TypedDict):
    """输入状态"""
    question: str
    # 对话历史, add_messages会自动把节点返回的的messages字典转Message对象并进行追加
    messages: Annotated[List[AnyMessage], add_messages]


class OverallState(InputState):
    """主状态"""
    is_relevant: bool  # 意图识别结果：True=与数据查询相关，False=无关将被拒答
    clarification_question: str  # 需要向用户追问的内容；非空则终止 pipeline 等待用户补充
    standalone_question: str  # 由意图节点结合历史改写出的自包含问题；下游节点优先使用

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

    validates: list[ValidateState]  # hql校验列表
    correct_count: int  # 已发生的 generate→validate 纠错回路次数

    execute_result: ExecuteState  # 执行节点执行hql的结果
