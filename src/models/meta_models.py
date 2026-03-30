from typing import Optional, List

from sqlalchemy import String, Text, JSON, ForeignKey, Table, Column
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# column_info 与 metric_info 的多对多关联表
column_metric = Table(
    "column_metric",
    Base.metadata, # 把中间表交给sqlalchemy管理
    Column("column_id", String(64), ForeignKey("column_info.id"), primary_key=True, comment="列编号"),
    Column("metric_id", String(64), ForeignKey("metric_info.id"), primary_key=True, comment="指标编号"),
)


class TableInfo(Base):
    __tablename__ = "table_info"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="表编号")
    name: Mapped[Optional[str]] = mapped_column(String(128), comment="表名称")
    role: Mapped[Optional[str]] = mapped_column(String(32), comment="表类型(fact/dim)")
    description: Mapped[Optional[str]] = mapped_column(Text, comment="表描述")
    # back_populates设置双向绑定：当我在 TableInfo 对象里给 columns 列表加了一个新列时，请自动把那个新列对象的 table 属性设置为当前表。
    columns: Mapped[List["ColumnInfo"]] = relationship(back_populates="table")


class ColumnInfo(Base):
    __tablename__ = "column_info"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="列编号")
    name: Mapped[Optional[str]] = mapped_column(String(128), comment="列名称")
    type: Mapped[Optional[str]] = mapped_column(String(64), comment="数据类型")
    role: Mapped[Optional[str]] = mapped_column(String(32), comment="列类型(primary_key,foreign_key,measure,dimension)")
    examples: Mapped[Optional[list]] = mapped_column(JSON, comment="数据示例")
    description: Mapped[Optional[str]] = mapped_column(Text, comment="列描述")
    alias: Mapped[Optional[list]] = mapped_column(JSON, comment="列别名")
    # 外键约束：使用table_info.id外键关联table表（一对多关系）
    table_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("table_info.id"), comment="所属表编号")

    # back_populates设置双向绑定：当我在 ColumnInfo 对象里给 table 属性设置了一个新表时，请自动把那个 table 对象的 columns 列表里加上当前列。
    table: Mapped[Optional["TableInfo"]] = relationship(back_populates="columns")

    # secondary指定多对多关联表column_metric：实现对metric_info表的自动查查询，对关系表column_metric的自动管理（增删改）
    # back_populates设置双向绑定：当我在 ColumnInfo 对象里给 metrics 列表加了一个新指标时，请自动把那个新指标对象的 columns 列表里加上当前列。
    metrics: Mapped[List["MetricInfo"]] = relationship(secondary=column_metric, back_populates="columns")


class MetricInfo(Base):
    __tablename__ = "metric_info"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="指标编码")
    name: Mapped[Optional[str]] = mapped_column(String(128), comment="指标名称")
    description: Mapped[Optional[str]] = mapped_column(Text, comment="指标描述")
    relevant_columns: Mapped[Optional[list]] = mapped_column(JSON, comment="关联的列")
    alias: Mapped[Optional[list]] = mapped_column(JSON, comment="指标别名")

    # secondary指定多对多关联表column_metric：实现对metric_info表的自动查查询，对关系表column_metric的自动管理（增删改）
    # back_populates设置双向绑定：当我在 MetricInfo 对象里给 columns 列表加了一个新列时，请自动把那个新列对象的 metrics 列表里加上当前指标。
    columns: Mapped[List["ColumnInfo"]] = relationship(secondary=column_metric, back_populates="metrics")
