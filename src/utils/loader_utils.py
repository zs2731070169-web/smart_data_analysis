from pathlib import Path
from typing import Type, TypeVar

from omegaconf import OmegaConf

T = TypeVar("T")


def load_conf(schema_cls: Type[T], conf_path: Path) -> T:
    """
    加载指定路径下的配置文件，返回与 schema_cls 相同类型的实例
    :param schema_cls: Type[T] 表示 schema_cls 参数接收的是一个类本
    :param conf_path:
    :return:
    """
    # 加载配置文件为一个字典
    conf_content = OmegaConf.load(conf_path)
    # 创建一个schema_cls类型的structure结构
    structure = OmegaConf.structured(schema_cls)
    # 把配置文件的字典字段覆盖到structure结构相同字段
    config = OmegaConf.merge(structure, conf_content)
    # 转为 schema_cls 对象
    return OmegaConf.to_object(config)


def load_prompt(prompt: str) -> str:
    """
    根据prompt名称加载prompt文件
    :param prompt:
    :return:
    """
    path = Path(__file__).parents[2] / "prompts" / prompt
    return path.read_text(encoding="utf-8")
