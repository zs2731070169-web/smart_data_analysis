from sqlalchemy import Connection, text, quoted_name
from tenacity import retry, stop_after_attempt, wait_exponential

from infra.log.logging import logger


class DwHiveRepository:

    def __init__(self, dw_connect: Connection):
        self.dw_connect = dw_connect

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def get_column_types(self, table_name: str):
        result = self.dw_connect.execute(text(f"DESCRIBE {table_name}"))
        rows = result.fetchall()

        column_types = {}
        for column_name, column_type, _ in rows:
            column_types[column_name] = column_type

        logger.info(f"获取表 {table_name} 字段类型成功，共 {len(column_types)} 个字段")

        return column_types

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def get_column_values(self, table_name: str, column_name: str, limit: int, offset: int = 0) -> list:
        # 反引号包裹，防止sql注入
        safe_table_name = quoted_name(table_name, quote=True)
        safe_column_name = quoted_name(column_name, quote=True)

        # 执行sql查询
        result = self.dw_connect.execute(text(f"""
            SELECT {safe_column_name} AS column_value
            FROM {safe_table_name}
            GROUP BY {safe_column_name}
            LIMIT {limit}
            OFFSET {offset}
        """))
        rows = result.fetchall()
        column_values = [row.column_value for row in rows if rows]

        if len(column_values):
            logger.info(f"获取表 {table_name} 字段 {column_name} 的值成功，共 {len(column_values)} 个值，offset={offset}")

        return column_values