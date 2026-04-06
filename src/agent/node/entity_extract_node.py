import jieba
import jieba.analyse
from langgraph.runtime import Runtime

from agent.schema.context_schema import EnvContext
from agent.schema.state_schema import InputState
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


def entity_extract_node(state: InputState, runtime: Runtime[EnvContext]) -> dict[str, list[str]]:
    """
    实体抽取节点
    :param state:
    :param runtime:
    :return:
    """
    writer = runtime.stream_writer
    writer("开始执行实体抽取节点")

    try:
        question = state['question']

        # 提取实体
        entities = jieba.analyse.extract_tags(question, allowPOS=ALLOW_POS)
        entities.append(question)

        # 去除question和tags里的重复项
        entities = list(set(entities))
        logger.info(f"抽取到的实体: {entities}")

        return {"entities": entities}
    except Exception as e:
        logger.error(f"实体抽取失败: {str(e)}")
        raise Exception('实体抽取失败，请稍后重试或联系数据团队😿')
