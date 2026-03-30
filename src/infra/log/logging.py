import sys
import uuid
from pathlib import Path

from loguru import logger

from conf.app_config import app_config
from infra.log import task_id_context
from utils.time_utils import any_datetime, datetime_format, DATE_FORMAT

log_format = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<magenta>task_id - {extra[task_id]}</magenta> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)


def extract_init(record):
    task_id = task_id_context.get(None)  # 不存在时返回 None，不会抛异常
    if task_id is None:
        task_id = uuid.uuid4().hex
    record["extra"]["task_id"] = task_id


logger.remove()
# 添加任务id函数
logger = logger.patch(extract_init)
# 控制台输出配置
if app_config.logging.console.enable: logger.add(sys.stdout, level=app_config.logging.console.level, format=log_format)
# 日志文件输出配置
if app_config.logging.file.enable:
    # 基于项目根目录解析日志路径，避免相对路径受工作目录影响
    root_path = Path(__file__).parents[3]
    path = root_path / app_config.logging.file.path
    path.mkdir(exist_ok=True, parents=True)
    logger.add(
        sink=path.joinpath(f"app_{datetime_format(any_datetime(), DATE_FORMAT)}.log"),
        level=app_config.logging.file.level,
        format=log_format,
        rotation=app_config.logging.file.rotation,
        retention=app_config.logging.file.retention,
    )
