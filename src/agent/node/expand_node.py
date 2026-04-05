import asyncio

from langgraph.runtime import Runtime

from agent.schema.context_schema import EnvContext
from agent.schema.state_schema import OverallState, DbMeta, SysDateTime
from build.lib.utils.time_utils import datetime_format
from infra.log.logging import logger
from utils.time_utils import DATE_FORMAT, now, quarter, month


async def expand_node(state: OverallState, runtime: Runtime[EnvContext]):
    """
    字段扩展节点
    :param state:
    :param runtime:
    :return:
    """
    writer = runtime.stream_writer
    writer("开始执行扩展节点")

    # meta_repository = runtime.context.get('repositories').meta
    # filter_table_info_list = state.get('filter_table_info_list', [])

    # 扩展时间
    current_time = datetime_format(now(), DATE_FORMAT)
    # 当前季度
    current_quarter = quarter(month())
    expand_datetime = SysDateTime(
        current_time=current_time,
        current_quarter=current_quarter
    )

    # 扩展数据库版本号、方言、执行环境
    dm_repository = runtime.context.get('repositories').dw
    result = await asyncio.to_thread(dm_repository.get_version)
    version = result.split()[0] or ""
    result = await asyncio.to_thread(dm_repository.is_hs2)
    is_hs2 = "hive.server2.thrift.port" in result
    if is_hs2:
        dialect = "环境确认：HiveServer2 (HS2)。语法限制：严格遵循 Hive 官方函数库，不支持 Spark 语法插件。"
    else:
        dialect = "环境确认：非原生 HS2。请优先考虑标准 SQL 兼容性。"
    expand_db_metadata = DbMeta(
        version=version,
        dialect=dialect,
    )

    logger.info(
        f"扩展后的当前时间: {current_time}, "
        f"当前季度: {current_quarter}, "
        f"hive数据库版本: {version}, "
        f"方言: {dialect}"
    )

    return {
        'expand_datetime': expand_datetime,
        'expand_db_metadata': expand_db_metadata,
    }
