from typing import Any, Union

from langgraph.runtime import Runtime

from agent.schema.context_schema import EnvContext
from agent.schema.state_schema import OverallState, TableColumnState, TableState, MetricState
from infra.log.logging import logger
from models.meta_models import ColumnInfo


async def merge_node(state: OverallState, runtime: Runtime[EnvContext]):
    """
    召回结果合并节点
    :param state:
    :param runtime:
    :return:
    """
    writer = runtime.stream_writer
    writer("开始执行召回结果合并节点")

    try:
        meta_repository = runtime.context.get('repositories').meta

        # 召回的字段、字段值、指标列表
        column_list: list[dict[str, Any]] = state.get('retrieval_column_list', [])
        value_list: list[dict[str, Any]] = state.get('retrieval_value_list', [])
        metrics_list: list[dict[str, Any]] = state.get('retrieval_metrics_list', [])

        # 合并以后的表和指标列表
        table_info_list = []
        metrics_info_list = []

        # 遍历得到id -> column的映射字典
        column_map = {column['id']: column for column in column_list}

        # 把字段值添加到对应字段的example里
        for value in value_list:
            column_id = value['column_id']
            # 如果字段列表里没有这个值的字段，就从数据库查询这个字段，把值添加到这个字段的example里
            if column_id not in column_map:
                # 查询字段信息
                column_info = await meta_repository.get_column_by_id(column_id)
                if not column_info:
                    logger.warning(f"未找到字段 {column_id} 的元数据，跳过")
                    continue
                column_map.update({column_id: _convert_dict(ColumnInfo, column_info)})
            # 从字段映射字典里获取字段
            column = column_map[column_id]
            # 字段的example没有重复的值，就把值添加到这个字段的example里
            if value['value'] not in column['examples']:
                column['examples'].append(value['value'])

        logger.info("字段值合并成功")

        # 查询所有字段的表名，并构建列表, 每个元素是 table_name.column_name
        table_ids = {column['table_id'] for column in column_map.values()}
        table_name_map = await meta_repository.get_table_name_by_ids(table_ids)
        relevant_table_column_list = []
        for column in column_map.values():
            table_name = table_name_map[column['table_id']]
            relevant_table_column_list.append(f"{table_name}.{column['name']}")

        logger.info("表名-字段列表构建成功")

        # 把指标所需要的对应字段添加到字段列表
        for metrics in metrics_list:
            for relevant_column in metrics['relevant_columns']:
                # 如果指标对应的字段不在表名-字段映射字典里，就从数据库查询这个字段，并把这个字段添加到字段映射字典里
                if relevant_column not in relevant_table_column_list:
                    column_name = relevant_column.split('.')[1]
                    column_info = await meta_repository.get_column_by_metric_id(metrics['id'], column_name)
                    if column_info is None:
                        logger.warning(f"未找到指标 {metrics['id']} 对应的字段 {column_name}，跳过")
                        continue
                    column = _convert_dict(ColumnInfo, column_info)
                    column_map.update({column['id']: column})

        logger.info("指标相关字段合并成功")

        # 将字段用表id进行分组，每个表对应自己的字段
        table_column_map = {}
        for column in column_map.values():
            table_column_map.setdefault(column['table_id'], []).append(column)

        logger.info("将字段按照表id进行分组")

        # 并把表信息和字段信息进行合并，形成最终的表信息列表
        for table_id, table_columns in table_column_map.items():
            # 查询表信息
            table_info = await meta_repository.get_table_by_id(table_id)
            if table_info is None:
                logger.warning(f"未找到表 {table_id} 的元数据，跳过")
                continue
            # 遍历字段列表构建返回字段状态信息
            table_column_state_list: list[TableColumnState] = []
            for table_column in table_columns:
                table_column_state_list.append(_convert_to_table_column_state(table_column))
            # 如果是维度表，判断主键是否在该表字段列表里，如果不在则到数据库查询，并把主键字段添加到对应表字段列表
            column_roles = [table_column_state.role for table_column_state in table_column_state_list]
            if 'dim' == table_info.role and 'primary_key' not in column_roles:
                primary_key = await meta_repository.get_column_primary_key_by_table_id(table_id)
                if primary_key:
                    table_column_state_list.append(_convert_to_table_column_state(primary_key))
            # 如果是事实表，就获取他的所有主键，将table_column_state_list不存在的主键添加进去
            elif 'fact' == table_info.role:
                foreign_keys = await meta_repository.get_columns_foreign_key_by_id(table_id)
                column_name_list = [column['name'] for column in table_columns]
                for foreign_key in foreign_keys:
                    if foreign_key and foreign_key.name not in column_name_list:
                        table_column_state_list.append(_convert_to_table_column_state(foreign_key))
            # 构建表状态信息
            table_state = TableState()
            table_state.name = table_info.name
            table_state.role = table_info.role
            table_state.description = table_info.description
            table_state.columns = table_column_state_list
            # 添加到返回列表
            table_info_list.append(table_state)

        logger.info("table_info_list 表信息列表构建成功")

        # 构建指标信息列表
        for metric in metrics_list:
            metrics_info_list.append(MetricState(
                name=metric['name'],
                description=metric['description'],
                relevant_columns=metric['relevant_columns'],
                alias=metric['alias']
            ))

        logger.info("metrics_info_list 指标信息列表构建成功")

        logger.info(f"召回信息合并成功，表信息列表长度: {len(table_info_list)}，指标信息列表长度: {len(metrics_info_list)}")

        return {
            'merge_table_info_list': table_info_list,
            'merge_metrics_info_list': metrics_info_list,
        }

    except Exception as e:
        logger.error(f"召回结果合并失败: {str(e)}")
        raise Exception('召回结果合并失败，请稍后重试或联系数据团队😿')


def _convert_to_table_column_state(table_column: Union[dict[str, Any], ColumnInfo]) -> TableColumnState:
    if isinstance(table_column, dict):
        return TableColumnState(
            name=table_column.get('name', ''),
            type=table_column.get('type', ''),
            role=table_column.get('role', ''),
            description=table_column.get('description', ''),
            examples=table_column.get('examples') or [],
            alias=table_column.get('alias') or []
        )
    return TableColumnState(
        name=table_column.name or '',
        type=table_column.type or '',
        role=table_column.role or '',
        description=table_column.description or '',
        examples=table_column.examples or [],
        alias=table_column.alias or []
    )


def _convert_dict[T](orm_cls: T, obj: Any) -> dict[str, Any]:
    return {col.name: getattr(obj, col.name) for col in orm_cls.__mapper__.columns}
