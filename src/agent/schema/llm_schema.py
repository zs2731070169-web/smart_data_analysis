import json
from typing import Literal

from json_repair import repair_json
from pydantic import BaseModel, Field, field_validator

from build.lib.agent.schema.TableColumnInfo import SelectedTable
from infra.log.logging import logger
from utils.text_utils import clean_code_block


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


class ErrorItem(BaseModel):
    """单个校验错误项"""
    error_type: Literal["syntax", "context_missing", "semantic"] = Field(
        default="semantic",
        description=(
            "错误来源类型，必须三选一：\n"
            "  syntax        — HQL 基础语法/编译错误\n"
            "  context_missing — 字段或指标在上下文中缺失\n"
            "  semantic      — 语义错误：意图匹配偏差、时间范围偏差、指标口径偏差等"
        )
    )
    error: str = Field(
        description="错误描述，采用'预期 vs 实际 vs 差异'三段论：1.错误维度；2.预期逻辑（含具体日期推算）；3.HQL实际逻辑；4.业务差异后果")


class ValidateResult(BaseModel):
    """HQL 校验结果，无错误时 errors 为空列表"""
    errors: list[ErrorItem] = Field(description="错误列表，HQL 完全正确时为空列表")

    @field_validator('errors', mode='before')
    @classmethod
    def convert_errors(cls, value):
        """兼容 LLM 将 errors 字段以字符串形式返回的情况（含代码块包裹或 JSON 格式不完整）"""
        if isinstance(value, str):
            logger.warning(f"LLM 输出的 errors 字段是字符串，正在尝试解析，模型原始输出：{value}")
            try:
                # 清理 Markdown 标记
                value = clean_code_block(value)
                # 使用 json_repair 修复未转义引号、单引号、尾逗号等常见 JSON 问题
                return json.loads(repair_json(value, ensure_ascii=False))
            except Exception as e:
                logger.error(f"解析修复后的 JSON 失败: {e}, 原始内容: {value}")
                return []
        return value


class ErrorJudge(BaseModel):
    """判断是否是真是错误"""
    is_real_error: bool = Field(
        description="True 表示这是一个真实存在的 HQL 错误；False 表示该条目实际上是在确认 HQL 正确，属于幻觉输出")


class MissingInfo(BaseModel):
    name: str = Field(
        description="缺失字段或指标，仅当存在缺失字段或指标的时候在有效，每个元素是需要补全的字段名或指标名")
    type: Literal['metric', 'column'] = Field(description="缺失类型，是指标还是字段，值为 'metric' 或 'column'")


class ColumnCompleteInfo(BaseModel):
    """字段补全信息"""
    is_missing: bool = Field(
        description="是否存在缺失字段或指标，True 表示上下文存在字段或指标缺失；False 表示上下文字段完整或指标且够用")
    missing_list: list[MissingInfo] = Field(
        description="缺失字段或指标列表，仅当存在缺失字段或指标的时候在有效，每个元素是需要补全的字段名或指标名")
