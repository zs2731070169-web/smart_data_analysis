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

    # # 给过滤后的列表扩展维度表主键和事实表外键，用于后续连表SQL生成
    # for table_info in filter_table_info_list:
    #     table_role = table_info.role
    #     column_roles = [column.role for column in table_info.columns]
    #     # 如果是维度表且没有主键字段，那么就加上主键
    #     if 'dim' in table_role and 'primary_key' not in column_roles:
    #         primary_key = await meta_repository.get_column_primary_key_by_table_name(table_info.name)
    #         if primary_key:
    #             table_info.columns.append(TableColumnState(
    #                 name=primary_key.name,
    #                 type=primary_key.type,
    #                 role=primary_key.role,
    #                 description=primary_key.description,
    #                 examples=primary_key.examples,
    #                 alias=primary_key.alias
    #             ))
    #     # 如果是实时表，就加上外键
    #     elif 'fact' in table_role:
    #         foreign_keys = await meta_repository.get_columns_by_role_and_table_role('foreign_key', 'fact')
    #         column_names = [column.name for column in table_info.columns]
    #         # 遍历每一个外键，仅添加没有的外键
    #         for foreign_key in foreign_keys:
    #             if foreign_key.name not in column_names:
    #                 table_info.columns.append(
    #                     TableColumnState(
    #                         name=foreign_key.name,
    #                         type=foreign_key.type,
    #                         role=foreign_key.role,
    #                         description=foreign_key.description,
    #                         examples=foreign_key.examples,
    #                         alias=foreign_key.alias
    #                     )
    #                 )

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
