from typing import TypedDict


class TableColumnState:
    name: str # 字段名
    type: str # 数据类型
    role: str # 字段类型(primary_key,foreign_key,measure,dimension)
    description: str # 描述信息
    examples: list[str] # 数据示例
    alias: list[str] # 字段别称


class TableState:
    name: str # 表名
    description: str # 描述信息
    role: str # 表类型
    columns: list[TableColumnState] # 字段列表


class MetricState:
    name: str # 指标名称
    description: str # 指标描述
    relevant_columns: list[str] # 关联列
    alias: list[str] # 指标别称列表


class InputState(TypedDict):
    """输入状态"""
    question: str


class OverallState(InputState):
    """主状态"""
    entities: list[str]  # 用户查询抽取的实体列表

    column_list: list[dict]  # 字段元数据列表，每个字段元数据包含字段名称、所属表、字段描述等信息
    value_list: list[dict] # 字段值列表
    metrics_list: list[dict] # 指标列表，每个指标包含指标名称、所属表、指标描述等信息

    table_info_list: list[TableState]
    metrics_info_list: list[MetricState]

    error: str  # 校验sql的错误信息
