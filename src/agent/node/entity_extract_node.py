import jieba
import jieba.analyse
from langgraph.runtime import Runtime

from agent.schema.context_schema import EnvContext
from agent.schema.state_schema import OverallState
from infra.log.logging import logger

# 对查询进行分词，只提取指定词性的词
ALLOW_POS = (
    "n",  # 名词: 数据、服务器、表格
    "nr",  # 人名: 张三、李四
    "ns",  # 地名: 北京、上海
    "nt",  # 机构团体名: 政府、学校、某公司
    "nz",  # 其他专有名词: Unicode、哈希算法、诺贝尔奖
    "v",  # 动词: 运行、开发
    "vn",  # 名动词: 工作、研究
    "a",  # 形容词: 美丽、快速
    "an",  # 名形词: 难度、合法性、复杂度
    "eng",  # 英文
    "i",  # 成语
    "l",  # 常用固定短语
)


def entity_extract_node(state: OverallState, runtime: Runtime[EnvContext]) -> dict[str, list[str]]:
    """
    实体抽取节点：基于意图节点改写出的自包含问题 standalone_question 做关键词抽取。
    多轮指代/省略由 intent_check_node 在 LLM 侧统一消解，这里保持纯关键词逻辑。
    """
    writer = runtime.stream_writer
    writer("开始执行实体抽取节点")

    # standalone_question 由 intent_check_node 写入；未命中或降级时回退到原问题
    question = state.get('standalone_question') or state['question']

    # 提取实体并去重；整句保留以便后续向量召回时保留原始语义
    entities = jieba.analyse.extract_tags(question, allowPOS=ALLOW_POS)
    entities.append(question)
    entities = list(set(entities))

    logger.info(f"抽取到的实体: {entities}")
    return {"entities": entities}
