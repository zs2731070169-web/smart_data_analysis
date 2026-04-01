import jieba
import jieba.analyse
from langgraph.runtime import Runtime

from infra.agent.context import EnvContext
from infra.agent.state import InputState
from infra.log.logging import logger

# 对查询进行分词，只提取指定词性的词
allow_pos = (
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


def entity_extract(state: InputState, runtime: Runtime[EnvContext]) -> dict[str, list[str]]:
    """
    实体抽取节点
    :param state:
    :param runtime:
    :return:
    """
    writer = runtime.stream_writer
    writer("开始实体抽取节点")

    question = state['question']

    # 提取实体
    entities = jieba.analyse.extract_tags(question, allowPOS=allow_pos)

    # 添加问题，防止实体抽取遗漏
    entities.append(question)

    # 去除question和tags里的重复项
    entities = list(set(entities))

    logger.info(f"抽取到的实体: {entities}")

    return {"entities": entities}
