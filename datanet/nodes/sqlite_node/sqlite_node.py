"""一个只读 SQLite 表节点，不依赖具体业务和项目配置。"""

import sqlite3
from pathlib import Path

from datanet.nodes.node import Node, NodeResult


def quote_identifier(name: str) -> str:
    """表名、列名单独引用，支持中文及双引号。"""
    if not isinstance(name, str):
        raise TypeError("表名和列名必须是字符串")
    if not name or "\x00" in name:
        raise ValueError("表名和列名不能为空或包含空字符")
    return '"' + name.replace('"', '""') + '"'


class SqliteNode(Node):
    def __init__(self, node_id: str, name: str, data_kind: str,
                 db_path: str | Path, table_name: str, key_column: str):
        super().__init__(node_id, name, data_kind)
        self.db_path = Path(db_path).resolve()
        self.table_name = table_name
        self.key_column = key_column
        self._table_sql = quote_identifier(table_name)
        self._key_sql = quote_identifier(key_column)

    def get(self, key: str) -> NodeResult:
        if not isinstance(key, str):
            raise TypeError("查询主键必须是字符串")
        try:
            # 文件缺失时报告错误，不意外创建空数据库。
            connection = sqlite3.connect(self.db_path.as_uri() + "?mode=ro", uri=True)
            try:
                connection.row_factory = sqlite3.Row
                columns = connection.execute(
                    f"PRAGMA table_info({self._table_sql})"
                ).fetchall()
                if not columns:
                    return NodeResult(status="error", errors=[f"表不存在：{self.table_name}"])
                if self.key_column not in {column["name"] for column in columns}:
                    return NodeResult(status="error", errors=[f"表缺少主键列：{self.key_column}"])
                # 最多两行即可发现重复主键；主键值使用参数绑定。
                rows = connection.execute(
                    f"SELECT * FROM {self._table_sql} WHERE {self._key_sql} = ? LIMIT 2",
                    (key,),
                ).fetchall()
            finally:
                connection.close()
        except sqlite3.Error as error:
            return NodeResult(status="error", errors=[str(error)])
        if not rows:
            return NodeResult(status="not_found")
        if len(rows) > 1:
            return NodeResult(status="error", errors=[f"主键重复：{key}"])
        return NodeResult(
            items=[dict(rows[0])],
            sources=[{
                "node_id": self.node_id,
                "database": self.db_path.as_posix(),
                "table": self.table_name,
                "key_column": self.key_column,
                "key": key,
            }],
        )
