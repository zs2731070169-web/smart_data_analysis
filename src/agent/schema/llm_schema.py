import json

from pydantic import BaseModel, Field, field_validator

from enums.types import ErrorTypes
from utils.text_utils import clean_block


class IntentCheckResult(BaseModel):
    """意图识别结果"""
    is_relevant: bool = Field(
        description="True 表示该问题属于本系统可处理的数据查询；False 表示与数据查询无关"
    )
    needs_clarification: bool = Field(
        default=False,
        description=(
            "True 表示问题与数据查询相关，但存在关键歧义，需向用户追问后才能准确执行；"
            "False 表示问题已足够明确或无需追问。"
            "仅当 is_relevant=True 时本字段才有意义。"
        )
    )
    clarification_question: str = Field(
        default="",
        description=(
            "当 needs_clarification=True 时，向用户提出的追问内容。"
            "须简洁、具体，直接点出不确定的维度或条件，并给出 2~4 个常见选项供用户参考。"
            "当 needs_clarification=False 时，本字段为空字符串。"
        )
    )
    rejection_reason: str = Field(
        default="",
        description=(
            "当 is_relevant=False 时，向用户解释为何无法处理（简短、礼貌、点明系统专注于数据查询/分析）；"
            "is_relevant=True 时为空字符串。"
        )
    )


class SelectedTable(BaseModel):
    """单张被选中的表及其字段"""
    table_name: str = Field(description="表名")
    columns: list[str] = Field(description="该表中被选中的字段名列表")


class TableColumnInfo(BaseModel):
    """表与字段过滤结果：回答用户问题所需的表和字段"""
    reasoning: str = Field(description="模型的推理过程描述，解释为什么选择这些表和字段")
    tables: list[SelectedTable] = Field(description="被选中的表与字段列表，每项包含一张表及其字段")


class MetricInfo(BaseModel):
    """指标过滤结果：回答用户问题所需的指标"""
    metrics: list[str] = Field(description="被选中的指标列表，每项是一个指标名称")


class ValidateErrorItem(BaseModel):
    """HQL 校验错误项"""
    error: str = Field(
        description="错误描述，采用【错误维度】预期逻辑 → 实际逻辑 → 差异后果 的三段论结构"
    )
    suggestion: str = Field(
        description="针对该错误的具体可落地修正建议，需包含明确的字段、值或表达式"
    )
    is_valid: bool = Field(
        description="是否校验通过，通过返回True，不通过返回False，后续处理将根据此字段进行过滤"
    )
    error_type: ErrorTypes = Field(
        description="错误类别，取值必须为 time / metric / intent / field / syntax 之一"
    )


class ValidateResult(BaseModel):
    """HQL 语义校验结果"""
    errors: list[ValidateErrorItem] = Field(
        default_factory=list,
        description="校验错误列表；HQL 无错误时返回空数组"
    )

    @field_validator('errors', mode='before')
    @classmethod
    def _coerce_errors(cls, value):
        # 任何不符合预期的输入一律降级为空数组
        try:
            if isinstance(value, str):
                # 去掉```
                value = clean_block(value.strip())
                value = json.loads(value or "[]")
            # 外层必须是 []
            if not isinstance(value, list):
                return []
            # 满足任一合法类型就返回有效校验列表
            return [item for item in value if isinstance(item, (dict, ValidateErrorItem))]
        except (json.JSONDecodeError, TypeError):
            return []
        except Exception:
            return []
