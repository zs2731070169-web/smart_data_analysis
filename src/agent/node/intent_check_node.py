from langgraph.runtime import Runtime

from agent.schema.context_schema import EnvContext
from agent.schema.llm_schema import IntentCheckResult
from agent.schema.state_schema import InputState
from infra.client import filter_llm
from infra.error import LLMServiceError
from infra.log.logging import logger
from utils.history_utils import compress_history
from utils.llm_retry_utils import acall_with_retry
from utils.loader_utils import load_prompt

# 当 LLM 未给出拒答原因时使用的兜底文案
_DEFAULT_REJECTION = (
    "抱歉，我专注于数据查询与分析类问题，您的问题暂不在能力范围内。"
    "您可以尝试询问与销售、订单、客户等业务数据相关的统计或分析问题。"
)


async def intent_check_node(state: InputState, runtime: Runtime[EnvContext]) -> dict:
    """
    意图识别节点：
    - 与数据分析无关 → 拒答并终止 pipeline
    - 相关但存在关键歧义 → 输出追问内容，终止 pipeline 等待用户补充
    - 相关且明确 → 通过，进入后续节点
    :param state:
    :param runtime:
    :return:
    """
    writer = runtime.stream_writer
    writer('开始执行意图识别')

    question = state["question"] or []

    # 压缩历史对话
    messages = state.get("messages") or []
    history = compress_history(messages[:-1])

    chain = filter_llm.with_structured_output(schema=IntentCheckResult, method='function_calling')
    try:
        result: IntentCheckResult = await acall_with_retry(
            lambda: chain.ainvoke([
                {"role": "system", "content": load_prompt("intent_check.md")},
                *history,
                {"role": "user", "content": question},
            ]),
            op_name="intent_check",
        )
    except LLMServiceError as e:
        # 降级：意图判定失败不阻断对话，按"相关且明确"放行给下游主链路兜底
        # standalone_question 留空，下游通过 `or state['question']` 回退到原句
        logger.warning(
            f"意图识别 LLM 失败降级为放行: reason={e.classified.reason.value} "
            f"status={e.classified.status_code} msg={e.classified.message}"
        )
        return {"is_relevant": True, "clarification_question": "", "standalone_question": ""}

    # 改写结果兜底：LLM 未给或给了空串时回退到原问题，保证下游一定能拿到一个可用的自包含问题
    standalone = (result.standalone_question or "").strip() or question

    logger.info(
        f"意图识别结果: "
        f"{'相关' if result.is_relevant else '无关'} | "
        f"{'需追问' if result.needs_clarification else '无需追问'} | "
        f"原问题: {question} | "
        f"改写: {standalone if standalone != question else '(无需改写)'}"
    )

    # ① 无关问题 → 拒答并终止
    if not result.is_relevant:
        rejection = (result.rejection_reason or "").strip() or _DEFAULT_REJECTION
        writer(rejection)
        return {"is_relevant": False, "standalone_question": ""}

    # ② 相关但需追问 → 推送追问内容并终止，等待用户补充后再次发起
    clarification = (result.clarification_question or "").strip()
    if result.needs_clarification and clarification:
        writer(clarification)
        return {
            "is_relevant": True,
            "clarification_question": clarification,
            "standalone_question": "",
        }

    # ③ 相关且明确 → 通过；写入自包含问题供下游召回使用
    return {
        "is_relevant": True,
        "clarification_question": "",
        "standalone_question": standalone,
    }
